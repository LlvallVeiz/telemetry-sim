"""Tests for threshold alerts: firing, non-firing, edge behaviour."""

import unittest

from telemetry_sim.alerts import AlertEngine, ThresholdAlert
from telemetry_sim.sensors import Reading


def reading(value, topic="sensors/temp-01/temperature", t=0.0):
    return Reading("temp-01", t, topic, value, "degC")


class TestThresholdAlert(unittest.TestCase):
    def test_fires_above_threshold(self):
        a = ThresholdAlert("hot", "sensors/+/temperature", 30.0, "above")
        ev = a.evaluate(reading(31.5))
        self.assertIsNotNone(ev)
        self.assertEqual(ev.value, 31.5)
        self.assertEqual(a.fire_count, 1)

    def test_does_not_fire_below_threshold(self):
        a = ThresholdAlert("hot", "sensors/+/temperature", 30.0, "above")
        self.assertIsNone(a.evaluate(reading(29.9)))
        self.assertEqual(a.fire_count, 0)

    def test_fires_below_direction(self):
        a = ThresholdAlert("cold", "sensors/+/temperature", 10.0, "below")
        self.assertIsNotNone(a.evaluate(reading(5.0)))
        self.assertIsNone(a.evaluate(reading(15.0)))

    def test_topic_filter_respected(self):
        a = ThresholdAlert("hot", "sensors/+/temperature", 30.0, "above")
        self.assertIsNone(a.evaluate(reading(99.0, topic="sensors/hum-01/humidity")))

    def test_edge_trigger_fires_once_per_crossing(self):
        a = ThresholdAlert("hot", "sensors/+/temperature", 30.0, "above")
        self.assertIsNotNone(a.evaluate(reading(31.0, t=0.0)))
        self.assertIsNone(a.evaluate(reading(32.0, t=1.0)))   # still above
        self.assertIsNone(a.evaluate(reading(20.0, t=2.0)))   # back below
        self.assertIsNotNone(a.evaluate(reading(33.0, t=3.0)))  # new crossing
        self.assertEqual(a.fire_count, 2)

    def test_level_trigger_fires_every_sample(self):
        a = ThresholdAlert("hot", "sensors/+/temperature", 30.0, "above",
                           edge_trigger=False)
        self.assertIsNotNone(a.evaluate(reading(31.0, t=0.0)))
        self.assertIsNotNone(a.evaluate(reading(32.0, t=1.0)))
        self.assertEqual(a.fire_count, 2)

    def test_callback_invoked(self):
        seen = []
        a = ThresholdAlert("hot", "sensors/+/temperature", 30.0, "above",
                           callback=seen.append)
        a.evaluate(reading(40.0))
        self.assertEqual(len(seen), 1)


class TestAlertEngine(unittest.TestCase):
    def test_engine_collects_events(self):
        eng = AlertEngine([
            ThresholdAlert("hot", "sensors/+/temperature", 30.0, "above"),
            ThresholdAlert("dry", "sensors/+/humidity", 20.0, "below"),
        ])
        fired = eng.evaluate(reading(35.0))
        self.assertEqual(len(fired), 1)
        fired = eng.evaluate(Reading("hum-01", 1.0, "sensors/hum-01/humidity",
                                     10.0, "%RH"))
        self.assertEqual(len(fired), 1)
        self.assertEqual(len(eng.events), 2)


if __name__ == "__main__":
    unittest.main()
