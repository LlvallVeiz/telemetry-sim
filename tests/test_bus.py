"""Tests for the MQTT-style bus: delivery, wildcards, QoS 1, retained."""

import unittest

from telemetry_sim.bus import MQTTBus, topic_matches


class TestWildcardMatching(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(topic_matches("sensors/temp-01/temperature",
                                      "sensors/temp-01/temperature"))
        self.assertFalse(topic_matches("sensors/temp-01/temperature",
                                       "sensors/temp-01/humidity"))

    def test_single_level_wildcard(self):
        self.assertTrue(topic_matches("sensors/+/temperature",
                                      "sensors/temp-01/temperature"))
        self.assertFalse(topic_matches("sensors/+/temperature",
                                       "sensors/temp-01/room/temperature"))
        self.assertFalse(topic_matches("sensors/+/temperature",
                                       "sensors/temperature"))

    def test_multi_level_wildcard(self):
        self.assertTrue(topic_matches("sensors/#", "sensors/temp-01/temperature"))
        self.assertTrue(topic_matches("sensors/#", "sensors/a/b/c/d"))
        self.assertFalse(topic_matches("sensors/#", "actuators/light-01/state"))

    def test_hash_must_be_final(self):
        self.assertFalse(topic_matches("sensors/#/temperature",
                                       "sensors/x/temperature"))


class TestPubSubDelivery(unittest.TestCase):
    def test_delivery_to_matching_subscriber(self):
        bus = MQTTBus()
        received = []
        bus.subscribe("sensors/+/temperature",
                      lambda t, p, q: received.append((t, p)))
        n = bus.publish("sensors/temp-01/temperature", 25.5)
        self.assertEqual(n, 1)
        self.assertEqual(received, [("sensors/temp-01/temperature", 25.5)])

    def test_no_delivery_to_nonmatching(self):
        bus = MQTTBus()
        received = []
        bus.subscribe("sensors/+/humidity", lambda t, p, q: received.append(p))
        n = bus.publish("sensors/temp-01/temperature", 25.5)
        self.assertEqual(n, 0)
        self.assertEqual(received, [])

    def test_wildcard_hash_receives_all(self):
        bus = MQTTBus()
        received = []
        bus.subscribe("sensors/#", lambda t, p, q: received.append(t))
        bus.publish("sensors/temp-01/temperature", 1)
        bus.publish("sensors/hum-01/humidity", 2)
        bus.publish("other/topic", 3)
        self.assertEqual(received, ["sensors/temp-01/temperature",
                                    "sensors/hum-01/humidity"])

    def test_publish_topic_rejects_wildcards(self):
        bus = MQTTBus()
        with self.assertRaises(ValueError):
            bus.publish("sensors/+/temperature", 1)


class TestQoS(unittest.TestCase):
    def test_qos0_drop_loses_message(self):
        bus = MQTTBus()
        received = []
        bus.subscribe("a/b", lambda t, p, q: received.append(p), qos=0)
        bus.drop_next(1)
        n = bus.publish("a/b", "x", qos=0)
        self.assertEqual(n, 0)
        self.assertEqual(received, [])
        self.assertEqual(bus.stats.dropped, 1)

    def test_qos1_retry_recovers_from_drop(self):
        bus = MQTTBus(max_retries=3)
        received = []
        bus.subscribe("a/b", lambda t, p, q: received.append(p), qos=1)
        bus.drop_next(2)  # first two attempts fail, third succeeds
        n = bus.publish("a/b", "x", qos=1)
        self.assertEqual(n, 1)
        self.assertEqual(received, ["x"])
        self.assertEqual(bus.stats.retries, 2)

    def test_qos1_gives_up_after_max_retries(self):
        bus = MQTTBus(max_retries=2)
        received = []
        bus.subscribe("a/b", lambda t, p, q: received.append(p), qos=1)
        bus.drop_next(10)
        n = bus.publish("a/b", "x", qos=1)
        self.assertEqual(n, 0)
        self.assertEqual(received, [])


class TestRetained(unittest.TestCase):
    def test_retained_replayed_to_new_subscriber(self):
        bus = MQTTBus()
        bus.publish("sensors/temp-01/temperature", 24.0, retain=True)
        received = []
        bus.subscribe("sensors/+/temperature",
                      lambda t, p, q: received.append((t, p)))
        self.assertEqual(received, [("sensors/temp-01/temperature", 24.0)])
        self.assertEqual(bus.stats.retained_replayed, 1)

    def test_non_retained_not_replayed(self):
        bus = MQTTBus()
        bus.publish("sensors/temp-01/temperature", 24.0, retain=False)
        received = []
        bus.subscribe("sensors/#", lambda t, p, q: received.append(p))
        self.assertEqual(received, [])

    def test_retained_latest_wins(self):
        bus = MQTTBus()
        bus.publish("a/b", 1, retain=True)
        bus.publish("a/b", 2, retain=True)
        received = []
        bus.subscribe("a/b", lambda t, p, q: received.append(p))
        self.assertEqual(received, [2])


if __name__ == "__main__":
    unittest.main()
