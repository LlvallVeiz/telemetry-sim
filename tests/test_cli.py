"""Integration tests: full simulation pipeline + CLI entry points."""

import tempfile
import unittest
from pathlib import Path

from telemetry_sim.cli import main, make_plot, run_simulation


class TestSimulationPipeline(unittest.TestCase):
    def test_run_produces_samples_on_all_topics(self):
        bus, buffer, alerts, sensors = run_simulation(steps=50, seed=42)
        topics = buffer.topics()
        self.assertIn("sensors/temp-01/temperature", topics)
        self.assertIn("sensors/hum-01/humidity", topics)
        self.assertIn("sensors/piezo-01/energy", topics)
        self.assertGreater(len(buffer), 100)
        self.assertGreater(bus.stats.published, 0)
        self.assertEqual(bus.stats.dropped, 0)

    def test_piezo_generates_energy(self):
        bus, buffer, alerts, sensors = run_simulation(steps=200, seed=42)
        piezo = sensors["piezo"]
        self.assertGreater(piezo.total_steps, 0)
        self.assertGreater(piezo.total_generated_j, 0.0)


class TestCliCommands(unittest.TestCase):
    def test_run_command(self):
        self.assertEqual(main(["run", "--steps", "20"]), 0)

    def test_topics_command(self):
        self.assertEqual(main(["topics", "--steps", "20"]), 0)

    def test_export_command(self):
        with tempfile.TemporaryDirectory() as d:
            out = str(Path(d) / "telemetry.csv")
            self.assertEqual(main(["export", "--steps", "20",
                                   "--output", out]), 0)
            text = Path(out).read_text(encoding="utf-8")
            self.assertIn("timestamp,topic,value,unit", text)

    def test_plot_command(self):
        with tempfile.TemporaryDirectory() as d:
            out = str(Path(d) / "telemetry.png")
            self.assertEqual(main(["plot", "--steps", "20",
                                   "--output", out]), 0)
            data = Path(out).read_bytes()
            self.assertTrue(data.startswith(b"\x89PNG"))  # PNG magic bytes

    def test_make_plot_directly(self):
        bus, buffer, alerts, sensors = run_simulation(steps=30, seed=1)
        with tempfile.TemporaryDirectory() as d:
            path = make_plot(buffer, Path(d) / "p.png")
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
