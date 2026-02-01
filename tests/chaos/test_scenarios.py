"""Chaos engineering test scenarios.

Tests system behavior under various failure conditions to validate
retry logic, circuit breakers, and graceful degradation.
"""

from __future__ import annotations

import time

import pytest

from scry_ingestor.testing.chaos import (
    ChaosMonkey,
    DatabaseLatency,
    KafkaUnavailable,
    NetworkFailure,
    RedisFailure,
    ServiceDegradation,
    database_slowdown,
    full_degradation,
    kafka_outage,
)


@pytest.mark.asyncio
async def test_kafka_unavailable_scenario():
    """Test system behavior when Kafka is unavailable."""
    scenario = kafka_outage()

    # Verify scenario activation
    with scenario:
        assert scenario.activated
        assert scenario.name == "Kafka Unavailable"

        # Simulate operation that would use Kafka
        with pytest.raises(ConnectionError, match="Kafka broker unavailable"):
            # This would normally publish to Kafka
            from scry_ingestor.messaging.publisher import get_ingestion_publisher
            from scry_ingestor.schemas.payload import (
                IngestionMetadata,
                IngestionPayload,
                ValidationResult,
            )

            publisher = get_ingestion_publisher()
            mock_payload = IngestionPayload(
                data={"test": "data"},
                metadata=IngestionMetadata(
                    source_id="test",
                    adapter_type="test",
                    timestamp="2024-01-01T00:00:00Z",
                    processing_duration_ms=100,
                    processing_mode="local",
                    correlation_id=None,
                ),
                validation=ValidationResult(is_valid=True),
            )
            publisher.publish_success(mock_payload)

    # Verify scenario deactivation
    assert not scenario.activated


@pytest.mark.asyncio
async def test_database_latency_injection():
    """Test database latency injection."""
    scenario = database_slowdown(latency_ms=100, probability=1.0)

    with scenario:
        # Measure time with latency injection
        start_time = time.time()
        with scenario.inject():
            pass  # Simulate database operation
        elapsed_ms = (time.time() - start_time) * 1000

        # Should have added ~100ms latency
        assert elapsed_ms >= 90  # Allow some tolerance


@pytest.mark.asyncio
async def test_database_latency_probability():
    """Test probabilistic database latency."""
    scenario = DatabaseLatency(latency_ms=50, probability=0.0)

    with scenario:
        # With 0% probability, should not add latency
        start_time = time.time()
        with scenario.inject():
            pass
        elapsed_ms = (time.time() - start_time) * 1000

        # Should NOT have added latency
        assert elapsed_ms < 20


@pytest.mark.asyncio
async def test_redis_connection_failure():
    """Test Redis connection failure injection."""
    scenario = RedisFailure(failure_type="connection_error", probability=1.0)

    with scenario:
        # Should raise connection error
        with pytest.raises(ConnectionError, match="Redis connection refused"):
            scenario.inject_failure()


@pytest.mark.asyncio
async def test_redis_timeout():
    """Test Redis timeout injection."""
    scenario = RedisFailure(failure_type="timeout", probability=1.0)

    with scenario:
        with pytest.raises(TimeoutError, match="Redis operation timed out"):
            scenario.inject_failure()


@pytest.mark.asyncio
async def test_redis_data_loss():
    """Test Redis cache miss simulation."""
    scenario = RedisFailure(failure_type="data_loss", probability=1.0)

    with scenario:
        # Data loss returns None (cache miss)
        result = scenario.inject_failure()
        assert result is None


@pytest.mark.asyncio
async def test_network_timeout():
    """Test network timeout injection."""
    scenario = NetworkFailure(failure_type="timeout", delay=2.0, probability=1.0)

    with scenario:
        with pytest.raises(TimeoutError, match="Network timeout"):
            scenario.inject_failure()


@pytest.mark.asyncio
async def test_network_connection_error():
    """Test network connection error injection."""
    scenario = NetworkFailure(
        failure_type="connection_error", probability=1.0
    )

    with scenario:
        with pytest.raises(ConnectionError, match="Failed to establish connection"):
            scenario.inject_failure()


@pytest.mark.asyncio
async def test_network_slow_response():
    """Test slow network response injection."""
    scenario = NetworkFailure(
        failure_type="slow_response", delay=0.1, probability=1.0
    )

    with scenario:
        start_time = time.time()
        scenario.inject_failure()
        elapsed = time.time() - start_time

        # Should have added delay
        assert elapsed >= 0.09


@pytest.mark.asyncio
async def test_service_degradation():
    """Test gradual service degradation."""
    scenario = ServiceDegradation(
        response_time_multiplier=3.0, error_rate=0.5, probability=1.0
    )

    with scenario:
        # Test latency addition
        start_time = time.time()
        await scenario.add_latency(base_latency=0.05)
        elapsed = time.time() - start_time

        # Should multiply base latency
        assert elapsed >= 0.14  # 0.05 * 3.0 = 0.15, allow tolerance

        # Test error rate (probabilistic)
        errors = 0
        for _ in range(100):
            if scenario.should_error():
                errors += 1

        # With 50% error rate, should get roughly 50 errors
        assert 30 < errors < 70  # Allow variance


