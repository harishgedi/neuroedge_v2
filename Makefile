# NeuroEdge v2 — Makefile
# Usage: make <target>
# Requires: Python 3.11+, Docker, docker compose

.PHONY: install install-dev lint test test-cov run docker-up docker-down docker-logs clean help

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

install:  ## Install runtime dependencies
	pip install -r requirements.txt

install-dev:  ## Install all dependencies including dev tools
	pip install -r requirements-dev.txt

lint:  ## Run ruff linter
	ruff check . --fix

test:  ## Run unit tests
	pytest tests/ -v --tb=short

test-cov:  ## Run tests with coverage report (fails if <80%)
	pytest tests/ -v --cov=backend --cov-report=term-missing --cov-report=html --cov-fail-under=80

run:  ## Start API locally (hot reload)
	python run.py

sim:  ## Start IoT simulator (API must be running)
	python edge/iot_sim/simulator.py

docker-up:  ## Start full stack: API + Simulator + Prometheus + Grafana
	docker compose up --build -d
	@echo ""
	@echo "✅  NeuroEdge stack started:"
	@echo "   API:        http://localhost:8000"
	@echo "   Dashboard:  http://localhost:8000/ui"
	@echo "   API Docs:   http://localhost:8000/docs"
	@echo "   Prometheus: http://localhost:9090"
	@echo "   Grafana:    http://localhost:3000  (admin / neuroedge)"
	@echo ""

docker-down:  ## Stop all containers
	docker compose down

docker-logs:  ## Follow logs
	docker compose logs -f

docker-clean:  ## Stop containers and remove volumes
	docker compose down -v

audit:  ## Security audit of dependencies
	pip-audit -r requirements.txt

clean:  ## Remove build artifacts and cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .coverage coverage.xml htmlcov .ruff_cache .mypy_cache
	rm -f neuroedge.db
