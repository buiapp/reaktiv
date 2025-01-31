import asyncio
from reaktiv import Signal, ComputeSignal, Effect

async def main():
    # Real-time stock prices
    apple_price = Signal(195.00)
    google_price = Signal(2750.00)
    
    # User's portfolio
    shares = Signal({
        'AAPL': 100,
        'GOOGL': 50
    })

    # Computed total portfolio value
    portfolio_value = ComputeSignal(lambda: (
        shares.get()['AAPL'] * apple_price.get() +
        shares.get()['GOOGL'] * google_price.get()
    ))

    # Price alert system
    async def check_alerts():
        if apple_price.get() > 200:
            print("📈 AAPL alert: Above $200!")
        if google_price.get() < 2700:
            print("📉 GOOGL alert: Below $2700!")

    # Automatic updates
    async def live_updates():
        # Simulate real-time updates
        while True:
            await asyncio.sleep(1)
            apple_price.set(apple_price.get() * 1.01)  # +1%
            google_price.set(google_price.get() * 0.995)  # -0.5%
            print(f"🍏 AAPL: ${apple_price.get():,.2f}  🌐 GOOGL: ${google_price.get():,.2f}")

    # Track portfolio value
    async def monitor_portfolio():
        print(f"💰 Current value: ${portfolio_value.get():,.2f}")

    # Set up effects
    alerts_effect = Effect(check_alerts)
    updates_effect = Effect(live_updates)
    portfolio_effect = Effect(monitor_portfolio)

    alerts_effect.schedule()
    updates_effect.schedule()
    portfolio_effect.schedule()
    
    # Run for 5 seconds
    await asyncio.sleep(5)

asyncio.run(main())