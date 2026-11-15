# Advanced Features

This page covers advanced features and techniques in reaktiv for building more sophisticated reactive systems.

## Custom Equality Functions

By default, reaktiv uses identity comparison (`is`) to determine if a signal's value has changed. For more complex types, you can provide custom equality functions:

```pyodide install="reaktiv" height="22" theme="github,one_dark"
from reaktiv import signal

# Custom equality for dictionaries
def dict_equal(a, b):
    if not isinstance(a, dict) or not isinstance(b, dict):
        return a == b
    if set(a.keys()) != set(b.keys()):
        return False
    return all(a[k] == b[k] for k in a)

# Create a signal with custom equality
user = signal({"name": "Alice", "age": 30}, equal=dict_equal)

# This won't trigger updates because the dictionaries are equal by value
user.set({"name": "Alice", "age": 30})

# This will trigger updates because the "age" value is different
user.set({"name": "Alice", "age": 31})

print(user())
```

Custom equality functions are especially useful for:

- Complex data structures like dictionaries, lists, or custom objects
- Case-insensitive string comparison
- Numerical comparison with tolerance (for floating-point values)
- Domain-specific equality (e.g., comparing users by ID regardless of other attributes)

## Effect Cleanup

Effects can register cleanup functions that will run before the next execution or when the effect is disposed:

```pyodide install="reaktiv" assets="no" height="30" theme="github,one_dark"
from reaktiv import signal, effect

counter = signal(0)

def counter_effect(on_cleanup):
    value = counter()
    print(f"Setting up for counter value: {value}")
    
    # Set up some resource or state
    
    # Define cleanup function
    def cleanup():
        print(f"Cleaning up for counter value: {value}")
        # Release resources, remove event listeners, etc.
    
    # Register the cleanup function
    on_cleanup(cleanup)

# Create and schedule the effect
logger = effect(counter_effect)

# Prints: "Setting up for counter value: 0"

# Update the signal
counter.set(1)
# Prints: "Cleaning up for counter value: 0"
# Prints: "Setting up for counter value: 1"

# Dispose the effect
logger.dispose()
# Prints: "Cleaning up for counter value: 1"
```

This pattern is useful for:

- Managing subscriptions to external event sources
- Releasing resources when values change or the effect is disposed
- Setting up and tearing down UI elements in response to data changes
- Cancelling pending operations when new values arrive

## Asynchronous Iteration

The `to_async_iter` utility lets you use signals with `async for` loops:

```pyodide install="reaktiv" assets="no" height="25" theme="github,one_dark"
import asyncio
from reaktiv import signal, to_async_iter

async def main():
    counter = signal(0)
    
    # Start a task that increments the counter
    async def increment_counter():
        for i in range(1, 5):
            await asyncio.sleep(0.05)
            counter.set(i)
    
    asyncio.create_task(increment_counter())
    
    # Use the signal as an async iterator
    async for value in to_async_iter(counter):
        print(f"Got value: {value}")
        if value >= 4:
            break

await main()
```

Output:
```
Got value: 0
Got value: 1
Got value: 2
Got value: 3
Got value: 4
```

This is useful for:

- Building reactive data processing pipelines
- Integrating with other async code
- Responding to signal changes in event loops
- Creating reactive streams of data

## Selective Dependency Tracking

You can selectively control which signals create dependencies using `untracked`:

```pyodide install="reaktiv" assets="no" height="28" theme="github,one_dark"
from reaktiv import signal, effect, untracked

user_id = signal(123)
user_data = signal({"name": "Alice"})
show_details = signal(False)

def render_user():
    # Always creates a dependency on user_id
    id_value = user_id()
    
    # Only access user_data if show_details is true,
    # but don't create a dependency on show_details
    if untracked(show_details):
        print(f"User {id_value}: {user_data()}")
    else:
        print(f"User {id_value}")

# Create and schedule the effect
display = effect(render_user)

# Update dependencies will trigger the effect
user_id.set(456)

# This update won't trigger the effect, even though it changes the output
show_details.set(True)

user_data.set({"name": "Grace"})  # Now tracked because details are visible
display.dispose()
```

