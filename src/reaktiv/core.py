import asyncio
import contextvars
import traceback
import inspect
import warnings
from typing import (
    Generic, TypeVar, Optional, Callable,
    Coroutine, Set, Protocol, Union, Deque, List, Tuple
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
_deferred_signal_notifications: List[Tuple['Signal', List['Subscriber']]] = []
_computation_stack: contextvars.ContextVar[List['ComputeSignal']] = contextvars.ContextVar(
    'computation_stack', default=[]
)

# Track the current update cycle to prevent duplicate effect triggers
_current_update_cycle = 0

# --------------------------------------------------
# Batch Management
# --------------------------------------------------

@contextmanager
def batch():
    """Batch multiple signal updates together, deferring computations and effects until completion."""
    global _batch_depth, _current_update_cycle
    _batch_depth += 1
    # is_outermost_batch = _batch_depth == 1 # Check if this is the start of the outermost batch (useful for debugging)
    try:
        yield
    finally:
        _batch_depth -= 1
        if _batch_depth == 0:
            # Increment the update cycle counter ONLY when the outermost batch completes
            _current_update_cycle += 1
            debug_log(f"Batch finished, incremented update cycle to: {_current_update_cycle}")
            # Process all deferred notifications
            _process_deferred_notifications()
            _process_deferred_computed()
            _process_sync_effects()

def _process_deferred_notifications() -> None:
    """Process all deferred signal notifications from the batch."""
    global _deferred_signal_notifications
    if _batch_depth > 0:
        return
    
    # Copy the list to avoid issues if new notifications are added during processing
    notifications = _deferred_signal_notifications
    _deferred_signal_notifications = []
    
    for signal, subscribers in notifications:
        debug_log(f"Processing deferred notifications for signal: {signal} to {len(subscribers)} subscribers")
        for subscriber in subscribers:
            subscriber.notify()

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
    
    def __repr__(self) -> str:
        """Provide a useful representation (e.g. for Jupyter notebooks) that shows the current value."""
        try:
            return f"Signal(value={repr(self._value)})"
        except Exception as e:
            return f"Signal(error_displaying_value: {str(e)})"
    
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
        global _current_update_cycle, _deferred_signal_notifications
        debug_log(f"Signal set() called with new_value: {new_value} (old_value: {self._value})")

        # Check if this set() is being called during a ComputeSignal's computation
        computation_stack = _computation_stack.get()
        if computation_stack:
            # There's at least one ComputeSignal computing right now
            caller_compute = computation_stack[-1]  # The most recent ComputeSignal in the stack
            
            # Get information about the compute function without using traceback
            try:
                compute_fn_info = f"{caller_compute._compute_fn.__code__.co_filename}:{caller_compute._compute_fn.__code__.co_firstlineno}"
            except Exception:
                compute_fn_info = str(caller_compute._compute_fn)
                
            raise RuntimeError(
                f"Side effect detected: Cannot set Signal from within a ComputeSignal computation.\n"
                f"ComputeSignal should only read signals, not set them.\n"
                f"The offending ComputeSignal was defined at: {compute_fn_info}"
            )

        # Use custom equality function if provided, otherwise use identity check
        should_update = True
        if self._equal is not None:
            try:
                if self._equal(self._value, new_value):
                    debug_log("Signal set() - new_value considered equal by custom equality function; no update.")
                    should_update = False
            except Exception as e:
                 debug_log(f"Error in custom equality check during set: {e}")
                 # Defaulting to update on error
        elif self._value is new_value: # Use 'is' for default identity check
            debug_log("Signal set() - new_value is identical to old_value; no update.")
            should_update = False

        if not should_update:
            return

        self._value = new_value
        debug_log(f"Signal value updated to: {new_value}, notifying subscribers.")

        # Increment update cycle ONLY if this 'set' is the top-level trigger (not inside a batch)
        is_top_level_trigger = _batch_depth == 0
        if is_top_level_trigger:
             _current_update_cycle += 1
             debug_log(f"Signal set() incremented update cycle to: {_current_update_cycle}")

        # Use list() to avoid issues if subscribers change during iteration
        subscribers_to_notify = list(self._subscribers)
        
        if _batch_depth > 0:
            # In batch mode, defer notifications until the batch completes
            debug_log(f"Signal set() inside batch, deferring notifications for {len(subscribers_to_notify)} subscribers")
            if subscribers_to_notify:
                _deferred_signal_notifications.append((self, subscribers_to_notify))
        else:
            # Outside batch, notify subscribers immediately
            debug_log(f"Signal set() outside batch, notifying {len(subscribers_to_notify)} subscribers immediately")
            for subscriber in subscribers_to_notify:
                # Check if subscriber is still valid (WeakSet might have removed it)
                if subscriber in self._subscribers:
                    debug_log(f"Notifying direct subscriber: {subscriber}")
                    subscriber.notify()

            # If this set() call is the outermost operation (not within a batch),
            # process effects immediately after notifying direct subscribers and their consequences.
            debug_log("Signal set() is top-level trigger, processing deferred computed and sync effects.")
            _process_deferred_computed() # Process any computed signals dirtied by this set
            _process_sync_effects()      # Process any effects dirtied by this set or computed signals

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
    """Computed signal that derives value from other signals."""
    def __init__(self, compute_fn: Callable[[], T], *, equal: Optional[Callable[[T, T], bool]] = None):
        self._compute_fn = compute_fn
        self._dependencies: Set[Signal] = set()
        self._computing = False
        self._dirty = True  # Mark as dirty initially
        self._initialized = False  # Track if initial computation has been done
        self._notifying = False  # Flag to prevent notification loops
        self._last_error: Optional[Exception] = None  # Track last error
        
        super().__init__(None, equal=equal) # type: ignore
        debug_log(f"ComputeSignal initialized with compute_fn: {compute_fn}")
    
    def __repr__(self) -> str:
        """Provide a useful representation (e.g. for Jupyter notebooks) that shows the computed value."""
        if self._dirty or not self._initialized:
            # Don't trigger computation just for display purposes
            return "Computed(value=<not computed yet>)"
        
        try:
            value = self._value
            return f"Computed(value={repr(value)})"
        except Exception as e:
            return f"Computed(error_displaying_value: {str(e)})"
    
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
            new_value = None
            exception_occurred = False
            try:
                # Store any dependency that gets tracked during the computation, even if it fails
                new_value = self._compute_fn()
                debug_log(f"ComputeSignal new computed value: {new_value}")
            except Exception as e:
                # Remember that an exception occurred, but don't handle it here
                exception_occurred = True
                # Re-raise the exception after dependency tracking is complete
                raise
            finally:
                _current_effect.reset(tracker_token)

            # Only update the value if no exception occurred
            if not exception_occurred:
                old_value = self._value
                self._value = new_value

                # Check if values have changed based on equality function or identity
                has_changed = True  # Default to assume changed
                if self._equal is not None:
                    # Use custom equality function if provided
                    try:
                        has_changed = not self._equal(old_value, new_value) if old_value is not None and new_value is not None else True
                    except Exception as e:
                        debug_log(f"Error in custom equality check: {e}")
                else:
                    # Default to identity comparison
                    has_changed = old_value is not new_value

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
        finally:
            self._computing = False
            if not exception_occurred:
                self._dirty = False  # Ensure dirty flag is reset after computation only if no exception
            # Always restore the token, whether exception occurred or not
            _computation_stack.reset(token)
            debug_log("ComputeSignal _compute() completed.")

    def _queue_notifications(self):
        """Queue notifications to be processed after batch completion"""
        if self._notifying or self._computing:
            debug_log("ComputeSignal avoiding notification while computing or in notification loop")
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
        
        # Only notify subscribers if we have a custom equality function and need to check equality
        # or if we're transitioning from an error state
        if self._subscribers:
            if self._equal is not None:
                # We need to compute now to check if the value changed according to our custom equality
                old_value = self._value
                
                # Temporarily clear the dirty flag for computation
                self._dirty = False
                self._computing = True
                try:
                    # Try to compute the new value
                    new_value = self._compute_fn()
                    
                    # Always update the internal value
                    self._value = new_value
                    
                    # Check if the values are considered equal by our custom equality function
                    should_notify = True
                    try:
                        if old_value is not None and new_value is not None:
                            if self._equal(old_value, new_value):
                                debug_log("ComputeSignal values equal according to custom equality, suppressing notification")
                                should_notify = False
                    except Exception as e:
                        debug_log(f"Error in custom equality check: {e}")
                    
                    # Only notify if values are not considered equal
                    if should_notify:
                        debug_log("ComputeSignal values differ or error in equality check, will notify subscribers")
                        if _batch_depth > 0:
                            debug_log("ComputeSignal deferring notifications until batch completion")
                            _deferred_computed_queue.append(self)
                        else:
                            self._notify_subscribers()
                    else:
                        # Don't reset dirty flag if we have error, so we recompute next time
                        self._dirty = False
                except Exception:
                    # An exception occurred during computation, restore dirty state
                    debug_log("Exception occurred during ComputeSignal notification check")
                    self._dirty = True
                    # Always notify when transitioning to or from error state
                    if _batch_depth > 0:
                        debug_log("ComputeSignal deferring notifications until batch completion")
                        _deferred_computed_queue.append(self)
                    else:
                        self._notify_subscribers()
                finally:
                    self._computing = False
            else:
                # No custom equality function, always notify
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

# Create an alias for ComputeSignal
Computed = ComputeSignal

class Effect(DependencyTracker, Subscriber):
    """Reactive effect that tracks signal dependencies."""
    def __init__(self, func: Callable[..., Union[None, Coroutine[None, None, None]]]):
        self._func = func
        self._dependencies: Set[Signal] = set()
        self._disposed = False
        self._new_dependencies: Optional[Set[Signal]] = None
        self._is_async = asyncio.iscoroutinefunction(func)
        self._dirty = False
        self._cleanups: Optional[List[Callable[[], None]]] = None
        self._executing = False  # Flag to prevent recursive/concurrent runs
        self._last_update_cycle = -1  # Track the last update cycle when this effect was triggered
        self._async_task: Optional[asyncio.Task] = None # To manage the async task if needed
        debug_log(f"Effect created with func: {func}, is_async: {self._is_async}")
        
        # Automatically schedule the effect upon creation (previously done by schedule())
        if self._is_async:
            # Schedule the initial async run if not already executing
            if not self._executing:
                debug_log("Scheduling initial async effect execution.")
                self._async_task = asyncio.create_task(self._run_effect_func_async())
            else:
                debug_log("Initial async effect schedule skipped, already running.")
        else:
            # Mark sync effect as dirty and process immediately if not in batch
            self._mark_dirty()
            if _batch_depth == 0:
                debug_log("Processing sync effects immediately after initial schedule.")
                _process_sync_effects()
    
    def schedule(self) -> None:
        """
        DEPRECATED: Effects are now automatically scheduled when created.
        
        This method is kept for backward compatibility and will be removed in a future version.
        """
        warnings.warn(
            "schedule() is deprecated and will be removed in a future version. Effects are now automatically scheduled when created.",
            DeprecationWarning, 
            stacklevel=2
        )

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
        global _current_update_cycle
        debug_log(f"Effect notify() called during update cycle {_current_update_cycle}.")

        if self._disposed:
            debug_log("Effect is disposed, ignoring notify().")
            return
        # Removed _executing check here, let the execution methods handle it

        # Check if this effect was already scheduled in the current update cycle
        if self._last_update_cycle == _current_update_cycle:
            debug_log(f"Effect already scheduled in current update cycle {_current_update_cycle}, skipping duplicate notification.")
            return

        # Mark that this effect was scheduled in the current update cycle
        self._last_update_cycle = _current_update_cycle

        if self._is_async:
            # Schedule the async task to run if not already executing
            if not self._executing:
                debug_log("Scheduling async effect execution via notify.")
                self._async_task = asyncio.create_task(self._run_effect_func_async())
            else:
                debug_log("Async effect already running, notify() skipped task creation.")
        else:
            # Mark sync effect as dirty for processing later
            self._mark_dirty()

    def _mark_dirty(self):
        # This should only be called for SYNC effects now
        if self._is_async:
             debug_log("ERROR: _mark_dirty called on async effect.") # Should not happen
             return
        if not self._dirty:
            self._dirty = True
            _sync_effect_queue.add(self)
            debug_log("Sync effect marked as dirty and added to queue.")

    async def _run_effect_func_async(self) -> None:
        # Combined checks for disposed and executing
        if self._disposed or self._executing:
            debug_log(f"Async effect execution skipped: disposed={self._disposed}, executing={self._executing}")
            return

        self._executing = True
        debug_log("Async effect execution starting.")
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
            exception_occurred = False
            try:
                # Directly await the coroutine function
                if pass_on_cleanup:
                    await self._func(on_cleanup) # type: ignore
                else:
                    await self._func() # type: ignore
            except asyncio.CancelledError:
                 debug_log("Async effect task cancelled.")
                 # Run new cleanups immediately if cancelled
                 for cleanup in current_cleanups:
                     try: cleanup()
                     except Exception: traceback.print_exc()
                 raise # Re-raise CancelledError
            except Exception:
                exception_occurred = True
                traceback.print_exc()
                debug_log("Effect function raised an exception during async execution.")
            finally:
                _current_effect.reset(token)

            # Check disposed again *after* await, as effect might be disposed during await
            if self._disposed:
                 debug_log("Effect disposed during async execution, skipping dependency update.")
                 # Run new cleanups immediately if disposed during execution
                 for cleanup in current_cleanups:
                     try: cleanup()
                     except Exception: traceback.print_exc()
                 return # Skip dependency management and storing cleanups

            self._cleanups = current_cleanups

            # Update dependencies - use the new dependencies if available,
            # otherwise maintain the existing dependencies to preserve subscriptions
            # when exceptions occur (similar to sync effect implementation)
            if not exception_occurred and self._new_dependencies is not None and len(self._new_dependencies) > 0:
                new_deps = self._new_dependencies
                old_deps = set(self._dependencies)

                # Unsubscribe from signals that are no longer dependencies
                for signal in old_deps - new_deps:
                    signal.unsubscribe(self)
                    debug_log(f"Effect unsubscribed from old dependency: {signal}")

                # Subscribe to new signals
                for signal in new_deps - old_deps:
                     signal.subscribe(self)
                     debug_log(f"Effect subscribed to new dependency: {signal}")

                self._dependencies = new_deps
            else:
                # If an exception occurred, maintain existing dependencies
                debug_log("Exception occurred or no new dependencies tracked in async effect, maintaining existing dependencies")

            # Always clear new_dependencies for next run regardless of what happened
            self._new_dependencies = None

            debug_log("Async effect dependency update complete.")

        finally:
            self._executing = False
            debug_log("Async effect execution finished.")
            # Clear the task reference once done
            if self._async_task and self._async_task.done():
                 self._async_task = None

    def _execute_sync(self) -> None:
        # This should only be called for SYNC effects
        if self._is_async:
             debug_log("ERROR: _execute_sync called on async effect.") # Should not happen
             return

        # Combined checks
        if self._disposed or not self._dirty or self._executing:
            debug_log(f"Sync effect execution skipped: disposed={self._disposed}, dirty={self._dirty}, executing={self._executing}")
            return

        self._executing = True
        self._dirty = False # Mark as not dirty since we are running it now
        debug_log("Sync effect execution starting.")
        try:
            # Run previous cleanups
            if self._cleanups is not None:
                debug_log("Running sync cleanup functions")
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
            exception_occurred = False
            try:
                # Call the sync function directly
                if pass_on_cleanup:
                    self._func(on_cleanup)
                else:
                    self._func()
            except Exception:
                exception_occurred = True
                traceback.print_exc()
                debug_log("Effect function raised an exception during sync execution.")
            finally:
                _current_effect.reset(token)

            # Check disposed state after execution
            if self._disposed:
                 debug_log("Effect disposed during sync execution, skipping dependency update.")
                 # Run new cleanups immediately if disposed during execution
                 for cleanup in current_cleanups:
                     try: cleanup()
                     except Exception: traceback.print_exc()
                 return # Skip dependency management and storing cleanups

            self._cleanups = current_cleanups

            # Update dependencies - use the new dependencies if available,
            # otherwise maintain the existing dependencies to preserve subscriptions
            # even when exceptions occur
            if not exception_occurred and self._new_dependencies is not None and len(self._new_dependencies) > 0:
                new_deps = self._new_dependencies
                old_deps = set(self._dependencies)

                # Unsubscribe from signals that are no longer dependencies
                for signal in old_deps - new_deps:
                    signal.unsubscribe(self)
                    debug_log(f"Effect unsubscribed from old dependency: {signal}")

                # Subscribe to new signals
                # No need to re-subscribe if already subscribed
                for signal in new_deps - old_deps:
                     signal.subscribe(self)
                     debug_log(f"Effect subscribed to new dependency: {signal}")

                self._dependencies = new_deps
            else:
                # If an exception occurred, maintain existing dependencies
                debug_log("Exception occurred or no new dependencies tracked, maintaining existing dependencies")

            # Always clear new_dependencies for next run regardless of what happened
            self._new_dependencies = None

            debug_log("Sync effect dependency update complete.")

        finally:
            self._executing = False
            debug_log("Sync effect execution finished.")

    def dispose(self) -> None:
        debug_log("Effect dispose() called.")
        if self._disposed:
            return

        self._disposed = True # Set disposed flag early

        # Cancel pending async task if any
        if self._async_task and not self._async_task.done():
            debug_log("Cancelling pending async effect task.")
            self._async_task.cancel()
            # We might want to await the cancellation or handle CancelledError,
            # but for simplicity, we just cancel. Cleanup should handle resource release.

        # Run final cleanups
        if self._cleanups is not None:
            debug_log("Running final cleanup functions")
            for cleanup in self._cleanups:
                try:
                    cleanup()
                except Exception:
                    traceback.print_exc()
            self._cleanups = None

        # Unsubscribe from all dependencies
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
        
    Deprecated:
        Use Signal class directly instead:
        counter = Signal(0)
    """
    # warnings.warn(
    #     "The signal() function is deprecated. Use Signal class directly instead: Signal(value)",
    #     DeprecationWarning, 
    #     stacklevel=2
    # )
    return Signal(value, equal=equal)

def computed(compute_fn: Callable[[], T], *, equal: Optional[Callable[[T, T], bool]] = None) -> ComputeSignal[T]:
    """Create a computed signal that derives its value from other signals.
    
    Usage:
        count = signal(0)
        doubled = computed(lambda: count() * 2)
        print(doubled())  # Access computed value
        
    Deprecated:
        Use Computed class directly instead:
        doubled = Computed(lambda: count() * 2)
    """
    # warnings.warn(
    #     "The computed() function is deprecated. Use Computed class directly instead: Computed(compute_fn)",
    #     DeprecationWarning, 
    #     stacklevel=2
    # )
    return ComputeSignal(compute_fn, equal=equal)

def effect(func: Callable[..., Union[None, Coroutine[None, None, None]]]) -> Effect:
    """Create an effect that automatically runs when its dependencies change.
    
    The effect is automatically scheduled when created.
    
    Usage:
        count = signal(0)
        effect_instance = effect(lambda: print(f"Count changed: {count()}"))
        
    Deprecated:
        Use Effect class directly instead:
        effect_instance = Effect(lambda: print(f"Count changed: {count()}"))
    """
    # warnings.warn(
    #     "The effect() function is deprecated. Use Effect class directly instead: Effect(func)",
    #     DeprecationWarning, 
    #     stacklevel=2
    # )
    effect_instance = Effect(func)
    return effect_instance