import pytest
import asyncio
from typing import List
from reaktiv import Signal, Effect, ComputeSignal
import reaktiv.core as rc

rc.set_debug(True) 

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

    effect = Effect(test_effect)
    effect.schedule()
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

    effect = Effect(test_effect)
    effect.schedule()
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
    effect.schedule()
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

    e1 = Effect(effect1)
    e2 = Effect(effect2)
    e1.schedule()
    e2.schedule()
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

    effect = Effect(async_effect)
    effect.schedule()
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

    effect = Effect(error_effect)
    effect.schedule()
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
    effect.schedule()
    await asyncio.sleep(0)
    
    assert len(signal._subscribers) == 1
    
    effect.dispose()
    await asyncio.sleep(0)
    
    assert len(signal._subscribers) == 0

@pytest.mark.asyncio
async def test_nested_effects():
    parent_signal = Signal(0)
    child_signal = Signal(10)
    parent_executions = 0
    child_executions = 0

    async def child_effect():
        nonlocal child_executions
        child_signal.get()
        child_executions += 1

    async def parent_effect():
        nonlocal parent_executions
        parent_signal.get()
        parent_executions += 1
        
        if parent_signal.get() > 0:
            effect = Effect(child_effect)
            effect.schedule()

    effect = Effect(parent_effect)
    effect.schedule()
    await asyncio.sleep(0)
    
    parent_signal.set(1)
    await asyncio.sleep(0)
    
    child_signal.set(20)
    await asyncio.sleep(0)
    
    assert parent_executions == 2
    assert child_executions == 1

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
    
    effect = Effect(log_squared)
    effect.schedule()
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
    
    c = ComputeSignal(
        lambda: a.get() if switch.get() else b.get()
    )

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
    b = ComputeSignal(lambda: a.get() + 10, default=0)  # b = a + 10

    # 2) Track how many times the effect runs, and what values it observed
    effect_run_count = 0
    observed_values = []

    def my_effect():
        nonlocal effect_run_count
        val_a = a.get()   # ensures subscription to 'a'
        val_b = b.get()   # ensures subscription to 'b'
        effect_run_count += 1
        observed_values.append((val_a, val_b))

    # 3) Create and schedule the effect (sync or async—this example is sync)
    eff = Effect(my_effect)
    eff.schedule()

    # 4) Wait a little for the initial effect run
    await asyncio.sleep(0.1)

    # Check initial run
    assert effect_run_count == 1, "Effect should have run once initially."
    assert observed_values[-1] == (1, 11), "Expected a=1, b=11 on initial run."

    # 5) Update 'a' from 1 to 2 => 'b' becomes 12 => effect should trigger once
    a.set(2)
    await asyncio.sleep(0.1)

    assert effect_run_count == 2, "Updating 'a' once should trigger exactly one new effect run."
    assert observed_values[-1] == (2, 12), "Expected a=2, b=12 after first update."

    # 6) Update 'a' again => 'b' changes again => effect triggers once more
    a.set(5)
    await asyncio.sleep(0.1)

    assert effect_run_count == 3, "Updating 'a' again should trigger exactly one new effect run."
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
    b = ComputeSignal(lambda: a.get() + 10, default=0)  # b = a + 10

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
    eff = Effect(my_async_effect)
    eff.schedule()  # Manually schedule once to establish subscriptions

    # 4) Wait briefly for the initial effect run
    await asyncio.sleep(0.1)

    # Verify one initial run
    assert effect_run_count == 1, "Effect should have run once initially."
    assert observed_values[-1] == (1, 11), "Expected a=1, b=11 on initial run."

    # 5) Update 'a' => 'b' re-computes => effect should trigger once
    a.set(2)
    # Wait enough time for the async effect to run
    await asyncio.sleep(0.1)

    assert effect_run_count == 2, "Updating 'a' to 2 should trigger exactly one new effect run."
    assert observed_values[-1] == (2, 12), "Expected a=2, b=12 after the update."

    # 6) Update 'a' again => 'b' changes => effect triggers once more
    a.set(5)
    await asyncio.sleep(0.1)

    assert effect_run_count == 3, "Updating 'a' to 5 should trigger exactly one new effect run."
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
    signal_trigger_count = 0
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

    c_sum = ComputeSignal(compute_fn, default=0)

    # ------------------------------------------------------------------------------
    # 4) Define a synchronous effect that depends on s1
    # ------------------------------------------------------------------------------
    def sync_effect():
        nonlocal sync_effect_trigger_count
        _ = s1.get()  # ensures subscription
        sync_effect_trigger_count += 1

    sync_eff = Effect(sync_effect)
    sync_eff.schedule()  # run once so it subscribes

    # ------------------------------------------------------------------------------
    # 5) Define an asynchronous effect that depends on c_sum
    # ------------------------------------------------------------------------------
    async def async_effect():
        nonlocal async_effect_trigger_count
        _ = c_sum.get()  # ensures subscription
        async_effect_trigger_count += 1
        await asyncio.sleep(0.1)  # simulate "work"

    async_eff = Effect(async_effect)
    async_eff.schedule()  # run once so it subscribes

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
        await asyncio.sleep(1)
        print(f"Async read: {val}")

    async_eff = Effect(async_effect)
    async_eff.schedule()

    # 2) A sync effect
    def sync_effect():
        val = b.get()
        print(f"Sync read: {val}")

    sync_eff = Effect(sync_effect)
    sync_eff.schedule()

    print("Sync set:")
    for _ in range(3):
        b.set(b.get() + 1)
        print(f"Sync Set: {b.get()}")

    print("Async set:")
    for _ in range(3):
        a.set(a.get() + 1)
        print(f"Async set: {a.get()}")
        await asyncio.sleep(0.1)

    print("Waiting 3s for all async runs to complete...")
    await asyncio.sleep(3)
    print("Done.")

    # Now capture the output and assert it for correctness
    captured = capsys.readouterr()

    # Check that the Sync effect read all increments
    assert "Sync read: 1" in captured.out
    assert "Sync read: 2" in captured.out
    assert "Sync read: 3" in captured.out

    assert "Async read: 1" in captured.out
    assert "Async read: 2" in captured.out
    assert "Async read: 3" in captured.out

    # Check for other textual markers to confirm the flow ran
    assert "Sync set:" in captured.out
    assert "Async set:" in captured.out
    assert "Waiting 3s for all async runs to complete..." in captured.out
    assert "Done." in captured.out

@pytest.mark.asyncio
@pytest.mark.timeout(0.01)
async def test_circular_dependency_guard():
    """Test protection against circular dependencies"""
    switch = Signal(False)
    s = Signal(1)
    
    # Create signals that will form a circular dependency when switch is True
    a = ComputeSignal(lambda: s.get() + (b.get() if switch.get() else 0))
    b = ComputeSignal(lambda: a.get() if switch.get() else 0)
    
    # Initial state (no circular dependency)
    assert a.get() == 1  # 1 + 0
    assert b.get() == 0
    
    # Activate circular dependency
    switch.set(True)
    
    with pytest.raises(RuntimeError) as excinfo:
        # Trigger computation cycle
        s.set(2)
        await asyncio.sleep(0)
    
    assert "Circular dependency detected" in str(excinfo.value)