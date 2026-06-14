"""Scheduler: minimal batching & effect flush."""

from __future__ import annotations

from contextlib import contextmanager
import asyncio
import threading
from typing import Optional, Callable, Generator

from ._debug import debug_log
from . import graph


class _SchedulerState:
    __slots__ = ("batch_depth", "batched_effect_head")

    def __init__(self) -> None:
        self.batch_depth = 0
        self.batched_effect_head: Optional[graph._BatchedEffect] = None


_thread_state = threading.local()


def _get_state() -> _SchedulerState:
    state = getattr(_thread_state, "scheduler_state", None)
    if state is None:
        state = _SchedulerState()
        _thread_state.scheduler_state = state
    return state


def current_batch_depth() -> int:
    return _get_state().batch_depth


# ---------------------------------------------------------------------------
# Batch management
# ---------------------------------------------------------------------------


@contextmanager
def batch() -> Generator[None, None, None]:
    """Batch multiple signal updates to prevent redundant effect executions.
    
    When you update multiple signals, each change normally triggers effects immediately.
    Using `batch()` defers all effect executions until the batch completes, ensuring
    each effect runs only once with the final values.
    
    Yields:
        None
        
    Examples:
        Without batching:
        ```python
        from reaktiv import Signal, Effect
        
        x = Signal(1)
        y = Signal(2)
        
        def log_values():
            print(f"x: {x()}, y: {y()}")
        
        Effect(log_values)
        # Prints: "x: 1, y: 2"
        
        x.set(10)  # Effect runs
        # Prints: "x: 10, y: 2"
        
        y.set(20)  # Effect runs again
        # Prints: "x: 10, y: 20"
        ```
        
        With batching:
        ```python
        from reaktiv import Signal, Effect, batch
        
        x = Signal(1)
        y = Signal(2)
        
        def log_values():
            print(f"x: {x()}, y: {y()}")
        
        Effect(log_values)
        # Prints: "x: 1, y: 2"
        
        with batch():
            x.set(10)  # No effect execution yet
            y.set(20)  # No effect execution yet
        # After batch completes: Effect runs once
        # Prints: "x: 10, y: 20"
        ```
        
        Multiple updates:
        ```python
        from reaktiv import Signal, Effect, batch
        
        items = Signal([])
        
        def log_count():
            print(f"Items: {len(items())}")
        
        Effect(log_count)
        # Prints: "Items: 0"
        
        # Without batch, effect would run 3 times
        with batch():
            items.set([1])
            items.set([1, 2])
            items.set([1, 2, 3])
        # Effect runs once with final value
        # Prints: "Items: 3"
        ```
        
        Nested batches:
        ```python
        from reaktiv import Signal, Effect, batch
        
        x = Signal(0)
        effect = Effect(lambda: print(f"x={x()}"))  # retain reference
        # Prints: "x=0"
        
        with batch():
            x.set(1)
            with batch():
                x.set(2)
                x.set(3)
            x.set(4)
        # Effect runs once after outermost batch
        # Prints: "x=4"
        ```
    """
    state = _get_state()
    state.batch_depth += 1
    debug_log(lambda: f"Batch start depth={state.batch_depth}")
    try:
        yield
    finally:
        state.batch_depth -= 1
        debug_log(lambda: f"Batch end depth={state.batch_depth}")
        if state.batch_depth == 0:
            _flush_effects()


# ---------------------------------------------------------------------------
# Public API used by Signal.set to wrap notification
# ---------------------------------------------------------------------------


def start_batch():
    _get_state().batch_depth += 1


def end_batch():
    state = _get_state()
    state.batch_depth -= 1
    if state.batch_depth == 0:
        _flush_effects()


# ---------------------------------------------------------------------------
# Effect flush loop
# ---------------------------------------------------------------------------


def _flush_effects():
    state = _get_state()
    if state.batch_depth > 0:
        return

    # Cycle guard
    iterations = 0
    while state.batched_effect_head is not None:
        iterations += 1
        if iterations > graph.MAX_BATCH_ITERATIONS:
            raise RuntimeError("Reactive cycle detected (effect iterations exceeded)")

        head = state.batched_effect_head
        state.batched_effect_head = None

        # Traverse linked list
        current = head
        while current is not None:
            nxt = current._next_batched_effect
            current._next_batched_effect = None
            current._flags &= ~graph.NOTIFIED
            if not (current._flags & graph.DISPOSED) and current._needs_run():
                try:
                    current._run_callback()
                except Exception as e:
                    debug_log(lambda exc=e: f"Effect execution error: {exc}")
            current = nxt


# ---------------------------------------------------------------------------
# Helpers for Effect to enqueue itself
# ---------------------------------------------------------------------------


def enqueue_effect(effect):
    state = _get_state()
    if state.batched_effect_head is not None:
        effect._next_batched_effect = state.batched_effect_head
    state.batched_effect_head = effect


# Async task helper (central so tests can monkeypatch)
_create_task: Optional[Callable] = None


def create_task(coro):
    if _create_task is not None:
        return _create_task(coro)
    return asyncio.create_task(coro)


def flush_now():
    _flush_effects()
