#!/usr/bin/env python3
"""
Logging utility for Fabric Deployment System
Provides consistent logging configuration across all modules
"""

import os
import logging
import colorlog
from pathlib import Path
from datetime import datetime
from typing import Optional

# Create logs directory if it doesn't exist
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def setup_logger(
    name: str, level: Optional[str] = None, log_file: Optional[str] = None
) -> logging.Logger:
    """
    Setup a logger with colored console output and file logging

    Args:
        name: Logger name (usually __name__)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional specific log file name

    Returns:
        Configured logger instance
    """
    # Get log level from environment or parameter
    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO")

    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Console handler with color
    console_handler = colorlog.StreamHandler()
    console_handler.setLevel(numeric_level)

    # Color format for console
    console_format = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s%(reset)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler
    if log_file is None:
        # Default log file name based on date
        log_file = f"deployment_{datetime.now().strftime('%Y%m%d')}.log"

    file_path = LOG_DIR / log_file
    file_handler = logging.FileHandler(file_path, mode="a")
    file_handler.setLevel(logging.DEBUG)  # Always log everything to file

    # Simple format for file (no colors)
    file_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get an existing logger or create a new one

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger


class DeploymentLogger:
    """
    Specialized logger for deployment operations with structured logging
    """

    def __init__(self, customer_id: str, environment: str, mode: str):
        """
        Initialize deployment logger

        Args:
            customer_id: Customer identifier
            environment: Target environment
            mode: Deployment mode
        """
        self.customer_id = customer_id
        self.environment = environment
        self.mode = mode

        # Create dedicated log file for this deployment
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = f"{customer_id}_{environment}_{mode}_{timestamp}.log"

        self.logger = setup_logger(
            f"deployment.{customer_id}.{environment}", log_file=log_file
        )

        # Log deployment start
        self.logger.info("=" * 80)
        self.logger.info("Deployment Started")
        self.logger.info(f"Customer: {customer_id}")
        self.logger.info(f"Environment: {environment}")
        self.logger.info(f"Mode: {mode}")
        self.logger.info(f"Timestamp: {timestamp}")
        self.logger.info("=" * 80)

    def log_step(self, step: str, message: str, level: str = "INFO"):
        """
        Log a deployment step with structure

        Args:
            step: Step identifier
            message: Log message
            level: Log level
        """
        formatted_message = f"[{step}] {message}"
        getattr(self.logger, level.lower())(formatted_message)

    def log_item_deployment(
        self, item_type: str, item_name: str, status: str, details: Optional[str] = None
    ):
        """
        Log individual item deployment

        Args:
            item_type: Type of Fabric item
            item_name: Name of the item
            status: Deployment status (SUCCESS, FAILED, SKIPPED)
            details: Additional details
        """
        message = f"[ITEM] {item_type}/{item_name} - {status}"
        if details:
            message += f" - {details}"

        if status == "FAILED":
            self.logger.error(message)
        elif status == "SKIPPED":
            self.logger.warning(message)
        else:
            self.logger.info(message)

    def log_validation(
        self, check_name: str, result: bool, message: Optional[str] = None
    ):
        """
        Log validation check result

        Args:
            check_name: Name of validation check
            result: Pass/fail result
            message: Additional message
        """
        status = "PASSED" if result else "FAILED"
        log_message = f"[VALIDATION] {check_name} - {status}"
        if message:
            log_message += f" - {message}"

        if result:
            self.logger.info(log_message)
        else:
            self.logger.error(log_message)

    def log_error(self, error: Exception, context: Optional[str] = None):
        """
        Log an error with full details

        Args:
            error: Exception object
            context: Context where error occurred
        """
        error_type = type(error).__name__
        error_message = str(error)

        log_message = f"[ERROR] {error_type}: {error_message}"
        if context:
            log_message = f"[ERROR] [{context}] {error_type}: {error_message}"

        self.logger.error(log_message)
        self.logger.debug("Stack trace:", exc_info=True)

    def log_summary(
        self, items_deployed: int, errors: int, warnings: int, duration: float
    ):
        """
        Log deployment summary

        Args:
            items_deployed: Number of items successfully deployed
            errors: Number of errors
            warnings: Number of warnings
            duration: Deployment duration in seconds
        """
        self.logger.info("=" * 80)
        self.logger.info("Deployment Summary")
        self.logger.info(f"Items Deployed: {items_deployed}")
        self.logger.info(f"Errors: {errors}")
        self.logger.info(f"Warnings: {warnings}")
        self.logger.info(f"Duration: {duration:.2f} seconds")

        if errors > 0:
            self.logger.error("Deployment completed with errors")
        elif warnings > 0:
            self.logger.warning("Deployment completed with warnings")
        else:
            self.logger.info("Deployment completed successfully")

        self.logger.info("=" * 80)


# Utility function for one-off logging
def log_message(
    message: str, level: str = "INFO", logger_name: str = "fabric_deployment"
):
    """
    Quick logging without setting up a logger

    Args:
        message: Message to log
        level: Log level
        logger_name: Logger name to use
    """
    logger = get_logger(logger_name)
    getattr(logger, level.lower())(message)


# Configure root logger to prevent propagation issues
def configure_root_logger():
    """Configure the root logger with basic settings"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Suppress noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("azure").setLevel(logging.WARNING)


# Auto-configure root logger on import
configure_root_logger()


if __name__ == "__main__":
    """Test the logging functionality"""

    # Test basic logger
    logger = setup_logger("test_logger", level="DEBUG")
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    logger.critical("This is a critical message")

    # Test deployment logger
    deploy_logger = DeploymentLogger("test-customer", "dev", "full")
    deploy_logger.log_step("INIT", "Initializing deployment")
    deploy_logger.log_item_deployment("Notebook", "MyNotebook", "SUCCESS")
    deploy_logger.log_item_deployment(
        "Report", "MyReport", "FAILED", "Connection error"
    )
    deploy_logger.log_validation("check_workspace_exists", True)
    deploy_logger.log_validation("check_capacity", False, "Capacity not found")

    try:
        raise ValueError("Test error for logging")
    except Exception as e:
        deploy_logger.log_error(e, "Testing error logging")

    deploy_logger.log_summary(items_deployed=10, errors=2, warnings=5, duration=120.5)

    print(f"\nLog files created in: {LOG_DIR}")
