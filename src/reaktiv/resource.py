"""Resource - Async reactivity with resources.

A Resource gives you a way to incorporate async data into your application's 
signal-based code and still allow you to access its data synchronously.

This implementation is inspired by Angular's ResourceSignal.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import weakref
from enum import Enum
from typing import (
    Any,
    Awaitable,
    Callable,
    Generic,
    Optional,
    TypeVar,
    Union,
    cast,
    overload,
)
from dataclasses import dataclass

from .signal import Signal, ComputeSignal, ReadonlySignal, _assert_writable
from .context import untracked
from ._descriptor import PerInstanceDescriptor, is_instance_method
from ._debug import debug_log
from .effect import Effect
from . import scheduler as _sched
from .scheduler import batch


T = TypeVar("T")
P = TypeVar("P")


class ResourceStatus(str, Enum):
    """Status of a resource's async operation.
    
    Attributes:
        IDLE: No valid request and the loader has not run
        ERROR: The loader has encountered an error
        LOADING: The loader is running as a result of the params value changing
        RELOADING: The loader is running as a result of reload() being called
        RESOLVED: The loader has completed successfully
        LOCAL: The resource's value has been set locally via set() or update()
        CANCELLED: The current load was explicitly cancelled; any previous value is retained
    """

    IDLE = "idle"
    ERROR = "error"
    LOADING = "loading"
    RELOADING = "reloading"
    RESOLVED = "resolved"
    LOCAL = "local"
    CANCELLED = "cancelled"


@dataclass
class PreviousResourceState:
    """Container for previous resource state information."""

    status: ResourceStatus


@dataclass
class ResourceLoaderParams(Generic[P]):
    """Parameters passed to a resource loader function."""

    params: P
    previous: PreviousResourceState
    cancellation: asyncio.Event


@dataclass(frozen=True)
class ResourceSnapshot(Generic[T]):
    """Atomic snapshot of a resource's current state.
    
    Either contains a value (when resolved/loading/reloading/local) or an error.
    Snapshots are immutable: the cached record is shared by every reader.
    """

    status: ResourceStatus
    value: Optional[T] = None
    error: Optional[Exception] = None


class ResourceDescriptor(PerInstanceDescriptor["Resource[P, T]"], Generic[P, T]):
    """Descriptor that creates one Resource per owner instance."""

    def __init__(self, params: Callable[..., Optional[P]], *, equal: Optional[Callable[[T, T], bool]] = None) -> None:
        super().__init__()
        self._params = params
        self._equal = equal
        self._loader: Optional[
            Callable[..., Awaitable[T]]
        ] = None

    def loader(self, func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        self._loader = func
        return func

    def _create(self, instance: object) -> "Resource[P, T]":
        if self._loader is None:
            raise RuntimeError("Resource decorator requires a loader")
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

        def params() -> Optional[P]:
            if is_instance_method(self._params):
                return cast(Callable[[object], Optional[P]], self._params)(owner())
            return cast(Callable[[], Optional[P]], self._params)()

        async def loader(loader_params: ResourceLoaderParams[P]) -> T:
            assert self._loader is not None
            if is_instance_method(self._loader):
                return await cast(
                    Callable[[object, ResourceLoaderParams[P]], Awaitable[T]],
                    self._loader,
                )(owner(), loader_params)
            return await cast(
                Callable[[ResourceLoaderParams[P]], Awaitable[T]], self._loader
            )(loader_params)

        return Resource(params=params, loader=loader, equal=self._equal)


class Resource(Generic[P, T]):
    """A reactive resource that handles async data loading.

    Provides a signal-based interface for async operations with automatic
    dependency tracking, cancellation support, and status management.
    
    IMPORTANT: Resource must be created within an async context
    (i.e., when an event loop is running). This ensures proper async
    task scheduling and prevents threading complexity.
    """

    @overload
    def __new__(
        cls,
        params: Callable[[Any], Optional[P]],
        *, equal: Optional[Callable[[Any, Any], bool]] = None,
    ) -> ResourceDescriptor[P, Any]: ...

    @overload
    def __new__(
        cls,
        params: Callable[[], Optional[P]],
        loader: Callable[[ResourceLoaderParams[P]], Awaitable[T]],
        *, equal: Optional[Callable[[T, T], bool]] = None,
    ) -> "Resource[P, T]": ...

    def __new__(
        cls,
        params: Callable[..., Optional[P]],
        loader: Optional[Callable[[ResourceLoaderParams[P]], Awaitable[T]]] = None,
        *, equal: Optional[Callable[[T, T], bool]] = None,
    ) -> Union["Resource[P, T]", ResourceDescriptor[P, Any]]:
        if loader is None and callable(params):
            return ResourceDescriptor(params, equal=equal)
        return super().__new__(cls)

    @overload
    def __init__(
        self,
        params: Callable[[Any], Optional[P]],
        *, equal: Optional[Callable[[Any, Any], bool]] = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        params: Callable[[], Optional[P]],
        loader: Callable[[ResourceLoaderParams[P]], Awaitable[T]],
        *, equal: Optional[Callable[[T, T], bool]] = None,
    ) -> None: ...

    def __init__(
        self,
        params: Callable[..., Optional[P]],
        loader: Optional[Callable[[ResourceLoaderParams[P]], Awaitable[T]]] = None,
        *, equal: Optional[Callable[[T, T], bool]] = None,
    ):
        """Initialize a Resource.

        Args:
            params: A reactive computation that produces parameter values
            loader: An async function that loads data based on params
            equal: Optional comparison for loaded/manual values; True retains the old value
            
        Raises:
            RuntimeError: If no asyncio event loop is running
        """
        if loader is None:
            return

        # Enforce asyncio context requirement
        try:
            # Loads always run on this loop, even when params change on another thread.
            self._loop = asyncio.get_running_loop()
        except RuntimeError as e:
            raise RuntimeError(
                "Resource must be created within an asyncio context. "
                "Make sure you're inside an async function and using asyncio.run() or similar. "
                "Example: asyncio.run(main()) where Resource is created in main()."
            ) from e
        self._loader = loader
        self._params_compute = ComputeSignal(params)

        # Internal state
        def value_equal(previous: Optional[T], current: Optional[T]) -> bool:
            if previous is None or current is None or equal is None:
                return previous is current
            return equal(previous, current)

        self._value_signal: Signal[Optional[T]] = Signal(None, equal=value_equal)
        self._error_signal: Signal[Optional[Exception]] = Signal(None)
        self._status_signal: Signal[ResourceStatus] = Signal(ResourceStatus.IDLE)
        self._is_loading_signal: Signal[bool] = Signal(False)

        # Cancellation control
        self._current_cancellation: Optional[asyncio.Event] = None

        # Track the loading task
        self._loading_task: Optional[Union[asyncio.Task[None], concurrent.futures.Future[None]]] = None

        # Previous status for loader params
        self._previous_status: ResourceStatus = ResourceStatus.IDLE

        # Track previous params to detect changes
        self._previous_params: Optional[P] = None

        # Watch params changes - use sync Effect
        self._disposed = False
        # Advanced by every params change, set(), reload() and cancel(). A
        # params change queued from another thread applies only if nothing
        # newer happened in the meantime.
        self._request_generation = 0
        self._params_watcher = Effect(self._watch_params)

        # Cached snapshot computed signal
        self._snapshot_signal: Optional[ComputeSignal[ResourceSnapshot[T]]] = None
        self._value_computed: Optional[ComputeSignal[Optional[T]]] = None

        debug_log("Resource initialized")

    def _watch_params(self) -> None:
        """Internal watcher that triggers loading when params change.

        Runs on whichever thread wrote the params. Only the tracked read happens
        here; cancelling the previous load and starting the next one happen on
        the resource's event loop, because asyncio objects are not thread-safe.
        """
        params = self._params_compute.get()

        # Check if params actually changed
        if params == self._previous_params:
            return

        self._previous_params = params
        generation = self._next_request_generation()
        if _sched.running_loop() is self._loop:
            self._apply_params(params, generation)
        else:
            _sched.call_soon(self._loop, self._apply_params, params, generation)

    def _next_request_generation(self) -> int:
        """Make any queued params change obsolete; return the new generation."""
        self._request_generation += 1
        return self._request_generation

    def _apply_params(self, params: Optional[P], generation: int) -> None:
        """Cancel the current load and start the next one. Owner loop only.

        A queued change is dropped when a newer change, set(), reload() or
        cancel() happened after it was queued.
        """
        if self._disposed or generation != self._request_generation:
            return

        if params is None:
            # If params is None, abort any ongoing load and set status to idle
            self._abort_current_load()
            with untracked(), batch():  # one transition
                self._status_signal.set(ResourceStatus.IDLE)
                self._is_loading_signal.set(False)
            return

        # Cancel any ongoing load, then start the new one
        self._abort_current_load()
        self._start_load(params)

    def _abort_current_load(self) -> None:
        """Abort the current loading operation if one is in progress."""
        if self._current_cancellation is not None:
            # Set the event so the loader can detect cancellation
            self._current_cancellation.set()
            self._current_cancellation = None
        
        # Note: We don't call task.cancel() here because we want the loader
        # to detect cancellation via the event and clean up gracefully.
        # The task will complete naturally when the loader checks the event.

    def _start_load(self, params: P, is_reload: bool = False) -> None:
        """Start a new loading operation.

        Args:
            params: The parameter value to pass to the loader
            is_reload: Whether this load is from a manual reload call
        """
        # Create new cancellation event
        cancellation = asyncio.Event()
        self._current_cancellation = cancellation

        # Set status
        with untracked(), batch():  # one transition
            if is_reload:
                self._status_signal.set(ResourceStatus.RELOADING)
            else:
                self._status_signal.set(ResourceStatus.LOADING)

            self._is_loading_signal.set(True)
            self._error_signal.set(None)

        # Observers of the transition above ran user code, which may have
        # disposed or cancelled the resource, written a local value or started
        # another load. Each of those sets this load's cancellation event.
        if cancellation.is_set():
            debug_log("Load superseded while publishing its status; not starting it")
            return

        # Build loader params
        loader_params = ResourceLoaderParams(
            params=params,
            previous=PreviousResourceState(status=self._previous_status),
            cancellation=cancellation,
        )

        # Store previous status
        self._previous_status = self._status_signal._value

        # Start the async load
        self._run_loader(loader_params, cancellation)

    def _run_loader(
        self, loader_params: ResourceLoaderParams[P], cancellation: asyncio.Event
    ) -> None:
        """Execute the loader function asynchronously.

        Args:
            loader_params: Parameters to pass to the loader
            cancellation: The cancellation event for this operation
        """

        async def _execute() -> None:
            if cancellation.is_set():
                # Superseded before the task got to run (for example by an
                # observer of the loading status): never call the loader.
                debug_log("Load superseded before it started")
                return
            try:
                result = await self._loader(loader_params)

                # Check if cancelled
                if cancellation.is_set():
                    debug_log("Load aborted, not updating value")
                    return

                # Update state (use untracked to avoid triggering watchers)
                with untracked(), batch():  # one transition
                    self._value_signal.set(result)
                    self._status_signal.set(ResourceStatus.RESOLVED)
                    self._is_loading_signal.set(False)
                    self._error_signal.set(None)
                self._previous_status = ResourceStatus.RESOLVED

                debug_log(lambda: f"Resource loaded successfully: {result}")

            except asyncio.CancelledError:
                # Task was cancelled, clean exit without warnings
                debug_log("Load task cancelled")
                raise  # Re-raise to properly mark task as cancelled

            except Exception as e:
                # Check if cancelled
                if cancellation.is_set():
                    debug_log(lambda exc=e: f"Load cancelled during error: {exc}")
                    return

                # Update error state (use untracked to avoid triggering watchers)
                with untracked(), batch():  # one transition
                    self._error_signal.set(e)
                    self._status_signal.set(ResourceStatus.ERROR)
                    self._is_loading_signal.set(False)
                self._previous_status = ResourceStatus.ERROR

                debug_log(lambda exc=e: f"Resource load error: {exc}")

        # Schedule on the resource's event loop (thread-safe from other threads).
        # Store task reference to prevent garbage collection!
        task = _sched.create_task(_execute(), self._loop)
        self._loading_task = task
        
        # Add done callback to handle task completion and prevent "pending task" warnings
        def _task_done_callback(t: Union[asyncio.Task[None], concurrent.futures.Future[None]]) -> None:
            try:
                # Retrieve result/exception to mark task as "retrieved"
                # This prevents "Task was destroyed but it is pending" warnings
                t.result()
            except asyncio.CancelledError:
                # Expected when we cancel tasks
                debug_log("Task was cancelled (expected)")
            except Exception as e:
                # Already logged in _execute, just consume the exception
                debug_log(lambda exc=e: f"Task completed with exception: {exc}")
        
        task.add_done_callback(_task_done_callback)
        debug_log(lambda: f"Scheduled loader in event loop, task: {self._loading_task}")

    def reload(self) -> None:
        """Manually trigger the loader to reload data.

        This will execute the loader even if params haven't changed,
        and sets the status to RELOADING during the operation.
        """
        _assert_writable()  # before any state change: a rejected call changes nothing
        if self._disposed:
            return
        self._next_request_generation()

        # Force re-execution of the watcher by marking it dirty
        # We do this by getting the current params and starting a new load
        with untracked():
            params = self._params_compute.get()
            if params is not None:
                self._abort_current_load()
                self._start_load(params, is_reload=True)

    @property
    def value(self) -> ComputeSignal[Optional[T]]:
        """Signal containing the loaded value or None if not yet loaded.

        Reading this signal will throw if the resource is in error state.
        Use has_value() as a guard before reading this in computed signals.
        The same signal is returned on every access.
        """
        if self._value_computed is None:

            def _get_value() -> Optional[T]:
                if self._status_signal.get() == ResourceStatus.ERROR:
                    error = self._error_signal.get()
                    raise error if error else RuntimeError("Resource is in error state")
                return self._value_signal.get()

            self._value_computed = ComputeSignal(_get_value, equal=self._value_signal._equal)
        return self._value_computed

    @property
    def error(self) -> ReadonlySignal[Optional[Exception]]:
        """Readonly signal containing the most recent error or None."""
        return self._error_signal.as_readonly()

    @property
    def is_loading(self) -> ReadonlySignal[bool]:
        """Readonly signal indicating whether the loader is currently running."""
        return self._is_loading_signal.as_readonly()

    @property
    def status(self) -> ReadonlySignal[ResourceStatus]:
        """Readonly signal containing the current status of the resource."""
        return self._status_signal.as_readonly()

    @property
    def cancellation_event(self) -> Optional[asyncio.Event]:
        """Get the current cancellation event, if any.
        
        Returns the cancellation event for the currently running request,
        or None if no request is in progress. The loader can check
        `event.is_set()` to see if the request was cancelled.
        """
        return self._current_cancellation

    def previous_status(self) -> ResourceStatus:
        """Get the previous status of the resource.
        
        This is useful for tracking state transitions and implementing
        optimistic updates or caching strategies.
        """
        return self._previous_status

    def snapshot(self) -> ComputeSignal[ResourceSnapshot[T]]:
        """Get an atomic snapshot of the resource's current state.
        
        Returns a computed signal containing a ResourceSnapshot with the
        current status, value (if available), and error (if any).
        This provides a way to access the resource's state atomically
        without multiple signal reads.
        
        Example:
            ```python
            def show_data():
                snap = resource.snapshot()()
                if snap.status == ResourceStatus.RESOLVED:
                    print(f"Value: {snap.value}")
                elif snap.status == ResourceStatus.ERROR:
                    print(f"Error: {snap.error}")
            ```
        """
        if self._snapshot_signal is None:
            def compute_snapshot() -> ResourceSnapshot[T]:
                status = self._status_signal.get()
                if status == ResourceStatus.ERROR:
                    return ResourceSnapshot(
                        status=status,
                        error=self._error_signal.get(),
                    )
                else:
                    return ResourceSnapshot(
                        status=status,
                        value=self._value_signal.get(),
                    )
            
            self._snapshot_signal = ComputeSignal(compute_snapshot)
        
        return self._snapshot_signal

    def has_value(self) -> bool:
        """Check if the resource has a valid value.
        
        Returns True if the resource has a value and is not in error state.
        Check it before calling ``value()``, which raises in the error state.
        It is a runtime check only: static type checkers do not narrow
        ``value()`` from ``Optional[T]`` to ``T`` after it.
        
        Example:
            ```python
            @computed
            def name():
                return (
                    resource.value()["name"]
                    if resource.has_value()
                    else "Loading..."
                )
            ```
        """
        return (
            self._value_signal.get() is not None
            and self._status_signal.get() != ResourceStatus.ERROR
        )

    def set(self, value: T) -> None:
        """Locally set the resource value.

        This sets the status to LOCAL and cancels any ongoing load. The new
        value and status are published together. A rejected write (inside a
        computed or a Watcher notify callback) or a raising ``equal`` leaves the
        resource, including a running load, untouched.
        """
        _assert_writable()
        with batch():
            self._value_signal.set(value)  # may raise from equal: nothing changed yet
            self._next_request_generation()
            self._abort_current_load()
            self._status_signal.set(ResourceStatus.LOCAL)
            self._is_loading_signal.set(False)
            self._error_signal.set(None)
            self._previous_status = ResourceStatus.LOCAL

    def update(self, update_fn: Callable[[Optional[T]], T]) -> None:
        """Update the resource value using a function.

        This sets the status to LOCAL and cancels any ongoing load. Reading the
        current value here does not create a dependency.
        """
        _assert_writable()  # before calling update_fn: a rejected write runs nothing
        current = untracked(self._value_signal)
        self.set(update_fn(current))

    def cancel(self) -> bool:
        """Cancel the current load, retaining its last value and request dependencies.

        Signals cancellation to the loader and cancels its asyncio task. Cleanup runs
        at the next await; even a loader that suppresses cancellation cannot publish
        its obsolete result. A parameter change or ``reload()`` starts a new load.
        Returns False when no load is running. Call on the resource's owner loop.
        """
        _assert_writable()  # before any state change: a rejected call changes nothing
        with untracked(), batch():
            if not self._is_loading_signal():
                return False
            self._next_request_generation()
            self._abort_current_load()
            task = self._loading_task
            if task is not None and not task.done():
                task.cancel()
            self._error_signal.set(None)
            self._status_signal.set(ResourceStatus.CANCELLED)
            self._is_loading_signal.set(False)
            self._previous_status = ResourceStatus.CANCELLED
        return True

    def dispose(self) -> None:
        """Stop the resource permanently.

        Cancels a running load (its result is never published), stops reacting
        to parameter changes, and turns ``reload()`` into a no-op. The last
        value, error and status stay readable. Call on the resource's event loop.
        """
        _assert_writable()  # before marking disposed, so a rejected call can be retried
        if self._disposed:
            return
        self._disposed = True
        self._params_watcher.dispose()
        self.cancel()

    def destroy(self) -> None:
        """Alias of :meth:`dispose`, kept for compatibility."""
        self.dispose()

    def __del__(self) -> None:
        """Automatic cleanup when garbage collected.
        
        Cancels any pending async tasks when the Resource is
        garbage collected, preventing resource leaks.
        """
        try:
            self._abort_current_load()
            debug_log("Resource garbage collected and cleaned up")
        except Exception:
            # Ignore errors during cleanup - we're being GC'd anyway
            pass


class _TypedResourceFactory(Generic[P, T]):
    """Typed Resource decorator used by ``resource[Params, Value]`` syntax."""

    def __call__(self, params: Callable[..., object], /, *, equal: Optional[Callable[[T, T], bool]] = None) -> ResourceDescriptor[P, T]:
        return ResourceDescriptor(cast(Callable[..., Optional[P]], params), equal=equal)


class _ResourceFactory:
    """Lowercase decorator-friendly Resource factory."""

    @overload
    def __call__(
        self,
        params: Callable[[Any], Optional[P]],
        *, equal: Optional[Callable[[Any, Any], bool]] = None,
    ) -> ResourceDescriptor[P, Any]: ...

    @overload
    def __call__(
        self,
        params: Callable[[], Optional[P]],
        loader: Callable[[ResourceLoaderParams[P]], Awaitable[T]],
        *, equal: Optional[Callable[[T, T], bool]] = None,
    ) -> Resource[P, T]: ...

    def __call__(
        self,
        params: Callable[..., Optional[P]],
        loader: Optional[Callable[[ResourceLoaderParams[P]], Awaitable[T]]] = None,
        *, equal: Optional[Callable[[T, T], bool]] = None,
    ) -> Union[Resource[P, T], ResourceDescriptor[P, Any]]:
        if loader is None:
            return Resource(params, equal=equal)
        return Resource(params, loader=loader, equal=equal)

    @overload
    def __getitem__(
        self, types: tuple[type[P], type[T]]
    ) -> _TypedResourceFactory[P, T]: ...

    @overload
    def __getitem__(self, types: object) -> _TypedResourceFactory[Any, Any]: ...

    def __getitem__(self, types: object) -> _TypedResourceFactory[Any, Any]:
        del types
        return _TypedResourceFactory()


resource: _ResourceFactory = _ResourceFactory()
