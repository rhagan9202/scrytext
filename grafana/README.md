# Grafana & Prometheus Monitoring Setup

This directory contains Grafana dashboards and Prometheus alerting rules for comprehensive monitoring of the Scry_Ingestor service.

## Directory Structure

```
grafana/
├── dashboards/
│   ├── scry-ingestor-overview.json      # Main operational dashboard
│   └── scry-ingestor-tracing.json       # Distributed tracing & validation
├── alerts/
│   └── scry_ingestor_alerts.yml         # Prometheus alerting rules
└── README.md                             # This file
```

## Dashboard Overview

### 1. Scry Ingestor - Overview (`scry-ingestor-overview.json`)

**Purpose**: Primary operational dashboard for monitoring ingestion health and performance.

**Panels**:
- **Ingestion Rate (Success/Error)**: Real-time success and error rates
- **Ingestion Rate by Adapter**: Breakdown of ingestion volume per adapter type
- **Processing Duration Percentiles**: P50, P95, P99 latency tracking
- **Error Rate by Type**: Distribution of error types over time
- **Active Requests**: Current concurrent ingestion operations
- **SLA Violations**: Hourly count of SLA threshold breaches

**Use Cases**:
- Monitor overall service health
- Identify performance degradation
- Track SLA compliance
- Detect adapter-specific issues

### 2. Scry Ingestor - Tracing & Validation (`scry-ingestor-tracing.json`)

**Purpose**: Deep-dive dashboard for distributed tracing metrics and data quality validation.

**Panels**:
- **Trace Span Creation Rate**: Volume of trace spans by operation
- **Trace Span Duration Percentiles**: Per-operation latency breakdown
- **Validation Errors by Adapter**: Data quality issues by source
- **Validation Warnings by Adapter**: Non-critical validation findings
- **Payload Size Distribution**: P50/P95/P99 payload sizes per adapter

**Use Cases**:
- Diagnose performance bottlenecks in specific operations
- Track data quality trends
- Identify large payloads impacting performance
- Correlate validation issues with adapters

## Installing Dashboards

### Method 1: Grafana UI Import

1. Navigate to Grafana → Dashboards → Import
2. Click "Upload JSON file"
3. Select `scry-ingestor-overview.json` or `scry-ingestor-tracing.json`
4. Select your Prometheus data source
5. Click "Import"

### Method 2: Provisioning (Recommended for Production)

Add to your Grafana provisioning configuration (`/etc/grafana/provisioning/dashboards/`):

```yaml
# scry-dashboards.yml
apiVersion: 1

providers:
  - name: 'Scry Ingestor'
    orgId: 1
    folder: 'Scry Ingestor'
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /path/to/scrytext/grafana/dashboards
```

### Method 3: Kubernetes ConfigMap (for containerized deployments)

```bash
kubectl create configmap scry-dashboards \
  --from-file=grafana/dashboards/ \
  --namespace=monitoring
```

Then reference in Grafana deployment:

```yaml
volumeMounts:
  - name: scry-dashboards
    mountPath: /etc/grafana/provisioning/dashboards/scry
volumes:
  - name: scry-dashboards
    configMap:
      name: scry-dashboards
```

## Prometheus Alerting Rules

### Installing Alerts

**Standalone Prometheus**:

1. Copy `alerts/scry_ingestor_alerts.yml` to your Prometheus configuration directory
2. Update `prometheus.yml`:

```yaml
rule_files:
  - "scry_ingestor_alerts.yml"
```

3. Reload Prometheus:

```bash
curl -X POST http://localhost:9090/-/reload
# or
kill -HUP $(pgrep prometheus)
```

**Kubernetes Prometheus Operator**:

Create a PrometheusRule resource:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: scry-ingestor-alerts
  namespace: monitoring
spec:
  groups:
    # Paste contents of scry_ingestor_alerts.yml here
```

### Alert Categories

#### Critical Alerts (Immediate Action Required)

- **IngestionHighErrorRate**: Error rate > 10% for 5 minutes
- **IngestionCompleteFailure**: Zero successful ingestions for 10 minutes
- **IngestionSLAViolationCritical**: >10 critical SLA violations in 15 minutes
- **IngestionProcessingP99High**: P99 latency > 30 seconds for 10 minutes
- **IngestionActiveRequestsSaturated**: >50 concurrent requests for 5 minutes

#### Warning Alerts (Monitor & Investigate)

- **IngestionElevatedErrorRate**: Error rate > 5% for 10 minutes
- **IngestionSLAViolationWarning**: >20 warning SLA violations in 30 minutes
- **IngestionProcessingP95High**: P95 latency > 10 seconds for 15 minutes
- **IngestionAdapterSpecificErrors**: Adapter-specific error rate > 0.5/sec
- **IngestionValidationErrorsElevated**: Validation error rate > 1.0/sec
- **IngestionLargePayloads**: P95 payload size > 50MB

#### Informational Alerts (Awareness)

- **IngestionTraceSpanDurationAnomalous**: Span duration 2x historical baseline
- **IngestionNoActivity**: No ingestion attempts for 30 minutes

## Alerting Integration

### Alertmanager Configuration

Example Alertmanager config for routing Scry_Ingestor alerts:

```yaml
route:
  group_by: ['alertname', 'service']
  group_wait: 10s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'default'
  routes:
    - match:
        service: scry-ingestor
        severity: critical
      receiver: 'pagerduty-critical'
      continue: true
    - match:
        service: scry-ingestor
        severity: warning
      receiver: 'slack-warnings'

