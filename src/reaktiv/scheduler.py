"""Scheduler: minimal batching & effect flush."""

from __future__ import annotations

from contextlib import contextmanager
import asyncio
from typing import Optional, Callable, Set, TYPE_CHECKING

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
def batch():
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
