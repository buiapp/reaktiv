import random
from reaktiv import signal, computed, effect, batch
from time import sleep


# Initialize sensor readings (in °C)
sensor1 = signal(20.0)
sensor2 = signal(21.0)
sensor3 = signal(19.5)

# Compute aggregates: average, minimum, and maximum temperature.
@computed
def avg_temp():
    return (sensor1() + sensor2() + sensor3()) / 3


@computed
def min_temp():
    return min(sensor1(), sensor2(), sensor3())


@computed
def max_temp():
    return max(sensor1(), sensor2(), sensor3())


# Effect to display current sensor readings and computed statistics.
def display_aggregates():
    print(f"🌡️ Sensor readings: {sensor1():.2f}°C, {sensor2():.2f}°C, {sensor3():.2f}°C")
    print(
        f"📊 Avg: {avg_temp():.2f}°C | ⬇️ Min: {min_temp():.2f}°C | ⬆️ Max: {max_temp():.2f}°C"
    )
    print("-------------------------------------------------------------")


# Schedule the display effect.
_display_effect = effect(display_aggregates)


# Effect to trigger alerts when values exceed safe limits.
def temperature_alert():
    if avg_temp() > 25:
        print("🚨 ALERT: Average temperature is too high! 🔥")
    if min_temp() < 15:
        print("🚨 ALERT: One or more sensors report a temperature that's too low! ❄️")
    if max_temp() > 30:
        print("🚨 ALERT: A sensor is overheating! 🔥")


# Schedule the alert effect.
_alert_effect = effect(temperature_alert)


def update_sensor(sensor, sensor_name: str):
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
    sensor.update(lambda current: current + change)


# Simulate periodic sensor updates.
for _ in range(15):
    sleep(1)
    with batch():
        update_sensor(sensor1, "Sensor1")
        update_sensor(sensor2, "Sensor2")
        update_sensor(sensor3, "Sensor3")
