import asyncio
import contextvars
import traceback
from typing import Generic, TypeVar, Optional, Callable, Coroutine, Set
from weakref import WeakSet

T = TypeVar("T")

_current_effect: contextvars.ContextVar[Optional["Effect"]] = contextvars.ContextVar(
    "_current_effect", default=None
)

class Signal(Generic[T]):
    """Reactive signal container that tracks dependent effects."""

    def __init__(self, value: T) -> None:
        self._value = value
        self._subscribers: WeakSet["Effect"] = WeakSet()

    def get(self) -> T:
        if (effect := _current_effect.get(None)) is not None:
            effect.add_dependency(self)
        return self._value

    def set(self, new_value: T) -> None:
        if self._value == new_value:
            return
        self._value = new_value
        for effect in self._subscribers:
            effect.schedule()

    def subscribe(self, effect: "Effect") -> None:
        self._subscribers.add(effect)

    def unsubscribe(self, effect: "Effect") -> None:
        self._subscribers.discard(effect)

class Effect:
    """Reactive effect that automatically tracks and responds to signal dependencies."""

    def __init__(self, coroutine: Callable[[], Coroutine[None, None, None]]) -> None:
        self._coroutine = coroutine
        self._dependencies: Set[Signal] = set()
        self._scheduled: bool = False
        self._disposed: bool = False
        self._new_dependencies: Optional[Set[Signal]] = None

    def add_dependency(self, signal: Signal) -> None:
        if self._disposed or self._new_dependencies is None:
            return
        self._new_dependencies.add(signal)

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

        new_deps = self._new_dependencies
        self._new_dependencies = None

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