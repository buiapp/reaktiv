import pytest
import asyncio
from reaktiv import Signal, Effect, ComputeSignal, batch, untracked
from reaktiv._debug import set_debug

set_debug(True)


@pytest.mark.asyncio
async def test_signal_initialization():
    signal = Signal(42)
    assert signal.get() == 42


@pytest.mark.asyncio
async def test_signal_set_value():
    signal = Signal(0)
    signal.set(5)
    assert signal.get() == 5


@pytest.mark.asyncio
async def test_basic_effect_execution():
    signal = Signal(0)
    execution_count = 0

    async def test_effect():
        nonlocal execution_count
        signal.get()
        execution_count += 1

    _effect = Effect(test_effect)
    await asyncio.sleep(0)

    signal.set(1)
    await asyncio.sleep(0)

    assert execution_count == 2


@pytest.mark.asyncio
async def test_effect_dependency_tracking():
    signal1 = Signal(0)
    signal2 = Signal("test")
    execution_count = 0

    async def test_effect():
        nonlocal execution_count
        if signal1.get() > 0:
            signal2.get()
        execution_count += 1

    _effect = Effect(test_effect)
    # effect is automatically scheduled now
    await asyncio.sleep(0)

    signal2.set("new")
    await asyncio.sleep(0)
    assert execution_count == 1

    signal1.set(1)
    await asyncio.sleep(0)
    assert execution_count == 2

    signal2.set("another")
    await asyncio.sleep(0)
    assert execution_count == 3


@pytest.mark.asyncio
async def test_effect_disposal():
    signal = Signal(0)
    execution_count = 0

    async def test_effect():
        nonlocal execution_count
        signal.get()
        execution_count += 1

    effect = Effect(test_effect)
    # effect is automatically scheduled now
    await asyncio.sleep(0)

    signal.set(1)
    await asyncio.sleep(0)
    assert execution_count == 2

    effect.dispose()
    signal.set(2)
    await asyncio.sleep(0)
    assert execution_count == 2


@pytest.mark.asyncio
async def test_multiple_effects():
    signal = Signal(0)
    executions = [0, 0]

    async def effect1():
        signal.get()
        executions[0] += 1

    async def effect2():
        signal.get()
        executions[1] += 1

    _e1 = Effect(effect1)
    _e2 = Effect(effect2)
    # effects are automatically scheduled now
    await asyncio.sleep(0)

    signal.set(1)
    await asyncio.sleep(0)

    assert executions == [2, 2]


@pytest.mark.asyncio
async def test_async_effect():
    signal = Signal(0)
    results = []

    async def async_effect():
        await asyncio.sleep(0.01)
        results.append(signal.get())

    _effect = Effect(async_effect)
    # effect is automatically scheduled now
    await asyncio.sleep(0.02)

    signal.set(1)
    await asyncio.sleep(0.02)

    assert results == [0, 1]


@pytest.mark.asyncio
async def test_effect_error_handling(capsys):
    signal = Signal(0)

    async def error_effect():
        signal.get()
        raise ValueError("Test error")

    _effect = Effect(error_effect)
    # effect is automatically scheduled now
    await asyncio.sleep(0)

    signal.set(1)
    await asyncio.sleep(0)

    captured = capsys.readouterr()
    assert "Test error" in captured.err
    assert "ValueError" in captured.err


@pytest.mark.asyncio
async def test_memory_management():
    signal = Signal(0)

    async def test_effect():
        signal.get()

    effect = Effect(test_effect)
    # effect is automatically scheduled now
    await asyncio.sleep(0)

    # There's no public subscriber API; instead ensure effect detaches by stopping notifications.
    count = 0

    async def probe():
        nonlocal count
        signal.get()
        count += 1

    _probe_effect = Effect(probe)
    await asyncio.sleep(0)
    # initial run
    assert count == 1

    effect.dispose()
    signal.set(2)
    await asyncio.sleep(0)
    assert count == 2


@pytest.mark.asyncio
async def test_compute_signal_basic():
    source = Signal(5)
    doubled = ComputeSignal(lambda: source.get() * 2)
    assert doubled.get() == 10
    source.set(6)
    assert doubled.get() == 12


@pytest.mark.asyncio
async def test_compute_signal_dependencies():
    a = Signal(2)
    b = Signal(3)
    sum_signal = ComputeSignal(lambda: a.get() + b.get())
    assert sum_signal.get() == 5
    a.set(4)
    assert sum_signal.get() == 7
    b.set(5)
    assert sum_signal.get() == 9


@pytest.mark.asyncio
async def test_compute_signal_nested():
    base = Signal(10)
    increment = Signal(1)
    computed = ComputeSignal(lambda: base.get() + increment.get())
    doubled = ComputeSignal(lambda: computed.get() * 2)
    assert doubled.get() == 22  # (10+1)*2
    base.set(20)
    assert doubled.get() == 42  # (20+1)*2
    increment.set(2)
    assert doubled.get() == 44  # (20+2)*2


@pytest.mark.asyncio
async def test_compute_signal_effect():
    source = Signal(0)
    squared = ComputeSignal(lambda: source.get() ** 2)
    log = []

    async def log_squared():
        log.append(squared.get())

    _effect = Effect(log_squared)
    # effect is automatically scheduled now
    await asyncio.sleep(0)
    source.set(2)
    await asyncio.sleep(0)
    assert log == [0, 4]


