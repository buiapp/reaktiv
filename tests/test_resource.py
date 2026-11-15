"""Tests for Resource."""

import asyncio
import pytest
import pytest_asyncio
from reaktiv import (
    Signal,
    Resource,
    ResourceStatus,
    Computed,
    ComputeSignal,
    Effect,
    Linked,
    LinkedSignal,
    is_thread_safety_enabled,
    set_thread_safety,
    to_async_iter,
    untracked,
)


# Store all resources created in tests for cleanup
_resources = []


@pytest_asyncio.fixture(autouse=True)
async def cleanup_resources():
    """Automatically clean up resources after each test."""
    _resources.clear()
    yield
    # Cancel all pending tasks from resources
    for resource in _resources:
        resource.destroy()
    # Give tasks time to cancel
    await asyncio.sleep(0.01)


def create_resource(*args, **kwargs):
    """Helper to create and track resources for cleanup."""
    resource = Resource(*args, **kwargs)
    _resources.append(resource)
    return resource


@pytest.mark.asyncio
async def test_resource_basic_loading():
    """Test basic resource loading functionality."""
    user_id = Signal("user123")
    load_count = 0

    async def fetch_user(params):
        nonlocal load_count
        load_count += 1
        await asyncio.sleep(0.01)  # Simulate network delay
        return {"id": params.params["id"], "name": f"User {params.params['id']}"}

    user_resource = create_resource(
        params=lambda: {"id": user_id()}, loader=lambda p: fetch_user(p)
    )

    # Initially should be loading
    assert user_resource.status() == ResourceStatus.LOADING
    assert user_resource.is_loading()
    assert not user_resource.has_value()

    # Wait for load to complete
    await asyncio.sleep(0.05)

    # Should be resolved
    assert user_resource.status() == ResourceStatus.RESOLVED
    assert not user_resource.is_loading()
    assert user_resource.has_value()
    assert user_resource.value()["id"] == "user123"
    assert user_resource.value()["name"] == "User user123"
    assert load_count == 1


@pytest.mark.asyncio
async def test_resource_params_change():
    """Test resource reloads when params change."""
    user_id = Signal("user1")
    load_count = 0

    async def fetch_user(params):
        nonlocal load_count
        load_count += 1
        await asyncio.sleep(0.01)
        return {"id": params.params["id"], "name": f"User {params.params['id']}"}

    user_resource = create_resource(
        params=lambda: {"id": user_id()}, loader=lambda p: fetch_user(p)
    )

    # Wait for initial load
    await asyncio.sleep(0.05)
    assert user_resource.value()["id"] == "user1"
    assert load_count == 1

    # Change params
    user_id.set("user2")
    assert user_resource.status() == ResourceStatus.LOADING

    # Wait for new load
    await asyncio.sleep(0.05)
    assert user_resource.value()["id"] == "user2"
    assert user_resource.status() == ResourceStatus.RESOLVED
    assert load_count == 2


@pytest.mark.asyncio
async def test_resource_reloads_for_each_param_change_with_async_iterator_subscriber():
    """Resource params should keep reloading after prior graph/effect activity."""
    original_thread_safety = is_thread_safety_enabled()
    set_thread_safety(True)

    _run_prior_public_graph_workload()

    project_id = Signal("project-0")
    loads: list[str] = []

    async def fetch_project(params):
        loads.append(params.params["id"])
        await asyncio.sleep(0)
        return {"id": params.params["id"]}

    try:
        project_resource = create_resource(
            params=lambda: {"id": project_id()},
            loader=lambda p: fetch_project(p),
        )

        iterations = 25
        observed_task = asyncio.create_task(
            _collect_values(project_id, expected=iterations)
        )

        await _wait_for(
            lambda: (
                project_resource.status() == ResourceStatus.RESOLVED
                and project_resource.value()["id"] == "project-0"
            )
        )

        for index in range(1, iterations + 1):
            expected = f"project-{index}"
            project_id.set(expected)
            await _wait_for(lambda: project_resource.status() == ResourceStatus.RESOLVED)

        observed = await observed_task

        await _wait_for(
            lambda: (
                project_resource.status() == ResourceStatus.RESOLVED
                and project_resource.value()["id"] == "project-25"
            )
        )

        assert observed == [f"project-{index}" for index in range(1, iterations + 1)]
        assert loads == [f"project-{index}" for index in range(0, iterations + 1)]
    finally:
        set_thread_safety(original_thread_safety)


