# Real-World Examples

This section contains practical examples of using reaktiv in real-world scenarios. These examples demonstrate how reactive programming can simplify complex state management challenges.

## Table of Contents

- [Real-World Examples](#real-world-examples)
  - [Table of Contents](#table-of-contents)
  - [Configuration Management](#configuration-management)
  - [Data Processing Pipeline](#data-processing-pipeline)
  - [Cache Invalidation](#cache-invalidation)
  - [Form Validation](#form-validation)
  - [API Data Fetching](#api-data-fetching)
  - [Status Monitoring](#status-monitoring)

## Configuration Management

Managing configuration from multiple sources (defaults, user settings, environment) with automatic priority resolution:

```pyodide install="reaktiv" height="35" theme="github_light_default,github_dark"
from reaktiv import Signal, Computed, Effect

# Different configuration sources
default_config = Signal({
    "timeout": 30,
    "retries": 3,
    "debug": False,
    "log_level": "INFO"
})

user_config = Signal({})
env_config = Signal({})

# Effective config merges all sources with proper priority
effective_config = Computed(lambda: {
    **default_config(),
    **user_config(),
    **env_config()  # Environment overrides everything
})

# Derived settings that automatically update when any config changes
connection_settings = Computed(lambda: {
    "connect_timeout": effective_config()["timeout"],
    "max_attempts": effective_config()["retries"],
    "verbose": effective_config()["debug"]
})

logger_settings = Computed(lambda: {
    "level": effective_config()["log_level"],
    "debug_mode": effective_config()["debug"]
})

# Effect to log when settings change
config_monitor = Effect(lambda: print(f"Config updated: {effective_config()}"))

# Update a specific config source
user_config.set({"timeout": 60, "log_level": "DEBUG"})
# Automatically updates effective_config, connection_settings, logger_settings
# and triggers the config_monitor effect

# Later, update from environment
env_config.set({"retries": 5})
# Everything dependent on retries updates automatically

print(connection_settings())
print(logger_settings())
config_monitor.dispose()
```

## Data Processing Pipeline

Building a multi-stage data processing pipeline where each step depends on the previous one:

```pyodide install="reaktiv" assets="no" height="32" theme="github_light_default,github_dark"
from reaktiv import Signal, Computed
import json

# Raw data source
raw_data = Signal('{"values": [1, 2, 3, -4, 5, -6]}')

# Parsing stage
parsed_data = Computed(lambda: json.loads(raw_data()))

# Extraction stage
values = Computed(lambda: parsed_data()["values"])

# Filtering stage
positive_values = Computed(lambda: [x for x in values() if x > 0])

# Transformation stage
squared_values = Computed(lambda: [x * x for x in positive_values()])

# Aggregation stage
stats = Computed(lambda: {
    "count": len(squared_values()),
    "sum": sum(squared_values()),
    "average": sum(squared_values()) / len(squared_values()) if squared_values() else 0
})

print(stats())
# {'count': 4, 'sum': 39, 'average': 9.75}

# Update the raw data - all stages recompute automatically
raw_data.set('{"values": [10, 20, 30, 40]}')
print(stats())
# {'count': 4, 'sum': 3000, 'average': 750.0}
```

## Cache Invalidation

Smart cache invalidation system that automatically refreshes cached data when dependencies change:

```pyodide install="reaktiv" assets="no" height="32" theme="github_light_default,github_dark"
from reaktiv import Signal, Computed, Effect
import time

# Simulated database
db = {"user1": {"name": "Alice"}, "user2": {"name": "Bob"}}

# Cache version signal - incremented when database changes
cache_version = Signal(1)

# Active user ID
user_id = Signal("user1")

# This computed value acts as our cache with automatic invalidation
user_data = Computed(lambda: {
    "id": user_id(),
    "data": db[user_id()],  # In real code, this would be a database query
    "cached_at": time.time(),
    "version": cache_version()  # Including version causes cache refresh when version changes
})

# Cache monitor
cache_logger = Effect(lambda: print(
    f"Cache data for user {user_data()['id']}: {user_data()['data']} "
    f"(version: {user_data()['version']})"
))

# Change user - cache recomputes automatically
user_id.set("user2")

# Simulate database update and cache invalidation
db["user2"] = {"name": "Robert"}
cache_version.update(lambda v: v + 1)  # Increment version to invalidate cache
cache_logger.dispose()
```

## Form Validation

Complex form validation with interdependent fields:

```pyodide install="reaktiv" assets="no" height="42" theme="github_light_default,github_dark"
from reaktiv import Signal, Computed, Effect

# Form fields
username = Signal("")
password = Signal("")
password_confirm = Signal("")
email = Signal("")
terms_accepted = Signal(False)

# Individual field validations
username_error = Computed(lambda: 
    "Username is required" if not username() else
    "Username must be at least 3 characters" if len(username()) < 3 else
    None
)

password_error = Computed(lambda:
    "Password is required" if not password() else
    "Password must be at least 8 characters" if len(password()) < 8 else
    None
)

password_match_error = Computed(lambda:
    "Passwords don't match" if password() != password_confirm() else None
)

email_error = Computed(lambda:
    "Email is required" if not email() else
    "Invalid email format" if "@" not in email() else
    None
)

terms_error = Computed(lambda:
    "You must accept the terms" if not terms_accepted() else None
)

# Combined form validation status
form_errors = Computed(lambda: {
    "username": username_error(),
    "password": password_error(),
    "password_confirm": password_match_error(),
    "email": email_error(),
    "terms": terms_error()
})

has_errors = Computed(lambda: any(
    error is not None for error in form_errors().values()
))

# Form submission state
can_submit = Computed(lambda: not has_errors() and terms_accepted())

# Monitor submission state
submission_monitor = Effect(lambda: print(
    f"Form can be submitted: {can_submit()}"
))

# User interaction simulation
username.set("bob")
email.set("bob@example.com")
password.set("password123")
password_confirm.set("password123")
terms_accepted.set(True)
submission_monitor.dispose()
```

## API Data Fetching

Keep request parameters, loading state, errors, and automatic refresh together
in a reactive model:

```pyodide install="reaktiv" assets="no" height="42" theme="github_light_default,github_dark"
import asyncio

from reaktiv import (
    ReactiveModel,
    ResourceLoaderParams,
    ResourceStatus,
    effect,
    field,
    resource,
)


class UserStore(ReactiveModel):
    user_id = field(2)

    def __init__(self):
        self.finished = asyncio.Event()
        super().__init__()

    @resource[int, dict[str, object]]
    def user(self):
        return self.user_id()

    @user.loader
    async def load_user(self, request: ResourceLoaderParams[int]):
        await asyncio.sleep(0.1)  # Replace with an HTTP request.
        user_id = request.params
        if user_id % 2:
            raise RuntimeError(f"User {user_id} was not found")
        return {"id": user_id, "name": f"User {user_id}", "active": True}

    @effect
    def show_status(self):
        status = self.user.status()

        if status in {ResourceStatus.LOADING, ResourceStatus.RELOADING}:
            print(f"Loading user {self.user_id()}...")
        elif status == ResourceStatus.ERROR:
            print(f"Error: {self.user.error()}")
            self.finished.set()
        elif self.user.has_value():
            print(f"Loaded: {self.user.value()}")
            self.finished.set()


async def wait_for_load(store):
    await store.finished.wait()
    store.finished.clear()


store = UserStore()
await wait_for_load(store)

print("\nSwitching users reloads automatically:")
store.user_id.set(4)
await wait_for_load(store)

print("\nRefreshing the current user:")
store.user.reload()
await wait_for_load(store)

print("\nErrors are reactive state too:")
store.user_id.set(3)
await wait_for_load(store)

store.dispose()
```

## Status Monitoring

Building a reactive system monitoring dashboard:

```pyodide install="reaktiv" assets="no" height="45" theme="github_light_default,github_dark"
from reaktiv import Signal, Computed, Effect

# System metrics (in a real app, these would be updated from actual monitoring)
cpu_usage = Signal(25.0)  # percentage
memory_usage = Signal(40.0)  # percentage
disk_usage = Signal(60.0)  # percentage
error_count = Signal(0)
request_count = Signal(1000)

# Derived metrics
error_rate = Computed(lambda: 
    (error_count() / request_count() * 100) if request_count() > 0 else 0
)

# Status thresholds
cpu_status = Computed(lambda:
    "critical" if cpu_usage() > 90 else
    "warning" if cpu_usage() > 70 else
    "normal"
)

memory_status = Computed(lambda:
    "critical" if memory_usage() > 90 else
    "warning" if memory_usage() > 70 else
    "normal"
)

disk_status = Computed(lambda:
    "critical" if disk_usage() > 90 else
    "warning" if disk_usage() > 80 else
    "normal"
)

error_status = Computed(lambda:
    "critical" if error_rate() > 5 else
    "warning" if error_rate() > 1 else
    "normal"
)

# Overall system status (worst of any individual status)
system_status = Computed(lambda: 
    "critical" if any(s() == "critical" for s in (cpu_status, memory_status, disk_status, error_status)) else
    "warning" if any(s() == "warning" for s in (cpu_status, memory_status, disk_status, error_status)) else
    "normal"
)

# Alert system
def alert_system():
    status = system_status()
    components = []
    
    if cpu_status() != "normal":
        components.append(f"CPU: {cpu_usage():.1f}%")
    if memory_status() != "normal":
        components.append(f"Memory: {memory_usage():.1f}%")
    if disk_status() != "normal":
        components.append(f"Disk: {disk_usage():.1f}%")
    if error_status() != "normal":
        components.append(f"Error rate: {error_rate():.2f}%")
    
    if status != "normal":
        print(f"❗ System status: {status.upper()}")
        print(f"   Affected components: {', '.join(components)}")
    else:
        print("✓ System status: NORMAL - All systems operational")

# Monitor status changes
status_monitor = Effect(alert_system)

# Initial output: "✓ System status: NORMAL - All systems operational"

# Simulate memory spike
memory_usage.set(75.0)
# Output: "❗ System status: WARNING
#          Affected components: Memory: 75.0%"

# Simulate error increase
error_count.set(100)
request_count.set(1000)
# Output: "❗ System status: WARNING
#          Affected components: Memory: 75.0%, Error rate: 10.00%"

# Simulate critical CPU spike
cpu_usage.set(95.0)
# Output: "❗ System status: CRITICAL
#          Affected components: CPU: 95.0%, Memory: 75.0%, Error rate: 10.00%"

# Simulate recovery
memory_usage.set(50.0)
cpu_usage.set(30.0)
error_count.set(5)
# Output: "❗ System status: WARNING
#          Affected components: Error rate: 0.50%"

# Full recovery
error_count.set(0)
# Output: "✓ System status: NORMAL - All systems operational"
status_monitor.dispose()
```

Each of these examples demonstrates how reaktiv simplifies complex state management scenarios by automatically handling dependencies and updates. You can build on these patterns to create more complex reactive systems tailored to your specific needs.

For more detailed examples or to contribute your own, visit our [GitHub repository](https://github.com/buiapp/reaktiv).
