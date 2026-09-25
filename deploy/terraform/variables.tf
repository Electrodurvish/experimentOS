variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "name" {
  description = "Name prefix for all resources."
  type        = string
  default     = "experimentos"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)."
  type        = string
  default     = "prod"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.40.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones to spread subnets across."
  type        = number
  default     = 3

  validation {
    condition     = var.az_count >= 2 && var.az_count <= 3
    error_message = "az_count must be 2 or 3 (RDS and ElastiCache subnet groups need >= 2 AZs)."
  }
}

variable "single_nat_gateway" {
  description = "Use one NAT gateway for all AZs (cheaper, not AZ-redundant)."
  type        = bool
  default     = false
}

# --- EKS ---------------------------------------------------------------------

variable "kubernetes_version" {
  description = "EKS control plane version."
  type        = string
  default     = "1.31"
}

variable "cluster_endpoint_public_access_cidrs" {
  description = "CIDRs allowed to reach the public EKS API endpoint. Restrict this."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "node_instance_types" {
  description = "Instance types for the default managed node group."
  type        = list(string)
  default     = ["m6i.large"]
}

variable "node_min_size" {
  type    = number
  default = 2
}

variable "node_desired_size" {
  type    = number
  default = 3
}

variable "node_max_size" {
  type    = number
  default = 6
}

# --- RDS PostgreSQL ------------------------------------------------------------

variable "db_engine_version" {
  description = "PostgreSQL major.minor version."
  type        = string
  default     = "16.4"
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "db_allocated_storage" {
  description = "Initial storage in GiB."
  type        = number
  default     = 50
}

variable "db_max_allocated_storage" {
  description = "Storage autoscaling ceiling in GiB."
  type        = number
  default     = 200
}

variable "db_multi_az" {
  type    = bool
  default = true
}

variable "db_name" {
  type    = string
  default = "experimentos"
}

variable "db_username" {
  type    = string
  default = "experimentos"
}

variable "db_backup_retention_days" {
  type    = number
  default = 7
}

variable "db_deletion_protection" {
  type    = bool
  default = true
}

# --- ElastiCache Redis ---------------------------------------------------------

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.small"
}

variable "redis_engine_version" {
  type    = string
  default = "7.1"
}

variable "redis_num_cache_clusters" {
  description = "Primary + replicas. >= 2 enables automatic failover / Multi-AZ."
  type        = number
  default     = 2
}

# --- ECR -----------------------------------------------------------------------

variable "ecr_repositories" {
  description = "ECR repositories to create (image names)."
  type        = list(string)
  default     = ["experimentos-api", "experimentos-frontend"]
}

variable "ecr_keep_images" {
  description = "Number of images kept per repository by the lifecycle policy."
  type        = number
  default     = 50
}

variable "tags" {
  description = "Extra tags applied to every resource."
  type        = map(string)
  default     = {}
}
