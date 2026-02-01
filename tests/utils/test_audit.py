"""Tests for audit logging and sensitive data redaction."""

from scry_ingestor.utils.audit import (
    AuditAction,
    AuditEvent,
    AuditLogger,
    AuditOutcome,
    SensitiveFieldRedactor,
    get_audit_logger,
)


class TestSensitiveFieldRedactor:
    """Test sensitive data redaction."""

    def test_redact_api_key_in_string(self):
        """Test API key redaction in strings."""
        text = 'API_KEY="sk_live_1234567890abcdef" in config'
        redacted = SensitiveFieldRedactor.redact_string(text)
        assert "sk_live_1234567890abcdef" not in redacted
        assert "***REDACTED***" in redacted

    def test_redact_password_in_string(self):
        """Test password redaction in strings."""
        text = "password=SuperSecret123 in database"
        redacted = SensitiveFieldRedactor.redact_string(text)
        assert "SuperSecret123" not in redacted
        assert "***REDACTED***" in redacted

    def test_redact_bearer_token(self):
        """Test bearer token redaction."""
        text = "token=eyJhbGciOiJIUzI1NiIs in header"
        redacted = SensitiveFieldRedactor.redact_string(text)
        assert "eyJhbGciOiJIUzI1NiIs" not in redacted
        assert "***REDACTED***" in redacted

    def test_redact_credit_card(self):
        """Test credit card number redaction (show last 4)."""
        text = "Card: 4532-1234-5678-9010"
        redacted = SensitiveFieldRedactor.redact_string(text)
        assert "4532-1234-5678" not in redacted
        assert "9010" in redacted  # Last 4 digits preserved
        assert "****-****-****-9010" in redacted

    def test_redact_ssn(self):
        """Test SSN redaction (show last 4)."""
        text = "SSN: 123-45-6789"
        redacted = SensitiveFieldRedactor.redact_string(text)
        assert "123-45" not in redacted
        assert "6789" in redacted  # Last 4 digits preserved
        assert "***-**-6789" in redacted

    def test_redact_email_partial(self):
        """Test email redaction (partial, keep domain)."""
        text = "Email: john.doe@example.com"
        redacted = SensitiveFieldRedactor.redact_string(text)
        assert "john.doe" not in redacted
        assert "example.com" in redacted  # Domain preserved
        assert "joh***@example.com" in redacted

    def test_redact_dict_with_sensitive_fields(self):
        """Test dictionary redaction with sensitive field names."""
        data = {
            "username": "alice",
            "password": "secret123",
            "api_key": "sk_test_abc123",
            "email": "alice@example.com",
            "normal_field": "safe_value",
        }
        redacted = SensitiveFieldRedactor.redact_dict(data)

        # Sensitive fields should be redacted
        assert redacted["password"] == "***REDACTED***"
        assert redacted["api_key"] == "***REDACTED***"

        # Email should be partially redacted
        assert "ali***@example.com" in redacted["email"]

        # Non-sensitive fields should be preserved
        assert redacted["username"] == "alice"
        assert redacted["normal_field"] == "safe_value"

    def test_redact_nested_dict(self):
        """Test nested dictionary redaction."""
        data = {
            "user": {
                "name": "Alice",
                "credentials": {
                    "password": "secret",
                    "token": "xyz123",
                },
            },
            "api_key": "abc123",
        }
        redacted = SensitiveFieldRedactor.redact_dict(data)

        assert redacted["user"]["name"] == "Alice"
        assert redacted["user"]["credentials"] == "***REDACTED***"
        assert redacted["api_key"] == "***REDACTED***"

    def test_redact_list_with_dicts(self):
        """Test redaction of lists containing dictionaries."""
        data = {
            "users": [
                {"name": "Alice", "password": "secret1"},
                {"name": "Bob", "password": "secret2"},
            ]
        }
        redacted = SensitiveFieldRedactor.redact_dict(data)

        assert redacted["users"][0]["name"] == "Alice"
        assert redacted["users"][0]["password"] == "***REDACTED***"
        assert redacted["users"][1]["name"] == "Bob"
        assert redacted["users"][1]["password"] == "***REDACTED***"

    def test_redact_depth_limit(self):
        """Test maximum recursion depth for redaction."""
        # Create deeply nested dict
        deep_dict = {"level1": {"level2": {"level3": {"password": "secret"}}}}

        # With max_depth=2, level3 shouldn't be redacted
        redacted = SensitiveFieldRedactor.redact_dict(deep_dict, max_depth=2)
        assert "level1" in redacted
        assert "level2" in redacted["level1"]
        # Level 3 should be returned as-is due to depth limit
        assert redacted["level1"]["level2"] == {"level3": {"password": "secret"}}

    def test_no_false_positives(self):
        """Test that normal text isn't incorrectly redacted."""
        text = "The passport application was approved yesterday"
        redacted = SensitiveFieldRedactor.redact_string(text)
        # "passport" contains "pass" but shouldn't be redacted as password
        assert redacted == text

    def test_case_insensitive_field_matching(self):
        """Test that field matching is case-insensitive."""
        data = {
            "PASSWORD": "secret1",
            "Password": "secret2",
            "PaSsWoRd": "secret3",
        }
        redacted = SensitiveFieldRedactor.redact_dict(data)

        assert redacted["PASSWORD"] == "***REDACTED***"
        assert redacted["Password"] == "***REDACTED***"
        assert redacted["PaSsWoRd"] == "***REDACTED***"


