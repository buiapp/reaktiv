import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from reaktiv import Effect, Signal, Computed, ComputeSignal, LinkedSignal, batch, untracked


@dataclass(frozen=True)
class _UltimateGraphState:
    version: int
    base: int
    quantity: int
    tax: int
    discount: int
    option: int


def _join_all(threads):
    for thread in threads:
        thread.join(timeout=2)
    assert not [thread.name for thread in threads if thread.is_alive()]


def test_independent_graph_effect_flush_is_not_blocked_by_other_graph_effect():
    left = Signal(0)
    right = Signal(0)

    left_effect_entered = threading.Event()
    release_left_effect = threading.Event()
    right_set_completed = threading.Event()
    right_effect_ran = threading.Event()
    right_effect_values = []
    right_effect_lock = threading.Lock()

    def left_effect():
        if left() == 1:
            left_effect_entered.set()
            assert release_left_effect.wait(timeout=2)

    def right_effect():
        with right_effect_lock:
            right_effect_values.append(right())
        right_effect_ran.set()

    left_ref = Effect(left_effect)
    right_ref = Effect(right_effect)

    with right_effect_lock:
        right_effect_values.clear()
    right_effect_ran.clear()

    left_thread = threading.Thread(target=lambda: left.set(1))
    left_thread.start()
    assert left_effect_entered.wait(timeout=2)

    right_thread = threading.Thread(
        target=lambda: (right.set(1), right_set_completed.set())
    )
    right_thread.start()

    assert right_set_completed.wait(timeout=2)
    assert right() == 1
    assert right_effect_ran.wait(timeout=2)

    with right_effect_lock:
        assert right_effect_values == [1]

    release_left_effect.set()
    left_thread.join(timeout=2)
    right_thread.join(timeout=2)

    assert not left_thread.is_alive()
    assert not right_thread.is_alive()
    left_ref.dispose()
    right_ref.dispose()


def test_independent_complex_graphs_can_recompute_in_parallel():
    left_base = Signal(1)
    right_base = Signal(10)

    left_entered = threading.Event()
    right_entered = threading.Event()
    release = threading.Event()
    overlap = []
    overlap_lock = threading.Lock()

    left_mid = Computed(lambda: left_base() * 2)
    right_mid = Computed(lambda: right_base() + 7)

    def left_compute():
        if left_base() == 2:
            left_entered.set()
            assert right_entered.wait(timeout=2)
            assert release.wait(timeout=2)
        return left_mid() + 3

    def right_compute():
        if right_base() == 20:
            right_entered.set()
            assert left_entered.wait(timeout=2)
            with overlap_lock:
                overlap.append("both-running")
            assert release.wait(timeout=2)
        return right_mid() * 5

    left_final = Computed(left_compute)
    right_final = Computed(right_compute)

    assert left_final() == 5
    assert right_final() == 85

    left_base.set(2)
    right_base.set(20)

    results = {}
    left_thread = threading.Thread(target=lambda: results.update(left=left_final()))
    right_thread = threading.Thread(target=lambda: results.update(right=right_final()))

    left_thread.start()
    right_thread.start()

    assert left_entered.wait(timeout=2)
    assert right_entered.wait(timeout=2)
    release.set()
    left_thread.join(timeout=2)
    right_thread.join(timeout=2)

    assert not left_thread.is_alive()
    assert not right_thread.is_alive()
    assert results == {"left": 7, "right": 135}
    assert overlap == ["both-running"]


def test_shared_subgraph_computed_recomputation_is_serialized_per_computed():
    base = Signal(0)
    started = threading.Event()
    finish = threading.Event()
    compute_entries = 0
    compute_lock = threading.Lock()

    def compute_shared():
        nonlocal compute_entries
        if base() == 1:
            with compute_lock:
                compute_entries += 1
            started.set()
            assert finish.wait(timeout=2)
        return base() * 10

    shared = Computed(compute_shared)

    assert shared() == 0
    base.set(1)

    first_result = {}
    second_result = {}
    first = threading.Thread(target=lambda: first_result.update(value=shared()))
    second = threading.Thread(target=lambda: second_result.update(value=shared()))

    first.start()
    assert started.wait(timeout=2)
    second.start()
    time.sleep(0.05)

    assert second.is_alive()
    with compute_lock:
        assert compute_entries == 1

    finish.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert first_result == {"value": 10}
    assert second_result == {"value": 10}
    with compute_lock:
        assert compute_entries == 1


