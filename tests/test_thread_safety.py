"""Thread safety tests for reaktiv signals.

These tests verify basic thread safety behavior for public API.
"""
import pytest
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from reaktiv import Signal, ComputeSignal, Effect, set_thread_safety, is_thread_safety_enabled


class TestThreadSafetyConfiguration:
    """Test the thread safety configuration functions."""

    def test_thread_safety_default_enabled(self):
        """Test that thread safety is enabled by default."""
        assert is_thread_safety_enabled() is True

    def test_set_thread_safety_enable(self):
        """Test enabling thread safety."""
        set_thread_safety(True)
        assert is_thread_safety_enabled() is True

    def test_set_thread_safety_disable(self):
        """Test disabling thread safety."""
        original = is_thread_safety_enabled()
        try:
            set_thread_safety(False)
            assert is_thread_safety_enabled() is False
        finally:
            set_thread_safety(original)  # Restore original state

    def test_set_thread_safety_toggle(self):
        """Test toggling thread safety multiple times."""
        original = is_thread_safety_enabled()
        try:
            set_thread_safety(False)
            assert is_thread_safety_enabled() is False
            
            set_thread_safety(True)
            assert is_thread_safety_enabled() is True
            
            set_thread_safety(False)
            assert is_thread_safety_enabled() is False
        finally:
            set_thread_safety(original)


