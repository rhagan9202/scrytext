# Operational Hardening Guide

This guide covers the production-ready operational features of Scry_Ingestor, including health checks, graceful shutdown, and configuration reload capabilities.

## Table of Contents

- [Health Checks](#health-checks)
- [Graceful Shutdown](#graceful-shutdown)
- [Configuration Reload](#configuration-reload)
- [Kubernetes Integration](#kubernetes-integration)
- [Monitoring & Observability](#monitoring--observability)

## Health Checks

Scry_Ingestor provides comprehensive health check endpoints for monitoring service availability and dependency health.

### Endpoints

#### GET /health

**Purpose**: Liveness probe - indicates if the service is alive and responding.

**Use case**: Kubernetes liveness probes, basic uptime monitoring.

**Response**:
```json
{
  "status": "healthy",
  "service": "scry_ingestor",
  "checked_at": "2025-10-05T12:34:56.789Z"
}
```

**Status codes**:
- `200 OK`: Service is alive
- Checks only critical components (API service itself)

#### GET /ready

**Purpose**: Readiness probe - indicates if the service is ready to accept traffic.

**Use case**: Kubernetes readiness probes, load balancer health checks.

**Query parameters**:
- `detailed` (boolean, default: false): Include detailed component status

**Response** (without detailed):
```json
{
  "status": "healthy",
  "service": "scry_ingestor",
  "version": "1.0.0",
  "checked_at": "2025-10-05T12:34:56.789Z",
  "uptime_seconds": 3600.5,
  "components": {}
}
```

**Response** (with `?detailed=true`):
```json
{
  "status": "healthy",
  "service": "scry_ingestor",
  "version": "1.0.0",
  "checked_at": "2025-10-05T12:34:56.789Z",
  "uptime_seconds": 3600.5,
  "components": {
    "database": {
      "name": "database",
      "status": "healthy",
      "message": "Database connection successful",
      "checked_at": "2025-10-05T12:34:56.789Z",
      "metadata": {
        "driver": "postgresql+psycopg2"
      }
    },
    "redis": {
      "name": "redis",
      "status": "healthy",
      "message": "Redis connection successful",
      "checked_at": "2025-10-05T12:34:56.789Z",
      "metadata": {
        "version": "7.0.5",
        "uptime_seconds": 86400
      }
    },
    "celery": {
      "name": "celery",
      "status": "healthy",
      "message": "2 worker(s) active",
      "checked_at": "2025-10-05T12:34:56.789Z",
      "metadata": {
        "workers": ["worker1@hostname", "worker2@hostname"],
        "worker_count": 2
      }
    },
    "kafka": {
      "name": "kafka",
      "status": "healthy",
      "message": "Kafka status checked",
      "checked_at": "2025-10-05T12:34:56.789Z",
      "metadata": {}
    }
  }
}
```

**Status values**:
- `healthy`: All required components are operational
- `degraded`: Some optional components are unavailable, but service can still function
- `unhealthy`: Critical components are unavailable

**Status codes**:
- `200 OK`: Always returns 200 (status is in response body)

#### GET /health/detailed

**Purpose**: Comprehensive health status for troubleshooting and monitoring dashboards.

**Use case**: Detailed status pages, monitoring dashboards, troubleshooting.

**Response**: Same as `/ready?detailed=true` but always includes full component details.

### Health Check Components

The system monitors these components:

1. **API**: FastAPI service itself (always healthy if responding)
2. **Database**: PostgreSQL connection and query execution
3. **Redis**: Redis connection and ping
4. **Celery**: Worker availability and count
5. **Kafka**: Message queue connectivity

### Custom Health Checks

You can register custom health checks for new components:

```python
from scry_ingestor.utils.health import ComponentHealth, HealthStatus, get_health_checker

def check_my_service() -> ComponentHealth:
    """Check custom service health."""
    try:
        # Your health check logic
        result = my_service.ping()
        return ComponentHealth(
            name="my_service",
            status=HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY,
            message="Service is operational" if result else "Service unreachable",
            metadata={"version": my_service.version}
        )
    except Exception as e:
        return ComponentHealth(
            name="my_service",
            status=HealthStatus.UNHEALTHY,
            message=f"Health check failed: {e}"
        )

# Register the check
checker = get_health_checker()
checker.register_check("my_service", check_my_service)
```

## Graceful Shutdown

Scry_Ingestor implements graceful shutdown to ensure clean resource cleanup and request draining.

### Signal Handling

The service handles these signals:

- **SIGTERM**: Graceful shutdown (default Kubernetes termination signal)
- **SIGINT**: Graceful shutdown (Ctrl+C)
- **SIGHUP**: Configuration reload (Unix only)

### Shutdown Sequence

When a shutdown signal is received:

1. **Stop accepting new requests**: Service marks itself as not ready
2. **Drain in-flight requests**: Wait up to 2 seconds for active requests to complete
3. **Close connections**: Close Redis and database connection pools
4. **Execute shutdown handlers**: Run registered cleanup handlers in LIFO order
5. **Exit cleanly**: Process exits with code 0

### Custom Shutdown Handlers

Register custom cleanup logic:

```python
from scry_ingestor.utils.signals import get_shutdown_manager

shutdown_manager = get_shutdown_manager()

def cleanup_my_resources():
    """Clean up custom resources."""
    my_connection_pool.close()
    my_cache.flush()

shutdown_manager.register_handler(cleanup_my_resources)
```

### Kubernetes Pod Termination

Configure your Pod spec for graceful shutdown:

```yaml
spec:
  terminationGracePeriodSeconds: 30  # Allow 30s for graceful shutdown
  containers:
  - name: scry-ingestor
    image: scry-ingestor:latest
    lifecycle:
      preStop:
        exec:
          command: ["/bin/sh", "-c", "sleep 5"]  # Delay before SIGTERM
```

## Configuration Reload

Scry_Ingestor supports hot-reloading of certain configurations without service restart.

### Reloadable Configuration

**Can be reloaded**:
- Adapter configurations (PDF, Word, JSON, CSV, Excel, REST, BeautifulSoup)
- Environment-specific settings (from `settings.<environment>.yaml`)
- Feature flags
- Log levels
- Operational thresholds

**Cannot be reloaded** (requires restart):
- Database URL
- Redis URL
- Kafka broker URLs
- Server port bindings

### Reload Methods

#### Method 1: SIGHUP Signal (Unix only)

```bash
# Find the process ID
ps aux | grep "uvicorn"

# Send SIGHUP
kill -HUP <pid>
```

#### Method 2: API Endpoint

```bash
# Reload via API
curl -X POST http://localhost:8000/api/v1/config/reload

# Response
{
  "adapters": {
    "pdf": { ... },
    "word": { ... },
    ...
  },
  "settings": {
    "environment": "production",
    "log_level": "INFO",
    ...
  },
  "status": "success"
}
```

#### Method 3: Programmatically

```python
from scry_ingestor.utils.reload import reload_configuration

# Async context
result = await reload_configuration()

# Or in sync context
from scry_ingestor.utils.reload import get_config_reloader

reloader = get_config_reloader()
result = reloader.reload_all()
```

### Configuration File Structure

```
config/
├── settings.base.yaml          # Base settings
├── settings.development.yaml   # Dev environment
├── settings.production.yaml    # Prod environment
├── pdf_adapter.yaml            # PDF adapter config
├── word_adapter.yaml           # Word adapter config
├── json_adapter.yaml           # JSON adapter config
├── csv_adapter.yaml            # CSV adapter config
├── excel_adapter.yaml          # Excel adapter config
├── rest_adapter.yaml           # REST adapter config
└── soup_adapter.yaml           # BeautifulSoup adapter config
```

## Kubernetes Integration

### Complete Deployment Example

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: scry-ingestor
  labels:
    app: scry-ingestor
spec:
  replicas: 3
  selector:
    matchLabels:
      app: scry-ingestor
  template:
    metadata:
      labels:
        app: scry-ingestor
    spec:
      terminationGracePeriodSeconds: 30
      containers:
      - name: scry-ingestor
        image: scry-ingestor:1.0.0
        ports:
        - containerPort: 8000
          name: http
        env:
        - name: SCRY_ENVIRONMENT
          value: "production"
        - name: SCRY_DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: scry-secrets
              key: database-url
        - name: SCRY_REDIS_URL
          valueFrom:
            secretKeyRef:
              name: scry-secrets
              key: redis-url
        
        # Liveness probe: Is the service alive?
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
          timeoutSeconds: 3
          failureThreshold: 3
        
        # Readiness probe: Can it accept traffic?
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 2
        
        # Resource limits
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        
        # Graceful shutdown
        lifecycle:
          preStop:
            exec:
              command: ["/bin/sh", "-c", "sleep 5"]
```

### Service and Ingress

```yaml
apiVersion: v1
kind: Service
metadata:
  name: scry-ingestor
spec:
  selector:
    app: scry-ingestor
  ports:
  - port: 80
    targetPort: 8000
  type: ClusterIP

---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: scry-ingestor
  annotations:
    nginx.ingress.kubernetes.io/health-check-path: "/health"
spec:
  rules:
  - host: api.scry-ingestor.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: scry-ingestor
            port:
              number: 80
```

## Monitoring & Observability

### Prometheus Metrics

Health check metrics are automatically exported at `/metrics`:

```
# HELP scry_ingestor_health_status Component health status (1=healthy, 0.5=degraded, 0=unhealthy)
# TYPE scry_ingestor_health_status gauge
scry_ingestor_health_status{component="database"} 1.0
scry_ingestor_health_status{component="redis"} 1.0
scry_ingestor_health_status{component="celery"} 1.0
scry_ingestor_health_status{component="kafka"} 0.5

# HELP scry_ingestor_uptime_seconds Service uptime in seconds
# TYPE scry_ingestor_uptime_seconds counter
scry_ingestor_uptime_seconds 3600.5
```

### Grafana Dashboard

Import the dashboard from `grafana/dashboards/scry-ingestor-overview.json` to monitor:

- Service uptime and health status
- Component availability over time
- Request latency and error rates
- Resource utilization

### Alerting

Configure alerts in `grafana/alerts/scry_ingestor_alerts.yml`:

```yaml
groups:
- name: scry_ingestor
  interval: 30s
  rules:
  - alert: ScryIngestorUnhealthy
    expr: scry_ingestor_health_status{component="database"} < 1
    for: 2m
    labels:
      severity: critical
    annotations:
      summary: "Scry Ingestor component unhealthy"
      description: "Component {{ $labels.component }} is unhealthy for more than 2 minutes"
```

### Logging

All operational events are logged with structured context:

```json
{
  "timestamp": "2025-10-05T12:34:56.789Z",
  "level": "INFO",
  "message": "Received SIGTERM, initiating graceful shutdown...",
  "context": {
    "service": "scry_ingestor",
    "environment": "production"
  }
}
```

## Best Practices

### Health Check Configuration

1. **Set appropriate timeouts**: Health checks should complete within 3-5 seconds
2. **Use liveness for restarts**: Liveness probes should only check if the process is alive
3. **Use readiness for traffic**: Readiness probes should check all dependencies
4. **Avoid cascading failures**: Don't make readiness depend on downstream service readiness

### Graceful Shutdown

1. **Configure termination grace period**: Allow at least 30 seconds
2. **Implement idempotent cleanup**: Shutdown handlers may be called multiple times
3. **Log shutdown progress**: Help with debugging stuck shutdowns
4. **Test shutdown behavior**: Verify cleanup happens correctly

### Configuration Reload

1. **Validate before reload**: Ensure new config is valid before applying
2. **Use versioning**: Track which config version is active
3. **Log all reloads**: Audit trail for configuration changes
4. **Test in staging**: Verify config changes don't break service

## Troubleshooting

### Service Won't Start

**Check**:
1. Database connectivity: `psql $SCRY_DATABASE_URL`
2. Redis connectivity: `redis-cli -u $SCRY_REDIS_URL ping`
3. Configuration syntax: `poetry run python -c "from scry_ingestor.utils.config import get_settings; get_settings()"`

### Health Checks Failing

**Check**:
1. Component logs: `kubectl logs <pod> | grep -i error`
2. Detailed health status: `curl http://localhost:8000/health/detailed`
3. Component connectivity from pod: `kubectl exec <pod> -- curl <component-url>`

### Graceful Shutdown Not Working

**Check**:
1. Signal handling installed: Look for "Installed signal handler" in logs
2. Termination grace period: Ensure Kubernetes allows enough time
3. Shutdown handlers: Verify custom handlers don't hang

### Configuration Reload Not Working

**Check**:
1. File permissions: Ensure config files are readable
2. YAML syntax: Validate with `yamllint config/*.yaml`
3. Reload logs: Check for "Configuration reload complete" message

## See Also

- [Deployment Guide](DEPLOYMENT_GUIDE.md)
- [Monitoring Guide](MONITORING.md)
- [Performance Tuning](PERFORMANCE.md)
- [API Reference](API_REFERENCE.md)
