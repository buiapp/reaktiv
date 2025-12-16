"""Tests for Linked decorator with proper type inference."""

from reaktiv import Signal, Linked, Effect


def test_linked_decorator_basic() -> None:
    """Test basic @Linked decorator usage."""
    source = Signal(5)

    @Linked
    def derived() -> int:
        return source() * 2

    assert derived() == 10

    # Can be read like computed
    source.set(10)
    assert derived() == 20

    # Can be manually set like signal
    derived.set(100)
    assert derived() == 100

    # Resets when source changes
    source.set(15)
    assert derived() == 30


def test_linked_decorator_with_equality() -> None:
    """Test @Linked decorator with custom equality function."""
    source = Signal(5)

    def int_equal(a: int, b: int) -> bool:
        return a == b

    @Linked(equal=int_equal)
    def derived() -> int:
        return source() * 2

    assert derived() == 10

    # Manual set
    derived.set(50)
    assert derived() == 50


def test_linked_factory_basic() -> None:
    """Test Linked as a factory function."""
    source = Signal(5)
    derived = Linked(lambda: source() * 2)

    assert derived() == 10
    source.set(10)
    assert derived() == 20

    derived.set(100)
    assert derived() == 100


def test_linked_factory_with_equality() -> None:
    """Test Linked factory with custom equality."""
    source = Signal(5)

    def int_equal(a: int, b: int) -> bool:
        return a == b

    derived = Linked(lambda: source() * 2, equal=int_equal)

    assert derived() == 10
    derived.set(50)
    assert derived() == 50


def test_linked_decorator_with_effect() -> None:
    """Test that decorated linked signals work with effects."""
    source = Signal(5)
    effect_values = []

    @Linked
    def derived() -> int:
        return source() * 2

    def track_derived():
        effect_values.append(derived())

    _eff = Effect(track_derived)

    assert effect_values == [10]

    # Manual set triggers effect
    derived.set(100)
    assert effect_values == [10, 100]

    # Source change triggers reset and effect
    source.set(10)
    assert effect_values == [10, 100, 20]


def test_linked_decorator_manual_override() -> None:
    """Test that manual values persist until source changes."""
    source = Signal(0)

    @Linked
    def counter() -> int:
        return source()

    assert counter() == 0

    # Manually increment
    counter.set(5)
    assert counter() == 5

    # Manual value persists
    assert counter() == 5

    # Source change resets to source value
    source.set(1)
    assert counter() == 1


def test_linked_decorator_chaining() -> None:
    """Test chaining multiple linked signals."""
    base = Signal(1)

    @Linked
    def first() -> int:
        return base() * 2

    @Linked
    def second() -> int:
        return first() * 3

    assert second() == 6

    # Manual override in chain
    first.set(10)
    assert second() == 30

    # Base change resets the chain
    base.set(2)
    assert first() == 4
    assert second() == 12


def test_linked_decorator_complex_type() -> None:
    """Test decorator with complex return types."""
    items = Signal([1, 2, 3])

    @Linked
    def processed() -> list:
        return [x * 2 for x in items()]

    assert processed() == [2, 4, 6]

    # Manual override
    processed.set([10, 20, 30])
    assert processed() == [10, 20, 30]

    # Reset on source change
    items.set([5, 6])
    assert processed() == [10, 12]


def test_linked_decorator_string_type() -> None:
    """Test decorator with string return type."""
    name = Signal("Alice")

    @Linked
    def greeting() -> str:
        return f"Hello, {name()}!"

    assert greeting() == "Hello, Alice!"

    greeting.set("Custom greeting")
    assert greeting() == "Custom greeting"

    name.set("Bob")
    assert greeting() == "Hello, Bob!"


def test_linked_update_method() -> None:
    """Test that update method works with decorated linked signals."""
    source = Signal(5)

    @Linked
    def counter() -> int:
        return source()

    # Access to initialize
    assert counter() == 5

    # Update using function
    counter.update(lambda x: x + 10)
    assert counter() == 15

    # Reset on source change
    source.set(0)
    assert counter() == 0


def test_linked_decorator_none_return() -> None:
    """Test decorator that returns None."""
    trigger = Signal(0)

    @Linked
    def nullable() -> None:
        trigger()  # Access signal to create dependency
        return None

    assert nullable() is None

    nullable.set(None)
    assert nullable() is None


def test_linked_decorator_dict_return() -> None:
    """Test decorator with dict return type."""
    x = Signal(1)
    y = Signal(2)

    @Linked
    def point() -> dict:
        return {"x": x(), "y": y()}

    assert point() == {"x": 1, "y": 2}

    point.set({"x": 10, "y": 20})
    assert point() == {"x": 10, "y": 20}

    x.set(5)
    # Should reset to computed value
    assert point() == {"x": 5, "y": 2}
