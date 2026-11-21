# telemetry-sim

IoT sensor-telemetry simulator built from scratch in Python. Virtual sensor
nodes (temperature, humidity, and a piezoelectric footstep energy harvester)
publish readings over an in-process MQTT-style pub/sub bus into a time-series
ring buffer, with threshold alerts, CSV export, and matplotlib plots.

## What it does

- **Virtual sensor nodes**
  - `TemperatureSensor` — ambient temperature (°C) with a diurnal sinusoid + Gaussian noise.
  - `HumiditySensor` — relative humidity (%RH), anti-correlated with temperature.
  - `PiezoHarvester` — piezoelectric footstep energy-harvester tile (see model below).
- **MQTT-style pub/sub bus** (`MQTTBus`)
  - Topic filters with wildcards: `+` (single level) and `#` (multi-level).
  - QoS 0 (fire-and-forget) and QoS 1 (at-least-once with retry on simulated drop).
  - Retained messages replayed immediately to new subscribers.
- **Time-series ring buffer** — fixed capacity, oldest samples evicted, CSV export.
- **Threshold alerts** — configurable rules (above/below, edge- or level-triggered).
- **CLI** with `run`, `topics`, `export`, and `plot` subcommands.
- **matplotlib time-series plots** saved as PNG (one subplot per topic).

## Piezoelectric model (units & assumptions)

Linear piezoelectric constitutive relation (stress-charge form, IEEE Std 176):

```
Q = d33 * F                    [C]   charge per footstep
V = Q / Cp                     [V]   open-circuit voltage
E = 0.5 * Cp * V^2 = Q^2/(2Cp) [J]   stored energy
```

| Parameter | Default | Basis |
|---|---|---|
| `d33` | 300 pC/N | Mid-range PZT ceramic (PZT-5A ≈ 374 pC/N, PZT-5H ≈ 593 pC/N; PVDF film ≈ −33 pC/N) |
| `Cp` | 10 nF | Typical 20 mm PZT disc (5–30 nF range) |
| `F` | 700 N | ~70 kg person (m·g, g = 9.81 m/s²); heel-strike peaks 1.0–1.5× body weight |
| elements | 8 in parallel | Charge/energy scale with element count; voltage does not |
| efficiency | 0.7 | Rectifier + storage losses |
| leakage | 0.1 %/s | Capacitor self-discharge between steps |

With defaults, one footstep yields Q ≈ 1.68 µC (8 elements), V ≈ 21 V per
element, E ≈ 12 µJ stored. All parameters are configurable in
`PiezoHarvester(...)`. Per-step force varies ±10 % for realism.

## Architecture

```
sensors.py          TemperatureSensor / HumiditySensor / PiezoHarvester
      │  Reading(topic, value, unit, timestamp)
      ▼
bus.py              MQTTBus: wildcards, QoS 0/1 + retry, retained messages
      │
      ├──► buffer.py   RingBuffer (fixed capacity, eviction) → CSV export
      └──► alerts.py   AlertEngine / ThresholdAlert (edge/level triggered)
cli.py              run / topics / export / plot subcommands + plotting
```

Topics used: `sensors/temp-01/temperature`, `sensors/hum-01/humidity`,
`sensors/piezo-01/energy`.

## Requirements

- Python 3.12
- `numpy >= 1.26`, `matplotlib >= 3.6` (see `requirements.txt`)
- Tests use only the standard-library `unittest`.

## Build / run

```bash
pip install -r requirements.txt

# Simulate 200 ticks (1 s each) and print a summary
python3 -m telemetry_sim run --steps 200

# List topics, sample counts and latest values
python3 -m telemetry_sim topics --steps 200

# Export buffered samples to CSV
python3 -m telemetry_sim export --steps 500 --output telemetry.csv

# Save a time-series plot (PNG)
python3 -m telemetry_sim plot --steps 500 --output telemetry.png
```

Options shared by all subcommands: `--steps N`, `--dt SECONDS`, `--seed INT`
(fixed seed = deterministic run).

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Coverage: pub/sub delivery + wildcard matching, QoS 1 retry after simulated
drops, retained-message replay, ring-buffer eviction + CSV export, piezo
energy-model bounds (non-negative, monotonic in steps, physically bounded,
force scaling, leakage), alert firing/non-firing and edge behaviour, and an
end-to-end pipeline + CLI integration test.

## Project layout

```
telemetry_sim/
  __init__.py
  __main__.py     # python -m telemetry_sim
  sensors.py      # sensor nodes + piezo physics
  bus.py          # MQTT-style pub/sub bus
  buffer.py       # ring buffer + CSV export
  alerts.py       # threshold alerts
  cli.py          # CLI + simulation wiring + plotting
tests/
  test_bus.py  test_buffer.py  test_sensors.py  test_alerts.py  test_cli.py
requirements.txt
README.md
```