def test_dependent_graphs_should_serialize_at_shared_dependency_boundary():
    source = Signal(1)
    shared_started = threading.Event()
    release_shared = threading.Event()
    compute_entries = 0
    compute_lock = threading.Lock()

    def compute_shared():
        nonlocal compute_entries
        if source() == 2:
            with compute_lock:
                compute_entries += 1
            shared_started.set()
            assert release_shared.wait(timeout=2)
        return source() * 2

    shared = Computed(compute_shared)
    left = Computed(lambda: shared() + 1)
    right = Computed(lambda: shared() + 100)

    assert left() == 3
    assert right() == 102

    source.set(2)

    left_result = {}
    right_result = {}
    left_thread = threading.Thread(target=lambda: left_result.update(value=left()))
    right_thread = threading.Thread(target=lambda: right_result.update(value=right()))

    left_thread.start()
    assert shared_started.wait(timeout=2)
    right_thread.start()
    time.sleep(0.05)

    try:
        assert right_thread.is_alive()
        with compute_lock:
            assert compute_entries == 1

        release_shared.set()
        left_thread.join(timeout=2)
        right_thread.join(timeout=2)

        assert not left_thread.is_alive()
        assert not right_thread.is_alive()
        assert left_result == {"value": 5}
        assert right_result == {"value": 104}
        with compute_lock:
            assert compute_entries == 1
    finally:
        release_shared.set()
        left_thread.join(timeout=2)
        right_thread.join(timeout=2)


def _burn_cpu_until(predicate, *, timeout=1.0):
    deadline = time.perf_counter() + timeout
    total = 0
    while not predicate() and time.perf_counter() < deadline:
        for i in range(10_000):
            total += (i * i) % 97
    return predicate(), total


def test_cpu_heavy_independent_computed_graphs_can_enter_concurrently():
    left_base = Signal(0)
    right_base = Signal(0)
    left_entered = threading.Event()
    right_entered = threading.Event()

    def left_compute():
        if left_base() == 1:
            left_entered.set()
            observed_right, total = _burn_cpu_until(right_entered.is_set)
            assert observed_right
            return total + left_base()
        return left_base()

    def right_compute():
        if right_base() == 1:
            right_entered.set()
            observed_left, total = _burn_cpu_until(left_entered.is_set)
            assert observed_left
            return total + right_base()
        return right_base()

    left = Computed(left_compute)
    right = Computed(right_compute)

    assert left() == 0
    assert right() == 0

    left_base.set(1)
    right_base.set(1)

    results = {}
    left_thread = threading.Thread(target=lambda: results.update(left=left()))
    right_thread = threading.Thread(target=lambda: results.update(right=right()))

    left_thread.start()
    right_thread.start()
    left_thread.join(timeout=2)
    right_thread.join(timeout=2)

    assert not left_thread.is_alive()
    assert not right_thread.is_alive()
    assert left_entered.is_set()
    assert right_entered.is_set()
    assert results["left"] > 0
    assert results["right"] > 0


def test_cpu_heavy_effect_does_not_block_unrelated_effect_flush_or_signal_write():
    left = Signal(0)
    right = Signal(0)
    left_effect_entered = threading.Event()
    right_set_completed = threading.Event()
    right_effect_ran = threading.Event()
    allow_left_effect_to_finish = threading.Event()
    right_effect_values = []
    right_effect_lock = threading.Lock()

    def left_effect():
        if left() == 1:
            left_effect_entered.set()
            observed_right_set, total = _burn_cpu_until(right_set_completed.is_set)
            assert observed_right_set
            observed_release, total = _burn_cpu_until(
                allow_left_effect_to_finish.is_set
            )
            assert observed_release
            assert total >= 0

    def right_effect():
        with right_effect_lock:
            right_effect_values.append(right())
        right_effect_ran.set()

    left_ref = Effect(left_effect)
    right_ref = Effect(right_effect)

    with right_effect_lock:
        right_effect_values.clear()
    right_effect_ran.clear()

    left_thread = threading.Thread(target=lambda: left.set(1))
    left_thread.start()
    assert left_effect_entered.wait(timeout=2)

    right_thread = threading.Thread(
        target=lambda: (right.set(1), right_set_completed.set())
    )
    right_thread.start()

    assert right_set_completed.wait(timeout=2)
    assert right() == 1
    assert right_effect_ran.wait(timeout=2)

    with right_effect_lock:
        assert right_effect_values == [1]

    allow_left_effect_to_finish.set()
    left_thread.join(timeout=2)
    right_thread.join(timeout=2)

    assert not left_thread.is_alive()
    assert not right_thread.is_alive()

    left_ref.dispose()
    right_ref.dispose()