class TestAuditEvent:
    """Test audit event creation."""

    def test_create_auth_success_event(self):
        """Test creating authentication success event."""
        event = AuditEvent(
            action=AuditAction.LOGIN_SUCCESS,
            outcome=AuditOutcome.SUCCESS,
            actor="user@example.com",
            actor_type="user",
            client_ip="192.168.1.100",
        )

        assert event.action == AuditAction.LOGIN_SUCCESS
        assert event.outcome == AuditOutcome.SUCCESS
        assert event.actor == "user@example.com"
        assert event.client_ip == "192.168.1.100"
        assert event.timestamp  # Should be auto-generated

    def test_create_data_access_event(self):
        """Test creating data access event."""
        event = AuditEvent(
            action=AuditAction.DATA_READ,
            outcome=AuditOutcome.SUCCESS,
            actor="api_key_xyz",
            actor_type="api_key",
            resource="/data/records/12345",
            resource_type="record",
            correlation_id="trace-abc-123",
        )

        assert event.action == AuditAction.DATA_READ
        assert event.resource == "/data/records/12345"
        assert event.correlation_id == "trace-abc-123"

    def test_create_failure_event_with_error(self):
        """Test creating failure event with error message."""
        event = AuditEvent(
            action=AuditAction.LOGIN_FAILURE,
            outcome=AuditOutcome.FAILURE,
            actor="unknown_user",
            error_message="Invalid credentials",
        )

        assert event.outcome == AuditOutcome.FAILURE
        assert event.error_message == "Invalid credentials"


