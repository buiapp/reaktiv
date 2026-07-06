"""
IoT Sensor Agent with reaktiv.

This example demonstrates how reaktiv can be used to create a reactive system
that responds to hardware sensor changes running in a separate thread.

Key concepts demonstrated:
- Automatic recalculation of derived values as sensor readings change
- Reactive effects for monitoring, alerting, and taking action on sensor data
- Clean separation between sensor data acquisition and business logic

In a real-world application:
- The sensor loop would interface with actual hardware via libraries like
  RPi.GPIO, Adafruit_CircuitPython, Arduino libraries, etc.
- Multiple effects might update displays, trigger actuators, log to databases,
  or send notifications through various channels
"""

import threading
import time
import random
from typing import Literal, Optional

from reaktiv import ReactiveModel, batch, computed, effect, field

ComfortLevel = Literal["TOO COLD", "TOO HOT", "TOO DRY", "TOO HUMID", "COMFORTABLE"]
SensorStatus = Literal["ERROR", "ACTIVE", "STANDBY"]


class IoTSensorAgent(ReactiveModel):
    """Threaded IoT sensor agent that provides reactive sensor data updates."""

    # Core sensor signals - in a real system these would be updated from hardware
    temperature = field(21.0)
    humidity = field(50.0)
    is_running = field(False)
    sensor_error = field(False)

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        super().__init__()

    # Computed values automatically derive from raw sensor data
    @computed
    def heat_index(self) -> float:
        return self.temperature() + 0.05 * self.humidity()

    @computed
    def comfort_level(self) -> ComfortLevel:
        """Determine comfort level based on temperature and humidity."""
        t, h = self.temperature(), self.humidity()

        if t < 18:
            return "TOO COLD"
        if t > 26:
            return "TOO HOT"
        if h < 30:
            return "TOO DRY"
        if h > 70:
            return "TOO HUMID"
        return "COMFORTABLE"

    @computed
    def sensor_status(self) -> SensorStatus:
        if self.sensor_error():
            return "ERROR"
        if self.is_running():
            return "ACTIVE"
        return "STANDBY"

    def start_sensor(self) -> None:
        """Start the sensor agent thread."""
        if self.is_running():
            return

        self.is_running.set(True)
        self._thread = threading.Thread(target=self._sensor_loop, daemon=True)
        self._thread.start()
        print(f"Sensor agent started with status: {self.sensor_status()}")

    def stop_sensor(self) -> None:
        """Stop the sensor agent."""
        self.is_running.set(False)
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _sensor_loop(self) -> None:
        """Main sensor polling loop running in a separate thread.

        In a real application, this would read from actual hardware sensors.
        """
        try:
            while self.is_running():
                # Simulate sensor readings with small random changes
                # In a real application: read from I2C/SPI/GPIO sensors here
                new_temp = max(
                    10, min(35, self.temperature() + random.uniform(-0.5, 0.5))
                )
                new_humidity = max(20, min(90, self.humidity() + random.uniform(-1, 1)))

                # Occasionally simulate sensor error (1% chance)
                # In a real application: detect actual hardware communication errors
                if random.random() < 0.01:
                    self.sensor_error.set(True)
                    time.sleep(2)
                    self.sensor_error.set(False)

                # Update signals if not in error state
                if not self.sensor_error():
                    # Simply updating these signals will automatically trigger
                    # all dependent computed values and effects
                    with batch():
                        self.temperature.set(new_temp)
                        self.humidity.set(new_humidity)

                time.sleep(1)

        except Exception as e:
            print(f"Sensor error: {e}")
            with batch():
                self.sensor_error.set(True)
                self.is_running.set(False)


def demo() -> None:
    """Demonstrate how reaktiv enables automatic reactions to sensor data changes."""
    # Create sensor agent
    sensor = IoTSensorAgent()

    # Define effect functions
    def log_sensor() -> None:
        """Log current sensor readings to console."""
        print(
            f"Temp: {sensor.temperature():.1f}°C | "
            f"Humidity: {sensor.humidity():.1f}% | "
            f"Status: {sensor.sensor_status()} | "
            f"Comfort: {sensor.comfort_level()}"
        )

    def temp_alert() -> None:
        """Alert when temperature exceeds threshold."""
        if sensor.temperature() > 28:
            print(f"⚠️ HIGH TEMPERATURE ALERT: {sensor.temperature():.1f}°C!")

    def monitor_status() -> None:
        """Monitor sensor health and report errors."""
        if sensor.sensor_status() == "ERROR":
            print("🚨 SENSOR ERROR DETECTED!")

    def control_climate() -> None:
        """Simulated climate control system actions."""
        if sensor.comfort_level() == "COMFORTABLE":
            return

        temp = sensor.temperature()
        if temp > 26:
            action = "COOLING"
        elif temp < 18:
            action = "HEATING"
        else:
            action = "IDLE"

        print(f"🔄 HVAC ACTION: {action}")

    # Create effects with named functions
    _log_sensor_eff = effect(log_sensor)
    _temp_alert_eff = effect(temp_alert)
    _monitor_status_eff = effect(monitor_status)
    _control_climate_eff = effect(control_climate)

    try:
        print("Starting IoT sensor monitoring system...")
        print(
            "All monitoring, alerts, and climate control will react automatically to sensor changes"
        )
        sensor.start_sensor()
        time.sleep(15)  # Run for 15 seconds
    except KeyboardInterrupt:
        print("\nDemo interrupted")
    finally:
        sensor.stop_sensor()
        print("Demo completed")


if __name__ == "__main__":
    demo()
