"""DEPRECATED: Operators module for reaktiv signals."""

import asyncio
import time
import warnings
from typing import TypeVar, Callable, Generic, Optional, Union, Tuple, Any
from weakref import WeakSet
from .core import (
    Signal,
    ComputeSignal,
    Effect,
    _current_effect,
    Subscriber,
    debug_log,
    _process_sync_effects,
    _batch_depth,
)

T = TypeVar("T")

# --------------------------------------------------
# DEPRECATION NOTICE
# --------------------------------------------------
"""
DEPRECATED: The operators module is deprecated and will be removed in a future version.

After reconsidering the design philosophy of reactive signals, I've decided that signal-based 
state management should NOT have a time dimension, unlike RxJS observables. 

Signals are meant to represent current state values that change over time, but the operators 
in this module (debounce, throttle, filter, etc.) introduce temporal behavior that doesn't 
align with the core concept of signals as state containers.

For time-based operations, consider using:
- Standard async/await patterns
- asyncio utilities (asyncio.sleep, asyncio.wait_for, etc.)
- Custom Effects that implement the temporal logic you need
- External libraries designed for reactive streams (like RxPY) if you need complex temporal operators

The core Signal, Computed, and Effect primitives remain the recommended way to manage 
reactive state without temporal concerns.
"""

# --------------------------------------------------
# Base Class for Operator Signals
# --------------------------------------------------


class _OperatorSignal(Generic[T]):
    """DEPRECATED: A read-only signal produced by an operator.

    This class is deprecated along with all operators as they introduce temporal
    behavior that doesn't align with signal-based state management principles.
    """

    def __init__(
        self, initial_value: T, *, equal: Optional[Callable[[T, T], bool]] = None
    ):
        warnings.warn(
            "_OperatorSignal is deprecated and will be removed in a future version. "
            "Operators introduce temporal behavior that doesn't belong in signal-based state management.",
            DeprecationWarning,
            stacklevel=3,  # Higher stack level since this is typically called from operator functions
        )
        self._value = initial_value
        self._subscribers: WeakSet[Subscriber] = WeakSet()
        self._equal = equal or (
            lambda a, b: a is b
        )  # Default to identity check like Signal
        self._internal_effect: Optional[Effect] = None
        self._disposed = False
        debug_log(f"OperatorSignal initialized with value: {initial_value}")

    def __call__(self) -> T:
        return self.get()

    def get(self) -> T:
        if self._disposed:
            debug_log("Attempted to get value from disposed OperatorSignal")
            # Return last known value
            return self._value

        tracker = _current_effect.get(None)
        if tracker is not None:
            # Track this operator signal itself as a dependency.
            # The tracker's add_dependency method should call our subscribe method.
            # We provide the necessary methods (subscribe/unsubscribe) via duck typing.
            tracker.add_dependency(self)  # type: ignore
            debug_log(
                f"OperatorSignal get() called, dependency added for tracker: {tracker}"
            )

        debug_log(f"OperatorSignal get() returning value: {self._value}")
        return self._value

    def _update_value(self, new_value: T):
        """Internal method to update the value and notify subscribers."""
        if self._disposed:
            return
        debug_log(
            f"OperatorSignal _update_value() called with new_value: {new_value} (old_value: {self._value})"
        )
        if self._equal(self._value, new_value):
            debug_log(
                "OperatorSignal _update_value() - new_value considered equal; no update."
            )
            return

        self._value = new_value
        debug_log(
            f"OperatorSignal value updated to: {new_value}, notifying subscribers."
        )

        # Determine if this update is happening outside a batch
        is_top_level_trigger = _batch_depth == 0
        # No need to increment update cycle here, handled by source/batch

        # Notify own subscribers
        subscribers_to_notify = list(self._subscribers)
        for subscriber in subscribers_to_notify:
            debug_log(f"OperatorSignal notifying subscriber: {subscriber}")
            if hasattr(subscriber, "notify") and callable(subscriber.notify):
                subscriber.notify()
            else:
                debug_log(
                    f"OperatorSignal found invalid subscriber: {subscriber}, removing."
                )
                self._subscribers.discard(subscriber)

        # Process sync effects immediately if this update is not part of a batch
        if is_top_level_trigger:
            debug_log("OperatorSignal update is top-level, processing sync effects.")
            _process_sync_effects()
        else:
            debug_log(
                "OperatorSignal update is inside a batch, deferring effect processing."
            )

    # --- Methods for Duck Typing as a Dependency Source ---

    def subscribe(self, subscriber: Subscriber) -> None:
        """Allows trackers (Effects, ComputeSignals) to subscribe to this signal."""
        if not self._disposed:
            self._subscribers.add(subscriber)
            debug_log(f"Subscriber {subscriber} added to OperatorSignal {self}.")

    def unsubscribe(self, subscriber: Subscriber) -> None:
        """Allows trackers to unsubscribe from this signal."""
        self._subscribers.discard(subscriber)
        debug_log(f"Subscriber {subscriber} removed from OperatorSignal {self}.")

    # --- Methods for Duck Typing for internal _current_effect usage ---
    # These might be called if this signal itself is the tracker (which it isn't)
    # or if the tracker.add_dependency implementation expects them.

    def add_dependency(
        self, signal: Union[Signal, ComputeSignal, "_OperatorSignal"]
    ) -> None:
        """Satisfies DependencyTracker protocol via duck typing. No-op for OperatorSignal."""
        # This signal relies on its internal Effect for tracking *its* sources.
        # It does not track other signals directly via this method.
        debug_log(
            f"OperatorSignal.add_dependency called (likely NO-OP needed): {signal}"
        )
        pass

    def notify(self) -> None:
        """Satisfies Subscriber protocol via duck typing. No-op for OperatorSignal."""
        # This signal is notified by its internal Effect, not directly by its sources.
        debug_log("OperatorSignal.notify called (likely NO-OP needed)")
        pass

    # --- Cleanup ---

    def dispose(self):
        """Clean up the internal effect and resources."""
        debug_log(f"OperatorSignal dispose() called for {self}")
        if self._disposed:
            return
        self._disposed = True
        if self._internal_effect:
            debug_log(f"Disposing internal effect for {self}")
            self._internal_effect.dispose()
            self._internal_effect = None
        # Clear subscribers to release references
        self._subscribers.clear()
        debug_log(f"OperatorSignal {self} disposed.")

    def __del__(self):
        # Attempt cleanup when garbage collected, though explicit dispose() is preferred
        if not self._disposed:
            # Avoid running complex logic or logging in __del__ if possible
            # self.dispose() # Calling dispose() here can be risky
            pass


