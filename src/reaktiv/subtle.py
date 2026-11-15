"""Low-level primitives for framework authors, modelled on TC39 ``Signal.subtle``.

Application code should use ``effect``. These helpers let integrations build
their own scheduling, track reads, and detect changes without evaluating.
"""

from __future__ import annotations

import threading
import traceback
from typing import Any, Callable, Optional, Union

from . import graph
from .protocols import ReadableSignal
from .signal import ComputeSignal, ReadonlySignal, Signal, _SignalBase

__all__ = ["Watcher", "current_consumer", "signal_version"]

# Every signal node: writable, computed (including linked) and read-only views.
_Node = Union[Signal[Any], ComputeSignal[Any], ReadonlySignal[Any]]


def _producer(node: _Node) -> _SignalBase[Any]:
    if isinstance(node, ReadonlySignal):
        return node._signal
    if not isinstance(node, _SignalBase):
        raise TypeError("Expected a Signal or ReadonlySignal")
    return node


class Watcher:
    """Get notified when watched signals may have changed, without evaluating them.

    ``notify`` runs synchronously while a change propagates (also inside
    ``batch``), at most once until the watcher is re-armed with ``watch()``.
    It must not read or write signals, not even through ``untracked``; doing
    so raises. Schedule work instead, and read the nodes returned by
    ``get_pending()`` on your own schedule::

        watcher = Watcher(lambda: loop.call_soon(flush))
        view = computed(render)
        watcher.watch(view)

        def flush():
            watcher.watch()      # re-arm first, so changes made while
                                 # committing schedule another flush
            for node in watcher.get_pending():
                commit(node())   # evaluate and apply side effects here

    Re-arming after committing instead would suppress notifications caused
    by the commit and leave nodes pending with no flush scheduled.

    Differences from TC39 ``Signal.subtle.Watcher``: sources reference a
    watcher weakly (keep it alive for as long as it should observe, and call
    ``dispose()`` or register it with ``model.own`` when finished); exceptions
    raised by ``notify`` are printed instead of propagating, so the remaining
    consumers are still notified. As in TC39, only computed nodes are ever
    pending; watching a plain signal notifies but never makes it pending.
    """

    _reaktiv_weak_target = True

    def __init__(self, notify: Callable[[], None]) -> None:
        self._notify_fn = notify
        self._sources: Optional[graph.Edge] = None
        self._source_map: dict[int, graph.Edge] = {}
        self._flags: int = graph.TRACKING
        self._graph_lock: Optional[threading.RLock] = threading.RLock()
        # Handles exactly as passed by the caller (readonly wrappers stay readonly).
        self._watched: dict[int, tuple[_SignalBase[Any], ReadableSignal[Any]]] = {}

    def watch(self, *nodes: _Node) -> None:
        """Start watching ``nodes`` and re-arm ``notify``. Never evaluates them.

        Does nothing after ``dispose()``, so an already scheduled flush can
        safely re-arm a watcher that was disposed in the meantime.
        """
        producers = [(_producer(node), node) for node in nodes]
        with graph.consumer_lock(self):
            if self._flags & graph.DISPOSED:
                return
            for source, node in producers:
                edge = graph.add_source(source, self)
                if edge is not None:
                    edge.version = source._version
                    self._watched[id(source)] = (source, node)
            self._flags &= ~graph.NOTIFIED

    def unwatch(self, *nodes: _Node) -> None:
        """Stop watching ``nodes``; nodes that are not watched are ignored."""
        producers = [_producer(node) for node in nodes]
        with graph.consumer_lock(self):
            for source in producers:
                if graph.remove_source(self, source):
                    del self._watched[id(source)]

    def dispose(self) -> None:
        """Stop watching everything; ``notify`` is never called again."""
        with graph.consumer_lock(self):
            self._flags |= graph.DISPOSED
            for source, _ in list(self._watched.values()):
                graph.remove_source(self, source)
            self._watched.clear()

    def get_pending(self) -> list[ReadableSignal[Any]]:
        """Return watched computed nodes that need evaluation. Never evaluates."""
        with graph.consumer_lock(self):
            watched = list(self._watched.values())
        return [
            node
            for source, node in watched
            if isinstance(source, ComputeSignal)
            and (source._flags & graph.OUTDATED or source._version == 0)
        ]

    def _notify(self) -> None:
        with graph.consumer_lock(self):
            if self._flags & (graph.NOTIFIED | graph.DISPOSED):
                return
            self._flags |= graph.NOTIFIED
        # Nothing is tracked during notify, and reads/writes are rejected even
        # under untracked(); the guard is independent of the tracking context.
        previous_consumer = graph.set_active_consumer(None)
        previous_notifying = graph.set_notifying(True)
        try:
            self._notify_fn()
        except Exception:
            traceback.print_exc()
        finally:
            graph.set_notifying(previous_notifying)
            graph.set_active_consumer(previous_consumer)


def current_consumer() -> Optional[object]:
    """Return the computation or effect currently tracking reads, or None.

    ``None`` also inside ``untracked`` and during a Watcher's ``notify``. Treat
    the result as an opaque identity:
    do not run, schedule or mutate it.
    """
    return graph.active_consumer.get()


def signal_version(node: _Node) -> int:
    """Return the node's revision without reading, evaluating or tracking it.

    The revision advances whenever the node publishes a new value (or error).
    It is local to one node. A computed that is stale keeps its old revision
    until something reads it.
    """
    source = _producer(node)
    if source._lock is not None:
        with source._lock:
            return source._version
    return source._version
