import asyncio
import contextvars
import traceback
import inspect
from typing import (
    Generic, TypeVar, Optional, Callable,
    Coroutine, Set, Protocol, Any, Union
)
from weakref import WeakSet

T = TypeVar("T")

class DependencyTracker(Protocol):
    def add_dependency(self, signal: 'Signal') -> None: ...

class Subscriber(Protocol):
    def notify(self) -> None: ...

_current_effect: contextvars.ContextVar[Optional[DependencyTracker]] = contextvars.ContextVar(
    "_current_effect", default=None
)

class Signal(Generic[T]):
    """Reactive signal container that tracks dependent effects and computed signals."""
    def __init__(self, value: T):
        self._value = value
        self._subscribers: WeakSet[Subscriber] = WeakSet()

    def get(self) -> T:
        if (tracker := _current_effect.get(None)) is not None:
            tracker.add_dependency(self)
        return self._value

    def set(self, new_value: T) -> None:
        if self._value == new_value:
            return
        self._value = new_value
        for subscriber in self._subscribers:
            subscriber.notify()

    def subscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.add(subscriber)

    def unsubscribe(self, subscriber: Subscriber) -> None:
        self._subscribers.discard(subscriber)

class ComputeSignal(Signal[T], DependencyTracker, Subscriber):
    """Computed signal that derives value from other signals with error handling."""
    def __init__(self, compute_fn: Callable[[], T], default: Optional[T] = None):
        self._compute_fn = compute_fn
        self._default = default
        self._dependencies: Set[Signal] = set()
        self._computing = False  # Track computation state
        super().__init__(default)
        self._value: T = default  # type: ignore
        self._compute()

    def _compute(self) -> None:
        if self._computing:
            raise RuntimeError("Circular dependency detected")
            
        self._computing = True
        try:
            old_deps = set(self._dependencies)
            self._dependencies.clear()
            
            token = _current_effect.set(self)
            try:
                new_value = self._compute_fn()
            except Exception as e:
                traceback.print_exc()
                new_value = getattr(self, '_value', self._default)
            finally:
                _current_effect.reset(token)

            if new_value != self._value:
                self._value = new_value
                for subscriber in self._subscribers:
                    subscriber.notify()

            # Update dependencies
            for signal in old_deps - self._dependencies:
                signal.unsubscribe(self)
            for signal in self._dependencies - old_deps:
                signal.subscribe(self)
                
        finally:
            self._computing = False

    def add_dependency(self, signal: Signal) -> None:
        self._dependencies.add(signal)

    def notify(self) -> None:
        self._compute()

    def get(self) -> T:
        return super().get()
    
    def set(self, new_value: T) -> None:
        raise AttributeError("Cannot manually set value of ComputeSignal - update dependencies instead")

class Effect(DependencyTracker, Subscriber):
    """Reactive effect that tracks signal dependencies.

    For asynchronous effects, notifications are debounced (only one scheduled run
    is active at a time). For synchronous effects, every notification increments an
    internal counter so that if multiple signals update while the effect is running,
    the effect function is executed once per update.
    """
    def __init__(self, func: Callable[[], Union[None, Coroutine[Any, Any, Any]]]):
        self._func = func  # May be synchronous or asynchronous.
        self._dependencies: Set[Signal] = set()
        self._disposed = False
        self._new_dependencies: Optional[Set[Signal]] = None
        # For async scheduling:
        self._scheduled = False
        # Determine whether the passed function is asynchronous.
        self._is_async = asyncio.iscoroutinefunction(func)
        # For synchronous effects, count pending notifications.
        self._executing_sync = False
        self._pending_sync = 0

    def add_dependency(self, signal: Signal) -> None:
        if self._disposed or self._new_dependencies is None:
            return
        self._new_dependencies.add(signal)

    def notify(self) -> None:
        if self._is_async:
            self.schedule()
        else:
            self._pending_sync += 1
            if not self._executing_sync:
                self._execute_sync()

    def schedule(self) -> None:
        if self._disposed:
            return
        if self._is_async:
            if self._scheduled:
                return
            self._scheduled = True
            asyncio.create_task(self._execute())
        else:
            self._pending_sync += 1
            if not self._executing_sync:
                self._execute_sync()

    async def _execute(self) -> None:
        self._scheduled = False
        if self._disposed:
            return

        self._new_dependencies = set()
        token = _current_effect.set(self)
        try:
            result = self._func()
            if inspect.isawaitable(result):
                await result
        except Exception as e:
            traceback.print_exc()
        finally:
            _current_effect.reset(token)

        if self._disposed:
            return

        new_deps = self._new_dependencies or set()
        self._new_dependencies = None

        # Update subscriptions: remove old ones and add new ones.
        for signal in self._dependencies - new_deps:
            signal.unsubscribe(self)
        for signal in new_deps - self._dependencies:
            signal.subscribe(self)
        self._dependencies = new_deps

    def _execute_sync(self) -> None:
        if self._disposed:
            return
        self._executing_sync = True
        try:
            # Process one notification per pending count.
            while self._pending_sync > 0:
                self._pending_sync -= 1
                self._new_dependencies = set()
                token = _current_effect.set(self)
                try:
                    self._func()
                except Exception:
                    traceback.print_exc()
                finally:
                    _current_effect.reset(token)
                if self._disposed:
                    return
                new_deps = self._new_dependencies or set()
                self._new_dependencies = None
                # Update subscriptions.
                for signal in self._dependencies - new_deps:
                    signal.unsubscribe(self)
                for signal in new_deps - self._dependencies:
                    signal.subscribe(self)
                self._dependencies = new_deps
        finally:
            self._executing_sync = False

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        for signal in self._dependencies:
            signal.unsubscribe(self)
        self._dependencies.clear()