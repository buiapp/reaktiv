import asyncio
import contextvars
import traceback
import inspect
from typing import (
    Generic, TypeVar, Optional, Callable,
    Coroutine, Set, Protocol, Any, Union, Deque, List
)
from weakref import WeakSet
from collections import deque

# --------------------------------------------------
# Debugging Helpers
# --------------------------------------------------

_debug_enabled = False
_suppress_debug = False  # When True, debug logging is suppressed

def set_debug(enabled: bool) -> None:
    global _debug_enabled
    _debug_enabled = enabled

def debug_log(msg: str) -> None:
    if _debug_enabled and not _suppress_debug:
        print(f"[REAKTIV DEBUG] {msg}")

# --------------------------------------------------
# Global State Management
# --------------------------------------------------

_batch_depth = 0
_sync_effect_queue: Set['Effect'] = set()
_deferred_computed_queue: Deque['ComputeSignal'] = deque()
_computation_stack: contextvars.ContextVar[List['ComputeSignal']] = contextvars.ContextVar(
    'computation_stack', default=[]
)

# --------------------------------------------------
# Batch Management
# --------------------------------------------------

def process_sync_effects() -> None:
    global _sync_effect_queue
    while _sync_effect_queue:
        effects = list(_sync_effect_queue)
        _sync_effect_queue.clear()
        for effect in effects:
            if not effect._disposed and effect._dirty:
                effect._execute_sync()

def process_deferred_computed() -> None:
    global _deferred_computed_queue
    while _deferred_computed_queue:
        computed = _deferred_computed_queue.popleft()
        computed._notify_subscribers()

# --------------------------------------------------
# Reactive Core
# --------------------------------------------------

T = TypeVar("T")

class DependencyTracker(Protocol):
    def add_dependency(self, signal: 'Signal') -> None: ...

class Subscriber(Protocol):
    def notify(self) -> None: ...

_current_effect: contextvars.ContextVar[Optional[DependencyTracker]] = contextvars.ContextVar(
    "_current_effect", default=None
)

class Signal(Generic[T]):
    """Reactive signal container that tracks dependent effects and computed signals."""
    def __init__(self, value: T):
        self._value = value
        self._subscribers: WeakSet[Subscriber] = WeakSet()
        debug_log(f"Signal initialized with value: {value}")

    def get(self) -> T:
        tracker = _current_effect.get(None)
        if tracker is not None:
            tracker.add_dependency(self)
            debug_log(f"Signal get() called, dependency added for tracker: {tracker}")
        debug_log(f"Signal get() returning value: {self._value}")
        return self._value

    def set(self, new_value: T) -> None:
        global _batch_depth
        debug_log(f"Signal set() called with new_value: {new_value} (old_value: {self._value})")
        if self._value == new_value:
            debug_log("Signal set() - new_value is the same as old_value; no update.")
            return
        self._value = new_value
        debug_log(f"Signal value updated to: {new_value}, notifying subscribers.")
        
        _batch_depth += 1
        try:
            for subscriber in list(self._subscribers):
                debug_log(f"Notifying direct subscriber: {subscriber}")
                subscriber.notify()
            process_deferred_computed()
        finally:
            _batch_depth -= 1
            if _batch_depth == 0:
                process_sync_effects()

    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.add(subscriber)
        debug_log(f"Subscriber {subscriber} added to Signal.")

    def unsubscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.discard(subscriber)
        debug_log(f"Subscriber {subscriber} removed from Signal.")

class ComputeSignal(Signal[T], DependencyTracker, Subscriber):
    """Computed signal that derives value from other signals with error handling."""
    def __init__(self, compute_fn: Callable[[], T], default: Optional[T] = None):
        self._compute_fn = compute_fn
        self._default = default
        self._dependencies: Set[Signal] = set()
        self._computing = False

        super().__init__(default)
        self._value: T = default  # type: ignore
        debug_log(f"ComputeSignal initialized with default value: {default} and compute_fn: {compute_fn}")
        self._compute()

    def _compute(self) -> None:
        debug_log("ComputeSignal _compute() called.")
        stack = _computation_stack.get()
        if self in stack:
            debug_log("ComputeSignal _compute() - Circular dependency detected!")
            raise RuntimeError("Circular dependency detected") from None
        
        token = _computation_stack.set(stack + [self])
        try:
            self._computing = True
            old_deps = set(self._dependencies)
            self._dependencies.clear()

            tracker_token = _current_effect.set(self)
            try:
                new_value = self._compute_fn()
                debug_log(f"ComputeSignal new computed value: {new_value}")
            except RuntimeError as e:
                if "Circular dependency detected" in str(e):
                    raise
                traceback.print_exc()
                debug_log("ComputeSignal encountered an exception during computation.")
                new_value = getattr(self, '_value', self._default)
            except Exception:
                traceback.print_exc()
                debug_log("ComputeSignal encountered an exception during computation.")
                new_value = getattr(self, '_value', self._default)
            finally:
                _current_effect.reset(tracker_token)

            if new_value != self._value:
                self._value = new_value
                debug_log(f"ComputeSignal value updated to: {new_value}, queuing subscriber notifications.")
                self._queue_notifications()

            for signal in old_deps - self._dependencies:
                signal.unsubscribe(self)
                debug_log(f"ComputeSignal unsubscribed from old dependency: {signal}")
            for signal in self._dependencies - old_deps:
                signal.subscribe(self)
                debug_log(f"ComputeSignal subscribed to new dependency: {signal}")

            # --- Circular Dependency Detection ---
            global _suppress_debug
            prev_suppress = _suppress_debug
            _suppress_debug = True
            try:
                if self._detect_cycle():
                    raise RuntimeError("Circular dependency detected") from None
            finally:
                _suppress_debug = prev_suppress
        finally:
            self._computing = False
            debug_log("ComputeSignal _compute() completed.")
            _computation_stack.reset(token)

    def _queue_notifications(self):
        """Queue notifications to be processed after batch completion"""
        if _batch_depth > 0:
            debug_log("ComputeSignal deferring notifications until batch completion")
            _deferred_computed_queue.append(self)
        else:
            self._notify_subscribers()

    def _notify_subscribers(self):
        """Immediately notify subscribers"""
        debug_log(f"ComputeSignal notifying {len(self._subscribers)} subscribers")
        for subscriber in list(self._subscribers):
            subscriber.notify()

    def add_dependency(self, signal: Signal) -> None:
        self._dependencies.add(signal)
        debug_log(f"ComputeSignal add_dependency() called with signal: {signal}")

    def notify(self) -> None:
        debug_log("ComputeSignal notify() received. Triggering re-compute.")
        self._compute()

    def set(self, new_value: T) -> None:
        raise AttributeError("Cannot manually set value of ComputeSignal - update dependencies instead")

    def _detect_cycle(self, visited: Optional[Set['ComputeSignal']] = None) -> bool:
        """Return True if a circular dependency (cycle) is detected in the dependency graph."""
        if visited is None:
            visited = set()
        if self in visited:
            return True
        visited.add(self)
        for dep in self._dependencies:
            if isinstance(dep, ComputeSignal):
                if dep._detect_cycle(visited):
                    return True
        visited.remove(self)
        return False