@pytest.mark.asyncio
async def test_compute_dynamic_dependencies():
    switch = Signal(True)
    a = Signal(10)
    b = Signal(20)

    dynamic = ComputeSignal(lambda: a.get() if switch.get() else b.get())
    assert dynamic.get() == 10

    switch.set(False)
    assert dynamic.get() == 20

    a.set(15)  # Shouldn't affect dynamic now
    assert dynamic.get() == 20

    switch.set(True)
    assert dynamic.get() == 15


@pytest.mark.asyncio
async def test_diamond_dependency():
    """Test computed signals with diamond-shaped dependencies"""
    base = Signal(1)
    a = ComputeSignal(lambda: base.get() + 1)
    b = ComputeSignal(lambda: base.get() * 2)
    c = ComputeSignal(lambda: a.get() + b.get())

    # Initial values
    assert c.get() == 4  # (1+1) + (1*2) = 4

    # Update base and verify propagation
    base.set(2)
    await asyncio.sleep(0)
    assert a.get() == 3
    assert b.get() == 4
    assert c.get() == 7  # 3 + 4

    # Verify dependencies update properly
    base.set(3)
    await asyncio.sleep(0)
    assert c.get() == 10  # (3+1) + (3*2) = 4 + 6 = 10


@pytest.mark.asyncio
async def test_dynamic_dependencies():
    """Test computed signals that change their dependencies dynamically"""
    switch = Signal(True)
    a = Signal(10)
    b = Signal(20)

    c = ComputeSignal(lambda: a.get() if switch.get() else b.get())

    # Initial state
    assert c.get() == 10

    # Switch dependency
    switch.set(False)
    await asyncio.sleep(0)
    assert c.get() == 20

    # Update original dependency (shouldn't affect)
    a.set(15)
    await asyncio.sleep(0)
    assert c.get() == 20  # Still using b

    # Update new dependency
    b.set(25)
    await asyncio.sleep(0)
    assert c.get() == 25


@pytest.mark.asyncio
async def test_deep_nesting():
    """Test 3-level deep computed signal dependencies"""
    base = Signal(1)
    level1 = ComputeSignal(lambda: base.get() * 2)
    level2 = ComputeSignal(lambda: level1.get() + 5)
    level3 = ComputeSignal(lambda: level2.get() * 3)

    assert level3.get() == 21  # ((1*2)+5)*3

    base.set(3)
    await asyncio.sleep(0)
    assert level3.get() == 33  # ((3*2)+5)*3


@pytest.mark.asyncio
async def test_overlapping_updates():
    """Test scenario where multiple dependencies update simultaneously"""
    x = Signal(1)
    y = Signal(2)
    a = ComputeSignal(lambda: x.get() + y.get())
    b = ComputeSignal(lambda: x.get() - y.get())
    c = ComputeSignal(lambda: a.get() * b.get())

    assert c.get() == -3  # (1+2) * (1-2) = -3

    # Update both base signals
    x.set(4)
    y.set(1)
    await asyncio.sleep(0)
    assert c.get() == 15  # (4+1) * (4-1) = 5*3


@pytest.mark.asyncio
async def test_signal_computed_effect_triggers_once():
    """
    - We have one Signal 'a'.
    - One ComputeSignal 'b' that depends on 'a'.
    - One Effect that depends on both 'a' and 'b'.
    - We update 'a' => expect effect triggers once, and we assert the new values.
    - We update 'a' again (thus changing b) => expect effect triggers once, assert values.
    """
    # 1) Create our Signal and ComputeSignal
    a = Signal(1)
    b = ComputeSignal(lambda: a.get() + 10)  # b = a + 10

    # 2) Track how many times the effect runs, and what values it observed
    effect_run_count = 0
    observed_values = []

    def my_effect():
        nonlocal effect_run_count
        val_a = a.get()  # ensures subscription to 'a'
        val_b = b.get()  # ensures subscription to 'b'
        effect_run_count += 1
        observed_values.append((val_a, val_b))

    # 3) Create and schedule the effect (sync or async—this example is sync)
    _eff = Effect(my_effect)

    # Check initial run
    assert effect_run_count == 1, "Effect should have run once initially."
    assert observed_values[-1] == (1, 11), "Expected a=1, b=11 on initial run."

    # 5) Update 'a' from 1 to 2 => 'b' becomes 12 => effect should trigger once
    a.set(2)
    await asyncio.sleep(0.1)

    assert effect_run_count == 2, (
        "Updating 'a' once should trigger exactly one new effect run."
    )
    assert observed_values[-1] == (2, 12), "Expected a=2, b=12 after first update."

    # 6) Update 'a' again => 'b' changes again => effect triggers once more
    a.set(5)
    await asyncio.sleep(0.1)

    assert effect_run_count == 3, (
        "Updating 'a' again should trigger exactly one new effect run."
    )
    assert observed_values[-1] == (5, 15), "Expected a=5, b=15 after second update."


