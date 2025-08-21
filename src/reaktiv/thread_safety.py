"""Thread safety configuration for reactive signals.

This module provides a global toggle for thread safety features.
When enabled, signals and effects will use appropriate locking mechanisms.
"""

from __future__ import annotations

from ._debug import debug_log

# Global toggle for thread safety. When False, no thread safety measures are applied
_THREAD_SAFETY_ENABLED: bool = True


def set_thread_safety(enabled: bool) -> None:
    """Enable or disable thread-safety globally.

    - When True (default): Signal/Effect operations may use locking for thread safety.
    - When False: No thread safety measures are applied (not thread-safe!).

    Args:
        enabled: Whether to enable thread safety features.
    """
    global _THREAD_SAFETY_ENABLED
    _THREAD_SAFETY_ENABLED = bool(enabled)
    debug_log(f"Thread safety {'enabled' if enabled else 'disabled'}")


def is_thread_safety_enabled() -> bool:
    """Return current global thread-safety state.

    Returns:
        True if thread safety is enabled, False otherwise.
    """
    return _THREAD_SAFETY_ENABLED
