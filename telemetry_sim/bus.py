"""In-process MQTT-style publish/subscribe bus.

Implements the subset of MQTT 3.1.1 semantics needed for simulation:
  - Topic filters with wildcards: '+' matches exactly one level,
    '#' matches all remaining levels (must be the final level).
  - QoS 0: fire-and-forget (at most once). A simulated drop loses the message.
  - QoS 1: at-least-once. On a simulated drop the bus retries delivery
    up to `max_retries` times, so subscribers may receive duplicates.
  - Retained messages: the last retained payload per topic is replayed
    immediately to every new matching subscriber.

Drops are simulated deterministically for testability: `drop_next(n)`
forces the next n delivery attempts to fail, and `drop_rate` (with a
seeded RNG) drops attempts probabilistically.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable

Callback = Callable[[str, object, int], None]  # (topic, payload, qos)


def topic_matches(filter_: str, topic: str) -> bool:
    """Return True if MQTT topic filter `filter_` matches `topic`."""
    f_parts = filter_.split("/")
    t_parts = topic.split("/")
    for i, fp in enumerate(f_parts):
        if fp == "#":
            return i == len(f_parts) - 1  # '#' only valid as final level
        if i >= len(t_parts):
            return False
        if fp != "+" and fp != t_parts[i]:
            return False
    return len(f_parts) == len(t_parts)


@dataclass
class _Subscription:
    filter_: str
    callback: Callback
    qos: int


@dataclass
class Message:
    topic: str
    payload: object
    qos: int = 0
    retain: bool = False


@dataclass
class BusStats:
    published: int = 0
    delivered: int = 0
    dropped: int = 0
    retries: int = 0
    retained_replayed: int = 0


class MQTTBus:
    """Synchronous in-process pub/sub bus with MQTT-style semantics."""

    def __init__(self, max_retries: int = 3, drop_rate: float = 0.0,
                 seed: int | None = None):
        self.max_retries = max_retries
        self.drop_rate = drop_rate
        self._rng = random.Random(seed)
        self._subs: list[_Subscription] = []
        self._retained: dict[str, Message] = {}
        self._forced_drops = 0
        self.stats = BusStats()
        self.history: list[Message] = []

    # -- test hooks --------------------------------------------------------
    def drop_next(self, n: int = 1) -> None:
        """Force the next n delivery attempts to be dropped."""
        self._forced_drops += n

    def _should_drop(self) -> bool:
        if self._forced_drops > 0:
            self._forced_drops -= 1
            return True
        return self.drop_rate > 0.0 and self._rng.random() < self.drop_rate

    # -- pub/sub -----------------------------------------------------------
    def subscribe(self, filter_: str, callback: Callback, qos: int = 0) -> None:
        if qos not in (0, 1):
            raise ValueError("qos must be 0 or 1")
        self._subs.append(_Subscription(filter_, callback, qos))
        # Replay retained messages matching the new subscription.
        for msg in list(self._retained.values()):
            if topic_matches(filter_, msg.topic):
                callback(msg.topic, msg.payload, msg.qos)
                self.stats.retained_replayed += 1
                self.stats.delivered += 1

    def unsubscribe(self, callback: Callback) -> int:
        before = len(self._subs)
        self._subs = [s for s in self._subs if s.callback is not callback]
        return before - len(self._subs)

    def publish(self, topic: str, payload: object, qos: int = 0,
                retain: bool = False) -> int:
        """Publish a message; returns the number of successful deliveries."""
        if qos not in (0, 1):
            raise ValueError("qos must be 0 or 1")
        if "+" in topic or "#" in topic:
            raise ValueError("publish topic must not contain wildcards")
        msg = Message(topic, payload, qos, retain)
        self.history.append(msg)
        self.stats.published += 1
        if retain:
            self._retained[topic] = msg
        deliveries = 0
        for sub in list(self._subs):
            if not topic_matches(sub.filter_, topic):
                continue
            effective_qos = min(qos, sub.qos) if sub.qos else qos
            # Deliver at the higher guarantee requested by either side:
            # a QoS1 subscriber gets retries even for QoS0 publishes in
            # this simulator, matching "at-least-once if either asks".
            effective_qos = max(qos, sub.qos)
            if self._deliver(sub, msg, effective_qos):
                deliveries += 1
        return deliveries

    def _deliver(self, sub: _Subscription, msg: Message, qos: int) -> bool:
        attempts = 1 + (self.max_retries if qos == 1 else 0)
        for attempt in range(attempts):
            if self._should_drop():
                self.stats.dropped += 1
                if attempt < attempts - 1:
                    self.stats.retries += 1
                continue
            sub.callback(msg.topic, msg.payload, qos)
            self.stats.delivered += 1
            return True
        return False

    # -- introspection -----------------------------------------------------
    def topics(self) -> list[str]:
        """Distinct topics seen so far, sorted."""
        return sorted({m.topic for m in self.history})

    def retained_topics(self) -> list[str]:
        return sorted(self._retained.keys())