@pytest.mark.asyncio
async def test_signal_computed_async_effect_triggers_once():
    """
    Similar to the sync version, but uses an asynchronous effect.
    - One Signal 'a' (initially 1).
    - One ComputeSignal 'b' that depends on 'a' (b = a + 10).
    - One async Effect that depends on both 'a' and 'b'.
    - We update 'a' => expect the effect to trigger exactly once each time,
      and assert the new values (a, b) within the effect.
    """

    # 1) Create the Signal and ComputeSignal
    a = Signal(1)
    b = ComputeSignal(lambda: a.get() + 10)  # b = a + 10

    # 2) Track how many times the effect runs, and what values it observed
    effect_run_count = 0
    observed_values = []

    async def my_async_effect():
        # We read a and b to ensure the effect depends on both
        nonlocal effect_run_count
        val_a = a.get()
        val_b = b.get()

        # Simulate "work" or concurrency
        await asyncio.sleep(0.01)

        effect_run_count += 1
        observed_values.append((val_a, val_b))

    # 3) Create the asynchronous Effect and schedule the first run
    _eff = Effect(my_async_effect)

    # 4) Wait briefly for the initial effect run
    await asyncio.sleep(0.1)

    # Verify one initial run
    assert effect_run_count == 1, "Effect should have run once initially."
    assert observed_values[-1] == (1, 11), "Expected a=1, b=11 on initial run."

    # 5) Update 'a' => 'b' re-computes => effect should trigger once
    a.set(2)
    # Wait enough time for the async effect to run
    await asyncio.sleep(0.1)

    assert effect_run_count == 2, (
        "Updating 'a' to 2 should trigger exactly one new effect run."
    )
    assert observed_values[-1] == (2, 12), "Expected a=2, b=12 after the update."

    # 6) Update 'a' again => 'b' changes => effect triggers once more
    a.set(5)
    await asyncio.sleep(0.1)

    assert effect_run_count == 3, (
        "Updating 'a' to 5 should trigger exactly one new effect run."
    )
    assert observed_values[-1] == (5, 15), "Expected a=5, b=15 after the update."


@pytest.mark.asyncio
async def test_no_redundant_triggers():
    """
    Tests that signals, compute signals, and effects do NOT get triggered
    multiple times for the same value.
    """
    # ------------------------------------------------------------------------------
    # 1) Prepare counters to track how many times things are triggered / recomputed.
    # ------------------------------------------------------------------------------
    compute_trigger_count = 0
    sync_effect_trigger_count = 0
    async_effect_trigger_count = 0

    # ------------------------------------------------------------------------------
    # 2) Define two signals: s1, s2
    # ------------------------------------------------------------------------------
    s1 = Signal(0)
    s2 = Signal(10)

    # ------------------------------------------------------------------------------
    # 3) Define a ComputeSignal that depends on s1 and s2
    #    We'll track how many times it actually re-computes.
    # ------------------------------------------------------------------------------
    def compute_fn():
        nonlocal compute_trigger_count
        compute_trigger_count += 1
        return s1.get() + s2.get()

    c_sum = ComputeSignal(compute_fn)

    # ------------------------------------------------------------------------------
    # 4) Define a synchronous effect that depends on s1
    # ------------------------------------------------------------------------------
    def sync_effect():
        nonlocal sync_effect_trigger_count
        _ = s1.get()  # ensures subscription
        sync_effect_trigger_count += 1

    _sync_eff = Effect(sync_effect)

    # ------------------------------------------------------------------------------
    # 5) Define an asynchronous effect that depends on c_sum
    # ------------------------------------------------------------------------------
    async def async_effect():
        nonlocal async_effect_trigger_count
        _ = c_sum.get()  # ensures subscription
        async_effect_trigger_count += 1
        await asyncio.sleep(0.1)  # simulate "work"

    _async_eff = Effect(async_effect)

    # Give a small pause so both effects subscribe (auto-run).
    await asyncio.sleep(0.05)

    # ------------------------------------------------------------------------------
    # 6) Test: Setting the same value should NOT trigger notifications
    # ------------------------------------------------------------------------------
    # s1 is currently 0; let's "set" it to 0 again
    s1.set(0)
    # s2 is currently 10; let's "set" it to 10 again
    s2.set(10)
    # Wait a moment so if any erroneous triggers happened, they'd appear
    await asyncio.sleep(0.1)

    # We expect:
    # - No increments to s1 or s2's subscribers,
    # - No re-computation of c_sum,
    # - No new triggers for sync/async effect.
    assert sync_effect_trigger_count == 1, (
        "Sync effect should not have triggered again if s1 didn't change."
    )
    assert async_effect_trigger_count == 1, (
        "Async effect should not have triggered again if c_sum didn't change."
    )
    # The compute signal was computed initially at creation,
    # so compute_trigger_count should still be 1 (the creation time).
    # If it re-computed, that means a redundant notification occurred.
    assert compute_trigger_count == 1, (
        "ComputeSignal should not recompute when s1, s2 remain unchanged."
    )

    # ------------------------------------------------------------------------------
    # 7) Test: Changing a signal value once => triggers everything exactly once
    # ------------------------------------------------------------------------------
    s1.set(1)  # from 0 to 1 is a real change
    # Wait enough time for sync + async to run
    await asyncio.sleep(0.2)

    # Now we expect exactly 1 additional trigger for the sync effect,
    # 1 additional run of the async effect,
    # and 1 additional compute re-calc for c_sum.
    assert sync_effect_trigger_count == 2, (
        "Sync effect should trigger exactly once more after s1 changes from 0 to 1."
    )
    assert async_effect_trigger_count == 2, (
        "Async effect should trigger exactly once more because c_sum changed (0->11)."
    )
    assert compute_trigger_count == 2, (
        "ComputeSignal should recompute exactly once more after s1 changed."
    )

    # ------------------------------------------------------------------------------
    # 8) Test: Setting the same value again => no further triggers
    # ------------------------------------------------------------------------------
    s1.set(1)  # from 1 to 1 (no change)
    await asyncio.sleep(0.2)

    assert sync_effect_trigger_count == 2, (
        "Sync effect shouldn't trigger again if the value didn't change."
    )
    assert async_effect_trigger_count == 2, (
        "Async effect shouldn't trigger again if c_sum didn't change."
    )
    assert compute_trigger_count == 2, (
        "ComputeSignal shouldn't recompute for a non-change in s1."
    )

    # ------------------------------------------------------------------------------
    # 9) Last test: Changing s2 => triggers everything exactly once more
    # ------------------------------------------------------------------------------
    s2.set(11)  # from 10 to 11 is a real change
    await asyncio.sleep(0.2)

    # c_sum was 1 + 10 = 11; now it's 1 + 11 = 12 => effect triggers
    assert sync_effect_trigger_count == 2, (
        "Sync effect depends only on s1, so it shouldn't trigger from s2 changes."
    )
    # But the async effect depends on c_sum, so it should trigger once
    assert async_effect_trigger_count == 3, (
        "Async effect should trigger once more after c_sum changed (11->12)."
    )
    assert compute_trigger_count == 3, (
        "ComputeSignal should have recomputed once more when s2 changed."
    )

    # If all assertions pass, it means no redundant triggers happened
    # when values were unchanged, and exactly one trigger happened
    # per legitimate value change.