class Effect(DependencyTracker, Subscriber):
    """Reactive effect that tracks signal dependencies.
    
    Asynchronous effects are scheduled using a pending-run flag so that if a run is already pending,
    additional notifications in the same update are ignored.
    """
    def __init__(self, func: Callable[[], Union[None, Coroutine[Any, Any, Any]]]):
        self._func = func
        self._dependencies: Set[Signal] = set()
        self._disposed = False
        self._new_dependencies: Optional[Set[Signal]] = None
        self._is_async = asyncio.iscoroutinefunction(func)
        self._executing_sync = False
        self._dirty = False
        # For async effects: whether a run is pending (0 = no pending run, 1 = run pending)
        self._pending_runs: int = 0
        debug_log(f"Effect created with func: {func}, is_async: {self._is_async}")

    def add_dependency(self, signal: Signal) -> None:
        if self._disposed:
            return
        if self._new_dependencies is None:
            self._new_dependencies = set()
        if signal not in self._dependencies and signal not in self._new_dependencies:
            signal.subscribe(self)
            debug_log(f"Effect immediately subscribed to new dependency: {signal}")
        self._new_dependencies.add(signal)
        debug_log(f"Effect add_dependency() called, signal: {signal}")

    def notify(self) -> None:
        debug_log("Effect notify() called.")
        if self._disposed:
            debug_log("Effect is disposed, ignoring notify().")
            return
        if self._is_async:
            self.schedule()
        else:
            self._mark_dirty()

    def schedule(self) -> None:
        debug_log("Effect schedule() called.")
        if self._disposed:
            debug_log("Effect is disposed, schedule() ignored.")
            return
        if self._is_async:
            if self._pending_runs == 0:
                self._pending_runs = 1
                asyncio.create_task(self._async_runner())
            # Otherwise, a run is already pending; ignore additional notifications.
        else:
            self._mark_dirty()

    def _mark_dirty(self):
        if not self._dirty:
            self._dirty = True
            _sync_effect_queue.add(self)
            debug_log("Effect marked as dirty and added to queue.")
            if _batch_depth == 0:
                process_sync_effects()

    async def _async_runner(self) -> None:
        while self._pending_runs > 0:
            self._pending_runs = 0
            await self._run_effect_func_async()
            await asyncio.sleep(0)

    async def _run_effect_func_async(self) -> None:
        self._new_dependencies = set()
        token = _current_effect.set(self)
        try:
            result = self._func()
            if inspect.isawaitable(result):
                await result
        except Exception:
            traceback.print_exc()
            debug_log("Effect function raised an exception during async execution.")
        finally:
            _current_effect.reset(token)
        if self._disposed:
            return
        new_deps = self._new_dependencies or set()
        self._new_dependencies = None
        for signal in self._dependencies - new_deps:
            signal.unsubscribe(self)
            debug_log(f"Effect unsubscribed from old dependency: {signal}")
        self._dependencies = new_deps

    def _execute_sync(self) -> None:
        if self._disposed or not self._dirty:
            debug_log("Effect _execute_sync() skipped, not dirty or disposed.")
            return
        self._dirty = False
        debug_log("Effect _execute_sync() beginning.")
        self._executing_sync = True
        try:
            self._new_dependencies = set()
            token = _current_effect.set(self)
            try:
                self._func()
            except Exception:
                traceback.print_exc()
                debug_log("Effect function raised an exception during sync execution.")
            finally:
                _current_effect.reset(token)
            if self._disposed:
                return
            new_deps = self._new_dependencies or set()
            self._new_dependencies = None
            for signal in self._dependencies - new_deps:
                signal.unsubscribe(self)
                debug_log(f"Effect unsubscribed from old dependency: {signal}")
            self._dependencies = new_deps
        finally:
            self._executing_sync = False
            debug_log("Effect _execute_sync() completed.")

    def dispose(self) -> None:
        debug_log("Effect dispose() called.")
        if self._disposed:
            return
        self._disposed = True
        for signal in self._dependencies:
            signal.unsubscribe(self)
        self._dependencies.clear()
        debug_log("Effect dependencies cleared and effect disposed.")
