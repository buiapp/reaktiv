import asyncio
from typing import Dict

from reaktiv import Signal, batch, computed, effect, signal


Shares = Dict[str, int]


async def main() -> None:
    # Real-time stock prices
    apple_price = signal(195.00)
    google_price = signal(2750.00)

    # User's portfolio
    shares: Signal[Shares] = signal({"AAPL": 100, "GOOGL": 50})

    # Computed total portfolio value
    @computed
    def portfolio_value() -> float:
        return shares()["AAPL"] * apple_price() + shares()["GOOGL"] * google_price()

    # Price alert system
    def check_alerts() -> None:
        # create a snapshot of the signal values
        apple_price_value = apple_price()
        google_price_value = google_price()

        async def print_alert() -> None:
            if apple_price_value > 200:
                print("📈 AAPL alert: Above $200!")
            if google_price_value < 2700:
                print("📉 GOOGL alert: Below $2700!")

        # print the alert asynchronously
        asyncio.create_task(print_alert())

    # Automatic updates
    async def live_updates() -> None:
        # Simulate real-time updates
        while True:
            await asyncio.sleep(1)
            with batch():
                apple_price.update(lambda v: v * 1.01)  # +1%
                google_price.update(lambda v: v * 0.995)  # -0.5%

            print(f"🍏 AAPL: ${apple_price():,.2f}  🌐 GOOGL: ${google_price():,.2f}")

    # Track portfolio value
    def monitor_portfolio() -> None:
        print(f"💰 Current value: ${portfolio_value():,.2f}")

    # Set up effects
    _alerts_effect = effect(check_alerts)
    _portfolio_effect = effect(monitor_portfolio)

    # Start live updates
    _updates_task = asyncio.create_task(live_updates())

    # Run for 5 seconds
    await asyncio.sleep(5)


asyncio.run(main())
