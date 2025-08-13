"""Reactive graph core inspired by Preact Signals.

Edge-based dependency tracking with versioned producers and
lazy subscription. Not part of the public API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol
import contextvars

# ---------------------------------------------------------------------------
# Flags (bit mask) shared by ComputeSignal / Effect
# ---------------------------------------------------------------------------
RUNNING = 1 << 0
NOTIFIED = 1 << 1
OUTDATED = 1 << 2
DISPOSED = 1 << 3
HAS_ERROR = 1 << 4
TRACKING = 1 << 5

# ---------------------------------------------------------------------------
# Global reactive state
# ---------------------------------------------------------------------------
active_consumer: contextvars.ContextVar[Optional["_Consumer"]] = contextvars.ContextVar(
    "active_consumer", default=None
)

global_version = 0  # incremented whenever a writable signal changes
batch_depth = 0
batch_iteration = 0  # cycle guard similar to preact
MAX_BATCH_ITERATIONS = 100


# Batched effect linked list head (set by Effect)
class _BatchedEffect(Protocol):
    _next_batched_effect: Optional["_BatchedEffect"]
    _flags: int

    def _needs_run(self) -> bool: ...
    def _run_callback(self) -> None: ...


batched_effect_head: Optional[_BatchedEffect] = None


# ---------------------------------------------------------------------------
# Protocols for participants
# ---------------------------------------------------------------------------
class _Consumer(Protocol):
    _sources: Optional["Edge"]
    _flags: int

    def _notify(self) -> None: ...


class _Producer(Protocol):
    _version: int
    _targets: Optional["Edge"]
    _node: Optional["Edge"]

    def _subscribe_edge(self, edge: "Edge") -> None: ...
    def _unsubscribe_edge(self, edge: "Edge") -> None: ...
    def _refresh(self) -> bool: ...


# ---------------------------------------------------------------------------
# Edge node connecting a producer to a consumer
# ---------------------------------------------------------------------------
@dataclass
class Edge:
    source: _Producer
    target: _Consumer
    prev_source: Optional["Edge"] = None
    next_source: Optional["Edge"] = None
    prev_target: Optional["Edge"] = None
    next_target: Optional["Edge"] = None
    version: int = 0  # last seen producer version (-1 reusable)
    rollback_node: Optional["Edge"] = None


# ---------------------------------------------------------------------------
# Dependency management
# ---------------------------------------------------------------------------


def add_dependency(source: _Producer) -> Optional[Edge]:
    consumer = active_consumer.get()
    if consumer is None:
        return None

    node = source._node
    if node is None or node.target is not consumer:
        prev_head = consumer._sources
        edge = Edge(source, consumer, prev_head)
        if prev_head is not None:
            prev_head.next_source = edge
        consumer._sources = edge
        source._node = edge
        if consumer._flags & TRACKING:
            source._subscribe_edge(edge)
        return edge
    elif node.version == -1:
        node.version = 0
        if node.next_source is not None:
            nxt = node.next_source
            prv = node.prev_source
            if prv is not None:
                prv.next_source = nxt
            nxt.prev_source = prv
            prev_head = consumer._sources
            node.prev_source = prev_head
            node.next_source = None
            if prev_head is not None:
                prev_head.next_source = node
            consumer._sources = node
        return node
    return None


# ---------------------------------------------------------------------------
# Source list lifecycle
# ---------------------------------------------------------------------------


def prepare_sources(target: _Consumer) -> None:
    edge = target._sources
    while edge is not None:
        rollback = edge.source._node
        if rollback is not None:
            edge.rollback_node = rollback
        edge.source._node = edge
        edge.version = -1
        if edge.next_source is None:
            target._sources = edge
        edge = edge.next_source


def cleanup_sources(target: _Consumer) -> None:
    edge = target._sources
    head: Optional[Edge] = None
    while edge is not None:
        prev_edge = edge.prev_source
        if edge.version == -1:
            edge.source._unsubscribe_edge(edge)
            if prev_edge is not None:
                prev_edge.next_source = edge.next_source
            if edge.next_source is not None:
                edge.next_source.prev_source = prev_edge
        else:
            head = edge
        edge.source._node = edge.rollback_node
        edge.rollback_node = None
        edge = prev_edge
    target._sources = head


# ---------------------------------------------------------------------------
# Recompute heuristic
# ---------------------------------------------------------------------------


def needs_to_recompute(target: _Consumer) -> bool:
    edge = target._sources
    while edge is not None:
        src = edge.source
        if (
            src._version != edge.version
            or not src._refresh()
            or src._version != edge.version
        ):
            return True
        edge = edge.next_source
    return False


# ---------------------------------------------------------------------------
# Active consumer management
# ---------------------------------------------------------------------------


def set_active_consumer(consumer: Optional[_Consumer]) -> Optional[_Consumer]:
    prev = active_consumer.get()
    active_consumer.set(consumer)
    return prev
