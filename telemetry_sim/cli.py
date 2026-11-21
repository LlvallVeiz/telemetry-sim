"""Command-line interface: run / topics / export / plot subcommands."""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from .alerts import AlertEngine, ThresholdAlert
from .buffer import RingBuffer, Sample
from .bus import MQTTBus
from .sensors import HumiditySensor, PiezoHarvester, Reading, TemperatureSensor


def build_simulation(seed: int = 42, buffer_capacity: int = 10000):
    """Wire sensors -> bus -> buffer + alerts. Returns (bus, buffer, alerts, sensors)."""
    bus = MQTTBus(seed=seed)
    buffer = RingBuffer(capacity=buffer_capacity)
    alerts = AlertEngine([
        ThresholdAlert("high-temp", "sensors/+/temperature", 30.0, "above"),
        ThresholdAlert("high-humidity", "sensors/+/humidity", 80.0, "above"),
        ThresholdAlert("energy-milestone", "sensors/+/energy", 1e-4, "above"),
    ])
    sensors = {
        "temperature": TemperatureSensor(seed=seed),
        "humidity": HumiditySensor(seed=seed + 1),
        "piezo": PiezoHarvester(seed=seed + 2),
    }

    def to_buffer(topic: str, payload: object, qos: int) -> None:
        if isinstance(payload, Reading):
            buffer.append(Sample(payload.timestamp, payload.topic,
                                 payload.value, payload.unit))

    bus.subscribe("sensors/#", to_buffer, qos=1)
    bus.subscribe("sensors/#", alerts.bus_handler(), qos=0)
    return bus, buffer, alerts, sensors


def run_simulation(steps: int = 100, dt: float = 1.0, seed: int = 42,
                   footstep_prob: float = 0.3, buffer_capacity: int = 10000):
    """Run the simulation for `steps` ticks; returns (bus, buffer, alerts, sensors)."""
    bus, buffer, alerts, sensors = build_simulation(seed, buffer_capacity)
    rng = random.Random(seed + 99)
    piezo: PiezoHarvester = sensors["piezo"]  # type: ignore[assignment]
    for i in range(steps):
        t = i * dt
        for key in ("temperature", "humidity"):
            reading = sensors[key].sample(t)  # type: ignore[attr-defined]
            bus.publish(reading.topic, reading, qos=1, retain=True)
        if rng.random() < footstep_prob:
            reading = piezo.step(t)
            bus.publish(reading.topic, reading, qos=1, retain=True)
        else:
            reading = piezo.sample(t)
            bus.publish(reading.topic, reading, qos=0)
    return bus, buffer, alerts, sensors


def summarize(bus: MQTTBus, buffer: RingBuffer, alerts: AlertEngine, sensors) -> str:
    piezo: PiezoHarvester = sensors["piezo"]  # type: ignore[assignment]
    lines = [
        "=== telemetry-sim summary ===",
        f"messages published : {bus.stats.published}",
        f"messages delivered : {bus.stats.delivered}",
        f"messages dropped   : {bus.stats.dropped} (retries: {bus.stats.retries})",
        f"buffered samples   : {len(buffer)} (evicted: {buffer.evicted})",
        f"alerts fired       : {len(alerts.events)}",
        f"footsteps          : {piezo.total_steps}",
        f"energy generated   : {piezo.total_generated_j:.6e} J",
        f"energy stored      : {piezo.stored_j:.6e} J",
        f"topics             : {', '.join(buffer.topics())}",
    ]
    for ev in alerts.events[:10]:
        lines.append(f"  ALERT {ev.rule_name}: {ev.topic}={ev.value:.4g} "
                     f"({ev.direction} {ev.threshold:g}) @ t={ev.timestamp:g}s")
    return "\n".join(lines)


def make_plot(buffer: RingBuffer, out: str | Path) -> Path:
    """Save a matplotlib time-series plot (one subplot per topic) to PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    topics = buffer.topics()
    if not topics:
        raise ValueError("no samples to plot")
    fig, axes = plt.subplots(len(topics), 1, figsize=(10, 2.6 * len(topics)),
                             sharex=True, squeeze=False)
    for ax, topic in zip(axes[:, 0], topics):
        samples = buffer.by_topic(topic)
        xs = [s.timestamp for s in samples]
        ys = [s.value for s in samples]
        ax.plot(xs, ys, linewidth=1.2)
        ax.set_ylabel(samples[0].unit or "value")
        ax.set_title(topic, fontsize=10, loc="left")
        ax.grid(True, alpha=0.3)
    axes[-1, 0].set_xlabel("time (s)")
    fig.tight_layout()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120)
    plt.close(fig)
    return out


# -- subcommands -----------------------------------------------------------
def cmd_run(args) -> int:
    bus, buffer, alerts, sensors = run_simulation(
        steps=args.steps, dt=args.dt, seed=args.seed)
    print(summarize(bus, buffer, alerts, sensors))
    return 0


def cmd_topics(args) -> int:
    bus, buffer, alerts, sensors = run_simulation(
        steps=args.steps, dt=args.dt, seed=args.seed)
    print("Topics (topic : samples : latest value):")
    for topic in buffer.topics():
        latest = buffer.latest(topic)
        print(f"  {topic} : {len(buffer.by_topic(topic))} : "
              f"{latest.value:.6g} {latest.unit}" if latest else f"  {topic} : 0")
    print(f"Retained topics: {', '.join(bus.retained_topics())}")
    print(f"Total messages published: {bus.stats.published}")
    return 0


def cmd_export(args) -> int:
    bus, buffer, alerts, sensors = run_simulation(
        steps=args.steps, dt=args.dt, seed=args.seed)
    path = buffer.export_csv(args.output)
    print(f"Wrote {len(buffer)} samples to {path}")
    return 0


def cmd_plot(args) -> int:
    bus, buffer, alerts, sensors = run_simulation(
        steps=args.steps, dt=args.dt, seed=args.seed)
    path = make_plot(buffer, args.output)
    print(f"Wrote plot ({len(buffer.topics())} topics, {len(buffer)} samples) to {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="telemetry-sim",
                                description="IoT sensor-telemetry simulator")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("--steps", type=int, default=100, help="simulation ticks")
        sp.add_argument("--dt", type=float, default=1.0, help="seconds per tick")
        sp.add_argument("--seed", type=int, default=42, help="RNG seed")

    sp = sub.add_parser("run", help="simulate N steps and print a summary")
    common(sp); sp.set_defaults(func=cmd_run)
    sp = sub.add_parser("topics", help="list topics and message counts")
    common(sp); sp.set_defaults(func=cmd_topics)
    sp = sub.add_parser("export", help="write buffered samples to CSV")
    common(sp); sp.add_argument("--output", default="telemetry.csv")
    sp.set_defaults(func=cmd_export)
    sp = sub.add_parser("plot", help="save a matplotlib time-series PNG")
    common(sp); sp.add_argument("--output", default="telemetry.png")
    sp.set_defaults(func=cmd_plot)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
