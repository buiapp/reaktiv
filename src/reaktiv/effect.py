"""Effect implementation with sync/async support and batched scheduling."""

from __future__ import annotations

import asyncio
import inspect
import threading
import traceback
import weakref
from typing import Any, Callable, Coroutine, List, Optional, Union, cast, overload

from ._descriptor import PerInstanceDescriptor, is_instance_method
from ._debug import debug_log
from . import graph
from . import scheduler as _sched

EffectFn = Callable[..., object]
CleanupRegistrar = Callable[[Callable[[], None]], None]


class EffectDescriptor(PerInstanceDescriptor["Effect"]):
    """Descriptor that creates one Effect per owner instance."""

    initialize_eagerly = True

    def __init__(self, func: Callable[..., object]) -> None:
        super().__init__()
        self._func = func

    def _create(self, instance: object) -> "Effect":
        parameters = tuple(inspect.signature(self._func).parameters.values())
        accepts_cleanup = len(parameters) >= 2
        try:
            instance_ref = weakref.ref(instance)

            def owner() -> object:
                current = instance_ref()
                if current is None:
                    raise ReferenceError("Reactive owner has been garbage collected")
                return current

        except TypeError:

            def owner() -> object:
                return instance

        if asyncio.iscoroutinefunction(self._func):
            if accepts_cleanup:

                async def async_with_cleanup(on_cleanup):
                    return await cast(Callable[..., Any], self._func)(
                        owner(), on_cleanup
                    )

                return _create_effect_instance(async_with_cleanup)

            async def async_without_cleanup():
                return await cast(Callable[..., Any], self._func)(owner())

            return _create_effect_instance(async_without_cleanup)

        if accepts_cleanup:

            def sync_with_cleanup(on_cleanup):
                return self._func(owner(), on_cleanup)

            return _create_effect_instance(sync_with_cleanup)

        def sync_without_cleanup():
            return self._func(owner())

        return _create_effect_instance(sync_without_cleanup)


