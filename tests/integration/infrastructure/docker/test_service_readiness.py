"""
Integration test for Docker service readiness (TIER 2)

Verifies all Docker services (ClickHouse, Redis, PostgreSQL) are reachable.
This is a basic connectivity test - run before TIER 1 tests to verify environment.
"""

import pytest
import psycopg2
import redis as redis_lib
from clickhouse_driver import Client

from config.settings import get_settings


@pytest.mark.integration
@pytest.mark.tier2  # 🔧 TIER 2 - Infrastructure
def test_all_docker_services_reachable():
    """Verify ClickHouse, Redis, PostgreSQL are reachable"""
    settings = get_settings()

    # ClickHouse
    print("\n[1/3] Testing ClickHouse connectivity...")
    client = Client(
        host=settings.CLICKHOUSE_HOST,
        port=settings.CLICKHOUSE_PORT,
        user=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD
    )
    result = client.execute("SELECT 1")
    assert result == [(1,)]
    client.disconnect()
    print("  ✓ ClickHouse reachable")

    # Redis
    print("\n[2/3] Testing Redis connectivity...")
    r = redis_lib.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
    assert r.ping()
    r.close()
    print("  ✓ Redis reachable")

    # PostgreSQL
    print("\n[3/3] Testing PostgreSQL connectivity...")
    conn = psycopg2.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        database=settings.POSTGRES_DB,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD
    )
    assert conn is not None
    conn.close()
    print("  ✓ PostgreSQL reachable")

    print("\n✅ All Docker services reachable")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
