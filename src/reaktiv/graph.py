"""Reactive graph core inspired by Preact Signals.

Edge-based dependency tracking with versioned producers and
lazy subscription. Not part of the public API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, Union
import contextvars
import threading
import weakref

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
_graph_mutation_lock = threading.RLock()


def mutation_lock() -> threading.RLock:
    return _graph_mutation_lock


def producer_lock(source: "_Producer") -> threading.RLock:
    lock = getattr(source, "_lock", None)
    if lock is not None:
        return lock
    return mutation_lock()


def consumer_lock(consumer: "_Consumer") -> threading.RLock:
    lock = getattr(consumer, "_graph_lock", None)
    if lock is not None:
        return lock
    lock = getattr(consumer, "_computation_lock", None)
    if lock is not None:
        return lock
    return mutation_lock()


def snapshot_targets(source: "_Producer") -> List["_Consumer"]:
    if source._targets is None:
        return []

    targets: List[_Consumer] = []
    with producer_lock(source):
        node = source._targets
        while node is not None:
            target = node.target
            if target is not None:
                targets.append(target)
            node = node.next_target
    return targets


# ---------------------------------------------------------------------------
# Protocols for participants
# ---------------------------------------------------------------------------
class _Consumer(Protocol):
    _sources: Optional["Edge"]
    _source_map: Dict[int, "Edge"]
    _flags: int
    _graph_lock: Optional[threading.RLock]

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
    _target_ref: Union[_Consumer, "weakref.ref[_Consumer]"] = field(repr=False)
    prev_source: Optional["Edge"] = None
    next_source: Optional["Edge"] = None
    prev_target: Optional["Edge"] = None
    next_target: Optional["Edge"] = None
    version: int = 0  # last seen producer version (-1 reusable)
    rollback_node: Optional["Edge"] = None

    @property
    def target(self) -> Optional[_Consumer]:
        """Get the target consumer, dereferencing weakref if needed."""
        if isinstance(self._target_ref, weakref.ref):
            return self._target_ref()
        return self._target_ref

    def is_alive(self) -> bool:
        """Check if the target is still alive."""
        return self.target is not None


# ---------------------------------------------------------------------------
# Dependency management
# ---------------------------------------------------------------------------


def _is_effect(consumer: _Consumer) -> bool:
    """Check if consumer is an Effect."""
    # Avoid circular import by checking type name
    return type(consumer).__name__ == "Effect"


def _create_edge_with_weakref_cleanup(source: _Producer, consumer: _Consumer, prev_head: Optional[Edge]) -> Edge:
    """Create an Edge with weakref for Effects and cleanup callback."""
    
    # Use weakref for Effects to allow garbage collection
    if _is_effect(consumer):
        def on_effect_gc(weak_ref: "weakref.ref[_Consumer]") -> None:
            """Called when an Effect is garbage collected - clean up the edge."""
            # Remove edge from source's targets list
            with mutation_lock():
                edge_to_remove = None
                current = source._targets
                while current is not None:
                    if current._target_ref is weak_ref:
                        edge_to_remove = current
                        break
                    current = current.next_target

                if edge_to_remove is not None:
                    source._unsubscribe_edge(edge_to_remove)
        
        target_ref = weakref.ref(consumer, on_effect_gc)
    else:
        target_ref = consumer
    
    return Edge(source, target_ref, prev_head)


def add_dependency(source: _Producer) -> Optional[Edge]:
    consumer = active_consumer.get()
    if consumer is None:
        return None

    lock = consumer._graph_lock
    if lock is None:
        return _add_dependency_unlocked(source, consumer)

    with lock:
        return _add_dependency_unlocked(source, consumer)


def _add_dependency_unlocked(source: _Producer, consumer: _Consumer) -> Optional[Edge]:
    source_id = id(source)
    edge = consumer._source_map.get(source_id)
    if edge is not None and edge.target is consumer:
        if edge.version == -1:
            edge.version = 0
            return edge
        return None

    prev_head = consumer._sources
    edge = _create_edge_with_weakref_cleanup(source, consumer, prev_head)
    if prev_head is not None:
        prev_head.next_source = edge
    consumer._sources = edge
    consumer._source_map[source_id] = edge
    if consumer._flags & TRACKING:
        source._subscribe_edge(edge)
    return edge


# ---------------------------------------------------------------------------
# Source list lifecycle
# ---------------------------------------------------------------------------


def prepare_sources(target: _Consumer) -> None:
    lock = target._graph_lock
    if lock is not None:
        with lock:
            _prepare_sources_unlocked(target)
        return
    _prepare_sources_unlocked(target)


def _prepare_sources_unlocked(target: _Consumer) -> None:
    edge = target._sources
    while edge is not None:
        edge.version = -1
        edge = edge.prev_source


def cleanup_sources(target: _Consumer) -> None:
    lock = target._graph_lock
    if lock is not None:
        with lock:
            _cleanup_sources_unlocked(target)
        return
    _cleanup_sources_unlocked(target)


def _cleanup_sources_unlocked(target: _Consumer) -> None:
    edge = target._sources
    while edge is not None:
        prev_edge = edge.prev_source
        if edge.version == -1:
            edge.source._unsubscribe_edge(edge)
            target._source_map.pop(id(edge.source), None)
            if prev_edge is not None:
                prev_edge.next_source = edge.next_source
            if edge.next_source is not None:
                edge.next_source.prev_source = prev_edge
            if target._sources is edge:
                target._sources = prev_edge
            edge.prev_source = None
            edge.next_source = None
        edge = prev_edge


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
        edge = edge.prev_source
    return False


# ---------------------------------------------------------------------------
# Active consumer management
# ---------------------------------------------------------------------------


def set_active_consumer(consumer: Optional[_Consumer]) -> Optional[_Consumer]:
    prev = active_consumer.get()
    active_consumer.set(consumer)
    return prev
