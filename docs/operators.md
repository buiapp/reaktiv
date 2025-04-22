# Operators

Reaktiv provides several built-in operators that allow you to create new signals derived from existing ones by applying transformations or controlling the timing of emissions. These operators return a read-only signal (`_OperatorSignal`) that automatically updates based on the source signal and the operator's logic.

All operators are designed to work seamlessly with both synchronous and asynchronous effects and computations.

!!! note
    Some operators (`debounce_signal`, `throttle_signal`) rely on internal timers and therefore **require a running `asyncio` event loop** to function correctly. `filter_signal` is purely synchronous and does not have this requirement.

## `filter_signal`

Creates a signal that only emits values from the source signal that satisfy a given predicate function.

**Asyncio Requirement:** No

**Signature:**

```python
filter_signal(
    source: Union[Signal[T], ComputeSignal[T], _OperatorSignal[T]],
    predicate: Callable[[T], bool]
) -> _OperatorSignal[T]
```

**Parameters:**

*   `source`: The input signal (`Signal`, `ComputeSignal`, or another operator signal).
*   `predicate`: A function that takes a value from the source signal and returns `True` if the value should be emitted, `False` otherwise.

**Example:**

```python
import asyncio
from reaktiv import signal, filter_signal, effect # Use shortcut APIs

source = signal(0)
even_numbers = filter_signal(source, lambda x: x % 2 == 0)

# Effect will only run when even_numbers emits a new value
# Keep a reference to the effect
even_effect = effect(lambda: print(f"Got an even number: {even_numbers()}"))

source.set(1) # predicate(1) is False, even_numbers doesn't emit
source.set(2) # predicate(2) is True, even_numbers emits 2
# Output: Got an even number: 2
source.set(3) # predicate(3) is False, even_numbers doesn't emit
source.set(4) # predicate(4) is True, even_numbers emits 4
# Output: Got an even number: 4

# even_effect remains active until it goes out of scope or is disposed
```

## `debounce_signal`

Creates a signal that emits a value from the source signal only after a specified time span has passed without the source emitting any new values. This is useful for scenarios like handling user input where you only want to react after the user has stopped typing for a moment.

**Asyncio Requirement:** Yes

**Signature:**

```python
debounce_signal(
    source: Union[Signal[T], ComputeSignal[T], _OperatorSignal[T]],
    delay_seconds: float
) -> _OperatorSignal[T]
```

**Parameters:**

*   `source`: The input signal.
*   `delay_seconds`: The time in seconds to wait for quiescence before emitting the last value received from the source.

**Example:**

```python
import asyncio
from reaktiv import signal, debounce_signal, effect # Use shortcut APIs

async def main():
    query = signal("")
    # Only process the query 500ms after the user stops typing
    debounced_query = debounce_signal(query, 0.5)

    # Keep a reference to the effect
    query_effect = effect(lambda: print(f"Processing search for: {debounced_query()}"))

    print("User types 're'...")
    query.set("re")
    await asyncio.sleep(0.2)
    print("User types 'aktiv'...")
    query.set("reaktiv") # Timer resets
    await asyncio.sleep(0.2)
    print("User types '!'...")
    query.set("reaktiv!") # Timer resets again

    print("Waiting for debounce...")
    await asyncio.sleep(0.6) # Wait longer than the debounce delay
    # Output: Processing search for: reaktiv!

    # query_effect remains active

asyncio.run(main())
```

## `throttle_signal`

Creates a signal that emits a value from the source signal immediately (if `leading` is `True`), then ignores subsequent source emissions for a specified time interval. It can optionally emit the last value received during the ignored interval when the interval ends (if `trailing` is `True`). This is useful for rate-limiting events, like handling rapid button clicks or frequent sensor updates.

**Asyncio Requirement:** Yes

**Signature:**

```python
throttle_signal(
    source: Union[Signal[T], ComputeSignal[T], _OperatorSignal[T]],
    interval_seconds: float,
    leading: bool = True,
    trailing: bool = False
) -> _OperatorSignal[T]
```

**Parameters:**

*   `source`: The input signal.
*   `interval_seconds`: The duration in seconds during which source emissions are ignored after an emission.
*   `leading`: If `True` (default), emit the first value immediately when it arrives.
*   `trailing`: If `True` (default is `False`), emit the last value received during the throttle interval after the interval has passed.

**Example (Leading only):**

```python
import asyncio
from reaktiv import signal, throttle_signal, effect # Use shortcut APIs

async def main():
    clicks = signal(0)
    # Handle click, but ignore rapid clicks within 200ms
    throttled_clicks = throttle_signal(clicks, 0.2, leading=True, trailing=False)

    # Keep a reference to the effect
    click_effect = effect(lambda: print(f"Click handled! Count: {throttled_clicks()}"))

    print("Rapid clicks...")
    clicks.set(1) # Emitted (leading)
    # Output: Click handled! Count: 1
    await asyncio.sleep(0.05)
    clicks.set(2) # Throttled
    await asyncio.sleep(0.05)
    clicks.set(3) # Throttled

    print("Waiting past interval...")
    await asyncio.sleep(0.2) # Interval ends

    print("Another click...")
    clicks.set(4) # Emitted (leading, interval passed)
    # Output: Click handled! Count: 4

    await asyncio.sleep(0.1)
    # click_effect remains active

asyncio.run(main())
```

**Example (Leading and Trailing):**

```python
import asyncio
from reaktiv import signal, throttle_signal, effect # Use shortcut APIs

async def main():
    sensor = signal(0.0)
    # Process sensor value immediately, and also the last value after 1s interval
    processed_sensor = throttle_signal(sensor, 1.0, leading=True, trailing=True)

    # Keep a reference to the effect
    sensor_effect = effect(lambda: print(f"Processed sensor value: {processed_sensor():.2f}"))

    print("Sensor updates rapidly...")
    sensor.set(10.5) # Emitted (leading)
    # Output: Processed sensor value: 10.50
    await asyncio.sleep(0.3)
    sensor.set(11.2)
    await asyncio.sleep(0.3)
    sensor.set(12.8) # Last value in interval

    print("Waiting for trailing edge...")
    await asyncio.sleep(0.5) # 1.1s total elapsed, interval ended
    # Output: Processed sensor value: 12.80 (trailing)

    await asyncio.sleep(0.1)
    # sensor_effect remains active

asyncio.run(main())
```
