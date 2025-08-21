"""Writable Signal implementation.

Migrated to Edge-based dependency tracking and minimal scheduler.
"""

from __future__ import annotations

import threading
from typing import Callable, Generic, Optional, TypeVar, cast

from ._debug import debug_log
from . import graph
from .scheduler import start_batch, end_batch
from . import scheduler as _sched
from .thread_safety import is_thread_safety_enabled

T = TypeVar("T")


class Signal(Generic[T]):
    """Reactive writable signal."""

    __slots__ = (
        "_value",
        "_equal",
        "_readonly_cache",
        "_version",
        "_targets",
        "_node",
        "_lock",
    )

    def __init__(self, value: T, *, equal: Optional[Callable[[T, T], bool]] = None):
        self._value = value
        self._equal = equal
        self._readonly_cache: Optional[ReadonlySignal[T]] = None
        self._version: int = 0
        self._targets: Optional[graph.Edge] = None
        self._node: Optional[graph.Edge] = None
        # RLock for thread-safe operations - only when thread safety is enabled
        self._lock = threading.RLock() if is_thread_safety_enabled() else None
        debug_log(f"Signal initialized with value: {value}")

    def __repr__(self) -> str:
        try:
            return f"Signal(value={repr(self._value)})"
        except Exception as e:
            return f"Signal(error_displaying_value: {str(e)})"

    def __call__(self) -> T:
        return self.get()

    # Producer API expected by graph core
    def _subscribe_edge(self, edge: graph.Edge) -> None:
        targets = self._targets
        if targets is not edge and edge.prev_target is None:
            edge.next_target = targets
            self._targets = edge
            if targets is not None:
                targets.prev_target = edge

    def _unsubscribe_edge(self, edge: graph.Edge) -> None:
        if self._targets is None:
            return
        prev = edge.prev_target
        nxt = edge.next_target
        if prev is not None:
            prev.next_target = nxt
            edge.prev_target = None
        if nxt is not None:
            nxt.prev_target = prev
            edge.next_target = None
        if edge is self._targets:
            self._targets = nxt

    def _refresh(self) -> bool:
        return True

    def get(self) -> T:
        # Use lock to protect the read operation only when thread safety is enabled
        if self._lock is not None:
            with self._lock:
                edge = graph.add_dependency(self)
                if edge is not None:
                    edge.version = self._version
                debug_log(f"Signal get() returning value: {self._value}")
                return self._value
        else:
            edge = graph.add_dependency(self)
            if edge is not None:
                edge.version = self._version
            debug_log(f"Signal get() returning value: {self._value}")
            return self._value

    def set(self, new_value: T) -> None:
        debug_log(
            f"Signal set() called with new_value: {new_value} (old_value: {self._value})"
        )
        # Disallow side effects from within a ComputeSignal's computation
        active = graph.active_consumer.get()
        if active is not None:
            if isinstance(active, ComputeSignal):
                raise RuntimeError(
                    "Side effect detected: Cannot set Signal from within a ComputeSignal computation"
                )

        # Use lock to protect the entire set operation when thread safety is enabled
        if self._lock is not None:
            with self._lock:
                self._set_internal(new_value)
        else:
            self._set_internal(new_value)

    def _set_internal(self, new_value: T) -> None:
        """Internal set method that does the actual work without locking."""
        should_update = True
        if self._equal is not None:
            try:
                if self._equal(self._value, new_value):
                    should_update = False
            except Exception as e:
                debug_log(f"Error in custom equality check during set: {e}")
        else:
            if self._value is new_value:
                should_update = False
        if not should_update:
            return

        self._value = new_value
        self._version += 1
        graph.global_version += 1

        start_batch()
        try:
            node = self._targets
            while node is not None:
                node.target._notify()
                node = node.next_target
        finally:
            end_batch()

    def update(self, update_fn: Callable[[T], T]) -> None:
        """Atomically update the signal using a function."""
        # Use lock to protect the read-modify-write operation when thread safety is enabled
        if self._lock is not None:
            with self._lock:
                new_value = update_fn(self._value)
                self._set_internal(new_value)
        else:
            new_value = update_fn(self._value)
            self._set_internal(new_value)

    def as_readonly(self) -> "ReadonlySignal[T]":
        if self._readonly_cache is None:
            self._readonly_cache = ReadonlySignal(self)
        return self._readonly_cache


class ReadonlySignal(Generic[T]):
    """A readonly wrapper around a Signal that prevents modification."""

    __slots__ = ("_signal",)

    def __init__(self, signal: Signal[T]):
        self._signal = signal

    def __repr__(self) -> str:
        try:
            return f"ReadonlySignal(value={repr(self._signal._value)})"
        except Exception as e:
            return f"ReadonlySignal(error_displaying_value: {str(e)})"

    def __call__(self) -> T:
        return self.get()

    def get(self) -> T:
        return self._signal.get()