@pytest.mark.asyncio
async def test_backpressure(capsys):
    """
    This test checks that both synchronous and asynchronous effects
    can handle multiple rapid signal updates without race conditions
    or missed updates (backpressure test).
    """

    # Create two signals
    a = Signal(0)
    b = Signal(0)

    # 1) An async effect
    async def async_effect():
        val = a.get()  # triggers immediate subscription
        await asyncio.sleep(0.05)  # Reduced sleep time for faster test execution
        print(f"Async read: {val}")

    _async_eff = Effect(async_effect)

    # 2) A sync effect
    def sync_effect():
        val = b.get()
        print(f"Sync read: {val}")

    _sync_eff = Effect(sync_effect)

    # Wait for initial effects to run
    await asyncio.sleep(0.1)

    # Clear previous output
    capsys.readouterr()

    print("Sync set:")
    for i in range(3):
        b.set(i + 1)  # Set to 1, 2, 3
        print(f"Sync Set: {b.get()}")
        await asyncio.sleep(0.01)  # Small delay to allow sync effects to process

    # Make sure sync effects had time to run
    await asyncio.sleep(0.05)

    print("Async set:")
    for i in range(3):
        a.set(i + 1)  # Set to 1, 2, 3
        print(f"Async set: {a.get()}")
        await asyncio.sleep(0.1)  # Ensure each async effect runs before next update

    # Wait for all async effects to complete
    await asyncio.sleep(0.2)
    print("Done.")

    # Capture the output and check for correctness
    captured = capsys.readouterr().out

    # Check that the Sync effect read all values
    assert "Sync read: 1" in captured, "Missing sync read 1"
    assert "Sync read: 2" in captured, "Missing sync read 2"
    assert "Sync read: 3" in captured, "Missing sync read 3"

    # Check that the Async effect read all values
    assert "Async read: 1" in captured, "Missing async read 1"
    assert "Async read: 2" in captured, "Missing async read 2"
    assert "Async read: 3" in captured, "Missing async read 3"

    # Check for other markers to confirm the flow
    assert "Sync set:" in captured
    assert "Async set:" in captured
    assert "Done." in captured


@pytest.mark.asyncio
async def test_signal_update_basic():
    """Test basic signal update functionality"""
    signal = Signal(5)
    signal.update(lambda x: x * 2)
    assert signal.get() == 10


@pytest.mark.asyncio
async def test_signal_update_effect():
    """Test that updating a signal triggers effects"""
    signal = Signal(0)
    executions = 0

    async def effect():
        nonlocal executions
        signal.get()
        executions += 1

    _eff = Effect(effect)
    await asyncio.sleep(0)

    # Initial effect run
    assert executions == 1

    signal.update(lambda x: x + 1)
    await asyncio.sleep(0)

    # Should trigger effect again
    assert executions == 2


@pytest.mark.asyncio
async def test_signal_update_no_change():
    """Test no effect trigger when value doesn't change"""
    signal = Signal(5)
    executions = 0

    async def effect():
        nonlocal executions
        signal.get()
        executions += 1

    _eff = Effect(effect)
    await asyncio.sleep(0)

    signal.update(lambda x: x)  # Returns same value
    await asyncio.sleep(0)

    assert executions == 1  # No additional execution


@pytest.mark.asyncio
async def test_batch_basic():
    """Test basic batching functionality"""
    a = Signal(1)
    b = Signal(2)
    c = ComputeSignal(lambda: a.get() + b.get())
    executions = 0

    async def effect():
        nonlocal executions
        a.get()
        b.get()
        executions += 1

    _eff = Effect(effect)
    await asyncio.sleep(0)

    # Initial execution
    assert c.get() == 3
    assert executions == 1

    with batch():
        a.set(2)
        b.set(3)

    await asyncio.sleep(0)
    assert c.get() == 5
    assert executions == 2  # Only one additional execution


@pytest.mark.asyncio
async def test_batch_nested():
    """Test nested batch operations"""
    a = Signal(1)
    executions = 0

    async def effect():
        nonlocal executions
        a.get()
        executions += 1

    _eff = Effect(effect)
    await asyncio.sleep(0)

    with batch():
        with batch():
            a.set(2)
            a.set(3)
        a.set(4)

    await asyncio.sleep(0)
    assert executions == 2  # Initial + one batch update