# --------------------------------------------------
# Operator Functions
# --------------------------------------------------


def filter_signal(
    source: Union[Signal[T], ComputeSignal[T], _OperatorSignal[T]],
    predicate: Callable[[T], bool],
) -> _OperatorSignal[Optional[T]]:
    """DEPRECATED: This function is deprecated and will be removed in a future version.

    Signal-based state management should not have temporal/filtering behavior.
    Consider using a ComputeSignal with conditional logic instead:

    Example:
        filtered = Computed(lambda: source() if predicate(source()) else None)

    Creates a read-only signal that only emits values from the source signal
    that satisfy the predicate function.

    The initial value will be the source's initial value if it passes the predicate.
    If the initial value doesn't pass the predicate, it will still be used as the
    initial state of the returned signal, but no notifications will be triggered
    for this initial value.

    This operator is synchronous and does not require an asyncio event loop.
    """
    warnings.warn(
        "filter_signal is deprecated and will be removed in a future version. "
        "Signal-based state management should not have filtering behavior. "
        "Consider using ComputeSignal with conditional logic instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    # Get initial value without tracking dependency here
    initial_source_value = source.get()
    initial_value_passes = False
    try:
        initial_value_passes = predicate(initial_source_value)
    except Exception as e:
        debug_log(f"Filter predicate failed on initial value: {e}")

    # Determine the correct initial value for the filtered signal
    # If the initial source value passes, use it. Otherwise, use None.
    # We might need a more sophisticated way to handle non-None types later.
    initial_filtered_value = initial_source_value if initial_value_passes else None

    # Create the operator signal instance
    source_equal = getattr(source, "_equal", None)
    # The type checker needs help here as initial_filtered_value can be None
    filtered_sig: _OperatorSignal[Optional[T]] = _OperatorSignal(
        initial_filtered_value, equal=source_equal
    )

    # Define the effect function
    def _run_filter():
        # This effect runs whenever the source changes
        value = source.get()  # Track source as dependency inside effect
        if predicate(value):
            filtered_sig._update_value(value)
        # If predicate is false, we don't update. The signal retains its last valid value.
        # Consider if we should update to None when predicate becomes false?
        # Current behavior: keeps last valid value.

    # Create the internal effect
    internal_effect = Effect(_run_filter)
    filtered_sig._internal_effect = internal_effect

    return filtered_sig


def debounce_signal(
    source: Union[Signal[T], ComputeSignal[T], _OperatorSignal[T]], delay_seconds: float
) -> _OperatorSignal[T]:
    """DEPRECATED: This function is deprecated and will be removed in a future version.

    Signal-based state management should not have temporal behavior like debouncing.
    Consider using asyncio utilities in an Effect instead.

    Creates a read-only signal that emits a value from the source signal
    only after a particular time span has passed without another source emission.

    Note: This operator requires a running asyncio event loop to manage its internal timer.
    """
    warnings.warn(
        "debounce_signal is deprecated and will be removed in a future version. "
        "Signal-based state management should not have temporal behavior. "
        "Consider using asyncio utilities in Effects instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    initial_source_value = source.get()
    source_equal = getattr(source, "_equal", None)
    debounced_sig = _OperatorSignal(initial_source_value, equal=source_equal)

    timer_handle: Optional[asyncio.TimerHandle] = None
    pending_value: Optional[T] = None
    has_pending_value = False

    def _emit_debounced():
        nonlocal timer_handle, has_pending_value, pending_value
        if has_pending_value:
            # Type ignore justification: has_pending_value ensures pending_value is set
            debounced_sig._update_value(pending_value)  # type: ignore
            has_pending_value = False
        timer_handle = None  # Clear handle after firing or cancellation

    # Define the effect function (must be async for timer)
    async def _run_debounce(on_cleanup: Callable[[Callable[[], None]], None]):
        nonlocal timer_handle, pending_value, has_pending_value
        # Capture the latest value from source (tracks dependency)
        current_value = source.get()
        pending_value = current_value
        has_pending_value = True
        debug_log(f"Debounce: captured value {current_value}")

        # Cancel existing timer if any
        if timer_handle:
            debug_log("Debounce: cancelling previous timer")
            timer_handle.cancel()
            timer_handle = None  # Ensure handle is cleared immediately

        # Schedule new timer
        try:
            loop = asyncio.get_running_loop()
            debug_log(f"Debounce: scheduling timer for {delay_seconds}s")
            timer_handle = loop.call_later(delay_seconds, _emit_debounced)
        except RuntimeError:
            debug_log("Debounce: No running event loop found. Cannot schedule timer.")
            pass

        # Cleanup function to cancel timer if effect is destroyed/re-run
        def cleanup():
            nonlocal timer_handle
            if timer_handle:
                debug_log("Debounce: cleanup cancelling timer")
                timer_handle.cancel()
                timer_handle = None

        on_cleanup(cleanup)

    # Create the internal effect
    internal_effect = Effect(_run_debounce)  # Effect detects async automatically
    debounced_sig._internal_effect = internal_effect

    return debounced_sig


def throttle_signal(
    source: Union[Signal[T], ComputeSignal[T], _OperatorSignal[T]],
    interval_seconds: float,
    leading: bool = True,
    trailing: bool = False,
) -> _OperatorSignal[T]:
    """DEPRECATED: This function is deprecated and will be removed in a future version.

    Signal-based state management should not have temporal behavior like throttling.
    Consider using asyncio utilities in an Effect instead.

    Creates a read-only signal that emits a value from the source signal,
    then ignores subsequent source emissions for a specified duration.
    Can optionally emit a trailing value. Uses non-shortcut API.

    Note: This operator requires a running asyncio event loop to manage its internal timer(s).
    """
    warnings.warn(
        "throttle_signal is deprecated and will be removed in a future version. "
        "Signal-based state management should not have temporal behavior. "
        "Consider using asyncio utilities in Effects instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    initial_source_value = source.get()
    source_equal = getattr(source, "_equal", None)
    throttled_sig = _OperatorSignal(initial_source_value, equal=source_equal)

    timer_handle: Optional[asyncio.TimerHandle] = None
    trailing_value: Optional[T] = None
    has_trailing_value = False
    last_emit_time: float = (
        -interval_seconds - 1
    )  # Ensure first emit is allowed if leading

    def _emit_trailing():
        nonlocal timer_handle, has_trailing_value, trailing_value, last_emit_time
        timer_handle = None  # Timer fired or was cancelled
        if trailing and has_trailing_value:
            debug_log(f"Throttle: emitting trailing value {trailing_value}")
            # Type ignore justification: has_trailing_value ensures trailing_value is set
            current_time = time.monotonic()
            throttled_sig._update_value(trailing_value)  # type: ignore
            last_emit_time = current_time  # Update last emit time for trailing emit
            has_trailing_value = False
        # If not trailing or no trailing value, do nothing

    async def _run_throttle(on_cleanup: Callable[[Callable[[], None]], None]):
        nonlocal last_emit_time, timer_handle, trailing_value, has_trailing_value
        current_time = time.monotonic()
        value = source.get()  # Track source dependency
        debug_log(
            f"Throttle: received value {value} at {current_time:.4f} (last emit: {last_emit_time:.4f})"
        )

        if trailing:
            trailing_value = value
            has_trailing_value = True

        def cleanup():
            nonlocal timer_handle
            if timer_handle:
                debug_log("Throttle: cleanup cancelling timer")
                timer_handle.cancel()
                timer_handle = None

        on_cleanup(cleanup)

        time_since_last_emit = current_time - last_emit_time
        is_interval_passed = time_since_last_emit >= interval_seconds

        if is_interval_passed:
            debug_log("Throttle: interval passed")
            if timer_handle:
                timer_handle.cancel()
                timer_handle = None

            if leading:
                debug_log(f"Throttle: emitting leading value {value}")
                # Store value before potential update
                value_before_update = throttled_sig._value
                throttled_sig._update_value(value)
                # Check if the value actually changed before updating last_emit_time
                if not throttled_sig._equal(value_before_update, throttled_sig._value):
                    debug_log(
                        "Throttle: Leading value caused update, updating last_emit_time"
                    )
                    last_emit_time = current_time
                    has_trailing_value = False  # Leading emit consumed the value
                else:
                    debug_log(
                        "Throttle: Leading value did not cause update, last_emit_time unchanged"
                    )

            elif trailing:
                debug_log(
                    f"Throttle: interval passed, leading=False, scheduling trailing timer for {interval_seconds}s"
                )
                try:
                    loop = asyncio.get_running_loop()
                    if not timer_handle:  # Avoid rescheduling if already scheduled
                        timer_handle = loop.call_later(interval_seconds, _emit_trailing)
                except RuntimeError:
                    debug_log(
                        "Throttle: No running event loop found. Cannot schedule timer."
                    )
                    pass

        else:  # Interval has *not* passed
            debug_log("Throttle: within interval")
            if trailing and not timer_handle:
                remaining_time = interval_seconds - time_since_last_emit
                debug_log(
                    f"Throttle: within interval, scheduling trailing timer for {remaining_time:.4f}s"
                )
                try:
                    loop = asyncio.get_running_loop()
                    timer_handle = loop.call_later(remaining_time, _emit_trailing)
                except RuntimeError:
                    debug_log(
                        "Throttle: No running event loop found. Cannot schedule timer."
                    )
                    pass

    # Create the internal effect
    internal_effect = Effect(_run_throttle)
    throttled_sig._internal_effect = internal_effect

    return throttled_sig


# Sentinel object for pairwise
_NO_VALUE = object()


def pairwise_signal(
    source: Union[Signal[T], ComputeSignal[T], _OperatorSignal[T]],
    emit_on_first: bool = False,
) -> _OperatorSignal[Optional[Tuple[Optional[T], T]]]:
    """DEPRECATED: This function is deprecated and will be removed in a future version.

    Signal-based state management should not have temporal/stateful behavior like pairwise.
    Consider maintaining previous state explicitly in a Signal or using a ComputeSignal.

    Creates a read-only signal that emits a tuple containing the previous
    and current values from the source signal.

    Args:
        source: The input signal.
        emit_on_first: If True, emits `(None, first_value)` when the source
                       emits its first value. If False (default), the first
                       emission from the source does not produce an output,
                       and the second emission produces `(first_value, second_value)`.

    Returns:
        An operator signal emitting tuples of `(previous, current)` values.
        The type of `previous` is `Optional[T]`. The initial value of the
        signal before any valid pair is emitted is `None`.
    """
    warnings.warn(
        "pairwise_signal is deprecated and will be removed in a future version. "
        "Signal-based state management should not have temporal/stateful behavior. "
        "Consider maintaining previous state explicitly in Signals instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    previous_value: Any = _NO_VALUE
    # Get initial value without tracking dependency here
    initial_source_value = source.get()

    # Determine the correct initial value for the pairwise signal
    initial_pairwise_value: Optional[Tuple[Optional[T], T]] = None
    if emit_on_first:
        # If emit_on_first, the initial state reflects the first pair.
        initial_pairwise_value = (None, initial_source_value)
        # Store the initial source value as the "previous" for the *next* run
        previous_value = initial_source_value
    # else: initial_pairwise_value remains None, previous_value remains _NO_VALUE

    # Initialize the signal with the calculated initial value.
    # Add explicit type hint here to match the return signature
    pairwise_sig: _OperatorSignal[Optional[Tuple[Optional[T], T]]] = _OperatorSignal(
        initial_pairwise_value
    )
    debug_log(
        f"Pairwise: Initialized signal with {initial_pairwise_value}. emit_on_first={emit_on_first}"
    )

    def _run_pairwise():
        nonlocal previous_value
        # Get current value and track source dependency
        current_value = source.get()

        # Get the source's equality function
        def default_equal(a: Any, b: Any) -> bool:
            return a == b if a is not None and b is not None else a is b

        source_equal = getattr(source, "_equal", default_equal)

        if source_equal is None:
            source_equal = default_equal

        # Check if the current value is the same as the previous one.
        is_same_as_previous = (previous_value is not _NO_VALUE) and source_equal(
            previous_value, current_value
        )

        if is_same_as_previous:
            debug_log(
                f"Pairwise: current value {current_value} is same as previous {previous_value}, skipping update."
            )
            return  # Skip emission

        output_value: Optional[Tuple[Optional[T], T]] = None
        should_emit = False

        if previous_value is _NO_VALUE:
            # This case should now only happen if emit_on_first was False
            # and this is the first value received. We just store it.
            debug_log(
                f"Pairwise (emit_on_first=False): First run, storing previous={current_value}, no emission."
            )
            pass  # No emission needed yet
        else:
            # This is a subsequent run. Prepare the pair.
            debug_log(f"Pairwise: Preparing ({previous_value}, {current_value})")
            output_value = (previous_value, current_value)
            should_emit = True

        # Update previous value for the next run, regardless of whether we emitted this time.
        previous_value = current_value

        # Emit the value if needed
        if should_emit:
            debug_log(f"Pairwise: Emitting {output_value}")
            pairwise_sig._update_value(output_value)

        # No cleanup needed for pairwise

    # Create the internal effect
    internal_effect = Effect(_run_pairwise)
    pairwise_sig._internal_effect = internal_effect

    return pairwise_sig
