import pytest
import asyncio
from reaktiv import Signal, Effect, ComputeSignal

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