def test_many_independent_diamond_graphs_update_correctly_in_parallel():
    graph_count = 8
    iterations = 50
    graphs = []

    for index in range(graph_count):
        source = Signal(index)
        left = Computed(lambda source=source: source() + 1)
        right = Computed(lambda source=source: source() * 2)
        combined = Computed(lambda left=left, right=right: left() + right())
        effect_values = []
        effect_lock = threading.Lock()

        def make_track(combined, effect_values, effect_lock):
            def track():
                with effect_lock:
                    effect_values.append(combined())

            return track

        effect = Effect(make_track(combined, effect_values, effect_lock))
        with effect_lock:
            effect_values.clear()
        graphs.append((source, combined, effect, effect_values, effect_lock))

    def update_graph(index: int):
        source, combined, _, _, _ = graphs[index]
        for value in range(iterations):
            next_value = index * 1_000 + value
            source.set(next_value)
            assert combined() == next_value + 1 + next_value * 2

    with ThreadPoolExecutor(max_workers=graph_count) as executor:
        futures = [executor.submit(update_graph, index) for index in range(graph_count)]
        for future in as_completed(futures):
            future.result()

    for index, (source, combined, effect, effect_values, effect_lock) in enumerate(
        graphs
    ):
        final_value = index * 1_000 + iterations - 1
        first_value = index * 1_000
        initial_value = index
        expected_runs = iterations - int(first_value == initial_value)
        assert source() == final_value
        assert combined() == final_value + 1 + final_value * 2
        with effect_lock:
            assert len(effect_values) == expected_runs
            assert effect_values[-1] == combined()
        effect.dispose()


def test_shared_source_fanout_graphs_remain_consistent_under_parallel_readers():
    source = Signal(0)
    multiplier = Signal(2)
    shared = Computed(lambda: source() * multiplier())
    left = Computed(lambda: shared() + source())
    right = Computed(lambda: shared() - source())
    total = Computed(lambda: left() + right())

    observed = []
    effect = Effect(lambda: observed.append(total()))
    observed.clear()

    stop = threading.Event()
    reader_errors = []
    reader_error_lock = threading.Lock()
    start = threading.Barrier(5)

    def reader():
        local_reads = 0
        start.wait()
        while not stop.is_set():
            # Exercise the fanout graph while the writer invalidates shared
            # dependencies. These reads are not expected to be one atomic
            # snapshot; they are here to force concurrent refresh paths.
            source()
            multiplier()
            shared()
            left()
            right()
            total()
            local_reads += 1
            time.sleep(0)
        return local_reads

    def guarded_reader():
        try:
            return reader()
        except BaseException as exc:
            with reader_error_lock:
                reader_errors.append(exc)
            raise

    reader_threads = [
        threading.Thread(target=guarded_reader, name=f"fanout-reader-{index}")
        for index in range(4)
    ]
    try:
        for thread in reader_threads:
            thread.start()

        start.wait()
        # Mutate both the shared source and a secondary dependency. This used
        # to expose stale downstream computeds when notifications coalesced.
        for value in range(1, 80):
            source.set(value)
            if value % 7 == 0:
                multiplier.set(2 + value % 5)
            if value % 3 == 0:
                time.sleep(0)

        stop.set()
        _join_all(reader_threads)

        assert reader_errors == []
        src = source()
        mult = multiplier()
        # After all writers/readers settle, every node must agree with the final
        # source state and the effect must have observed the final total.
        assert shared() == src * mult
        assert left() == shared() + src
        assert right() == shared() - src
        assert total() == left() + right()
        assert observed[-1] == total()
    finally:
        stop.set()
        effect.dispose()


def test_shared_source_fanout_effect_observes_final_public_value_after_updates():
    source = Signal(0)
    multiplier = Signal(2)
    shared = Computed(lambda: source() * multiplier())
    left = Computed(lambda: shared() + source())
    right = Computed(lambda: shared() - source())
    total = Computed(lambda: left() + right())
    observed = []
    effect = Effect(lambda: observed.append(total()))
    observed.clear()

    source.set(78)
    multiplier.set(4)
    observed.clear()

    # A plain read of an intermediate computed should not leave downstream
    # public values or effects stale after the next source update.
    assert shared() == 312

    source.set(79)

    assert source() == 79
    assert multiplier() == 4
    assert shared() == 316
    assert left() == 395
    assert right() == 237
    assert total() == 632
    assert observed[-1] == 632
    effect.dispose()


