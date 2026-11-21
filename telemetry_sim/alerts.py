"""Threshold alerts over sensor readings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .bus import topic_matches
from .sensors import Reading


@dataclass
class AlertEvent:
    rule_name: str
    topic: str
    value: float
    threshold: float
    direction: str  # "above" | "below"
    timestamp: float


@dataclass
class ThresholdAlert:
    """Fires when a matching reading crosses a threshold.

    direction="above" fires when value > threshold; "below" when
    value < threshold. With `edge_trigger=True` (default) the alert
    fires only on the crossing edge, not on every sample beyond the
    threshold — the usual behaviour for alarm systems.
    """
    name: str
    topic_filter: str
    threshold: float
    direction: str = "above"
    edge_trigger: bool = True
    callback: Callable[[AlertEvent], None] | None = None
    _active: bool = field(default=False, repr=False)
    fire_count: int = field(default=0, repr=False)

    def __post_init__(self):
        if self.direction not in ("above", "below"):
            raise ValueError("direction must be 'above' or 'below'")

    def _breached(self, value: float) -> bool:
        return value > self.threshold if self.direction == "above" else value < self.threshold

    def evaluate(self, reading: Reading) -> AlertEvent | None:
        if not topic_matches(self.topic_filter, reading.topic):
            return None
        breached = self._breached(reading.value)
        should_fire = breached and (not self.edge_trigger or not self._active)
        self._active = breached
        if not should_fire:
            return None
        self.fire_count += 1
        event = AlertEvent(self.name, reading.topic, reading.value,
                           self.threshold, self.direction, reading.timestamp)
        if self.callback is not None:
            self.callback(event)
        return event


class AlertEngine:
    """Evaluates a set of threshold rules against incoming readings."""

    def __init__(self, rules: list[ThresholdAlert] | None = None):
        self.rules: list[ThresholdAlert] = list(rules or [])
        self.events: list[AlertEvent] = []

    def add(self, rule: ThresholdAlert) -> None:
        self.rules.append(rule)

    def evaluate(self, reading: Reading) -> list[AlertEvent]:
        fired = []
        for rule in self.rules:
            ev = rule.evaluate(reading)
            if ev is not None:
                self.events.append(ev)
                fired.append(ev)
        return fired

    def bus_handler(self):
        """Return a bus callback that evaluates Reading payloads."""
        def _handler(topic: str, payload: object, qos: int) -> None:
            if isinstance(payload, Reading):
                self.evaluate(payload)
        return _handler