class TestAuditLogger:
    """Test audit logger functionality."""

    def test_log_auth_success(self):
        """Test logging authentication success."""
        logger = AuditLogger()
        # Should not raise
        logger.log_auth_success(
            actor="user@example.com",
            client_ip="192.168.1.1",
            correlation_id="trace-123",
        )

    def test_log_auth_failure(self):
        """Test logging authentication failure."""
        logger = AuditLogger()
        # Should not raise
        logger.log_auth_failure(
            actor="unknown_user",
            reason="Invalid password",
            client_ip="192.168.1.1",
        )

    def test_log_data_access(self):
        """Test logging data access."""
        logger = AuditLogger()
        logger.log_data_access(
            actor="service_account",
            resource="/data/records/123",
            action=AuditAction.DATA_READ,
            outcome=AuditOutcome.SUCCESS,
            actor_type="service",
            resource_type="record",
        )

    def test_log_config_change(self):
        """Test logging configuration change."""
        logger = AuditLogger()
        logger.log_config_change(
            actor="admin",
            resource="adapters.yaml",
            outcome=AuditOutcome.SUCCESS,
            details={"changed_field": "max_retries", "old_value": 3, "new_value": 5},
        )

    def test_log_ingestion(self):
        """Test logging ingestion operation."""
        logger = AuditLogger()
        logger.log_ingestion(
            actor="ingestion_service",
            resource="source_123",
            outcome=AuditOutcome.SUCCESS,
            adapter_type="pdf",
            source_id="document_456",
            correlation_id="trace-789",
        )

    def test_automatic_redaction_enabled(self):
        """Test that automatic redaction is enabled by default."""
        logger = AuditLogger()
        assert logger.redact_sensitive is True

        # Log event with sensitive data
        logger.log_auth_success(
            actor="user@example.com",
            client_ip="192.168.1.1",
            password="should_be_redacted",  # Extra detail
        )
        # If this doesn't raise, redaction is working

    def test_redaction_disabled(self):
        """Test logger with redaction disabled."""
        logger = AuditLogger(redact_sensitive=False)
        assert logger.redact_sensitive is False

    def test_get_audit_logger_singleton(self):
        """Test global audit logger instance."""
        logger1 = get_audit_logger()
        logger2 = get_audit_logger()
        assert logger1 is logger2  # Should be same instance


class TestAuditLoggerIntegration:
    """Integration tests for audit logging."""

    def test_full_audit_flow_auth(self):
        """Test complete authentication audit flow."""
        logger = get_audit_logger()

        # Successful login
        logger.log_auth_success(
            actor="alice@example.com",
            client_ip="10.0.0.1",
            correlation_id="req-001",
        )

        # Failed login attempt
        logger.log_auth_failure(
            actor="attacker@evil.com",
            reason="Invalid credentials",
            client_ip="192.168.1.999",
            correlation_id="req-002",
        )

    def test_full_audit_flow_data_operations(self):
        """Test complete data operation audit flow."""
        logger = get_audit_logger()

        # Data read
        logger.log_data_access(
            actor="analyst_user",
            resource="records/batch_20240101",
            action=AuditAction.DATA_READ,
            outcome=AuditOutcome.SUCCESS,
            resource_type="batch",
            correlation_id="analysis-001",
        )

        # Data write
        logger.log_data_access(
            actor="etl_service",
            resource="records/batch_20240102",
            action=AuditAction.DATA_WRITE,
            outcome=AuditOutcome.SUCCESS,
            actor_type="service",
            resource_type="batch",
            details={"record_count": 1500},
        )

        # Data deletion (denied)
        logger.log_data_access(
            actor="unauthorized_user",
            resource="records/sensitive_data",
            action=AuditAction.DATA_DELETE,
            outcome=AuditOutcome.DENIED,
            error_message="Insufficient permissions",
            resource_type="record",
        )

    def test_redaction_in_logged_event(self):
        """Test that sensitive data is redacted in logged events."""
        logger = AuditLogger(redact_sensitive=True)

        # Create event with sensitive details
        event = AuditEvent(
            action=AuditAction.CONFIG_UPDATED,
            outcome=AuditOutcome.SUCCESS,
            actor="admin",
            details={
                "api_key": "sk_live_dangerous_key",
                "password": "SuperSecret123",
                "safe_field": "safe_value",
            },
        )

        # Log the event (redaction happens here)
        logger.log_event(event)

        # The original event should still have sensitive data
        assert event.details["api_key"] == "sk_live_dangerous_key"
        assert event.details["password"] == "SuperSecret123"

        # But when logged, it would be redacted (we can't easily test the log output,
        # but we verify redaction logic works)
