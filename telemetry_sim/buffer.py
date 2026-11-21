"""Fixed-capacity time-series ring buffer with CSV export."""

from __future__ import annotations

import csv
from collections import deque
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Sample:
    timestamp: float
    topic: str
    value: float
    unit: str = ""


class RingBuffer:
    """Time-series ring buffer: once full, the oldest sample is evicted."""

    def __init__(self, capacity: int = 1000):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self._data: deque[Sample] = deque(maxlen=capacity)
        self.evicted = 0

    def append(self, sample: Sample) -> None:
        if len(self._data) == self.capacity:
            self.evicted += 1
        self._data.append(sample)

    def extend(self, samples) -> None:
        for s in samples:
            self.append(s)

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    def samples(self) -> list[Sample]:
        return list(self._data)

    def by_topic(self, topic: str) -> list[Sample]:
        return [s for s in self._data if s.topic == topic]

    def topics(self) -> list[str]:
        return sorted({s.topic for s in self._data})

    def latest(self, topic: str) -> Sample | None:
        for s in reversed(self._data):
            if s.topic == topic:
                return s
        return None

    def clear(self) -> None:
        self._data.clear()
        self.evicted = 0

    def export_csv(self, path: str | Path) -> Path:
        """Write all buffered samples to CSV; returns the path written."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["timestamp", "topic", "value", "unit"])
            for s in self._data:
                writer.writerow([s.timestamp, s.topic, s.value, s.unit])
        return p
