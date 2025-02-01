import asyncio
import random
from reaktiv import Signal, ComputeSignal, Effect

async def main():
    # Initialize sensor readings (in °C)
    sensor1 = Signal(20.0)
    sensor2 = Signal(21.0)
    sensor3 = Signal(19.5)

    # Compute aggregates: average, minimum, and maximum temperature.
    avg_temp = ComputeSignal(lambda: (sensor1.get() + sensor2.get() + sensor3.get()) / 3)
    min_temp = ComputeSignal(lambda: min(sensor1.get(), sensor2.get(), sensor3.get()))
    max_temp = ComputeSignal(lambda: max(sensor1.get(), sensor2.get(), sensor3.get()))

    # Effect to display current sensor readings and computed statistics.
    async def display_aggregates():
        print(f"🌡️ Sensor readings: {sensor1.get():.2f}°C, {sensor2.get():.2f}°C, {sensor3.get():.2f}°C")
        print(f"📊 Avg: {avg_temp.get():.2f}°C | ⬇️ Min: {min_temp.get():.2f}°C | ⬆️ Max: {max_temp.get():.2f}°C")
        print("-------------------------------------------------------------")

    # Schedule the display effect.
    display_effect = Effect(display_aggregates)
    display_effect.schedule()

    # Effect to trigger alerts when values exceed safe limits.
    async def temperature_alert():
        if avg_temp.get() > 25:
            print("🚨 ALERT: Average temperature is too high! 🔥")
        if min_temp.get() < 15:
            print("🚨 ALERT: One or more sensors report a temperature that's too low! ❄️")
        if max_temp.get() > 30:
            print("🚨 ALERT: A sensor is overheating! 🔥")

    # Schedule the alert effect.
    alert_effect = Effect(temperature_alert)
    alert_effect.schedule()

    def update_sensor(sensor: Signal, sensor_name: str):
        """
        Update a sensor value with a normal drift.
        With a 10% chance, inject a fault (a dramatic spike or drop) to trigger alerts.
        """
        if random.random() < 0.1:
            # Fault injection: choose a spike (overheat) or a drop (undercool)
            change = random.choice([random.uniform(5.0, 10.0), random.uniform(-10.0, -5.0)])
            print(f"[{sensor_name}] ⚠️ Fault injection: {change:+.2f}°C")
        else:
            # Normal fluctuation
            change = random.uniform(-0.5, 1.0)
        sensor.set(sensor.get() + change)

    # Simulate periodic sensor updates.
    for _ in range(15):
        await asyncio.sleep(2)
        update_sensor(sensor1, "Sensor1")
        update_sensor(sensor2, "Sensor2")
        update_sensor(sensor3, "Sensor3")

    # Allow any pending effects to process.
    await asyncio.sleep(1)

if __name__ == '__main__':
    asyncio.run(main())
