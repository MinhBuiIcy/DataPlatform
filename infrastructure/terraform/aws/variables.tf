# ============================================
# GENERAL VARIABLES
# ============================================

variable "environment" {
  description = "Environment name (local, dev, staging, production)"
  type        = string
  default     = "local"

  validation {
    condition     = contains(["local", "dev", "staging", "production"], var.environment)
    error_message = "Environment must be one of: local, dev, staging, production"
  }
}

variable "project_name" {
  description = "Project name for tagging"
  type        = string
  default     = "AlgoTrading"
}

# ============================================
# AWS CONFIGURATION
# ============================================

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "aws_access_key_id" {
  description = "AWS access key ID (use 'test' for LocalStack)"
  type        = string
  default     = "test"
  sensitive   = true
}

variable "aws_secret_access_key" {
  description = "AWS secret access key (use 'test' for LocalStack)"
  type        = string
  default     = "test"
  sensitive   = true
}

variable "localstack_endpoint" {
  description = "LocalStack endpoint URL (empty string for real AWS)"
  type        = string
  default     = ""
}

# ============================================
# PHASE 1 - KINESIS VARIABLES
# ============================================

variable "kinesis_shard_count" {
  description = "Number of shards for Kinesis stream (1 for local, 3-5 for production)"
  type        = number
  default     = 1

  validation {
    condition     = var.kinesis_shard_count >= 1 && var.kinesis_shard_count <= 100
    error_message = "Kinesis shard count must be between 1 and 100"
  }
}

variable "kinesis_retention_hours" {
  description = "Kinesis data retention period in hours (24-168)"
  type        = number
  default     = 24

  validation {
    condition     = var.kinesis_retention_hours >= 24 && var.kinesis_retention_hours <= 168
    error_message = "Retention must be between 24 and 168 hours"
  }
}

# ============================================
# PHASE 1 - S3 VARIABLES
# ============================================

variable "enable_s3_versioning" {
  description = "Enable versioning for S3 buckets"
  type        = bool
  default     = false # Disabled for local, enabled for production
}

variable "s3_lifecycle_enabled" {
  description = "Enable S3 lifecycle rules"
  type        = bool
  default     = false
}

variable "s3_lifecycle_days" {
  description = "Days to keep objects before moving to cheaper storage"
  type        = number
  default     = 90
}
