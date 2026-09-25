terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.79, < 6.0"
    }
  }

  # Remote state. Create the bucket/table once (outside this stack), then:
  #   terraform init -backend-config="bucket=<bucket>" -backend-config="key=experimentos/terraform.tfstate" \
  #                  -backend-config="region=<region>" -backend-config="dynamodb_table=<lock-table>"
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = local.tags
  }
}