@pytest.mark.asyncio
async def test_batch_with_computed():
    """Test batching with computed signals"""
    a = Signal(1)
    b = ComputeSignal(lambda: a.get() * 2)
    executions = 0

    async def effect():
        nonlocal executions
        b.get()
        executions += 1

    _eff = Effect(effect)
    await asyncio.sleep(0)

    with batch():
        a.set(2)
        a.set(3)

    await asyncio.sleep(0)
    assert executions == 2  # Initial + one update after batch
    assert b.get() == 6


@pytest.mark.asyncio
async def test_untracked(capsys):
    tracked_signal = Signal(1)
    untracked_signal = Signal(10)
    effect_count = 0

    async def effect_fn():
        nonlocal effect_count
        effect_count += 1
        tracked = tracked_signal.get()
        untracked_val = untracked(lambda: untracked_signal.get())
        print(f"Effect ran: tracked={tracked}, untracked={untracked_val}")

    _effect = Effect(effect_fn)

    # Let async effects process
    await asyncio.sleep(0)

    # Initial run
    assert effect_count == 1
    assert "tracked=1, untracked=10" in capsys.readouterr().out

    # Update tracked signal
    tracked_signal.set(2)
    await asyncio.sleep(0)
    assert effect_count == 2
    assert "tracked=2, untracked=10" in capsys.readouterr().out

    # Update untracked signal
    untracked_signal.set(20)
    await asyncio.sleep(0)
    assert effect_count == 2  # Should remain unchanged


def test_untracked_direct_signal():
    """Test that untracked can be called with a signal directly as an argument."""
    tracked_signal = Signal(1)
    untracked_signal = Signal(10)
    effect_count = 0

    # Use these lists to track values instead of printing to console
    tracked_values = []
    untracked_values = []

    def effect_fn():
        nonlocal effect_count
        effect_count += 1

        # Get and track values
        tracked_val = tracked_signal.get()
        tracked_values.append(tracked_val)

        # Use the direct signal argument approach
        untracked_val = untracked(untracked_signal)  # No lambda needed

        # Also test the original lambda approach for comparison
        untracked_val2 = untracked(lambda: untracked_signal.get())

        # Track the untracked value
        untracked_values.append(untracked_val)

        # Both approaches should give the same result
        assert untracked_val == untracked_val2

    _effect = Effect(effect_fn)

    # Initial run
    assert effect_count == 1
    assert tracked_values == [1]
    assert untracked_values == [10]

    # Update tracked signal
    tracked_signal.set(2)
    assert effect_count == 2
    assert tracked_values == [1, 2]
    assert untracked_values == [
        10,
        10,
    ]  # Still 10, as we haven't updated untracked_signal yet

    # Update untracked signal - should not trigger effect regardless of how untracked was called
    untracked_signal.set(20)
    assert effect_count == 2  # Should remain unchanged
    assert len(tracked_values) == 2  # No additional tracked values
    assert len(untracked_values) == 2  # No additional untracked values

    # Verify the updated value is returned by both untracked approaches
    assert untracked(untracked_signal) == 20
    assert untracked(lambda: untracked_signal.get()) == 20


@pytest.mark.asyncio
async def test_effect_cleanup(capsys):
    a = Signal(0)
    cleanup_called = []

    async def effect_fn(on_cleanup):
        a.get()
        cleanup_called.append(False)

        def cleanup():
            cleanup_called[-1] = True
            print(f"Cleanup executed: {a.get()}")

        on_cleanup(cleanup)
        print(f"Effect ran: {a.get()}")

    effect = Effect(effect_fn)

    await asyncio.sleep(0)

    assert "Effect ran: 0" in capsys.readouterr().out
    assert cleanup_called == [False]

    # Second run
    a.set(1)
    await asyncio.sleep(0)
    output = capsys.readouterr().out
    assert "Cleanup executed: 1" in output
    assert "Effect ran: 1" in output
    assert cleanup_called == [True, False]

    # Dispose
    effect.dispose()
    await asyncio.sleep(0)
    assert cleanup_called == [True, True]


@pytest.mark.asyncio
async def test_cleanup_on_dispose():
    cleanup_called = False

    def effect_fn(on_cleanup):
        nonlocal cleanup_called

        def cleanup():
            nonlocal cleanup_called
            cleanup_called = True

        on_cleanup(cleanup)

    effect = Effect(effect_fn)
    await asyncio.sleep(0)

    assert not cleanup_called
    effect.dispose()
    assert cleanup_called


@pytest.mark.asyncio
async def test_multiple_cleanups():
    cleanups = []
    a = Signal(0)

    async def effect_fn(on_cleanup):
        a.get()
        on_cleanup(lambda: cleanups.append(1))
        on_cleanup(lambda: cleanups.append(2))

    effect = Effect(effect_fn)
    await asyncio.sleep(0)

    assert cleanups == []

    a.set(1)
    await asyncio.sleep(0)
    assert cleanups == [1, 2]

    cleanups.clear()
    effect.dispose()
    assert cleanups == [1, 2]


