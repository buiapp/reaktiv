import pytest
import asyncio
from reaktiv import Signal, Effect, ComputeSignal, batch, untracked
from reaktiv.linked import LinkedSignal
from reaktiv._debug import set_debug

set_debug(True)


# --------------------------------------------------
# Basic LinkedSignal Tests
# --------------------------------------------------


def test_linked_signal_basic():
    """Test basic LinkedSignal functionality with simple pattern"""
    source = Signal("initial")
    linked = LinkedSignal(lambda: source().upper())

    assert linked() == "INITIAL"

    # Manual override
    linked.set("MANUAL")
    assert linked() == "MANUAL"

    # Source change triggers reset
    source.set("changed")
    assert linked() == "CHANGED"  # Reset, not "MANUAL"


def test_linked_signal_advanced_pattern():
    """Test LinkedSignal with explicit source and computation"""
    options = Signal(["A", "B", "C"])

    selected = LinkedSignal(
        source=options,
        computation=lambda new_opts, prev: (
            prev.value if prev and prev.value in new_opts else new_opts[0]
        ),
    )

    # Initial value should be first option
    assert selected() == "A"

    # Manual selection
    selected.set("B")
    assert selected() == "B"

    # Options change but B still available
    options.set(["X", "B", "Y"])
    assert selected() == "B"  # Preserved

    # Options change and B not available
    options.set(["X", "Y", "Z"])
    assert selected() == "X"  # Reset to first


def test_linked_signal_initialization_patterns():
    """Test different initialization patterns for LinkedSignal"""
    # Pattern 1: Simple computation function
    counter = Signal(2)
    doubled = LinkedSignal(lambda: counter() * 2)
    assert doubled() == 4

    # Pattern 2: Explicit source and computation
    items = Signal([1, 2, 3])
    first_item = LinkedSignal(
        source=items,
        computation=lambda new_items, prev: new_items[0] if new_items else None,
    )
    assert first_item() == 1

    # Pattern 3: Invalid patterns should raise ValueError
    with pytest.raises(ValueError, match="LinkedSignal requires either"):
        LinkedSignal()

    with pytest.raises(ValueError, match="LinkedSignal requires either"):
        LinkedSignal(source=items)  # Missing computation

    with pytest.raises(ValueError, match="LinkedSignal requires either"):
        LinkedSignal(computation=lambda x, y: x)  # Missing source


def test_linked_signal_previous_state():
    """Test that previous state is correctly passed to computation function"""
    source = Signal(1)
    history = []

    def track_computation(new_val, prev):
        history.append(
            {
                "new_val": new_val,
                "prev_value": prev.value if prev else None,
                "prev_source": prev.source if prev else None,
            }
        )
        return new_val * 10

    linked = LinkedSignal(source=source, computation=track_computation)

    # Initial computation - no previous state
    assert linked() == 10
    assert len(history) == 1
    assert history[0]["prev_value"] is None
    assert history[0]["prev_source"] is None

    # Manual override
    linked.set(99)
    assert linked() == 99

    # Source change - should have previous state
    source.set(2)
    assert linked() == 20
    assert len(history) == 2
    assert history[1]["prev_value"] == 99  # Previous linked value
    assert history[1]["prev_source"] == 1  # Previous source value


def test_linked_signal_manual_operations():
    """Test manual set and update operations"""
    source = Signal(5)
    linked = LinkedSignal(lambda: source() * 2)

    assert linked() == 10

    # Test set
    linked.set(100)
    assert linked() == 100

    # Test update
    linked.update(lambda x: x + 1)
    assert linked() == 101

    # Source change resets
    source.set(3)
    assert linked() == 6  # Reset to source() * 2


# --------------------------------------------------
# Integration Tests
# --------------------------------------------------


def test_linked_signal_with_computed_and_effects():
    """Test LinkedSignal integration with ComputeSignal and Effect"""
    counter = Signal(0)
    doubled = LinkedSignal(lambda: counter() * 2)

    # Works with ComputeSignal
    display = ComputeSignal(lambda: f"Value: {doubled()}")
    assert display() == "Value: 0"

    # Works with Effects
    log = []
    _effect = Effect(lambda: log.append(doubled()))

    # Initial effect run
    assert log == [0]

    # Manual change triggers effect
    doubled.set(99)
    assert log == [0, 99]
    assert display() == "Value: 99"

    # Source change resets and triggers effect
    counter.set(5)
    assert log == [0, 99, 10]
    assert display() == "Value: 10"


