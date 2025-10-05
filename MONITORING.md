# Monitoring & Observability Guide

This guide covers how Scry_Ingestor exposes metrics, tracing data, Grafana dashboards, and Prometheus alerting rules to achieve production-grade observability.

## Overview

Scry_Ingestor provides:

- **Prometheus Metrics**: Instrumentation for ingestion attempts, errors, latency, SLA tracking, payload sizes, tracing spans, and validation outcomes.
- **Distributed Tracing**: Lightweight span tracking with correlation ID propagation for end-to-end request visibility.
- **Grafana Dashboards**: Prebuilt visualizations for operational monitoring and tracing/validation insights.
- **Prometheus Alerting Rules**: Warning/critical alerts tailored to ingestion SLA and performance objectives.

## Metrics

Metrics are exposed via the `/metrics` endpoint on the FastAPI service (default port `8000`). The Celery workers reuse the same metrics module, so ensure they run with a Prometheus exporter (e.g., via `prometheus_client.start_http_server`).

### Metric Catalog

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `ingestion_attempts_total` | Counter | `adapter`, `status` | Total ingestion attempts by adapter and status |
| `ingestion_errors_total` | Counter | `error_type` | Total ingestion errors grouped by error type |
| `processing_duration_seconds` | Histogram | *none* | Latency distribution of ingestion pipelines |
| `ingestion_sla_violations_total` | Counter | `adapter`, `severity` | SLA breaches (warning/critical) |
| `ingestion_active_requests` | Gauge | `adapter` | Number of in-flight ingestion requests |
| `ingestion_payload_size_bytes` | Histogram | `adapter` | Payload size distribution in bytes |
| `trace_spans_created_total` | Counter | `operation` | Trace spans created per operation |
| `trace_span_duration_seconds` | Histogram | `operation` | Duration distribution of trace spans |
| `validation_errors_total` | Counter | `adapter`, `error_category` | Validation errors by category |
| `validation_warnings_total` | Counter | `adapter`, `warning_category` | Validation warnings by category |

### Instrumentation Utilities

Use helpers from `scry_ingestor.monitoring.metrics`:

- `record_ingestion_attempt(adapter, status)`
- `record_ingestion_error(error_type)`
- `observe_processing_duration(duration_seconds)`
- `record_sla_violation(adapter, severity="warning")`
- `increment_active_requests(adapter)` / `decrement_active_requests(adapter)`
- `observe_payload_size(adapter, size_bytes)`
- `record_trace_span_created(operation)`
- `observe_trace_span_duration(operation, duration_seconds)`
- `record_validation_error(adapter, error_category="general")`
- `record_validation_warning(adapter, warning_category="general")`

### Example PromQL Queries

```promql
# Total success rate (last 5 minutes)
sum(rate(ingestion_attempts_total{status="success"}[5m]))

# Error rate by adapter
sum(rate(ingestion_attempts_total{status="error"}[5m])) by (adapter)
/
sum(rate(ingestion_attempts_total[5m])) by (adapter)

# Latency percentiles
histogram_quantile(0.95, sum(rate(processing_duration_seconds_bucket[5m])) by (le))

# SLA compliance
1 - (
  sum(increase(ingestion_sla_violations_total[1h]))
  /
  sum(increase(ingestion_attempts_total[1h]))
)
```

## Distributed Tracing & Correlation IDs

The tracing utilities in `scry_ingestor.monitoring.tracing` let you propagate correlation IDs and log spans.

### Core APIs

- `ensure_correlation_id(provided_id: str | None = None) -> str`
- `trace_span(operation: str, correlation_id: str | None = None, **metadata)`
- `extract_correlation_id_from_headers(headers: dict[str, str])`
- `inject_correlation_id_into_headers(headers: dict[str, str], correlation_id: str | None = None)`

### Usage Example

```python
from scry_ingestor.monitoring.tracing import ensure_correlation_id, trace_span
from scry_ingestor.monitoring.metrics import record_trace_span_created, observe_trace_span_duration

async def process_request(request):
    correlation_id = ensure_correlation_id(request.headers.get("X-Correlation-ID"))

    with trace_span("adapter.process", correlation_id=correlation_id) as span:
        record_trace_span_created(span.operation)
        result = await adapter.process()
        span.metadata["records"] = len(result)

    observe_trace_span_duration(span.operation, (span.duration_ms or 0) / 1000)

    return result
```