@pytest.mark.asyncio
async def test_compute_signal_exception_propagation():
    """Test that ComputeSignal now properly propagates exceptions to callers (Angular signals behavior)"""
    # Test with a compute signal that depends on another signal
    source = Signal(0)
    # Now using division to match expected math results: 10 divided by source value
    computed = ComputeSignal(lambda: 10 / source.get())

    # Initially, since source is 0, trying to access the computed signal should raise an exception
    with pytest.raises(ZeroDivisionError):
        computed.get()

    # After setting source to a valid value, should compute normally
    source.set(2)
    assert computed.get() == 5

    # Make source a subscriber of the computed signal to ensure notification
    source.set(5)
    assert computed.get() == 2

    # Setting source back to 0 should raise an exception again
    source.set(0)
    with pytest.raises(ZeroDivisionError):
        computed.get()


@pytest.mark.asyncio
async def test_compute_signal_exception_with_multiple_dependencies():
    """Test ComputeSignal exception handling with multiple signal dependencies"""
    a = Signal(5)
    b = Signal(3)
    computed = ComputeSignal(
        lambda: a.get() + b.get()
        if a.get() is not None and b.get() is not None
        else None
    )

    # Initially, should compute normally
    assert computed.get() == 8  # 5 + 3

    # Setting either signal to None should now result in None
    a.set(None)
    assert computed.get() is None

    # Setting back to valid values should compute properly
    a.set(10)
    assert computed.get() == 13  # 10 + 3

    # Test with exception in computation
    def problematic_compute():
        if a.get() < 0 or b.get() < 0:
            raise ValueError("Negative values not allowed")
        return a.get() + b.get()

    computed_with_validation = ComputeSignal(problematic_compute)

    # Should work with valid values
    assert computed_with_validation.get() == 13  # 10 + 3

    # Should raise exception with negative values
    a.set(-5)
    with pytest.raises(ValueError, match="Negative values not allowed"):
        computed_with_validation.get()


@pytest.mark.asyncio
async def test_compute_signal_equality_function():
    """Test that ComputeSignal respects custom equality functions"""
    # Create a source signal and a computed signal with a custom equality function
    # that considers numbers equal if they're within 0.5 of each other
    source = Signal(1)
    computed_with_tolerance = ComputeSignal(
        lambda: source.get() * 3.333, equal=lambda a, b: abs(a - b) < 0.5
    )

    # Create a tracking mechanism for effect triggers
    effect_executions = 0

    async def track_effect():
        nonlocal effect_executions
        computed_with_tolerance.get()
        effect_executions += 1

    # Create and schedule the effect
    _eff = Effect(track_effect)
    await asyncio.sleep(0)

    # Initial execution
    assert effect_executions == 1
    _initial_value = computed_with_tolerance.get()

    # Test a small change that should be considered "equal" by our custom function
    source.set(1.1)  # 1.1 * 3.333 ≈ 3.67, which is within 0.5 of the original value
    await asyncio.sleep(0)
    # Effect should NOT have executed again
    assert effect_executions == 1

    # Test a larger change that should NOT be considered equal
    source.set(1.5)  # 1.5 * 3.333 = 5.0, which is NOT within 0.5 of the original value
    await asyncio.sleep(0)
    # Effect should have executed again
    assert effect_executions == 2


@pytest.mark.asyncio
async def test_compute_signal_custom_equality():
    """Test ComputeSignal with a more complex custom equality function"""

    # Create a signal with object values
    class Item:
        def __init__(self, category, value):
            self.category = category
            self.value = value

    source = Signal(Item("A", 100))

    # Computed signal that extracts relevant data but uses an equality function
    # that only considers the category for equality
    computed_category_aware = ComputeSignal(
        lambda: {"category": source.get().category, "value": source.get().value},
        equal=lambda a, b: a and b and a.get("category") == b.get("category"),
    )

    # Track the computed value changes
    computed_updates = []

    def track_computed_changes():
        value = computed_category_aware.get()
        computed_updates.append(dict(value))  # Make a copy

    # Set up an effect to track changes
    _track_effect = Effect(track_computed_changes)
    await asyncio.sleep(0)

    # Initial update recorded
    assert len(computed_updates) == 1
    assert computed_updates[0] == {"category": "A", "value": 100}

    # Update the value but keep the category the same
    source.set(Item("A", 200))
    await asyncio.sleep(0)
    # No new update should be recorded since the category is the same
    assert len(computed_updates) == 1

    # Update the category
    source.set(Item("B", 200))
    await asyncio.sleep(0)
    # New update should be recorded
    assert len(computed_updates) == 2
    assert computed_updates[1] == {"category": "B", "value": 200}


@pytest.mark.asyncio
async def test_compute_signal_none_handling():
    """Test ComputeSignal equality handling with None values"""
    source = Signal(None)

    # Computed signal with a custom equality function that handles None
    def safe_equal(a, b):
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False
        # For non-None values, consider them equal if they have the same string representation
        return str(a) == str(b)

    computed_with_safe_equality = ComputeSignal(lambda: source.get(), equal=safe_equal)

    # Track updates
    updates = []

    def track():
        updates.append(computed_with_safe_equality.get())

    _eff = Effect(track)
    await asyncio.sleep(0)

    # Initial update
    assert updates == [None]

    # Setting to None again shouldn't trigger an update
    source.set(None)
    await asyncio.sleep(0)
    assert len(updates) == 1

    # Setting to a value should trigger an update
    source.set("test")
    await asyncio.sleep(0)
    assert len(updates) == 2
    assert updates[-1] == "test"

    # Setting to a number that converts to the same string shouldn't trigger
    source.set("test")  # Same string, no update
    await asyncio.sleep(0)
    assert len(updates) == 2


