data "aws_availability_zones" "available" {
  state = "available"

  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

locals {
  cluster_name = "${var.name}-${var.environment}"
  azs          = slice(data.aws_availability_zones.available.names, 0, var.az_count)

  tags = merge(
    {
      Project     = var.name
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.tags,
  )
}

# -----------------------------------------------------------------------------
# VPC: public subnets (load balancers), private subnets (nodes), and isolated
# database subnets (RDS / ElastiCache, no internet route).
# -----------------------------------------------------------------------------
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.16"

  name = local.cluster_name
  cidr = var.vpc_cidr
  azs  = local.azs

  public_subnets   = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, i)]
  private_subnets  = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 4, i + 1)]
  database_subnets = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, i + 100)]

  create_database_subnet_group       = true
  create_database_subnet_route_table = true

  enable_nat_gateway   = true
  single_nat_gateway   = var.single_nat_gateway
  enable_dns_hostnames = true
  enable_dns_support   = true

  # Subnet discovery for the AWS Load Balancer Controller.
  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
  }
}
