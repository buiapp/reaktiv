"""reaktiv.subtle: framework-author primitives that never force evaluation."""

import gc
import weakref

import pytest

from reaktiv import ReactiveModel, batch, computed, effect, linked, signal, untracked
from reaktiv import graph
from reaktiv.subtle import Watcher, current_consumer, signal_version


def targets(node):
    return graph.snapshot_targets(node)


# --------------------------------------------------------------------------
# Watcher
# --------------------------------------------------------------------------


def test_watcher_notifies_without_evaluating_and_reports_pending():
    calls, notified = [], []
    source = signal(1)
    derived = computed(lambda: calls.append(source()) or source() * 2)
    watcher = Watcher(lambda: notified.append(True))

    watcher.watch(derived)
    assert calls == []  # watching never evaluates
    assert watcher.get_pending() == [derived]  # never evaluated yet
    assert derived() == 2
    assert watcher.get_pending() == []

    source.set(2)
    assert notified == [True]
    assert calls == [1]  # notify happened before any recomputation
    assert watcher.get_pending() == [derived]
    assert derived() == 4
    assert watcher.get_pending() == []


def test_watcher_notifies_once_until_rearmed():
    source = signal(1)
    derived = computed(lambda: source())
    notified = []
    watcher = Watcher(lambda: notified.append(True))
    watcher.watch(derived)
    derived()

    source.set(2)
    source.set(3)
    assert len(notified) == 1
    derived()
    watcher.watch()  # re-arm
    source.set(4)
    assert len(notified) == 2


def test_watcher_notifies_synchronously_inside_batch():
    source = signal(1)
    notified = []
    watcher = Watcher(lambda: notified.append(True))
    watcher.watch(source)
    with batch():
        source.set(2)
        assert notified == [True]


def test_watcher_on_plain_signal_notifies_but_is_never_pending():
    source = signal(1)
    notified = []
    watcher = Watcher(lambda: notified.append(True))
    watcher.watch(source)
    source.set(2)
    assert notified == [True]
    assert watcher.get_pending() == []


def test_reading_or_writing_inside_notify_is_rejected_without_breaking_propagation(capsys):
    source, other = signal(1), signal(0)
    seen = []

    def notify():
        if source.get() > 0:  # forbidden read
            seen.append("read")

    reader = Watcher(notify)
    reader.watch(source)
    writer = Watcher(lambda: other.set(1))  # forbidden write
    writer.watch(source)
    keep = effect(lambda: seen.append(source()))

    source.set(2)
    errors = capsys.readouterr().err
    assert "Cannot read signals inside a Watcher notify callback" in errors
    assert "Cannot set signals inside a Watcher notify callback" in errors
    assert other() == 0
    assert seen == [1, 2]  # the effect still ran
    assert current_consumer() is None
    keep.dispose()


def test_untracked_cannot_bypass_the_notify_guard(capsys):
    source, other = signal(1), signal(0)
    read_values = []
    reader = Watcher(lambda: read_values.append(untracked(source)))
    reader.watch(source)
    writer = Watcher(lambda: untracked(lambda: other.set(99)))
    writer.watch(source)

    source.set(2)
    errors = capsys.readouterr().err
    assert "Cannot read signals inside a Watcher notify callback" in errors
    assert "Cannot set signals inside a Watcher notify callback" in errors
    assert read_values == []
    assert other() == 0
    assert source() == 2  # the guard is lifted again after notify


def test_rejected_reads_and_writes_in_notify_evaluate_nothing(capsys):
    runs = []
    source = signal(1)
    derived = computed(lambda: runs.append(source()) or source())
    choice = linked(lambda: runs.append(("linked", source())) or source())
    watcher = Watcher(lambda: (derived(), choice.set(5)))
    other = Watcher(lambda: choice.set(5))
    watcher.watch(source)
    other.watch(source)

    source.set(2)
    errors = capsys.readouterr().err
    assert errors.count("RuntimeError: Cannot read signals inside a Watcher") == 1
    assert errors.count("RuntimeError: Cannot set signals inside a Watcher") == 1
    assert runs == []  # neither the computed nor the linked signal ran


