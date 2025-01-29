import asyncio
from typing import Optional, Set
from signal_library import Signal, Effect

async def main():
    # Create signals
    count = Signal(0)
    name = Signal("Alice")

    # Create effect that logs count changes
    async def log_count():
        print(f"Count updated: {count.get()}")

    effect = Effect(log_count)
    effect.schedule()

    # Create effect with multiple dependencies
    async def user_info():
        print(f"User {name.get()} has count {count.get()}")

    user_effect = Effect(user_info)
    user_effect.schedule()

    # Update signals
    await asyncio.sleep(0.1)
    count.set(1)  # Triggers both effects
    await asyncio.sleep(0.1)
    name.set("Bob")  # Triggers only user_effect
    await asyncio.sleep(0.1)

    # Cleanup
    effect.dispose()
    user_effect.dispose()

asyncio.run(main())