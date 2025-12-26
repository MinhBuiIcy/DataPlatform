"""
Integration tests for Docker service connections
Tests ClickHouse, Redis, and PostgreSQL connectivity

Run with: python -m pytest tests/integration/test_docker_connections.py -v
Or directly: python tests/integration/test_docker_connections.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import psycopg2
import redis
from clickhouse_driver import Client

from config.settings import get_settings


def test_clickhouse_connection():
    """Test ClickHouse connection and basic query"""
    print("\n=== Testing ClickHouse Connection ===")
    settings = get_settings()

    try:
        client = Client(
            host=settings.CLICKHOUSE_HOST,
            port=settings.CLICKHOUSE_PORT,
            database=settings.CLICKHOUSE_DB,
            user=settings.CLICKHOUSE_USER,
            password=settings.CLICKHOUSE_PASSWORD,
        )

        # Test basic query
        result = client.execute("SELECT 1")
        assert result == [(1,)], f"Expected [(1,)], got {result}"
        print(f"✓ Basic query: SELECT 1 = {result}")

        # Test database exists
        result = client.execute("SHOW DATABASES")
        databases = [row[0] for row in result]
        assert settings.CLICKHOUSE_DB in databases, f"Database {settings.CLICKHOUSE_DB} not found"
        print(f"✓ Database exists: {settings.CLICKHOUSE_DB}")

        # Test tables exist
        result = client.execute(f"SHOW TABLES FROM {settings.CLICKHOUSE_DB}")
        tables = [row[0] for row in result]
        expected_tables = [
            "market_trades",
            "orderbook_snapshots",
            "candles_1m",
            "indicators",
            "strategy_signals",
        ]
        for table in expected_tables:
            assert table in tables, f"Table {table} not found"
        print(f"✓ All tables exist: {', '.join(expected_tables)}")

        # Test insert and query on market_trades
        client.execute("""
            INSERT INTO trading.market_trades
            (timestamp, exchange, symbol, trade_id, price, quantity, side, is_buyer_maker)
            VALUES
            (now(), 'test', 'BTC/USDT', 'test_1', 50000.0, 0.1, 'buy', 1)
        """)
        result = client.execute(
            "SELECT COUNT(*) FROM trading.market_trades WHERE exchange = 'test'"
        )
        count = result[0][0]
        assert count >= 1, f"Expected at least 1 row, got {count}"
        print(f"✓ Insert and query successful: {count} test rows found")

        # Cleanup test data
        client.execute("DELETE FROM trading.market_trades WHERE exchange = 'test'")

        print("✓ ClickHouse connection successful!")
        print(f"  Host: {settings.CLICKHOUSE_HOST}:{settings.CLICKHOUSE_PORT}")
        print(f"  Database: {settings.CLICKHOUSE_DB}")

    except Exception as e:
        print(f"✗ ClickHouse connection failed: {e}")
        raise


def test_redis_connection():
    """Test Redis connection and basic operations"""
    print("\n=== Testing Redis Connection ===")
    settings = get_settings()

    try:
        r = redis.from_url(settings.redis_url)

        # Test ping
        assert r.ping(), "Redis ping failed"
        print("✓ Ping successful")

        # Test set/get
        test_key = "test_connection_key"
        test_value = "test_value_123"
        r.set(test_key, test_value)
        retrieved = r.get(test_key)
        assert retrieved.decode("utf-8") == test_value, f"Expected {test_value}, got {retrieved}"
        print(f"✓ Set/Get successful: {test_key} = {test_value}")

        # Test hash operations
        hash_key = "test_hash"
        r.hset(hash_key, "field1", "value1")
        r.hset(hash_key, "field2", "value2")
        hash_data = r.hgetall(hash_key)
        assert len(hash_data) == 2, f"Expected 2 fields, got {len(hash_data)}"
        print(f"✓ Hash operations successful: {len(hash_data)} fields")

        # Test list operations
        list_key = "test_list"
        r.rpush(list_key, "item1", "item2", "item3")
        list_len = r.llen(list_key)
        assert list_len == 3, f"Expected 3 items, got {list_len}"
        print(f"✓ List operations successful: {list_len} items")

        # Cleanup test data
        r.delete(test_key, hash_key, list_key)

        # Test Redis info
        info = r.info()
        print(f"✓ Redis version: {info['redis_version']}")
        print("✓ Redis connection successful!")
        print(f"  Host: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
        print(f"  DB: {settings.REDIS_DB}")

    except Exception as e:
        print(f"✗ Redis connection failed: {e}")
        raise


def test_postgres_connection():
    """Test PostgreSQL connection and basic query"""
    print("\n=== Testing PostgreSQL Connection ===")
    settings = get_settings()

    try:
        conn = psycopg2.connect(settings.postgres_dsn)
        cursor = conn.cursor()

        # Test basic query
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        assert result == (1,), f"Expected (1,), got {result}"
        print(f"✓ Basic query: SELECT 1 = {result}")

        # Test database exists
        cursor.execute("SELECT current_database()")
        db_name = cursor.fetchone()[0]
        assert db_name == settings.POSTGRES_DB, f"Expected {settings.POSTGRES_DB}, got {db_name}"
        print(f"✓ Database: {db_name}")

        # Test tables exist
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        tables = [row[0] for row in cursor.fetchall()]
        expected_tables = [
            "users",
            "exchange_credentials",
            "strategies",
            "orders",
            "executions",
            "portfolios",
            "strategy_performance",
            "system_logs",
        ]
        for table in expected_tables:
            assert table in tables, f"Table {table} not found"
        print(f"✓ All tables exist: {', '.join(expected_tables)}")

        # Test insert and query on users table
        cursor.execute("""
            INSERT INTO users (email, password_hash, api_key_hash)
            VALUES ('test@example.com', 'test_hash', 'test_api_key')
            RETURNING id, email
        """)
        user_id, email = cursor.fetchone()
        assert email == "test@example.com", f"Expected test@example.com, got {email}"
        print(f"✓ Insert successful: user_id = {user_id}")

        # Test query
        cursor.execute("SELECT COUNT(*) FROM users WHERE email = 'test@example.com'")
        count = cursor.fetchone()[0]
        assert count == 1, f"Expected 1 row, got {count}"
        print(f"✓ Query successful: {count} test user found")

        # Cleanup test data
        cursor.execute("DELETE FROM users WHERE email = 'test@example.com'")
        conn.commit()

        # Test PostgreSQL version
        cursor.execute("SELECT version()")
        version = cursor.fetchone()[0]
        print(f"✓ PostgreSQL version: {version.split(',')[0]}")

        cursor.close()
        conn.close()

        print("✓ PostgreSQL connection successful!")
        print(f"  Host: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}")
        print(f"  Database: {settings.POSTGRES_DB}")

    except Exception as e:
        print(f"✗ PostgreSQL connection failed: {e}")
        raise


def main():
    """Run all connection tests"""
    print("=" * 60)
    print("Docker Services Connection Tests")
    print("=" * 60)

    results = {"ClickHouse": False, "Redis": False, "PostgreSQL": False}

    # Test ClickHouse
    try:
        results["ClickHouse"] = test_clickhouse_connection()
    except Exception as e:
        print(f"ClickHouse test failed: {e}")

    # Test Redis
    try:
        results["Redis"] = test_redis_connection()
    except Exception as e:
        print(f"Redis test failed: {e}")

    # Test PostgreSQL
    try:
        results["PostgreSQL"] = test_postgres_connection()
    except Exception as e:
        print(f"PostgreSQL test failed: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    for service, status in results.items():
        status_icon = "✓" if status else "✗"
        status_text = "PASS" if status else "FAIL"
        print(f"{status_icon} {service}: {status_text}")

    print("=" * 60)

    all_passed = all(results.values())
    if all_passed:
        print("\n🎉 All connection tests passed!")
        return 0
    else:
        print("\n❌ Some connection tests failed!")
        return 1


if __name__ == "__main__":
    exit(main())
