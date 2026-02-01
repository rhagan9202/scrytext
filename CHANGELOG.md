# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [1.0.0] - 2026-01-28

### Added
- Stable ingestion service with adapter pattern covering JSON, CSV, Excel, Word, PDF, and REST sources.
- Async FastAPI API with Celery background tasks, health checks, and graceful shutdown.
- Configuration profiles, environment validation, and optional AWS Secrets Manager integration.
- Kafka event publishing with Schema Registry support and health degradation handling.
- Observability via Prometheus metrics, Grafana dashboards, and structured logging.
- Operational tooling for Docker, Kubernetes, Terraform, and migration workflows.

### Changed
- Documentation consolidated across deployment, monitoring, and operational hardening guides.

