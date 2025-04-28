import asyncio
from reaktiv import batch, Signal, Computed, Effect

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
    portfolio_value = Computed(lambda: (
        shares()['AAPL'] * apple_price() +
        shares()['GOOGL'] * google_price()
    ))
    
    # Price alert system
    async def check_alerts():
        if apple_price() > 200:
            print("📈 AAPL alert: Above $200!")
        if google_price() < 2700:
            print("📉 GOOGL alert: Below $2700!")
    
    # Automatic updates
    async def live_updates():
        # Simulate real-time updates
        while True:
            await asyncio.sleep(1)
            with batch():
                apple_price.update(lambda v: v * 1.01)  # +1%
                google_price.update(lambda v: v * 0.995)  # -0.5%
            
            print(f"🍏 AAPL: ${apple_price():,.2f}  🌐 GOOGL: ${google_price():,.2f}")
    
    # Track portfolio value
    async def monitor_portfolio():
        print(f"💰 Current value: ${portfolio_value():,.2f}")
    
    # Set up effects
    alerts_effect = Effect(check_alerts)
    portfolio_effect = Effect(monitor_portfolio)
    
    # Start live updates
    updates_task = asyncio.create_task(live_updates())
    
    # Run for 5 seconds
    await asyncio.sleep(5)

asyncio.run(main())