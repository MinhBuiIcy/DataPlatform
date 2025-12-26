# ============================================
# PHASE 1: FOUNDATION & REAL-TIME DATA
#
# Resources:
# - S3 Buckets (2): Raw data, ML models
# - Kinesis Stream (1): Market trades
#
# Goal: Minimal setup to start Phase 1 development
# ============================================

# ============================================
# S3 BUCKET: RAW MARKET DATA
# ============================================

resource "aws_s3_bucket" "trading_raw_data" {
  bucket = "trading-raw-data-${var.environment}"

  # Force destroy for local development (BE CAREFUL in production!)
  force_destroy = var.environment == "local" ? true : false

  tags = {
    Name        = "Trading Raw Data"
    Environment = var.environment
    Project     = var.project_name
    Phase       = "1"
    Purpose     = "Store raw market data from WebSocket streams"
  }
}

# S3 Bucket Versioning (Optional - disabled for local)
resource "aws_s3_bucket_versioning" "trading_raw_data" {
  count  = var.enable_s3_versioning ? 1 : 0
  bucket = aws_s3_bucket.trading_raw_data.id

  versioning_configuration {
    status = "Enabled"
  }
}

# S3 Lifecycle Rules (Optional - for production cost optimization)
resource "aws_s3_bucket_lifecycle_configuration" "trading_raw_data" {
  count  = var.s3_lifecycle_enabled ? 1 : 0
  bucket = aws_s3_bucket.trading_raw_data.id

  rule {
    id     = "archive-old-data"
    status = "Enabled"

    transition {
      days          = var.s3_lifecycle_days
      storage_class = "GLACIER"
    }

    expiration {
      days = var.s3_lifecycle_days * 2
    }
  }
}

# ============================================
# S3 BUCKET: ML MODELS
# ============================================

resource "aws_s3_bucket" "trading_models" {
  bucket = "trading-models-${var.environment}"

  force_destroy = var.environment == "local" ? true : false

  tags = {
    Name        = "ML Models Storage"
    Environment = var.environment
    Project     = var.project_name
    Phase       = "5"
    Purpose     = "Store trained ML models and artifacts"
  }
}

resource "aws_s3_bucket_versioning" "trading_models" {
  count  = var.enable_s3_versioning ? 1 : 0
  bucket = aws_s3_bucket.trading_models.id

  versioning_configuration {
    status = "Enabled"
  }
}

# ============================================
# KINESIS STREAM: MARKET TRADES
# ============================================

resource "aws_kinesis_stream" "market_trades" {
  name             = "market-trades-${var.environment}"
  shard_count      = var.kinesis_shard_count
  retention_period = var.kinesis_retention_hours

  # Shard level metrics (optional - costs extra on real AWS)
  shard_level_metrics = var.environment != "local" ? [
    "IncomingBytes",
    "IncomingRecords",
    "OutgoingBytes",
    "OutgoingRecords",
  ] : []

  # Stream mode: PROVISIONED (manual shards) or ON_DEMAND (auto-scaling)
  stream_mode_details {
    stream_mode = "PROVISIONED"
  }

  tags = {
    Name        = "Market Trades Stream"
    Environment = var.environment
    Project     = var.project_name
    Phase       = "1"
    Purpose     = "Real-time market data stream from exchanges"
  }
}

# ============================================
# OUTPUTS (for reference in code)
# ============================================

output "phase1_resources" {
  description = "Phase 1 resources summary"
  value = {
    s3_raw_data_bucket     = aws_s3_bucket.trading_raw_data.bucket
    s3_raw_data_arn        = aws_s3_bucket.trading_raw_data.arn
    s3_models_bucket       = aws_s3_bucket.trading_models.bucket
    s3_models_arn          = aws_s3_bucket.trading_models.arn
    kinesis_stream_name    = aws_kinesis_stream.market_trades.name
    kinesis_stream_arn     = aws_kinesis_stream.market_trades.arn
    kinesis_shard_count    = aws_kinesis_stream.market_trades.shard_count
  }
}
