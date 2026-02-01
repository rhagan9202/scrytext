"""Audit logging infrastructure for security-sensitive operations."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .logging import setup_logger

# Separate audit logger (writes to dedicated audit log file)
audit_logger = setup_logger("scry_ingestor.audit", context={"log_type": "audit"})


class AuditAction(str, Enum):
    """Enumeration of auditable actions."""

    # Authentication & Authorization
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    LOGOUT = "auth.logout"
    API_KEY_CREATED = "auth.api_key.created"
    API_KEY_REVOKED = "auth.api_key.revoked"
    PERMISSION_DENIED = "auth.permission.denied"

    # Data Access
    DATA_READ = "data.read"
    DATA_WRITE = "data.write"
    DATA_DELETE = "data.delete"
    DATA_EXPORT = "data.export"

    # Configuration Changes
    CONFIG_UPDATED = "config.updated"
    CONFIG_RELOADED = "config.reloaded"
    ADAPTER_REGISTERED = "config.adapter.registered"
    ADAPTER_REMOVED = "config.adapter.removed"

    # Ingestion Operations
    INGESTION_STARTED = "ingestion.started"
    INGESTION_COMPLETED = "ingestion.completed"
    INGESTION_FAILED = "ingestion.failed"

    # System Operations
    SERVICE_STARTED = "system.service.started"
    SERVICE_STOPPED = "system.service.stopped"
    HEALTH_CHECK_FAILED = "system.health.failed"


class AuditOutcome(str, Enum):
    """Audit event outcome."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    DENIED = "denied"


class AuditEvent(BaseModel):
    """Structured audit event."""

    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp of the event",
    )
    action: AuditAction = Field(..., description="Action being audited")
    outcome: AuditOutcome = Field(..., description="Outcome of the action")
    actor: str = Field(..., description="User, service, or API key performing action")
    actor_type: str = Field(
        default="user",
        description="Type of actor (user, service, api_key, system)",
    )
    resource: str | None = Field(
        default=None, description="Resource being acted upon"
    )
    resource_type: str | None = Field(
        default=None, description="Type of resource (file, record, config)"
    )
    client_ip: str | None = Field(
        default=None, description="IP address of the client"
    )
    correlation_id: str | None = Field(
        default=None, description="Correlation ID for distributed tracing"
    )
    details: dict[str, Any] = Field(
        default_factory=dict, description="Additional context-specific details"
    )
    error_message: str | None = Field(
        default=None, description="Error message if outcome is failure/denied"
    )


class SensitiveFieldRedactor:
    """Redacts sensitive information from log data."""

    # Patterns for sensitive data detection
    PATTERNS = {
        "api_key": re.compile(
            r"(api[_-]?key|apikey)[\"']?\s*[:=]\s*[\"']?([a-zA-Z0-9_\-]+)",
            re.IGNORECASE,
        ),
        "password": re.compile(
            r"(password|passwd|pwd)[\"']?\s*[:=]\s*[\"']?([^\s\"']+)",
            re.IGNORECASE,
        ),
        "token": re.compile(
            r"(token|bearer)[\"']?\s*[:=]\s*[\"']?([a-zA-Z0-9_.\-]+)",
            re.IGNORECASE,
        ),
        "credit_card": re.compile(
            r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b"
        ),
        "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "email": re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
        ),
    }

    # Fields that should always be redacted (case-insensitive)
    SENSITIVE_FIELD_NAMES = {
        "password",
        "passwd",
        "pwd",
        "secret",
        "api_key",
        "apikey",
        "token",
        "bearer",
        "authorization",
        "auth",
        "credentials",
        "private_key",
        "aws_secret_access_key",
        "aws_access_key_id",
        "database_url",
        "connection_string",
    }

    @classmethod
    def redact_string(cls, text: str) -> str:
        """Redact sensitive patterns in a string."""
        if not isinstance(text, str):
            return text

        redacted = text
        for pattern_name, pattern in cls.PATTERNS.items():
            if pattern_name in ["email"]:
                # Partial redaction for emails: keep domain
                redacted = pattern.sub(
                    lambda m: (
                        f"{m.group().split('@')[0][:3]}***@"
                        f"{m.group().split('@')[1]}"
                    ),
                    redacted,
                )
            elif pattern_name in ["credit_card"]:
                # Show only last 4 digits
                redacted = pattern.sub(lambda m: f"****-****-****-{m.group()[-4:]}", redacted)
            elif pattern_name in ["ssn"]:
                # Show only last 4 digits
                redacted = pattern.sub(lambda m: f"***-**-{m.group()[-4:]}", redacted)
            else:
                # Full redaction for keys/tokens/passwords
                redacted = pattern.sub(r"\1=***REDACTED***", redacted)

        return redacted

    @classmethod
    def redact_dict(cls, data: dict[str, Any], max_depth: int = 10) -> dict[str, Any]:
        """Recursively redact sensitive fields in a dictionary."""
        if max_depth <= 0:
            return data

        redacted = {}
        for key, value in data.items():
            # Check if key is sensitive
            if key.lower() in cls.SENSITIVE_FIELD_NAMES:
                redacted[key] = "***REDACTED***"
            elif isinstance(value, dict):
                redacted[key] = cls.redact_dict(value, max_depth - 1)
            elif isinstance(value, list):
                redacted[key] = [
                    (
                        cls.redact_dict(item, max_depth - 1)
                        if isinstance(item, dict)
                        else cls.redact_string(str(item))
                    )
                    for item in value
                ]
            elif isinstance(value, str):
                redacted[key] = cls.redact_string(value)
            else:
                redacted[key] = value

        return redacted

    @classmethod
    def redact_object(cls, obj: Any) -> Any:
        """Redact sensitive data from various object types."""
        if isinstance(obj, dict):
            return cls.redact_dict(obj)
        elif isinstance(obj, str):
            return cls.redact_string(obj)
        elif isinstance(obj, list):
            return [cls.redact_object(item) for item in obj]
        elif hasattr(obj, "__dict__"):
            # Handle Pydantic models and other objects with __dict__
            return cls.redact_dict(obj.__dict__)
        else:
            return obj


