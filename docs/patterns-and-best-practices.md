# Patterns and Best Practices

This guide covers common patterns, best practices, and real-world examples for using reaktiv effectively.

## Effect Patterns

### Dependency Tracking

**Important:** Signal dependencies are established when signals are called within the effect function. Call dependent signals at the beginning of your effect to ensure proper dependency tracking.

```python
from reaktiv import Signal, Effect

name = Signal("Alice")
age = Signal(30)
enabled = Signal(True)

def my_effect():
    # ✅ GOOD: Call all dependent signals first
    current_name = name()
    current_age = age()
    is_enabled = enabled()
    
    # Then use the values
    if is_enabled:
        print(f"{current_name} is {current_age} years old")

# Keep reference to prevent GC
effect = Effect(my_effect)
```

**Why this matters:**

- Dependencies are tracked during effect execution
- Conditional signal reads can lead to inconsistent dependencies
- Reading signals early ensures they're always tracked

```python
# ❌ AVOID: Conditional dependency tracking
def problematic_effect():
    is_enabled = enabled()
    
    if is_enabled:
        # This creates dependency only when enabled is True
        print(name())
    # Effect won't re-run when name changes if enabled is False

# ✅ BETTER: Always establish dependencies
def better_effect():
    # Read all dependencies first
    current_name = name()
    is_enabled = enabled()
    
    # Then use conditionally
    if is_enabled:
        print(current_name)
```

### Memory Management

**⚠️ CRITICAL:** Effects must be retained in a variable to prevent garbage collection. An effect created without storing the reference will be immediately garbage collected and won't work.

```python
from reaktiv import Signal, Effect

counter = Signal(0)

# ❌ WRONG: Effect will be garbage collected immediately
Effect(lambda: print(counter()))

# ✅ CORRECT: Store reference to prevent GC
effect = Effect(lambda: print(counter()))
```

To prevent memory leaks:

1. **Always** keep a reference to your effect as long as you need it
2. Call `dispose()` when you're done with the effect
3. Avoid creating effects inside loops or frequently-called functions without disposing of them

```python
from reaktiv import Signal, Effect

def create_temporary_effect(s):
    # Store reference while needed
    temp_effect = Effect(lambda: print(f"Value: {s()}"))
    # ... do something ...
    temp_effect.dispose()  # Clean up properly

# Better pattern for component lifecycle
class MyComponent:
    def __init__(self, s):
        self.s = s
        # Store as instance variable
        self.effect_instance = Effect(self._render)
    
    def _render(self):
        print(f"Rendering: {self.s()}")
    
    def destroy(self):
        self.effect_instance.dispose()
```

### Notification Batching

When multiple signals change, their effects are batched to avoid unnecessary executions:

```python
from reaktiv import Signal, Effect, batch

x = Signal(1)
y = Signal(2)

def log_values():
    print(f"x: {x()}, y: {y()}")

# Keep reference to prevent GC
logger = Effect(log_values)  # Prints: "x: 1, y: 2"

# Without batching, the effect would run twice:
# x.set(10)  # Effect runs
# y.set(20)  # Effect runs again

# With batching, the effect runs only once:
with batch():
    x.set(10)  # No effect execution yet
    y.set(20)  # No effect execution yet
# After batch completes: Effect runs once
# Prints: "x: 10, y: 20"
```