class Effect:
    """A reactive effect that automatically tracks signal dependencies and re-runs when they change.
    
    Effect creates a side effect function that runs immediately and re-runs whenever
    any signal it depends on changes. For synchronous effects outside a batch, every
    successful dependency update that changes a value triggers one effect execution.
    Updates inside ``batch()`` are intentionally coalesced and run once after the
    outermost batch completes. It supports optional cleanup logic.
    
    Lifecycle and Memory Management:
        Effects are weakly referenced to prevent memory leaks. This means:
        
        - **Without a stored reference**: The Effect will be garbage collected immediately
          and stop responding to signal changes. Cleanup functions will run
          automatically during garbage collection.
          
        - **With a stored reference**: The Effect persists and continues reacting to changes.
          Call dispose() explicitly when done to ensure immediate cleanup.
          
        Best practices:
        - Store Effect references: ``self.effect = Effect(...)``
        - Call dispose() explicitly: ``self.effect.dispose()``
        - Cleanup functions run automatically on GC, but prefer explicit dispose()
    
    Cleanup Functions:
        Effects can register cleanup logic to run when:
        1. The effect reruns (cleanup from previous run)
        2. dispose() is called explicitly
        3. The Effect is garbage collected (automatic)
        
        Register cleanup by returning a function or using the on_cleanup parameter.
    
    Note:
        Async functions are supported but still experimental and may not behave as expected
        in all scenarios.
    
    Args:
        func: The effect function to run. Can be sync or async (experimental). May optionally 
            accept an `on_cleanup` callback parameter for registering cleanup logic, or return 
            a cleanup function.
            
    Examples:
        Basic effect:
        ```python
        from reaktiv import Signal, Effect
        
        counter = Signal(0)
        
        # Effect runs immediately and on every change
        # Must retain reference to prevent garbage collection
        effect = Effect(lambda: print(f"Counter: {counter()}"))
        # Prints: "Counter: 0"
        
        counter.set(1)
        # Prints: "Counter: 1"

        counter.set(2)
        # Prints: "Counter: 2"
        ```
        
        Effect with cleanup:
        ```python
        from reaktiv import Signal, Effect
        
        user_id = Signal(1)
        
        def subscribe_to_user():
            uid = user_id()
            print(f"Subscribing to user {uid}")
            
            # Return cleanup function
            def cleanup():
                print(f"Unsubscribing from user {uid}")
            return cleanup
        
        effect = Effect(subscribe_to_user)
        # Prints: "Subscribing to user 1"
        
        user_id.set(2)
        # Prints: "Unsubscribing from user 1"
        # Prints: "Subscribing to user 2"
        
        effect.dispose()
        # Prints: "Unsubscribing from user 2"
        ```
        
        Effect with on_cleanup parameter:
        ```python
        from reaktiv import Signal, Effect
        
        enabled = Signal(True)
        
        def my_effect(on_cleanup):
            if enabled():
                print("Starting...")
                on_cleanup(lambda: print("Stopping..."))
        
        effect = Effect(my_effect)
        # Prints: "Starting..."
        
        enabled.set(False)
        # Prints: "Stopping..."
        ```
        
        Manual disposal:
        ```python
        from reaktiv import Signal, Effect
        
        count = Signal(0)
        
        effect = Effect(lambda: print(count()))
        # Prints: 0
        
        count.set(1)
        # Prints: 1
        
        effect.dispose()
        
        count.set(2)
        # No print - effect is disposed
        ```
    """

    __slots__ = (
        "_fn",
        "_cleanup",
        "_sources",
        "_source_map",
        "_next_batched_effect",
        "_flags",
        "_is_async",
        "_accepts_cleanup",
        "_async_task",
        "_executing",
        "_graph_lock",
        "__weakref__",  # Allow weak references for garbage collection
    )

    @overload
    def __new__(cls, func: Callable[[], object], /) -> "Effect": ...

    @overload
    def __new__(cls, func: Callable[[CleanupRegistrar], object], /) -> "Effect": ...

    @overload
    def __new__(cls, func: Callable[[Any], object], /) -> EffectDescriptor: ...

    @overload
    def __new__(
        cls, func: Callable[[Any, CleanupRegistrar], object], /
    ) -> EffectDescriptor: ...

    def __new__(cls, func: EffectFn) -> Union["Effect", EffectDescriptor]:
        if is_instance_method(func):
            return EffectDescriptor(func)
        return super().__new__(cls)

    def __init__(self, func: EffectFn):
        self._fn = func
        self._cleanup: Optional[Callable[[], None]] = None
        self._sources: Optional[graph.Edge] = None
        self._next_batched_effect: Optional[Effect] = None
        self._source_map: dict[int, graph.Edge] = {}
        self._flags: int = graph.TRACKING
        self._is_async = asyncio.iscoroutinefunction(func)
        self._accepts_cleanup = len(inspect.signature(func).parameters) >= 1
        self._async_task: Optional[asyncio.Task] = None
        self._executing: bool = False
        self._graph_lock: Optional[threading.RLock] = threading.RLock()
        debug_log(
            lambda: f"Effect created with func: {func}, is_async: {self._is_async}"
        )

        # Schedule initial run
        self._notify()
        if _sched.current_batch_depth() == 0:
            _sched.flush_now()

    # --------------------------- Scheduling API ----------------------------
    def _notify(self) -> None:
        if not (self._flags & graph.NOTIFIED):
            self._flags |= graph.NOTIFIED
            _sched.enqueue_effect(self)

    def _lock(self) -> threading.RLock:
        if self._graph_lock is None:
            raise RuntimeError("Effect graph lock is not initialized")
        return self._graph_lock

    def _needs_run(self) -> bool:
        with self._lock():
            if self._flags & graph.DISPOSED:
                return False
            if self._executing:
                return False
            # Always run on first execution (no sources yet)
            if self._sources is None:
                return True
            # Check if any dependencies have actually changed (Preact Signals style)
            return graph.needs_to_recompute(self)

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
        with self._lock():
            if self._flags & graph.DISPOSED:
                return
            if self._fn is None:
                return

            if self._executing:
                return

            if self._is_async:
                self._executing = True
                self._async_task = _sched.create_task(self._run_effect_async())
                return

            self._executing = True
            finish = self._start()
            try:
                fn = self._fn

                pending_cleanups: List[Callable[[], None]] = []

                def on_cleanup(fn_cleanup: Callable[[], None]) -> None:
                    pending_cleanups.append(fn_cleanup)

                try:
                    result = fn(on_cleanup) if self._accepts_cleanup else fn()
                    if callable(result):
                        pending_cleanups.append(cast(Callable[[], None], result))
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
                try:
                    finish()
                finally:
                    self._executing = False

    # --------------------------- Async execution ----------------------------
    async def _run_effect_async(self) -> None:
        try:
            finish = self._start()
            pending_cleanups: List[Callable[[], None]] = []

            def on_cleanup(fn_cleanup: Callable[[], None]) -> None:
                pending_cleanups.append(fn_cleanup)

            try:
                if self._accepts_cleanup:
                    await cast(
                        Callable[
                            [Callable[[Callable[[], None]], None]],
                            Coroutine[Any, Any, None],
                        ],
                        self._fn,
                    )(on_cleanup)
                else:
                    await cast(Callable[[], Coroutine[Any, Any, None]], self._fn)()
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
        with graph.consumer_lock(self):
            node = self._sources
            while node is not None:
                prev = node.prev_source
                node.source._unsubscribe_edge(node)
                node = prev
            self._sources = None
            self._source_map.clear()
        # run cleanup
        self._run_cleanup()
        # cancel async task
        if self._async_task is not None and not self._async_task.done():
            self._async_task.cancel()

    def dispose(self) -> None:
        """Stop the effect and prevent it from running again.
        
        This method:
        - Marks the effect as disposed
        - Unsubscribes from all signal dependencies
        - Runs any pending cleanup functions
        - Cancels any in-progress async tasks
        
        After calling dispose(), the effect will no longer react to signal changes.
        
        Examples:
            ```python
            from reaktiv import Signal, Effect
            
            counter = Signal(0)
            
            effect = Effect(lambda: print(f"Count: {counter()}"))
            # Prints: "Count: 0"
            
            counter.set(1)
            # Prints: "Count: 1"
            
            effect.dispose()
            
            counter.set(2)
            # No output - effect is disposed
            ```
        """
        with self._lock():
            self._flags |= graph.DISPOSED
            if not (self._flags & graph.RUNNING):
                self._dispose_now()

    def __del__(self) -> None:
        """Run cleanup function when Effect is garbage collected.
        
        This ensures that cleanup functions (e.g., closing connections, canceling
        subscriptions) are executed even if dispose() is not called explicitly.
        
        Note: This is called automatically by Python's garbage collector when the
        Effect has no more references. For deterministic cleanup, prefer calling
        dispose() explicitly.
        """
        self._run_cleanup()


def _create_effect_instance(func: EffectFn) -> Effect:
    effect = Effect(func)
    if isinstance(effect, EffectDescriptor):
        raise TypeError("Expected an Effect instance, got an Effect descriptor")
    return effect


class _EffectFactory:
    """Lowercase decorator-friendly Effect factory."""

    @overload
    def __call__(self, func: Callable[[], object], /) -> Effect: ...

    @overload
    def __call__(self, func: Callable[[Any], object], /) -> EffectDescriptor: ...

    @overload
    def __call__(
        self, func: Callable[[Any, CleanupRegistrar], object], /
    ) -> EffectDescriptor: ...

    def __call__(self, func: EffectFn, /) -> Union[Effect, EffectDescriptor]:
        return Effect(func)


effect = _EffectFactory()
