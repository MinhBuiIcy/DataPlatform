#!/bin/bash
# ============================================
# Kafka Topics Creation Script
# Purpose: Create topics for Phase 2+ on startup
# ============================================

set -e

echo "Waiting for Kafka to be ready..."
sleep 10

KAFKA_BROKER="kafka:9092"

echo "Creating Kafka topics..."

# Phase 1 topics (already exist, but using --if-not-exists)
kafka-topics --bootstrap-server $KAFKA_BROKER \
    --create --if-not-exists \
    --topic market-trades \
    --partitions 3 \
    --replication-factor 1 \
    --config retention.ms=86400000 \
    --config compression.type=lz4

kafka-topics --bootstrap-server $KAFKA_BROKER \
    --create --if-not-exists \
    --topic order-books \
    --partitions 3 \
    --replication-factor 1 \
    --config retention.ms=3600000 \
    --config compression.type=lz4

# Phase 2 topics (NEW)
kafka-topics --bootstrap-server $KAFKA_BROKER \
    --create --if-not-exists \
    --topic candle-events \
    --partitions 3 \
    --replication-factor 1 \
    --config retention.ms=86400000 \
    --config compression.type=lz4

echo "✅ All Kafka topics created successfully"

# List all topics for verification
echo ""
echo "📋 Available topics:"
kafka-topics --bootstrap-server $KAFKA_BROKER --list
