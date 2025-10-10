# Makefile for PM Arbitrage Bot

.PHONY: help setup install dev test lint typecheck format clean paper live backtest doctor discovery discovery-record docker-build docker-run

# Default target
help:
	@echo "PM Arbitrage Bot - Available Commands:"
	@echo ""
	@echo "Setup:"
	@echo "  setup          - Set up development environment"
	@echo "  install        - Install production dependencies"
	@echo "  dev            - Install development dependencies"
	@echo ""
	@echo "Development:"
	@echo "  test           - Run test suite"
	@echo "  lint           - Run linting checks"
	@echo "  typecheck      - Run type checking"
	@echo "  format         - Format code"
	@echo "  clean          - Clean build artifacts"
	@echo ""
	@echo "Health & Discovery:"
	@echo "  doctor         - Run health check"
	@echo "  discovery      - Run discovery mode"
	@echo "  discovery-record - Run discovery with data recording"
	@echo ""
	@echo "Running:"
	@echo "  paper          - Run paper trading"
	@echo "  live           - Run live trading (requires CONFIRM_LIVE=true)"
	@echo "  backtest       - Run backtest (requires data file)"
	@echo ""
	@echo "Docker:"
	@echo "  docker-build   - Build Docker image"
	@echo "  docker-run     - Run Docker container"
	@echo "  docker-compose - Start all services with docker-compose"

# Setup development environment
setup:
	@echo "Setting up development environment..."
	/usr/local/bin/python3.13 -m venv venv
	. venv/bin/activate && pip install --upgrade pip
	. venv/bin/activate && pip install -e ".[dev]"
	@echo "Development environment ready!"
	@echo "Activate with: source venv/bin/activate"

# Install production dependencies
install:
	pip install -e .

# Install development dependencies
dev:
	pip install -e ".[dev]"

# Run tests
test:
	pytest tests/ -v --cov=src --cov-report=term-missing

# Run linting
lint:
	/usr/local/bin/python3.13 -m ruff check src/ tests/

# Run type checking
typecheck:
	/usr/local/bin/python3.13 -m mypy src/

# Format code
format:
	/usr/local/bin/python3.13 -m ruff format src/ tests/
	/usr/local/bin/python3.13 -m black src/ tests/

# Clean build artifacts
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Run paper trading
paper:
	/usr/local/bin/python3.13 -m src.scripts.run_paper

# Run live trading (requires confirmation)
live:
	@if [ "$(CONFIRM_LIVE)" != "true" ]; then \
		echo "ERROR: Live trading requires CONFIRM_LIVE=true"; \
		echo "Set environment variable: export CONFIRM_LIVE=true"; \
		exit 1; \
	fi
	/usr/local/bin/python3.13 -m src.scripts.run_live

# Run backtest
backtest:
	/usr/local/bin/python3.13 scripts/backtest_cli.py --data data/quotes_sample.parquet --start 2025-01-01 --end 2025-01-31

# Run health check
doctor:
	/usr/local/bin/python3.13 scripts/doctor.py

# Run discovery mode
discovery:
	/usr/local/bin/python3.13 scripts/run_discovery.py --poll-ms 1500

# Run discovery with data recording
discovery-record:
	/usr/local/bin/python3.13 scripts/run_discovery.py --poll-ms 1500 --record data/quotes_sample.parquet

# Build Docker image
docker-build:
	docker build -t pm-arb .

# Run Docker container
docker-run:
	docker run --env-file .env pm-arb

# Start all services with docker-compose
docker-compose:
	docker-compose up -d

# Stop all services
docker-stop:
	docker-compose down

# View logs
docker-logs:
	docker-compose logs -f

# Database operations
db-migrate:
	@echo "Running database migrations..."
	# Add migration commands here

db-reset:
	@echo "Resetting database..."
	rm -f pm_arb.db

# Security checks
security:
	bandit -r src/
	safety check

# Performance testing
perf-test:
	pytest tests/ -k "perf" --benchmark-only

# Documentation
docs:
	@echo "Generating documentation..."
	# Add documentation generation commands here

# Release
release:
	@echo "Creating release..."
	# Add release commands here
