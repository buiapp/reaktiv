# Patterns and Best Practices

This guide covers common patterns, best practices, and real-world examples for using reaktiv effectively.

## Effect Patterns

### Dependency Tracking

Dependencies are whatever an effect (or computed) reads during its **latest
run**. Tracking is dynamic: a signal read only in a branch that was not taken
is not a dependency, and that is correct. When the condition changes, the
effect reruns, takes the other branch and starts tracking the signals it reads
there.

```pyodide install="reaktiv" height="24" theme="github,one_dark"
from reaktiv import signal, effect

name = signal("Alice")
enabled = signal(True)

def greet():
    if enabled():
        print(f"Hello, {name()}")  # tracked only while enabled is True

greeter = effect(greet)   # Prints: "Hello, Alice"
enabled.set(False)        # reruns; name is no longer a dependency
name.set("Grace")         # does not rerun: the effect would print nothing
enabled.set(True)         # Prints: "Hello, Grace"
greeter.dispose()
```

**Structure effects as "read, then act":**

- Read the signals the effect reacts to at the start, then perform the side
  effect. A read placed after code that can raise or return early is never
  tracked when that happens, so the effect stops reacting to it.
- Do the side-effect work inside `with untracked():`. Helpers and callbacks
  you call may read signals; untracked, they cannot subscribe the effect by
  accident.
- Branches are still fine: a signal the effect does not need in this run does
  not have to be read. Extra "just in case" reads only cause extra runs.

### Memory Management

**⚠️ CRITICAL:** Effects must be retained in a variable to prevent garbage collection. An effect created without storing the reference will be immediately garbage collected and won't work.

```python
from reaktiv import signal, effect

counter = signal(0)

# ❌ WRONG: Effect will be garbage collected immediately
def print_counter():
    print(counter())

effect(print_counter)

# ✅ CORRECT: Store reference to prevent GC
counter_effect = effect(print_counter)
```

To prevent memory leaks:

1. **Always** keep a reference to your effect as long as you need it
2. Call `dispose()` when you're done with the effect
3. Avoid creating effects inside loops or frequently-called functions without disposing of them

```pyodide install="reaktiv" assets="no" height="28" theme="github,one_dark"
from reaktiv import signal, effect

def create_temporary_effect(s):
    # Store reference while needed
    def print_value():
        print(f"Value: {s()}")

    temp_effect = effect(print_value)
    # ... do something ...
    temp_effect.dispose()  # Clean up properly

# Better pattern for component lifecycle
class MyComponent:
    def __init__(self, s):
        self.s = s
        # Store as instance variable
        self.effect_instance = effect(self._render)
    
    def _render(self):
        print(f"Rendering: {self.s()}")
    
    def destroy(self):
        self.effect_instance.dispose()


signal = signal("ready")
component = MyComponent(signal)
signal.set("updated")
component.destroy()
```

### Notification Batching

When multiple signals change, their effects are batched to avoid unnecessary executions:

```pyodide install="reaktiv" assets="no" height="25" theme="github,one_dark"
from reaktiv import signal, effect, batch

x = signal(1)
y = signal(2)

def log_values():
    print(f"x: {x()}, y: {y()}")

# Keep reference to prevent GC
logger = effect(log_values)  # Prints: "x: 1, y: 2"

# Without batching, the effect would run twice:
# x.set(10)  # Effect runs
# y.set(20)  # Effect runs again

# With batching, the effect runs only once:
with batch():
    x.set(10)  # No effect execution yet
    y.set(20)  # No effect execution yet
# After batch completes: Effect runs once
# Prints: "x: 10, y: 20"
logger.dispose()
```