def test_rejected_linked_update_never_calls_the_updater(capsys):
    calls = []
    source = signal(1)
    choice = linked(lambda: source())
    choice()

    def updater(where):
        return lambda value: calls.append((where, value)) or value + 1

    watcher = Watcher(lambda: choice.update(updater("notify")))
    watcher.watch(source)
    source.set(2)
    assert "RuntimeError: Cannot set signals inside a Watcher" in capsys.readouterr().err

    writer = computed(lambda: choice.update(updater("computed")))
    with pytest.raises(RuntimeError, match="Side effect detected"):
        writer()
    assert calls == []


def test_linked_set_inside_a_computed_is_rejected():
    source = signal(1)
    choice = linked(lambda: source())
    writer = computed(lambda: choice.set(source()))
    with pytest.raises(RuntimeError, match="Side effect detected"):
        writer()


def test_work_scheduled_from_notify_can_read():
    import asyncio

    async def main():
        source = signal(1)
        derived = computed(lambda: source() * 2)
        seen = []
        loop = asyncio.get_running_loop()

        def flush():
            watcher.watch()
            for node in watcher.get_pending():
                seen.append(node())

        # call_soon and create_task copy the context of the notify call
        watcher = Watcher(lambda: loop.call_soon(flush))
        watcher.watch(derived)
        flush()
        source.set(2)
        await asyncio.sleep(0)
        assert seen == [2, 4]

    asyncio.run(main())


def test_unwatch_stops_notifications_and_releases_lazy_subscriptions():
    source = signal(1)
    derived = computed(lambda: source())
    notified = []
    watcher = Watcher(lambda: notified.append(True))
    watcher.watch(derived)
    derived()
    assert targets(source) == [derived]

    watcher.unwatch(derived)
    watcher.unwatch(derived)  # ignored when not watched
    assert targets(derived) == []
    assert targets(source) == []
    source.set(2)
    assert notified == []
    assert watcher.get_pending() == []


def test_watcher_returns_the_handles_it_was_given():
    source = signal(1)
    derived = computed(lambda: source())
    readonly = derived.as_readonly()
    watcher = Watcher(lambda: None)
    watcher.watch(readonly)
    assert watcher.get_pending() == [readonly]
    with pytest.raises(TypeError):
        watcher.watch(object())  # type: ignore[arg-type]


def test_watcher_is_weakly_retained_by_sources():
    source = signal(1)
    notified = []
    watcher = Watcher(lambda: notified.append(True))
    watcher.watch(source)
    reference = weakref.ref(watcher)
    del watcher
    gc.collect()
    assert reference() is None
    assert targets(source) == []
    source.set(2)
    assert notified == []


def test_custom_scheduler_built_on_watcher_defers_and_coalesces_work():
    """A framework-style deferred effect: evaluate and commit on its own tick."""
    queue = []
    first, second = signal(1), signal(10)
    view = computed(lambda: first() + second())
    committed = []
    log = signal(0)  # side effects write signals outside the computed

    watcher = Watcher(lambda: queue.append("tick"))

    def flush():
        queue.clear()
        watcher.watch()
        for node in watcher.get_pending():
            committed.append(node())
            log.update(lambda n: n + 1)

    watcher.watch(view)
    flush()
    first.set(2)
    second.set(20)
    assert queue == ["tick"]  # coalesced until the scheduler runs
    assert committed == [11]
    flush()
    assert committed == [11, 22]
    assert log() == 2


def test_documented_flush_schedules_again_when_committing_changes_a_dependency():
    queue, rendered = [], []
    count = signal(0)
    view = computed(lambda: count())
    watcher = Watcher(lambda: queue.append(flush))

    def flush():
        watcher.watch()  # re-arm before committing
        for node in watcher.get_pending():
            value = node()
            rendered.append(value)
            if value == 1:
                count.set(2)  # committing changes a watched dependency

    watcher.watch(view)
    flush()
    count.set(1)
    while queue:
        queue.pop(0)()
    assert rendered == [0, 1, 2]
    assert rendered[-1] == count()
    assert watcher.get_pending() == []


