# TA-Lib Base Docker Image
# Pre-built image with TA-Lib compiled and ready to use
#
# Build once, reuse many times:
#   docker build -t trading-platform/talib-base:3.11 .
#
# Reduces build time from 8-10 minutes → 30 seconds

FROM python:3.11-slim

LABEL maintainer="trading-platform"
LABEL description="Python 3.11 with TA-Lib pre-installed for technical analysis"

# Install build dependencies
RUN apt-get update && apt-get install -y \
    wget \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Download and compile TA-Lib C library
ENV TA_LIB_VERSION=0.4.0
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-${TA_LIB_VERSION}-src.tar.gz && \
    tar -xzf ta-lib-${TA_LIB_VERSION}-src.tar.gz && \
    cd ta-lib/ && \
    # Update config.guess and config.sub for ARM64 support \
    wget -O config.guess 'http://git.savannah.gnu.org/gitweb/?p=config.git;a=blob_plain;f=config.guess;hb=HEAD' && \
    wget -O config.sub 'http://git.savannah.gnu.org/gitweb/?p=config.git;a=blob_plain;f=config.sub;hb=HEAD' && \
    ./configure --prefix=/usr && \
    make && \
    make install && \
    cd .. && \
    rm -rf ta-lib ta-lib-${TA_LIB_VERSION}-src.tar.gz

# Install Python TA-Lib wrapper (use latest compatible version)
RUN pip install --no-cache-dir "TA-Lib>=0.4.28"

# Verify installation
RUN python -c "import talib; print(f'TA-Lib version: {talib.__version__}')"

# Clean up build dependencies to reduce image size (optional)
# Comment out if you need to compile other C extensions
RUN apt-get purge -y wget && apt-get autoremove -y

# Set working directory
WORKDIR /app

CMD ["python"]
