import asyncio
import contextvars
import traceback
from typing import (
    Generic, TypeVar, Optional, Callable, 
    Coroutine, Set, Protocol, Any
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

class Effect(DependencyTracker, Subscriber):
    """Reactive effect that tracks signal dependencies."""
    def __init__(self, coroutine: Callable[[], Coroutine[None, None, None]]):
        self._coroutine = coroutine
        self._dependencies: Set[Signal] = set()
        self._scheduled = False
        self._disposed = False
        self._new_dependencies: Optional[Set[Signal]] = None

    def add_dependency(self, signal: Signal) -> None:
        if self._disposed or self._new_dependencies is None:
            return
        self._new_dependencies.add(signal)

    def notify(self) -> None:
        self.schedule()

    def schedule(self) -> None:
        if self._disposed or self._scheduled:
            return
        self._scheduled = True
        asyncio.create_task(self._execute())

    async def _execute(self) -> None:
        self._scheduled = False
        if self._disposed:
            return

        self._new_dependencies = set()
        token = _current_effect.set(self)
        try:
            await self._coroutine()
        except Exception as e:
            traceback.print_exc()
        finally:
            _current_effect.reset(token)

        if self._disposed:
            return

        new_deps = self._new_dependencies or set()
        self._new_dependencies = None

        # Update subscriptions
        for signal in self._dependencies - new_deps:
            signal.unsubscribe(self)
        for signal in new_deps - self._dependencies:
            signal.subscribe(self)

        self._dependencies = new_deps

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        for signal in self._dependencies:
            signal.unsubscribe(self)
        self._dependencies.clear()