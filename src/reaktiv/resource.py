"""Resource - Async reactivity with resources.

A Resource gives you a way to incorporate async data into your application's 
signal-based code and still allow you to access its data synchronously.

This implementation is inspired by Angular's ResourceSignal.
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import (
    Awaitable,
    Callable,
    Generic,
    Optional,
    TypeVar,
)
from dataclasses import dataclass

from .signal import Signal, ComputeSignal, ReadonlySignal
from .context import untracked
from ._debug import debug_log
from .effect import Effect


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
    """

    IDLE = "idle"
    ERROR = "error"
    LOADING = "loading"
    RELOADING = "reloading"
    RESOLVED = "resolved"
    LOCAL = "local"


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


@dataclass
class ResourceSnapshot(Generic[T]):
    """Atomic snapshot of a resource's current state.
    
    Either contains a value (when resolved/loading/reloading/local) or an error.
    """

    status: ResourceStatus
    value: Optional[T] = None
    error: Optional[Exception] = None


class Resource(Generic[P, T]):
    """A reactive resource that handles async data loading.

    Provides a signal-based interface for async operations with automatic
    dependency tracking, cancellation support, and status management.
    
    IMPORTANT: Resource must be created within an async context
    (i.e., when an event loop is running). This ensures proper async
    task scheduling and prevents threading complexity.
    """

    def __init__(
        self,
        params: Callable[[], Optional[P]],
        loader: Callable[[ResourceLoaderParams[P]], Awaitable[T]],
    ):
        """Initialize a Resource.

        Args:
            params: A reactive computation that produces parameter values
            loader: An async function that loads data based on params
            
        Raises:
            RuntimeError: If no asyncio event loop is running
        """
        # Enforce asyncio context requirement
        try:
            asyncio.get_running_loop()
        except RuntimeError as e:
            raise RuntimeError(
                "Resource must be created within an asyncio context. "
                "Make sure you're inside an async function and using asyncio.run() or similar. "
                "Example: asyncio.run(main()) where Resource is created in main()."
            ) from e
        self._loader = loader
        self._params_compute = ComputeSignal(params)

        # Internal state
        self._value_signal: Signal[Optional[T]] = Signal(None)
        self._error_signal: Signal[Optional[Exception]] = Signal(None)
        self._status_signal: Signal[ResourceStatus] = Signal(ResourceStatus.IDLE)
        self._is_loading_signal: Signal[bool] = Signal(False)

        # Cancellation control
        self._current_cancellation: Optional[asyncio.Event] = None

        # Track the loading task
        self._loading_task: Optional[asyncio.Task[None]] = None

        # Previous status for loader params
        self._previous_status: ResourceStatus = ResourceStatus.IDLE

        # Manual reload counter to differentiate from param changes
        self._reload_requested = False

        # Track previous params to detect changes
        self._previous_params: Optional[P] = None

        # Watch params changes - use sync Effect
        self._params_watcher = Effect(self._watch_params)

        # Cached snapshot computed signal
        self._snapshot_signal: Optional[ComputeSignal[ResourceSnapshot[T]]] = None

        debug_log("Resource initialized")

    def _watch_params(self) -> None:
        """Internal watcher that triggers loading when params change."""
        params = self._params_compute.get()

        # Check if params actually changed
        if params == self._previous_params and not self._reload_requested:
            return

        self._previous_params = params

        if params is None:
            # If params is None, abort any ongoing load and set status to idle
            self._abort_current_load()
            with untracked():
                self._status_signal.set(ResourceStatus.IDLE)
                self._is_loading_signal.set(False)
            return

        # Cancel any ongoing load
        self._abort_current_load()

        # Start new load
        self._start_load(params, is_reload=self._reload_requested)
        self._reload_requested = False

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
        with untracked():
            if is_reload:
                self._status_signal.set(ResourceStatus.RELOADING)
            else:
                self._status_signal.set(ResourceStatus.LOADING)

            self._is_loading_signal.set(True)
            self._error_signal.set(None)

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
            try:
                result = await self._loader(loader_params)

                # Check if cancelled
                if cancellation.is_set():
                    debug_log("Load aborted, not updating value")
                    return

                # Update state (use untracked to avoid triggering watchers)
                with untracked():
                    self._value_signal.set(result)
                    self._status_signal.set(ResourceStatus.RESOLVED)
                    self._is_loading_signal.set(False)
                    self._error_signal.set(None)
                self._previous_status = ResourceStatus.RESOLVED

                debug_log(f"Resource loaded successfully: {result}")

            except asyncio.CancelledError:
                # Task was cancelled, clean exit without warnings
                debug_log("Load task cancelled")
                raise  # Re-raise to properly mark task as cancelled

            except Exception as e:
                # Check if cancelled
                if cancellation.is_set():
                    debug_log(f"Load cancelled during error: {e}")
                    return

                # Update error state (use untracked to avoid triggering watchers)
                with untracked():
                    self._error_signal.set(e)
                    self._status_signal.set(ResourceStatus.ERROR)
                    self._is_loading_signal.set(False)
                self._previous_status = ResourceStatus.ERROR

                debug_log(f"Resource load error: {e}")

        # Schedule in the current event loop
        loop = asyncio.get_running_loop()
        # Store task reference to prevent garbage collection!
        task = loop.create_task(_execute())
        self._loading_task = task
        
        # Add done callback to handle task completion and prevent "pending task" warnings
        def _task_done_callback(t: asyncio.Task) -> None:
            try:
                # Retrieve result/exception to mark task as "retrieved"
                # This prevents "Task was destroyed but it is pending" warnings
                t.result()
            except asyncio.CancelledError:
                # Expected when we cancel tasks
                debug_log("Task was cancelled (expected)")
            except Exception as e:
                # Already logged in _execute, just consume the exception
                debug_log(f"Task completed with exception: {e}")
        
        task.add_done_callback(_task_done_callback)
        debug_log(f"Scheduled loader in event loop, task: {self._loading_task}")

    def reload(self) -> None:
        """Manually trigger the loader to reload data.

        This will execute the loader even if params haven't changed,
        and sets the status to RELOADING during the operation.
        """
        self._reload_requested = True

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
        """

        def _get_value() -> Optional[T]:
            if self._status_signal.get() == ResourceStatus.ERROR:
                error = self._error_signal.get()
                raise error if error else RuntimeError("Resource is in error state")
            return self._value_signal.get()

        return ComputeSignal(_get_value)

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
        """Check if the resource has a valid value (type guard).
        
        Returns True if the resource has a value and is not in error state.
        This method can be used as a type guard in computed signals before
        accessing the value.
        
        Example:
            ```python
            name = Computed(lambda: (
                resource.value()()['name'] 
                if resource.has_value() 
                else 'Loading...'
            ))
            ```
        """
        return (
            self._value_signal.get() is not None
            and self._status_signal.get() != ResourceStatus.ERROR
        )

    def set(self, value: T) -> None:
        """Locally set the resource value.

        This sets the status to LOCAL and cancels any ongoing load.
        """
        self._abort_current_load()
        self._value_signal.set(value)
        self._status_signal.set(ResourceStatus.LOCAL)
        self._is_loading_signal.set(False)
        self._error_signal.set(None)
        self._previous_status = ResourceStatus.LOCAL

    def update(self, update_fn: Callable[[Optional[T]], T]) -> None:
        """Update the resource value using a function.

        This sets the status to LOCAL and cancels any ongoing load.
        """
        self._abort_current_load()
        current = self._value_signal.get()
        new_value = update_fn(current)
        self.set(new_value)

    def destroy(self) -> None:
        """Clean up the resource by cancelling any pending tasks.
        
        This method should be called when the resource is no longer needed
        to ensure proper cleanup of async tasks.
        """
        self._abort_current_load()

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
