import pytest
import asyncio
from reaktiv import Signal, Computed, Effect, batch


@pytest.mark.asyncio
async def test_batch_effect_notifications():
    """Test that effects are only triggered once after a batch update completes."""
    # Setup simple counter signals
    x = Signal(5)
    y = Signal(10)

    sum_xy = Computed(lambda: x() + y())
    product_xy = Computed(lambda: x() * y())

    # Track effect calls
    effect_calls = []

    async def track_changes():
        effect_calls.append((sum_xy(), product_xy()))

    # Register effect
    _tracker = Effect(track_changes)

    # Wait for initial effect to complete
    await asyncio.sleep(0.01)

    # Verify initial call
    assert len(effect_calls) == 1
    assert effect_calls[0] == (15, 50)  # 5+10=15, 5*10=50

    # Reset tracking
    effect_calls.clear()

    # Make multiple updates within a batch
    with batch():
        x.set(8)
        y.set(20)

    # Wait for effects to process
    await asyncio.sleep(0.01)

    # With proper batching, the effect should be called exactly once
    # after the batch completes
    assert len(effect_calls) == 1, (
        f"Effect called {len(effect_calls)} times instead of once"
    )
    assert effect_calls[0] == (28, 160)  # 8+20=28, 8*20=160

    # Test another batch update
    effect_calls.clear()

    with batch():
        x.set(12)
        y.set(30)

    await asyncio.sleep(0.01)

    # Verify effect called only once
    assert len(effect_calls) == 1, (
        f"Effect called {len(effect_calls)} times instead of once"
    )
    assert effect_calls[0] == (42, 360)  # 12+30=42, 12*30=360


@pytest.mark.asyncio
async def test_batch_sync_effect_notifications():
    """Test that synchronous effects are only triggered once after a batch update completes."""
    # Setup simple counter signals
    a = Signal(1)
    b = Signal(2)

    sum_ab = Computed(lambda: a() + b())
    diff_ab = Computed(lambda: a() - b())

    # Track effect calls
    effect_calls = []

    def track_changes_sync():
        effect_calls.append((sum_ab(), diff_ab()))

    # Register sync effect
    _tracker = Effect(track_changes_sync)

    # Verify initial call
    assert len(effect_calls) == 1
    assert effect_calls[0] == (3, -1)  # 1+2=3, 1-2=-1

    # Reset tracking
    effect_calls.clear()

    # Make multiple updates within a batch
    with batch():
        a.set(5)
        b.set(3)

    # With proper batching, the sync effect should be called exactly once
    # after the batch completes
    assert len(effect_calls) == 1, (
        f"Sync effect called {len(effect_calls)} times instead of once"
    )
    assert effect_calls[0] == (8, 2)  # 5+3=8, 5-3=2

    # Test another batch update
    effect_calls.clear()

    with batch():
        a.set(10)
        b.set(4)

    # Verify effect called only once
    assert len(effect_calls) == 1, (
        f"Sync effect called {len(effect_calls)} times instead of once"
    )
    assert effect_calls[0] == (14, 6)  # 10+4=14, 10-4=6
