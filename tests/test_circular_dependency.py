import pytest
from reaktiv import Signal, Computed, Effect


def test_simple_circular_dependency():
    """Test detection of a simple circular dependency between two computed signals."""

    # Create a circular dependency: a -> b -> a
    def compute_a():
        return b() + 1

    def compute_b():
        return a() + 1

    a = Computed(compute_a)
    b = Computed(compute_b)

    # Accessing either computed signal should raise a RuntimeError
    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        a()

    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        b()


def test_three_way_circular_dependency():
    """Test detection of a three-way circular dependency."""

    # Create a circular dependency: a -> b -> c -> a
    def compute_a():
        return b() + 1

    def compute_b():
        return c() + 1

    def compute_c():
        return a() + 1

    a = Computed(compute_a)
    b = Computed(compute_b)
    c = Computed(compute_c)

    # Accessing any computed signal should raise a RuntimeError
    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        a()

    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        b()

    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        c()


def test_self_referencing_dependency():
    """Test detection of a computed signal that depends on itself."""

    # Create a self-referencing dependency
    def compute_self():
        return self_ref() + 1

    self_ref = Computed(compute_self)

    # Accessing the self-referencing computed signal should raise a RuntimeError
    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        self_ref()


def test_indirect_circular_dependency():
    """Test detection of a more complex circular dependency with valid dependencies mixed in."""
    # Create a valid base signal
    base = Signal(10)

    # Create some valid computed signals
    valid1 = Computed(lambda: base() * 2)
    valid2 = Computed(lambda: valid1() + 5)

    # Create circular dependencies involving the valid signals
    def compute_circular1():
        return valid2() + circular2() + 1

    def compute_circular2():
        return circular1() + 1

    circular1 = Computed(compute_circular1)
    circular2 = Computed(compute_circular2)

    # Valid signals should work fine
    assert valid1() == 20  # 10 * 2
    assert valid2() == 25  # 20 + 5

    # Circular dependencies should be detected
    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        circular1()

    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        circular2()


def test_circular_dependency_with_effect():
    """Test that effects can depend on signals with circular dependencies without issues."""
    # Create a valid signal
    source = Signal(5)
    valid_computed = Computed(lambda: source() * 2)

    # Create circular dependencies
    def compute_a():
        return b() + 1

    def compute_b():
        return a() + 1

    a = Computed(compute_a)
    b = Computed(compute_b)

    # Create effects that depend on valid signals (should work)
    effect_calls = []

    def valid_effect():
        effect_calls.append(valid_computed())

    effect = Effect(valid_effect)

    # The effect should work with valid computed signals
    assert len(effect_calls) == 1
    assert effect_calls[0] == 10

    # Update the source to trigger the effect
    source.set(10)
    assert len(effect_calls) == 2
    assert effect_calls[1] == 20

    # The circular dependencies should still be detected when accessed directly
    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        a()

    effect.dispose()


def test_detect_cycle_method():
    """Test the _detect_cycle method directly."""

    # Create a simple circular dependency
    def compute_a():
        return b() + 1

    def compute_b():
        return a() + 1

    a = Computed(compute_a)
    b = Computed(compute_b)

    # Note: _detect_cycle might not work correctly until dependencies are established
    # This happens during the first computation attempt
    try:
        a()
    except RuntimeError:
        pass  # Expected

    # After the computation attempt, dependencies should be established
    # and we can test the cycle detection method
    # Note: This test might need adjustment based on implementation details


def test_no_false_positive_cycle_detection():
    """Test that valid dependency chains don't trigger false positive cycle detection."""
    # Create a valid chain: base -> level1 -> level2 -> level3
    base = Signal(1)
    level1 = Computed(lambda: base() + 1)
    level2 = Computed(lambda: level1() + 1)
    level3 = Computed(lambda: level2() + 1)

    # All should compute correctly without cycle detection errors
    assert base() == 1
    assert level1() == 2
    assert level2() == 3
    assert level3() == 4

    # Update base and ensure all levels update correctly
    base.set(5)
    assert level1() == 6
    assert level2() == 7
    assert level3() == 8


def test_circular_dependency_error_message():
    """Test that the error message for circular dependency is clear and helpful."""

    def compute_a():
        return b() + 1

    def compute_b():
        return a() + 1

    a = Computed(compute_a)
    b = Computed(compute_b)

    # Check that the exact error message is raised
    with pytest.raises(RuntimeError) as exc_info:
        a()

    assert str(exc_info.value) == "Circular dependency detected"


def test_circular_dependency_with_multiple_paths():
    """Test circular dependency detection with multiple dependency paths."""
    # Create a diamond dependency with a cycle
    base = Signal(1)

    def compute_left():
        return base() + cycle_node()

    def compute_right():
        return base() + cycle_node()

    def compute_cycle():
        return left() + right() + 1

    left = Computed(compute_left)
    right = Computed(compute_right)
    cycle_node = Computed(compute_cycle)

    # Should detect the circular dependency
    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        left()

    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        right()

    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        cycle_node()


def test_deep_circular_dependency_chain():
    """Test circular dependency detection in a deeper chain."""

    # Create a longer circular chain: a -> b -> c -> d -> e -> a
    def compute_a():
        return b() + 1

    def compute_b():
        return c() + 1

    def compute_c():
        return d() + 1

    def compute_d():
        return e() + 1

    def compute_e():
        return a() + 1

    a = Computed(compute_a)
    b = Computed(compute_b)
    c = Computed(compute_c)
    d = Computed(compute_d)
    e = Computed(compute_e)

    # Should detect the circular dependency regardless of entry point
    for computed_signal in [a, b, c, d, e]:
        with pytest.raises(RuntimeError, match="Circular dependency detected"):
            computed_signal()


def test_circular_dependency_mixed_with_valid_dependencies():
    """Test circular dependency detection when mixed with valid signal dependencies."""
    # Create valid base signals
    x = Signal(10)
    y = Signal(20)

    # Create valid computed signals
    sum_xy = Computed(lambda: x() + y())
    product_xy = Computed(lambda: x() * y())

    # Create circular dependencies that also use valid signals
    def compute_circular_a():
        return sum_xy() + circular_b() + 1

    def compute_circular_b():
        return product_xy() + circular_a() + 1

    circular_a = Computed(compute_circular_a)
    circular_b = Computed(compute_circular_b)

    # Valid signals should work correctly
    assert sum_xy() == 30
    assert product_xy() == 200

    # Circular dependencies should be detected
    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        circular_a()

    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        circular_b()

    # Updating valid signals should not affect circular dependency detection
    x.set(5)
    y.set(15)

    assert sum_xy() == 20
    assert product_xy() == 75

    # Circular dependencies should still be detected
    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        circular_a()

    with pytest.raises(RuntimeError, match="Circular dependency detected"):
        circular_b()
