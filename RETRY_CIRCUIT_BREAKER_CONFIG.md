# Retry and Circuit Breaker Configuration Guide

## Overview
This document codifies the retry policies and circuit breaker settings used throughout Scry_Ingestor. These configurations ensure resilient handling of transient failures while preventing cascading failures in distributed systems.

## Retry Policies

### Default Retry Configuration
The system uses exponential backoff with configurable parameters:

```python
# scry_ingestor/tasks/policies.py
DEFAULT_RETRY_POLICY = {
    "max_retries": 3,
    "interval_start": 0,      # Initial retry delay (seconds)
    "interval_step": 2,        # Exponential backoff multiplier
    "interval_max": 10,        # Maximum retry delay (seconds)
    "retry_on": [
        # Transient errors that should trigger retries
        ConnectionError,
        TimeoutError,
        OSError,
    ],
}
```

### Retry Timing Examples
With default settings:
- **Attempt 1**: Immediate (0s delay)
- **Attempt 2**: 0 + (2^1) = 2s delay
- **Attempt 3**: 2 + (2^2) = 6s delay
- **Attempt 4**: min(6 + (2^3), 10) = 10s delay (capped)

Total time before final failure: ~18 seconds

### Adapter-Specific Retry Policies

#### Database Operations
```python
DATABASE_RETRY_POLICY = {
    "max_retries": 5,
    "interval_start": 0.5,
    "interval_step": 2,
    "interval_max": 30,
    "retry_on": [
        # Database-specific errors
        OperationalError,        # Connection pool exhausted
        InterfaceError,          # Connection lost
        TimeoutError,            # Query timeout
    ],
}
```

**Use cases**: 
- Long-running queries that might timeout
- Connection pool contention during high load
- Temporary database unavailability during failover

**Total retry window**: ~63 seconds (0.5s + 1s + 2s + 4s + 8s + 16s + 30s)

#### Kafka/Message Queue Operations
```python
KAFKA_RETRY_POLICY = {
    "max_retries": 10,         # Higher retries for message publishing
    "interval_start": 1,
    "interval_step": 1.5,      # Gentler exponential backoff
    "interval_max": 60,
    "retry_on": [
        KafkaException,
        ConnectionError,
        TimeoutError,
    ],
}
```

**Use cases**:
- Kafka broker temporarily unavailable
- Network partition between service and Kafka cluster
- Schema registry unavailability

**Total retry window**: ~5 minutes (allows for broker failover)

#### External API Calls (REST Adapter)
```python
API_RETRY_POLICY = {
    "max_retries": 3,
    "interval_start": 1,
    "interval_step": 3,        # Aggressive backoff to respect rate limits
    "interval_max": 60,
    "retry_on": [
        HTTPError,              # 5xx errors only
        ConnectionError,
        Timeout,
    ],
    "retry_status_codes": [500, 502, 503, 504, 429],  # Retry these HTTP codes
}
```

**Use cases**:
- Third-party API rate limiting (429)
- Temporary service unavailability (503)
- Gateway timeouts (504)

**Backoff behavior**: 1s → 4s → 13s → 40s (respects upstream rate limits)

#### File I/O Operations
```python
FILE_IO_RETRY_POLICY = {
    "max_retries": 3,
    "interval_start": 0.1,     # Quick retries for filesystem ops
    "interval_step": 2,
    "interval_max": 5,
    "retry_on": [
        OSError,
        IOError,
        PermissionError,
    ],
}
```

**Use cases**:
- Temporary file locks
- NFS/network filesystem latency
- Race conditions in file access

## Circuit Breaker Configuration

### Default Circuit Breaker Settings
```python
# scry_ingestor/tasks/circuit_breaker.py
DEFAULT_CIRCUIT_BREAKER_CONFIG = {
    "failure_threshold": 5,            # Open after N consecutive failures
    "success_threshold": 2,            # Close after N consecutive successes in half-open
    "timeout": 60,                     # Seconds to wait before trying half-open
    "expected_exception": Exception,   # Exceptions that count as failures
}
```

### Circuit Breaker State Machine
```
CLOSED (Normal) → OPEN (Failing) → HALF_OPEN (Testing) → CLOSED (Recovered)
       ↑                                      ↓
       └──────────────────────────────────────┘
```

#### State Transitions

**CLOSED → OPEN**:
- Trigger: `failure_threshold` consecutive failures
- Action: Immediately reject requests with `CircuitBreakerOpenError`
- Duration: Continue until `timeout` expires

**OPEN → HALF_OPEN**:
- Trigger: `timeout` seconds elapsed
- Action: Allow limited request probes
- Behavior: Test with single request

**HALF_OPEN → CLOSED**:
- Trigger: `success_threshold` consecutive successes
- Action: Resume normal operation
- Metrics: Reset failure counter

**HALF_OPEN → OPEN**:
- Trigger: Any failure during testing
- Action: Return to OPEN state
- Duration: Reset `timeout` timer

### Service-Specific Circuit Breakers

#### Kafka Publisher Circuit Breaker
```python
KAFKA_CIRCUIT_BREAKER = {
    "failure_threshold": 10,      # Allow more failures (async, non-critical)
    "success_threshold": 3,       # Require more successes to close
    "timeout": 120,               # 2-minute recovery window
    "expected_exception": (KafkaException, ConnectionError),
}
```

**Rationale**: Message publishing is asynchronous and non-blocking. Higher thresholds prevent premature circuit opening during transient Kafka issues.

