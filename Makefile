.PHONY: help install test lint format clean run dev docker-up docker-down

# Default target
.DEFAULT_GOAL := help

# Ensure Poetry is in PATH
export PATH := /home/orchestrator/.local/bin:$(PATH)

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)Codetoreum - AI Agent Orchestration Platform$(NC)"
	@echo ""
	@echo "$(GREEN)Available targets:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'

install: ## Install dependencies with Poetry
	@echo "$(BLUE)Installing dependencies...$(NC)"
	poetry install
	poetry run pre-commit install

install-dev: ## Install all dependencies including dev tools
	@echo "$(BLUE)Installing all dependencies...$(NC)"
	poetry install --with dev,docs

update: ## Update dependencies
	@echo "$(BLUE)Updating dependencies...$(NC)"
	poetry update

test: ## Run all tests
	@echo "$(BLUE)Running tests...$(NC)"
	poetry run pytest -n 2

test-unit: ## Run unit tests only
	@echo "$(BLUE)Running unit tests...$(NC)"
	poetry run pytest -m unit -n 2

test-integration: ## Run integration tests only
	@echo "$(BLUE)Running integration tests...$(NC)"
	poetry run pytest -m integration -n 1

test-simulation: ## Run simulation tests only
	@echo "$(BLUE)Running simulation tests...$(NC)"
	poetry run pytest -m simulation -n 1

test-cov: ## Run tests with coverage report
	@echo "$(BLUE)Running tests with coverage...$(NC)"
	poetry run pytest -n 1 --cov=src --cov-report=html --cov-report=term-missing --cov-report=json
	@echo "$(GREEN)Coverage report generated in htmlcov/index.html$(NC)"

test-cov-enforce: ## Run tests with per-layer coverage enforcement
	@echo "$(BLUE)Running tests with per-layer coverage enforcement...$(NC)"
	python3 scripts/enforce_coverage.py
	@echo "$(GREEN)Coverage enforcement passed!$(NC)"

lint: ## Run all linters
	@echo "$(BLUE)Running linters...$(NC)"
	poetry run ruff check src/ tests/
	poetry run mypy src/

lint-fix: ## Run linters with auto-fix
	@echo "$(BLUE)Running linters with auto-fix...$(NC)"
	poetry run ruff check --fix src/ tests/

format: ## Format code with black and ruff
	@echo "$(BLUE)Formatting code...$(NC)"
	poetry run black src/ tests/
	poetry run ruff check --fix src/ tests/

format-check: ## Check code formatting without changes
	@echo "$(BLUE)Checking code formatting...$(NC)"
	poetry run black --check src/ tests/
	poetry run ruff check src/ tests/

type-check: ## Run type checking with mypy
	@echo "$(BLUE)Running type checks...$(NC)"
	poetry run mypy src/

pre-commit: ## Run pre-commit hooks on all files
	@echo "$(BLUE)Running pre-commit hooks...$(NC)"
	poetry run pre-commit run --all-files

clean: ## Clean up generated files
	@echo "$(BLUE)Cleaning up...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	find . -type f -name "coverage.xml" -delete 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "$(GREEN)Cleanup complete$(NC)"

dev: ## Run development server with auto-reload
	@echo "$(BLUE)Starting development server...$(NC)"
	poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

run: ## Run production server
	@echo "$(BLUE)Starting production server...$(NC)"
	poetry run uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4

shell: ## Open Poetry shell
	@echo "$(BLUE)Opening Poetry shell...$(NC)"
	poetry shell

docker-up: ## Start Docker services
	@echo "$(BLUE)Starting Docker services...$(NC)"
	docker-compose up -d

docker-down: ## Stop Docker services
	@echo "$(BLUE)Stopping Docker services...$(NC)"
	docker-compose down

docker-logs: ## View Docker logs
	docker-compose logs -f

docker-rebuild: ## Rebuild Docker images
	@echo "$(BLUE)Rebuilding Docker images...$(NC)"
	docker-compose build --no-cache

validate: lint type-check test ## Run all validation checks (lint, type-check, test)
	@echo "$(GREEN)All validation checks passed!$(NC)"

ci: format-check lint type-check test-cov ## Run CI pipeline locally
	@echo "$(GREEN)CI pipeline completed successfully!$(NC)"

.PHONY: docs
docs: ## Build documentation
	@echo "$(BLUE)Building documentation...$(NC)"
	poetry run mkdocs build

docs-serve: ## Serve documentation locally
	@echo "$(BLUE)Serving documentation at http://localhost:8001$(NC)"
	poetry run mkdocs serve -a localhost:8001