## Choosing Between Effects, Resources and Watchers

Three tools react to changes. They differ in who decides *when* work runs and
whether that work is asynchronous:

| Use | For | When it runs |
|---|---|---|
| `effect` | Synchronous side effects: logging, writing other signals, updating a UI you own | Immediately after the write, or when the outermost `batch()` ends |
| `resource` | Loading data asynchronously from reactive parameters, with status, errors, cancellation and reloads | The loader starts on the resource's event loop when its parameters change |
| `reaktiv.subtle.Watcher` | Integrations that own scheduling (a UI frame, an event loop tick, a host's own queue) | Never by itself: you are notified and evaluate later, on your schedule |

- **Prefer synchronous effects.** An async effect (`async def`) is supported,
  but it re-runs as a whole on every change and has no status, error or
  cancellation state of its own. To load data, use a `resource`. To react to
  changes in async code, use `to_async_iter`.
- **Use a `Watcher` only when you need custom scheduling.** It is a low-level
  primitive for framework authors; see [subtle](api/subtle.md).

## Threads and Event Loops

- **Thread safety is enabled by default.** Signals, computed values and effects
  use locks so they can be read and written from several threads.
  `set_thread_safety(False)` removes that overhead for single-threaded programs.
  It is startup configuration: each object allocates its locks when it is
  created, so changing the setting later does not affect existing signals,
  computed values or effects.
- **Locks protect the graph, not your invariants.** They keep each read,
  write and `update()` consistent. They do not make several reads an atomic
  snapshot, and they do not move work between threads; event-loop affinity
  (below) is a separate rule.
- **An effect runs on the thread that first schedules it.** Usually that is the
  thread that made the write, synchronously or when that thread's outermost
  `batch()` ends. An effect that is already waiting in another thread's batch
  is not scheduled again: it runs once, on that thread, when its batch ends. So
  every write is eventually followed by a run of its effects, but not
  necessarily on the writing thread or immediately. A `Watcher`'s `notify`
  runs on the writing thread.
- **Async effects and resources belong to the event loop they were created
  on.** Both must be created while a loop is running. When a write on another
  thread triggers them, the work is handed to that loop: async effects,
  loaders, and cancelling a superseded load all run on the owner loop's thread.
  Changing a resource's parameters is therefore safe from any thread, and so
  is disposing an effect: a running async effect is cancelled on its loop.
- **Call a resource's own methods on its loop**: `set()`, `update()`,
  `reload()`, `cancel()` and `dispose()`. From another thread, schedule the
  call there, for example `loop.call_soon_threadsafe(res.cancel)`.

### What `batch()` does and does not do

`batch()` defers effects until the outermost batch on the *current thread*
ends, so each effect runs once with the final values. It is not a transaction:

- **Writes apply immediately.** Reads inside the batch, including computed
  values, already see the new values; only effects wait.
- **There is no rollback.** If the block raises, the writes made before the
  exception stay, and the deferred effects still run when the batch exits.
- **It does not isolate threads.** Other threads see each write as it happens,
  and multiple signals read from another thread are not an atomic snapshot.
  A batch defers only effects that are pending in it: a write on another
  thread still runs its other effects immediately on that thread.

```python
import threading
from reaktiv import batch, effect, signal

x, y = signal(0), signal(0)
on_x = effect(lambda: print("on_x sees", x(), "on", threading.current_thread().name))
on_y = effect(lambda: print("on_y sees", y(), "on", threading.current_thread().name))

with batch():
    x.set(1)  # on_x is now pending in this thread's batch
    print("inside the batch, x reads", x())  # 1: writes apply immediately
    writer = threading.Thread(target=lambda: y.set(2), name="writer")
    writer.start()
    writer.join()  # on_y already ran on the writer thread: it was not pending
    print("batch still open")
# The batch ends: on_x runs once, here.
on_x.dispose()
on_y.dispose()
```
