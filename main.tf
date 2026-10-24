terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
    rediscloud = {
      source  = "RedisLabs/rediscloud"
      version = "~> 2.18"
    }
  }
}

provider "aws" {
  region              = var.aws_region
  profile             = var.aws_profile
  allowed_account_ids = ["735486936198"]
  default_tags {
    tags = local.tags
  }
}

provider "rediscloud" {}

variable "aws_resources_name_prefix" {
  description = "Prefix used for AWS resource names."
  type        = string
  default     = "redis-peering"
}

variable "subscription_name" {
  description = "Redis Cloud Pro subscription name."
  type        = string
  default     = "redis-peering-pro-us-west-2"
}

variable "database_name" {
  description = "Redis Cloud database name."
  type        = string
  default     = "redis-peering-db"
}

variable "cloud_provider" {
  description = "Cloud provider for the Redis Cloud Pro subscription."
  type        = string
  default     = "AWS"
}

variable "payment_method" {
  description = "Redis Cloud payment method. Use marketplace for Marketplace accounts, credit-card for card billing, or null for direct contracts that do not require a payment method."
  type        = string
  default     = "credit-card"

  validation {
    condition     = var.payment_method == null || contains(["marketplace", "credit-card"], var.payment_method)
    error_message = "payment_method must be marketplace, credit-card, or null."
  }
}

variable "redis_region" {
  description = "Cloud provider region for the Redis Cloud Pro subscription."
  type        = string
  default     = "us-west-2"
}

variable "redis_deployment_cidr" {
  description = "Redis Cloud producer deployment CIDR. Must be a /24 and must not overlap the AWS VPC CIDR."
  type        = string
  default     = "192.168.0.0/24"
}

variable "dataset_size_in_gb" {
  description = "Dataset size for the Redis database."
  type        = number
  default     = 25
}

variable "throughput_measurement_value" {
  description = "Database throughput in operations per second."
  type        = number
  default     = 25000
}

variable "replication" {
  description = "Whether database replication is enabled."
  type        = bool
  default     = false
}

variable "support_oss_cluster_api" {
  description = "Whether the Redis database should support the open-source Redis Cluster API."
  type        = bool
  default     = false
}

variable "enable_public_endpoint" {
  description = "Whether Redis Cloud should expose a public endpoint."
  type        = bool
  default     = false
}

variable "aws_region" {
  description = "AWS region. Must match the Redis Cloud subscription region."
  type        = string
  default     = "us-west-2"
}

variable "aws_profile" {
  description = "Optional AWS shared config profile, for example an AWS SSO profile. Leave null to use the normal AWS credential chain."
  type        = string
  default     = null
}

variable "aws_vpc_id" {
  description = "The AWS consumer VPC ID to connect to Redis Cloud. This VPC must be in aws_region."
  type        = string
}

resource "random_password" "database" {
  length  = 32
  special = false
}

data "rediscloud_payment_method" "current" {
  count = var.payment_method == "credit-card" ? 1 : 0
}

resource "rediscloud_subscription" "pro" {
  name                   = var.subscription_name
  payment_method         = var.payment_method
  payment_method_id      = var.payment_method == "credit-card" ? data.rediscloud_payment_method.current[0].id : null
  memory_storage         = "ram"
  public_endpoint_access = var.enable_public_endpoint

  cloud_provider {
    provider = var.cloud_provider

    region {
      region                       = var.redis_region
      multiple_availability_zones  = false
      networking_deployment_cidr   = var.redis_deployment_cidr
      preferred_availability_zones = []
    }
  }

  creation_plan {
    dataset_size_in_gb           = var.dataset_size_in_gb
    quantity                     = 1
    replication                  = var.replication
    support_oss_cluster_api      = var.support_oss_cluster_api
    throughput_measurement_by    = "operations-per-second"
    throughput_measurement_value = var.throughput_measurement_value
  }

  timeouts {
    create = "60m"
    update = "60m"
    delete = "30m"
  }
}

resource "rediscloud_subscription_database" "database" {
  subscription_id              = rediscloud_subscription.pro.id
  name                         = var.database_name
  dataset_size_in_gb           = var.dataset_size_in_gb
  protocol                     = "redis"
  replication                  = var.replication
  support_oss_cluster_api      = var.support_oss_cluster_api
  data_persistence             = "none"
  throughput_measurement_by    = "operations-per-second"
  throughput_measurement_value = var.throughput_measurement_value
  password                     = random_password.database.result
  enable_default_user          = true
  source_ips                   = concat([data.aws_vpc.consumer.cidr_block], var.additional_source_ips)
  tags                         = local.tags

  timeouts {
    create = "60m"
    update = "60m"
    delete = "30m"
  }
}


locals {
  tags = {
    owner         = "lionel_giavelli"
    skip_deletion = "yes"
  }
}

data "aws_caller_identity" "current" {}
data "aws_vpc" "consumer" {
  id = var.aws_vpc_id
}
data "aws_route_tables" "consumer" {
  vpc_id = var.aws_vpc_id
}

resource "rediscloud_subscription_peering" "consumer" {
  subscription_id = rediscloud_subscription.pro.id
  region          = var.aws_region
  aws_account_id  = data.aws_caller_identity.current.account_id
  vpc_id          = data.aws_vpc.consumer.id
  vpc_cidr        = data.aws_vpc.consumer.cidr_block
}

resource "aws_vpc_peering_connection_accepter" "redis" {
  vpc_peering_connection_id = rediscloud_subscription_peering.consumer.aws_peering_id
  auto_accept               = true
  tags                      = { Name = var.aws_resources_name_prefix }
}

resource "aws_route" "redis" {
  for_each                  = toset(data.aws_route_tables.consumer.ids)
  route_table_id            = each.value
  destination_cidr_block    = var.redis_deployment_cidr
  vpc_peering_connection_id = aws_vpc_peering_connection_accepter.redis.id
}

output "subscription_id" {
  value = rediscloud_subscription.pro.id
}
output "database_id" {
  value = rediscloud_subscription_database.database.db_id
}
output "private_endpoint" {
  value = rediscloud_subscription_database.database.private_endpoint
}
output "database_password" {
  value     = random_password.database.result
  sensitive = true
}
output "peering_id" {
  value = aws_vpc_peering_connection_accepter.redis.id
}
output "consumer_vpc_id" {
  value = data.aws_vpc.consumer.id
}
output "route_table_ids" {
  value = data.aws_route_tables.consumer.ids
}

variable "additional_source_ips" {
  type    = list(string)
  default = []
}
output "public_endpoint" {
  value = rediscloud_subscription_database.database.public_endpoint
}