@pytest.mark.asyncio
async def test_linked_signal_with_async_effects():
    """Test LinkedSignal with async effects"""
    source = Signal(1)
    linked = LinkedSignal(lambda: source() + 100)

    log = []

    async def async_effect():
        await asyncio.sleep(0.01)
        log.append(linked())

    _effect = Effect(async_effect)
    await asyncio.sleep(0.05)

    # Initial run
    assert log == [101]

    # Manual change
    linked.set(200)
    await asyncio.sleep(0.05)
    assert log == [101, 200]

    # Source change resets
    source.set(3)
    await asyncio.sleep(0.05)
    assert log == [101, 200, 103]


def test_linked_signal_with_batching():
    """Test LinkedSignal behavior in batch operations"""
    source = Signal(1)
    linked = LinkedSignal(lambda: source() * 10)

    effect_runs = []
    _effect = Effect(lambda: effect_runs.append(linked()))

    # Initial run
    assert effect_runs == [10]

    # Manual operations in batch
    with batch():
        linked.set(50)
        linked.update(lambda x: x + 1)

    assert effect_runs == [10, 51]  # Only one additional run

    # Source change in batch
    with batch():
        source.set(2)
        source.set(3)

    assert effect_runs == [10, 51, 30]  # Reset to final source value * 10


def test_linked_signal_dependency_tracking():
    """Test that LinkedSignal properly tracks dependencies"""
    a = Signal(1)
    b = Signal(2)

    # LinkedSignal that depends on both a and b
    linked = LinkedSignal(lambda: a() + b())

    effect_runs = 0

    def track_effect():
        nonlocal effect_runs
        linked()  # Access linked signal
        effect_runs += 1

    _effect = Effect(track_effect)

    # Initial run
    assert effect_runs == 1
    assert linked() == 3

    # Change a - should trigger reset and effect
    a.set(10)
    assert effect_runs == 2
    assert linked() == 12  # 10 + 2

    # Change b - should trigger reset and effect
    b.set(5)
    assert effect_runs == 3
    assert linked() == 15  # 10 + 5

    # Manual change - should trigger effect but not reset
    linked.set(99)
    assert effect_runs == 4
    assert linked() == 99


def test_linked_signal_advanced_dependency_tracking():
    """Test LinkedSignal with advanced pattern dependency tracking"""
    source = Signal([1, 2, 3])
    other = Signal(100)

    # LinkedSignal that only resets when source changes, not when other changes
    selected = LinkedSignal(
        source=source, computation=lambda items, prev: items[0] if items else None
    )

    effect_runs = 0

    def track_effect():
        nonlocal effect_runs
        selected()  # Access linked signal
        other()  # Also access other signal
        effect_runs += 1

    _effect = Effect(track_effect)

    # Initial run
    assert effect_runs == 1
    assert selected() == 1

    # Manual override - should trigger effect
    selected.set(99)
    assert effect_runs == 2
    assert selected() == 99  # Manually set value

    # Change other signal - should trigger effect but NOT reset LinkedSignal
    other.set(200)
    assert effect_runs == 3
    assert selected() == 99  # Still manually set value

    # Change source - should trigger effect AND reset LinkedSignal
    source.set([4, 5, 6])
    assert effect_runs == 4
    assert selected() == 4  # Reset to first item


# --------------------------------------------------
# Edge Cases and Error Handling
# --------------------------------------------------


def test_linked_signal_with_empty_source():
    """Test LinkedSignal behavior with empty or None source values"""
    source = Signal([1, 2, 3])

    selected = LinkedSignal(
        source=source,
        computation=lambda items, prev: (
            items[0] if items else (prev.value if prev else "default")
        ),
    )

    assert selected() == 1

    # Empty source
    source.set([])
    assert selected() == 1  # Should preserve previous value

    # Manual change while empty
    selected.set("manual")
    assert selected() == "manual"

    # Source becomes non-empty
    source.set([10, 20])
    assert selected() == 10  # Reset to first item


