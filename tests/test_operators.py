import asyncio
import pytest
from typing import List, Any, Callable, Coroutine # Added Callable, Coroutine
from reaktiv.core import Signal, Effect, set_debug
from reaktiv.operators import filter_signal, debounce_signal, throttle_signal

# Enable debug logging for tests if helpful
# set_debug(True)

# Helper to collect values using an Effect
@pytest.mark.asyncio
async def collect_values(
    sig_to_watch: Any, # Can be Signal, ComputeSignal, or _OperatorSignal
    action_fn: Callable[[], Coroutine[None, None, None]],
    action_delay: float = 0.01, # Delay between actions
    collect_delay: float = 0.1 # Time to wait after actions for effects/timers
) -> List[Any]:
    """Runs actions, collects results from a signal via an effect, and handles cleanup."""
    collected = []
    effect_instance = None
    try:
        # Define the effect function
        def _collector_effect():
            try:
                collected.append(sig_to_watch.get()) # Use .get()
            except Exception as e:
                collected.append(e) # Collect errors too

        # Create the effect
        effect_instance = Effect(_collector_effect)

        # Allow initial effect run
        await asyncio.sleep(0.001)

        # Perform actions
        await action_fn()

        # Wait long enough for debounces/throttles/effects to settle
        await asyncio.sleep(collect_delay)

    finally:
        # Ensure cleanup
        if effect_instance:
            effect_instance.dispose()
        # Also dispose the operator signal if it's an operator signal
        if hasattr(sig_to_watch, 'dispose'):
             sig_to_watch.dispose()

    return collected

# === Test filter_signal ===

@pytest.mark.asyncio
async def test_filter_signal_basic():
    s = Signal(0) # Use class directly
    f = filter_signal(s, lambda x: x % 2 == 0)

    async def actions():
        await asyncio.sleep(0.001) # Allow initial effect
        s.set(1) # Filtered out
        await asyncio.sleep(0.01)
        s.set(2) # Passes
        await asyncio.sleep(0.01)
        s.set(3) # Filtered out
        await asyncio.sleep(0.01)
        s.set(4) # Passes
        await asyncio.sleep(0.01)

    results = await collect_values(f, actions, collect_delay=0.05)

    # Initial value (0) + value 2 + value 4
    assert results == [0, 2, 4]

@pytest.mark.asyncio
async def test_filter_signal_initial_value_fails():
    s = Signal(1) # Initial value fails predicate
    f = filter_signal(s, lambda x: x % 2 == 0)

    async def actions():
        await asyncio.sleep(0.001)
        s.set(2) # First valid value
        await asyncio.sleep(0.01)
        s.set(3) # Filtered out
        await asyncio.sleep(0.01)

    results = await collect_values(f, actions, collect_delay=0.05)
    
    assert results == [None, 2]

# === Test debounce_signal ===

@pytest.mark.asyncio
async def test_debounce_signal_basic():
    s = Signal(0)
    debounce_time = 0.05
    d = debounce_signal(s, debounce_time)

    async def actions():
        await asyncio.sleep(0.001)
        s.set(1)
        await asyncio.sleep(debounce_time / 3)
        s.set(2)
        await asyncio.sleep(debounce_time / 3)
        s.set(3) # Only this value should make it through after the delay
        # Wait longer than debounce time after last set
        await asyncio.sleep(debounce_time * 1.5)
        s.set(4) # New value after debounce settled
        await asyncio.sleep(debounce_time * 1.5)
        s.set(5) # Another value

    results = await collect_values(d, actions, collect_delay=debounce_time * 1.5)

    # Initial (0), then debounced (3), then debounced (4), then debounced (5)
    assert results == [0, 3, 4, 5]

@pytest.mark.asyncio
async def test_debounce_signal_no_extra_emissions():
    s = Signal(0)
    debounce_time = 0.05
    d = debounce_signal(s, debounce_time)

    async def actions():
        await asyncio.sleep(0.001)
        s.set(1)
        await asyncio.sleep(debounce_time * 1.5) # Let first debounce fire
        s.set(2)
        await asyncio.sleep(debounce_time / 3)
        s.set(3)
        # Wait for second debounce to fire (only value 3)
        await asyncio.sleep(debounce_time * 1.5)
        # Wait some more to ensure no other emissions
        await asyncio.sleep(debounce_time * 2)

    results = await collect_values(d, actions, collect_delay=0.01) # Short delay after actions finished

    # Initial (0), then debounced (1), then debounced (3)
    assert results == [0, 1, 3]

# === Test throttle_signal ===

@pytest.mark.asyncio
async def test_throttle_signal_leading_true_trailing_false():
    s = Signal(0)
    throttle_time = 0.05
    t = throttle_signal(s, throttle_time, leading=True, trailing=False)

    async def actions():
        await asyncio.sleep(0.001)
        s.set(1) # Emits immediately (leading=True)
        await asyncio.sleep(throttle_time / 3)
        s.set(2) # Throttled
        await asyncio.sleep(throttle_time / 3)
        s.set(3) # Throttled
        # Wait past throttle interval
        await asyncio.sleep(throttle_time * 1.5)
        s.set(4) # Interval passed, emits immediately
        await asyncio.sleep(throttle_time / 3)
        s.set(5) # Throttled

    results = await collect_values(t, actions, collect_delay=throttle_time * 1.5)

    # Initial (0), Leading (1), Leading (4)
    assert results == [0, 1, 4]

