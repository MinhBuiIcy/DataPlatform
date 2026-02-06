# Indicator Service
# Kafka Consumer → TA-Lib Indicators → ClickHouse + Redis
#
# Uses pre-built TA-Lib base image for fast builds

ARG TALIB_BASE_IMAGE=trading-platform/talib-base:3.11
FROM ${TALIB_BASE_IMAGE}

WORKDIR /app

# Install uv (fast Python package manager)
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies using uv
# Note: TA-Lib Python wrapper already installed in base image
RUN uv sync --no-dev

# Copy application code
COPY . /app

# Set Python path
ENV PYTHONPATH=/app

# Run service
CMD ["uv", "run", "python", "services/indicator_service/main.py"]
