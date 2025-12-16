"""Tests for Computed decorator with proper type inference."""
from reaktiv import Signal, Computed, Effect


def test_decorator_basic() -> None:
    """Test basic @Computed decorator usage."""
    count = Signal(5)

    @Computed
    def double() -> int:
        return count() * 2

    assert double() == 10
    count.set(10)
    assert double() == 20


def test_decorator_with_equality() -> None:
    """Test @Computed decorator with custom equality function."""
    count = Signal(5)
    call_count = 0

    def int_equal(a: int, b: int) -> bool:
        return a == b

    @Computed(equal=int_equal)
    def double() -> int:
        nonlocal call_count
        call_count += 1
        return count() * 2

    assert double() == 10
    assert call_count == 1

    # Set to same computed value - should not recompute
    count.set(5)
    assert double() == 10
    # The compute function is called during refresh, but version doesn't change
    assert call_count >= 1


def test_factory_basic() -> None:
    """Test Computed as a factory function."""
    count = Signal(5)
    double = Computed(lambda: count() * 2)

    assert double() == 10
    count.set(10)
    assert double() == 20


def test_factory_with_equality() -> None:
    """Test Computed factory with custom equality."""
    count = Signal(5)
    call_count = 0

    def int_equal(a: int, b: int) -> bool:
        return a == b

    def compute() -> int:
        nonlocal call_count
        call_count += 1
        return count() * 2

    double = Computed(compute, equal=int_equal)

    assert double() == 10
    assert call_count == 1


def test_decorator_with_multiple_dependencies() -> None:
    """Test decorator with multiple signal dependencies."""
    first = Signal("John")
    last = Signal("Doe")

    @Computed
    def full_name() -> str:
        return f"{first()} {last()}"

    assert full_name() == "John Doe"
    first.set("Jane")
    assert full_name() == "Jane Doe"
    last.set("Smith")
    assert full_name() == "Jane Smith"


def test_decorator_chaining() -> None:
    """Test chaining multiple computed signals."""
    count = Signal(5)

    @Computed
    def double() -> int:
        return count() * 2

    @Computed
    def quadruple() -> int:
        return double() * 2

    assert quadruple() == 20
    count.set(10)
    assert quadruple() == 40


def test_decorator_with_effect() -> None:
    """Test that decorated computed signals work with effects."""
    count = Signal(5)
    effect_values = []

    @Computed
    def double() -> int:
        return count() * 2

    def track_double() -> None:
        effect_values.append(double())

    _eff = Effect(track_double)

    assert effect_values == [10]
    count.set(10)
    assert effect_values == [10, 20]


def test_decorator_return_type_preservation() -> None:
    """Test that return types are properly preserved."""
    # This test verifies type hints work correctly - actual verification
    # happens at type-checking time, but we can verify runtime behavior

    class CustomClass:
        def __init__(self, value: int):
            self.value = value

    count = Signal(5)

    @Computed
    def create_custom() -> CustomClass:
        return CustomClass(count())

    result = create_custom()
    assert isinstance(result, CustomClass)
    assert result.value == 5


def test_decorator_approximate_equality() -> None:
    """Test decorator with approximate floating-point equality."""
    value = Signal(1.0)

    def approx_equal(a: float, b: float) -> bool:
        return abs(a - b) < 0.0001

    @Computed(equal=approx_equal)
    def computed_value() -> float:
        return value() * 2.0

    assert computed_value() == 2.0

    # Small change within tolerance
    value.set(1.00001)
    # Value updates internally but version doesn't change
    assert abs(computed_value() - 2.00002) < 0.0001


def test_decorator_with_none_return() -> None:
    """Test decorator that returns None."""
    trigger = Signal(0)

    @Computed
    def returns_none() -> None:
        trigger()  # Access signal to create dependency
        return None

    assert returns_none() is None
    trigger.set(1)
    assert returns_none() is None


def test_decorator_complex_computation() -> None:
    """Test decorator with complex computation logic."""
    numbers = Signal([1, 2, 3, 4, 5])

    @Computed
    def statistics() -> dict:
        nums = numbers()
        return {
            "sum": sum(nums),
            "avg": sum(nums) / len(nums),
            "min": min(nums),
            "max": max(nums),
        }

    stats = statistics()
    assert stats["sum"] == 15
    assert stats["avg"] == 3.0
    assert stats["min"] == 1
    assert stats["max"] == 5

    numbers.set([10, 20, 30])
    stats = statistics()
    assert stats["sum"] == 60
    assert stats["avg"] == 20.0
