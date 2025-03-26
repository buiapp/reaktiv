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
from contextlib import contextmanager

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

@contextmanager
def batch():
    """Batch multiple signal updates together, deferring computations and effects until completion."""
    global _batch_depth
    _batch_depth += 1
    try:
        yield
    finally:
        _batch_depth -= 1
        if _batch_depth == 0:
            _process_deferred_computed()
            _process_sync_effects()

def _process_deferred_computed() -> None:
    global _deferred_computed_queue
    if _batch_depth > 0:
        return
    while _deferred_computed_queue:
        computed = _deferred_computed_queue.popleft()
        computed._notify_subscribers()

def _process_sync_effects() -> None:
    global _sync_effect_queue
    if _batch_depth > 0:
        return
    while _sync_effect_queue:
        effects = list(_sync_effect_queue)
        _sync_effect_queue.clear()
        for effect in effects:
            if not effect._disposed and effect._dirty:
                effect._execute_sync()

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

def untracked(func: Callable[[], T]) -> T:
    """Execute a function without creating dependencies on accessed signals."""
    token = _current_effect.set(None)
    try:
        return func()
    finally:
        _current_effect.reset(token)

class Signal(Generic[T]):
    """Reactive signal container that tracks dependent effects and computed signals."""
    def __init__(self, value: T, *, equal: Optional[Callable[[T, T], bool]] = None):
        self._value = value
        self._subscribers: WeakSet[Subscriber] = WeakSet()
        self._equal = equal  # Store the custom equality function
        debug_log(f"Signal initialized with value: {value}")
    
    def __call__(self) -> T:
        """Allow signals to be called directly to get their value."""
        return self.get()

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
        
        # Use custom equality function if provided, otherwise use == operator
        if self._equal is not None:
            # Use custom equality function
            if self._equal(self._value, new_value):
                debug_log("Signal set() - new_value considered equal by custom equality function; no update.")
                return
        else:
            # use identity check for equality
            if self._value is new_value:
                debug_log("Signal set() - new_value is identical to old_value; no update.")
                return
            
        self._value = new_value
        debug_log(f"Signal value updated to: {new_value}, notifying subscribers.")
        
        _batch_depth += 1
        try:
            for subscriber in list(self._subscribers):
                debug_log(f"Notifying direct subscriber: {subscriber}")
                subscriber.notify()
            _process_deferred_computed()
        finally:
            _batch_depth -= 1
            if _batch_depth == 0:
                _process_deferred_computed()  # Process deferred computed signals after updates
                _process_sync_effects()

    def update(self, update_fn: Callable[[T], T]) -> None:
        """Update the signal's value using a function that receives the current value."""
        self.set(update_fn(self._value))

    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.add(subscriber)
        debug_log(f"Subscriber {subscriber} added to Signal.")

    def unsubscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.discard(subscriber)
        debug_log(f"Subscriber {subscriber} removed from Signal.")

