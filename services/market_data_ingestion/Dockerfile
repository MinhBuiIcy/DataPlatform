# Market Data Ingestion Service
# WebSocket → Kinesis/Kafka + S3 + ClickHouse + Redis

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

# Set Python path
ENV PYTHONPATH=/app

# Run service
CMD ["uv", "run", "python", "services/market_data_ingestion/main.py"]
