import pytest
import asyncio
from signal_library import Signal, Effect

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