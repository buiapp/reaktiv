"""Tests for Resource."""

import asyncio
import pytest
import pytest_asyncio
from reaktiv import (
    Signal,
    Resource,
    ResourceStatus,
    Computed,
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

