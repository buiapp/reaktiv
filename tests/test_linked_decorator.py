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


def test_linked_model_computation_uses_manual_previous_and_source():
    from reaktiv import ReactiveModel, field, linked

    class Model(ReactiveModel):
        options = field([1, 2, 3])

        def keep_selection(self, source, previous):
            return previous.value if previous is not None and previous.value in source else source[0]

        @linked(computation=keep_selection)
        def selected(self):
            return self.options()

    first, second = Model(), Model()
    assert first.selected() == second.selected() == 1
    first.selected.set(2)
    first.options.set([2, 3])
    assert first.selected() == 2
    first.options.set([3, 4])
    assert first.selected() == 3
    assert second.selected() == 1


def test_linked_previous_none_is_a_value_not_initial_state():
    from reaktiv import linked
    source = Signal(1)
    seen = []

    def compute(current, previous):
        seen.append(previous)
        return None

    value = linked(source=source, computation=compute)
    assert value() is None
    source.set(2)
    assert value() is None
    assert seen[0] is None
    assert seen[1].value is None
    assert seen[1].source == 1


def test_typed_linked_model_computation_and_weak_owner():
    import gc
    import weakref
    from reaktiv import ReactiveModel, field, linked

    class Model(ReactiveModel):
        limit = field(10)

        def clamp(self, source, previous) -> int:
            return 1 if previous is None else min(previous.value, source)

        @linked[int](computation=clamp)
        def page(self):
            return self.limit()

    model = Model()
    node = model.page
    assert node() == 1
    node.set(8)
    model.limit.set(5)
    assert node() == 5
    owner = weakref.ref(model)
    del model
    gc.collect()
    assert owner() is None


def test_linked_previous_state_survives_failed_source_and_computation():
    import pytest
    from reaktiv import linked
    source = Signal(1)

    def compute(current, previous):
        if current == 2:
            raise ValueError('failed computation')
        return current if previous is None else previous.value + current

    def read_source():
        current = source()
        if current == 4:
            raise ValueError('failed source')
        return current

    value = linked(source=read_source, computation=compute)
    assert value() == 1
    value.set(10)
    source.set(2)
    with pytest.raises(ValueError):
        value()
    source.set(3)
    assert value() == 13
    source.set(4)
    with pytest.raises(ValueError, match='failed source'):
        value()
    source.set(5)
    assert value() == 18


def test_parameterized_linked_decorator_on_plain_function():
    from reaktiv import linked, signal

    source = signal(3)

    @linked(computation=lambda current, previous: current * 10)
    def scaled():
        return source()

    assert scaled() == 30
    scaled.set(1)
    source.set(4)
    assert scaled() == 40


def test_linked_method_computation_does_not_depend_on_parameter_names():
    from reaktiv import ReactiveModel, field, linked

    def increment(owner, current, previous):
        return current + owner.step()

    class Model(ReactiveModel):
        step = field(1)
        count = field(1)

        @linked(computation=increment)
        def next_count(self):
            return self.count()

    model = Model()
    assert model.next_count() == 2
    model.count.set(5)
    assert model.next_count() == 6
