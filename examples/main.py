import asyncio
from reaktiv import Signal, ComputeSignal, Effect

async def main():
    # Basic signals
    counter = Signal(1)  # Start with non-zero value
    username = Signal("Alice")
    active = Signal(True)

    # Computed signals
    doubled = ComputeSignal(lambda: counter.get() * 2)
    tax_rate = Signal(0.2)
    total = ComputeSignal(lambda: doubled.get() * (1 + tax_rate.get()))
    display_name = ComputeSignal(lambda: 
        f"{username.get().upper()}" if active.get() 
        else "INACTIVE USER"
    )
    risky_computation = ComputeSignal(
        lambda: 10 / counter.get(),
        default=float('inf')
    )

    # Logging effect
    async def log_changes():
        print(f"\nCounter: {counter.get()}")
        print(f"Display name: {display_name.get()}")
        print(f"Doubled: {doubled.get()}")
        print(f"Total with tax: {total.get():.2f}")
        print(f"Risk computation: {risky_computation.get():.2f}")

    log_effect = Effect(log_changes)
    log_effect.schedule()

    # Demonstration sequence
    print("=== Initial state ===")
    await asyncio.sleep(0.1)

    print("\n=== Update counter to 5 ===")
    counter.set(5)
    await asyncio.sleep(0.1)

    print("\n=== Deactivate user ===")
    active.set(False)
    await asyncio.sleep(0.1)

    print("\n=== Update username to Bob (while inactive) ===")
    username.set("Bob")
    await asyncio.sleep(0.1)

    print("\n=== Reactivate and update username to Charlie ===")
    active.set(True)
    username.set("Charlie")
    await asyncio.sleep(0.1)

    print("\n=== Trigger division by zero ===")
    counter.set(0)
    await asyncio.sleep(0.1)

    log_effect.dispose()

if __name__ == "__main__":
    asyncio.run(main())