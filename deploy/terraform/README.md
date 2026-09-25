# ExperimentOS on AWS (Terraform)

Minimal, real infrastructure for running ExperimentOS on AWS. It creates the
network, the Kubernetes cluster and the two data stores that have a clear
managed-service answer. Everything else is either deployed in-cluster or left
as a documented choice.

## What this stack creates

| File | Resources |
|---|---|
| `main.tf` | VPC across 2-3 AZs (`terraform-aws-modules/vpc`): public subnets (load balancers), private subnets (nodes), isolated database subnets, NAT gateway(s) |
| `eks.tf` | EKS cluster (`terraform-aws-modules/eks` v20), one managed node group (AL2023), core add-ons, EBS CSI driver with IRSA, access entries (the applying identity becomes cluster admin) |
| `data-stores.tf` | RDS PostgreSQL 16 (Multi-AZ, gp3, encrypted, master password managed by RDS in Secrets Manager), ElastiCache Redis 7 (replication group, TLS in transit, encrypted at rest), security groups that allow only the EKS node SG, ECR repos `experimentos-api` / `experimentos-frontend` (immutable tags, scan on push, lifecycle policy) |
| `outputs.tf` | Cluster name/endpoint, kubeconfig command, RDS endpoint and secret ARN, Redis endpoint, ECR URLs |

## Where each component runs

| Component | Where | Notes |
|---|---|---|
| api, event-consumer, celery-worker, celery-beat, frontend | EKS, Helm chart `deploy/helm/experimentos`, synced by ArgoCD | See `deploy/argocd/` |
| PostgreSQL | **RDS** (this stack) | `DATABASE_URL=postgres://experimentos:<pw>@<postgres_endpoint>/experimentos` |
| Redis | **ElastiCache** (this stack) | `REDIS_URL=rediss://<redis_primary_endpoint>:6379/0` (`rediss` because TLS is on) |
| Kafka | *Choice, not built here* | **Amazon MSK** (managed, IAM or SASL/SCRAM auth). The app's producer/consumer only pass `bootstrap.servers` today (`apps/events/producer.py:30`, `apps/events/consumer.py:93`), so MSK needs either the plaintext/TLS listener inside the VPC or a backend change to pass `security.protocol`/SASL settings. Alternative: Strimzi operator in-cluster. |
| ClickHouse | *Choice, not built here* | **ClickHouse Cloud** (AWS PrivateLink) or the Altinity ClickHouse operator in-cluster on EBS gp3 volumes (the EBS CSI driver is installed for this). |
| Sticky assignments (Cassandra/Scylla) | *Choice, not built here* | **Amazon Keyspaces** is CQL-compatible but needs TLS + SigV4 auth plugin (backend change in `apps/engine/sticky.py:37`) and does not support `SimpleStrategy` keyspace creation used by `ensure_schema()`. Alternatives: Scylla Operator in-cluster, or disable with `CASSANDRA_STICKY_ENABLED=False` (assignment stays deterministic via hashing; sticky only matters when allocations change). |
| RabbitMQ (Celery broker) | *Choice, not built here* | **Amazon MQ for RabbitMQ**, or the RabbitMQ cluster operator in-cluster. |
| Secrets | AWS Secrets Manager -> External Secrets Operator -> Kubernetes Secret `experimentos-secrets` | `values-prod.yaml` sets `existingSecret: experimentos-secrets` |
| Observability | kube-prometheus-stack (Prometheus Operator) + Grafana/Tempo/Loki | Chart ships ServiceMonitors behind `serviceMonitor.enabled` |

Cluster add-ons that are expected but not installed by this stack (install them
with Helm/ArgoCD after the cluster exists): ingress-nginx (or AWS Load Balancer
Controller), cert-manager, External Secrets Operator, metrics-server (required
for the HPAs), kube-prometheus-stack, ArgoCD.

## Usage

```bash
cd deploy/terraform
cp terraform.tfvars.example terraform.tfvars    # edit

terraform init \
  -backend-config="bucket=<state-bucket>" \
  -backend-config="key=experimentos/prod.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="dynamodb_table=<lock-table>"
terraform plan -out plan.tfplan
terraform apply plan.tfplan

$(terraform output -raw kubeconfig_command)
```

Then install cluster add-ons, create the `experimentos-secrets` Secret (via
External Secrets), and apply `deploy/argocd/project.yaml` +
`deploy/argocd/application-prod.yaml`.

Validation without AWS credentials:

```bash
terraform fmt -check -recursive
terraform init -backend=false && terraform validate
```

## Cost/HA knobs

Defaults are HA (3 AZs, NAT per AZ, Multi-AZ RDS, Redis primary + replica).
For a dev environment set `single_nat_gateway = true`, `db_multi_az = false`,
`db_deletion_protection = false`, `redis_num_cache_clusters = 1`.

## Not covered (deliberately)

- No MSK / ClickHouse / Keyspaces / Amazon MQ resources (see table above).
- No WAF, no GuardDuty, no VPC endpoints for ECR/S3 (worth adding to cut NAT cost).
- No GitHub OIDC role for pushing to ECR - CI pushes to GHCR by default.
