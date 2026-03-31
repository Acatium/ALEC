# ALEC Development Makefile
# Usage: make help

.PHONY: help test test-docker test-local test-setup lint format typecheck build up down logs clean

# Default target
help:
	@echo "ALEC Development Commands"
	@echo ""
	@echo "Testing:"
	@echo "  make test        Run tests (Docker preferred, falls back to local)"
	@echo "  make test-docker Run tests in Docker container"
	@echo "  make test-local  Run tests using local virtualenv"
	@echo "  make test-setup  Set up local test environment"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint        Run ruff linter"
	@echo "  make format      Format code with black and isort"
	@echo "  make typecheck   Run mypy type checker"
	@echo ""
	@echo "Docker:"
	@echo "  make build       Build all Docker images"
	@echo "  make up          Start all services"
	@echo "  make down        Stop all services"
	@echo "  make logs        Tail service logs"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean       Remove build artifacts and caches"

# =============================================================================
# Testing
# =============================================================================

test: ## Run tests (auto-selects Docker or local)
	@if command -v docker-compose >/dev/null 2>&1; then \
		echo "Running tests in Docker..."; \
		docker-compose --profile test run --rm test-runner pytest core/ -v --tb=short; \
	elif [ -f .venv/bin/pytest ]; then \
		echo "Running tests with local venv..."; \
		.venv/bin/pytest core/ -v --tb=short; \
	else \
		echo "❌ No test environment. Run: make test-setup"; \
		exit 1; \
	fi

test-docker: ## Run tests in Docker container
	docker-compose --profile test run --rm test-runner pytest core/ -v --tb=short

test-local: ## Run tests using local virtualenv
	@if [ -f .venv/bin/pytest ]; then \
		.venv/bin/pytest core/ -v --tb=short; \
	else \
		echo "❌ Local venv not found. Run: make test-setup"; \
		exit 1; \
	fi

test-setup: ## Set up local test environment
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements-dev.txt
	@echo ""
	@echo "✅ Test environment ready!"
	@echo "   Run tests: make test-local"
	@echo "   Or activate: source .venv/bin/activate"

# =============================================================================
# Code Quality
# =============================================================================

lint: ## Run ruff linter
	@if [ -f .venv/bin/ruff ]; then \
		.venv/bin/ruff check core/; \
	elif command -v ruff >/dev/null 2>&1; then \
		ruff check core/; \
	else \
		echo "ruff not found. Run: make test-setup"; \
		exit 1; \
	fi

format: ## Format code with black and isort
	@if [ -f .venv/bin/black ]; then \
		.venv/bin/black core/ && .venv/bin/isort core/; \
	elif command -v black >/dev/null 2>&1; then \
		black core/ && isort core/; \
	else \
		echo "black/isort not found. Run: make test-setup"; \
		exit 1; \
	fi

typecheck: ## Run mypy type checker
	@if [ -f .venv/bin/mypy ]; then \
		.venv/bin/mypy core/ --ignore-missing-imports; \
	elif command -v mypy >/dev/null 2>&1; then \
		mypy core/ --ignore-missing-imports; \
	else \
		echo "mypy not found. Run: make test-setup"; \
		exit 1; \
	fi

# =============================================================================
# Docker
# =============================================================================

build: ## Build all Docker images
	docker-compose build --quiet

build-test: ## Build test runner image
	docker-compose --profile test build test-runner

up: ## Start all services
	docker-compose up -d --quiet-pull

down: ## Stop all services
	docker-compose down

logs: ## Tail service logs
	docker-compose logs -f

# =============================================================================
# Cleanup
# =============================================================================

clean: ## Remove build artifacts and caches
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✓ Cleaned build artifacts"