@pytest.mark.asyncio
async def test_resource_manual_reload():
    """Test manual reload functionality."""
    user_id = Signal("user1")
    load_count = 0

    async def fetch_user(params):
        nonlocal load_count
        load_count += 1
        await asyncio.sleep(0.01)
        return {"id": params.params["id"], "count": load_count}

    user_resource = create_resource(
        params=lambda: {"id": user_id()}, loader=lambda p: fetch_user(p)
    )

    # Wait for initial load
    await asyncio.sleep(0.05)
    assert user_resource.value()["count"] == 1
    assert load_count == 1

    # Manual reload without changing params
    user_resource.reload()
    assert user_resource.status() == ResourceStatus.RELOADING

    # Wait for reload
    await asyncio.sleep(0.05)
    assert user_resource.value()["count"] == 2
    assert user_resource.status() == ResourceStatus.RESOLVED
    assert load_count == 2


@pytest.mark.asyncio
async def test_resource_abort_on_params_change():
    """Test that ongoing requests are aborted when params change."""
    user_id = Signal("user1")
    completed_loads = []

    async def fetch_user(params):
        user_id = params.params["id"]
        try:
            await asyncio.sleep(0.1)  # Long delay
            completed_loads.append(user_id)
            return {"id": user_id, "name": f"User {user_id}"}
        except asyncio.CancelledError:
            # This won't be caught by our AbortSignal, but shows the pattern
            raise

    user_resource = create_resource(
        params=lambda: {"id": user_id()}, loader=lambda p: fetch_user(p)
    )

    # Start loading user1
    await asyncio.sleep(0.01)

    # Change params before first load completes (should abort)
    user_id.set("user2")
    await asyncio.sleep(0.01)

    # Change again
    user_id.set("user3")

    # Wait for all to potentially complete
    await asyncio.sleep(0.2)

    # Only the last request should have completed
    # (Note: abort behavior depends on how the loader handles abort_signal)
    assert user_resource.value()["id"] == "user3"
    
    # Give cancelled tasks time to clean up
    await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_resource_error_handling():
    """Test error handling in resource."""
    user_id = Signal("user1")

    async def fetch_user_with_error(params):
        await asyncio.sleep(0.01)
        if params.params["id"] == "error":
            raise ValueError("User not found")
        return {"id": params.params["id"], "name": f"User {params.params['id']}"}

    user_resource = create_resource(
        params=lambda: {"id": user_id()}, loader=lambda p: fetch_user_with_error(p)
    )

    # Wait for initial load
    await asyncio.sleep(0.05)
    assert user_resource.status() == ResourceStatus.RESOLVED

    # Trigger error
    user_id.set("error")
    await asyncio.sleep(0.05)

    assert user_resource.status() == ResourceStatus.ERROR
    assert user_resource.error() is not None
    assert isinstance(user_resource.error(), ValueError)
    assert not user_resource.has_value()

    # Reading value should throw
    with pytest.raises(ValueError):
        user_resource.value()


@pytest.mark.asyncio
async def test_resource_idle_state():
    """Test resource idle state when params is None."""
    user_id: Signal[str | None] = Signal(None)

    async def fetch_user(params):
        await asyncio.sleep(0.01)
        return {"id": params.params["id"]}

    user_resource = create_resource(
        params=lambda: {"id": user_id()} if user_id() is not None else None,
        loader=lambda p: fetch_user(p),
    )

    # Should be idle since params is None
    assert user_resource.status() == ResourceStatus.IDLE
    assert not user_resource.is_loading()

    # Set params to trigger load
    user_id.set("user1")
    await asyncio.sleep(0.05)

    assert user_resource.status() == ResourceStatus.RESOLVED
    assert user_resource.value()["id"] == "user1"

    # Set back to None
    user_id.set(None)
    assert user_resource.status() == ResourceStatus.IDLE


