# Resource API

The `Resource` class is a reactive primitive for handling asynchronous data loading with automatic dependency tracking, request cancellation, and comprehensive status management.

## Overview

Resource integrates async operations into your reactive application while providing a synchronous interface for accessing data. It's ideal for API calls, data fetching, and any async operation that depends on reactive parameters.

**Key Features:**

- **Automatic reloading** when reactive dependencies change
- **Request cancellation** for outdated requests (prevents race conditions)
- **6 status states** for precise UI control: IDLE, LOADING, RELOADING, RESOLVED, ERROR, LOCAL
- **Type-safe** with full generic type support
- **Seamless integration** with signals and computed signals
- **Manual reload** capability via `reload()`
- **Local state override** via `set()` and `update()` for optimistic updates
- **Automatic cleanup** when garbage collected

## Basic Usage

```python
import asyncio
from reaktiv import Signal, Resource, ResourceStatus

async def main():
    # Reactive parameter
    user_id = Signal(1)
    
    # Define async loader
    async def fetch_user(params):
        # Access current params
        uid = params.params["user_id"]
        
        # Check for cancellation
        if params.cancellation.is_set():
            return None
            
        # Simulate API call
        await asyncio.sleep(0.5)
        return {"id": uid, "name": f"User {uid}"}
    
    # Create resource
    user_resource = Resource(
        params=lambda: {"user_id": user_id()},
        loader=fetch_user
    )
    
    # Wait for initial load
    await asyncio.sleep(0.6)
    
    # Access data safely
    if user_resource.has_value():
        user = user_resource.value()
        print(f"User: {user['name']}")
    
    # Check status
    status = user_resource.status()
    if status == ResourceStatus.RESOLVED:
        print("Data loaded successfully")
    elif status == ResourceStatus.ERROR:
        print(f"Error: {user_resource.error()}")
    
    # Changing params automatically triggers reload
    user_id.set(2)
    await asyncio.sleep(0.6)
    print(user_resource.value())  # {"id": 2, "name": "User 2"}

asyncio.run(main())
```

## Creation

```python
Resource(
    params: Callable[[], Optional[P]],
    loader: Callable[[ResourceLoaderParams[P]], Awaitable[T]]
) -> Resource[P, T]
```

Creates a new Resource that loads data asynchronously based on reactive parameters.

### Parameters

- **`params`**: A reactive computation that returns parameter values for the loader. When this returns a different value, the resource automatically reloads. If it returns `None`, the loader won't run and the resource enters `IDLE` state.

- **`loader`**: An async function that loads data. Receives a `ResourceLoaderParams` object with:
  - `params`: The current parameter value (type `P`)
  - `previous`: Previous resource state containing prior `status`
  - `cancellation`: An `asyncio.Event` that is set when the request is cancelled

### Returns

A `Resource[P, T]` instance with properties and methods to access loaded data and status.

### Important Requirements

⚠️ **Must be created within an async context** (inside an async function with a running event loop). Use `asyncio.run()` to start your async context.

```python
# ✅ Correct
async def main():
    resource = Resource(params=..., loader=...)
    # ... use resource ...

asyncio.run(main())

# ❌ Wrong - RuntimeError: no event loop
resource = Resource(params=..., loader=...)
```

## Properties

All properties return reactive signals that can be read in computed signals or effects.

### `value`

```python
@property
def value() -> ComputeSignal[Optional[T]]
```

Returns a computed signal containing the loaded value or `None` if not yet loaded.

**Important**: Reading this will throw an exception if the resource is in `ERROR` state. Always use `has_value()` as a guard before accessing.

```python
# ✅ Safe access with type guard
if user_resource.has_value():
    user = user_resource.value()
    print(user["name"])

# ✅ In computed signals
@Computed
def display_name():
    if user_resource.has_value():
        return user_resource.value()["name"]
    return "Loading..."
```

### `error`

```python
@property
def error() -> ReadonlySignal[Optional[Exception]]
```

Returns a readonly signal containing the most recent error, or `None` if no error occurred.

```python
if user_resource.status() == ResourceStatus.ERROR:
    error = user_resource.error()
    print(f"Failed to load: {error}")
```

### `status`

```python
@property
def status() -> ReadonlySignal[ResourceStatus]
```

Returns a readonly signal containing the current status. The six possible statuses are:

- **`IDLE`**: No valid request, loader has not run (params returned `None`)
- **`LOADING`**: Initial load in progress (params changed from `None` or initial load)
- **`RELOADING`**: Reload in progress (manual `reload()` was called)
- **`RESOLVED`**: Load completed successfully with data
- **`ERROR`**: Load failed with an error
- **`LOCAL`**: Value was set locally via `set()` or `update()`

