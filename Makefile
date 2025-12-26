# Makefile for Algorithmic Trading Platform

.PHONY: help install test lint format clean hooks
.PHONY: docker-up docker-down docker-logs docker-ps docker-clean
.PHONY: terraform-init terraform-plan terraform-apply terraform-destroy terraform-output
.PHONY: setup-local

help:
	@echo "Available commands:"
	@echo ""
	@echo "Development:"
	@echo "  make install          - Install Python dependencies (uv sync)"
	@echo "  make hooks            - Install git hooks (pre-push checks)"
	@echo "  make test             - Run all tests"
	@echo "  make test-unit        - Run unit tests only"
	@echo "  make lint             - Run ruff linter"
	@echo "  make format           - Format code with ruff"
	@echo "  make clean            - Clean build artifacts"
	@echo ""
	@echo "Docker (Stateful Services):"
	@echo "  make docker-up        - Start all services (ClickHouse, Redis, PostgreSQL, Grafana)"
	@echo "  make docker-down      - Stop all services"
	@echo "  make docker-logs      - View logs (all services)"
	@echo "  make docker-ps        - Show service status"
	@echo "  make docker-clean     - Stop and remove all data (CAUTION!)"
	@echo ""
	@echo "Terraform (Cloud Infrastructure):"
	@echo "  make terraform-init   - Initialize Terraform"
	@echo "  make terraform-plan   - Preview infrastructure changes"
	@echo "  make terraform-apply  - Deploy to LocalStack/AWS"
	@echo "  make terraform-destroy - Destroy infrastructure"
	@echo "  make terraform-output - Show outputs (S3, Kinesis URLs)"
	@echo ""
	@echo "Quick Setup:"
	@echo "  make setup-local      - Complete local setup (Docker + Terraform)"

install:
	@echo "Installing dependencies with uv..."
	uv sync

hooks:
	@echo "Installing git hooks..."
	./scripts/install-hooks.sh

test:
	@echo "Running all tests..."
	uv run pytest tests/ -v --tb=short

test-unit:
	@echo "Running unit tests..."
	uv run pytest tests/unit/ -v

lint:
	@echo "Running ruff linter..."
	uv run ruff check . --fix

format:
	@echo "Formatting code with ruff..."
	uv run ruff format .

# ============================================
# DOCKER COMMANDS
# ============================================

docker-up:
	@echo "Starting all Docker services..."
	docker-compose -f infrastructure/docker/docker-compose.yml up -d
	@echo "Services started! Access:"
	@echo "  ClickHouse:  http://localhost:8123"
	@echo "  Redis:       localhost:6379"
	@echo "  PostgreSQL:  localhost:5432"
	@echo "  Prometheus:  http://localhost:9090"
	@echo "  Grafana:     http://localhost:3000 (admin/admin)"

docker-down:
	@echo "Stopping all Docker services..."
	docker-compose -f infrastructure/docker/docker-compose.yml down

docker-logs:
	docker-compose -f infrastructure/docker/docker-compose.yml logs -f

docker-ps:
	docker-compose -f infrastructure/docker/docker-compose.yml ps

docker-clean:
	@echo "WARNING: This will delete all data!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker-compose -f infrastructure/docker/docker-compose.yml down -v; \
		echo "All data removed!"; \
	fi

# ============================================
# TERRAFORM COMMANDS
# ============================================

terraform-init:
	@echo "Initializing Terraform..."
	cd infrastructure/terraform/aws && terraform init

terraform-plan:
	@echo "Planning Terraform changes..."
	cd infrastructure/terraform/aws && terraform plan -var-file=environments/local.tfvars

terraform-apply:
	@echo "Applying Terraform changes..."
	cd infrastructure/terraform/aws && terraform apply -var-file=environments/local.tfvars -auto-approve
	@echo "Generating .env.terraform..."
	cd infrastructure/terraform/aws && terraform output -raw env_file_format > ../../../.env.terraform
	@echo "Done! Check .env.terraform for resource details"

terraform-destroy:
	@echo "Destroying Terraform infrastructure..."
	cd infrastructure/terraform/aws && terraform destroy -var-file=environments/local.tfvars

terraform-output:
	cd infrastructure/terraform/aws && terraform output

# ============================================
# QUICK SETUP
# ============================================

setup-local:
	@echo "Setting up complete local environment..."
	@echo ""
	@echo "Step 1/3: Starting Docker services..."
	$(MAKE) docker-up
	@echo ""
	@echo "Step 2/3: Initializing Terraform..."
	$(MAKE) terraform-init
	@echo ""
	@echo "Step 3/3: Deploying to LocalStack..."
	$(MAKE) terraform-apply
	@echo ""
	@echo "Setup complete! ✅"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Copy .env.terraform values to .env"
	@echo "  2. Run 'make docker-ps' to verify services"
	@echo "  3. Access Grafana at http://localhost:3000"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.pyo' -delete
	find . -type d -name '*.egg-info' -exec rm -rf {} +
	rm -rf build/ dist/ .pytest_cache/ .coverage htmlcov/
