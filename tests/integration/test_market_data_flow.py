"""
Integration test for market data flow

Tests the complete flow:
1. Start market data ingestion service
2. Wait for data to accumulate
3. Verify data in ClickHouse, Redis, Kinesis
4. Stop service gracefully

Run with: pytest tests/integration/test_market_data_flow.py -v -s
"""

import asyncio
import json
import signal
import subprocess

import boto3
import pytest
import redis
from clickhouse_driver import Client

from config.settings import get_settings


@pytest.fixture(scope="module")
def settings():
    """Get application settings"""
    return get_settings()


@pytest.fixture(scope="module")
def clickhouse_client(settings):
    """Create ClickHouse client"""
    client = Client(
        host=settings.CLICKHOUSE_HOST,
        port=settings.CLICKHOUSE_PORT,
        database=settings.CLICKHOUSE_DB,
        user=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
    )
    yield client
    client.disconnect()


@pytest.fixture(scope="module")
def redis_client(settings):
    """Create Redis client"""
    client = redis.from_url(settings.redis_url, decode_responses=True)
    yield client
    client.close()


@pytest.fixture(scope="module")
def kinesis_client(settings):
    """Create Kinesis client (LocalStack)"""
    client = boto3.client(
        "kinesis",
        endpoint_url=settings.AWS_ENDPOINT_URL,
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )
    return client


