output "region" {
  value = var.region
}

output "vpc_id" {
  value = module.vpc.vpc_id
}

output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "kubeconfig_command" {
  description = "Run this to point kubectl at the cluster."
  value       = "aws eks update-kubeconfig --region ${var.region} --name ${module.eks.cluster_name}"
}

output "oidc_provider_arn" {
  description = "For IRSA roles (External Secrets, AWS Load Balancer Controller)."
  value       = module.eks.oidc_provider_arn
}

output "postgres_endpoint" {
  description = "host:port of the RDS instance."
  value       = aws_db_instance.postgres.endpoint
}

output "postgres_master_secret_arn" {
  description = "Secrets Manager secret holding the RDS master username/password (JSON)."
  value       = aws_db_instance.postgres.master_user_secret[0].secret_arn
}

output "redis_primary_endpoint" {
  description = "Use as REDIS_URL=rediss://<this>:6379/0 (TLS in transit is enabled)."
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "ecr_repository_urls" {
  value = { for k, r in aws_ecr_repository.this : k => r.repository_url }
}
