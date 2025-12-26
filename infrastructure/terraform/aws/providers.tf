terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# AWS Provider Configuration
# Works with both LocalStack and real AWS
provider "aws" {
  region     = var.aws_region
  access_key = var.aws_access_key_id
  secret_key = var.aws_secret_access_key

  # Skip validation for LocalStack
  skip_credentials_validation = var.localstack_endpoint != ""
  skip_metadata_api_check     = var.localstack_endpoint != ""
  skip_requesting_account_id  = var.localstack_endpoint != ""
  s3_use_path_style           = var.localstack_endpoint != ""

  # Dynamic endpoints - only set for LocalStack
  # When localstack_endpoint is empty, uses real AWS endpoints
  dynamic "endpoints" {
    for_each = var.localstack_endpoint != "" ? [1] : []
    content {
      s3             = var.localstack_endpoint
      kinesis        = var.localstack_endpoint
      dynamodb       = var.localstack_endpoint
      sqs            = var.localstack_endpoint
      sns            = var.localstack_endpoint
      iam            = var.localstack_endpoint
      secretsmanager = var.localstack_endpoint
      cloudwatch     = var.localstack_endpoint
      eventbridge    = var.localstack_endpoint
      lambda         = var.localstack_endpoint
    }
  }
}
