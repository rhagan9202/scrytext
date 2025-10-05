# Performance Characteristics

This document summarizes known performance traits, operational limits, and tuning options for Scry_Ingestor.

## Throughput Targets

| Scenario | Baseline Throughput | Notes |
| --- | --- | --- |
| PDF ingestion (layout mode off) | ~20 pages/sec per worker | CPU-bound; parallelize with multiple workers |
| PDF ingestion (layout mode on) | ~8 pages/sec per worker | Adds OCR-like processing; expect higher CPU usage |
| REST adapter (JSON payloads) | ~150 req/sec per worker | Bound by upstream API latency |
| CSV/Excel ingestion | ~40 MB/min per worker | Memory usage scales with file size; chunk large files |

> **Tip:** Benchmark with your data. The numbers above reflect default settings on 4 vCPU / 8 GB RAM containers.

## File Size Limits

| Adapter | Recommended Max Size | Hard Limit |
| --- | --- | --- |
| PDF | 100 MB | 250 MB (configurable via `max_bytes`) |
| Word | 50 MB | 150 MB |
| CSV/Excel | 200 MB | None (streaming supported) |
| REST | N/A | Request timeout governed by `timeout_seconds` |

## Concurrency

- FastAPI API workers: configure with Uvicorn/Gunicorn (e.g., `uvicorn --workers 4`)
- Celery workers: default concurrency matches CPU count; tune via `--concurrency` flag
- Avoid running CPU-intensive adapters (PDF layout + OCR) on the same worker as network-intensive adapters to reduce contention

## Latency Budget

| Stage | Typical Duration |
| --- | --- |
| Data collection | 50–1000 ms (source-dependent) |
| Validation | 20–150 ms |
| Transformation | 100–600 ms |
| Persistence + messaging | 10–50 ms |

Total pipeline latency usually stays under **2 seconds** for medium documents (<10 pages). Enable asynchronous ingestion for larger workloads.

## Resource Utilization

- **CPU:** PDF parsing and OCR features are CPU-heavy; allocate 2+ vCPUs per worker for consistent performance.
- **Memory:** Large documents can spike memory usage (200–400 MB). Use streaming options (`use_streaming`: true) where available.
- **Disk I/O:** Temporary files live in `/tmp`. Mount fast SSD storage or tune `TMPDIR` for high-volume processing.

## Scaling Guidelines

1. **Horizontal Scaling:** Add more API pods/containers and Celery workers. Use Kubernetes HPA or ECS Service Auto Scaling.
2. **Workload Segregation:** Deploy dedicated worker pools per adapter family (e.g., PDF vs. REST) to optimize resource allocation.
3. **Backpressure:** Monitor queue depth (RabbitMQ/Kafka). Use circuit breaker policies (`tasks/circuit_breaker.py`) to shed load when downstream systems fail.
4. **Caching:** Cache adapter configuration and heavy resources (e.g., ML models) per worker to avoid repeated initialization.

## Monitoring

- Prometheus metrics exposed at `/metrics`
  - `scry_ingestion_attempt_total` (labels: adapter, status)
  - `scry_ingestion_duration_seconds_bucket`
  - `scry_ingestion_errors_total`
- Emit logs with correlation IDs for distributed tracing.
- Configure alerts for error rate spikes (>5%), long-running jobs, and queue backlog.

## Optimization Tips

- Enable table extraction only when needed; it adds overhead.
- Tune retry policies (`config/adapters.yaml`, `RetryConfig`) to avoid long waits on flaky sources.
- For massive CSV/Excel files, enable chunking (`chunk_size`, `use_streaming` options) to reduce peak memory usage.
- Utilize cloud processing mode for adapters that support it to offload heavy computation (e.g., AWS Textract for PDFs).

## Known Limits

- Single worker throughput caps around 2–3 concurrent heavy ingestions due to CPU contention.
- Synchronous API responses can grow large; consider asynchronous ingestion with callbacks for giga-scale documents.
- Some adapters rely on third-party services (OCR, REST APIs); enforce rate limits and exponential backoff settings.

Monitor performance regularly and feed findings back into configuration defaults to keep the system efficient at scale.
