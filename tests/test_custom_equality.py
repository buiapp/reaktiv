import pytest
import asyncio
from reaktiv import Signal, Effect, ComputeSignal


@pytest.mark.asyncio
async def test_signal_custom_equality():
    """Test that a Signal with custom equality function works correctly."""

    # Use a custom equality function that checks if the lengths are the same
    def list_length_equal(a, b):
        return len(a) == len(b)

    # Create a signal with custom equality function
    data = Signal([1, 2, 3], equal=list_length_equal)

    # Create an effect to track updates
    effect_runs = 0

    async def effect_fn():
        nonlocal effect_runs
        data.get()
        effect_runs += 1

    _effect = Effect(effect_fn)
    await asyncio.sleep(0)

    # Initial run
    assert effect_runs == 1

    # Update with a different list of the same length - should NOT trigger the effect
    data.set([4, 5, 6])
    await asyncio.sleep(0)
    assert effect_runs == 1, "Effect should not run for equal-length lists"

    # Update with a list of different length - SHOULD trigger the effect
    data.set([7, 8, 9, 10])
    await asyncio.sleep(0)
    assert effect_runs == 2, "Effect should run for different-length lists"


@pytest.mark.asyncio
async def test_signal_default_equality():
    """Test that a Signal without custom equality uses identity comparison by default."""
    # Create a regular signal with default equality
    data = Signal([1, 2, 3])

    # Create an effect to track updates
    effect_runs = 0

    async def effect_fn():
        nonlocal effect_runs
        data.get()
        effect_runs += 1

    _effect = Effect(effect_fn)
    await asyncio.sleep(0)

    # Initial run
    assert effect_runs == 1

    # Update with a different list with the same values - SHOULD trigger the effect
    # because Signal's default equality uses identity comparison (is), not value equality
    data.set([1, 2, 3])
    await asyncio.sleep(0)
    assert effect_runs == 2, (
        "Effect should run for different list instances even with same values"
    )

    # Setting the exact same object instance should NOT trigger the effect
    same_list = [4, 5, 6]
    data.set(same_list)
    await asyncio.sleep(0)
    assert effect_runs == 3, "Effect should run when value changes"

    # Setting the same instance again should NOT trigger the effect
    data.set(same_list)
    await asyncio.sleep(0)
    assert effect_runs == 3, (
        "Effect should not run when setting the same object instance"
    )


@pytest.mark.asyncio
async def test_computed_signal_custom_equality():
    """Test that computed signals work with custom equality functions."""

    # Define a simpler custom equality function for testing
    def within_tolerance(a, b, tolerance=0.1):
        return abs(a - b) <= tolerance

    # Create a base signal and a computed signal with custom equality
    base = Signal(100)
    computed = ComputeSignal(
        lambda: base.get() / 10,  # Simple computation: divide by 10
        equal=lambda a, b: within_tolerance(a, b),
    )

    # Verify initial value
    assert computed.get() == 10.0

    # Setup notification tracking via Effect (no subscribe API)
    notifications = []

    async def tracker():
        notifications.append(computed.get())

    _tracker = Effect(tracker)
    await asyncio.sleep(0)
    # Clear the initial snapshot emitted by the tracker effect
    notifications.clear()

    # Small change within tolerance (100 -> 101) => 10.0 -> 10.1
    base.set(101)
    # Computed value should update internally
    assert computed.get() == 10.1
    await asyncio.sleep(0)
    # No effect notification due to custom equality within tolerance
    assert notifications == []

    # Reset notifications list for clarity
    notifications.clear()

    # Change outside tolerance (101 -> 112) => 10.1 -> 11.2
    base.set(112)
    # Computed value should update
    assert computed.get() == 11.2
    await asyncio.sleep(0)
    # Now a notification should be sent (outside tolerance)
    assert len(notifications) > 0
    assert notifications[-1] == 11.2


@pytest.mark.asyncio
async def test_deep_equality_example():
    """Test custom equality for nested data structures."""
    import json

    def json_equal(a, b):
        return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    # Test with a simple list
    data = Signal(["test"], equal=json_equal)

    # Track effect executions
    effect_runs = 0

    async def effect_fn():
        nonlocal effect_runs
        data.get()
        effect_runs += 1

    _effect = Effect(effect_fn)
    await asyncio.sleep(0)

    # Initial run
    assert effect_runs == 1

    # Same content, different instance - should NOT trigger update
    data.set(["test"])
    await asyncio.sleep(0)
    assert effect_runs == 1, "No update should occur when content is the same"

    # Different content - SHOULD trigger update
    data.set(["different"])
    await asyncio.sleep(0)
    assert effect_runs == 2, "Update should occur when content changes"

    # Test with a nested structure
    user_data = Signal(
        {
            "profile": {
                "name": "Alice",
                "preferences": ["dark mode", "notifications on"],
            }
        },
        equal=json_equal,
    )

    profile_updates = 0

    async def profile_effect():
        nonlocal profile_updates
        user_data.get()
        profile_updates += 1

    _profile_monitor = Effect(profile_effect)
    await asyncio.sleep(0)

    # Initial run
    assert profile_updates == 1

    # Same structure in a new object - should NOT trigger update
    user_data.set(
        {"profile": {"name": "Alice", "preferences": ["dark mode", "notifications on"]}}
    )
    await asyncio.sleep(0)
    assert profile_updates == 1, "No update for identical nested structure"

    # Changed nested value - SHOULD trigger update
    user_data.set(
        {
            "profile": {
                "name": "Alice",
                "preferences": ["light mode", "notifications on"],  # Changed preference
            }
        }
    )
    await asyncio.sleep(0)
    assert profile_updates == 2, "Update should occur when nested value changes"
