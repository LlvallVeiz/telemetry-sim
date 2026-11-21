"""telemetry_sim — IoT sensor-telemetry simulator.

Simulates temperature, humidity and piezoelectric footstep energy-harvester
nodes publishing over an in-process MQTT-style pub/sub bus, with a time-series
ring buffer, threshold alerts and matplotlib plotting.
"""

__version__ = "1.0.0"
__all__ = ["sensors", "bus", "buffer", "alerts", "cli"]