```python
from reaktiv import ResourceStatus

status = user_resource.status()

match status:
    case ResourceStatus.LOADING | ResourceStatus.RELOADING:
        print("⏳ Loading...")
    case ResourceStatus.RESOLVED:
        print(f"✅ Data: {user_resource.value()}")
    case ResourceStatus.ERROR:
        print(f"❌ Error: {user_resource.error()}")
    case ResourceStatus.IDLE:
        print("No data")
    case ResourceStatus.LOCAL:
        print(f"📝 Local: {user_resource.value()}")
```

### `is_loading`

```python
@property
def is_loading() -> ReadonlySignal[bool]
```

Returns a readonly signal indicating whether any loading operation is in progress (either `LOADING` or `RELOADING`).

```python
# Simple loading indicator
if user_resource.is_loading():
    print("⏳ Loading...")
```

### `cancellation_event`

```python
@property
def cancellation_event() -> Optional[asyncio.Event]
```

Returns the current cancellation event for the active request, or `None` if no request is in progress.

The loader can check `event.is_set()` to detect if the request was cancelled.

```python
async def fetch_data(params):
    # Long operation
    for i in range(100):
        # Check if cancelled
        if params.cancellation.is_set():
            print("Request cancelled, stopping...")
            return None
        
        await asyncio.sleep(0.1)
        # ... process chunk ...
    
    return result
```

## Methods

### `has_value()`

```python
def has_value() -> bool
```

Type guard that returns `True` if the resource has a valid value and is not in error state.

**Use this before accessing `.value()` to prevent exceptions.**

```python
# ✅ Safe value access
if user_resource.has_value():
    user = user_resource.value()
    print(user["name"])

# ✅ In computed signals
@Computed
def user_name():
    if user_resource.has_value():
        return user_resource.value()["name"]
    return "No user"
```

### `reload()`

```python
def reload() -> None
```

Manually triggers the loader to reload data, even if parameters haven't changed. Sets status to `RELOADING` during the operation and cancels any ongoing requests.

```python
# Manual refresh button
def on_refresh_clicked():
    user_resource.reload()

# Periodic refresh
async def auto_refresh():
    while True:
        await asyncio.sleep(60)
        user_resource.reload()
```

### `set()`

```python
def set(value: T) -> None
```

Locally sets the resource value, canceling any ongoing load. Sets status to `LOCAL`.

Useful for optimistic updates or temporary local overrides.

```python
# Optimistic update before API call
user_resource.set({"id": "123", "name": "Updated Name"})

# Later, reload to get server state
user_resource.reload()
```

### `update()`

```python
def update(update_fn: Callable[[Optional[T]], T]) -> None
```

Updates the resource value using a function. Sets status to `LOCAL` and cancels any ongoing load.

```python
# Increment counter optimistically
counter_resource.update(lambda current: (current or 0) + 1)

# Update nested data
user_resource.update(lambda user: {
    **(user or {}),
    "settings": {"theme": "dark"}
})
```

### `snapshot()`

```python
def snapshot() -> ComputeSignal[ResourceSnapshot[T]]
```

Returns a computed signal containing an atomic snapshot of the resource's state.

The snapshot provides safe access to status, value, and error in a single atomic read, preventing race conditions.

```python
# Get atomic snapshot
snap = user_resource.snapshot()()

if snap.status == ResourceStatus.RESOLVED:
    print(f"Value: {snap.value}")
elif snap.status == ResourceStatus.ERROR:
    print(f"Error: {snap.error}")

# Use in computed signals
@Computed
def message():
    snap = user_resource.snapshot()()
    
    if snap.status == ResourceStatus.RESOLVED:
        return f"Hello, {snap.value['name']}!"
    elif snap.status == ResourceStatus.ERROR:
        return f"Error: {snap.error}"
    else:
        return "Loading..."
```

### `previous_status()`

```python
def previous_status() -> ResourceStatus
```

Returns the previous status of the resource before the current one.

Useful for tracking state transitions and implementing caching or stale-data strategies.

```python
# Show stale data while reloading
if (user_resource.status() == ResourceStatus.LOADING and
    user_resource.previous_status() == ResourceStatus.RESOLVED):
    # Show old data with loading indicator
    print(f"Reloading... (showing stale data: {user_resource.value()})")
```

### `destroy()`

```python
def destroy() -> None
```

Explicitly cleans up the resource by canceling any pending async tasks.