receivers:
  - name: 'pagerduty-critical'
    pagerduty_configs:
      - service_key: '<your-pagerduty-key>'
  - name: 'slack-warnings'
    slack_configs:
      - api_url: '<your-slack-webhook>'
        channel: '#scry-alerts'
        title: 'Scry Ingestor Alert'
  - name: 'default'
    slack_configs:
      - api_url: '<your-slack-webhook>'
        channel: '#general-monitoring'
```

## SLA Thresholds

Default SLA thresholds used in metrics and alerts:

| Metric | Warning Threshold | Critical Threshold |
|--------|-------------------|-------------------|
| Processing Duration (P95) | 10 seconds | 30 seconds |
| Error Rate | 5% | 10% |
| Active Requests | 25 concurrent | 50 concurrent |
| Payload Size (P95) | 50MB | 100MB |

**Customizing SLA Thresholds**:

To adjust thresholds, modify the corresponding PromQL expressions in:
- Alert rules: `grafana/alerts/scry_ingestor_alerts.yml`
- Dashboard thresholds: Panel JSON configurations

## Metrics Reference

### Core Ingestion Metrics

```promql
# Ingestion attempts by adapter and status
ingestion_attempts_total{adapter="<adapter>", status="<success|error>"}

# Ingestion errors by error type
ingestion_errors_total{error_type="<type>"}

# Processing duration histogram
processing_duration_seconds_bucket{le="<bucket>"}
processing_duration_seconds_count
processing_duration_seconds_sum

# SLA violations
ingestion_sla_violations_total{adapter="<adapter>", severity="<warning|critical>"}

# Active concurrent requests
ingestion_active_requests{adapter="<adapter>"}

# Payload size histogram
ingestion_payload_size_bytes_bucket{adapter="<adapter>", le="<bucket>"}
```

### Distributed Tracing Metrics

```promql
# Trace span creation
trace_spans_created_total{operation="<operation>"}

# Trace span duration histogram
trace_span_duration_seconds_bucket{operation="<operation>", le="<bucket>"}
```

### Validation Metrics

```promql
# Validation errors
validation_errors_total{adapter="<adapter>", error_category="<category>"}

# Validation warnings
validation_warnings_total{adapter="<adapter>", warning_category="<category>"}
```

## Useful PromQL Queries

### Error Rate Calculation

```promql
# Overall error rate (last 5 minutes)
sum(rate(ingestion_attempts_total{status="error"}[5m])) 
/ 
sum(rate(ingestion_attempts_total[5m]))

# Per-adapter error rate
sum by(adapter) (rate(ingestion_attempts_total{status="error"}[5m])) 
/ 
sum by(adapter) (rate(ingestion_attempts_total[5m]))
```

### Latency Percentiles

```promql
# P50 processing duration
histogram_quantile(0.50, sum(rate(processing_duration_seconds_bucket[5m])) by (le))

# P95 by adapter
histogram_quantile(0.95, sum by(adapter, le) (rate(processing_duration_seconds_bucket[5m])))

# P99 global
histogram_quantile(0.99, sum(rate(processing_duration_seconds_bucket[5m])) by (le))
```

### Throughput

```promql
# Successful ingestions per second
sum(rate(ingestion_attempts_total{status="success"}[5m]))

# Total throughput by adapter
sum by(adapter) (rate(ingestion_attempts_total[5m]))
```

### SLA Compliance

```promql
# SLA compliance rate (last hour)
1 - (
  sum(increase(ingestion_sla_violations_total[1h])) 
  / 
  sum(increase(ingestion_attempts_total[1h]))
)
```

## Troubleshooting

### Dashboard Not Loading

1. Verify Prometheus data source is configured in Grafana
2. Check Prometheus is scraping Scry_Ingestor metrics endpoint (`/metrics`)
3. Confirm time range is set appropriately (default: last 1 hour)

### No Data in Panels

```bash
# Test metrics endpoint
curl http://localhost:8000/metrics | grep ingestion_attempts_total

# Verify Prometheus is scraping
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="scry-ingestor")'

# Check for scrape errors
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.health!="up")'
```

### Alerts Not Firing

1. Verify alert rules are loaded:
   ```bash
   curl http://localhost:9090/api/v1/rules | jq '.data.groups[] | select(.name | contains("scry_ingestor"))'
   ```

2. Check alert evaluation:
   ```bash
   curl http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | select(.labels.service=="scry-ingestor")'
   ```

3. Confirm Alertmanager is receiving alerts:
   ```bash
   curl http://localhost:9093/api/v2/alerts
   ```

## Best Practices

1. **Dashboard Organization**: Use folders in Grafana to organize Scry_Ingestor dashboards
2. **Template Variables**: Add dashboard variables for filtering by adapter, environment, or instance
3. **Alert Tuning**: Adjust thresholds based on historical baseline and capacity planning
4. **Correlation IDs**: Use distributed tracing dashboard to correlate spans across services
5. **Regular Review**: Schedule weekly reviews of SLA violations and validation trends

## Support

For questions or issues with monitoring setup:
- Review `MONITORING_GUIDE.md` in project documentation
- Check project issue tracker for known monitoring limitations
- Consult Prometheus/Grafana official documentation for platform-specific issues