def test_thread_local_batches_do_not_coalesce_unrelated_thread_effects():
    signal_count = 4
    updates_per_thread = 20
    signals = [Signal(0) for _ in range(signal_count)]
    effect_values = [[] for _ in range(signal_count)]
    locks = [threading.Lock() for _ in range(signal_count)]
    effects = []

    for index, signal in enumerate(signals):
        def make_effect(index=index, signal=signal):
            def effect_fn():
                with locks[index]:
                    effect_values[index].append(signal())

            return effect_fn

        effects.append(Effect(make_effect()))

    for index in range(signal_count):
        with locks[index]:
            effect_values[index].clear()

    def worker(index: int):
        signal = signals[index]
        for value in range(1, updates_per_thread + 1):
            with batch():
                signal.set(value * 10)
                signal.set(value * 10 + 1)

    threads = [
        threading.Thread(target=worker, args=(index,), name=f"batch-worker-{index}")
        for index in range(signal_count)
    ]
    for thread in threads:
        thread.start()
    _join_all(threads)

    for index, effect in enumerate(effects):
        expected_values = [value * 10 + 1 for value in range(1, updates_per_thread + 1)]
        with locks[index]:
            assert effect_values[index] == expected_values
        effect.dispose()


def test_linked_signals_manual_and_source_updates_are_thread_safe():
    source = Signal(1)
    linked = LinkedSignal(lambda: source() * 10)
    display = Computed(lambda: linked() + source())
    observed = []
    observed_lock = threading.Lock()

    def track():
        with observed_lock:
            observed.append(display())

    effect = Effect(track)
    with observed_lock:
        observed.clear()

    def source_worker():
        for value in range(2, 42):
            source.set(value)

    def linked_worker():
        for value in range(100, 140):
            linked.set(value)

    threads = [
        threading.Thread(target=source_worker, name="linked-source-worker"),
        threading.Thread(target=linked_worker, name="linked-manual-worker"),
    ]
    for thread in threads:
        thread.start()
    _join_all(threads)

    final_source = source()
    final_display = display()
    assert final_display in {linked() + final_source, final_source * 10 + final_source}
    with observed_lock:
        assert observed
        assert observed[-1] == final_display
    effect.dispose()


