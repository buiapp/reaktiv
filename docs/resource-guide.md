# Resource Signal - Complete User Guide

## Table of Contents

1. [Mental Model](#mental-model)
2. [Core Concepts](#core-concepts)
3. [Common Use Cases](#common-use-cases)
4. [Design Patterns](#design-patterns)
5. [Best Practices](#best-practices)

---

## Mental Model

### The Spreadsheet Analogy Extended

If you understand signals as "cells in a reactive spreadsheet," then **Resource** is like a cell that fetches data from an external source (like a database query or API call) whenever its dependencies change.

Think of it this way:

- **Cell A1**: Contains a user ID (a Signal)
- **Cell B1**: Fetches user data from a database when A1 changes (a Resource)
- **Cell C1**: Displays the user's name from B1 (a Computed)

When you change A1, B1 automatically re-queries the database, and C1 automatically updates with the new name. But unlike normal spreadsheet cells, B1 knows it's waiting for data (LOADING status), can handle errors (ERROR status), and can cancel outdated requests.

### Key Principles

1. **Async Data, Sync Interface**: Resource brings asynchronous operations into the synchronous, reactive world of signals. You can read resource values synchronously in computed signals and effects, even though the data is loaded asynchronously.

2. **Automatic Request Management**: When the parameters change, Resource automatically:
   - Cancels the previous request (if still running)
   - Starts a new request with updated parameters
   - Updates status signals throughout the lifecycle

3. **Status-Driven UI**: Resources expose multiple status signals (`status`, `is_loading`, `has_value`, `error`) that enable you to build sophisticated UIs without manual state management.

4. **Declarative Dependencies**: Just define what parameters affect the request. The library handles when to fetch, when to cancel, and when to update.

### Comparison with Traditional Approaches

**Traditional (imperative):**
```python
class UserComponent:
    def __init__(self):
        self.user_id = None
        self.user_data = None
        self.is_loading = False
        self.error = None
        self.pending_request = None
    
    async def load_user(self, user_id):
        # Cancel previous request
        if self.pending_request:
            self.pending_request.cancel()
        
        # Set loading state
        self.is_loading = True
        self.error = None
        
        try:
            # Make request
            self.pending_request = asyncio.create_task(fetch_user(user_id))
            self.user_data = await self.pending_request
            self.is_loading = False
        except Exception as e:
            self.error = e
            self.is_loading = False
    
    def set_user_id(self, new_id):
        self.user_id = new_id
        asyncio.create_task(self.load_user(new_id))
```

**Reactive (declarative):**
```python
user_id = Signal("user123")

user_resource = Resource(
    params=lambda: {"id": user_id()},
    loader=fetch_user
)

# That's it! Loading, cancellation, and state management are automatic.
# Access with: user_resource.value(), user_resource.is_loading(), etc.
```

---

## Core Concepts

### 1. Resource Creation

Resources must be created within an async context (when an event loop is running):

```python
import asyncio
from reaktiv import Resource, Signal

async def main():
    user_id = Signal(1)
    
    user_resource = Resource(
        params=lambda: {"user_id": user_id()},
        loader=fetch_user_data
    )
    
    # ... use resource

asyncio.run(main())
```

**Why async context?** Resources need an event loop to schedule async tasks. This design prevents threading complexity and ensures predictable async behavior.

### 2. Parameters Function

The `params` function is a reactive computation—like a computed signal—that produces parameter values:

```python
# Simple static params
Resource(
    params=lambda: {"user_id": 123},
    loader=fetch_user
)

# Reactive params - reloads when user_id changes
user_id = Signal(1)
Resource(
    params=lambda: {"user_id": user_id()},
    loader=fetch_user
)

# Multi-dependency params
user_id = Signal(1)
include_posts = Signal(True)
Resource(
    params=lambda: {
        "user_id": user_id(),
        "include_posts": include_posts()
    },
    loader=fetch_user_with_options
)

# Conditional params - returning None prevents loading
user_id = Signal(None)
Resource(
    params=lambda: {"user_id": user_id()} if user_id() is not None else None,
    loader=fetch_user
)
```

**Key Point**: When `params` returns `None`, the loader doesn't run and status becomes `IDLE`.

### 3. Loader Function

The loader is an async function that receives `ResourceLoaderParams` and returns the loaded data:

```python
async def fetch_user(params: ResourceLoaderParams):
    # Access the params
    user_id = params.params["user_id"]
    
    # Check for cancellation
    if params.cancellation.is_set():
        return None
    
    # Access previous state
    if params.previous.status == ResourceStatus.RESOLVED:
        # Can implement optimistic updates or caching
        pass
    
    # Perform async operation
    response = await http_client.get(f"/users/{user_id}")
    
    # Check cancellation before returning
    if params.cancellation.is_set():
        return None
    
    return response.json()
```

**Loader Parameters:**

- `params.params`: The value from your params function
- `params.cancellation`: An `asyncio.Event` that signals when the request should be cancelled
- `params.previous`: Contains `status` of the previous state (useful for optimistic updates)

### 4. Resource Status States

Resources have six distinct states:

| Status | Description | `has_value()` | `is_loading()` | Use Case |
|--------|-------------|---------------|----------------|----------|
| `IDLE` | No valid params, loader hasn't run | `False` | `False` | Initial state or params is None |
| `LOADING` | Loader running due to params change | `False` | `True` | First load or param change |
| `RELOADING` | Loader running due to manual `reload()` | May be `True`* | `True` | Manual refresh while keeping old value |
| `RESOLVED` | Loader completed successfully | `True` | `False` | Normal success state |
| `ERROR` | Loader threw an exception | `False` | `False` | Error occurred |
| `LOCAL` | Value set manually via `set()` or `update()` | `True` | `False` | Optimistic updates |

\* During RELOADING, the previous value remains available while new data loads.

### 5. Accessing Resource Data

```python
# Check if data is available
if user_resource.has_value():
    user = user_resource.value()  # Note: value is a computed signal
    print(user["name"])

# Access status
status = user_resource.status()  # ReadonlySignal

# Check loading state
if user_resource.is_loading():
    print("Loading...")

# Access error
if user_resource.status() == ResourceStatus.ERROR:
    error = user_resource.error()
    print(f"Error: {error}")

# Atomic snapshot (efficient for multiple checks)
snapshot = user_resource.snapshot()()
match snapshot.status:
    case ResourceStatus.RESOLVED:
        print(f"Value: {snapshot.value}")
    case ResourceStatus.ERROR:
        print(f"Error: {snapshot.error}")
    case ResourceStatus.LOADING:
        print("Loading...")
```

---

## Common Use Cases

### 1. Data Fetching (REST API)

```python
import asyncio
import aiohttp
from reaktiv import Resource, Signal

async def fetch_github_user(params):
    """Fetch user data from GitHub API."""
    username = params.params["username"]
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.github.com/users/{username}") as response:
            if params.cancellation.is_set():
                return None
            
            if response.status == 404:
                raise ValueError(f"User '{username}' not found")
            
            response.raise_for_status()
            return await response.json()

async def main():
    # Reactive username
    username = Signal("torvalds")
    
    # Create resource
    github_user = Resource(
        params=lambda: {"username": username()},
        loader=fetch_github_user
    )
    
    # Wait for initial load
    await asyncio.sleep(1)
    
    if github_user.has_value():
        user = github_user.value()
        print(f"Name: {user['name']}")
        print(f"Repos: {user['public_repos']}")
    
    # Change username - automatically fetches new data
    username.set("gvanrossum")
    await asyncio.sleep(1)
    
    if github_user.has_value():
        user = github_user.value()
        print(f"Name: {user['name']}")

asyncio.run(main())
```

### 2. Database Queries

```python
import asyncio
from reaktiv import Resource, Signal, Computed

# Simulated async database
class AsyncDB:
    async def query_user(self, user_id):
        await asyncio.sleep(0.1)  # Simulate query time
        return {
            "id": user_id,
            "name": f"User {user_id}",
            "email": f"user{user_id}@example.com"
        }

async def query_user_from_db(params):
    """Load user from database."""
    db = AsyncDB()
    user_id = params.params["user_id"]
    return await db.query_user(user_id)

async def main():
    db = AsyncDB()
    selected_user_id = Signal(1)
    
    # Resource automatically re-queries when ID changes
    user_resource = Resource(
        params=lambda: {"user_id": selected_user_id()},
        loader=query_user_from_db
    )
    
    # Computed signal that depends on resource
    user_email = Computed(lambda: (
        user_resource.value()["email"]
        if user_resource.has_value()
        else "No user selected"
    ))
    
    await asyncio.sleep(0.2)
    print(user_email())  # "user1@example.com"
    
    selected_user_id.set(42)
    await asyncio.sleep(0.2)
    print(user_email())  # "user42@example.com"

asyncio.run(main())
```

### 3. Search/Filter with Debouncing

```python
import asyncio
from reaktiv import Resource, Signal

async def search_products(params):
    """Search products with simulated API delay."""
    query = params.params["query"]
    
    # Don't search for empty queries
    if not query:
        return []
    
    # Simulate API call
    await asyncio.sleep(0.3)
    
    # Check if cancelled during delay
    if params.cancellation.is_set():
        return None
    
    # Simulated search results
    all_products = [
        "Apple iPhone", "Apple Watch", "Apple AirPods",
        "Samsung Galaxy", "Samsung TV", "Samsung Tablet"
    ]
    return [p for p in all_products if query.lower() in p.lower()]

async def main():
    search_query = Signal("")
    
    search_results = Resource(
        params=lambda: {"query": search_query()} if search_query() else None,
        loader=search_products
    )
    
    # Simulating rapid typing
    search_query.set("App")
    await asyncio.sleep(0.1)
    
    # Previous request gets automatically cancelled
    search_query.set("Apple")
    await asyncio.sleep(0.5)
    
    if search_results.has_value():
        results = search_results.value()
        print(f"Found: {results}")
        # Output: Found: ['Apple iPhone', 'Apple Watch', 'Apple AirPods']

asyncio.run(main())
```

### 4. Dependent Resources (Waterfall Loading)

```python
import asyncio
from reaktiv import Resource, Signal, Computed

async def fetch_user(params):
    """Fetch user by ID."""
    await asyncio.sleep(0.1)
    user_id = params.params["user_id"]
    return {
        "id": user_id,
        "name": f"User {user_id}",
        "company_id": 100 + user_id
    }

async def fetch_company(params):
    """Fetch company by ID."""
    await asyncio.sleep(0.1)
    company_id = params.params["company_id"]
    return {
        "id": company_id,
        "name": f"Company {company_id}"
    }

async def main():
    user_id = Signal(1)
    
    # First resource: fetch user
    user_resource = Resource(
        params=lambda: {"user_id": user_id()},
        loader=fetch_user
    )
    
    # Second resource: fetch company (depends on user data)
    company_resource = Resource(
        params=lambda: (
            {"company_id": user_resource.value()["company_id"]}
            if user_resource.has_value()
            else None
        ),
        loader=fetch_company
    )
    
    # Wait for both to load
    await asyncio.sleep(0.3)
    
    if company_resource.has_value():
        company = company_resource.value()
        print(f"Company: {company['name']}")  # "Company 101"
    
    # Changing user_id triggers both to reload
    user_id.set(2)
    await asyncio.sleep(0.3)
    
    if company_resource.has_value():
        company = company_resource.value()
        print(f"Company: {company['name']}")  # "Company 102"

asyncio.run(main())
```

### 5. Polling / Real-time Updates

```python
import asyncio
from reaktiv import Resource, Signal

async def fetch_server_status(params):
    """Check server status."""
    server_id = params.params["server_id"]
    await asyncio.sleep(0.5)
    
    # Simulate random status
    import random
    statuses = ["online", "offline", "degraded"]
    return {
        "server_id": server_id,
        "status": random.choice(statuses),
        "timestamp": asyncio.get_event_loop().time()
    }

async def main():
    server_id = Signal("server-1")
    
    server_status = Resource(
        params=lambda: {"server_id": server_id()},
        loader=fetch_server_status
    )
    
    # Poll every 2 seconds
    async def poll_status():
        while True:
            await asyncio.sleep(2)
            server_status.reload()  # Manual refresh
    
    poll_task = asyncio.create_task(poll_status())
    
    # Monitor for 6 seconds
    for _ in range(4):
        await asyncio.sleep(1.5)
        if server_status.has_value():
            status = server_status.value()
            print(f"Status: {status['status']} at {status['timestamp']:.2f}")
    
    poll_task.cancel()

asyncio.run(main())
```

---

## Design Patterns

### Pattern 1: Optimistic Updates

Update UI immediately while the server request is in progress:

```python
import asyncio
from reaktiv import Resource, Signal, ResourceStatus

async def save_user(params):
    """Save user to server."""
    user_data = params.params["user"]
    
    # Simulate network delay
    await asyncio.sleep(0.5)
    
    # Simulate occasional failures
    if user_data.get("email") == "invalid":
        raise ValueError("Invalid email")
    
    return {**user_data, "saved_at": "2024-01-22"}

async def main():
    user_data = Signal({"name": "Alice", "email": "alice@example.com"})
    
    save_resource = Resource(
        params=lambda: {"user": user_data()} if user_data() else None,
        loader=save_user
    )
    
    await asyncio.sleep(0.6)
    
    # Optimistic update: set local value immediately
    new_data = {"name": "Alice Updated", "email": "alice@example.com"}
    save_resource.set(new_data)
    
    # UI shows updated data immediately (status = LOCAL)
    print(f"Status: {save_resource.status()}")  # LOCAL
    print(f"Value: {save_resource.value()}")
    
    # Trigger actual save
    user_data.set(new_data)
    await asyncio.sleep(0.6)
    
    # Now status is RESOLVED with server response
    print(f"Status: {save_resource.status()}")  # RESOLVED
    print(f"Value: {save_resource.value()}")

asyncio.run(main())
```

### Pattern 2: Request Deduplication

Prevent redundant requests when params haven't actually changed:

```python
import asyncio
from reaktiv import Resource, Signal, Computed

request_count = 0

async def fetch_data(params):
    """Expensive data fetch operation."""
    global request_count
    request_count += 1
    
    await asyncio.sleep(0.1)
    return {"data": f"Result for {params.params['key']}"}

async def main():
    global request_count
    
    signal_a = Signal(1)
    signal_b = Signal(2)
    
    # Computed params - only changes when result changes
    combined_key = Computed(lambda: f"{signal_a()}-{signal_b()}")
    
    data_resource = Resource(
        params=lambda: {"key": combined_key()},
        loader=fetch_data
    )
    
    await asyncio.sleep(0.2)
    print(f"Requests: {request_count}")  # 1
    
    # Change signal_a but keep combined_key the same
    signal_a.set(1)  # No change in combined key
    await asyncio.sleep(0.2)
    print(f"Requests: {request_count}")  # Still 1 (no duplicate request)
    
    # Actually change the combined key
    signal_a.set(3)
    await asyncio.sleep(0.2)
    print(f"Requests: {request_count}")  # 2 (new request)

asyncio.run(main())
```

### Pattern 3: Error Handling with Retry

```python
import asyncio
from reaktiv import Resource, Signal, ResourceStatus

async def fetch_with_retry(params):
    """Fetch with automatic retry logic."""
    url = params.params["url"]
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            # Simulate API call that might fail
            await asyncio.sleep(0.1)
            
            if params.cancellation.is_set():
                return None
            
            # Simulate 50% failure rate
            import random
            if random.random() < 0.5:
                raise ConnectionError("Network error")
            
            return {"url": url, "data": "Success!"}
        
        except ConnectionError as e:
            if attempt == max_retries - 1:
                raise  # Re-raise on final attempt
            
            # Exponential backoff
            await asyncio.sleep(0.1 * (2 ** attempt))
    
    raise RuntimeError("Should not reach here")

async def main():
    url = Signal("https://api.example.com/data")
    
    data_resource = Resource(
        params=lambda: {"url": url()},
        loader=fetch_with_retry
    )
    
    # Wait for load (with retries)
    await asyncio.sleep(1)
    
    if data_resource.status() == ResourceStatus.ERROR:
        print(f"Error after retries: {data_resource.error()}")
    elif data_resource.has_value():
        print(f"Success: {data_resource.value()}")

asyncio.run(main())
```

### Pattern 4: Caching with Previous State

```python
import asyncio
from reaktiv import Resource, Signal, ResourceStatus

# Simulated cache
cache = {}

async def fetch_with_cache(params):
    """Fetch with cache fallback."""
    item_id = params.params["item_id"]
    
    # Check cache first
    if item_id in cache:
        print(f"Cache hit for {item_id}")
        return cache[item_id]
    
    # If previous load succeeded, we could return that while fetching
    if params.previous.status == ResourceStatus.RESOLVED:
        print("Returning stale data while refetching")
    
    # Fetch fresh data
    await asyncio.sleep(0.2)
    
    if params.cancellation.is_set():
        return None
    
    result = {"id": item_id, "data": f"Fresh data for {item_id}"}
    cache[item_id] = result
    return result

async def main():
    item_id = Signal(1)
    
    item_resource = Resource(
        params=lambda: {"item_id": item_id()},
        loader=fetch_with_cache
    )
    
    await asyncio.sleep(0.3)
    print(f"First load: {item_resource.value()}")
    
    # Change to new item
    item_id.set(2)
    await asyncio.sleep(0.3)
    print(f"Second load: {item_resource.value()}")
    
    # Return to cached item (instant)
    item_id.set(1)
    await asyncio.sleep(0.3)
    print(f"Cached load: {item_resource.value()}")

asyncio.run(main())
```

### Pattern 5: Conditional Loading

```python
import asyncio
from reaktiv import Resource, Signal, Computed

async def fetch_user_details(params):
    """Fetch detailed user information."""
    user_id = params.params["user_id"]
    await asyncio.sleep(0.2)
    return {
        "id": user_id,
        "details": f"Detailed info for user {user_id}"
    }

async def main():
    user_id = Signal(None)  # Start with no selection
    fetch_enabled = Signal(False)
    
    # Only fetch when both conditions are met
    should_fetch = Computed(lambda: (
        user_id() is not None and fetch_enabled()
    ))
    
    user_details = Resource(
        params=lambda: (
            {"user_id": user_id()}
            if should_fetch()
            else None
        ),
        loader=fetch_user_details
    )
    
    # Initially IDLE (params is None)
    await asyncio.sleep(0.1)
    print(f"Status: {user_details.status()}")  # IDLE
    
    # Set user but don't enable fetch
    user_id.set(123)
    await asyncio.sleep(0.1)
    print(f"Status: {user_details.status()}")  # Still IDLE
    
    # Enable fetch - now it loads
    fetch_enabled.set(True)
    await asyncio.sleep(0.3)
    print(f"Status: {user_details.status()}")  # RESOLVED
    print(f"Value: {user_details.value()}")

asyncio.run(main())
```

---

## Best Practices

### 1. Always Create Resources in Async Context

✅ **Good:**
```python
async def main():
    user_id = Signal(1)
    user_resource = Resource(
        params=lambda: {"id": user_id()},
        loader=fetch_user
    )
    # ... use resource

asyncio.run(main())
```

❌ **Bad:**
```python
# This will raise RuntimeError - no event loop running
user_id = Signal(1)
user_resource = Resource(
    params=lambda: {"id": user_id()},
    loader=fetch_user
)
```

### 2. Use `has_value()` as a Type Guard

✅ **Good:**
```python
user_name = Computed(lambda: (
    user_resource.value()["name"]
    if user_resource.has_value()
    else "Loading..."
))
```

❌ **Bad:**
```python
# This can throw if resource is in error state!
user_name = Computed(lambda: (
    user_resource.value()["name"]
    if user_resource.value() is not None
    else "Loading..."
))
```

### 3. Check Cancellation in Long-Running Loaders

✅ **Good:**
```python
async def fetch_large_dataset(params):
    data = []
    
    for i in range(1000):
        # Check cancellation periodically
        if params.cancellation.is_set():
            return None
        
        # Process chunk
        chunk = await process_chunk(i)
        data.extend(chunk)
    
    return data
```

❌ **Bad:**
```python
async def fetch_large_dataset(params):
    # Never checks cancellation - wastes resources
    data = []
    for i in range(1000):
        chunk = await process_chunk(i)
        data.extend(chunk)
    return data
```

### 4. Use Snapshot for Multiple Status Checks

✅ **Good (atomic):**
```python
def display_user():
    snap = user_resource.snapshot()()
    
    match snap.status:
        case ResourceStatus.LOADING:
            return "Loading..."
        case ResourceStatus.ERROR:
            return f"Error: {snap.error}"
        case ResourceStatus.RESOLVED:
            return f"User: {snap.value['name']}"
        case _:
            return "No data"
```

❌ **Bad (multiple signal reads):**
```python
def display_user():
    # Multiple signal reads - could be inconsistent
    if user_resource.is_loading():
        return "Loading..."
    elif user_resource.status() == ResourceStatus.ERROR:
        return f"Error: {user_resource.error()}"
    elif user_resource.has_value():
        return f"User: {user_resource.value()['name']}"
    return "No data"
```

### 5. Return None from Params to Prevent Loading

✅ **Good:**
```python
user_id = Signal(None)

user_resource = Resource(
    params=lambda: (
        {"id": user_id()}
        if user_id() is not None
        else None  # Prevents loading when no ID
    ),
    loader=fetch_user
)
```

❌ **Bad:**
```python
# Always passes params, even with invalid data
user_resource = Resource(
    params=lambda: {"id": user_id()},  # Passes None to loader
    loader=fetch_user  # Has to handle None case
)
```

### 6. Clean Up Resources When Done

✅ **Good:**
```python
async def main():
    resource = Resource(params=..., loader=...)
    
    try:
        # Use resource
        await asyncio.sleep(1)
    finally:
        resource.destroy()  # Clean up pending tasks
```

❌ **Bad:**
```python
async def main():
    resource = Resource(params=..., loader=...)
    # Just let it go - might leave pending tasks
```

### 7. Use Computed Params for Deduplication

✅ **Good:**
```python
# Only reloads when the computed key actually changes
filter_key = Computed(lambda: f"{category()}-{sort_order()}")

results = Resource(
    params=lambda: {"key": filter_key()},
    loader=fetch_results
)
```

❌ **Bad:**
```python
# Reloads on every signal change, even if result is the same
results = Resource(
    params=lambda: {"cat": category(), "sort": sort_order()},
    loader=fetch_results
)
```

---

## API Reference

For complete API documentation, see [Resource API Reference](api/resource-signal.md).

---

## Frequently Asked Questions

**Q: Why must Resources be created in async context?**

A: Resources need an event loop to schedule async tasks. This requirement ensures predictable behavior and prevents threading complexity. Always create resources inside `async def` functions run with `asyncio.run()`.

**Q: When should I use `reload()` vs changing params?**

A: Use `reload()` for manual refreshes (e.g., refresh button) where you want to reload without changing parameters. The status becomes `RELOADING` instead of `LOADING`, and the previous value stays available during reload.

**Q: Why does `value` throw when in ERROR state?**

A: This design encourages proper error handling. Always check `has_value()` before accessing `value()()`, or use `snapshot()` for safe access to all states.

**Q: How do I handle None as a valid value?**

A: The current implementation treats `None` as "no value". If you need `None` as a valid value, wrap it in a container: `{"data": None}`.

**Q: Can I use Resources with synchronous code?**

A: Resources must be created in async context, but you can access their signals synchronously once created. The async/sync bridge is the key benefit of Resources.

**Q: What happens to pending requests when params change?**

A: The previous request is automatically cancelled via the `cancellation` event. Your loader should check `params.cancellation.is_set()` and return early if cancelled.

**Q: Can multiple Resources depend on each other?**

A: Yes! Create "waterfall" loading by making one Resource's params depend on another's value (see [Dependent Resources](#4-dependent-resources-waterfall-loading) example).

---

## Summary

Resources bring async operations into the reactive signal-based world:

1. **Declarative**: Define what params affect loading; the library handles when
2. **Automatic**: Request management, cancellation, and status tracking are built-in
3. **Reactive**: Changes propagate automatically through the dependency graph
4. **Type-safe**: Full TypeScript-style type hints in Python
5. **Flexible**: Supports optimistic updates, caching, retries, and more

By using Resources, you can build sophisticated async UIs with less code, fewer bugs, and better user experience.
