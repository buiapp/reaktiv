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
    # Equal within tolerance: the previously published value is kept
    assert computed.get() == 10.0
    await asyncio.sleep(0)
    # No effect notification due to custom equality within tolerance
    assert notifications == []

    # Reset notifications list for clarity
    notifications.clear()

    # Change outside tolerance (101 -> 112) => 10.0 -> 11.2
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


# ---------------------------------------------------------------------------
# Equality semantics shared with Angular and Solid: equal() == True keeps the
# previously published value, for signals, computed and linked recomputation.
# ---------------------------------------------------------------------------

def _tolerance(a, b):
    return abs(a - b) < 0.1


def test_equal_computed_keeps_published_value_for_every_reader():
    from reaktiv import computed, signal

    source = signal(0.0)
    value = computed(lambda: source(), equal=_tolerance)
    runs = []
    downstream = computed(lambda: runs.append(1) or value())
    assert downstream() == 0.0
    source.set(0.05)
    assert value() == 0.0
    assert downstream() == 0.0
    assert len(runs) == 1


def test_tolerance_compares_against_published_value_so_drift_is_reported():
    from reaktiv import computed, signal

    source = signal(0.0)
    value = computed(lambda: source(), equal=_tolerance)
    seen = [value()]
    for step in (0.06, 0.12, 0.18, 0.24):
        source.set(step)
        seen.append(value())
    assert seen == [0.0, 0.0, 0.12, 0.12, 0.24]


def test_equal_linked_recomputation_keeps_published_value():
    from reaktiv import computed, linked, signal

    source = signal(0.0)
    value = linked(source=source, computation=lambda current, previous: current, equal=_tolerance)
    downstream = computed(lambda: value())
    assert downstream() == 0.0
    source.set(0.05)
    assert value() == 0.0
    assert downstream() == 0.0
    value.set(0.08)  # manual writes use the same rule
    assert value() == 0.0


def test_equal_is_not_called_for_the_first_value():
    from reaktiv import computed, signal

    calls = []
    source = signal(1)
    value = computed(lambda: source(), equal=lambda a, b: calls.append((a, b)) or False)
    assert value() == 1
    assert calls == []


def test_in_place_mutation_is_never_detected_even_with_value_equality():
    from reaktiv import computed, signal
    from reaktiv.subtle import signal_version

    items = signal([1, 2, 3], equal=lambda a, b: a == b)
    size = computed(lambda: len(items()))
    assert size() == 3
    current = items()
    current.append(4)
    items.set(current)  # equal() receives the same, already mutated list twice
    assert signal_version(items) == 0
    assert size() == 3
    items.update(lambda xs: [*xs, 5])  # copy-on-write is detected
    assert size() == 5


def _boom(a, b):
    raise ValueError("bad comparison")


def test_raising_equal_on_set_propagates_and_keeps_the_old_value():
    from reaktiv import signal

    value = signal(1, equal=_boom)
    with pytest.raises(ValueError, match="bad comparison"):
        value.set(2)
    assert value() == 1
    with pytest.raises(ValueError, match="bad comparison"):
        value.update(lambda current: current + 1)
    assert value() == 1


def test_raising_equal_in_computed_becomes_its_error_and_recovers():
    from reaktiv import computed, signal

    source = signal(1)
    calls = []

    def compare(a, b):
        calls.append((a, b))
        if b == 2:
            raise ValueError("bad comparison")
        return a == b

    value = computed(lambda: source(), equal=compare)
    assert value() == 1
    source.set(2)
    with pytest.raises(ValueError, match="bad comparison"):
        value()
    source.set(3)
    assert value() == 3  # not compared against the error
    assert calls == [(1, 2)]


@pytest.mark.asyncio
async def test_raising_equal_while_publishing_a_resource_value_is_a_load_error():
    from reaktiv import ResourceStatus, resource, signal

    params = signal(1)

    async def load(request):
        return request.params

    def compare(a, b):
        if b == 2:
            raise ValueError("bad comparison")
        return a == b

    res = resource(params=lambda: params(), loader=load, equal=compare)
    await asyncio.sleep(0.01)
    assert res.value() == 1
    params.set(2)
    await asyncio.sleep(0.01)
    assert res.status() == ResourceStatus.ERROR
    assert isinstance(res.error(), ValueError)
    with pytest.raises(ValueError, match="bad comparison"):
        res.set(2)  # local writes raise like signal.set
    res.dispose()


def test_computed_rejects_update_like_set():
    from reaktiv import computed, signal

    source = signal(2)
    doubled = computed(lambda: source() * 2)
    assert doubled() == 4

    with pytest.raises(AttributeError):
        doubled.update(lambda _: 99)
    with pytest.raises(AttributeError):
        doubled.set(99)
    assert doubled() == 4


def test_linked_computation_cannot_write_but_explicit_untracked_can():
    from reaktiv import computed, effect, linked, signal, untracked

    source = signal(2)
    other = signal(0)
    advanced = linked(
        source=source,
        computation=lambda current, previous: other.set(current) or current,
    )
    with pytest.raises(RuntimeError, match="Side effect"):
        advanced()

    assert other() == 0
    with pytest.raises(RuntimeError, match="Side effect"):
        computed(lambda: other.set(5) or 1)()

    # An explicit untracked() block is the escape hatch, as in Angular: it may
    # write, e.g. to initialize a signal lazily on first read.
    lazy = signal(None)
    initialized = computed(lambda: untracked(lambda: lazy.set("ready")) or lazy())
    assert initialized() == "ready"

    # An effect created inside a computation runs as an effect: it may write.
    written = signal(0)
    holder = []

    def make_effect():
        holder.append(effect(lambda: written.set(7)))
        return 1

    computed(make_effect)()
    assert written() == 7
    holder[0].dispose()
