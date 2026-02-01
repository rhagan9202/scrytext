"""Signal handling and graceful shutdown utilities."""

from __future__ import annotations

import asyncio
import signal
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
from typing import Any

from ..utils.logging import setup_logger

logger = setup_logger(__name__)


class GracefulShutdown:
    """
    Manages graceful shutdown for the application.

    Handles SIGTERM and SIGINT signals, executes registered shutdown handlers,
    and ensures clean resource cleanup.
    """

    def __init__(self) -> None:
        """Initialize graceful shutdown manager."""
        self._shutdown_handlers: list[Callable[[], Any]] = []
        self._is_shutting_down = False
        self._shutdown_event = asyncio.Event()
        self._executor = ThreadPoolExecutor(thread_name_prefix="scry-ingestor-shutdown")

    async def _run_sync_handler(self, handler: Callable[[], Any]) -> None:
        future = self._executor.submit(handler)
        try:
            while not future.done():
                await asyncio.sleep(0.01)
            future.result()
        except asyncio.CancelledError:
            future.cancel()
            raise

    def register_handler(self, handler: Callable[[], Any]) -> None:
        """
        Register a shutdown handler to be called during shutdown.

        Handlers are called in reverse registration order (LIFO).

        Args:
            handler: Sync or async callable to execute during shutdown
        """
        self._shutdown_handlers.append(handler)
        logger.info(f"Registered shutdown handler: {handler.__name__}")

    async def shutdown(self) -> None:
        """
        Execute graceful shutdown sequence.

        Calls all registered handlers in reverse order and marks shutdown complete.
        """
        if self._is_shutting_down:
            logger.warning("Shutdown already in progress")
            return

        self._is_shutting_down = True
        logger.info("Starting graceful shutdown...")

        # Execute handlers in reverse order (LIFO)
        for handler in reversed(self._shutdown_handlers):
            try:
                logger.info(f"Executing shutdown handler: {handler.__name__}")
                if asyncio.iscoroutinefunction(handler):
                    await handler()
                else:
                    await self._run_sync_handler(handler)
                logger.info(f"Completed shutdown handler: {handler.__name__}")
            except Exception as e:
                logger.error(
                    f"Error in shutdown handler {handler.__name__}: {e}", exc_info=True
                )

        self._shutdown_event.set()
        logger.info("Graceful shutdown complete")

    def is_shutting_down(self) -> bool:
        """Check if shutdown is in progress."""
        return self._is_shutting_down

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown to complete."""
        await self._shutdown_event.wait()


# Global shutdown manager instance
_shutdown_manager: GracefulShutdown | None = None


def get_shutdown_manager() -> GracefulShutdown:
    """Get or create global shutdown manager."""
    global _shutdown_manager
    if _shutdown_manager is None:
        _shutdown_manager = GracefulShutdown()
    return _shutdown_manager


def install_signal_handlers(
    shutdown_manager: GracefulShutdown | None = None,
    signals: list[signal.Signals] | None = None,
) -> None:
    """
    Install signal handlers for graceful shutdown.

    Args:
        shutdown_manager: Shutdown manager to use (creates new if None)
        signals: List of signals to handle (defaults to SIGTERM and SIGINT)
    """
    if shutdown_manager is None:
        shutdown_manager = get_shutdown_manager()

    if threading.current_thread() is not threading.main_thread():
        logger.info("Skipping signal handler installation outside main thread")
        return

    if signals is None:
        signals = [signal.SIGTERM, signal.SIGINT]

    def signal_handler(signum: int, frame: Any) -> None:
        """Handle shutdown signal."""
        sig_name = signal.Signals(signum).name
        logger.info(f"Received {sig_name}, initiating graceful shutdown...")

        # Schedule shutdown in the event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(shutdown_manager.shutdown())
        else:
            asyncio.run(shutdown_manager.shutdown())

    for sig in signals:
        signal.signal(sig, signal_handler)
        logger.info(f"Installed signal handler for {sig.name}")


def install_reload_handler(reload_fn: Callable[[], Any]) -> None:
    """
    Install SIGHUP handler for configuration reload.

    Args:
        reload_fn: Function to call when SIGHUP is received
    """

    def sighup_handler(signum: int, frame: Any) -> None:
        """Handle SIGHUP signal for config reload."""
        logger.info("Received SIGHUP, reloading configuration...")
        try:
            if asyncio.iscoroutinefunction(reload_fn):
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(reload_fn())
                else:
                    asyncio.run(reload_fn())
            else:
                reload_fn()
            logger.info("Configuration reload complete")
        except Exception as e:
            logger.error(f"Error during configuration reload: {e}", exc_info=True)

    if threading.current_thread() is not threading.main_thread():
        logger.info("Skipping SIGHUP handler installation outside main thread")
        return

    if sys.platform != "win32":  # SIGHUP not available on Windows
        signal.signal(signal.SIGHUP, sighup_handler)
        logger.info("Installed SIGHUP handler for configuration reload")
    else:
        logger.warning("SIGHUP handler not available on Windows")