class AuditLogger:
    """Audit logger with automatic sensitive data redaction."""

    def __init__(self, redact_sensitive: bool = True):
        """
        Initialize audit logger.

        Args:
            redact_sensitive: Whether to automatically redact sensitive data
        """
        self.redact_sensitive = redact_sensitive
        self.redactor = SensitiveFieldRedactor()

    def log_event(self, event: AuditEvent) -> None:
        """
        Log an audit event with automatic redaction.

        Args:
            event: Audit event to log
        """
        # Convert to dict for logging
        event_dict = event.model_dump(exclude_none=True)

        # Redact sensitive data if enabled
        if self.redact_sensitive:
            event_dict = self.redactor.redact_dict(event_dict)

        # Log as structured JSON
        audit_logger.info(
            f"AUDIT: {event.action.value}",
            extra={
                "audit_event": event_dict,
                "actor": event.actor,
                "action": event.action.value,
                "outcome": event.outcome.value,
                "resource": event.resource,
            },
        )

    def log_auth_success(
        self,
        actor: str,
        actor_type: str = "user",
        client_ip: str | None = None,
        correlation_id: str | None = None,
        **details: Any,
    ) -> None:
        """Log successful authentication."""
        event = AuditEvent(
            action=AuditAction.LOGIN_SUCCESS,
            outcome=AuditOutcome.SUCCESS,
            actor=actor,
            actor_type=actor_type,
            client_ip=client_ip,
            correlation_id=correlation_id,
            details=details,
        )
        self.log_event(event)

    def log_auth_failure(
        self,
        actor: str,
        reason: str,
        actor_type: str = "user",
        client_ip: str | None = None,
        correlation_id: str | None = None,
        **details: Any,
    ) -> None:
        """Log failed authentication attempt."""
        event = AuditEvent(
            action=AuditAction.LOGIN_FAILURE,
            outcome=AuditOutcome.FAILURE,
            actor=actor,
            actor_type=actor_type,
            client_ip=client_ip,
            correlation_id=correlation_id,
            error_message=reason,
            details=details,
        )
        self.log_event(event)

    def log_data_access(
        self,
        actor: str,
        resource: str,
        action: AuditAction,
        outcome: AuditOutcome,
        actor_type: str = "user",
        resource_type: str = "record",
        client_ip: str | None = None,
        correlation_id: str | None = None,
        error_message: str | None = None,
        **details: Any,
    ) -> None:
        """Log data access operation."""
        event = AuditEvent(
            action=action,
            outcome=outcome,
            actor=actor,
            actor_type=actor_type,
            resource=resource,
            resource_type=resource_type,
            client_ip=client_ip,
            correlation_id=correlation_id,
            error_message=error_message,
            details=details,
        )
        self.log_event(event)

    def log_config_change(
        self,
        actor: str,
        resource: str,
        outcome: AuditOutcome,
        actor_type: str = "system",
        client_ip: str | None = None,
        correlation_id: str | None = None,
        error_message: str | None = None,
        **details: Any,
    ) -> None:
        """Log configuration change."""
        event = AuditEvent(
            action=AuditAction.CONFIG_UPDATED,
            outcome=outcome,
            actor=actor,
            actor_type=actor_type,
            resource=resource,
            resource_type="config",
            client_ip=client_ip,
            correlation_id=correlation_id,
            error_message=error_message,
            details=details,
        )
        self.log_event(event)

    def log_ingestion(
        self,
        actor: str,
        resource: str,
        outcome: AuditOutcome,
        adapter_type: str,
        source_id: str,
        actor_type: str = "service",
        correlation_id: str | None = None,
        error_message: str | None = None,
        **details: Any,
    ) -> None:
        """Log data ingestion operation."""
        action = (
            AuditAction.INGESTION_COMPLETED
            if outcome == AuditOutcome.SUCCESS
            else AuditAction.INGESTION_FAILED
        )
        event = AuditEvent(
            action=action,
            outcome=outcome,
            actor=actor,
            actor_type=actor_type,
            resource=resource,
            resource_type="ingestion_record",
            correlation_id=correlation_id,
            error_message=error_message,
            details={"adapter_type": adapter_type, "source_id": source_id, **details},
        )
        self.log_event(event)


# Global audit logger instance
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Get or create the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger(redact_sensitive=True)
    return _audit_logger
