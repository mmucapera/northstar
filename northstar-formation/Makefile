.PHONY: install dev lint format test coverage clean build docs ci help sync lock

# Default target
.DEFAULT_GOAL := help

# Install production dependencies
install:
	uv sync --no-dev

# Install development dependencies
dev:
	uv sync
	uv run pre-commit install

# Sync dependencies (update lockfile and install)
sync:
	uv sync

# Update lockfile
lock:
	uv lock

# Run linters
lint:
	uv run ruff check src/ tests/
	uv run mypy src/

# Format code
format:
	uv run ruff format src/ tests/
	uv run ruff check src/ tests/ --fix

# Run tests
test:
	uv run pytest tests/ -v

# Run tests with coverage
coverage:
	uv run pytest tests/ --cov=northstar_formation --cov-report=html --cov-report=term-missing
	@echo "Coverage report: file://$(PWD)/htmlcov/index.html"

# Clean build artifacts
clean:
	rm -rf build/ dist/ *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov/ .coverage coverage.xml coverage_html/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Build package
build: clean
	uv build

# Generate documentation
docs:
	uv run mkdocs serve

# Run all checks (CI simulation)
ci: lint test

# Type check only
typecheck:
	uv run mypy src/

# Run tests in parallel
test-parallel:
	uv run pytest tests/ -v -n auto

# Run only unit tests
test-unit:
	uv run pytest tests/unit -v

# Run only integration tests
test-integration:
	uv run pytest tests/integration -v -m integration

# Show help
help:
	@echo "Northstar Formation - Available Commands"
	@echo "==================================="
	@echo ""
	@echo "Development:"
	@echo "  make dev          Install dev dependencies and pre-commit hooks"
	@echo "  make install      Install production dependencies only"
	@echo "  make sync         Sync dependencies from lockfile"
	@echo "  make lock         Update uv.lock file"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint         Run ruff and mypy linters"
	@echo "  make format       Format code with ruff"
	@echo "  make typecheck    Run mypy type checking only"
	@echo ""
	@echo "Testing:"
	@echo "  make test         Run all tests"
	@echo "  make test-parallel Run tests in parallel"
	@echo "  make coverage     Run tests with coverage report"
	@echo ""
	@echo "Build:"
	@echo "  make build        Build the package"
	@echo "  make clean        Clean build artifacts"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs         Serve documentation locally"
	@echo ""
	@echo "CI:"
	@echo "  make ci           Run all checks (lint + test)"