class ComputeSignal(Signal[T]):
    """Computed signal that derives value from other signals."""

    __slots__ = (
        "_fn",
        "_sources",
        "_global_version_seen",
        "_flags",
        "_last_error",
        "_dependencies",
        "_thread_local",
        "_computation_lock",
    ) + Signal.__slots__

    def __init__(
        self,
        compute_fn: Callable[[], T],
        *,
        equal: Optional[Callable[[T, T], bool]] = None,
    ):
        super().__init__(None, equal=equal)  # type: ignore[arg-type]
        self._fn = compute_fn
        # Explicit typing for consumer sources list
        self._sources: Optional[graph.Edge] = None
        self._global_version_seen: int = graph.global_version - 1
        self._flags: int = graph.OUTDATED
        self._last_error: Optional[BaseException] = None
        self._dependencies: set[object] = set()
        # Thread-local storage for tracking running state per thread
        self._thread_local = threading.local()
        # RLock for thread-safe computation - only when thread safety is enabled
        self._computation_lock = (
            threading.RLock() if is_thread_safety_enabled() else None
        )

    def _is_running_in_current_thread(self) -> bool:
        """Check if this signal is currently being computed in the current thread."""
        try:
            return getattr(self._thread_local, "is_running", False)
        except AttributeError:
            return False

    def _set_running_in_current_thread(self, running: bool) -> None:
        """Set the running state for the current thread."""
        self._thread_local.is_running = running

    # Producer API (override to detect first/last subscriber)
    def _subscribe_edge(self, edge: graph.Edge) -> None:
        had_subs = self._targets is not None
        super()._subscribe_edge(edge)
        if not had_subs and self._targets is not None:
            # became watched
            self._flags |= graph.OUTDATED | graph.TRACKING
            # lazily subscribe to existing sources
            node = self._sources
            while node is not None:
                node.source._subscribe_edge(node)
                node = node.next_source

    def _unsubscribe_edge(self, edge: graph.Edge) -> None:
        super()._unsubscribe_edge(edge)
        if self._targets is None:
            # lost last subscriber
            self._flags &= ~graph.TRACKING
            node = self._sources
            while node is not None:
                node.source._unsubscribe_edge(node)
                node = node.next_source

    # Consumer refresh logic
    def _refresh(self) -> bool:
        # clear NOTIFIED
        self._flags &= ~graph.NOTIFIED

        # Thread-safe cycle detection
        if self._is_running_in_current_thread():
            return False  # cycle guard: appear stale to caller

        force = bool(self._flags & graph.HAS_ERROR)

        # If tracking and not marked outdated, value can't have changed
        if (
            not force
            and (self._flags & (graph.OUTDATED | graph.TRACKING)) == graph.TRACKING
        ):
            return True
        # clear outdated bit
        self._flags &= ~graph.OUTDATED

        if not force and self._global_version_seen == graph.global_version:
            return True
        self._global_version_seen = graph.global_version

        # Thread-safe running tracking
        self._set_running_in_current_thread(True)

        # Skip recompute if nothing changed in sources
        if not force and self._version > 0 and not graph.needs_to_recompute(self):
            self._set_running_in_current_thread(False)
            return True

        prev = graph.set_active_consumer(self)
        try:
            graph.prepare_sources(self)
            try:
                self._dependencies.clear()
                value = self._fn()
                # equality check
                if (
                    self._equal is not None
                    and self._version > 0
                    and not (self._flags & graph.HAS_ERROR)
                ):
                    old_value = cast(T, self._value)
                    try:
                        if self._equal(old_value, value):
                            # Update internal value without bumping version
                            self._value = value
                            # clear previous error if any
                            self._flags &= ~graph.HAS_ERROR
                            self._last_error = None
                        else:
                            self._value = value
                            self._version += 1
                            self._flags &= ~graph.HAS_ERROR
                            self._last_error = None
                    except Exception as e:
                        debug_log(f"Error in custom equality check: {e}")
                        self._value = value
                        self._version += 1
                        self._flags &= ~graph.HAS_ERROR
                        self._last_error = None
                else:
                    # default identity equality: bump only when identity changes
                    if not (
                        self._version > 0
                        and not (self._flags & graph.HAS_ERROR)
                        and self._value is value
                    ):
                        self._value = value
                        self._version += 1
                        self._flags &= ~graph.HAS_ERROR
                        self._last_error = None
            except BaseException as err:  # sticky error until next recompute attempt
                self._last_error = err
                self._flags |= graph.HAS_ERROR
                self._value = err  # for debug repr
                self._version += 1
        finally:
            graph.cleanup_sources(self)
            graph.set_active_consumer(prev)
            # Remove current thread from running state (thread-safe cleanup)
            self._set_running_in_current_thread(False)
        # After recompute, capture current sources as dependencies for tests
        deps = set()
        node = self._sources
        while node is not None:
            deps.add(node.source)
            node = node.next_source
        self._dependencies = deps
        return True

    def _notify(self) -> None:
        if not (self._flags & graph.NOTIFIED):
            self._flags |= graph.OUTDATED | graph.NOTIFIED
            # schedule recompute; dependents will be notified only if version changes
            _sched.enqueue_computed(self)

    def get(self) -> T:
        # Thread-safe circular dependency detection
        if self._is_running_in_current_thread():
            raise RuntimeError("Circular dependency detected")

        # Use lock to protect the refresh operation only when thread safety is enabled
        if self._computation_lock is not None:
            with self._computation_lock:
                self._refresh()
        else:
            self._refresh()

        # participate as producer if someone depends on us
        edge = graph.add_dependency(self)
        if edge is not None:
            edge.version = self._version
        if self._flags & graph.HAS_ERROR:
            assert self._last_error is not None
            raise self._last_error
        return self._value  # type: ignore[return-value]

    def set(self, new_value: T) -> None:
        raise AttributeError("Cannot manually set value of ComputeSignal")


Computed = ComputeSignal