def test_watcher_is_consistent_under_threaded_writes():
    from concurrent.futures import ThreadPoolExecutor

    from reaktiv import is_thread_safety_enabled, set_thread_safety

    previous = is_thread_safety_enabled()
    set_thread_safety(True)
    try:
        source = signal(0)
        derived = computed(lambda: source() * 2)
        watcher = Watcher(lambda: None)
        watcher.watch(derived)

        def write():
            for value in range(1, 101):
                source.set(value)

        def observe():
            for _ in range(200):
                watcher.get_pending()
                assert signal_version(source) >= 0
                watcher.watch()

        with ThreadPoolExecutor(max_workers=3) as workers:
            futures = [workers.submit(write), workers.submit(observe), workers.submit(observe)]
            for future in futures:
                future.result(timeout=3)
        assert derived() == 200
    finally:
        set_thread_safety(previous)


# --------------------------------------------------------------------------
# current_consumer / signal_version
# --------------------------------------------------------------------------


def test_current_consumer_reports_tracking_context_without_changing_it():
    observed, incidental = signal(1), signal(2)
    consumers = []

    def calculate():
        consumers.append(current_consumer())
        assert untracked(current_consumer) is None
        signal_version(incidental)
        return observed()

    result = computed(calculate)
    assert result() == 1
    assert consumers == [result]
    incidental.set(3)
    assert result() == 1  # signal_version did not create a dependency
    assert consumers == [result]
    assert current_consumer() is None


def test_signal_version_is_passive_and_respects_equality():
    calls = []
    source = signal(1, equal=lambda old, new: old == new)
    readonly = source.as_readonly()
    source.set(1)
    assert signal_version(readonly) == 0
    source.set(2)
    assert signal_version(readonly) == 1

    derived = linked(lambda: calls.append(source()) or source() * 2)
    assert signal_version(derived) == 0
    assert calls == []
    assert derived() == 4
    source.set(3)
    assert signal_version(derived) == 1  # stale computed keeps its revision
    assert calls == [2]
    with pytest.raises(TypeError):
        signal_version(object())  # type: ignore[arg-type]


def test_failed_computation_publishes_a_revision():
    source = signal(0)
    result = computed(lambda: 10 // source())
    with pytest.raises(ZeroDivisionError):
        result()
    assert signal_version(result) == 1
    source.set(2)
    assert result() == 5
    assert signal_version(result) == 2


# --------------------------------------------------------------------------
# ReactiveModel.own
# --------------------------------------------------------------------------


def test_model_owns_extensions_in_reverse_order_and_disposes_once():
    order = []

    class Disposable:
        def dispose(self):
            order.append("dispose")

    class Destroyable:
        def destroy(self):
            order.append("destroy")

    model = ReactiveModel()
    first, second = Disposable(), Destroyable()
    assert model.own(first) is first
    model.own(first)
    model.own(second)
    source, values = signal(0), []
    model.own(effect(lambda: values.append(source())))
    model.dispose()
    source.set(1)
    assert values == [0]
    assert order == ["destroy", "dispose"]
    model.dispose()
    assert order == ["destroy", "dispose"]


def test_model_own_rejects_objects_without_cleanup():
    model = ReactiveModel()
    with pytest.raises(TypeError, match=r"dispose\(\) or destroy\(\)"):
        model.own(object())  # type: ignore[type-var]


def test_model_cleanup_distinguishes_equal_but_different_resources():
    disposed = []

    class Connection:
        def __init__(self, name):
            self.name = name

        def __eq__(self, other):
            return isinstance(other, Connection)

        def dispose(self):
            disposed.append(self.name)

    model = ReactiveModel()
    first, second = Connection("first"), Connection("second")
    model.own(first)
    model.own(second)
    model.own(first)
    model.dispose()
    assert disposed == ["second", "first"]


def test_core_import_has_no_optional_dependency():
    import subprocess
    import sys

    subprocess.run(
        [
            sys.executable,
            "-c",
            "import reaktiv, sys; assert not any(name.startswith(('fastapi', 'numpy')) for name in sys.modules)",
        ],
        check=True,
    )


def test_watcher_dispose_releases_everything_and_ignores_rearming():
    source = signal(1)
    derived = computed(lambda: source())
    notified = []
    watcher = Watcher(lambda: notified.append(True))
    watcher.watch(source, derived)
    derived()

    model = ReactiveModel()
    model.own(watcher)  # watchers are disposable
    model.dispose()
    assert targets(source) == []
    assert targets(derived) == []
    watcher.watch(source)  # e.g. a flush scheduled before disposal
    source.set(2)
    assert notified == []
    assert watcher.get_pending() == []