class TestMarketDataFlow:
    """Integration tests for complete data flow"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_complete_data_flow(
        self, settings, clickhouse_client, redis_client, kinesis_client
    ):
        """
        Test complete flow: Binance → StreamProcessor → [Kinesis, ClickHouse, Redis]

        Steps:
        1. Get initial trade count
        2. Start service
        3. Wait for data accumulation (10 seconds)
        4. Stop service
        5. Verify data in all 3 destinations
        """

        # Step 1: Get initial counts
        initial_count_result = clickhouse_client.execute(
            "SELECT count() FROM trading.market_trades"
        )
        initial_count = initial_count_result[0][0]
        print(f"\n📊 Initial trade count: {initial_count}")

        # Step 2: Start market data ingestion service
        print("\n🚀 Starting market data ingestion service...")
        process = subprocess.Popen(
            ["python", "services/market_data_ingestion/main.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=lambda: signal.signal(signal.SIGTERM, signal.SIG_DFL),
        )

        try:
            # Step 3: Wait for data accumulation
            print("⏳ Waiting 15 seconds for data accumulation...")
            await asyncio.sleep(15)

            # Step 4: Stop service gracefully
            print("\n⏹ Stopping service...")
            process.send_signal(signal.SIGINT)

            # Wait for graceful shutdown
            try:
                stdout, stderr = process.communicate(timeout=10)
                print(f"Service stopped with exit code: {process.returncode}")
            except subprocess.TimeoutExpired:
                print("⚠ Service didn't stop gracefully, killing...")
                process.kill()
                stdout, stderr = process.communicate()

            # Step 5: Verify data in ClickHouse
            print("\n✓ Verifying ClickHouse data...")
            final_count_result = clickhouse_client.execute(
                "SELECT count() FROM trading.market_trades"
            )
            final_count = final_count_result[0][0]
            new_trades = final_count - initial_count

            print(f"  Initial: {initial_count} trades")
            print(f"  Final: {final_count} trades")
            print(f"  New trades: {new_trades}")

            # Should have received at least 10 trades in 15 seconds
            assert new_trades >= 10, f"Expected at least 10 new trades, got {new_trades}"

            # Verify data structure
            sample_trades = clickhouse_client.execute(
                "SELECT exchange, symbol, price, quantity, side FROM trading.market_trades ORDER BY timestamp DESC LIMIT 5"
            )
            print(f"  Sample trades: {len(sample_trades)} records")
            for trade in sample_trades:
                exchange, symbol, price, quantity, side = trade
                print(f"    {exchange} {symbol}: {price} x {quantity} ({side})")

                # Verify data structure (exchange can be binance, coinbase, kraken)
                assert exchange in ["binance", "coinbase", "kraken"]
                assert len(symbol) > 0  # Symbol should be non-empty
                assert price > 0
                assert quantity > 0
                assert side in ["buy", "sell"]

            # Step 6: Verify data in Redis
            print("\n✓ Verifying Redis cache...")
            # Get any cached prices from Redis (keys are latest_price:<exchange>:<symbol>)
            cache_keys = redis_client.keys("latest_price:*")
            assert len(cache_keys) > 0, "No prices found in Redis cache"

            # Check first cached price
            first_key = cache_keys[0]
            cached_price = redis_client.get(first_key)
            assert cached_price is not None

            price_data = json.loads(cached_price)
            print(f"  {first_key}: ${price_data['price']} ({price_data['side']})")

            assert float(price_data["price"]) > 0
            assert price_data["side"] in ["buy", "sell"]

            # Step 7: Verify stream activity (Kinesis or Kafka)
            # Only verify Kinesis if using AWS/LocalStack provider
            if settings.CLOUD_PROVIDER in ["aws", "localstack"]:
                print("\n✓ Verifying Kinesis stream...")
                stream_description = kinesis_client.describe_stream(
                    StreamName=settings.KINESIS_STREAM_MARKET_TRADES
                )

                stream_status = stream_description["StreamDescription"]["StreamStatus"]
                print(f"  Stream status: {stream_status}")
                assert stream_status == "ACTIVE"

                # Get shard iterator
                shard_id = stream_description["StreamDescription"]["Shards"][0]["ShardId"]
                iterator_response = kinesis_client.get_shard_iterator(
                    StreamName=settings.KINESIS_STREAM_MARKET_TRADES,
                    ShardId=shard_id,
                    ShardIteratorType="TRIM_HORIZON",
                )

                # Try to get records (should have some)
                records_response = kinesis_client.get_records(
                    ShardIterator=iterator_response["ShardIterator"], Limit=10
                )

                records = records_response["Records"]
                print(f"  Found {len(records)} records in Kinesis")

                if len(records) > 0:
                    # Verify first record structure
                    first_record = json.loads(records[0]["Data"])
                    print(f"  Sample record: {first_record['symbol']} @ ${first_record['price']}")

                    assert "exchange" in first_record
                    assert "symbol" in first_record
                    assert "price" in first_record
                    assert "quantity" in first_record
            else:
                print(
                    f"\n⏩ Skipping Kinesis verification (using {settings.CLOUD_PROVIDER} provider with Kafka)"
                )

            print("\n✅ All integration tests passed!")

        except Exception as e:
            print(f"\n❌ Test failed: {e}")
            # Ensure process is killed
            if process.poll() is None:
                process.kill()
            raise

        finally:
            # Cleanup: ensure process is terminated
            if process.poll() is None:
                process.kill()
                process.wait()

    @pytest.mark.integration
    def test_docker_services_running(self):
        """
        Pre-requisite test: Verify all Docker services are running

        This should run before the main integration test
        """
        print("\n🐳 Checking Docker services...")

        required_containers = ["trading-clickhouse", "trading-redis", "localstack-main"]

        for container_name in required_containers:
            # Check if container is running
            result = subprocess.run(
                ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
            )

            assert container_name in result.stdout, (
                f"❌ {container_name} is not running. Start with: docker-compose up -d"
            )

            print(f"  ✓ {container_name} is running")

        print("✅ All required Docker services are running")


class TestDataQuality:
    """Test data quality and consistency"""

    @pytest.mark.integration
    def test_clickhouse_data_quality(self, clickhouse_client):
        """Test data quality in ClickHouse"""
        print("\n🔍 Testing data quality...")

        # Check for null values
        null_check = clickhouse_client.execute("""
            SELECT
                countIf(price = 0) as zero_prices,
                countIf(quantity = 0) as zero_quantities,
                countIf(symbol = '') as empty_symbols
            FROM trading.market_trades
            LIMIT 1
        """)

        zero_prices, zero_quantities, empty_symbols = null_check[0]

        print(f"  Zero prices: {zero_prices}")
        print(f"  Zero quantities: {zero_quantities}")
        print(f"  Empty symbols: {empty_symbols}")

        # Should have no invalid data
        assert zero_prices == 0, "Found trades with zero price"
        assert zero_quantities == 0, "Found trades with zero quantity"
        assert empty_symbols == 0, "Found trades with empty symbol"

    @pytest.mark.integration
    def test_redis_cache_consistency(self, redis_client, clickhouse_client):
        """Test that Redis cache matches ClickHouse latest data"""
        print("\n🔄 Testing Redis-ClickHouse consistency...")

        # Get latest trade from ClickHouse
        latest_btc = clickhouse_client.execute("""
            SELECT price, timestamp, side
            FROM trading.market_trades
            WHERE symbol = 'BTCUSDT'
            ORDER BY timestamp DESC
            LIMIT 1
        """)

        if latest_btc:
            ch_price, ch_timestamp, ch_side = latest_btc[0]

            # Get from Redis
            redis_data = redis_client.get("latest_price:binance:BTCUSDT")
            assert redis_data is not None, "BTC price not in Redis"

            redis_json = json.loads(redis_data)
            redis_price = float(redis_json["price"])

            print(f"  ClickHouse latest: ${ch_price}")
            print(f"  Redis cache: ${redis_price}")

            # Prices might differ slightly due to timing, but should be close
            # Allow 1% difference
            price_diff_pct = abs(ch_price - redis_price) / ch_price * 100
            assert price_diff_pct < 1, f"Price difference too large: {price_diff_pct}%"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
