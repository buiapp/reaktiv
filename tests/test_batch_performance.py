import pytest
import asyncio
from unittest.mock import Mock
from reaktiv import Signal, ComputeSignal, Effect, batch


class TestBatchPerformance:
    """Test that batch processing doesn't cause unnecessary computations and effect retriggers."""

    @pytest.mark.asyncio
    async def test_no_unnecessary_computations_in_batch(self):
        """Test that computed signals don't recompute unnecessarily during batch processing."""

        # Create base signals
        a = Signal(1)
        b = Signal(2)
        c = Signal(3)

        # Create mock compute functions to track calls
        compute_ab_mock = Mock(side_effect=lambda: a.get() + b.get())
        compute_bc_mock = Mock(side_effect=lambda: b.get() + c.get())
        compute_independent_mock = Mock(
            side_effect=lambda: 10
        )  # Independent of a, b, c

        # Create computed signals
        computed_ab = ComputeSignal(compute_ab_mock)
        computed_bc = ComputeSignal(compute_bc_mock)
        computed_independent = ComputeSignal(compute_independent_mock)

        # Initial access to establish baselines
        assert computed_ab.get() == 3  # 1 + 2
        assert computed_bc.get() == 5  # 2 + 3
        assert computed_independent.get() == 10

        # Verify initial computations
        assert compute_ab_mock.call_count == 1
        assert compute_bc_mock.call_count == 1
        assert compute_independent_mock.call_count == 1

        # Reset mocks to track only batch operations
        compute_ab_mock.reset_mock()
        compute_bc_mock.reset_mock()
        compute_independent_mock.reset_mock()

        # Perform batch update - only change 'a', which should only affect computed_ab
        with batch():
            a.set(
                5
            )  # This should only affect computed_ab, not computed_bc or computed_independent

        # Force recomputation by accessing values
        result_ab = computed_ab.get()
        result_bc = computed_bc.get()
        result_independent = computed_independent.get()

        # Verify results are correct
        assert result_ab == 7  # 5 + 2
        assert result_bc == 5  # 2 + 3 (unchanged)
        assert result_independent == 10  # unchanged

        # CRITICAL TEST: Only computed_ab should have recomputed
        # computed_bc and computed_independent should NOT have recomputed since their deps didn't change
        assert compute_ab_mock.call_count == 1, (
            "computed_ab should recompute once (dependency 'a' changed)"
        )
        assert compute_bc_mock.call_count == 0, (
            "computed_bc should NOT recompute (no dependencies changed)"
        )
        assert compute_independent_mock.call_count == 0, (
            "computed_independent should NOT recompute (no dependencies changed)"
        )

    @pytest.mark.asyncio
    async def test_no_unnecessary_effect_retriggers_in_batch(self):
        """Test that effects don't retrigger unnecessarily during batch processing."""

        # Create base signals
        x = Signal(1)
        y = Signal(2)
        z = Signal(3)

        # Create computed signals
        computed_xy = ComputeSignal(lambda: x.get() + y.get())
        computed_z = ComputeSignal(lambda: z.get() * 2)

        # Create mock effect functions to track calls
        effect_xy_mock = Mock()
        effect_z_mock = Mock()
        effect_all_mock = Mock()

        # Create effects
        async def effect_xy():
            computed_xy.get()
            effect_xy_mock()

        async def effect_z():
            computed_z.get()
            effect_z_mock()

        async def effect_all():
            computed_xy.get()
            computed_z.get()
            effect_all_mock()

        _effect1 = Effect(effect_xy)
        _effect2 = Effect(effect_z)
        _effect3 = Effect(effect_all)

        # Wait for initial effect runs
        await asyncio.sleep(0)

        # Verify initial runs
        assert effect_xy_mock.call_count == 1
        assert effect_z_mock.call_count == 1
        assert effect_all_mock.call_count == 1

        # Reset mocks to track only batch operations
        effect_xy_mock.reset_mock()
        effect_z_mock.reset_mock()
        effect_all_mock.reset_mock()

        # Perform batch update - only change 'x', which should only affect x-dependent effects
        with batch():
            x.set(5)  # This should only affect effect_xy and effect_all, not effect_z

        # Wait for effects to run
        await asyncio.sleep(0)

        # CRITICAL TEST: Only effects that depend on changed signals should retrigger
        assert effect_xy_mock.call_count == 1, (
            "effect_xy should run once (depends on x via computed_xy)"
        )
        assert effect_z_mock.call_count == 0, (
            "effect_z should NOT run (z didn't change)"
        )
        assert effect_all_mock.call_count == 1, (
            "effect_all should run once (depends on x via computed_xy)"
        )

    @pytest.mark.asyncio
    async def test_no_duplicate_notifications_in_complex_batch(self):
        """Test that effects depending on multiple computed signals don't get duplicate notifications."""

        # Create a diamond dependency pattern
        base = Signal(1)
        left = ComputeSignal(lambda: base.get() + 1)  # depends on base
        right = ComputeSignal(lambda: base.get() * 2)  # depends on base
        combined = ComputeSignal(
            lambda: left.get() + right.get()
        )  # depends on both left and right

        # Create mock effect that depends on both branches
        effect_mock = Mock()

        async def diamond_effect():
            # This effect depends on both left and right through combined
            # It should only run ONCE per batch, not multiple times
            combined.get()
            effect_mock()

        _effect = Effect(diamond_effect)

        # Wait for initial effect run
        await asyncio.sleep(0)
        assert effect_mock.call_count == 1

        # Reset mock
        effect_mock.reset_mock()

        # Perform batch update - this will affect both left and right
        with batch():
            base.set(5)

        # Wait for effects to run
        await asyncio.sleep(0)

        # CRITICAL TEST: Effect should run exactly once, not multiple times
        assert effect_mock.call_count == 1, (
            "Effect should run exactly once, not multiple times for diamond dependency"
        )

    @pytest.mark.asyncio
    async def test_respect_custom_equality_in_batch(self):
        """Test that custom equality functions are respected during batch processing."""

        # Custom equality that considers values within 0.1 as equal
        def close_enough(a, b):
            return abs(a - b) < 0.1

        source = Signal(1.0)
        computed_with_equality = ComputeSignal(
            lambda: source.get() * 2.0, equal=close_enough
        )

        # Create mock effect to track calls
        effect_mock = Mock()

        async def tracking_effect():
            computed_with_equality.get()
            effect_mock()

        _effect = Effect(tracking_effect)

        # Wait for initial effect run
        await asyncio.sleep(0)
        assert effect_mock.call_count == 1

        # Reset mock
        effect_mock.reset_mock()

        # Perform batch update with a small change that should be considered "equal"
        with batch():
            source.set(1.02)  # 1.02 * 2 = 2.04, which is within 0.1 of 2.0

        # Wait for potential effects
        await asyncio.sleep(0)

        # CRITICAL TEST: Effect should NOT run because values are considered equal
        assert effect_mock.call_count == 0, (
            "Effect should not run when computed value is considered equal by custom equality"
        )

        # Reset mock and test a larger change
        effect_mock.reset_mock()

        with batch():
            source.set(1.1)  # 1.1 * 2 = 2.2, which is NOT within 0.1 of 2.04

        await asyncio.sleep(0)

        # Effect should run this time
        assert effect_mock.call_count == 1, (
            "Effect should run when computed value changes beyond equality threshold"
        )

    @pytest.mark.asyncio
    async def test_no_redundant_recomputation_cascading_deps(self):
        """Test that cascading dependencies don't cause redundant recomputations."""

        # Create a chain: base -> level1 -> level2 -> level3
        base = Signal(1)

        # Mock the compute functions to track calls
        level1_mock = Mock(side_effect=lambda: base.get() + 1)
        level2_mock = Mock(side_effect=lambda: level1.get() * 2)
        level3_mock = Mock(side_effect=lambda: level2.get() + 10)

        level1 = ComputeSignal(level1_mock)
        level2 = ComputeSignal(level2_mock)
        level3 = ComputeSignal(level3_mock)

        # Initial access
        assert level3.get() == 14  # ((1 + 1) * 2) + 10 = 14

        # Verify initial computations
        assert level1_mock.call_count == 1
        assert level2_mock.call_count == 1
        assert level3_mock.call_count == 1

        # Reset mocks
        level1_mock.reset_mock()
        level2_mock.reset_mock()
        level3_mock.reset_mock()

        # Perform batch update
        with batch():
            base.set(5)

        # Force recomputation by accessing final value
        result = level3.get()
        assert result == 22  # ((5 + 1) * 2) + 10 = 22

        # CRITICAL TEST: Each level should compute exactly once, not multiple times
        assert level1_mock.call_count == 1, "level1 should compute exactly once"
        assert level2_mock.call_count == 1, "level2 should compute exactly once"
        assert level3_mock.call_count == 1, "level3 should compute exactly once"

    @pytest.mark.asyncio
    async def test_no_computation_when_dependencies_unchanged_in_batch(self):
        """Test that computed signals don't recompute when their dependencies haven't actually changed."""

        # Create signals
        stable = Signal(10)  # This won't change
        changing = Signal(1)  # This will change

        # Create computed signals
        stable_compute_mock = Mock(side_effect=lambda: stable.get() * 2)
        changing_compute_mock = Mock(side_effect=lambda: changing.get() * 3)

        stable_computed = ComputeSignal(stable_compute_mock)
        changing_computed = ComputeSignal(changing_compute_mock)

        # Initial access
        assert stable_computed.get() == 20
        assert changing_computed.get() == 3

        # Reset mocks
        stable_compute_mock.reset_mock()
        changing_compute_mock.reset_mock()

        # Perform batch where only one dependency changes
        with batch():
            changing.set(5)  # Only this changes
            # stable stays the same

        # Access both computed values
        stable_result = stable_computed.get()
        changing_result = changing_computed.get()

        assert stable_result == 20  # unchanged
        assert changing_result == 15  # 5 * 3

        # CRITICAL TEST: Only the changing_computed should have recomputed
        assert stable_compute_mock.call_count == 0, (
            "stable_computed should NOT recompute (dependency unchanged)"
        )
        assert changing_compute_mock.call_count == 1, (
            "changing_computed should recompute once (dependency changed)"
        )

    @pytest.mark.asyncio
    async def test_forced_recomputation_issue_in_deferred_processing(self):
        """Test that reveals the forced recomputation issue in _process_deferred_computed."""

        # Enable debug logging to trace the issue
        from reaktiv.core import set_debug

        set_debug(True)

        try:
            # This test specifically targets the problematic code path in _process_deferred_computed()
            # by manually adding computed signals to the deferred queue

            from reaktiv.core import _deferred_computed_queue

            # Create signals
            a = Signal(1)
            b = Signal(2)

            # Create computed signals with mock functions
            changing_mock = Mock(side_effect=lambda: a.get() + 10)  # Depends on 'a'
            stable_mock = Mock(
                side_effect=lambda: b.get() + 100
            )  # Depends on 'b' (won't change)
            independent_mock = Mock(side_effect=lambda: 999)  # No dependencies

            changing_computed = ComputeSignal(changing_mock)
            stable_computed = ComputeSignal(stable_mock)
            independent_computed = ComputeSignal(independent_mock)

            print(
                f"After creation - changing_computed subscribers: {len(changing_computed._subscribers)}"
            )
            print(
                f"After creation - stable_computed subscribers: {len(stable_computed._subscribers)}"
            )
            print(
                f"After creation - independent_computed subscribers: {len(independent_computed._subscribers)}"
            )

            # Create effects to ensure computed signals have subscribers
            effect_changing_mock = Mock()
            effect_stable_mock = Mock()
            effect_independent_mock = Mock()

            async def effect_changing():
                changing_computed.get()
                effect_changing_mock()

            async def effect_stable():
                stable_computed.get()
                effect_stable_mock()

            async def effect_independent():
                independent_computed.get()
                effect_independent_mock()

            _effect1 = Effect(effect_changing)
            _effect2 = Effect(effect_stable)
            _effect3 = Effect(effect_independent)

            # Wait for initial effect runs
            await asyncio.sleep(0)

            print(
                f"After effects created - changing_computed subscribers: {len(changing_computed._subscribers)}"
            )
            print(
                f"After effects created - stable_computed subscribers: {len(stable_computed._subscribers)}"
            )
            print(
                f"After effects created - independent_computed subscribers: {len(independent_computed._subscribers)}"
            )

            # Verify initial state
            assert changing_computed.get() == 11  # 1 + 10
            assert stable_computed.get() == 102  # 2 + 100
            assert independent_computed.get() == 999

            print(f"Before batch - changing_computed dirty: {changing_computed._dirty}")
            print(f"Before batch - stable_computed dirty: {stable_computed._dirty}")
            print(
                f"Before batch - independent_computed dirty: {independent_computed._dirty}"
            )

            # Reset all mocks
            changing_mock.reset_mock()
            stable_mock.reset_mock()
            independent_mock.reset_mock()
            effect_changing_mock.reset_mock()
            effect_stable_mock.reset_mock()
            effect_independent_mock.reset_mock()

            # Use batch context to trigger the deferred processing path
            with batch():
                # Change only 'a' (should only affect changing_computed)
                print("About to call a.set(5)")
                a.set(5)
                print("Called a.set(5)")

                print(
                    f"After a.set(5) - changing_computed dirty: {changing_computed._dirty}"
                )
                print(
                    f"After a.set(5) - stable_computed dirty: {stable_computed._dirty}"
                )
                print(
                    f"After a.set(5) - independent_computed dirty: {independent_computed._dirty}"
                )

                # Manually add ALL computed signals to deferred queue
                # This simulates the problematic scenario where unrelated signals
                # get queued during batch processing
                _deferred_computed_queue.append(stable_computed)
                _deferred_computed_queue.append(independent_computed)
                print("Manually added stable and independent to deferred queue")

            print("Batch completed")
            print(f"After batch - changing_computed dirty: {changing_computed._dirty}")
            print(f"After batch - stable_computed dirty: {stable_computed._dirty}")
            print(
                f"After batch - independent_computed dirty: {independent_computed._dirty}"
            )

            # The batch completion should call _process_deferred_computed automatically
            # Wait for any effects to run
            await asyncio.sleep(0)

            # CRITICAL TEST: This reveals the forced recomputation issue
            # changing_computed should recompute because its dependency 'a' changed
            print(f"changing_mock call count: {changing_mock.call_count}")
            print(f"stable_mock call count: {stable_mock.call_count}")
            print(f"independent_mock call count: {independent_mock.call_count}")

            assert changing_mock.call_count == 1, (
                "changing_computed should recompute (dependency changed)"
            )

            # These are the PERFORMANCE BUGS we're testing for:
            # stable_computed and independent_computed should NOT recompute since their
            # dependencies haven't changed, but the current implementation forces them to

            # Check for unnecessary recomputations
            stable_recomputed = stable_mock.call_count > 0
            independent_recomputed = independent_mock.call_count > 0

            if stable_recomputed:
                print(
                    f"⚠️  PERFORMANCE ISSUE: stable_computed recomputed {stable_mock.call_count} times unnecessarily"
                )
            if independent_recomputed:
                print(
                    f"⚠️  PERFORMANCE ISSUE: independent_computed recomputed {independent_mock.call_count} times unnecessarily"
                )

            # The fix should ensure these don't recompute unnecessarily
            assert stable_mock.call_count == 0, (
                "stable_computed should NOT recompute (dependencies unchanged)"
            )
            assert independent_mock.call_count == 0, (
                "independent_computed should NOT recompute (no dependencies on changed signals)"
            )

        finally:
            # Disable debug logging
            set_debug(False)
