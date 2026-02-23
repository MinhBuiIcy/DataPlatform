# Sync Service
# Scheduled REST API sync → ClickHouse (latest klines)

FROM python:3.11-slim

WORKDIR /app

# Install uv (fast Python package manager)
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies using uv
RUN uv sync --no-dev

# Copy application code
COPY . /app

# Create logs directory
RUN mkdir -p data/logs

# Set Python path
ENV PYTHONPATH=/app

# Run service
CMD ["uv", "run", "python", "services/sync_service/main.py"]
