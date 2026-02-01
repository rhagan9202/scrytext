"""Tests for retry utilities edge cases."""

import logging
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from scry_ingestor.utils.retry import (
    RetryableStatusError,
    RetryConfig,
    _parse_retry_after,
    execute_with_retry,
)


class TestRetryConfig:
    """Test suite for RetryConfig model."""

    def test_retry_config_defaults(self):
        """Test RetryConfig with default values."""
        config = RetryConfig()

        assert config.max_attempts >= 1
        assert config.backoff_factor > 0
        assert config.max_backoff is None or config.max_backoff > 0
        assert config.jitter >= 0
        assert config.enabled is False

    def test_retry_config_custom_values(self):
        """Test RetryConfig with custom values."""
        config = RetryConfig(
            enabled=True,
            max_attempts=5,
            backoff_factor=1.5,
            max_backoff=30.0,
            jitter=0.5,
        )

        assert config.enabled is True
        assert config.max_attempts == 5
        assert config.backoff_factor == 1.5
        assert config.max_backoff == 30.0
        assert config.jitter == 0.5

    def test_retry_config_validation_invalid_max_attempts(self):
        """Test RetryConfig validation for invalid max_attempts."""
        with pytest.raises(ValueError):
            RetryConfig(max_attempts=0)

    def test_retry_config_validation_invalid_delays(self):
        """Test RetryConfig validation for invalid delay values."""
        with pytest.raises(ValueError):
            RetryConfig(backoff_factor=0)

        with pytest.raises(ValueError):
            RetryConfig(max_backoff=-1)

    def test_retry_config_validation_invalid_jitter(self):
        """Test RetryConfig validation for invalid jitter."""
        with pytest.raises(ValueError):
            RetryConfig(jitter=-0.5)


class TestRetryableStatusError:
    """Test suite for RetryableStatusError."""

    def test_retryable_status_error_creation(self):
        """Test creating RetryableStatusError with mock response."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 503

        error = RetryableStatusError(mock_response)

        assert "Retryable HTTP status 503" in str(error)
        assert error.response == mock_response


class TestParseRetryAfter:
    """Test suite for _parse_retry_after function."""

    def test_parse_retry_after_none(self):
        """Test parsing None retry-after header."""
        result = _parse_retry_after(None)
        assert result is None

    def test_parse_retry_after_seconds(self):
        """Test parsing retry-after header with seconds."""
        result = _parse_retry_after("120")
        assert result == 120.0

    def test_parse_retry_after_invalid_format(self, caplog):
        """Test parsing invalid retry-after header format."""
        with caplog.at_level(logging.WARNING):
            result = _parse_retry_after("invalid-format")

        assert result is None
        assert "Failed to parse Retry-After header" in caplog.text


class TestExecuteWithRetry:
    """Test suite for execute_with_retry function."""

    @pytest.mark.asyncio
    async def test_execute_with_retry_success_first_attempt(self):
        """Test successful execution on first attempt."""
        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None

        mock_func = AsyncMock(return_value=mock_response)
        config = RetryConfig(enabled=True, max_attempts=3)

        result = await execute_with_retry(
            mock_func, method="GET", retry_config=config
        )

        assert result == mock_response
        assert mock_func.call_count == 1

    @pytest.mark.asyncio
    async def test_execute_with_retry_with_retryable_status(self):
        """Test retry behavior with retryable HTTP status codes."""
        success_response = Mock(spec=httpx.Response)
        success_response.status_code = 200
        success_response.raise_for_status.return_value = None

        # First call returns 503, second succeeds
        mock_func = AsyncMock(
            side_effect=[
                httpx.HTTPStatusError("503 Error", request=Mock(), response=Mock(status_code=503)),
                success_response,
            ]
        )

        config = RetryConfig(enabled=True, max_attempts=2, backoff_factor=0.01)

        result = await execute_with_retry(
            mock_func, method="GET", retry_config=config
        )

        assert result == success_response
        assert mock_func.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_with_retry_exhausts_attempts(self):
        """Test behavior when all retry attempts are exhausted."""
        mock_func = AsyncMock(side_effect=httpx.ConnectError("Connection failed"))
        config = RetryConfig(enabled=True, max_attempts=2, backoff_factor=0.01)

        with pytest.raises(httpx.ConnectError, match="Connection failed"):
            await execute_with_retry(mock_func, method="GET", retry_config=config)

        assert mock_func.call_count == 2


class TestEdgeCases:
    """Test edge cases for retry utilities."""

    def test_retry_config_edge_values(self):
        """Test RetryConfig with edge case values."""
        # Test minimum valid values
        config = RetryConfig(
            max_attempts=1,
            backoff_factor=0.001,
            max_backoff=0.001,
            jitter=0.0,
        )

        assert config.max_attempts == 1
        assert config.backoff_factor == 0.001
        assert config.max_backoff == 0.001
        assert config.jitter == 0.0

    def test_parse_retry_after_edge_cases(self):
        """Test _parse_retry_after with edge cases."""
        # Empty string
        assert _parse_retry_after("") is None

        # Zero seconds
        assert _parse_retry_after("0") == 0.0

        # Large number
        assert _parse_retry_after("999999") == 999999.0
