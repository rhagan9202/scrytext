# Deployment Guide

This guide provides comprehensive instructions for deploying Scry_Ingestor to Kubernetes using Helm and managing AWS infrastructure with Terraform.
z
> **📋 Run-Up Tasks Status**: ✅ **COMPLETE** - See [RUNUP_TASKS_COMPLETE.md](./RUNUP_TASKS_COMPLETE.md) for validation results.  
> All pre-deployment checks passed: Docker builds (474MB), security scans (0 CRITICAL/HIGH), config validation, tests passing.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Docker Build & Security Scanning](#docker-build--security-scanning)
3. [AWS Infrastructure Deployment](#aws-infrastructure-deployment)
4. [Kubernetes Deployment with Helm](#kubernetes-deployment-with-helm)
5. [CI/CD Pipeline](#cicd-pipeline)
6. [Monitoring & Observability](#monitoring--observability)
7. [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Tools

- **Docker**: 20.10+ with BuildKit support
- **Kubernetes**: 1.25+ (kubectl configured)
- **Helm**: 3.10+
- **Terraform**: 1.0+
- **AWS CLI**: 2.x configured with credentials
- **Poetry**: 1.8+ for Python dependency management

### Security Scanning Tools (Optional)

- **Trivy**: Container vulnerability scanner
- **Grype**: Vulnerability scanner
- **Syft**: SBOM generator

Install scanning tools:
```bash
# Trivy
wget https://github.com/aquasecurity/trivy/releases/download/v0.50.0/trivy_0.50.0_Linux-64bit.tar.gz
tar zxvf trivy_0.50.0_Linux-64bit.tar.gz
sudo mv trivy /usr/local/bin/

# Grype
curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin

# Syft
curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin
```

## Docker Build & Security Scanning

### Building Docker Images

The project uses a multi-stage Dockerfile optimized for security and size:

```bash
# Build runtime image (API service)
docker build --target runtime -t scry-ingestor:latest .

# Build Celery worker image
docker build --target celery-worker -t scry-ingestor-worker:latest .

# Build development image (with test dependencies)
docker build --target development -t scry-ingestor:dev .

# Build with specific version tag
docker build --target runtime -t scry-ingestor:v1.0.0 .
```

### Multi-Platform Builds

For ARM and AMD64 support:

```bash
# Setup buildx
docker buildx create --use --name multiarch

# Build and push multi-platform image
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --target runtime \
  -t ghcr.io/your-org/scry-ingestor:latest \
  --push .
```

### Security Scanning

Run comprehensive security scans:

```bash
# Run all security checks
./scripts/security-scan.sh scry-ingestor:latest

# Individual scans
trivy image --severity HIGH,CRITICAL scry-ingestor:latest
grype scry-ingestor:latest
syft scry-ingestor:latest -o cyclonedx-json > sbom.json
```

Reports are saved to `./security-reports/` with symlinks to latest results.

### Fixing Vulnerabilities

Update vulnerable dependencies:

```bash
# Update Python packages
poetry update fastapi python-multipart starlette

# Update lock file
poetry lock --no-update

# Rebuild and rescan
docker build --target runtime -t scry-ingestor:latest .
./scripts/security-scan.sh scry-ingestor:latest
```

## AWS Infrastructure Deployment

### Initial Setup

1. **Create S3 backend for Terraform state:**

```bash
# Create S3 bucket for state
aws s3api create-bucket \
  --bucket scry-terraform-state-<account-id> \
  --region us-east-1

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket scry-terraform-state-<account-id> \
  --versioning-configuration Status=Enabled

# Create DynamoDB table for state locking
aws dynamodb create-table \
  --table-name terraform-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

2. **Update backend configuration in `terraform/main.tf`:**

```hcl
terraform {
  backend "s3" {
    bucket         = "scry-terraform-state-<your-account-id>"
    key            = "scry-ingestor/<environment>/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-state-lock"
    encrypt        = true
  }
}
```

### Deploy Staging Environment

```bash
cd terraform/

# Initialize Terraform
terraform init

# Plan deployment
terraform plan -var-file=environments/staging.tfvars -out=staging.tfplan

# Review plan and apply
terraform apply staging.tfplan

# Save outputs for Helm configuration
terraform output -json > ../helm/scry-ingestor/terraform-outputs-staging.json
```

### Deploy Production Environment

```bash
cd terraform/

# Use separate workspace for production
terraform workspace new production
terraform workspace select production

# Plan deployment
terraform plan -var-file=environments/production.tfvars -out=production.tfplan

# Review plan and apply (requires approval in production)
terraform apply production.tfplan

# Save outputs
terraform output -json > ../helm/scry-ingestor/terraform-outputs-production.json
```

### Infrastructure Outputs

Terraform provides these outputs:

- **eks_cluster_endpoint**: EKS API endpoint
- **eks_cluster_certificate_authority_data**: Cluster CA cert
- **rds_endpoint**: PostgreSQL connection string
- **redis_endpoint**: ElastiCache Redis endpoint
- **kafka_bootstrap_brokers**: MSK Kafka broker list

## Kubernetes Deployment with Helm

### Configure kubectl for EKS

```bash
# Update kubeconfig for staging
aws eks update-kubeconfig \
  --region us-east-1 \
  --name scry-ingestor-staging

# Verify connection
kubectl cluster-info
kubectl get nodes
```

### Create Kubernetes Secrets

```bash
# Create namespace
kubectl create namespace scry-staging

# Create database secret
kubectl create secret generic scry-staging-postgresql \
  --namespace scry-staging \
  --from-literal=password='<database-password>' \
  --from-literal=url='postgresql://scry_app:<password>@<rds-endpoint>:5432/scry_staging'

# Create Redis secret
kubectl create secret generic scry-staging-redis \
  --namespace scry-staging \
  --from-literal=password='<redis-password>' \
  --from-literal=url='redis://:<password>@<redis-endpoint>:6379/0'

# Create API key secret
kubectl create secret generic scry-api-keys \
  --namespace scry-staging \
  --from-literal=admin-key='<generate-secure-key>'
```

### Deploy with Helm

#### Staging Deployment

```bash
cd helm/scry-ingestor/

# Install chart
helm install scry-ingestor . \
  --namespace scry-staging \
  --values values-staging.yaml \
  --set image.tag=develop-latest

# Verify deployment
kubectl get pods -n scry-staging
kubectl get svc -n scry-staging
kubectl logs -n scry-staging -l app.kubernetes.io/component=api
```

#### Production Deployment

```bash
cd helm/scry-ingestor/

# Create production namespace
kubectl create namespace scry-production

# Create production secrets (same as staging but with production values)

# Install chart with production values
helm install scry-ingestor . \
  --namespace scry-production \
  --values values-production.yaml \
  --set image.tag=v1.0.0

# Verify deployment
kubectl get pods -n scry-production
```

### Helm Operations

```bash
# Upgrade deployment
helm upgrade scry-ingestor ./helm/scry-ingestor \
  --namespace scry-staging \
  --values helm/scry-ingestor/values-staging.yaml \
  --set image.tag=develop-abc123

# Rollback to previous version
helm rollback scry-ingestor -n scry-staging

# View history
helm history scry-ingestor -n scry-staging

# Uninstall
helm uninstall scry-ingestor -n scry-staging
```

### Running Database Migrations

```bash
# Run migrations as Kubernetes job
kubectl run alembic-migrate \
  --namespace scry-staging \
  --image=scry-ingestor:develop-latest \
  --restart=Never \
  --command -- alembic upgrade head

# Check migration logs
kubectl logs -n scry-staging alembic-migrate

# Clean up job
kubectl delete pod alembic-migrate -n scry-staging
```

## CI/CD Pipeline

The project includes GitHub Actions workflows for automated deployment.

### CI/CD Workflow

Triggered on push to `develop` or version tags (`v*`):

1. **Lint**: Runs ruff, black, mypy
2. **Test**: Executes pytest with coverage
3. **Security**: Runs Bandit and Safety checks
4. **Build**: Creates multi-platform Docker images
5. **Scan**: Vulnerability scanning with Trivy/Grype, SBOM generation
6. **Deploy Staging**: Auto-deploys `develop` branch to staging
7. **Deploy Production**: Auto-deploys version tags to production

### Triggering Deployments

```bash
# Deploy to staging (push to develop)
git checkout develop
git merge feature/my-feature
git push origin develop
# GitHub Actions automatically deploys to staging

# Deploy to production (create version tag)
git checkout main
git merge develop
git tag -a v1.0.0 -m "Release v1.0.0"
git push origin main --tags
# GitHub Actions automatically deploys to production
```

### Required GitHub Secrets

Configure these in your GitHub repository settings:

- `AWS_ACCESS_KEY_ID`: AWS credentials
- `AWS_SECRET_ACCESS_KEY`: AWS secret
- `KUBE_CONFIG_DATA`: Base64-encoded kubeconfig
- `CODECOV_TOKEN`: Code coverage upload
- `GITHUB_TOKEN`: Automatically provided by GitHub

### Manual Workflow Dispatch

Trigger deployments manually from GitHub Actions UI:

1. Go to Actions tab
2. Select "CI/CD Pipeline" workflow
3. Click "Run workflow"
4. Select branch and environment

## Monitoring & Observability

### Prometheus Metrics

Scry_Ingestor exposes metrics at `/metrics`:

```bash
# Port-forward to access metrics locally
kubectl port-forward -n scry-staging svc/scry-ingestor-api 8000:80

# View metrics
curl http://localhost:8000/metrics
```

### Grafana Dashboards

Import dashboards from `grafana/dashboards/`:

1. Open Grafana UI
2. Import dashboard
3. Upload `scry-ingestor-overview.json`
4. Select Prometheus data source

### OpenTelemetry Tracing

Traces are exported to OpenTelemetry Collector:

```bash
# View traces in Jaeger UI
kubectl port-forward -n observability svc/jaeger-query 16686:16686

# Open browser
open http://localhost:16686
```

### Log Aggregation

Logs are collected by Fluentd/Fluent Bit:

```bash
# View logs in CloudWatch
aws logs tail /aws/eks/scry-ingestor-staging/application --follow

# Query logs with kubectl
kubectl logs -n scry-staging -l app.kubernetes.io/name=scry-ingestor --tail=100 -f
```

## Troubleshooting

### Pod Not Starting

```bash
# Check pod status
kubectl describe pod -n scry-staging <pod-name>

# View events
kubectl get events -n scry-staging --sort-by='.lastTimestamp'

# Check logs
kubectl logs -n scry-staging <pod-name> --previous
```

### Database Connection Issues

```bash
# Test database connectivity from pod
kubectl exec -it -n scry-staging <pod-name> -- \
  psql $DATABASE_URL -c "SELECT 1"

# Check secret exists
kubectl get secret scry-staging-postgresql -n scry-staging

# Verify RDS security group rules
aws ec2 describe-security-groups \
  --group-ids <rds-sg-id> \
  --query 'SecurityGroups[].IpPermissions'
```

### Performance Issues

```bash
# Check resource usage
kubectl top pods -n scry-staging
kubectl top nodes

# View HPA status
kubectl get hpa -n scry-staging

# Check for throttling
kubectl describe pod -n scry-staging <pod-name> | grep -i throttle
```

### Rollback Procedure

```bash
# List Helm releases
helm list -n scry-staging

# View release history
helm history scry-ingestor -n scry-staging

# Rollback to previous version
helm rollback scry-ingestor <revision-number> -n scry-staging

# Or rollback via kubectl
kubectl rollout undo deployment/scry-ingestor-api -n scry-staging
```

### Security Scan Failures

```bash
# Review vulnerability reports
cat security-reports/trivy-latest.json
cat security-reports/grype-latest.json

# Update vulnerable packages
poetry update <package-name>

# Rebuild and rescan
docker build -t scry-ingestor:latest .
./scripts/security-scan.sh scry-ingestor:latest
```

## Versioning Strategy

The project follows [Semantic Versioning](https://semver.org/):

- **Major** (1.0.0): Breaking changes
- **Minor** (0.1.0): New features (backward compatible)
- **Patch** (0.0.1): Bug fixes

Use the version helper script:

```bash
# Suggest next version based on commits
./scripts/version.sh suggest

# Bump version and create tag
./scripts/version.sh bump auto

# Generate changelog
./scripts/version.sh changelog > CHANGELOG.md
```

## Support

For issues or questions:

1. Check [Troubleshooting](#troubleshooting) section
2. Review logs and metrics
3. Consult [MONITORING.md](MONITORING.md) for observability details
4. Open a GitHub issue with full context
