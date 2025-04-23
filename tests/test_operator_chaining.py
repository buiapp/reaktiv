import pytest
from reaktiv import signal, computed, effect, filter_signal, pairwise_signal
import asyncio

def test_computed_filter_pairwise_chain():
    """Tests chaining computed -> filter -> pairwise."""
    # Base signal
    base_signal = signal(1)

    # Computed signal (doubles the base)
    doubled_signal = computed(lambda: base_signal() * 2)

    # Filtered signal (only values > 10)
    filtered_signal = filter_signal(doubled_signal, lambda x: x > 10)

    # Pairwise signal (pairs of consecutive filtered values)
    # Using emit_on_first=True to get the initial value
    pairwise_output = pairwise_signal(filtered_signal, emit_on_first=True)

    def log_results():
        # Log the results for debugging
        print("Base signal:", base_signal())
        print("Doubled signal:", doubled_signal())
        print("Filtered signal:", filtered_signal())
        print("Pairwise output:", pairwise_output())

    log_eff = effect(log_results)

    # Effect to collect results
    results = []
    test_effect = effect(lambda: results.append(pairwise_output()))

    print("Initial state:", pairwise_output())

    # Initial state: pairwise has value of (None, 2) because:
    # 1. Initial doubled value 2 is stored in filtered_signal
    # 2. pairwise_signal with emit_on_first=True emits (None, 2)
    assert results == [(None, 2)]

    # Update base signal -> doubled=12 -> filtered=12
    # The value 12 passes the filter, so filtered_signal updates to 12
    # Since this is the first actual passing value through the filter,
    # pairwise_signal should emit (2, 12) - the previous stored value and new value
    base_signal.set(6)
    assert results == [(None, 2), (2, 12)]
    assert pairwise_output() == (2, 12)

    # Update base signal -> doubled=14 -> filtered=14
    # The value 14 passes the filter, so filtered_signal updates to 14
    # Pairwise emits (previous=12, current=14)
    base_signal.set(7)
    assert results == [(None, 2), (2, 12), (12, 14)]
    assert pairwise_output() == (12, 14)

    # Update base signal -> doubled=6 -> filtered (value <= 10)
    # Filter blocks the value, pairwise does not emit
    base_signal.set(3)
    assert results == [(None, 2), (2, 12), (12, 14)]
    assert pairwise_output() == (12, 14) # Remains the last emitted value

    # Update base signal -> doubled=20 -> filtered=20
    # Pairwise emits (previous=14, current=20)
    base_signal.set(10)
    assert results == [(None, 2), (2, 12), (12, 14), (14, 20)]
    assert pairwise_output() == (14, 20)

    # Update base signal -> doubled=22 -> filtered=22
    # Pairwise emits (previous=20, current=22)
    base_signal.set(11)
    assert results == [(None, 2), (2, 12), (12, 14), (14, 20), (20, 22)]
    assert pairwise_output() == (20, 22)

    # Dispose effect to clean up
    test_effect.dispose()

async def main():
    # Run the test
    test_computed_filter_pairwise_chain()

asyncio.run(main())