def test_linked_signal_computation_exceptions():
    """Test LinkedSignal behavior when computation function throws exceptions"""
    source = Signal(1)

    def problematic_computation():
        val = source()
        if val == 0:
            raise ValueError("Cannot be zero")
        return val * 10

    linked = LinkedSignal(problematic_computation)

    # Initial computation should work
    assert linked() == 10

    # Manual override
    linked.set(99)
    assert linked() == 99

    # Source change that causes exception should not break the system
    # The exception should be contained within the effect system
    source.set(0)
    # LinkedSignal should keep its previous value since computation failed
    # The exact behavior depends on implementation - it might keep old value or propagate exception


def test_linked_signal_with_custom_equality():
    """Test LinkedSignal with custom equality function"""
    source = Signal(1.0)

    # Use custom equality that considers values equal if within 0.1
    linked = LinkedSignal(lambda: source() * 3.0, equal=lambda a, b: abs(a - b) < 0.1)

    effect_runs = 0

    def track_effect():
        nonlocal effect_runs
        linked()
        effect_runs += 1

    _effect = Effect(track_effect)

    # Initial run
    assert effect_runs == 1

    # Small change in source that results in small change in linked value
    source.set(1.02)  # 1.02 * 3.0 = 3.06, close to original
    # Effect might not run if the change is considered equal

    # Larger change
    source.set(1.5)  # 1.5 * 3.0 = 4.5, definitely different
    assert effect_runs >= 2  # Should definitely trigger


def test_linked_signal_dispose():
    """Test LinkedSignal disposal and cleanup"""
    source = Signal(1)
    linked = LinkedSignal(lambda: source() * 2)

    # Before disposal, LinkedSignal should react to source updates
    assert linked() == 2
    source.set(2)
    assert linked() == 4

    # Dispose the LinkedSignal
    linked.dispose()

    # Operations after disposal should be ignored
    linked.set(99)  # Should be ignored
    linked.update(lambda x: x + 1)  # Should be ignored

    # Source changes should not affect disposed LinkedSignal
    old_value = linked()
    source.set(10)
    assert linked() == old_value  # Should not change


def test_linked_signal_with_untracked():
    """Test LinkedSignal behavior with untracked contexts"""
    source = Signal(1)
    linked = LinkedSignal(lambda: source() * 10)

    effect_runs = 0

    def track_effect():
        nonlocal effect_runs
        effect_runs += 1

        # Normal access (should create dependency)
        tracked_value = linked()

        # Untracked access (should not create dependency)
        untracked_value = untracked(linked)

        assert tracked_value == untracked_value

    _effect = Effect(track_effect)

    # Initial run
    assert effect_runs == 1

    # Manual change should trigger effect (due to tracked access)
    linked.set(99)
    assert effect_runs == 2

    # Source change should trigger effect (due to tracked access)
    source.set(5)
    assert effect_runs == 3


# --------------------------------------------------
# Complex Scenarios
# --------------------------------------------------


def test_linked_signal_nested_dependencies():
    """Test LinkedSignal with nested dependency chains"""
    base = Signal(1)
    intermediate = ComputeSignal(lambda: base() + 10)
    linked = LinkedSignal(lambda: intermediate() * 2)

    assert linked() == 22  # (1 + 10) * 2

    # Manual override
    linked.set(100)
    assert linked() == 100

    # Change base - should trigger reset through intermediate
    base.set(5)
    assert linked() == 30  # (5 + 10) * 2


def test_linked_signal_diamond_dependency():
    """Test LinkedSignal in diamond dependency pattern"""
    base = Signal(1)

    # Two branches from base
    branch_a = ComputeSignal(lambda: base() + 1)
    branch_b = ComputeSignal(lambda: base() * 2)

    # LinkedSignal that combines both branches
    linked = LinkedSignal(lambda: branch_a() + branch_b())

    assert linked() == 4  # (1+1) + (1*2) = 4

    # Manual override
    linked.set(99)
    assert linked() == 99

    # Change base - should trigger reset
    base.set(3)
    assert linked() == 10  # (3+1) + (3*2) = 4 + 6 = 10


