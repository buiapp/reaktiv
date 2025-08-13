"""Effect implementation with sync/async support and batched scheduling."""

from __future__ import annotations

import asyncio
import inspect
import traceback
from typing import Callable, Coroutine, List, Optional, Union, cast

from ._debug import debug_log
from . import graph
from . import scheduler as _sched

EffectFn = Union[
    Callable[..., Optional[Callable[[], None]]],
    Callable[..., Coroutine[None, None, None]],
]


class Effect:
    """Reactive effect that tracks signal dependencies."""

    __slots__ = (
        "_fn",
        "_cleanup",
        "_sources",
        "_next_batched_effect",
        "_flags",
        "_is_async",
        "_async_task",
        "_executing",
    )

    def __init__(self, func: EffectFn):
        self._fn = func
        self._cleanup: Optional[Callable[[], None]] = None
        self._sources: Optional[graph.Edge] = None
        self._next_batched_effect: Optional[Effect] = None
        self._flags: int = graph.TRACKING
        self._is_async = asyncio.iscoroutinefunction(func)
        self._async_task: Optional[asyncio.Task] = None
        self._executing: bool = False
        debug_log(f"Effect created with func: {func}, is_async: {self._is_async}")

        # Schedule initial run
        self._notify()
        if graph.batch_depth == 0:
            _sched.flush_now()

    # --------------------------- Scheduling API ----------------------------
    def _notify(self) -> None:
        if not (self._flags & graph.NOTIFIED):
            self._flags |= graph.NOTIFIED
            _sched.enqueue_effect(self)

    def _needs_run(self) -> bool:
        if self._flags & graph.DISPOSED:
            return False
        if self._is_async and self._executing:
            return False
        return True

    # --------------------------- Execution helpers ----------------------------
    def _start(self) -> Callable[[], None]:
        if self._flags & graph.RUNNING:
            raise RuntimeError("Cycle detected in effects")
        self._flags |= graph.RUNNING
        self._flags &= ~graph.DISPOSED
        self._run_cleanup()
        graph.prepare_sources(self)
        graph.batch_iteration = 0

        _sched.start_batch()
        prev = graph.set_active_consumer(self)

        def _finish():
            self._end(prev)

        return _finish

    def _end(self, prev_consumer) -> None:
        if graph.active_consumer.get() is not self:
            raise RuntimeError("Out-of-order effect end")
        graph.cleanup_sources(self)
        graph.set_active_consumer(prev_consumer)
        self._flags &= ~graph.RUNNING
        if self._flags & graph.DISPOSED:
            self._dispose_now()
        _sched.end_batch()

    def _run_cleanup(self) -> None:
        if self._cleanup is not None:
            debug_log("Running effect cleanup")
            try:
                self._cleanup()
            except Exception:
                traceback.print_exc()
            finally:
                self._cleanup = None

    # --------------------------- Sync execution ----------------------------
    def _run_callback(self) -> None:
        if self._flags & graph.DISPOSED:
            return
        if self._fn is None:
            return

        if self._is_async:
            if self._executing:
                return
            self._executing = True
            self._async_task = _sched.create_task(self._run_effect_async())
            return

        finish = self._start()
        try:
            fn = cast(Callable[..., object], self._fn)
            sig = inspect.signature(fn)
            pass_on_cleanup = len(sig.parameters) >= 1

            pending_cleanups: List[Callable[[], None]] = []

            def on_cleanup(fn_cleanup: Callable[[], None]) -> None:
                pending_cleanups.append(fn_cleanup)

            try:
                result = fn(on_cleanup) if pass_on_cleanup else fn()
                if callable(result):
                    pending_cleanups.append(result)  # type: ignore[arg-type]
            except Exception:
                traceback.print_exc()
            finally:
                # adopt latest cleanup (run all pending once, then store composite)
                def _composite():
                    for c in pending_cleanups:
                        try:
                            c()
                        except Exception:
                            traceback.print_exc()

                self._cleanup = _composite if pending_cleanups else None
        finally:
            finish()

    # --------------------------- Async execution ----------------------------
    async def _run_effect_async(self) -> None:
        try:
            finish = self._start()
            fn = cast(Callable[..., object], self._fn)
            sig = inspect.signature(fn)
            pass_on_cleanup = len(sig.parameters) >= 1
            pending_cleanups: List[Callable[[], None]] = []

            def on_cleanup(fn_cleanup: Callable[[], None]) -> None:
                pending_cleanups.append(fn_cleanup)

            try:
                if pass_on_cleanup:
                    await cast(
                        Callable[
                            [Callable[[Callable[[], None]], None]],
                            Coroutine[None, None, None],
                        ],
                        self._fn,
                    )(on_cleanup)
                else:
                    await cast(Callable[[], Coroutine[None, None, None]], self._fn)()
            except asyncio.CancelledError:
                # run any collected cleanups even on cancel
                for c in pending_cleanups:
                    try:
                        c()
                    except Exception:
                        traceback.print_exc()
                raise
            except Exception:
                traceback.print_exc()
            finally:

                def _composite():
                    for c in pending_cleanups:
                        try:
                            c()
                        except Exception:
                            traceback.print_exc()

                self._cleanup = _composite if pending_cleanups else None
                finish()
        finally:
            self._executing = False
            if self._async_task is not None and self._async_task.done():
                self._async_task = None

    # --------------------------- Disposal ----------------------------
    def _dispose_now(self) -> None:
        # unsubscribe from sources
        node = self._sources
        while node is not None:
            node.source._unsubscribe_edge(node)
            node = node.next_source
        self._sources = None
        # run cleanup
        self._run_cleanup()
        # cancel async task
        if self._async_task is not None and not self._async_task.done():
            self._async_task.cancel()

    def dispose(self) -> None:
        self._flags |= graph.DISPOSED
        if not (self._flags & graph.RUNNING):
            self._dispose_now()
