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

```python
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
```

## Data Processing Pipeline

Building a multi-stage data processing pipeline where each step depends on the previous one:

```python
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
# {'count': 3, 'sum': 30, 'average': 10.0}

# Update the raw data - all stages recompute automatically
raw_data.set('{"values": [10, 20, 30, 40]}')
print(stats())
# {'count': 4, 'sum': 3000, 'average': 750.0}
```

## Cache Invalidation

Smart cache invalidation system that automatically refreshes cached data when dependencies change:

```python
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
```

## Form Validation

Complex form validation with interdependent fields:

```python
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
```

## API Data Fetching

Coordinating API data fetching with loading states and automatic refresh:

```python
import asyncio
from reaktiv import Signal, Computed, Effect

async def demo_api_fetching():
    # Signals to control the data fetch
    user_id = Signal(1)
    refresh_trigger = Signal(0)  # Increment to force refresh
    
    # Loading state
    is_loading = Signal(False)
    
    # Error handling
    error = Signal(None)
    
    # Data cache
    user_data = Signal(None)
    
    # Combined fetch key - changes when either user_id or refresh_trigger changes
    fetch_key = Computed(lambda: (user_id(), refresh_trigger()))
    
    # Effect that performs the data fetching
    async def fetch_user_data():
        # Get the current fetch key (creates dependency)
        current_fetch_key = fetch_key()
        user = user_id()
        
        # Reset states
        error.set(None)
        is_loading.set(True)
        
        try:
            # Simulate API call
            await asyncio.sleep(1)  # Pretend this is an API request
            
            # Simulate success or failure based on user_id
            if user % 2 == 0:
                user_data.set({"id": user, "name": f"User {user}", "status": "active"})
            else:
                # Simulate error for odd user IDs
                raise Exception(f"Failed to fetch user {user}")
                
        except Exception as e:
            error.set(str(e))
            user_data.set(None)
        finally:
            is_loading.set(False)
    
    # Create the effect
    fetcher = Effect(fetch_user_data)
    
    # Status reporting effect
    status_reporter = Effect(lambda: print(
        f"User {user_id()}: " +
        (f"Loading..." if is_loading() else
         f"Error: {error()}" if error() else
         f"Data: {user_data()}")
    ))
    
    # Let initial fetch complete
    await asyncio.sleep(1.5)
    
    # Change user - triggers automatic refetch
    print("\nSwitching to user 2...")
    user_id.set(2)
    await asyncio.sleep(1.5)
    
    # Force refresh current user
    print("\nRefreshing current user...")
    refresh_trigger.update(lambda n: n + 1)
    await asyncio.sleep(1.5)
    
    # Switch to user that will cause an error
    print("\nSwitching to user 3 (will cause error)...")
    user_id.set(3)
    await asyncio.sleep(1.5)

# Run the demo
# asyncio.run(demo_api_fetching())
```

## Status Monitoring

Building a reactive system monitoring dashboard:

```python
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
```

Each of these examples demonstrates how reaktiv simplifies complex state management scenarios by automatically handling dependencies and updates. You can build on these patterns to create more complex reactive systems tailored to your specific needs.

For more detailed examples or to contribute your own, visit our [GitHub repository](https://github.com/buiapp/reaktiv).
