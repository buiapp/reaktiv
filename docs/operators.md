# Operators

reaktiv provides several built-in operators that allow you to create new signals derived from existing ones by applying transformations or controlling the timing of emissions. These operators return a read-only signal (`_OperatorSignal`) that automatically updates based on the source signal and the operator's logic.

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
from reaktiv import Signal, filter_signal, Effect

source = Signal(0)
even_numbers = filter_signal(source, lambda x: x % 2 == 0)

# Effect will only run when even_numbers emits a new value
# Keep a reference to the effect
even_effect = Effect(lambda: print(f"Got an even number: {even_numbers()}"))

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
from reaktiv import Signal, debounce_signal, Effect

async def main():
    query = Signal("")
    # Only process the query 500ms after the user stops typing
    debounced_query = debounce_signal(query, 0.5)

    # Keep a reference to the effect
    query_effect = Effect(lambda: print(f"Processing search for: {debounced_query()}"))

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
from reaktiv import Signal, throttle_signal, Effect

async def main():
    clicks = Signal(0)
    # Handle click, but ignore rapid clicks within 200ms
    throttled_clicks = throttle_signal(clicks, 0.2, leading=True, trailing=False)

    # Keep a reference to the effect
    click_effect = Effect(lambda: print(f"Click handled! Count: {throttled_clicks()}"))

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
from reaktiv import Signal, throttle_signal, Effect

async def main():
    sensor = Signal(0.0)
    # Process sensor value immediately, and also the last value after 1s interval
    processed_sensor = throttle_signal(sensor, 1.0, leading=True, trailing=True)

    # Keep a reference to the effect
    sensor_effect = Effect(lambda: print(f"Processed sensor value: {processed_sensor():.2f}"))

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

## `pairwise_signal`

Creates a signal that emits tuples containing the previous and current values from a source signal. This is useful for tracking how values change over time and comparing current values with previous ones.

**Asyncio Requirement:** No

**Signature:**

```python
pairwise_signal(
    source: Union[Signal[T], ComputeSignal[T], _OperatorSignal[T]],
    emit_on_first: bool = False
) -> _OperatorSignal[Optional[Tuple[Optional[T], T]]]
```

**Parameters:**

*   `source`: The input signal.
*   `emit_on_first`: If `True`, emits `(None, first_value)` when the source emits its first value. If `False` (default), the first emission from the source does not produce an output, and the second emission produces `(first_value, second_value)`.

**Example (Default behavior - skip first):**

```python
import asyncio
from reaktiv import Signal, pairwise_signal, Effect

async def main():
    counter = Signal(0)
    # Create a signal that emits (previous, current) tuples
    changes = pairwise_signal(counter)
    
    # Keep a reference to the effect
    change_effect = Effect(lambda: print(f"Counter changed from {changes()[0]} to {changes()[1]}"))
    
    # Initial value doesn't emit with default settings (emit_on_first=False)
    print("Initial state - no effect output yet")
    
    # First change
    counter.set(1)
    # Output: Counter changed from 0 to 1
    
    # Second change  
    counter.set(5)
    # Output: Counter changed from 1 to 5
    
    # When value doesn't change, no emission occurs
    counter.set(5) # No output
    
    # Third change
    counter.set(10)
    # Output: Counter changed from 5 to 10
    
    await asyncio.sleep(0.1)
    # change_effect remains active

asyncio.run(main())
```

**Example (Emit on first value):**

```python
import asyncio
from reaktiv import Signal, pairwise_signal, Effect

async def main():
    price = Signal(100.0)
    # Create a signal that emits (previous, current) tuples, including on first value
    price_changes = pairwise_signal(price, emit_on_first=True)
    
    # Keep a reference to the effect
    # Handle the initial case where previous might be None
    price_effect = Effect(lambda: process_price_change(price_changes()))
    
    def process_price_change(change_tuple):
        prev, curr = change_tuple
        if prev is None:
            print(f"Initial price: ${curr:.2f}")
        else:
            diff = curr - prev
            percent = (diff / prev) * 100 if prev != 0 else 0
            direction = "up" if diff > 0 else "down" if diff < 0 else "unchanged"
            print(f"Price {direction}: ${curr:.2f} (${diff:+.2f}, {percent:+.1f}%)")
    
    # With emit_on_first=True, this produces output for the initial value
    # Output: Initial price: $100.00
    
    # First change
    price.set(105.0)
    # Output: Price up: $105.00 (+$5.00, +5.0%)
    
    # Second change
    price.set(95.5)
    # Output: Price down: $95.50 (-$9.50, -9.0%)
    
    await asyncio.sleep(0.1)
    # price_effect remains active

asyncio.run(main())
```

**Use Cases:**

* Calculating the difference between consecutive values
* Detecting direction of change (increasing/decreasing)
* Tracking value transitions for state machines
* Computing derivatives or rates of change
* Building charts and visualizations with transition animations
