from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import settings, load_adls_sources
from app.database import db
from app.api.extracts import router as extracts_router
from app.api.push_jobs import router as push_jobs_router
from app.api.medallion import router as medallion_router
from app.api.poller import router as poller_router
from app.services.poller_registry import PollerRegistry
from app.services.medallion_orchestrator import MedallionOrchestratorService
import logging
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Disable verbose logs from external libraries
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("azure.identity").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting INS Orchestrator API...")
    try:
        # Test pipeline database connection (if configured)
        if db:
            try:
                conn = db.get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.close()
                logger.info("Pipeline database connection established")
            except Exception as db_err:
                logger.warning(f"Pipeline DB connection failed (non-fatal): {db_err}")
        else:
            logger.info("Pipeline database not configured — skipping")

        # Auto-start ADLS pollers (supports N sources)
        sources = load_adls_sources()
        if sources:
            PollerRegistry.initialize(sources)
            try:
                results = await PollerRegistry.start_all()
                for source_id, started in results.items():
                    if started:
                        logger.info(f"ADLS poller '{source_id}' auto-started")
                    else:
                        logger.info(f"ADLS poller '{source_id}' skipped (disabled or already running)")
            except Exception as poller_err:
                logger.warning(f"ADLS poller auto-start failed (non-fatal): {poller_err}")
        else:
            logger.info("No ADLS poller sources configured — skipping auto-start")

        # Auto-start medallion orchestrator (if DB is configured)
        if db:
            try:
                await MedallionOrchestratorService.start()
                logger.info("Medallion orchestrator auto-started")
            except Exception as med_err:
                logger.warning(f"Medallion orchestrator auto-start failed (non-fatal): {med_err}")

    except Exception as e:
        logger.error(f"Failed to initialize application: {str(e)}")

    yield

    # Shutdown
    logger.info("Shutting down INS Orchestrator API...")

    # Stop medallion orchestrator (if running)
    await MedallionOrchestratorService.stop()
    logger.info("Medallion orchestrator stopped")

    # Stop all ADLS pollers
    await PollerRegistry.stop_all()
    logger.info("All ADLS pollers stopped")

    # Close pipeline database connection
    if db:
        db.close()
        logger.info("Pipeline database connection closed")


# Create FastAPI app
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="INS Orchestrator — Pipeline management, ADLS poller, and Fabric notebook trigger",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(extracts_router)
app.include_router(push_jobs_router)
app.include_router(medallion_router)
app.include_router(poller_router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "INS Orchestrator API",
        "version": settings.api_version,
        "status": "running",
        "endpoints": {
            "extracts": "/extracts",
            "push_jobs": "/push-jobs",
            "medallion_sync": "/medallion-sync",
            "medallion_orchestrator": "/medallion-sync/orchestrator",
            "medallion_dashboard": "/medallion-sync/dashboard",
            "poller": "/poller",
        },
        "docs": {
            "swagger": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
        },
    }


@app.get("/health")
async def health_check():
    """Lightweight health check for Azure probe — no DB calls."""
    return {"status": "healthy"}


@app.get("/health/deep")
async def health_check_deep():
    """Deep health check with DB connectivity test."""
    db_status = "not configured"
    if db:
        try:
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            db_status = "connected"
        except Exception as e:
            logger.error(f"Deep health check failed: {str(e)}")
            raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")

    return {
        "status": "healthy",
        "database": db_status,
        "poller": PollerRegistry.get_aggregate_status().model_dump(),
        "poller_sources": [s.model_dump() for s in PollerRegistry.list_sources()],
        "medallion_orchestrator": MedallionOrchestratorService.get_status(),
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8001"))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
        access_log=False,
    )