@pytest.mark.asyncio
async def test_effect_with_computed_exception(capsys):
    """Test how effects handle exceptions from computed signals"""
    source = Signal(1)
    # Create a computed signal that will throw an error when source is 0
    computed = ComputeSignal(lambda: 10 / source.get())

    effect_runs = 0
    error_caught = False

    def effect_fn():
        nonlocal effect_runs, error_caught
        effect_runs += 1
        try:
            value = computed.get()
            print(f"Effect got computed value: {value}")
        except Exception as e:
            error_caught = True
            print(f"Effect caught exception: {e}")

    # Create the effect
    _effect = Effect(effect_fn)

    # Initial run - computation should succeed
    await asyncio.sleep(0)
    assert effect_runs == 1
    assert not error_caught

    # Change source to a value that will cause exception
    source.set(0)
    await asyncio.sleep(0)

    # Effect should have run again, and caught the exception
    assert effect_runs == 2
    assert error_caught

    # Change source back to valid value
    error_caught = False  # Reset flag
    source.set(2)
    await asyncio.sleep(0)

    # Effect should run again and succeed
    assert effect_runs == 3
    assert not error_caught

    # Check console output
    captured = capsys.readouterr()
    assert "Effect got computed value: 10.0" in captured.out  # First run (10/1)
    assert "Effect caught exception: division by zero" in captured.out  # Second run
    assert "Effect got computed value: 5.0" in captured.out  # Third run (10/2)


@pytest.mark.asyncio
async def test_async_effect_with_computed_exception(capsys):
    """Test how async effects handle exceptions from computed signals"""
    source = Signal(1)
    # Create a computed signal that will throw an error when source is 0
    computed = ComputeSignal(lambda: 10 / source.get())

    effect_runs = 0
    error_caught = False

    async def async_effect_fn():
        nonlocal effect_runs, error_caught
        effect_runs += 1
        try:
            # Add a small delay to simulate async processing
            await asyncio.sleep(0.01)
            value = computed.get()
            print(f"Async effect got computed value: {value}")
        except Exception as e:
            error_caught = True
            print(f"Async effect caught exception: {e}")

    # Create the async effect
    _effect = Effect(async_effect_fn)

    # Initial run - computation should succeed
    await asyncio.sleep(0.05)
    assert effect_runs == 1
    assert not error_caught

    # Change source to a value that will cause exception
    source.set(0)
    await asyncio.sleep(0.05)

    # Effect should have run again, and caught the exception
    assert effect_runs == 2
    assert error_caught

    # Change source back to valid value
    error_caught = False  # Reset flag
    source.set(2)
    await asyncio.sleep(0.05)

    # Effect should run again and succeed
    assert effect_runs == 3
    assert not error_caught

    # Check console output
    captured = capsys.readouterr()
    assert "Async effect got computed value: 10.0" in captured.out  # First run (10/1)
    assert (
        "Async effect caught exception: division by zero" in captured.out
    )  # Second run
    assert "Async effect got computed value: 5.0" in captured.out  # Third run (10/2)


def test_compute_signal_cannot_set_signals():
    """Test that a ComputeSignal cannot set another Signal."""
    from reaktiv import Signal, Computed, batch

    # Create signals
    a = Signal(1)
    b = Signal(2)

    # Try to create a computed signal that sets another signal
    def create_bad_computed():
        return Computed(lambda: a.get() + b.set(10))  # This should fail

    # Check that creating such a computed signal raises RuntimeError
    try:
        c = create_bad_computed()
        # Trigger computation by getting the value
        c.get()
        assert False, "Should have raised RuntimeError"
    except RuntimeError as e:
        assert "Side effect detected" in str(e)
        assert "Cannot set Signal from within a ComputeSignal computation" in str(e)

    # Also test within batch context
    try:
        with batch():
            c = create_bad_computed()
            c.get()  # Trigger computation
        assert False, "Should have raised RuntimeError"
    except RuntimeError as e:
        assert "Side effect detected" in str(e)


# --------------------------------------------------
# ReadonlySignal Tests
# --------------------------------------------------


def test_readonly_signal_basic():
    """Test basic ReadonlySignal functionality"""
    signal = Signal(42)
    readonly = signal.as_readonly()

    # Should be able to read the value
    assert readonly() == 42
    assert readonly.get() == 42

    # Should update when source signal changes
    signal.set(100)
    assert readonly() == 100
    assert readonly.get() == 100


def test_readonly_signal_caching():
    """Test that as_readonly() returns the same instance"""
    signal = Signal(42)
    readonly1 = signal.as_readonly()
    readonly2 = signal.as_readonly()

    # Should be the same instance
    assert readonly1 is readonly2


def test_readonly_signal_with_computed():
    """Test ReadonlySignal works with ComputeSignal"""
    signal = Signal(10)
    readonly = signal.as_readonly()

    # Create computed signal that depends on readonly
    doubled = ComputeSignal(lambda: readonly() * 2)

    assert doubled.get() == 20

    # Update source signal
    signal.set(15)
    assert doubled.get() == 30


def test_readonly_signal_with_sync_effect():
    """Test ReadonlySignal works with synchronous effects"""
    signal = Signal(0)
    readonly = signal.as_readonly()
    executions = []

    def effect_fn():
        executions.append(readonly())

    _effect = Effect(effect_fn)

    # Initial execution
    assert executions == [0]

    # Update source signal
    signal.set(1)
    assert executions == [0, 1]

    signal.set(2)
    assert executions == [0, 1, 2]


