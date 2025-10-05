# Deployment Guide

This guide walks through deploying Scry_Ingestor in common environments. Choose the option that best matches your infrastructure and operational requirements.

## 1. Local Development

1. Install dependencies with Poetry:
   ```bash
   poetry install
   ```
2. Start the API:
   ```bash
   poetry run uvicorn scry_ingestor.api.main:app --reload
   ```
3. Optional: Launch background workers for Celery tasks:
   ```bash
   poetry run celery -A scry_ingestor.tasks.celery_app worker --loglevel=info
   ```

### Environment Variables

Create a `.env` file based on `.env.example` and ensure the following values are set:

- `SCRY_API_KEYS` (JSON array of API keys)
- `SCRY_DATABASE_URL` (PostgreSQL, MySQL, or SQLite connection string)
- `SCRY_BROKER_URL` (Message broker for Celery, e.g., `redis://localhost:6379/0`)
- `SCRY_RESULT_BACKEND` (Optional Celery result backend)

## 2. Docker

1. Build the image:
   ```bash
   docker build -t scry-ingestor:latest .
   ```
2. Run the container:
   ```bash
   docker run -p 8000:8000 --env-file .env scry-ingestor:latest
   ```
3. Access the API at `http://localhost:8000/docs`.

### Docker Compose

Use the provided `docker-compose.yml` to launch API, worker, broker, and database services together:

```bash
docker compose up --build
```

## 3. Kubernetes

### Prerequisites

- Container image pushed to your registry
- Kubernetes cluster (EKS, GKE, AKS, or self-managed)
- Ingress controller (NGINX, Traefik, etc.)

### Deployment Steps

1. Create Kubernetes secrets for environment variables and API keys:
   ```bash
   kubectl create secret generic scry-env --from-env-file=.env.production
   ```
2. Apply the deployment manifests (example skeleton):

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: scry-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: scry-api
  template:
    metadata:
      labels:
        app: scry-api
    spec:
      containers:
        - name: api
          image: ghcr.io/your-org/scry-ingestor:latest
          ports:
            - containerPort: 8000
          envFrom:
            - secretRef:
                name: scry-env
```

3. Expose the service via LoadBalancer or Ingress and configure TLS.
4. Deploy Celery workers and a broker (e.g., RabbitMQ, Redis) as separate deployments/statefulsets.
5. Configure horizontal pod autoscaling based on CPU or custom metrics (e.g., queue depth).

## 4. AWS Reference Architecture

- **Compute**: EKS (Kubernetes) or ECS Fargate
- **Storage**: S3 for raw artifacts, RDS PostgreSQL for metadata
- **Messaging**: Amazon MQ (RabbitMQ) or Amazon SQS
- **Secrets**: AWS Secrets Manager for API keys and credentials
- **Observability**: CloudWatch logging + Prometheus/Grafana (AMP)

### Example: ECS Fargate

1. Build and push the image to Amazon ECR.
2. Create a Task Definition with:
   - Container port 8000
   - Environment variables from Secrets Manager or SSM Parameter Store
   - Auto-scaling policy on CPU utilization
3. Deploy the service behind an Application Load Balancer with HTTPS listeners.
4. Use AWS Lambda or EventBridge to trigger ingestion tasks if running in event-driven mode.

## 5. Google Cloud (GCP)

- Deploy to Cloud Run for the API (serverless, HTTPS by default).
- Use Cloud Tasks or Pub/Sub for asynchronous ingestion.
- Store artifacts in Cloud Storage and metadata in Cloud SQL.
- Configure IAM-based secrets with Secret Manager.

## 6. Microsoft Azure

- Run the API in Azure Container Apps or AKS.
- Use Azure Service Bus or Storage Queues for task distribution.
- Store metadata in Azure SQL Database.
- Monitor performance with Azure Monitor + Application Insights.

## 7. Production Hardening Checklist

- ☑️ Configure HTTPS termination and enforce TLS 1.2+
- ☑️ Rotate API keys regularly and audit access logs
- ☑️ Enable rate limiting and WAF rules on the ingress layer
- ☑️ Set resource requests/limits for all containers
- ☑️ Configure structured logging (JSON) shipped to a centralized platform
- ☑️ Enable health probes (`/health/live`, `/health/ready`)
- ☑️ Set up Prometheus scraping on `/metrics`
- ☑️ Back up the metadata database and verify restore procedures
- ☑️ Run Celery workers with autoscaling and dead-letter queues for failed jobs

## 8. Disaster Recovery

- Maintain infrastructure-as-code (Terraform/Helm) for quick redeployments.
- Implement multi-region S3 replication for raw data.
- Periodically test restoring ingestion metadata from backups.

## 9. Support

Reach out to the platform team or open a GitHub issue for deployment assistance.