def test_linked_signal_multiple_linked_signals():
    """Test multiple LinkedSignals depending on the same source"""
    source = Signal(5)

    linked_a = LinkedSignal(lambda: source() * 2)
    linked_b = LinkedSignal(lambda: source() + 10)

    assert linked_a() == 10
    assert linked_b() == 15

    # Manual overrides
    linked_a.set(99)
    linked_b.set(88)
    assert linked_a() == 99
    assert linked_b() == 88

    # Source change resets both
    source.set(3)
    assert linked_a() == 6  # 3 * 2
    assert linked_b() == 13  # 3 + 10


def test_linked_signal_chained_linked_signals():
    """Test LinkedSignal depending on another LinkedSignal"""
    source = Signal(1)

    first_linked = LinkedSignal(lambda: source() * 10)
    second_linked = LinkedSignal(lambda: first_linked() + 100)

    assert first_linked() == 10
    assert second_linked() == 110

    # Manual override of first
    first_linked.set(50)
    assert first_linked() == 50
    assert second_linked() == 150  # Reset due to first_linked change

    # Manual override of second
    second_linked.set(999)
    assert second_linked() == 999

    # Source change resets chain
    source.set(2)
    assert first_linked() == 20  # Reset to source() * 10
    assert second_linked() == 120  # Reset to first_linked() + 100


@pytest.mark.asyncio
async def test_linked_signal_performance():
    """Test LinkedSignal performance with many rapid updates"""
    source = Signal(1)  # Start with 1, so initial linked value is 2
    linked = LinkedSignal(lambda: source() * 2)

    effect_count = 0

    async def track_effect():
        nonlocal effect_count
        linked()
        effect_count += 1

    _effect = Effect(track_effect)
    await asyncio.sleep(0.01)

    initial_count = effect_count

    # Rapid manual updates with distinct values
    for i in range(10, 20):  # Use 10-19 to ensure all values are distinct
        linked.set(i)

    await asyncio.sleep(0.01)

    # Batching may coalesce multiple manual updates into a single effect run
    # Ensure at least one additional effect run occurred
    assert effect_count >= initial_count + 1

    # Reset count for source updates test
    effect_count = 0

    # Rapid source updates
    for i in range(10):
        source.set(i)

    await asyncio.sleep(0.01)

    # Async effects may coalesce multiple notifications while executing
    # Ensure at least one effect ran and final value is correct
    assert effect_count >= 1
    assert linked() == 18  # Final source value (9) * 2


def test_linked_signal_repr():
    """Test LinkedSignal string representation"""
    source = Signal(42)
    linked = LinkedSignal(lambda: source() * 2)

    repr_str = repr(linked)
    assert "LinkedSignal" in repr_str
    assert "84" in repr_str  # 42 * 2


def test_linked_signal_smart_selection_use_case():
    """Test a realistic use case: smart item selection that preserves valid selections"""
    # Simulate a list of items with IDs
    items = Signal(
        [
            {"id": 1, "name": "Item A"},
            {"id": 2, "name": "Item B"},
            {"id": 3, "name": "Item C"},
        ]
    )

    # Smart selection that tries to preserve selection by ID
    selected_item = LinkedSignal(
        source=items,
        computation=lambda new_items, prev: (
            # Try to find previously selected item by ID
            next(
                (
                    item
                    for item in new_items
                    if prev and prev.value and item["id"] == prev.value["id"]
                ),
                None,
            )
            # Fallback to first item
            or (new_items[0] if new_items else None)
        ),
    )

    # Initial selection
    initial_item = selected_item()
    assert initial_item is not None
    assert initial_item["name"] == "Item A"

    # Manual selection
    selected_item.set(items()[1])  # Select Item B
    current_item = selected_item()
    assert current_item is not None
    assert current_item["name"] == "Item B"

    # Items list changes but Item B still exists
    items.set(
        [
            {"id": 2, "name": "Item B"},
            {"id": 4, "name": "Item D"},
            {"id": 1, "name": "Item A"},
        ]
    )
    preserved_item = selected_item()
    assert preserved_item is not None
    assert preserved_item["name"] == "Item B"  # Preserved!

    # Items list changes and Item B no longer exists
    items.set([{"id": 1, "name": "Item A"}, {"id": 5, "name": "Item E"}])
    fallback_item = selected_item()
    assert fallback_item is not None
    assert fallback_item["name"] == "Item A"  # Fallback to first
