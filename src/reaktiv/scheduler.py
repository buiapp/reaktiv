"""Scheduler: minimal batching & effect flush."""

from __future__ import annotations

from contextlib import contextmanager
import asyncio
from typing import Optional, Callable, Set, TYPE_CHECKING, Generator

from ._debug import debug_log
from . import graph

from collections import deque

if TYPE_CHECKING:  # only for type checkers, avoid runtime import cycles
    from .signal import ComputeSignal

_deferred_computed_queue: deque["ComputeSignal"] = deque()

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
    graph.batch_depth += 1
    debug_log(f"Batch start depth={graph.batch_depth}")
    try:
        yield
    finally:
        graph.batch_depth -= 1
        debug_log(f"Batch end depth={graph.batch_depth}")
        if graph.batch_depth == 0:
            _flush_effects()


# ---------------------------------------------------------------------------
# Public API used by Signal.set to wrap notification
# ---------------------------------------------------------------------------


def start_batch():
    graph.batch_depth += 1


def end_batch():
    graph.batch_depth -= 1
    if graph.batch_depth == 0:
        _flush_effects()


# ---------------------------------------------------------------------------
# Deferred computed processing
# ---------------------------------------------------------------------------


def enqueue_computed(comp: "ComputeSignal"):
    _deferred_computed_queue.append(comp)


def _process_deferred_computed():
    # Drain queue deduplicating while preserving order of last occurrence
    if not _deferred_computed_queue:
        return
    seen: Set[int] = set()
    batch: list["ComputeSignal"] = []
    while _deferred_computed_queue:
        comp = _deferred_computed_queue.pop()
        key = id(comp)
        if key in seen:
            continue
        seen.add(key)
        batch.append(comp)
    # Process in reverse to maintain FIFO behavior
    for comp in reversed(batch):
        try:
            prev_ver: Optional[int] = comp._version
            changed = False
            # Recompute now
            comp._refresh()
            new_ver: Optional[int] = comp._version
            changed = (
                prev_ver is not None and new_ver is not None and new_ver != prev_ver
            )
            # Only notify dependents if value actually changed
            if changed:
                node = comp._targets
                while node is not None:
                    node.target._notify()
                    node = node.next_target
        except Exception as e:
            debug_log(f"Error processing deferred computed: {e}")


# ---------------------------------------------------------------------------
# Effect flush loop
# ---------------------------------------------------------------------------


def _flush_effects():
    if graph.batch_depth > 0:
        return

    # First, process any pending computed recomputations; this may enqueue effects
    while _deferred_computed_queue:
        _process_deferred_computed()

    # Cycle guard
    iterations = 0
    while graph.batched_effect_head is not None:
        iterations += 1
        if iterations > graph.MAX_BATCH_ITERATIONS:
            raise RuntimeError("Reactive cycle detected (effect iterations exceeded)")

        head = graph.batched_effect_head
        graph.batched_effect_head = None

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
                    debug_log(f"Effect execution error: {e}")
            current = nxt

        # After running a batch of effects, process any newly enqueued computeds
        if _deferred_computed_queue:
            _process_deferred_computed()


# ---------------------------------------------------------------------------
# Helpers for Effect to enqueue itself
# ---------------------------------------------------------------------------


def enqueue_effect(effect):
    if graph.batched_effect_head is not None:
        effect._next_batched_effect = graph.batched_effect_head
    graph.batched_effect_head = effect


# Async task helper (central so tests can monkeypatch)
_create_task: Optional[Callable] = None


def create_task(coro):
    if _create_task is not None:
        return _create_task(coro)
    return asyncio.create_task(coro)


def flush_now():
    _flush_effects()
