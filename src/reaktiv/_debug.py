"""Internal debugging utilities for reaktiv."""

from __future__ import annotations

_debug_enabled = False
_suppress_debug = False  # When True, debug logging is suppressed


def set_debug(enabled: bool) -> None:
    """Enable or disable debug logging."""
    global _debug_enabled
    _debug_enabled = enabled


def debug_log(msg: str) -> None:
    """Log a debug message if debugging is enabled and not suppressed."""
    if _debug_enabled and not _suppress_debug:
        print(f"[REAKTIV DEBUG] {msg}")