**Note**: Resource automatically cleans up when garbage collected, so calling `destroy()` is optional in most cases. However, explicit cleanup is recommended for long-lived applications or when you need immediate cleanup.

```python
# Explicit cleanup (recommended for long-lived apps)
class DataManager:
    def __init__(self):
        self.user_resource = Resource(...)
    
    def cleanup(self):
        self.user_resource.destroy()

# Automatic cleanup (when garbage collected)
async def temporary_operation():
    temp_resource = Resource(params=..., loader=...)
    # ... use resource ...
    # Automatically cleaned up when function exits
```

## ResourceLoaderParams

The loader function receives a `ResourceLoaderParams[P]` object with the following properties:

### `params: P`

The current parameter value from the `params` computation.

```python
async def fetch_user(p: ResourceLoaderParams):
    user_id = p.params["id"]  # Access params
    # ... fetch data using user_id
```

### `previous: PreviousResourceState`

A `PreviousResourceState` object containing the previous `status`. Useful for caching decisions and optimizations.

```python
async def fetch_with_cache(p: ResourceLoaderParams):
    # Use cache if previous fetch succeeded
    if p.previous.status == ResourceStatus.RESOLVED:
        cached = get_from_cache(p.params["id"])
        if cached and not is_stale(cached):
            return cached
    
    # Fetch fresh data
    return await api.fetch(p.params["id"])
```

### `cancellation: asyncio.Event`

An `asyncio.Event` that is set when the request should be cancelled (e.g., when params change or `reload()` is called).

Check `cancellation.is_set()` during long operations to allow early exit.

```python
async def fetch_large_dataset(p: ResourceLoaderParams):
    result = []
    
    for chunk_id in range(100):
        # Check if cancelled
        if p.cancellation.is_set():
            print("Request cancelled, stopping early")
            return None
        
        chunk = await fetch_chunk(chunk_id)
        result.extend(chunk)
    
    return result
```

## Status Flow

Understanding how Resource transitions between statuses:

| Current Status | Trigger | Next Status | Description |
|---------------|---------|-------------|-------------|
| **Initial** | `params = None` | `IDLE` | Resource created with no params |
| **IDLE** | `params != None` | `LOADING` | Params set for the first time or changed from None |
| **IDLE** | `set()` / `update()` | `LOCAL` | Value set locally |
| **LOADING** | Load succeeds | `RESOLVED` | Data loaded successfully |
| **LOADING** | Load fails | `ERROR` | Load encountered an error |
| **LOADING** | `params` changed | `LOADING` | New params trigger new load (cancels current) |
| **LOADING** | `params = None` | `IDLE` | Params cleared |
| **LOADING** | `set()` / `update()` | `LOCAL` | Value set locally (cancels load) |
| **RESOLVED** | `reload()` | `RELOADING` | Manual reload requested |
| **RESOLVED** | `params` changed | `LOADING` | Params changed, trigger new load |
| **RESOLVED** | `params = None` | `IDLE` | Params cleared |
| **RESOLVED** | `set()` / `update()` | `LOCAL` | Value set locally |
| **ERROR** | `reload()` | `RELOADING` | Manual reload to retry |
| **ERROR** | `params` changed | `LOADING` | Params changed, trigger new load |
| **ERROR** | `params = None` | `IDLE` | Params cleared |
| **ERROR** | `set()` / `update()` | `LOCAL` | Value set locally |
| **RELOADING** | Load succeeds | `RESOLVED` | Reload completed successfully |
| **RELOADING** | Load fails | `ERROR` | Reload encountered an error |
| **RELOADING** | `params` changed | `LOADING` | Params changed during reload |
| **RELOADING** | `params = None` | `IDLE` | Params cleared |
| **RELOADING** | `set()` / `update()` | `LOCAL` | Value set locally (cancels reload) |
| **LOCAL** | `reload()` | `RELOADING` | Reload to get server state |
| **LOCAL** | `params` changed | `LOADING` | Params changed, trigger load |
| **LOCAL** | `params = None` | `IDLE` | Params cleared |
| **LOCAL** | `set()` / `update()` | `LOCAL` | Value updated locally |

**Summary:**

- **Loading starts**: When params change from `None` to a value, or when params value changes
- **Loading completes**: Transitions to `RESOLVED` (success) or `ERROR` (failure)
- **Manual reload**: Use `reload()` to transition to `RELOADING` state
- **Local override**: Use `set()` or `update()` to transition to `LOCAL` from any state
- **Reset to idle**: Set params to `None` to return to `IDLE` from any state