@pytest.mark.asyncio
async def test_resource_local_set():
    """Test setting resource value locally."""
    user_id = Signal("user1")

    async def fetch_user(params):
        await asyncio.sleep(0.01)
        return {"id": params.params["id"], "name": f"User {params.params['id']}"}

    user_resource = create_resource(
        params=lambda: {"id": user_id()}, loader=lambda p: fetch_user(p)
    )

    # Wait for initial load
    await asyncio.sleep(0.05)
    assert user_resource.status() == ResourceStatus.RESOLVED

    # Set value locally
    user_resource.set({"id": "local", "name": "Local User"})

    assert user_resource.status() == ResourceStatus.LOCAL
    assert user_resource.value()["id"] == "local"
    assert user_resource.value()["name"] == "Local User"


@pytest.mark.asyncio
async def test_resource_local_update():
    """Test updating resource value locally."""
    user_id = Signal("user1")

    async def fetch_user(params):
        await asyncio.sleep(0.01)
        return {"id": params.params["id"], "name": f"User {params.params['id']}"}

    user_resource = create_resource(
        params=lambda: {"id": user_id()}, loader=lambda p: fetch_user(p)
    )

    # Wait for initial load
    await asyncio.sleep(0.05)

    # Update value locally
    user_resource.update(lambda current: {**current, "name": "Updated Name"})

    assert user_resource.status() == ResourceStatus.LOCAL
    assert user_resource.value()["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_resource_with_computed():
    """Test using resource value in computed signals."""
    user_id = Signal("user1")

    async def fetch_user(params):
        await asyncio.sleep(0.01)
        return {"id": params.params["id"], "firstName": "John", "lastName": "Doe"}

    user_resource = create_resource(
        params=lambda: {"id": user_id()}, loader=lambda p: fetch_user(p)
    )

    # Create computed signal based on resource
    full_name = Computed(
        lambda: (
            f"{user_resource.value()['firstName']} {user_resource.value()['lastName']}"
            if user_resource.has_value()
            else "Loading..."
        )
    )

    # Initially should be loading
    assert full_name() == "Loading..."

    # Wait for load
    await asyncio.sleep(0.05)

    assert full_name() == "John Doe"


@pytest.mark.asyncio
async def test_resource_abort_signal_usage():
    """Test that cancellation is properly handled via asyncio.Event."""
    user_id = Signal("user1")
    load_count = 0
    cancelled = False

    async def fetch_user(params):
        nonlocal load_count, cancelled
        load_count += 1

        # Check cancellation in a loop
        for i in range(50):
            if params.cancellation.is_set():
                cancelled = True
                return None
            await asyncio.sleep(0.01)
        
        return {"id": params.params["id"]}

    _user_resource = create_resource(
        params=lambda: {"id": user_id()}, loader=lambda p: fetch_user(p)
    )

    # Wait for first load to start
    await asyncio.sleep(0.05)
    assert load_count >= 1

    # Change params to trigger cancellation
    user_id.set("user2")
    
    # Wait for cancellation to be detected
    await asyncio.sleep(0.2)

    assert cancelled


@pytest.mark.asyncio
async def test_resource_previous_state():
    """Test that previous state is passed to loader."""
    user_id = Signal("user1")
    previous_statuses = []

    async def fetch_user(params):
        previous_statuses.append(params.previous.status)
        await asyncio.sleep(0.01)
        return {"id": params.params["id"]}

    user_resource = create_resource(
        params=lambda: {"id": user_id()}, loader=lambda p: fetch_user(p)
    )

    # Wait for initial load
    await asyncio.sleep(0.05)

    # Change params
    user_id.set("user2")
    await asyncio.sleep(0.05)

    # Reload
    user_resource.reload()
    await asyncio.sleep(0.05)

    # Check previous statuses
    assert len(previous_statuses) >= 2
    # First load has IDLE as previous
    assert previous_statuses[0] == ResourceStatus.IDLE
    # Subsequent loads have RESOLVED or LOADING as previous


@pytest.mark.asyncio
async def test_resource_snapshot():
    """Test resource snapshot functionality."""
    user_id = Signal("user1")

    async def fetch_user(params):
        if params.params["id"] == "error":
            raise ValueError("Invalid user")
        await asyncio.sleep(0.01)
        return {"id": params.params["id"], "name": f"User {params.params['id']}"}

    user_resource = create_resource(
        params=lambda: {"id": user_id()},
        loader=lambda p: fetch_user(p)
    )

    # Wait for initial load
    await asyncio.sleep(0.05)

    # Get snapshot of resolved state
    snapshot = user_resource.snapshot()()
    assert snapshot.status == ResourceStatus.RESOLVED
    assert snapshot.value is not None
    assert snapshot.value["id"] == "user1"
    assert snapshot.error is None

    # Trigger error
    user_id.set("error")
    await asyncio.sleep(0.05)

    # Get snapshot of error state
    snapshot = user_resource.snapshot()()
    assert snapshot.status == ResourceStatus.ERROR
    assert snapshot.error is not None
    assert isinstance(snapshot.error, ValueError)


@pytest.mark.asyncio
async def test_resource_has_value():
    """Test resource has_value() method."""
    user_id = Signal("user1")

    async def fetch_user(params):
        if params.params["id"] == "error":
            raise ValueError("Invalid user")
        await asyncio.sleep(0.01)
        return {"id": params.params["id"]}

    user_resource = create_resource(
        params=lambda: {"id": user_id()},
        loader=lambda p: fetch_user(p)
    )

    # During loading, has_value should be False
    assert not user_resource.has_value()

    # Wait for load
    await asyncio.sleep(0.05)

    # After successful load, has_value should be True
    assert user_resource.has_value()

    # Trigger error
    user_id.set("error")
    await asyncio.sleep(0.05)

    # In error state, has_value should be False
    assert not user_resource.has_value()

    # Use has_value in a computed
    display = Computed(lambda: (
        user_resource.value()["id"]
        if user_resource.has_value()
        else "No data"
    ))

    assert display() == "No data"

    # Fix the error
    user_id.set("user2")
    await asyncio.sleep(0.05)

    assert user_resource.has_value()
    assert display() == "user2"


def test_resource_requires_asyncio_context():
    """Test that Resource raises error when created outside asyncio context."""
    user_id = Signal("user1")

    async def fetch_user(params):
        return {"id": params.params["id"]}

    # This should raise RuntimeError because we're not in an asyncio context
    with pytest.raises(RuntimeError, match="Resource must be created within an asyncio context"):
        Resource(
            params=lambda: {"id": user_id()},
            loader=lambda p: fetch_user(p)
        )


def _run_prior_public_graph_workload() -> None:
    price = Signal(1)
    quantity = Signal(2)
    tax = Signal(1)
    note = Signal("cold")

    subtotal = ComputeSignal(lambda: price() * quantity())

    @Computed
    def total():
        return subtotal() + tax()

    selected = LinkedSignal(lambda: total())

    @Linked
    def label():
        return f"{selected()}:{quantity()}"

    def effect_body():
        untracked(lambda: note())
        total()
        label()

    effect = Effect(effect_body)
    try:
        price.set(2)
        quantity.update(lambda value: value + 1)
        tax.set(2)
        selected.set(total())
    finally:
        effect.dispose()


async def _collect_values(signal, expected: int):
    values = []
    async for value in to_async_iter(signal, initial=False):
        values.append(value)
        if len(values) == expected:
            break
    return values


async def _wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("condition was not reached before timeout")


@pytest.mark.asyncio
async def test_resource_accepts_custom_value_equality():
    async def load(params):
        return 1.0

    resource = Resource(params=lambda: 1, loader=load, equal=lambda previous, current: abs(previous - current) < 0.1)
    resource.set(1.0)
    resource.set(1.05)
    assert resource.value() == 1.0
    resource.set(2.0)
    assert resource.value() == 2.0
    resource.destroy()


@pytest.mark.asyncio
async def test_resource_value_signal_preserves_always_changed_comparison():
    async def load(params):
        return []

    resource = Resource(params=lambda: None, loader=load, equal=lambda previous, current: False)
    value = [1]
    resource.set(value)
    values = resource.value
    runs = []
    observer = Effect(lambda: runs.append(values()))
    resource.set(value)
    assert len(runs) == 2
    observer.dispose()
    resource.destroy()


@pytest.mark.asyncio
async def test_cancel_suppresses_late_results_and_new_parameters_can_load():
    request = Signal(1)
    started, cleanup = asyncio.Event(), asyncio.Event()

    async def loader(context):
        if context.params == 1:
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                # Cancellation-resistant user code must not publish a late value.
                return 999
            finally:
                cleanup.set()
        return context.params * 10

    value = create_resource(params=request, loader=loader)
    await started.wait()
    cancellation = value.cancellation_event
    assert value.cancel()
    assert cancellation.is_set()
    assert value.status() == ResourceStatus.CANCELLED
    assert not value.is_loading() and not value.has_value()
    await asyncio.wait_for(cleanup.wait(), 1)
    await asyncio.sleep(0)
    assert value.value() is None
    assert not value.cancel()
    request.set(2)
    await asyncio.sleep(0)
    assert value.value() == 20 and value.status() == ResourceStatus.RESOLVED


@pytest.mark.asyncio
async def test_cancel_retains_last_value_and_reload_retries_the_same_parameters():
    release = asyncio.Event()
    calls = 0

    async def loader(context):
        nonlocal calls
        calls += 1
        if calls > 1:
            await release.wait()
        return calls

    value = create_resource(params=lambda: 'request', loader=loader)
    await asyncio.sleep(0)
    assert value.value() == 1
    value.reload()
    await asyncio.sleep(0)
    assert value.cancel()
    assert value.snapshot()().value == 1
    assert value.snapshot()().status == ResourceStatus.CANCELLED
    assert value.error() is None
    await asyncio.sleep(0)
    value.reload()
    release.set()
    await asyncio.sleep(0)
    assert value.value() == 3 and value.status() == ResourceStatus.RESOLVED


@pytest.mark.asyncio
async def test_cancel_before_loader_starts_does_not_run_user_code():
    calls = []

    async def loader(context):
        calls.append(context.params)
        return 1

    value = create_resource(params=lambda: 1, loader=loader)
    assert value.cancel()
    await asyncio.sleep(0)
    assert calls == [] and value.status() == ResourceStatus.CANCELLED


@pytest.mark.asyncio
async def test_resource_dispose_stops_params_tracking_and_late_results():
    from reaktiv import resource, signal

    params = signal(1)
    loads = []
    release = asyncio.Event()

    async def loader(request):
        loads.append(request.params)
        if request.params == 2:
            await release.wait()
        return request.params

    res = resource(params=lambda: params(), loader=loader)
    await asyncio.sleep(0.01)
    assert res.value() == 1

    params.set(2)
    await asyncio.sleep(0.01)
    res.dispose()
    release.set()
    await asyncio.sleep(0.01)
    assert res.value() == 1  # the in-flight result is never published
    assert res.status() == ResourceStatus.CANCELLED

    params.set(3)
    res.reload()
    await asyncio.sleep(0.01)
    assert loads == [1, 2]
    res.dispose()  # idempotent


@pytest.mark.asyncio
async def test_resource_destroy_is_an_alias_of_dispose():
    from reaktiv import resource, signal

    params = signal(1)
    loads = []

    async def loader(request):
        loads.append(request.params)
        return request.params

    res = resource(params=lambda: params(), loader=loader)
    await asyncio.sleep(0.01)
    res.destroy()
    params.set(2)
    await asyncio.sleep(0.01)
    assert loads == [1]


@pytest.mark.asyncio
async def test_rejected_resource_writes_leave_the_load_running():
    from reaktiv import computed, effect, resource, signal

    gate = asyncio.Event()
    params = signal(1)

    async def slow(request):
        await gate.wait()
        return 42

    res = resource(params=lambda: params(), loader=slow)
    await asyncio.sleep(0.01)
    calls = []
    with pytest.raises(RuntimeError, match="Side effect detected"):
        computed(lambda: res.set(5))()
    with pytest.raises(RuntimeError, match="Side effect detected"):
        computed(lambda: res.update(lambda v: calls.append(v) or 5))()
    assert calls == []
    gate.set()
    await asyncio.sleep(0.01)
    assert res.status() == ResourceStatus.RESOLVED
    assert res.value() == 42
    assert not res.is_loading()

    # update() does not subscribe the calling effect to the resource
    runs = []
    writer = effect(lambda: runs.append(params()) or res.update(lambda v: (v or 0) + 1))
    res.set(100)
    assert runs == [1]
    writer.dispose()
    res.dispose()


@pytest.mark.asyncio
async def test_resource_transitions_are_published_atomically():
    from reaktiv import effect, resource, signal

    params = signal(1)

    async def load(request):
        await asyncio.sleep(0)
        if request.params == 2:
            raise ValueError("failed")
        return request.params * 10

    res = resource(params=lambda: params(), loader=load)
    seen = []
    observer = effect(
        lambda: seen.append((res.status().value, res.value() if res.status() != ResourceStatus.ERROR else "error", res.is_loading()))
    )
    await asyncio.sleep(0.02)
    params.set(2)
    await asyncio.sleep(0.02)
    res.set(7)
    assert seen == [
        ("loading", None, True),
        ("resolved", 10, False),
        ("loading", 10, True),
        ("error", "error", False),
        ("local", 7, False),
    ]
    observer.dispose()
    res.dispose()


@pytest.mark.asyncio
async def test_resource_signal_handles_are_stable():
    from reaktiv import resource

    async def load(request):
        return 1

    res = resource(params=lambda: 1, loader=load)
    assert res.value is res.value
    assert res.status is res.status
    assert res.error is res.error
    assert res.is_loading is res.is_loading
    assert res.snapshot() is res.snapshot()
    await asyncio.sleep(0.01)
    assert res.value() == 1
    res.dispose()


@pytest.mark.asyncio
async def test_resource_params_changed_on_another_thread_load_on_its_loop():
    import threading

    from reaktiv import resource, signal

    params = signal(1)
    loads = []

    async def load(request):
        loads.append((request.params, threading.current_thread() is threading.main_thread()))
        return request.params

    res = resource(params=lambda: params(), loader=load)
    await asyncio.sleep(0.01)
    writer = threading.Thread(target=lambda: params.set(2))
    writer.start()
    writer.join()
    await asyncio.sleep(0.05)
    assert loads == [(1, True), (2, True)]
    assert res.status() == ResourceStatus.RESOLVED
    assert res.value() == 2
    res.dispose()


def test_params_changed_on_another_thread_cancel_a_waiting_loader_on_its_loop():
    import threading

    from reaktiv import resource, signal

    async def main():
        params = signal(1)
        loads, superseded = [], []

        async def load(request):
            loads.append(request.params)
            if request.params == 1:
                await request.cancellation.wait()  # wait until superseded
                superseded.append(threading.current_thread() is threading.main_thread())
                return "stale"
            return request.params

        res = resource(params=lambda: params(), loader=load)
        await asyncio.sleep(0.01)
        writer = threading.Thread(target=lambda: params.set(2))
        writer.start()
        writer.join()
        await asyncio.sleep(0.05)
        assert loads == [1, 2]
        assert superseded == [True]  # woken on the owner loop's thread
        assert res.status() == ResourceStatus.RESOLVED
        assert res.value() == 2  # the stale result was never published
        res.dispose()

    # Debug mode makes asyncio reject calls from the wrong thread.
    asyncio.run(main(), debug=True)


def _queue_params_change_from_worker(params, value):
    import threading

    writer = threading.Thread(target=lambda: params.set(value))
    writer.start()
    writer.join()  # the owner-loop callback is queued but has not run yet


def test_queued_params_change_does_not_override_a_newer_owner_loop_change():
    from reaktiv import resource, signal

    async def main():
        params = signal(1)
        calls = []

        async def load(request):
            calls.append(request.params)
            return request.params

        res = resource(params=lambda: params(), loader=load)
        await asyncio.sleep(0.01)
        _queue_params_change_from_worker(params, 2)
        params.set(3)  # applied immediately on the owner loop, before the queued 2
        await asyncio.sleep(0.05)
        assert calls == [1, 3]
        assert res.value() == 3
        res.dispose()

    asyncio.run(main(), debug=True)


def test_queued_params_change_is_superseded_by_set_and_reload():
    from reaktiv import resource, signal

    async def main():
        params = signal(1)
        calls = []

        async def load(request):
            calls.append(request.params)
            return request.params * 10

        res = resource(params=lambda: params(), loader=load)
        await asyncio.sleep(0.01)
        _queue_params_change_from_worker(params, 2)
        res.set(99)  # newer than the queued change: the local value stays
        await asyncio.sleep(0.05)
        assert calls == [1]
        assert res.value() == 99
        assert res.status() == ResourceStatus.LOCAL

        _queue_params_change_from_worker(params, 3)
        res.reload()  # newer: reloads the current params once
        await asyncio.sleep(0.05)
        assert calls == [1, 3]
        assert res.value() == 30
        res.dispose()

    asyncio.run(main(), debug=True)


@pytest.mark.parametrize("writer", ["worker", "owner"])
@pytest.mark.parametrize("action", ["dispose", "cancel", "set"])
def test_loader_does_not_start_when_its_loading_status_observer_stops_it(action, writer):
    import threading
    from reaktiv import effect, resource, signal

    async def main():
        params = signal(1)
        calls = []

        async def load(request):
            calls.append(request.params)
            return request.params * 10

        res = resource(params=lambda: params(), loader=load)
        await asyncio.sleep(0.01)
        assert calls == [1]

        def stop_on_loading():
            if res.status() == ResourceStatus.LOADING and params() == 2:
                with untracked():
                    if action == "dispose":
                        res.dispose()
                    elif action == "cancel":
                        res.cancel()
                    else:
                        res.set(99)

        observer = effect(stop_on_loading)
        if writer == "owner":
            params.set(2)
        else:
            worker = threading.Thread(target=lambda: params.set(2))
            worker.start()
            worker.join()
        await asyncio.sleep(0.05)

        assert calls == [1]
        expected = {
            "dispose": ResourceStatus.CANCELLED,
            "cancel": ResourceStatus.CANCELLED,
            "set": ResourceStatus.LOCAL,
        }[action]
        assert res.status() == expected
        assert res.is_loading() is False
        observer.dispose()
        res.dispose()

    asyncio.run(main(), debug=True)


def test_rejected_lifecycle_calls_leave_the_resource_unchanged():
    from reaktiv import computed, resource, signal
    from reaktiv.subtle import Watcher

    async def main():
        release = asyncio.Event()

        async def load(request):
            await release.wait()
            return 42

        res = resource(params=lambda: 1, loader=load)
        await asyncio.sleep(0)
        assert res.status() == ResourceStatus.LOADING

        trigger = signal(0)
        errors = []

        def notify():
            for action in (res.dispose, res.cancel, res.reload):
                try:
                    action()
                except RuntimeError:
                    errors.append(action.__name__)

        watcher = Watcher(notify)
        watcher.watch(trigger)
        trigger.set(1)  # notify runs: every lifecycle call must be rejected
        assert errors == ["dispose", "cancel", "reload"]
        assert res.status() == ResourceStatus.LOADING

        for action in (res.cancel, res.reload, res.dispose):
            with pytest.raises(RuntimeError):
                computed(lambda action=action: action())()
        assert res.status() == ResourceStatus.LOADING

        res.dispose()  # retrying outside the forbidden context works
        release.set()
        await asyncio.sleep(0.01)
        assert res.status() == ResourceStatus.CANCELLED
        assert res.value() is None
        watcher.dispose()

    asyncio.run(main(), debug=True)


def test_params_change_after_a_manual_reload_is_loading_not_reloading():
    from reaktiv import effect, resource, signal

    async def main():
        params = signal(1)

        async def load(request):
            return request.params * 10

        res = resource(params=lambda: params(), loader=load)
        await asyncio.sleep(0.01)
        res.reload()
        await asyncio.sleep(0.01)
        assert res.value() == 10

        statuses = []
        observer = effect(lambda: statuses.append(res.status()))
        params.set(2)
        await asyncio.sleep(0.01)
        assert ResourceStatus.LOADING in statuses
        assert ResourceStatus.RELOADING not in statuses
        assert res.value() == 20
        observer.dispose()
        res.dispose()

    asyncio.run(main(), debug=True)


def test_resource_snapshots_are_immutable():
    import dataclasses
    from reaktiv import resource

    async def main():
        async def load(request):
            return 2

        res = resource(params=lambda: 1, loader=load)
        await asyncio.sleep(0.01)
        snapshot = res.snapshot()()
        with pytest.raises(dataclasses.FrozenInstanceError):
            snapshot.value = 999
        assert res.snapshot()().value == 2
        res.dispose()

    asyncio.run(main())