@pytest.mark.asyncio
async def test_throttle_signal_leading_false_trailing_true():
    s = Signal(0)
    throttle_time = 0.05
    t = throttle_signal(s, throttle_time, leading=False, trailing=True)

    async def actions():
        await asyncio.sleep(0.001)
        s.set(1) # Ignored (leading=False), captured for trailing
        await asyncio.sleep(throttle_time / 3)
        s.set(2) # Ignored, updates trailing candidate
        await asyncio.sleep(throttle_time / 3)
        s.set(3) # Ignored, updates trailing candidate
        # Wait for throttle interval to allow trailing emit
        await asyncio.sleep(throttle_time * 1.5)
        s.set(4) # Ignored, captured for trailing
        await asyncio.sleep(throttle_time / 3)
        s.set(5) # Ignored, updates trailing candidate

    results = await collect_values(t, actions, collect_delay=throttle_time * 1.5)

    # Initial (0), Trailing (3), Trailing (5)
    assert results == [0, 3, 5]

@pytest.mark.asyncio
async def test_throttle_signal_leading_true_trailing_true():
    s = Signal(0)
    throttle_time = 0.05
    t = throttle_signal(s, throttle_time, leading=True, trailing=True)

    async def actions():
        await asyncio.sleep(0.001)
        s.set(1) # Emits immediately (leading=True)
        await asyncio.sleep(throttle_time / 3)
        s.set(2) # Throttled, captured for trailing
        await asyncio.sleep(throttle_time / 3)
        s.set(3) # Throttled, updates trailing candidate
        # Wait past throttle interval for trailing emit
        await asyncio.sleep(throttle_time * 1.5)
        s.set(4) # Emits immediately (leading=True, interval passed)
        await asyncio.sleep(throttle_time / 3)
        s.set(5) # Throttled, captured for trailing
        # Wait past interval for trailing emit
        await asyncio.sleep(throttle_time * 1.5)
        # Test case where no intermediate value happens
        s.set(6) # Emits immediately
        await asyncio.sleep(throttle_time * 1.5) # Wait past interval, no trailing should occur
        s.set(7) # Emits immediately

    results = await collect_values(t, actions, collect_delay=throttle_time * 1.5)

    # Initial (0), Leading (1), Trailing (3), Leading (4), Trailing (5), Leading (6), Leading(7)
    assert results == [0, 1, 3, 4, 5, 6, 7]

@pytest.mark.asyncio
async def test_operator_disposal():
    """Ensure disposing the operator signal cleans up its internal effect."""
    s = Signal(0)
    op_sig = debounce_signal(s, 0.1) # Example operator

    # Access internal effect (implementation detail, but useful for testing cleanup)
    internal_effect = op_sig._internal_effect
    assert internal_effect is not None
    assert not internal_effect._disposed

    # Check initial subscription (implementation detail)
    # assert internal_effect in s._subscribers # This check is fragile

    op_sig.dispose()

    assert op_sig._internal_effect is None
    assert internal_effect._disposed
    # Check effect unsubscribed (implementation detail)
    # assert internal_effect not in s._subscribers # This check is fragile

    # Ensure no more updates happen after disposal
    s.set(1)
    await asyncio.sleep(0.15)
    # If effect wasn't disposed, op_sig would update to 1
    assert op_sig.get() == 0 # Should remain initial value

    # Ensure getting value from disposed operator doesn't error (returns last value)
    assert op_sig.get() == 0

    # Ensure subscribing to disposed operator does nothing
    dummy_effect = Effect(lambda: None)
    op_sig.subscribe(dummy_effect)
    assert dummy_effect not in op_sig._subscribers
    dummy_effect.dispose()

@pytest.mark.asyncio
async def test_operator_with_sync_effect():
    """Verify an operator signal works correctly when consumed by a sync Effect."""
    s = Signal(0)
    debounce_time = 0.05
    # Use debounce as it has internal async logic (timers)
    op_sig = debounce_signal(s, debounce_time)

    collected_sync = []

    # Create a SYNCHRONOUS effect that depends on the operator signal
    sync_effect = Effect(lambda: collected_sync.append(op_sig.get()))

    try:
        await asyncio.sleep(0.001) # Allow initial runs to settle

        # --- Action Sequence --- 
        s.set(1)
        await asyncio.sleep(debounce_time / 3)
        s.set(2) # This should be the first debounced value
        await asyncio.sleep(debounce_time * 1.5) # Wait for debounce timer

        s.set(3)
        await asyncio.sleep(debounce_time / 3)
        s.set(4) # This should be the second debounced value
        await asyncio.sleep(debounce_time * 1.5) # Wait for debounce timer

        # --- Verification --- 
        # Expected: Initial value (0), first debounced value (2), second debounced value (4)
        assert collected_sync == [0, 2, 4]

    finally:
        # Cleanup
        sync_effect.dispose()
        op_sig.dispose()