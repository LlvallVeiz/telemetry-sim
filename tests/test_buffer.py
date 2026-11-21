"""Tests for the time-series ring buffer and CSV export."""

import csv
import tempfile
import unittest
from pathlib import Path

from telemetry_sim.buffer import RingBuffer, Sample


class TestRingBuffer(unittest.TestCase):
    def test_append_and_len(self):
        buf = RingBuffer(capacity=3)
        buf.append(Sample(0.0, "a/b", 1.0, "V"))
        buf.append(Sample(1.0, "a/b", 2.0, "V"))
        self.assertEqual(len(buf), 2)

    def test_eviction_of_oldest(self):
        buf = RingBuffer(capacity=3)
        for i in range(5):
            buf.append(Sample(float(i), "a/b", float(i), "V"))
        self.assertEqual(len(buf), 3)
        self.assertEqual(buf.evicted, 2)
        values = [s.value for s in buf.samples()]
        self.assertEqual(values, [2.0, 3.0, 4.0])  # oldest two gone

    def test_by_topic_and_latest(self):
        buf = RingBuffer(capacity=10)
        buf.append(Sample(0.0, "a/b", 1.0))
        buf.append(Sample(1.0, "a/c", 9.0))
        buf.append(Sample(2.0, "a/b", 3.0))
        self.assertEqual([s.value for s in buf.by_topic("a/b")], [1.0, 3.0])
        self.assertEqual(buf.latest("a/b").value, 3.0)
        self.assertIsNone(buf.latest("no/such"))
        self.assertEqual(buf.topics(), ["a/b", "a/c"])

    def test_invalid_capacity(self):
        with self.assertRaises(ValueError):
            RingBuffer(capacity=0)

    def test_csv_export(self):
        buf = RingBuffer(capacity=10)
        buf.append(Sample(0.0, "sensors/t/temperature", 25.5, "degC"))
        buf.append(Sample(1.0, "sensors/t/temperature", 25.7, "degC"))
        with tempfile.TemporaryDirectory() as d:
            path = buf.export_csv(Path(d) / "out.csv")
            with path.open(newline="", encoding="utf-8") as fh:
                rows = list(csv.reader(fh))
        self.assertEqual(rows[0], ["timestamp", "topic", "value", "unit"])
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1][1], "sensors/t/temperature")
        self.assertEqual(rows[2][3], "degC")


if __name__ == "__main__":
    unittest.main()