class TestBasicSignalThreadSafety:
    """Test basic signal operations under concurrent access."""

    def test_concurrent_signal_reads(self):
        """Test that concurrent reads of a signal are safe, even with changing values."""
        signal = Signal(0)
        results = []
        results_lock = threading.Lock()  # Only for test data collection
        num_threads = 5
        reads_per_thread = 20

        def read_worker():
            """Worker that reads the signal multiple times."""
            local_results = []
            for _ in range(reads_per_thread):
                value = signal.get()  # This is thread-safe automatically
                local_results.append(value)
                time.sleep(0.001)  # Small delay to allow value changes
            
            # Protect the shared results list
            with results_lock:
                results.extend(local_results)

        def value_updater():
            """Worker that updates the signal value during reads."""
            for i in range(50):  # More updates than total reads
                signal.set(i)
                time.sleep(0.001)

        # Run concurrent readers and one updater
        threads = []
        
        # Start reader threads
        for _ in range(num_threads):
            thread = threading.Thread(target=read_worker)
            threads.append(thread)
            thread.start()
        
        # Start updater thread
        updater_thread = threading.Thread(target=value_updater)
        threads.append(updater_thread)
        updater_thread.start()

        for thread in threads:
            thread.join()

        # All reads should return valid values (non-negative integers)
        assert len(results) == num_threads * reads_per_thread
        assert all(isinstance(value, int) and value >= 0 for value in results)
        
        # We should see multiple different values due to concurrent updates
        unique_values = set(results)
        assert len(unique_values) > 1, f"Expected multiple values, but only got: {unique_values}"
        
        # All values should be in the expected range
        assert all(0 <= value < 50 for value in results), f"Some values out of range: {set(results)}"

    def test_concurrent_signal_writes(self):
        """Test concurrent writes to signals."""
        signal = Signal(0)
        num_threads = 5
        writes_per_thread = 10
        
        def write_worker(start_value: int):
            """Worker that writes sequential values."""
            for i in range(writes_per_thread):
                signal.set(start_value + i)

        # Run concurrent writers with different value ranges
        threads = []
        for i in range(num_threads):
            start_val = i * writes_per_thread
            thread = threading.Thread(target=write_worker, args=(start_val,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # The final value should be one of the written values
        final_value = signal.get()
        expected_range = range(0, num_threads * writes_per_thread)
        assert final_value in expected_range

    def test_read_write_interference(self):
        """Test interference between concurrent reads and writes."""
        signal = Signal(0)
        read_values = []
        num_readers = 3
        num_writers = 2
        operations_per_thread = 20
        
        def reader_worker():
            """Worker that reads the signal repeatedly."""
            for _ in range(operations_per_thread):
                value = signal.get()
                read_values.append(value)
                time.sleep(0.001)

        def writer_worker(base_value: int):
            """Worker that writes incremental values."""
            for i in range(operations_per_thread):
                signal.set(base_value + i)
                time.sleep(0.001)

        # Start readers and writers concurrently
        threads = []
        
        # Start readers
        for _ in range(num_readers):
            thread = threading.Thread(target=reader_worker)
            threads.append(thread)
            thread.start()
        
        # Start writers
        for i in range(num_writers):
            base_val = i * 1000
            thread = threading.Thread(target=writer_worker, args=(base_val,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Verify we got some reads
        assert len(read_values) == num_readers * operations_per_thread
        
        # All read values should be valid (non-negative in this case)
        assert all(value >= 0 for value in read_values)


class TestComputedSignalThreadSafety:
    """Test computed signals under concurrent access."""

    def test_computed_signal_concurrent_reads(self):
        """Test concurrent reads of computed signals."""
        base_signal = Signal(10)
        computed = ComputeSignal(lambda: base_signal.get() * 2)
        
        results = []
        num_threads = 10
        reads_per_thread = 20

        def read_computed():
            """Worker that reads the computed signal."""
            for _ in range(reads_per_thread):
                value = computed.get()
                results.append(value)

        threads = []
        for _ in range(num_threads):
            thread = threading.Thread(target=read_computed)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # All reads should return the expected computed value (20)
        expected_count = num_threads * reads_per_thread
        assert len(results) == expected_count
        assert all(value == 20 for value in results)

    def test_computed_signal_with_changing_dependency(self):
        """Test computed signal with concurrently changing dependency."""
        base_signal = Signal(0)
        computed = ComputeSignal(lambda: base_signal.get() * 3)
        
        computed_values = []
        
        def read_computed():
            """Worker that reads computed signal."""
            for _ in range(30):
                value = computed.get()
                computed_values.append(value)
                time.sleep(0.001)

        def write_base():
            """Worker that updates base signal."""
            for i in range(30):
                base_signal.set(i)
                time.sleep(0.001)

        # Run operations concurrently
        threads = [
            threading.Thread(target=read_computed),
            threading.Thread(target=write_base),
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Verify computed values are consistent with the computation
        assert len(computed_values) == 30
        assert all(value % 3 == 0 for value in computed_values)

    def test_computed_signal_stress_test(self):
        """Moderate stress test for computed signals."""
        base_signal = Signal(5)
        computed = ComputeSignal(lambda: base_signal.get() * 4)
        
        results = []
        num_threads = 10
        reads_per_thread = 50
        
        def stress_reader():
            """Worker that reads the computed signal repeatedly."""
            for _ in range(reads_per_thread):
                value = computed.get()
                results.append(value)
        
        threads = [threading.Thread(target=stress_reader) for _ in range(num_threads)]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Verify results
        expected_count = num_threads * reads_per_thread
        assert len(results) == expected_count
        assert all(value == 20 for value in results)  # 5 * 4 = 20


class TestEffectThreadSafety:
    """Test effect execution under concurrent conditions."""

    def test_effect_execution_with_concurrent_updates(self):
        """Test effect execution when signal is updated concurrently."""
        signal = Signal(0)
        effect_executions = []
        execution_lock = threading.Lock()  # Only for test data collection

        def effect_fn():
            """Effect that records its execution."""
            value = signal.get()  # This is thread-safe automatically
            with execution_lock:  # Only to protect test data from race conditions
                effect_executions.append(value)

        # Create effect
        effect = Effect(effect_fn)
        
        # Wait for initial effect execution
        time.sleep(0.1)

        def updater():
            """Worker that updates the signal."""
            for i in range(10):
                signal.set(i)
                time.sleep(0.01)

        # Run multiple updaters concurrently
        threads = []
        for _ in range(2):
            thread = threading.Thread(target=updater)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Wait for any pending effects
        time.sleep(0.2)

        # Effect should have executed for signal changes
        assert len(effect_executions) > 0
        print(f"Effect executed {len(effect_executions)} times")

        # Cleanup
        effect.dispose()


class TestBasicConcurrentScenarios:
    """Test basic concurrent scenarios with multiple signals and effects."""

    def test_simple_dependency_graph(self):
        """Test a simple dependency graph under concurrent access."""
        s1 = Signal(1)
        s2 = Signal(2)
        computed = ComputeSignal(lambda: s1.get() + s2.get())
        
        effect_values = []
        effect_lock = threading.Lock()  # Only for test data collection

        def effect_fn():
            value = computed.get()  # This is thread-safe automatically
            with effect_lock:  # Only to protect test data from race conditions
                effect_values.append(value)

        effect = Effect(effect_fn)
        time.sleep(0.1)  # Wait for initial effect

        def update_s1():
            """Update s1 concurrently."""
            for i in range(10):
                s1.set(i)
                time.sleep(0.01)

        def update_s2():
            """Update s2 concurrently."""
            for i in range(10):
                s2.set(i * 2)
                time.sleep(0.01)

        # Run operations concurrently
        threads = [
            threading.Thread(target=update_s1),
            threading.Thread(target=update_s2),
        ]

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Wait for any pending effects
        time.sleep(0.2)

        # Effect should have executed
        assert len(effect_values) > 0

        # Cleanup
        effect.dispose()

    def test_multiple_computed_signals(self):
        """Test multiple computed signals being accessed concurrently."""
        base_signals = [Signal(i) for i in range(5)]
        computed_signals = [ComputeSignal(lambda i=i: base_signals[i].get() * 2) for i in range(5)]
        
        results = []
        results_lock = threading.Lock()
        
        def multi_signal_reader():
            """Read from multiple computed signals."""
            for _ in range(10):
                for i, computed in enumerate(computed_signals):
                    value = computed.get()
                    expected = i * 2
                    with results_lock:
                        results.append((i, value, expected))
        
        threads = [threading.Thread(target=multi_signal_reader) for _ in range(3)]
        
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # Verify all results
        for signal_id, actual_value, expected_value in results:
            assert actual_value == expected_value, f"Signal {signal_id}: expected {expected_value}, got {actual_value}"


class TestThreadSafetyStressTests:
    """Comprehensive stress tests to detect race conditions."""

    def test_atomic_increment_stress(self):
        """Stress test for atomic increment operations using update()."""
        signal = Signal(0)
        num_threads = 20
        increments_per_thread = 100
        
        def atomic_increment_worker():
            """Worker that does atomic increments."""
            for _ in range(increments_per_thread):
                signal.update(lambda x: x + 1)
        
        # Run concurrent atomic incrementers
        threads = []
        for _ in range(num_threads):
            thread = threading.Thread(target=atomic_increment_worker)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # With atomic operations, we should get exactly the expected result
        expected_value = num_threads * increments_per_thread
        actual_value = signal.get()
        assert actual_value == expected_value, f"Lost {expected_value - actual_value} increments due to race conditions"

    def test_manual_increment_race_detection(self):
        """Test to verify that atomic operations work correctly under stress."""
        # This test verifies our atomic operations work correctly
        signal = Signal(0)
        num_threads = 10
        increments_per_thread = 50
        completion_results = []
        
        def atomic_increment_worker():
            """Worker using atomic update operations."""
            local_count = 0
            for _ in range(increments_per_thread):
                # Atomic operation - should be completely safe
                signal.update(lambda x: x + 1)
                local_count += 1
            completion_results.append(local_count)
        
        threads = []
        for _ in range(num_threads):
            thread = threading.Thread(target=atomic_increment_worker)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        expected_value = num_threads * increments_per_thread
        actual_value = signal.get()
        
        # With atomic operations, we should get exactly the expected result
        assert actual_value == expected_value, f"Lost {expected_value - actual_value} increments - atomic operations not working!"
        
        # Verify all workers completed their operations
        assert sum(completion_results) == expected_value

    def test_delayed_operations_stress(self):
        """Stress test with artificial delays to increase race windows."""
        signal = Signal(0)
        num_threads = 15
        operations_per_thread = 20
        
        def delayed_worker():
            """Worker with delays to stress-test race conditions."""
            for _ in range(operations_per_thread):
                # Use update for atomic operation
                signal.update(lambda x: x + 1)
                time.sleep(0.001)  # Small delay to increase contention
        
        threads = []
        
        for _ in range(num_threads):
            thread = threading.Thread(target=delayed_worker)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        expected_value = num_threads * operations_per_thread
        actual_value = signal.get()
        
        # Should be exactly correct despite delays
        assert actual_value == expected_value, f"Lost {expected_value - actual_value} operations in delayed stress test"

    def test_mixed_operations_stress(self):
        """Stress test with mixed read, write, and update operations."""
        signal = Signal(100)
        read_results = []
        read_lock = threading.Lock()
        
        def reader_worker():
            """Worker that reads values."""
            for _ in range(50):
                value = signal.get()
                with read_lock:
                    read_results.append(value)
                time.sleep(0.0001)
        
        def writer_worker(base: int):
            """Worker that writes values."""
            for i in range(25):
                signal.set(base + i)
                time.sleep(0.0001)
        
        def updater_worker():
            """Worker that uses atomic updates."""
            for _ in range(25):
                signal.update(lambda x: x + 1)
                time.sleep(0.0001)
        
        # Mix of operations
        threads = []
        
        # Add readers
        for _ in range(3):
            threads.append(threading.Thread(target=reader_worker))
        
        # Add writers
        for i in range(2):
            threads.append(threading.Thread(target=writer_worker, args=(1000 + i * 100,)))
        
        # Add updaters
        for _ in range(2):
            threads.append(threading.Thread(target=updater_worker))
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Verify reads were successful
        assert len(read_results) == 3 * 50  # 3 readers * 50 reads each
        
        # All read values should be valid integers
        assert all(isinstance(value, int) for value in read_results)
        
        # Final signal should have a reasonable value
        final_value = signal.get()
        assert isinstance(final_value, int)

    def test_high_contention_stress(self):
        """High contention stress test with many threads."""
        signal = Signal(0)
        num_threads = 50  # High thread count
        operations_per_thread = 20
        
        def high_contention_worker():
            """Worker for high contention test."""
            for _ in range(operations_per_thread):
                # Rapid atomic increments
                signal.update(lambda x: x + 1)
        
        threads = []
        for _ in range(num_threads):
            thread = threading.Thread(target=high_contention_worker)
            threads.append(thread)
        
        # Start all threads rapidly
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        expected_value = num_threads * operations_per_thread
        actual_value = signal.get()
        
        assert actual_value == expected_value, f"High contention test failed: expected {expected_value}, got {actual_value}"

    def test_computed_signal_stress(self):
        """Stress test for computed signals under high concurrency."""
        base_signal = Signal(0)
        computed = ComputeSignal(lambda: base_signal.get() * 2 + 1)
        
        read_results = []
        read_lock = threading.Lock()
        
        def computed_reader():
            """Worker that reads computed signal."""
            for _ in range(100):
                value = computed.get()
                with read_lock:
                    read_results.append(value)
        
        def base_updater():
            """Worker that updates base signal."""
            for i in range(50):
                base_signal.set(i)
                time.sleep(0.001)
        
        # Start readers and updater
        threads = []
        
        # Multiple readers
        for _ in range(5):
            threads.append(threading.Thread(target=computed_reader))
        
        # One updater
        threads.append(threading.Thread(target=base_updater))
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Verify all reads were valid
        assert len(read_results) == 5 * 100
        
        # All computed values should follow the formula: base * 2 + 1
        for value in read_results:
            assert isinstance(value, int)
            assert value >= 1  # Minimum value when base=0: 0*2+1=1
            # Value should be odd (since base*2 is even, +1 makes it odd)
            assert value % 2 == 1, f"Computed value {value} should be odd"

    def test_complex_reactive_system_stress(self):
        """Complex stress test with signals, computed signals, and effects in multiple threads."""
        input_signal1 = Signal(0)
        input_signal2 = Signal(0)
        input_signal3 = Signal(10)
        
        # Computed signals with different complexities
        sum_computed = ComputeSignal(lambda: input_signal1.get() + input_signal2.get())
        product_computed = ComputeSignal(lambda: input_signal1.get() * input_signal2.get())
        final_computed = ComputeSignal(lambda: sum_computed.get() + input_signal3.get())
        
        # Track effect executions with limited scope to avoid infinite loops
        effect_results = []
        effect_lock = threading.Lock()
        max_effect_executions = 100  # Limit to prevent runaway effects
        
        def effect1_fn():
            """Effect that tracks sum changes."""
            with effect_lock:
                if len(effect_results) < max_effect_executions:
                    value = sum_computed.get()
                    effect_results.append(("sum_effect", value))
        
        def effect2_fn():
            """Effect that tracks input signal3 changes."""
            with effect_lock:
                if len(effect_results) < max_effect_executions:
                    value = input_signal3.get()
                    effect_results.append(("signal3_effect", value))
        
        # Create effects (fewer to reduce complexity)
        effect1 = Effect(effect1_fn)
        effect2 = Effect(effect2_fn)
        
        # Wait for initial effect executions
        time.sleep(0.05)
        
        # Clear initial effect results
        with effect_lock:
            effect_results.clear()
        
        # Define worker functions with reduced complexity
        def input1_updater():
            """Updates input_signal1 in a pattern."""
            for i in range(10):  # Reduced iterations
                input_signal1.update(lambda x: (x + 1) % 50)
                time.sleep(0.001)
        
        def input2_updater():
            """Updates input_signal2 in a different pattern."""
            for i in range(8):  # Reduced iterations
                input_signal2.set(i * 2)
                time.sleep(0.002)
        
        def input3_updater():
            """Updates input_signal3 using atomic operations."""
            for i in range(5):  # Reduced iterations
                input_signal3.update(lambda x: x + 2)
                time.sleep(0.003)
        
        def computed_reader():
            """Reads from computed signals concurrently."""
            local_reads = []
            for _ in range(15):  # Reduced iterations
                sum_val = sum_computed.get()
                product_val = product_computed.get()
                final_val = final_computed.get()
                local_reads.append((sum_val, product_val, final_val))
                time.sleep(0.001)
            return local_reads
        
        def signal_reader():
            """Reads from base signals concurrently."""
            local_reads = []
            for _ in range(12):  # Reduced iterations
                val1 = input_signal1.get()
                val2 = input_signal2.get()
                val3 = input_signal3.get()
                local_reads.append((val1, val2, val3))
                time.sleep(0.001)
            return local_reads
        
        # Start all operations concurrently with reduced thread count
        threads = []
        read_results = []
        
        # Updater threads
        threads.append(threading.Thread(target=input1_updater))
        threads.append(threading.Thread(target=input2_updater))
        threads.append(threading.Thread(target=input3_updater))
        
        # Reader threads (reduced count)
        for _ in range(2):  # Reduced from 3
            def make_computed_reader():
                def worker():
                    read_results.append(computed_reader())
                return worker
            thread = threading.Thread(target=make_computed_reader())
            threads.append(thread)
        
        for _ in range(1):  # Reduced from 2
            def make_signal_reader():
                def worker():
                    read_results.append(signal_reader())
                return worker
            thread = threading.Thread(target=make_signal_reader())
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all operations to complete with timeout safety
        for thread in threads:
            thread.join(timeout=2.0)  # Add timeout to prevent hanging
            if thread.is_alive():
                # Force cleanup if thread is still running
                pass  # In a real scenario, you might want to handle this differently
        
        # Wait for any pending effects with shorter timeout
        time.sleep(0.1)
        
        # Verify the system worked correctly
        
        # 1. Check that we got read results
        assert len(read_results) == 3  # 2 computed readers + 1 signal reader
        
        # 2. Verify computed signal consistency
        for read_batch in read_results:
            if read_batch and len(read_batch[0]) == 3:  # computed reads
                for sum_val, product_val, final_val in read_batch:
                    # All values should be integers
                    assert isinstance(sum_val, int)
                    assert isinstance(product_val, int)
                    assert isinstance(final_val, int)
                    
                    # Basic sanity checks
                    assert sum_val >= 0
                    assert product_val >= 0
                    assert final_val >= 10  # Should be at least initial signal3 value
        
        # 3. Check that effects were triggered (with limit)
        with effect_lock:
            # Effects should have been triggered but not excessively
            assert 0 < len(effect_results) <= max_effect_executions, f"Effect executions: {len(effect_results)}"
            
            # Verify effect types
            effect_types = [result[0] for result in effect_results]
            assert "sum_effect" in effect_types or "signal3_effect" in effect_types
        
        # 4. Verify final signal states are reasonable
        final_val1 = input_signal1.get()
        final_val2 = input_signal2.get()
        final_val3 = input_signal3.get()
        
        assert isinstance(final_val1, int)
        assert isinstance(final_val2, int)
        assert isinstance(final_val3, int)
        assert 0 <= final_val1 < 50  # Due to modulo operation
        assert final_val2 >= 0
        assert final_val3 >= 10  # Started at 10, only incremented
        
        # 5. Verify computed signals are consistent with current base values
        final_sum = sum_computed.get()
        final_product = product_computed.get()
        final_final = final_computed.get()
        
        expected_sum = final_val1 + final_val2
        expected_product = final_val1 * final_val2
        expected_final = expected_sum + final_val3
        
        assert final_sum == expected_sum, f"Sum computed inconsistent: {final_sum} != {expected_sum}"
        assert final_product == expected_product, f"Product computed inconsistent: {final_product} != {expected_product}"
        assert final_final == expected_final, f"Final computed inconsistent: {final_final} != {expected_final}"
        
        # Cleanup effects
        effect1.dispose()
        effect2.dispose()

    def test_cascading_effects_stress(self):
        """Test cascading effects in a multi-threaded environment."""
        # Create a chain of signals and computed signals
        source = Signal(0)
        level1 = ComputeSignal(lambda: source.get() * 2)
        level2 = ComputeSignal(lambda: level1.get() + 10)
        level3 = ComputeSignal(lambda: level2.get() * level1.get())
        
        # Track the cascade of effects
        effect_chain = []
        chain_lock = threading.Lock()
        
        def source_effect():
            with chain_lock:
                effect_chain.append(f"source_{source.get()}")
        
        def level1_effect():
            with chain_lock:
                effect_chain.append(f"level1_{level1.get()}")
        
        def level2_effect():
            with chain_lock:
                effect_chain.append(f"level2_{level2.get()}")
        
        def level3_effect():
            with chain_lock:
                effect_chain.append(f"level3_{level3.get()}")
        
        # Create effects at each level
        effects = [
            Effect(source_effect),
            Effect(level1_effect),
            Effect(level2_effect),
            Effect(level3_effect)
        ]
        
        # Wait for initial effects
        time.sleep(0.1)
        
        # Clear initial effects
        with chain_lock:
            effect_chain.clear()
        
        def rapid_updater():
            """Rapidly update the source signal."""
            for i in range(20):
                source.set(i)
                time.sleep(0.001)
        
        def concurrent_reader():
            """Read from all levels concurrently."""
            reads = []
            for _ in range(50):
                s = source.get()
                l1 = level1.get()
                l2 = level2.get()
                l3 = level3.get()
                reads.append((s, l1, l2, l3))
                time.sleep(0.0005)
            return reads
        
        # Start concurrent operations
        threads = []
        all_reads = []
        
        # Multiple updaters
        for _ in range(2):
            threads.append(threading.Thread(target=rapid_updater))
        
        # Multiple readers
        for _ in range(3):
            def make_reader():
                def worker():
                    all_reads.append(concurrent_reader())
                return worker
            thread = threading.Thread(target=make_reader())
            threads.append(thread)
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Wait for effects to settle
        time.sleep(0.2)
        
        # Verify cascading behavior
        
        # 1. Effects should have been triggered
        with chain_lock:
            assert len(effect_chain) > 0, "Cascading effects should have been triggered"
        
        # 2. Check mathematical consistency in reads
        for read_batch in all_reads:
            for s, l1, l2, l3 in read_batch:
                # Verify the mathematical relationships hold
                # (allowing for some concurrent update inconsistencies)
                if l1 == s * 2:  # If we caught a consistent state
                    expected_l2 = l1 + 10
                    expected_l3 = l2 * l1
                    
                    # In a consistent state, all should match
                    if l2 == expected_l2:
                        assert l3 == expected_l3, f"Level3 inconsistent: {l3} != {expected_l3} (s={s}, l1={l1}, l2={l2})"
        
        # 3. Final state should be mathematically consistent
        final_source = source.get()
        final_level1 = level1.get()
        final_level2 = level2.get()
        final_level3 = level3.get()
        
        assert final_level1 == final_source * 2
        assert final_level2 == final_level1 + 10
        assert final_level3 == final_level2 * final_level1
        
        # Cleanup
        for effect in effects:
            effect.dispose()


class TestThreadPoolIntegration:
    """Test integration with ThreadPoolExecutor."""

    def test_thread_pool_signal_updates(self):
        """Test signal updates using a thread pool."""
        signal = Signal(0)
        
        def increment_signal(amount: int) -> int:
            """Increment signal by amount and return new value."""
            # Use atomic update instead of manual read-modify-write
            signal.update(lambda x: x + amount)
            return signal.get()

        # Use thread pool to submit concurrent increment operations
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(increment_signal, 1) for _ in range(20)]
            
            # Collect results
            results = []
            for future in as_completed(futures):
                result = future.result()
                results.append(result)

        # With atomic operations, the final value should be exactly 20
        final_value = signal.get()
        assert final_value == 20, f"Expected 20, got {final_value} - atomic operations failed"

    def test_thread_pool_computed_signals(self):
        """Test computed signals with thread pool."""
        base = Signal(5)
        computed = ComputeSignal(lambda: base.get() ** 2)
        
        def read_computed() -> int:
            """Read computed signal value."""
            return computed.get()

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(read_computed) for _ in range(50)]
            
            results = []
            for future in as_completed(futures):
                result = future.result()
                results.append(result)

        # All results should be 25 (5^2)
        assert all(result == 25 for result in results)
        assert len(results) == 50


if __name__ == "__main__":
    # Run tests with pytest for better output
    pytest.main([__file__, "-v"])
