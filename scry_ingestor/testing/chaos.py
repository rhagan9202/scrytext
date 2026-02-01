"""Chaos engineering utilities for testing failure scenarios.

This module provides tools for simulating various failure conditions:
- Network failures (timeouts, connection errors)
- Service degradation (slow responses, partial failures)
- Resource exhaustion (connection pool exhaustion, memory pressure)
"""

from __future__ import annotations

import asyncio
import random
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from ..utils.logging import setup_logger

logger = setup_logger(__name__)


class ChaosScenario:
    """Base class for chaos testing scenarios."""

    def __init__(self, name: str, probability: float = 1.0):
        """
        Initialize chaos scenario.

        Args:
            name: Scenario name for logging
            probability: Probability of failure (0.0-1.0), default 1.0 (always fail)
        """
        self.name = name
        self.probability = probability
        self.activated = False

    def should_fail(self) -> bool:
        """Determine if failure should occur based on probability."""
        return random.random() < self.probability

    def __enter__(self):
        """Enter chaos scenario context."""
        self.activated = True
        logger.info(f"Chaos scenario activated: {self.name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit chaos scenario context."""
        self.activated = False
        logger.info(f"Chaos scenario deactivated: {self.name}")
        return False


class NetworkFailure(ChaosScenario):
    """Simulate network-related failures."""

    def __init__(
        self,
        failure_type: str = "timeout",
        delay: float = 5.0,
        probability: float = 1.0,
    ):
        """
        Initialize network failure scenario.

        Args:
            failure_type: Type of failure ('timeout', 'connection_error', 'slow_response')
            delay: Delay in seconds for slow responses
            probability: Probability of failure occurring
        """
        super().__init__(f"Network Failure: {failure_type}", probability)
        self.failure_type = failure_type
        self.delay = delay

    def inject_failure(self) -> None:
        """Inject network failure."""
        if not self.should_fail():
            return

        if self.failure_type == "timeout":
            raise TimeoutError(f"Network timeout after {self.delay}s")
        elif self.failure_type == "connection_error":
            raise ConnectionError("Failed to establish connection")
        elif self.failure_type == "slow_response":
            import time

            time.sleep(self.delay)


class KafkaUnavailable(ChaosScenario):
    """Simulate Kafka/message queue unavailability."""

    def __init__(self, probability: float = 1.0):
        """
        Initialize Kafka unavailable scenario.

        Args:
            probability: Probability of failure
        """
        super().__init__("Kafka Unavailable", probability)
        self._original_send = None
        self._patch = None

    def __enter__(self):
        """Patch Kafka producer to simulate unavailability."""
        super().__enter__()

        # Clear LRU cache to ensure fresh mock
        from scry_ingestor.messaging.publisher import get_ingestion_publisher
        get_ingestion_publisher.cache_clear()

        def failing_send(*args, **kwargs):
            if self.should_fail():
                raise ConnectionError("Kafka broker unavailable")
            return MagicMock()

        # Patch the publisher's publish methods
        mock_publisher = MagicMock()
        mock_publisher.publish_success.side_effect = failing_send
        mock_publisher.publish_failure.side_effect = failing_send

        self._patch = patch(
            "scry_ingestor.messaging.publisher.get_ingestion_publisher",
            return_value=mock_publisher
        )
        self._patch.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop patching Kafka producer."""
        if self._patch:
            self._patch.__exit__(exc_type, exc_val, exc_tb)
            # Clear cache again after patching
            from scry_ingestor.messaging.publisher import get_ingestion_publisher
            get_ingestion_publisher.cache_clear()
        return super().__exit__(exc_type, exc_val, exc_tb)


class DatabaseLatency(ChaosScenario):
    """Simulate database latency and slow queries."""

    def __init__(self, latency_ms: int = 5000, probability: float = 1.0):
        """
        Initialize database latency scenario.

        Args:
            latency_ms: Latency to inject in milliseconds
            probability: Probability of latency injection
        """
        super().__init__(f"Database Latency: {latency_ms}ms", probability)
        self.latency_ms = latency_ms

    @contextmanager
    def inject(self):
        """Context manager to inject latency into database operations."""
        if self.should_fail():
            logger.warning(f"Injecting {self.latency_ms}ms database latency")
            import time

            time.sleep(self.latency_ms / 1000.0)
        yield


class RedisFailure(ChaosScenario):
    """Simulate Redis connection failures."""

    def __init__(self, failure_type: str = "connection_error", probability: float = 1.0):
        """
        Initialize Redis failure scenario.

        Args:
            failure_type: Type of failure ('connection_error', 'timeout', 'data_loss')
            probability: Probability of failure
        """
        super().__init__(f"Redis Failure: {failure_type}", probability)
        self.failure_type = failure_type

    def inject_failure(self):
        """Inject Redis failure."""
        if not self.should_fail():
            return None

        if self.failure_type == "connection_error":
            raise ConnectionError("Redis connection refused")
        elif self.failure_type == "timeout":
            raise TimeoutError("Redis operation timed out")
        elif self.failure_type == "data_loss":
            return None  # Simulate cache miss
        return None


class ServiceDegradation(ChaosScenario):
    """Simulate gradual service degradation."""

    def __init__(
        self,
        response_time_multiplier: float = 5.0,
        error_rate: float = 0.3,
        probability: float = 1.0,
    ):
        """
        Initialize service degradation scenario.

        Args:
            response_time_multiplier: Multiply normal response time by this factor
            error_rate: Probability of random errors (0.0-1.0)
            probability: Probability of degradation occurring
        """
        super().__init__("Service Degradation", probability)
        self.response_time_multiplier = response_time_multiplier
        self.error_rate = error_rate

    def should_error(self) -> bool:
        """Determine if an error should occur during degradation."""
        return self.activated and random.random() < self.error_rate

    async def add_latency(self, base_latency: float = 0.1):
        """Add degraded latency to operation."""
        if self.activated and self.should_fail():
            await asyncio.sleep(base_latency * self.response_time_multiplier)


class CircuitBreakerTest:
    """Test circuit breaker behavior under failures."""

    def __init__(self, failure_count: int = 5):
        """
        Initialize circuit breaker test.

        Args:
            failure_count: Number of consecutive failures to trigger circuit breaker
        """
        self.failure_count = failure_count
        self.current_failures = 0

    def simulate_failure(self) -> bool:
        """
        Simulate a failure and return True if circuit should open.

        Returns:
            True if circuit breaker should open
        """
        self.current_failures += 1
        return self.current_failures >= self.failure_count

    def reset(self):
        """Reset failure counter."""
        self.current_failures = 0


class ChaosMonkey:
    """Orchestrate multiple chaos scenarios."""

    def __init__(self):
        """Initialize chaos monkey."""
        self.scenarios: list[ChaosScenario] = []
        self.active = False

    def add_scenario(self, scenario: ChaosScenario):
        """Add a chaos scenario."""
        self.scenarios.append(scenario)
        logger.info(f"Added chaos scenario: {scenario.name}")

    def start(self):
        """Activate all scenarios."""
        self.active = True
        for scenario in self.scenarios:
            scenario.__enter__()
        logger.warning(f"Chaos monkey started with {len(self.scenarios)} scenarios")

    def stop(self):
        """Deactivate all scenarios."""
        for scenario in reversed(self.scenarios):
            scenario.__exit__(None, None, None)
        self.active = False
        logger.info("Chaos monkey stopped")

    def __enter__(self):
        """Enter chaos monkey context."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit chaos monkey context."""
        self.stop()
        return False


# Predefined scenario builders
def kafka_outage(duration_seconds: float = 60.0) -> KafkaUnavailable:
    """Create a Kafka outage scenario."""
    return KafkaUnavailable(probability=1.0)


def database_slowdown(latency_ms: int = 5000, probability: float = 0.5) -> DatabaseLatency:
    """Create a database slowdown scenario."""
    return DatabaseLatency(latency_ms=latency_ms, probability=probability)


def redis_intermittent_failures(probability: float = 0.3) -> RedisFailure:
    """Create intermittent Redis failures."""
    return RedisFailure(failure_type="connection_error", probability=probability)


def network_partition(probability: float = 0.1) -> NetworkFailure:
    """Create network partition simulation."""
    return NetworkFailure(failure_type="connection_error", probability=probability)


def full_degradation() -> ChaosMonkey:
    """Create a scenario with all services degraded."""
    monkey = ChaosMonkey()
    monkey.add_scenario(database_slowdown(latency_ms=3000, probability=0.7))
    monkey.add_scenario(redis_intermittent_failures(probability=0.5))
    monkey.add_scenario(ServiceDegradation(response_time_multiplier=3.0, error_rate=0.2))
    return monkey