class ComputeSignal(Signal[T], DependencyTracker, Subscriber):
    """Computed signal that derives value from other signals with error handling."""
    def __init__(self, compute_fn: Callable[[], T], default: Optional[T] = None, *, equal: Optional[Callable[[T, T], bool]] = None):
        self._compute_fn = compute_fn
        self._default = default
        self._dependencies: Set[Signal] = set()
        self._computing = False
        self._dirty = True  # Mark as dirty initially
        self._initialized = False  # Track if initial computation has been done
        self._notifying = False  # Flag to prevent notification loops
        
        super().__init__(default, equal=equal)
        self._value = default  # type: ignore
        debug_log(f"ComputeSignal initialized with default value: {default} and compute_fn: {compute_fn}")

    def get(self) -> T:
        if self._dirty or not self._initialized:
            debug_log("ComputeSignal get() - First access or dirty state, computing value.")
            self._compute()
            self._initialized = True
            self._dirty = False
        return super().get()

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
            except Exception:
                traceback.print_exc()
                debug_log("ComputeSignal encountered an exception during computation. Using default value.")
                new_value = self._default
            finally:
                _current_effect.reset(tracker_token)

            # Always update the internal value with the new computed result
            old_value = self._value
            self._value = new_value

            # Notify subscribers if the value has changed or if the default value is used
            has_changed = old_value != new_value

            if has_changed:
                debug_log(f"ComputeSignal value considered changed, queuing subscriber notifications.")
                self._queue_notifications()
            else:
                debug_log(f"ComputeSignal value not considered changed, no subscriber notifications.")

            # Update dependencies
            for signal in old_deps - self._dependencies:
                signal.unsubscribe(self)
                debug_log(f"ComputeSignal unsubscribed from old dependency: {signal}")
            for signal in self._dependencies - old_deps:
                signal.subscribe(self)
                debug_log(f"ComputeSignal subscribed to new dependency: {signal}")

            # Circular Dependency Detection
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
            self._dirty = False  # Ensure dirty flag is reset after computation
            debug_log("ComputeSignal _compute() completed.")
            _computation_stack.reset(token)

    def _queue_notifications(self):
        """Queue notifications to be processed after batch completion"""
        if self._notifying:
            debug_log("ComputeSignal avoiding notification loop")
            return
            
        if _batch_depth > 0:
            debug_log("ComputeSignal deferring notifications until batch completion")
            _deferred_computed_queue.append(self)
        else:
            self._notify_subscribers()

    def _notify_subscribers(self):
        """Immediately notify subscribers"""
        debug_log(f"ComputeSignal notifying {len(self._subscribers)} subscribers")
        self._notifying = True
        try:
            for subscriber in list(self._subscribers):
                subscriber.notify()
        finally:
            self._notifying = False

    def add_dependency(self, signal: Signal) -> None:
        self._dependencies.add(signal)
        debug_log(f"ComputeSignal add_dependency() called with signal: {signal}")

    def notify(self) -> None:
        debug_log("ComputeSignal notify() received. Marking as dirty.")
        if self._computing:
            debug_log("ComputeSignal notify() - Ignoring notification during computation.")
            return
            
        # Mark as dirty so we recompute on next access
        was_dirty = self._dirty
        self._dirty = True
        
        # Only proceed if we weren't already dirty and we have subscribers
        if not was_dirty and self._subscribers:
            # If we have custom equality, we need to compute now to determine if we should notify
            if self._equal is not None:
                # Store old value before computing
                old_value = self._value
                
                # Clear the internal dirty flag and compute the new value
                # but don't allow it to queue additional notifications
                self._dirty = False
                self._computing = True
                try:
                    self._compute()  # Updates internal value, but won't queue notifications due to _computing=True
                finally:
                    self._computing = False
                    
                # Now manually check if we should notify based on custom equality
                new_value = self._value  # Get the updated value after _compute
                should_notify = True  # Default to notifying
                
                try:
                    if old_value is not None and new_value is not None:
                        # Only notify if values differ according to custom equality
                        if self._equal(old_value, new_value):
                            debug_log("ComputeSignal values equal according to custom equality, suppressing notification")
                            should_notify = False
                        else:
                            debug_log("ComputeSignal values differ according to custom equality, will notify")
                except Exception as e:
                    debug_log(f"Error in custom equality check: {e}")
                
                # Only queue notification if the values differ according to custom equality
                if should_notify:
                    # Use standard notification procedure
                    if _batch_depth > 0:
                        debug_log("ComputeSignal deferring notifications until batch completion")
                        _deferred_computed_queue.append(self)
                    else:
                        self._notify_subscribers()
            else:
                # No custom equality, use standard notification procedure
                if _batch_depth > 0:
                    debug_log("ComputeSignal deferring notifications until batch completion")
                    _deferred_computed_queue.append(self)
                else:
                    self._notify_subscribers()

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
                if dep._detect_cycle(visited.copy()):  # Use a copy to avoid modifying the original
                    return True
        return False

