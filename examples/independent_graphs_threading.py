"""Show that independent ReactiveModel graphs do not block each other."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from reaktiv import ReactiveModel, computed, effect, field

PrintRow = Callable[[str, str], None]


class DemoGraph(ReactiveModel):
    source = field(0)

    def __init__(
        self, multiplier: int, steps: int, right: bool, print_row: PrintRow
    ) -> None:
        self.multiplier = multiplier
        self.steps = steps
        self.right = right
        self.print_row = print_row
        self.effect_ran = threading.Event()
        self.set_returned = threading.Event()
        super().__init__()

    def print(self, message: str) -> None:
        self.print_row("", message) if self.right else self.print_row(message, "")

    @computed
    def total(self) -> int:
        return self.source() * self.multiplier

    @effect
    def show(self) -> None:
        value = self.total()
        if value == 0:
            return

        self.effect_ran.set()
        for step in range(1, self.steps + 1):
            self.print(f"working {step}/{self.steps}")
            time.sleep(0.35)
        self.print("done" if self.steps else f"done value={value}")

    def update(self) -> None:
        self.print("set(1)")
        self.source.set(1)
        self.set_returned.set()
        self.print("set returned")


def main() -> None:
    started = time.perf_counter()
    print_lock = threading.Lock()

    def print_row(left: str = "", right: str = "") -> None:
        elapsed_ms = (time.perf_counter() - started) * 1000
        with print_lock:
            print(f"{elapsed_ms:7.1f} ms | {left:<24} | {right}", flush=True)

    print("\nIndependent ReactiveModel graphs in different threads")
    print("Graph B should finish while slow Graph A is still working.\n")
    print(" time     | graph A: slow            | graph B: fast")
    print("-" * 65)

    slow = DemoGraph(multiplier=10, steps=6, right=False, print_row=print_row)
    fast = DemoGraph(multiplier=100, steps=0, right=True, print_row=print_row)

    slow_thread = threading.Thread(target=slow.update)
    fast_thread = threading.Thread(target=fast.update)

    try:
        slow_thread.start()
        assert slow.effect_ran.wait(timeout=1), "Graph A did not start"

        time.sleep(0.55)
        fast_thread.start()

        assert fast.effect_ran.wait(timeout=1), "Graph B was blocked"
        assert fast.set_returned.wait(timeout=1), "Graph B set() did not return"
        assert not slow.set_returned.is_set(), "Graph A finished too early"
        print_row("still working", "finished first")

        slow_thread.join(timeout=4)
        fast_thread.join(timeout=1)
        assert not slow_thread.is_alive()
        assert not fast_thread.is_alive()

        print("-" * 65)
        print("[PASS] Graph B finished while Graph A was still working.\n")
    finally:
        slow.dispose()
        fast.dispose()


if __name__ == "__main__":
    main()
