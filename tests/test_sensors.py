"""Tests for sensor models, especially the piezo energy model bounds."""

import unittest

from telemetry_sim.sensors import (HumiditySensor, PiezoHarvester,
                                   TemperatureSensor)


class TestEnvironmentalSensors(unittest.TestCase):
    def test_temperature_in_plausible_range(self):
        s = TemperatureSensor(seed=1)
        for t in range(0, 10000, 100):
            r = s.sample(float(t))
            self.assertGreaterEqual(r.value, -10.0)
            self.assertLessEqual(r.value, 50.0)
            self.assertEqual(r.unit, "degC")

    def test_humidity_in_plausible_range(self):
        s = HumiditySensor(seed=1)
        for t in range(0, 10000, 100):
            r = s.sample(float(t))
            self.assertGreaterEqual(r.value, 5.0)
            self.assertLessEqual(r.value, 100.0)
            self.assertEqual(r.unit, "%RH")

    def test_deterministic_with_seed(self):
        a = TemperatureSensor(seed=7).sample(100.0).value
        b = TemperatureSensor(seed=7).sample(100.0).value
        self.assertEqual(a, b)


class TestPiezoModel(unittest.TestCase):
    def test_charge_voltage_energy_formulas(self):
        p = PiezoHarvester(d33=300e-12, capacitance_f=10e-9, force_n=700.0,
                           num_elements=1, efficiency=1.0, seed=0)
        q = p.charge_per_step()
        self.assertAlmostEqual(q, 300e-12 * 700.0, places=15)
        v = p.voltage_per_step()
        self.assertAlmostEqual(v, q / 10e-9, places=9)
        e = p.energy_per_step()
        self.assertAlmostEqual(e, 0.5 * 10e-9 * v ** 2, places=15)

    def test_energy_nonnegative(self):
        p = PiezoHarvester(seed=3)
        for i in range(50):
            r = p.step(float(i))
            self.assertGreaterEqual(r.value, 0.0)
            self.assertGreaterEqual(r.extra["energy_this_step_j"], 0.0)

    def test_energy_monotonic_with_steps_no_leakage(self):
        p = PiezoHarvester(leakage_per_s=0.0, seed=5)
        prev = 0.0
        for i in range(30):
            r = p.step(float(i))
            self.assertGreater(r.value, prev)  # strictly increases
            prev = r.value
        self.assertEqual(p.total_steps, 30)

    def test_energy_within_physical_bounds(self):
        # One footstep on a small PZT tile yields microjoules, not joules.
        p = PiezoHarvester(seed=0)
        e = p.energy_per_step()
        self.assertGreater(e, 0.0)
        self.assertLess(e, 1e-3)  # < 1 mJ per step for these parameters
        v = p.voltage_per_step()
        self.assertGreater(v, 0.1)
        self.assertLess(v, 200.0)  # piezo discs: volts to tens of volts

    def test_more_force_more_energy(self):
        p = PiezoHarvester(seed=0)
        self.assertGreater(p.energy_per_step(force_n=900.0),
                           p.energy_per_step(force_n=400.0))

    def test_invalid_parameters_rejected(self):
        with self.assertRaises(ValueError):
            PiezoHarvester(efficiency=1.5)
        with self.assertRaises(ValueError):
            PiezoHarvester(capacitance_f=0.0)

    def test_leakage_reduces_stored_energy(self):
        p = PiezoHarvester(leakage_per_s=0.1, seed=0)
        p.step(0.0)
        stored_after_step = p.stored_j
        p.sample(10.0)  # 10 s of leakage, no new step
        self.assertLess(p.stored_j, stored_after_step)
        self.assertGreaterEqual(p.stored_j, 0.0)


if __name__ == "__main__":
    unittest.main()