class Effect(DependencyTracker, Subscriber):
    """Reactive effect that tracks signal dependencies."""
    def __init__(self, func: Callable[[], Union[None, Coroutine[Any, Any, Any]]]):
        self._func = func
        self._dependencies: Set[Signal] = set()
        self._disposed = False
        self._new_dependencies: Optional[Set[Signal]] = None
        self._is_async = asyncio.iscoroutinefunction(func)
        self._executing_sync = False
        self._dirty = False
        self._pending_runs: int = 0
        self._cleanups: Optional[List[Callable[[], None]]] = None
        self._executing = False  # Flag to prevent recursive runs
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
        if self._executing:
            debug_log("Effect is already executing, ignoring notify().")
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
        if self._executing:
            debug_log("Effect is already executing, ignoring schedule().")
            return
        if self._is_async:
            if self._pending_runs == 0:
                self._pending_runs = 1
                asyncio.create_task(self._async_runner())
        else:
            self._mark_dirty()

    def _mark_dirty(self):
        if not self._dirty:
            self._dirty = True
            _sync_effect_queue.add(self)
            debug_log("Effect marked as dirty and added to queue.")
            if _batch_depth == 0:
                _process_sync_effects()

    async def _async_runner(self) -> None:
        while self._pending_runs > 0:
            self._pending_runs = 0
            await self._run_effect_func_async()
            await asyncio.sleep(0)

    async def _run_effect_func_async(self) -> None:
        if self._executing:
            debug_log("Effect is already executing async, skipping.")
            return

        self._executing = True
        try:
            # Run previous cleanups
            if self._cleanups is not None:
                debug_log("Running async cleanup functions")
                for cleanup in self._cleanups:
                    try:
                        cleanup()
                    except Exception:
                        traceback.print_exc()
                self._cleanups = None
    
            self._new_dependencies = set()
            current_cleanups: List[Callable[[], None]] = []
            
            # Prepare on_cleanup argument if needed
            sig = inspect.signature(self._func)
            pass_on_cleanup = len(sig.parameters) >= 1
            
            def on_cleanup(fn: Callable[[], None]) -> None:
                current_cleanups.append(fn)
    
            token = _current_effect.set(self)
            try:
                if pass_on_cleanup:
                    result = self._func(on_cleanup)
                else:
                    result = self._func()
                
                if inspect.isawaitable(result):
                    await result
            except Exception:
                traceback.print_exc()
                debug_log("Effect function raised an exception during async execution.")
            finally:
                _current_effect.reset(token)
            
            self._cleanups = current_cleanups
            
            if self._disposed:
                return
            new_deps = self._new_dependencies or set()
            self._new_dependencies = None
            old_deps = set(self._dependencies)
            for signal in old_deps - new_deps:
                signal.unsubscribe(self)
                debug_log(f"Effect unsubscribed from old dependency: {signal}")
            self._dependencies = new_deps
        finally:
            self._executing = False

    def _execute_sync(self) -> None:
        if self._disposed or not self._dirty or self._executing:
            debug_log("Effect _execute_sync() skipped, not dirty or disposed or already executing.")
            return
        
        self._executing = True
        try:
            # Run previous cleanups
            if self._cleanups is not None:
                debug_log("Running cleanup functions")
                for cleanup in self._cleanups:
                    try:
                        cleanup()
                    except Exception:
                        traceback.print_exc()
                self._cleanups = None
    
            self._dirty = False
            debug_log("Effect _execute_sync() beginning.")
            self._executing_sync = True
            try:
                self._new_dependencies = set()
                current_cleanups: List[Callable[[], None]] = []
                
                # Prepare on_cleanup argument if needed
                sig = inspect.signature(self._func)
                pass_on_cleanup = len(sig.parameters) >= 1
                
                def on_cleanup(fn: Callable[[], None]) -> None:
                    current_cleanups.append(fn)
    
                token = _current_effect.set(self)
                try:
                    if pass_on_cleanup:
                        self._func(on_cleanup)
                    else:
                        self._func()
                except Exception:
                    traceback.print_exc()
                    debug_log("Effect function raised an exception during sync execution.")
                finally:
                    _current_effect.reset(token)
                
                self._cleanups = current_cleanups
                
                if self._disposed:
                    return
                new_deps = self._new_dependencies or set()
                self._new_dependencies = None
                old_deps = set(self._dependencies)
                for signal in old_deps - new_deps:
                    signal.unsubscribe(self)
                    debug_log(f"Effect unsubscribed from old dependency: {signal}")
                self._dependencies = new_deps
            finally:
                self._executing_sync = False
                debug_log("Effect _execute_sync() completed.")
        finally:
            self._executing = False

    def dispose(self) -> None:
        debug_log("Effect dispose() called.")
        if self._disposed:
            return
        
        # Run final cleanups
        if self._cleanups is not None:
            debug_log("Running final cleanup functions")
            for cleanup in self._cleanups:
                try:
                    cleanup()
                except Exception:
                    traceback.print_exc()
            self._cleanups = None
        
        self._disposed = True
        for signal in self._dependencies:
            signal.unsubscribe(self)
        self._dependencies.clear()
        debug_log("Effect dependencies cleared and effect disposed.")

# --------------------------------------------------
# Angular-like API shortcut functions
# --------------------------------------------------

def signal(value: T, *, equal: Optional[Callable[[T, T], bool]] = None) -> Signal[T]:
    """Create a writable signal with the given initial value.
    
    Usage:
        counter = signal(0)
        print(counter())  # Access value: 0
        counter.set(5)    # Set value
        counter.update(lambda x: x + 1)  # Update value
    """
    return Signal(value, equal=equal)

def computed(compute_fn: Callable[[], T], *, equal: Optional[Callable[[T, T], bool]] = None) -> ComputeSignal[T]:
    """Create a computed signal that derives its value from other signals.
    
    Usage:
        count = signal(0)
        doubled = computed(lambda: count() * 2)
        print(doubled())  # Access computed value
    """
    return ComputeSignal(compute_fn, equal=equal)

def effect(func: Callable[[], Union[None, Coroutine[Any, Any, Any]]]) -> Effect:
    """Create an effect that automatically runs when its dependencies change.
    
    The effect is automatically scheduled when created.
    
    Usage:
        count = signal(0)
        effect_instance = effect(lambda: print(f"Count changed: {count()}"))
    """
    effect_instance = Effect(func)
    effect_instance.schedule()  # Auto-schedule the effect immediately
    return effect_instance