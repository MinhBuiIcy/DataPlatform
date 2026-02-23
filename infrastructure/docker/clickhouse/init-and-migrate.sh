#!/bin/bash
# ============================================
# ClickHouse Init & Migration Script
# Purpose: Initialize schema + run all pending migrations
# Runs as an init container (like kafka-init pattern)
# ============================================

set -e

CH_HOST="${CLICKHOUSE_HOST:-clickhouse}"
CH_PORT="${CLICKHOUSE_PORT:-9000}"
CH_USER="${CLICKHOUSE_USER:-trading_user}"
CH_PASS="${CLICKHOUSE_PASSWORD:-trading_pass}"
CH_DB="${CLICKHOUSE_DB:-trading}"
MIGRATIONS_DIR="/migrations"

CH_CMD="clickhouse-client --host $CH_HOST --port $CH_PORT --user $CH_USER --password $CH_PASS"

echo "🔧 ClickHouse Init & Migration"
echo "   Host: $CH_HOST:$CH_PORT"
echo "   Database: $CH_DB"

# ============================================
# Step 1: Wait for ClickHouse to be ready
# ============================================
echo "⏳ Waiting for ClickHouse..."
for i in $(seq 1 30); do
    if $CH_CMD --query "SELECT 1" > /dev/null 2>&1; then
        echo "✅ ClickHouse is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ ClickHouse not ready after 30 attempts"
        exit 1
    fi
    sleep 2
done

# ============================================
# Step 2: Run init.sql (idempotent - uses IF NOT EXISTS)
# ============================================
echo "📦 Running init.sql..."
$CH_CMD --multiquery < /init/init.sql
echo "✅ Init schema applied"

# ============================================
# Step 3: Run pending migrations
# ============================================
echo "🔄 Checking migrations..."

# Ensure migration tracker exists (migration 000)
TRACKER_EXISTS=$($CH_CMD --database $CH_DB --query \
    "SELECT count() FROM system.tables WHERE database = '$CH_DB' AND name = 'schema_migrations'" 2>/dev/null || echo "0")

if [ "$TRACKER_EXISTS" = "0" ]; then
    echo "   Creating migration tracker..."
    $CH_CMD --database $CH_DB --multiquery < "$MIGRATIONS_DIR/000_migration_tracker.sql"
fi

# Get list of applied migrations
APPLIED=$($CH_CMD --database $CH_DB --query "SELECT version FROM schema_migrations" 2>/dev/null || echo "")

# Run each migration file in order
for migration_file in $(ls "$MIGRATIONS_DIR"/*.sql | sort); do
    filename=$(basename "$migration_file")
    version=$(echo "$filename" | grep -oP '^\d+')

    # Skip if already applied
    if echo "$APPLIED" | grep -q "^${version}$"; then
        echo "   ⏭️  Migration $filename (already applied)"
        continue
    fi

    echo "   🚀 Applying $filename..."
    if $CH_CMD --database $CH_DB --multiquery < "$migration_file"; then
        echo "   ✅ $filename applied"
    else
        echo "   ❌ $filename FAILED"
        exit 1
    fi
done

echo ""
echo "✅ All migrations applied!"

# Show summary
echo ""
echo "📋 Applied migrations:"
$CH_CMD --database $CH_DB --query "SELECT version, name, applied_at FROM schema_migrations ORDER BY version FORMAT PrettyCompact" 2>/dev/null || true

echo ""
echo "📋 Tables in $CH_DB:"
$CH_CMD --database $CH_DB --query "SHOW TABLES" 2>/dev/null || true