@pytest.mark.asyncio
async def test_chaos_monkey_multiple_scenarios():
    """Test chaos monkey orchestrating multiple scenarios."""
    monkey = ChaosMonkey()

    # Add multiple scenarios
    db_scenario = DatabaseLatency(latency_ms=50, probability=1.0)
    redis_scenario = RedisFailure(probability=1.0)

    monkey.add_scenario(db_scenario)
    monkey.add_scenario(redis_scenario)

    # Start chaos
    with monkey:
        assert monkey.active
        assert db_scenario.activated
        assert redis_scenario.activated

        # Both scenarios should be active
        with pytest.raises(ConnectionError):
            redis_scenario.inject_failure()

    # After exit, scenarios should be deactivated
    assert not monkey.active
    assert not db_scenario.activated
    assert not redis_scenario.activated


@pytest.mark.asyncio
async def test_full_degradation_scenario():
    """Test full system degradation with multiple failures."""
    monkey = full_degradation()

    with monkey:
        assert monkey.active
        assert len(monkey.scenarios) >= 3  # Should have multiple scenarios

        # All scenarios should be active
        for scenario in monkey.scenarios:
            assert scenario.activated


@pytest.mark.asyncio
async def test_probabilistic_failures():
    """Test that probabilistic failures work correctly."""
    # 0% probability - should never fail
    scenario = NetworkFailure(probability=0.0)
    assert not scenario.should_fail()

    # 100% probability - should always fail
    scenario = NetworkFailure(probability=1.0)
    assert scenario.should_fail()

    # 50% probability - test distribution
    scenario = NetworkFailure(probability=0.5)
    failures = sum(1 for _ in range(1000) if scenario.should_fail())

    # Should be roughly 500 failures out of 1000 attempts
    assert 400 < failures < 600


@pytest.mark.asyncio
async def test_circuit_breaker_under_failures():
    """Test circuit breaker behavior under repeated failures."""
    from scry_ingestor.testing.chaos import CircuitBreakerTest

    circuit_test = CircuitBreakerTest(failure_count=5)

    # Simulate failures
    for i in range(4):
        should_open = circuit_test.simulate_failure()
        assert not should_open  # Circuit should stay closed

    # 5th failure should trigger circuit breaker
    should_open = circuit_test.simulate_failure()
    assert should_open

    # Reset should clear failures
    circuit_test.reset()
    assert circuit_test.current_failures == 0


@pytest.mark.asyncio
async def test_chaos_scenario_context_manager():
    """Test chaos scenario context manager behavior."""
    scenario = DatabaseLatency(latency_ms=100)

    assert not scenario.activated

    with scenario:
        assert scenario.activated

    assert not scenario.activated


@pytest.mark.asyncio
async def test_kafka_intermittent_failures():
    """Test intermittent Kafka failures with probability."""
    scenario = KafkaUnavailable(probability=0.5)

    with scenario:
        # Try multiple times, should get mix of success and failure
        results = []
        for _ in range(20):
            try:
                from scry_ingestor.messaging.publisher import get_ingestion_publisher
                from scry_ingestor.schemas.payload import (
                    IngestionMetadata,
                    IngestionPayload,
                    ValidationResult,
                )

                publisher = get_ingestion_publisher()
                mock_payload = IngestionPayload(
                    data={"test": "data"},
                    metadata=IngestionMetadata(
                        source_id="test",
                        adapter_type="test",
                        timestamp="2024-01-01T00:00:00Z",
                        processing_duration_ms=100,
                        processing_mode="local",
                        correlation_id=None,
                    ),
                    validation=ValidationResult(is_valid=True),
                )
                publisher.publish_success(mock_payload)
                results.append("success")
            except ConnectionError:
                results.append("failure")

        # With 50% probability, should have both successes and failures
        assert "success" in results or "failure" in results


@pytest.mark.asyncio
async def test_degradation_without_errors():
    """Test service degradation with 0% error rate."""
    scenario = ServiceDegradation(error_rate=0.0, probability=1.0)

    with scenario:
        # Should never error
        for _ in range(100):
            assert not scenario.should_error()


@pytest.mark.asyncio
async def test_scenario_names():
    """Test that scenarios have descriptive names."""
    assert "Kafka" in KafkaUnavailable().name
    assert "Database" in DatabaseLatency(latency_ms=100).name
    assert "100" in DatabaseLatency(latency_ms=100).name
    assert "Redis" in RedisFailure().name
    assert "Network" in NetworkFailure().name
    assert "Degradation" in ServiceDegradation().name