def test_ultimate_complex_threaded_signal_graph_stays_consistent():
    state = Signal(_UltimateGraphState(0, base=2, quantity=3, tax=1, discount=0, option=5))
    bonus = Signal(0)
    manual_bias = Signal(0)
    audit_note = Signal("cold")
    independent = Signal(1)
    readonly_state = state.as_readonly()

    gross = ComputeSignal(lambda: readonly_state().base * readonly_state().quantity)

    @Computed
    def net() -> int:
        current = state()
        return gross() + current.tax - current.discount

    @Computed
    def fanout_left() -> int:
        return net() * 2 + bonus()

    @Computed
    def fanout_right() -> int:
        current = state()
        return net() // 2 - bonus() + current.option

    shared_total = Computed(lambda: fanout_left() + fanout_right())

    selected_total = LinkedSignal(
        source=lambda: (state().version, shared_total()),
        computation=lambda source_value, previous: (
            previous.value
            if previous is not None
            and previous.value % 11 == 0
            and source_value[0] % 5 != 0
            else source_value[1]
        ),
    )
    editable_total = LinkedSignal(lambda: shared_total() + manual_bias())
    independent_double = Computed(lambda: independent() * 2)

    @Computed
    def final_total() -> int:
        return gross() + selected_total() + editable_total() + independent_double()

    health_snapshot = Computed(
        lambda: {
            "version": state().version,
            "gross": gross(),
            "shared": shared_total(),
            "selected": selected_total(),
            "editable": editable_total(),
            "independent": independent_double(),
            "final": final_total(),
        }
    )

    observed = []
    observed_lock = threading.Lock()
    read_errors = []
    read_errors_lock = threading.Lock()
    start = threading.Barrier(6)
    stop_readers = threading.Event()

    def record_final():
        note = untracked(lambda: audit_note())
        snapshot = health_snapshot()
        with observed_lock:
            observed.append((snapshot["version"], snapshot["final"], note))

    effect = Effect(record_final)
    with observed_lock:
        observed.clear()

    assert final_total() == 52
    assert health_snapshot()["final"] == 52

    def guarded(worker):
        def run():
            try:
                start.wait(timeout=2)
                worker()
            except BaseException as exc:
                with read_errors_lock:
                    read_errors.append(exc)
                stop_readers.set()
                raise

        return run

    def state_writer():
        for version in range(1, 121):
            if stop_readers.is_set():
                return
            with batch():
                state.set(
                    _UltimateGraphState(
                        version=version,
                        base=2 + version % 17,
                        quantity=1 + version % 9,
                        tax=version % 13,
                        discount=version % 7,
                        option=5 + version % 11,
                    )
                )
                if version % 3 == 0:
                    bonus.set(version % 19)
                if version % 10 == 0:
                    audit_note.set(f"state:{version}")

    def linked_writer():
        for value in range(200, 320):
            if stop_readers.is_set():
                return
            with batch():
                selected_total.set(value)
                editable_total.set(value + manual_bias())
                if value % 4 == 0:
                    manual_bias.set(value % 23)

    def independent_writer():
        for value in range(1, 181):
            if stop_readers.is_set():
                return
            independent.set(value)

    def reader():
        while not stop_readers.is_set():
            snapshot = health_snapshot()
            assert isinstance(snapshot["version"], int)
            assert isinstance(snapshot["gross"], int)
            assert isinstance(snapshot["shared"], int)
            assert isinstance(snapshot["selected"], int)
            assert isinstance(snapshot["editable"], int)
            assert isinstance(snapshot["independent"], int)
            assert isinstance(snapshot["final"], int)

    threads = [
        threading.Thread(target=guarded(state_writer), name="ultimate-state-writer"),
        threading.Thread(target=guarded(linked_writer), name="ultimate-linked-writer"),
        threading.Thread(
            target=guarded(independent_writer), name="ultimate-independent-writer"
        ),
        threading.Thread(target=guarded(reader), name="ultimate-reader-0"),
        threading.Thread(target=guarded(reader), name="ultimate-reader-1"),
        threading.Thread(target=guarded(reader), name="ultimate-reader-2"),
    ]

    try:
        for thread in threads:
            thread.start()

        for thread in threads[:3]:
            thread.join(timeout=4)
        assert not [thread.name for thread in threads[:3] if thread.is_alive()]

        stop_readers.set()
        _join_all(threads[3:])

        with read_errors_lock:
            assert read_errors == []

        # Force a deterministic final transition after the concurrent phase. Both
        # linked signals should reset from their manual values to source-derived
        # values when this source update lands.
        with batch():
            state.set(
                _UltimateGraphState(
                    version=1_000,
                    base=13,
                    quantity=7,
                    tax=4,
                    discount=3,
                    option=9,
                )
            )
            bonus.set(6)
            manual_bias.set(8)
            independent.set(21)
            audit_note.set("settled")

        expected_gross = 13 * 7
        expected_net = expected_gross + 4 - 3
        expected_shared = (expected_net * 2 + 6) + (expected_net // 2 - 6 + 9)
        expected_editable = expected_shared + 8
        expected_final = expected_gross + expected_shared + expected_editable + 42

        assert gross() == expected_gross
        assert net() == expected_net
        assert fanout_left() == expected_net * 2 + 6
        assert fanout_right() == expected_net // 2 - 6 + 9
        assert shared_total() == expected_shared
        assert selected_total() == expected_shared
        assert editable_total() == expected_editable
        assert independent_double() == 42
        assert final_total() == expected_final
        assert health_snapshot() == {
            "version": 1_000,
            "gross": expected_gross,
            "shared": expected_shared,
            "selected": expected_shared,
            "editable": expected_editable,
            "independent": 42,
            "final": expected_final,
        }
        with observed_lock:
            assert observed
            assert observed[-1] == (1_000, expected_final, "settled")
    finally:
        stop_readers.set()
        for thread in threads:
            thread.join(timeout=2)
        effect.dispose()


def test_effect_dispose_during_concurrent_updates_stops_future_notifications():
    source = Signal(0)
    values = []
    values_lock = threading.Lock()
    stop_updates = threading.Event()

    def track():
        value = source()
        with values_lock:
            values.append(value)

    effect = Effect(track)
    with values_lock:
        values.clear()

    def updater():
        value = 1
        while not stop_updates.is_set():
            source.set(value)
            value += 1

    update_thread = threading.Thread(target=updater, name="dispose-updater")
    update_thread.start()

    deadline = time.perf_counter() + 2
    while time.perf_counter() < deadline:
        with values_lock:
            if len(values) >= 10:
                break
        time.sleep(0.001)

    effect.dispose()
    stop_updates.set()
    update_thread.join(timeout=2)
    assert not update_thread.is_alive()

    with values_lock:
        observed_at_dispose = len(values)

    for value in range(10_000, 10_010):
        source.set(value)

    with values_lock:
        assert len(values) == observed_at_dispose
