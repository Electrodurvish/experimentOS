# -----------------------------------------------------------------------------
# RDS PostgreSQL - source of truth for experiments, versions, audit log.
# The master password is generated and stored by RDS in Secrets Manager
# (manage_master_user_password); it never appears in Terraform state.
# -----------------------------------------------------------------------------
resource "aws_security_group" "rds" {
  name        = "${local.cluster_name}-rds"
  description = "PostgreSQL access from EKS nodes"
  vpc_id      = module.vpc.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_nodes" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = module.eks.node_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
  description                  = "PostgreSQL from EKS worker nodes"
}

resource "aws_db_parameter_group" "postgres" {
  name_prefix = "${local.cluster_name}-pg16-"
  family      = "postgres16"
  description = "ExperimentOS PostgreSQL parameters"

  parameter {
    name  = "log_min_duration_statement"
    value = "500"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_db_instance" "postgres" {
  identifier = "${local.cluster_name}-postgres"

  engine               = "postgres"
  engine_version       = var.db_engine_version
  instance_class       = var.db_instance_class
  parameter_group_name = aws_db_parameter_group.postgres.name

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name                     = var.db_name
  username                    = var.db_username
  manage_master_user_password = true

  db_subnet_group_name   = module.vpc.database_subnet_group_name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false
  multi_az               = var.db_multi_az

  backup_retention_period      = var.db_backup_retention_days
  backup_window                = "03:00-04:00"
  maintenance_window           = "sun:04:30-sun:05:30"
  auto_minor_version_upgrade   = true
  performance_insights_enabled = true
  copy_tags_to_snapshot        = true

  deletion_protection       = var.db_deletion_protection
  skip_final_snapshot       = false
  final_snapshot_identifier = "${local.cluster_name}-postgres-final"
}

# -----------------------------------------------------------------------------
# ElastiCache Redis - experiment config cache, distributed locks, event dedup.
# TLS in transit is on, so REDIS_URL must use the rediss:// scheme.
# -----------------------------------------------------------------------------
resource "aws_security_group" "redis" {
  name        = "${local.cluster_name}-redis"
  description = "Redis access from EKS nodes"
  vpc_id      = module.vpc.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "redis_from_nodes" {
  security_group_id            = aws_security_group.redis.id
  referenced_security_group_id = module.eks.node_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 6379
  to_port                      = 6379
  description                  = "Redis from EKS worker nodes"
}

resource "aws_elasticache_subnet_group" "redis" {
  name       = "${local.cluster_name}-redis"
  subnet_ids = module.vpc.database_subnets
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${local.cluster_name}-redis"
  description          = "ExperimentOS cache / locks / dedup"

  engine               = "redis"
  engine_version       = var.redis_engine_version
  node_type            = var.redis_node_type
  port                 = 6379
  parameter_group_name = "default.redis7"

  num_cache_clusters         = var.redis_num_cache_clusters
  automatic_failover_enabled = var.redis_num_cache_clusters > 1
  multi_az_enabled           = var.redis_num_cache_clusters > 1

  subnet_group_name  = aws_elasticache_subnet_group.redis.name
  security_group_ids = [aws_security_group.redis.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  snapshot_retention_limit = 1
  apply_immediately        = false
}

# -----------------------------------------------------------------------------
# ECR - optional alternative to GHCR (CI pushes to GHCR by default).
# -----------------------------------------------------------------------------
resource "aws_ecr_repository" "this" {
  for_each = toset(var.ecr_repositories)

  name                 = each.value
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "this" {
  for_each   = aws_ecr_repository.this
  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last ${var.ecr_keep_images} images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = var.ecr_keep_images
      }
      action = { type = "expire" }
    }]
  })
}