@pytest.mark.asyncio
async def test_readonly_signal_with_async_effect():
    """Test ReadonlySignal works with asynchronous effects"""
    signal = Signal(0)
    readonly = signal.as_readonly()
    executions = []

    async def async_effect_fn():
        await asyncio.sleep(0.01)
        executions.append(readonly())

    _effect = Effect(async_effect_fn)
    await asyncio.sleep(0.05)

    # Initial execution
    assert executions == [0]

    # Update source signal
    signal.set(1)
    await asyncio.sleep(0.05)
    assert executions == [0, 1]

    signal.set(2)
    await asyncio.sleep(0.05)
    assert executions == [0, 1, 2]


def test_readonly_signal_dependency_tracking():
    """Test that ReadonlySignal properly tracks dependencies"""
    signal = Signal(0)
    readonly = signal.as_readonly()
    effect_runs = 0

    def effect_fn():
        nonlocal effect_runs
        readonly()  # Access readonly signal
        effect_runs += 1

    _effect = Effect(effect_fn)

    # Initial run
    assert effect_runs == 1

    # Update source - should trigger effect
    signal.set(1)
    assert effect_runs == 2

    # Update again - should trigger effect again
    signal.set(2)
    assert effect_runs == 3


def test_readonly_signal_with_batching():
    """Test ReadonlySignal works correctly with batching"""
    signal = Signal(0)
    readonly = signal.as_readonly()
    effect_runs = 0
    final_values = []

    def effect_fn():
        nonlocal effect_runs
        effect_runs += 1
        final_values.append(readonly())

    _effect = Effect(effect_fn)

    # Initial run
    assert effect_runs == 1
    assert final_values == [0]

    # Batch multiple updates
    with batch():
        signal.set(1)
        signal.set(2)
        signal.set(3)

    # Should only trigger effect once after batch
    assert effect_runs == 2
    assert final_values == [0, 3]


def test_readonly_signal_with_untracked():
    """Test ReadonlySignal works with untracked context"""
    signal = Signal(0)
    readonly = signal.as_readonly()
    effect_runs = 0

    def effect_fn():
        nonlocal effect_runs
        effect_runs += 1

        # Access readonly signal normally (should create dependency)
        tracked_value = readonly()

        # Access readonly signal in untracked context (should not create dependency)
        untracked_value = untracked(readonly)

        assert tracked_value == untracked_value

    _effect = Effect(effect_fn)

    # Initial run
    assert effect_runs == 1

    # Update source - should trigger effect because of tracked access
    signal.set(1)
    assert effect_runs == 2


def test_readonly_signal_multiple_dependents():
    """Test ReadonlySignal with multiple dependent computations and effects"""
    signal = Signal(5)
    readonly = signal.as_readonly()

    # Multiple computed signals depending on readonly
    doubled = ComputeSignal(lambda: readonly() * 2)
    tripled = ComputeSignal(lambda: readonly() * 3)
    combined = ComputeSignal(lambda: doubled() + tripled())

    assert doubled.get() == 10
    assert tripled.get() == 15
    assert combined.get() == 25

    # Multiple effects
    effect1_runs = []
    effect2_runs = []

    def effect1():
        effect1_runs.append(readonly())

    def effect2():
        effect2_runs.append(doubled())

    _eff1 = Effect(effect1)
    _eff2 = Effect(effect2)

    # Initial runs
    assert effect1_runs == [5]
    assert effect2_runs == [10]

    # Update source
    signal.set(7)

    assert doubled.get() == 14
    assert tripled.get() == 21
    assert combined.get() == 35
    assert effect1_runs == [5, 7]
    assert effect2_runs == [10, 14]


def test_readonly_signal_equality_function():
    """Test ReadonlySignal respects the source signal's equality function"""
    # Signal with custom equality function
    signal = Signal(1.0, equal=lambda a, b: abs(a - b) < 0.1)
    readonly = signal.as_readonly()

    effect_runs = 0

    def effect_fn():
        nonlocal effect_runs
        readonly()
        effect_runs += 1

    _effect = Effect(effect_fn)

    # Initial run
    assert effect_runs == 1

    # Small change that should be considered equal
    signal.set(1.05)
    assert effect_runs == 1  # Should not trigger effect

    # Large change that should be considered different
    signal.set(1.2)
    assert effect_runs == 2  # Should trigger effect


def test_readonly_signal_repr():
    """Test ReadonlySignal __repr__ method"""
    signal = Signal(42)
    readonly = signal.as_readonly()

    repr_str = repr(readonly)
    assert "ReadonlySignal" in repr_str
    assert "42" in repr_str


@pytest.mark.asyncio
async def test_readonly_signal_complex_dependency_chain():
    """Test ReadonlySignal in a complex dependency chain"""
    # Create a chain: signal -> readonly -> computed -> effect
    signal = Signal(1)
    readonly = signal.as_readonly()
    computed = ComputeSignal(lambda: readonly() * 10)

    effect_values = []

    async def effect_fn():
        effect_values.append(computed())

    _effect = Effect(effect_fn)
    await asyncio.sleep(0.01)

    # Initial value
    assert effect_values == [10]

    # Update signal
    signal.set(2)
    await asyncio.sleep(0.01)
    assert effect_values == [10, 20]

    # Batch update
    with batch():
        signal.set(3)
        signal.set(4)

    await asyncio.sleep(0.01)
    assert effect_values == [10, 20, 40]  # Only final value from batch
