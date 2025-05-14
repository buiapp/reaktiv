# Why reaktiv?

When building applications that manage state, developers often struggle with keeping derived data in sync with its sources. reaktiv solves this fundamental problem through automatic dependency tracking and fine-grained reactivity.

## The Pain Points reaktiv Solves

### 1. The Manual State Synchronization Problem

Without a reactive system, developers typically face these challenges:

#### Before reaktiv: Manual State Propagation

```python
# Traditional approach with manual propagation
user_name = "Alice"
user_age = 30
# Derived state that depends on the above values
greeting = f"Hello, {user_name}! You are {user_age} years old."

# When state changes, you must remember to update ALL derived values
user_name = "Bob"  # State changed!
# Oops! Forgot to update greeting
# greeting still shows "Hello, Alice! You are 30 years old."

# Later in the code...
greeting = f"Hello, {user_name}! You are {user_age} years old."  # Manual update
```

#### After reaktiv: Automatic Propagation

```python
from reaktiv import Signal, Computed

# State as signals
user_name = Signal("Alice")
user_age = Signal(30)

# Derived state automatically updates when dependencies change
greeting = Computed(lambda: f"Hello, {user_name()}! You are {user_age()} years old.")

print(greeting())  # "Hello, Alice! You are 30 years old."

# When state changes, derived values update automatically
user_name.set("Bob")
print(greeting())  # "Hello, Bob! You are 30 years old."
```

### 2. The "Hidden State" Problem

Many developers don't realize how much "hidden state" exists in their applications. Every time you compute a value based on other values, you're creating state that needs to be managed.

```python
# Without reaktiv: Hidden state management
def get_total_price(items, tax_rate):
    subtotal = sum(item.price for item in items)
    return subtotal * (1 + tax_rate)

# This function is called in many places
# If items or tax_rate changes, you need to manually recalculate everywhere
```

### 3. The Dependency Tracking Problem

Manually tracking which parts of your code depend on which data becomes increasingly complex as applications grow.

```python
# Traditional approach with manual tracking
class ShoppingCart:
    def __init__(self, items=None):
        self.items = items or []
        self.subtotal = self._calculate_subtotal()
        self.tax = self._calculate_tax()
        self.total = self.subtotal + self.tax
    
    def _calculate_subtotal(self):
        return sum(item.price for item in self.items)
    
    def _calculate_tax(self):
        return self.subtotal * 0.1  # 10% tax
        
    def add_item(self, item):
        self.items.append(item)
        # Now we must manually update everything that depends on items
        self.subtotal = self._calculate_subtotal()
        self.tax = self._calculate_tax()  # Depends on subtotal
        self.total = self.subtotal + self.tax  # Depends on both
        
    # What if we add more derived values? The dependency chain gets complex!
```

## Before & After: How reaktiv Makes Your Code Better

### Example 1: Configuration with Overrides

#### Before reaktiv:

```python
def load_config():
    default_config = {"timeout": 30, "retries": 3, "debug": False}
    try:
        with open("user_config.json") as f:
            user_config = json.load(f)
    except FileNotFoundError:
        user_config = {}
        
    # Merge configs
    config = {**default_config, **user_config}
    
    # Derived values
    connection_settings = {
        "connect_timeout": config["timeout"],
        "max_attempts": config["retries"],
        "verbose": config["debug"],
    }
    
    return config, connection_settings

# Now what happens when config changes at runtime?
# You need to reload everything and update all dependents manually!
```

#### After reaktiv:

```python
from reaktiv import Signal, Computed

default_config = Signal({"timeout": 30, "retries": 3, "debug": False})
user_config = Signal({})

# Derived values automatically stay in sync
effective_config = Computed(lambda: {**default_config(), **user_config()})

connection_settings = Computed(lambda: {
    "connect_timeout": effective_config()["timeout"],
    "max_attempts": effective_config()["retries"],
    "verbose": effective_config()["debug"],
})

# When config changes, everything updates automatically
user_config.set({"timeout": 60})
print(connection_settings())  # connect_timeout is now 60
```

### Example 2: Data Processing Pipeline

#### Before reaktiv:

```python
class DataProcessor:
    def __init__(self, raw_data):
        self.raw_data = raw_data
        self.filtered_data = self._filter_data()
        self.transformed_data = self._transform_data()
        self.summary = self._summarize()
    
    def _filter_data(self):
        return [x for x in self.raw_data if x > 0]
    
    def _transform_data(self):
        return [x * 2 for x in self.filtered_data]
    
    def _summarize(self):
        return {
            "count": len(self.transformed_data),
            "sum": sum(self.transformed_data),
            "avg": sum(self.transformed_data) / len(self.transformed_data) if self.transformed_data else 0
        }
    
    def update_data(self, new_data):
        self.raw_data = new_data
        # Must manually update every step in the chain
        self.filtered_data = self._filter_data()
        self.transformed_data = self._transform_data()
        self.summary = self._summarize()
```

#### After reaktiv:

```python
from reaktiv import Signal, Computed

class ReactiveDataProcessor:
    def __init__(self, initial_data):
        self.raw_data = Signal(initial_data)
        
        # Each step automatically updates when dependencies change
        self.filtered_data = Computed(lambda: [x for x in self.raw_data() if x > 0])
        self.transformed_data = Computed(lambda: [x * 2 for x in self.filtered_data()])
        self.summary = Computed(lambda: {
            "count": len(self.transformed_data()),
            "sum": sum(self.transformed_data()),
            "avg": sum(self.transformed_data()) / len(self.transformed_data()) if self.transformed_data() else 0
        })
    
    def update_data(self, new_data):
        # Just update the source data - everything else updates automatically
        self.raw_data.set(new_data)
        
# Usage
processor = ReactiveDataProcessor([1, -2, 3, -4, 5])
print(processor.summary())  # Computed from the chain
processor.update_data([10, 20, 30])  # Everything recalculates automatically
```

## Comparing reaktiv with Alternatives

### reaktiv vs. RxPy/ReactiveX

| Feature | reaktiv | RxPy |
|---------|---------|------|
| **Focus** | Fine-grained state management | Event streams and operations |
| **Conceptual Model** | Signal-based (value over time) | Observable streams (collections over time) |
| **Learning Curve** | Gentle, minimal API | Steeper, many operators to learn |
| **Async Integration** | First-class Python `asyncio` support | Separate scheduler system |
| **Dependencies** | Zero external dependencies | Has external dependencies |
| **Granularity** | Value-level reactivity | Stream-level operations |
| **Execution Model** | Pull-based (lazy) | Push-based (eager) |

### reaktiv vs. Manual Observer Pattern

| Feature | reaktiv | Manual Observer Pattern |
|---------|---------|-------------------------|
| **Dependency Tracking** | Automatic | Manual |
| **Granularity** | Fine-grained | Coarse-grained |
| **Boilerplate** | Minimal | Extensive |
| **Memoization** | Built-in | Manual |
| **Memory Management** | Automatic cleanup | Manual cleanup |

## When to Use reaktiv

reaktiv shines in these scenarios:

1. **Complex State Dependencies**: When you have multiple pieces of state that depend on each other
2. **Derived Data**: When you compute values based on other values that change over time
3. **Reactive UIs**: When UI components need to update in response to state changes
4. **Data Processing Pipelines**: When you transform data through multiple steps
5. **Configuration Management**: When you need to compute effective configurations from multiple sources
6. **Caching Systems**: For smart cache invalidation when dependencies change

## When Not to Use reaktiv

reaktiv might not be the best fit for:

1. **Simple State**: If your application state is very simple with few dependencies
2. **Fire-and-forget Events**: For pure event handling without state tracking, a simpler event system may suffice
3. **Stream Processing**: If you're primarily doing stream operations like filtering, mapping large data streams (consider RxPy)
4. **Performance-critical, High-frequency Updates**: For systems where absolute minimal overhead is critical

## The Hidden Cost You Didn't Know You Were Paying

Many developers don't realize they're already paying a cost when managing state manually:

1. **Mental Overhead**: Constantly tracking what needs to update when something changes
2. **Bug Potential**: Forgotten updates leading to inconsistent state
3. **Refactoring Risk**: Adding new derived state requires updating many places
4. **Testing Complexity**: More moving parts to test when state updates are manual

reaktiv eliminates these hidden costs, allowing you to:

- Declare relationships once
- Let the system handle updates automatically
- Focus on business logic rather than state synchronization
- Build more reliable and maintainable applications

Reactive programming isn't just another tool—it's a fundamental shift in how we think about state management that can dramatically simplify complex applications.