#### Database Circuit Breaker
```python
DATABASE_CIRCUIT_BREAKER = {
    "failure_threshold": 3,       # Aggressive threshold (critical path)
    "success_threshold": 2,
    "timeout": 30,                # Quick recovery attempt
    "expected_exception": (OperationalError, InterfaceError),
}
```

**Rationale**: Database is on critical path. Fast circuit opening prevents request pileup and allows quick failover detection.

#### External API Circuit Breaker
```python
API_CIRCUIT_BREAKER = {
    "failure_threshold": 5,
    "success_threshold": 2,
    "timeout": 300,               # 5-minute backoff (respect upstream)
    "expected_exception": (HTTPError, ConnectionError, Timeout),
    "half_open_max_calls": 1,     # Single probe request in half-open
}
```

**Rationale**: External APIs may have longer recovery times. Extended timeout prevents overwhelming upstream services.

#### Redis Cache Circuit Breaker
```python
REDIS_CIRCUIT_BREAKER = {
    "failure_threshold": 8,       # Cache is non-critical, allow degradation
    "success_threshold": 3,
    "timeout": 60,
    "expected_exception": (RedisError, ConnectionError),
    "fallback_behavior": "skip",  # Bypass cache, hit source directly
}
```

**Rationale**: Caching is performance optimization, not critical path. Circuit opening degrades to direct source access.

## Configuration Tuning Guidelines

### When to Increase `max_retries`
- Operations with high transient failure rates (e.g., network calls)
- Non-critical async operations (e.g., metrics publishing)
- Services with known recovery patterns (e.g., Kafka broker failover ~30-60s)

### When to Decrease `max_retries`
- Synchronous critical-path operations
- User-facing endpoints (avoid long wait times)
- Operations with low success probability after first failure

### When to Increase `failure_threshold`
- Services with acceptable intermittent failures
- Non-critical operations (logging, metrics, caching)
- Services with transient blips (< 1% failure rate)

### When to Decrease `failure_threshold`
- Critical infrastructure dependencies
- Expensive operations (resource-intensive queries)
- Services with cascading failure risk

### When to Increase `timeout` (Circuit Breaker)
- External services with slow recovery (maintenance windows)
- Services with long failover processes (database replicas)
- Rate-limited APIs (respect their recovery period)

### When to Decrease `timeout`
- Fast-failing services (quick health detection)
- High-volume endpoints (minimize error accumulation)
- Services with health check endpoints (probe instead of timeout)

## Monitoring and Observability

### Metrics to Track
```python
# Retry metrics
retry_attempts_total{adapter="pdf", status="success|failure"}
retry_backoff_duration_seconds{adapter="pdf"}
retry_exhausted_total{adapter="pdf"}

# Circuit breaker metrics
circuit_breaker_state{service="kafka", state="open|closed|half_open"}
circuit_breaker_transitions_total{service="kafka", from_state="", to_state=""}
circuit_breaker_rejected_requests_total{service="kafka"}
```

### Alerting Thresholds
```yaml
# Alert if circuit breaker stays open > 5 minutes
- alert: CircuitBreakerStuckOpen
  expr: circuit_breaker_state{state="open"} == 1
  for: 5m

# Alert if retry exhaustion rate > 5%
- alert: HighRetryExhaustion
  expr: rate(retry_exhausted_total[5m]) / rate(retry_attempts_total[5m]) > 0.05
  for: 2m

# Alert if circuit opens repeatedly (flapping)
- alert: CircuitBreakerFlapping
  expr: rate(circuit_breaker_transitions_total[10m]) > 6  # 3 full cycles
  for: 5m
```

## Environment-Specific Configurations

### Development Environment
```yaml
# Faster feedback, fewer retries
retry:
  max_retries: 2
  interval_max: 5

circuit_breaker:
  failure_threshold: 3
  timeout: 10
```

### Staging Environment
```yaml
# Production-like, with faster recovery for testing
retry:
  max_retries: 3
  interval_max: 20

circuit_breaker:
  failure_threshold: 5
  timeout: 30
```

### Production Environment
```yaml
# Resilient, balanced for real traffic
retry:
  max_retries: 5
  interval_max: 60

circuit_breaker:
  failure_threshold: 10
  timeout: 120
```

## Testing Recommendations

### Unit Tests
- Test retry exhaustion scenarios
- Verify exponential backoff timing
- Test circuit breaker state transitions
- Mock dependencies to simulate failures

### Chaos Engineering
```python
# Use chaos testing framework
from scry_ingestor.testing.chaos import (
    kafka_outage,
    database_slowdown,
    network_partition,
)

# Test retry behavior under Kafka outage
with kafka_outage(probability=0.5):
    # 50% of calls fail, verify retries succeed
    publisher.publish_success(payload)

# Test circuit breaker with database latency
with database_slowdown(latency_ms=5000):
    # Verify circuit opens after threshold
    for _ in range(10):
        repository.save(record)
```

### Load Tests
- Verify retry backoff doesn't cause thundering herd
- Ensure circuit breaker prevents resource exhaustion
- Test recovery under sustained load after failures

## References
- Circuit Breaker Pattern: [Martin Fowler](https://martinfowler.com/bliki/CircuitBreaker.html)
- Exponential Backoff: [AWS Architecture Blog](https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/)
- Celery Retry Documentation: [Celery Docs](https://docs.celeryproject.org/en/stable/userguide/tasks.html#retrying)

## Version History
- **v1.0** (2024-01): Initial configuration codification
- Settings reflect production lessons learned from operational hardening phase