### Logging Integration

All logging contexts include `correlation_id` by default via `scry_ingestor.utils.logging.setup_logger`. Trace spans also log start/end messages with span IDs for easy cross-reference.

## Grafana Dashboards

Two dashboards are provisioned under `grafana/dashboards/`:

1. **Scry Ingestor - Overview** (`scry-ingestor-overview.json`)
   - Success/error rate stats
   - Latency percentile trends
   - Error type analysis
   - Active request count & SLA violations

2. **Scry Ingestor - Tracing & Validation** (`scry-ingestor-tracing.json`)
   - Trace span creation rates & duration percentiles
   - Validation error/warning breakdowns
   - Payload size distribution

### Import Methods

- **Grafana UI**: Dashboards → Import → Upload JSON
- **Provisioning**: Reference `grafana/dashboards/` folder in provisioning config
- **Kubernetes**: Package dashboards as ConfigMap and mount into Grafana pod (see `grafana/README.md`)

### Recommended Panel Thresholds

| Panel | Warning | Critical |
|-------|---------|----------|
| Processing Duration (p95) | 10s | 30s |
| Error Rate | 5% | 10% |
| Active Requests | 25 | 50 |
| SLA Violations (per hour) | 10 | 25 |

## Prometheus Alerting Rules

Alert rules live under `grafana/alerts/scry_ingestor_alerts.yml` and are organized into critical, warning, and informational groups (
`IngestionHighErrorRate`, `IngestionProcessingP99High`, `IngestionSLAViolationWarning`, etc.).

### Installation (Standalone Prometheus)

1. Copy alert file to Prometheus config directory
2. Update `prometheus.yml`:
   ```yaml
   rule_files:
     - "scry_ingestor_alerts.yml"
   ```
3. Reload Prometheus (`curl -X POST http://<prometheus>/-/reload`)

### Installation (Prometheus Operator)

Create a `PrometheusRule` manifest and paste the alert groups. See `grafana/README.md` for example.

### Alertmanager Integration

Configure routing to Slack/PagerDuty. Example (excerpt):

```yaml
route:
  receiver: "default"
  routes:
    - match:
        service: scry-ingestor
        severity: critical
      receiver: "pagerduty-critical"
    - match:
        service: scry-ingestor
        severity: warning
      receiver: "slack-warnings"
```

## Testing & Validation

### Unit Tests

- `tests/monitoring/test_metrics.py`: Validates new metrics helpers update Prometheus counters, gauges, and histograms correctly.
- `tests/monitoring/test_tracing.py`: Covers correlation ID propagation and `trace_span` behavior (including exception handling and metadata).

Run monitoring-specific tests:

```bash
poetry run pytest tests/monitoring -q
```

### Smoke Checks

- `curl http://localhost:8000/metrics` and check for new metric names
- Validate trace logging contains `span_id` and `correlation_id`
- Import Grafana dashboards and verify panels show data

## Operational Playbook

1. **High Error Rate**
   - Check `IngestionHighErrorRate` alert details
   - Identify adapters involved via `ingestion_attempts_total`
   - Correlate with trace spans to locate failing operations

2. **Latency Spikes**
   - Inspect `Processing Duration Percentiles` panel
   - Drill into `trace_span_duration_seconds` for specific operations
   - Evaluate payload size distributions and active requests for overload

3. **SLA Violations**
   - Review `SLA Violations` stat panel and associated alerts
   - Verify upstream data quality via validation metrics
   - Scale infrastructure or adjust thresholds if sustained

4. **Validation Failures**
   - Use Tracing & Validation dashboard for error categories
   - Cross-reference with adapter-specific logs and ingestion records
   - Notify data providers of recurring schema issues

## Additional References

- `grafana/README.md`: Detailed dashboard import/provisioning instructions
- `scry_ingestor/monitoring/metrics.py`: Metrics definitions and helpers
- `scry_ingestor/monitoring/tracing.py`: Correlation ID and tracing utilities
- `tests/monitoring/`: Automated monitoring test coverage

## Future Enhancements

- Integrate OpenTelemetry exporters for full distributed tracing pipelines
- Add service-level indicators (SLIs) for ingestion throughput and error budgets
- Expand dashboard templates with environment selectors and alert annotations

---

Monitor proactively and review metrics regularly to maintain SLA compliance and ensure data pipeline reliability.
