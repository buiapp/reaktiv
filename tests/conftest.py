import os
import sys
import signal
import threading
import faulthandler
import pytest

# Global per-test timeout (seconds). Override with PYTEST_TEST_TIMEOUT or PYTEST_TIMEOUT.
_DEFAULT = "5.0"
_TIMEOUT = float(
    os.environ.get("PYTEST_TEST_TIMEOUT", os.environ.get("PYTEST_TIMEOUT", _DEFAULT))
)


@pytest.fixture(autouse=True)
def _per_test_timeout():
    """Fail fast if any test hangs.

    Uses POSIX SIGALRM so it applies to both sync and asyncio tests on macOS/Linux.
    Set PYTEST_TEST_TIMEOUT=0 to disable.
    """
    if _TIMEOUT <= 0:
        yield
        return

    # Only main thread can set signal handlers
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    previous = signal.getsignal(signal.SIGALRM)

    def _handler(signum, frame):  # pragma: no cover
        # Dump all thread stacks to help debugging deadlocks
        faulthandler.dump_traceback(file=sys.stderr, all_threads=True)
        raise TimeoutError(f"Test exceeded timeout of {_TIMEOUT}s")

    signal.signal(signal.SIGALRM, _handler)
    try:
        # Start timer
        signal.setitimer(signal.ITIMER_REAL, _TIMEOUT)
        try:
            yield
        except TimeoutError:
            pytest.fail(f"Test timed out after {_TIMEOUT} seconds")
        finally:
            # Cancel timer
            signal.setitimer(signal.ITIMER_REAL, 0)
    finally:
        # Restore handler
        signal.signal(signal.SIGALRM, previous)
