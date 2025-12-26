#!/usr/bin/env python3
"""
Script to initialize the Algorithmic Trading Platform project structure.
Creates all directories and __init__.py files.
"""

from pathlib import Path


def create_structure():
    """Create the complete project structure."""

    base_path = Path(__file__).parent.parent  # DataPlatform/

    # Define the complete structure
    structure = {
        "config": [
            "environments",
            "providers",
        ],
        "core": [
            "interfaces",
            "models",
            "exceptions",
            "utils",
        ],
        "providers": [
            "aws",
            "gcp",
            "azure",
            "localstack",
            "s3_compatible",
            "opensource",
        ],
        "factory": [],
        "domain": [
            "strategies",
            "indicators",
            "risk",
            "backtesting",
            "execution",
        ],
        "services": [
            "market_data_ingestion",
            "stream_processor",
            "strategy_engine",
            "trading_api/routes",
            "ml_pipeline",
        ],
        "infrastructure": [
            "cdk/stacks",
            "terraform/modules/storage",
            "terraform/modules/streaming",
            "terraform/modules/compute",
            "docker",
            "kubernetes/deployments",
            "kubernetes/services",
            "kubernetes/configmaps",
        ],
        "scripts": [],
        "notebooks": [],
        "tests": [
            "unit/test_providers",
            "integration",
            "fixtures",
        ],
        "data": [
            "raw",
            "processed",
            "models",
            "backtest_results",
            "logs",
        ],
        "docs": [
            "diagrams",
        ],
        "monitoring": [
            "grafana/dashboards",
            "grafana/provisioning",
            "prometheus",
        ],
    }

    created_dirs = []
    created_files = []

    # Create directories and __init__.py files
    for parent, subdirs in structure.items():
        parent_path = base_path / parent

        # Create parent directory
        if not parent_path.exists():
            parent_path.mkdir(parents=True, exist_ok=True)
            created_dirs.append(str(parent_path.relative_to(base_path)))

        # Create __init__.py in parent
        init_file = parent_path / "__init__.py"
        if not init_file.exists():
            init_file.write_text('"""' + parent.capitalize() + ' package."""\n')
            created_files.append(str(init_file.relative_to(base_path)))

        # Create subdirectories
        if subdirs:
            for subdir in subdirs:
                subdir_path = parent_path / subdir
                if not subdir_path.exists():
                    subdir_path.mkdir(parents=True, exist_ok=True)
                    created_dirs.append(str(subdir_path.relative_to(base_path)))

                # Create __init__.py in subdirectory (skip non-Python dirs)
                if not any(
                    x in str(subdir_path)
                    for x in ["terraform", "docker", "kubernetes", "grafana", "prometheus"]
                ):
                    init_file = subdir_path / "__init__.py"
                    if not init_file.exists():
                        # Get package name from path
                        pkg_name = subdir.split("/")[-1].replace("_", " ").title()
                        init_file.write_text(f'"""{pkg_name} module."""\n')
                        created_files.append(str(init_file.relative_to(base_path)))

    # Create root-level files if they don't exist
    root_files = {
        ".env.example": """# Environment Configuration Template
# Copy this file to .env.local or .env.production and fill in values

# Environment
ENVIRONMENT=local  # local, dev, staging, production

# Cloud Provider
CLOUD_PROVIDER=localstack  # localstack, aws, gcp, azure

# AWS / LocalStack
AWS_ENDPOINT_URL=http://localhost:4566
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test

# Storage
STORAGE_BUCKET_NAME=trading-data

# Streaming
STREAM_NAME=market-trades

# Cache
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# Time-Series Database
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=

# Relational Database
POSTGRES_URL=postgresql://admin:password@localhost:5432/trading

# API
API_HOST=0.0.0.0
API_PORT=8000
API_SECRET_KEY=change-me-in-production

# Monitoring
PROMETHEUS_PORT=9090
GRAFANA_PORT=3000
""",
        ".gitignore": """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual Environment
venv/
ENV/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Environment
.env
.env.local
.env.production
.env.*.local

# Data
data/raw/*
!data/raw/.gitkeep
data/processed/*
!data/processed/.gitkeep
data/models/*
!data/models/.gitkeep
data/backtest_results/*
!data/backtest_results/.gitkeep
data/logs/*
!data/logs/.gitkeep

# Jupyter
.ipynb_checkpoints/
notebooks/.ipynb_checkpoints/

# Tests
.pytest_cache/
.coverage
htmlcov/

# OS
.DS_Store
Thumbs.db

# Terraform
*.tfstate
*.tfstate.*
.terraform/

# CDK
cdk.out/
*.js
*.d.ts
node_modules/

# Logs
*.log
""",
        "Makefile": """# Makefile for Algorithmic Trading Platform

.PHONY: help install test lint format docker-up docker-down deploy-local deploy-aws clean

help:
\t@echo "Available commands:"
\t@echo "  make install       - Install dependencies"
\t@echo "  make test          - Run tests"
\t@echo "  make lint          - Run linters"
\t@echo "  make format        - Format code"
\t@echo "  make docker-up     - Start local stack (LocalStack + Docker)"
\t@echo "  make docker-down   - Stop local stack"
\t@echo "  make deploy-local  - Deploy to LocalStack"
\t@echo "  make deploy-aws    - Deploy to AWS"
\t@echo "  make clean         - Clean build artifacts"

install:
\tpip install -r requirements.txt
\tpip install -e .

test:
\tpytest tests/ -v --cov=. --cov-report=html

lint:
\tflake8 . --max-line-length=120
\tmypy . --ignore-missing-imports

format:
\tblack . --line-length=120
\tisort .

docker-up:
\tdocker-compose -f infrastructure/docker/docker-compose.local.yml up -d

docker-down:
\tdocker-compose -f infrastructure/docker/docker-compose.local.yml down

deploy-local:
\t@echo "Deploying to LocalStack..."
\tcd infrastructure/cdk && cdklocal deploy

deploy-aws:
\t@echo "Deploying to AWS..."
\tcd infrastructure/cdk && cdk deploy

clean:
\tfind . -type d -name __pycache__ -exec rm -rf {} +
\tfind . -type f -name '*.pyc' -delete
\tfind . -type f -name '*.pyo' -delete
\tfind . -type d -name '*.egg-info' -exec rm -rf {} +
\trm -rf build/ dist/ .pytest_cache/ .coverage htmlcov/
""",
    }

    for filename, content in root_files.items():
        file_path = base_path / filename
        if not file_path.exists():
            file_path.write_text(content)
            created_files.append(str(file_path.relative_to(base_path)))

    # Create .gitkeep files in data directories
    data_dirs = ["raw", "processed", "models", "backtest_results", "logs"]
    for data_dir in data_dirs:
        gitkeep = base_path / "data" / data_dir / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("")
            created_files.append(str(gitkeep.relative_to(base_path)))

    # Print summary
    print("=" * 80)
    print("PROJECT STRUCTURE CREATED SUCCESSFULLY!")
    print("=" * 80)
    print(f"\n✅ Created {len(created_dirs)} directories")
    print(f"✅ Created {len(created_files)} files")

    print("\n📁 Directory Structure:")
    for dir_path in sorted(created_dirs)[:20]:  # Show first 20
        print(f"   {dir_path}/")
    if len(created_dirs) > 20:
        print(f"   ... and {len(created_dirs) - 20} more directories")

    print("\n📄 Key Files Created:")
    key_files = [f for f in created_files if f in [".env.example", ".gitignore", "Makefile"]]
    for file_path in key_files:
        print(f"   {file_path}")

    print("\n" + "=" * 80)
    print("NEXT STEPS:")
    print("=" * 80)
    print("1. Copy .env.example to .env.local:")
    print("   cp .env.example .env.local")
    print("\n2. Review and update .env.local with your settings")
    print("\n3. Install dependencies:")
    print("   make install")
    print("\n4. Start local development stack:")
    print("   make docker-up")
    print("=" * 80)


if __name__ == "__main__":
    create_structure()
