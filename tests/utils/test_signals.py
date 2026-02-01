"""Tests for signal handling and graceful shutdown."""

from __future__ import annotations

import asyncio

import pytest

from scry_ingestor.utils.signals import GracefulShutdown, get_shutdown_manager


@pytest.mark.asyncio
async def test_graceful_shutdown_creation():
    """Test GracefulShutdown initialization."""
    shutdown = GracefulShutdown()

    assert not shutdown.is_shutting_down()
    assert len(shutdown._shutdown_handlers) == 0


@pytest.mark.asyncio
async def test_register_shutdown_handler():
    """Test registering shutdown handlers."""
    shutdown = GracefulShutdown()
    called = []

    def handler():
        called.append("handler")

    shutdown.register_handler(handler)
    assert len(shutdown._shutdown_handlers) == 1


@pytest.mark.asyncio
async def test_shutdown_execution():
    """Test shutdown handler execution."""
    shutdown = GracefulShutdown()
    called = []

    def handler1():
        called.append("handler1")

    async def handler2():
        await asyncio.sleep(0.01)
        called.append("handler2")

    shutdown.register_handler(handler1)
    shutdown.register_handler(handler2)

    await shutdown.shutdown()

    assert shutdown.is_shutting_down()
    assert "handler1" in called
    assert "handler2" in called


@pytest.mark.asyncio
async def test_shutdown_lifo_order():
    """Test shutdown handlers execute in LIFO order."""
    shutdown = GracefulShutdown()
    order = []

    def handler1():
        order.append(1)

    def handler2():
        order.append(2)

    def handler3():
        order.append(3)

    shutdown.register_handler(handler1)
    shutdown.register_handler(handler2)
    shutdown.register_handler(handler3)

    await shutdown.shutdown()

    # Handlers should execute in reverse order (LIFO)
    assert order == [3, 2, 1]


@pytest.mark.asyncio
async def test_shutdown_error_handling():
    """Test that errors in handlers don't stop shutdown."""
    shutdown = GracefulShutdown()
    called = []

    def failing_handler():
        raise RuntimeError("Handler error")

    def good_handler():
        called.append("good")

    shutdown.register_handler(failing_handler)
    shutdown.register_handler(good_handler)

    await shutdown.shutdown()

    # Good handler should still execute despite error
    assert "good" in called
    assert shutdown.is_shutting_down()


@pytest.mark.asyncio
async def test_shutdown_idempotent():
    """Test that multiple shutdown calls are handled correctly."""
    shutdown = GracefulShutdown()
    call_count = []

    def handler():
        call_count.append(1)

    shutdown.register_handler(handler)

    await shutdown.shutdown()
    await shutdown.shutdown()  # Second call should be no-op

    # Handler should only be called once
    assert len(call_count) == 1


@pytest.mark.asyncio
async def test_get_shutdown_manager_singleton():
    """Test global shutdown manager singleton."""
    manager1 = get_shutdown_manager()
    manager2 = get_shutdown_manager()

    assert manager1 is manager2


@pytest.mark.asyncio
async def test_wait_for_shutdown():
    """Test waiting for shutdown completion."""
    shutdown = GracefulShutdown()

    async def wait_task():
        await shutdown.wait_for_shutdown()
        return "completed"

    # Start waiting
    wait_future = asyncio.create_task(wait_task())

    # Give it a moment
    await asyncio.sleep(0.01)
    assert not wait_future.done()

    # Trigger shutdown
    await shutdown.shutdown()

    # Wait should complete
    result = await wait_future
    assert result == "completed"
