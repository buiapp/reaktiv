"""Reaktiv Core Module."""

import asyncio
import contextvars
import traceback
import inspect
import warnings
from typing import (
    Generic,
    TypeVar,
    Optional,
    Callable,
    Coroutine,
    Set,
    Protocol,
    Union,
    Deque,
    List,
    Tuple,
    ContextManager,
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
    """Enable or disable debug logging."""
    global _debug_enabled
    _debug_enabled = enabled


def debug_log(msg: str) -> None:
    """Log a debug message if debugging is enabled and not suppressed."""
    if _debug_enabled and not _suppress_debug:
        print(f"[REAKTIV DEBUG] {msg}")


# --------------------------------------------------
# Global State Management
# --------------------------------------------------

_batch_depth = 0
_processing_batch = False  # Flag to track when we're processing batch notifications
_sync_effect_queue: Set["Effect"] = set()
_async_effect_queue: Set["Effect"] = set()
_deferred_computed_queue: Deque["ComputeSignal"] = deque()
_deferred_signal_notifications: List[Tuple["Signal", List["Subscriber"]]] = []
_computation_stack: contextvars.ContextVar[List["ComputeSignal"]] = (
    contextvars.ContextVar("computation_stack", default=[])
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
    debug_log(f"Batch started, depth now: {_batch_depth}")
    try:
        yield
    finally:
        _batch_depth -= 1
        debug_log(f"Batch ending, depth now: {_batch_depth}")
        if _batch_depth == 0:
            # Increment the update cycle counter ONLY when the outermost batch completes
            _current_update_cycle += 1
            debug_log(
                f"Batch finished, incremented update cycle to: {_current_update_cycle}"
            )
            # Set processing flag to ensure computed signals defer notifications
            global _processing_batch
            _processing_batch = True
            try:
                # Process all deferred operations in the correct order for glitch-free behavior
                debug_log("Processing batch completion - starting deferred operations")
                _process_deferred_notifications()
                _process_deferred_computed()
                _process_sync_effects()
                _process_async_effects()
                debug_log("Batch completion finished")
            finally:
                _processing_batch = False


def _process_deferred_notifications() -> None:
    """Process all deferred signal notifications from the batch."""
    global _deferred_signal_notifications
    if _batch_depth > 0:
        return

    # Copy the list to avoid issues if new notifications are added during processing
    notifications = _deferred_signal_notifications
    _deferred_signal_notifications = []

    # Collect all unique subscribers to avoid duplicate notifications
    unique_subscribers = set()
    for signal, subscribers in notifications:
        debug_log(
            f"Processing deferred notifications for signal: {signal} to {len(subscribers)} subscribers"
        )
        for subscriber in subscribers:
            unique_subscribers.add(subscriber)

    # Notify each subscriber only once
    for subscriber in unique_subscribers:
        subscriber.notify()


def _process_deferred_computed() -> None:
    global _deferred_computed_queue
    if _batch_depth > 0:
        return

    # Track all non-computed subscribers that need notification at the end
    final_subscribers_to_notify = set()

    # Process computed signals level by level until queue is empty
    while _deferred_computed_queue:
        # Take one computed signal at a time to ensure proper ordering
        computed = _deferred_computed_queue.popleft()
        debug_log(
            f"Processing deferred computed signal: {computed} with {len(computed._subscribers)} subscribers"
        )

        # Only process if there are subscribers and not currently computing
        if computed._subscribers and not computed._computing:
            # Check if any dependencies have actually changed
            # If the signal is not dirty, we don't need to recompute it
            if computed._dirty:
                old_value = computed._value

                try:
                    new_value = computed.get()  # This will trigger _compute() if dirty

                    # Use proper equality checking (respecting custom equality functions)
                    has_changed = True  # Default to assume changed
                    if computed._equal is not None:
                        # Use custom equality function if provided
                        try:
                            has_changed = (
                                not computed._equal(old_value, new_value)
                                if old_value is not None and new_value is not None
                                else True
                            )
                        except Exception as e:
                            debug_log(
                                f"Error in custom equality check during batch processing: {e}"
                            )
                            # Default to changed on error
                    else:
                        # Default to identity comparison
                        has_changed = old_value is not new_value

                    if has_changed:
                        debug_log(
                            f"Deferred computed signal {computed} value changed, notifying subscribers"
                        )
                        # Notify subscribers immediately - computed signals will re-queue themselves
                        for subscriber in computed._subscribers:
                            debug_log(f"Notifying subscriber: {subscriber}")
                            # Use isinstance for robust type checking instead of hasattr
                            if isinstance(subscriber, ComputeSignal):
                                # Computed signals get immediate notification (may re-queue)
                                subscriber.notify()
                            else:
                                # Non-computed subscribers (effects, etc.) get deferred
                                final_subscribers_to_notify.add(subscriber)
                    else:
                        debug_log(
                            f"Deferred computed signal {computed} value unchanged by equality function, no notifications"
                        )

                except Exception as e:
                    debug_log(f"Exception during deferred computed processing: {e}")
                    # On error, only notify if we were previously in a valid state
                    # This maintains consistency with normal computation error handling
                    for subscriber in computed._subscribers:
                        if isinstance(subscriber, ComputeSignal):
                            subscriber.notify()
                        else:
                            final_subscribers_to_notify.add(subscriber)
            else:
                # Signal is not dirty, which means none of its dependencies changed
                # No need to notify subscribers
                debug_log(
                    f"Deferred computed signal {computed} is not dirty, no need to recompute or notify"
                )

    # Notify all non-computed subscribers exactly once at the end
    for subscriber in final_subscribers_to_notify:
        debug_log(f"Notifying final subscriber: {subscriber}")
        subscriber.notify()


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


def _process_async_effects() -> None:
    """Process async effects by creating tasks for each unique effect in the queue."""
    global _async_effect_queue
    if _batch_depth > 0:
        return

    # Create tasks for all queued async effects
    async_effects = list(_async_effect_queue)
    _async_effect_queue.clear()

    for effect in async_effects:
        if not effect._disposed and not effect._executing:
            debug_log(f"Creating async task for batched effect: {effect}")
            effect._async_task = asyncio.create_task(effect._run_effect_func_async())


# --------------------------------------------------
# Reactive Core
# --------------------------------------------------

T = TypeVar("T")


class DependencyTracker(Protocol):
    """Protocol for objects that can track dependencies on signals."""

    def add_dependency(self, signal: "Signal") -> None:
        """Add a dependency on a signal, subscribing to it if not already subscribed."""
        ...


class Subscriber(Protocol):
    """Protocol for objects that can subscribe to signals and receive notifications."""

    def notify(self) -> None:
        """Notify the subscriber of a change in dependencies or signal value."""
        ...


_current_effect: contextvars.ContextVar[Optional[DependencyTracker]] = (
    contextvars.ContextVar("_current_effect", default=None)
)


def untracked(
    func_or_signal: Union[Callable[[], T], "Signal[T]", None] = None,
) -> Union[T, ContextManager[None]]:
    """Execute a function without creating dependencies on accessed signals, get a signal's value without creating a dependency, or create an untracked context.

    Args:
        func_or_signal: Either a function to execute, a signal to read, or None for context manager usage.

    Examples:
        # Using with a signal directly
        counter = Signal(0)
        value = untracked(counter)  # Read without tracking

        # Using with a function
        value = untracked(lambda: counter() * 2)  # Execute without tracking

        # Using as a context manager
        with untracked():
            value = counter()  # Read without tracking
            other_value = other_signal()  # Also read without tracking

    Returns:
        The result of the function, the signal's value, or a context manager.
    """
    if func_or_signal is None:
        # Return a context manager
        @contextmanager
        def untracked_context():
            token = _current_effect.set(None)
            try:
                yield
            finally:
                _current_effect.reset(token)

        return untracked_context()

    token = _current_effect.set(None)
    try:
        if isinstance(func_or_signal, Signal):
            # If a signal is passed, return its value without tracking
            return func_or_signal._value
        else:
            # If a function is passed, execute it without tracking
            return func_or_signal()
    finally:
        _current_effect.reset(token)


class Signal(Generic[T]):
    """Reactive signal container that tracks dependent effects and computed signals."""

    def __init__(self, value: T, *, equal: Optional[Callable[[T, T], bool]] = None):
        """Initialize a Signal with an initial value and an optional custom equality function."""
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
        """Get the current value of the signal, adding a dependency if in an effect context."""
        tracker = _current_effect.get(None)
        if tracker is not None:
            tracker.add_dependency(self)
            debug_log(f"Signal get() called, dependency added for tracker: {tracker}")
        debug_log(f"Signal get() returning value: {self._value}")
        return self._value

    def set(self, new_value: T) -> None:
        """Set a new value for the signal, notifying subscribers if the value has changed."""
        global _current_update_cycle, _deferred_signal_notifications
        debug_log(
            f"Signal set() called with new_value: {new_value} (old_value: {self._value})"
        )

        # Check if this set() is being called during a ComputeSignal's computation
        computation_stack = _computation_stack.get()
        if computation_stack:
            # There's at least one ComputeSignal computing right now
            caller_compute = computation_stack[
                -1
            ]  # The most recent ComputeSignal in the stack

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
                    debug_log(
                        "Signal set() - new_value considered equal by custom equality function; no update."
                    )
                    should_update = False
            except Exception as e:
                debug_log(f"Error in custom equality check during set: {e}")
                # Defaulting to update on error
        elif self._value is new_value:  # Use 'is' for default identity check
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
            debug_log(
                f"Signal set() incremented update cycle to: {_current_update_cycle}"
            )

        # Use list() to avoid issues if subscribers change during iteration
        subscribers_to_notify = list(self._subscribers)

        if _batch_depth > 0:
            # In batch mode, defer notifications until the batch completes
            debug_log(
                f"Signal set() inside batch, deferring notifications for {len(subscribers_to_notify)} subscribers"
            )
            if subscribers_to_notify:
                _deferred_signal_notifications.append((self, subscribers_to_notify))
        else:
            # Outside batch, notify subscribers immediately
            debug_log(
                f"Signal set() outside batch, notifying {len(subscribers_to_notify)} subscribers immediately"
            )
            for subscriber in subscribers_to_notify:
                # Check if subscriber is still valid (WeakSet might have removed it)
                if subscriber in self._subscribers:
                    debug_log(f"Notifying direct subscriber: {subscriber}")
                    subscriber.notify()

            # If this set() call is the outermost operation (not within a batch),
            # process effects immediately after notifying direct subscribers and their consequences.
            debug_log(
                "Signal set() is top-level trigger, processing deferred computed and sync effects."
            )
            _process_deferred_computed()  # Process any computed signals dirtied by this set
            _process_sync_effects()  # Process any effects dirtied by this set or computed signals
            _process_async_effects()

    def update(self, update_fn: Callable[[T], T]) -> None:
        """Update the signal's value using a function that receives the current value."""
        self.set(update_fn(self._value))

    def subscribe(self, subscriber: Subscriber) -> None:
        """Subscribe a subscriber to this signal."""
        self._subscribers.add(subscriber)
        debug_log(f"Subscriber {subscriber} added to Signal.")

    def unsubscribe(self, subscriber: Subscriber) -> None:
        """Unsubscribe a subscriber from this signal."""
        self._subscribers.discard(subscriber)
        debug_log(f"Subscriber {subscriber} removed from Signal.")


class ComputeSignal(Signal[T], DependencyTracker, Subscriber):
    """Computed signal that derives value from other signals."""

    def __init__(
        self,
        compute_fn: Callable[[], T],
        *,
        equal: Optional[Callable[[T, T], bool]] = None,
    ):
        """Initialize a ComputeSignal with a computation function."""
        self._compute_fn = compute_fn
        self._dependencies: Set[Signal] = set()
        self._computing = False
        self._dirty = True  # Mark as dirty initially
        self._initialized = False  # Track if initial computation has been done
        self._notifying = False  # Flag to prevent notification loops
        self._last_error: Optional[Exception] = None  # Track last error

        super().__init__(None, equal=equal)  # type: ignore
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
        """Get the computed value, computing it if necessary."""
        if self._dirty or not self._initialized:
            debug_log(
                "ComputeSignal get() - First access or dirty state, computing value."
            )
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
            except Exception:
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
                        has_changed = (
                            not self._equal(old_value, new_value)
                            if old_value is not None and new_value is not None
                            else True
                        )
                    except Exception as e:
                        debug_log(f"Error in custom equality check: {e}")
                else:
                    # Default to identity comparison
                    has_changed = old_value is not new_value

                if has_changed:
                    debug_log(
                        "ComputeSignal value considered changed, queuing subscriber notifications."
                    )
                    self._queue_notifications()
                else:
                    debug_log(
                        "ComputeSignal value not considered changed, no subscriber notifications."
                    )

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
        """Queue notifications to be processed after batch completion."""
        if self._notifying or self._computing:
            debug_log(
                "ComputeSignal avoiding notification while computing or in notification loop"
            )
            return

        if _batch_depth > 0:
            debug_log("ComputeSignal deferring notifications until batch completion")
            _deferred_computed_queue.append(self)
        else:
            self._notify_subscribers()

    def _notify_subscribers(self):
        """Notify all subscribers of this ComputeSignal."""
        debug_log(f"ComputeSignal notifying {len(self._subscribers)} subscribers")
        self._notifying = True
        try:
            for subscriber in list(self._subscribers):
                subscriber.notify()
        finally:
            self._notifying = False

    def add_dependency(self, signal: Signal) -> None:
        """Add a dependency on a signal, subscribing to it if not already subscribed."""
        self._dependencies.add(signal)
        debug_log(f"ComputeSignal add_dependency() called with signal: {signal}")

    def notify(self) -> None:
        """Notify the ComputeSignal of a change in dependencies."""
        debug_log("ComputeSignal notify() received. Marking as dirty.")
        if self._computing:
            debug_log(
                "ComputeSignal notify() - Ignoring notification during computation."
            )
            return

        # Mark as dirty so we recompute on next access
        self._dirty = True

        # For glitch-free behavior, defer notifications when:
        # 1. We're in a batch (as before)
        # 2. We have a custom equality function that might prevent unnecessary updates
        debug_log(f"ComputeSignal notify() has {len(self._subscribers)} subscribers")
        if self._subscribers:
            if _batch_depth > 0 or _processing_batch:
                debug_log(
                    "ComputeSignal deferring notifications until batch completion"
                )
                _deferred_computed_queue.append(self)
            elif self._equal is not None:
                debug_log(
                    "ComputeSignal deferring notifications for custom equality check"
                )
                _deferred_computed_queue.append(self)
            else:
                debug_log("ComputeSignal notifying subscribers immediately")
                self._notify_subscribers()

    def set(self, new_value: T) -> None:
        """Attempting to set a value on a ComputeSignal is not allowed."""
        raise AttributeError(
            "Cannot manually set value of ComputeSignal - update dependencies instead"
        )

    def _detect_cycle(self, visited: Optional[Set["ComputeSignal"]] = None) -> bool:
        """Return True if a circular dependency (cycle) is detected in the dependency graph."""
        if visited is None:
            visited = set()
        if self in visited:
            return True
        visited.add(self)
        for dep in self._dependencies:
            if isinstance(dep, ComputeSignal):
                if dep._detect_cycle(
                    visited.copy()
                ):  # Use a copy to avoid modifying the original
                    return True
        return False


# Create an alias for ComputeSignal
Computed = ComputeSignal


class Effect(DependencyTracker, Subscriber):
    """Reactive effect that tracks signal dependencies."""

    def __init__(self, func: Callable[..., Union[None, Coroutine[None, None, None]]]):
        """Initialize the effect with a function to run when dependencies change."""
        self._func = func
        self._dependencies: Set[Signal] = set()
        self._disposed = False
        self._new_dependencies: Optional[Set[Signal]] = None
        self._is_async = asyncio.iscoroutinefunction(func)
        self._dirty = False
        self._cleanups: Optional[List[Callable[[], None]]] = None
        self._executing = False  # Flag to prevent recursive/concurrent runs
        self._async_task: Optional[asyncio.Task] = (
            None  # To manage the async task if needed
        )
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
        """DEPRECATED: Effects are now automatically scheduled when created.

        This method is kept for backward compatibility and will be removed in a future version.
        """
        warnings.warn(
            "schedule() is deprecated and will be removed in a future version. Effects are now automatically scheduled when created.",
            DeprecationWarning,
            stacklevel=2,
        )

    def add_dependency(self, signal: Signal) -> None:
        """Add a dependency on a signal, subscribing to it if not already subscribed."""
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
        """Notify the effect of a change in dependencies."""
        global _current_update_cycle
        debug_log(
            f"Effect notify() called during update cycle {_current_update_cycle}."
        )

        if self._disposed:
            debug_log("Effect is disposed, ignoring notify().")
            return

        if self._is_async:
            # Queue async effect for batched processing
            if not self._executing:
                debug_log("Queueing async effect for batched processing.")
                _async_effect_queue.add(self)
            else:
                debug_log("Async effect already running, notify() skipped queueing.")
        else:
            # Mark sync effect as dirty for processing later
            self._mark_dirty()

    def _mark_dirty(self):
        # This should only be called for SYNC effects now
        if self._is_async:
            debug_log("ERROR: _mark_dirty called on async effect.")  # Should not happen
            return
        if not self._dirty:
            self._dirty = True
            _sync_effect_queue.add(self)
            debug_log("Sync effect marked as dirty and added to queue.")

    async def _run_effect_func_async(self) -> None:
        # Combined checks for disposed and executing
        if self._disposed or self._executing:
            debug_log(
                f"Async effect execution skipped: disposed={self._disposed}, executing={self._executing}"
            )
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
                    await self._func(on_cleanup)  # type: ignore
                else:
                    await self._func()  # type: ignore
            except asyncio.CancelledError:
                debug_log("Async effect task cancelled.")
                # Run new cleanups immediately if cancelled
                for cleanup in current_cleanups:
                    try:
                        cleanup()
                    except Exception:
                        traceback.print_exc()
                raise  # Re-raise CancelledError
            except Exception:
                exception_occurred = True
                traceback.print_exc()
                debug_log("Effect function raised an exception during async execution.")
            finally:
                _current_effect.reset(token)

            # Check disposed again *after* await, as effect might be disposed during await
            if self._disposed:
                debug_log(
                    "Effect disposed during async execution, skipping dependency update."
                )
                # Run new cleanups immediately if disposed during execution
                for cleanup in current_cleanups:
                    try:
                        cleanup()
                    except Exception:
                        traceback.print_exc()
                return  # Skip dependency management and storing cleanups

            self._cleanups = current_cleanups

            # Update dependencies - use the new dependencies if available,
            # otherwise maintain the existing dependencies to preserve subscriptions
            # when exceptions occur (similar to sync effect implementation)
            if (
                not exception_occurred
                and self._new_dependencies is not None
                and len(self._new_dependencies) > 0
            ):
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
                debug_log(
                    "Exception occurred or no new dependencies tracked in async effect, maintaining existing dependencies"
                )

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
            debug_log(
                "ERROR: _execute_sync called on async effect."
            )  # Should not happen
            return

        # Only check if disposed or not dirty - remove _executing check to allow loops
        if self._disposed or not self._dirty:
            debug_log(
                f"Sync effect execution skipped: disposed={self._disposed}, dirty={self._dirty}"
            )
            return

        # Track that we're executing but don't prevent re-execution
        was_executing = self._executing
        self._executing = True
        self._dirty = False  # Mark as not dirty since we are running it now
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
                debug_log(
                    "Effect disposed during sync execution, skipping dependency update."
                )
                # Run new cleanups immediately if disposed during execution
                for cleanup in current_cleanups:
                    try:
                        cleanup()
                    except Exception:
                        traceback.print_exc()
                return  # Skip dependency management and storing cleanups

            self._cleanups = current_cleanups

            # Update dependencies - use the new dependencies if available,
            # otherwise maintain the existing dependencies to preserve subscriptions
            # even when exceptions occur
            if (
                not exception_occurred
                and self._new_dependencies is not None
                and len(self._new_dependencies) > 0
            ):
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
                debug_log(
                    "Exception occurred or no new dependencies tracked, maintaining existing dependencies"
                )

            # Always clear new_dependencies for next run regardless of what happened
            self._new_dependencies = None

            debug_log("Sync effect dependency update complete.")

        finally:
            # Only restore previous executing state if we weren't already executing
            # This ensures nested executions can complete properly
            if not was_executing:
                self._executing = False
            debug_log("Sync effect execution finished.")

    def dispose(self) -> None:
        """Dispose of the effect, cleaning up resources and unsubscribing from dependencies."""
        debug_log("Effect dispose() called.")
        if self._disposed:
            return

        self._disposed = True  # Set disposed flag early

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


def computed(
    compute_fn: Callable[[], T], *, equal: Optional[Callable[[T, T], bool]] = None
) -> ComputeSignal[T]:
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
