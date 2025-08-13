"""Execution context for dependency tracking."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, TypeVar, Union, ContextManager

from . import graph
from .signal import Signal

T = TypeVar("T")


def untracked(
    func_or_signal: Union[Callable[[], T], object, None] = None,
) -> Union[T, ContextManager[None]]:
    """Execute without tracking, or get a signal value without tracking, or provide a context manager."""
    if func_or_signal is None:

        @contextmanager
        def _ctx():
            prev = graph.set_active_consumer(None)
            try:
                yield
            finally:
                graph.set_active_consumer(prev)

        return _ctx()

    prev = graph.set_active_consumer(None)
    try:
        if isinstance(func_or_signal, Signal):
            return func_or_signal._value
        else:
            return func_or_signal()  # type: ignore[misc]
    finally:
        graph.set_active_consumer(prev)
