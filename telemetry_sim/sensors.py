"""Virtual sensor nodes: temperature, humidity, piezoelectric harvester.

Physical model notes
--------------------
Temperature / humidity use a diurnal sinusoid plus Gaussian noise, a common
first-order approximation for indoor/outdoor environmental sensing. Values
are clamped to physically plausible ranges for inhabited spaces.

Piezoelectric footstep harvester
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Model (linear piezoelectric constitutive relation, stress-charge form):

    Q = d33 * F          [coulombs]
    V = Q / Cp           [volts]
    E = 0.5 * Cp * V^2 = Q^2 / (2 * Cp)   [joules]

where
  - d33 is the longitudinal piezoelectric charge coefficient [C/N].
    Typical PZT-5H ceramic: d33 ~ 593 pC/N; PZT-5A: ~374 pC/N;
    PVDF film: ~ -33 pC/N. We default to 300 pC/N, a conservative
    mid-range value for a PZT disc under a floor tile.
  - F is the compressive force of one footstep [N]. A 70 kg person
    exerts ~686 N static weight (m*g, g=9.81 m/s^2); dynamic heel-strike
    peaks are 1.0-1.5x body weight. Default 700 N.
  - Cp is the piezo element capacitance [F]. A 20 mm PZT disc is
    typically 5-30 nF. Default 10 nF.

With defaults: Q = 300e-12 * 700 = 210 nC, V = 21 V,
E = 2.2 uJ per step (per element). Real floor tiles use arrays of
elements and rectifier/storage losses; an array multiplier and an
efficiency factor (0-1) are exposed so users can scale to their tile.
Accumulated energy is tracked with optional leakage (self-discharge)
toward zero between steps.

References for ranges: standard PZT material datasheets (e.g. APC
International PZT-5A/5H properties) and the piezoelectric constitutive
equations as in IEEE Std 176.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


@dataclass
class Reading:
    """One sensor sample."""
    sensor_id: str
    timestamp: float          # seconds since simulation start
    topic: str
    value: float
    unit: str
    extra: dict = field(default_factory=dict)


class TemperatureSensor:
    """Ambient temperature with diurnal cycle + noise. Unit: degrees Celsius."""

    def __init__(self, sensor_id: str = "temp-01", base_c: float = 27.0,
                 amplitude_c: float = 3.0, period_s: float = 86400.0,
                 noise_std: float = 0.15, seed: int | None = None):
        self.sensor_id = sensor_id
        self.base_c = base_c
        self.amplitude_c = amplitude_c
        self.period_s = period_s
        self.noise_std = noise_std
        self._rng = random.Random(seed)
        self.topic = f"sensors/{sensor_id}/temperature"

    def sample(self, t: float) -> Reading:
        diurnal = self.amplitude_c * math.sin(2.0 * math.pi * t / self.period_s)
        value = self.base_c + diurnal + self._rng.gauss(0.0, self.noise_std)
        value = max(-10.0, min(50.0, value))
        return Reading(self.sensor_id, t, self.topic, round(value, 3), "degC")


class HumiditySensor:
    """Relative humidity with diurnal cycle (anti-correlated with temp). Unit: %RH."""

    def __init__(self, sensor_id: str = "hum-01", base_pct: float = 65.0,
                 amplitude_pct: float = 10.0, period_s: float = 86400.0,
                 noise_std: float = 1.0, seed: int | None = None):
        self.sensor_id = sensor_id
        self.base_pct = base_pct
        self.amplitude_pct = amplitude_pct
        self.period_s = period_s
        self.noise_std = noise_std
        self._rng = random.Random(seed)
        self.topic = f"sensors/{sensor_id}/humidity"

    def sample(self, t: float) -> Reading:
        # Humidity typically peaks when temperature is lowest -> phase shift pi.
        diurnal = self.amplitude_pct * math.sin(2.0 * math.pi * t / self.period_s + math.pi)
        value = self.base_pct + diurnal + self._rng.gauss(0.0, self.noise_std)
        value = max(5.0, min(100.0, value))
        return Reading(self.sensor_id, t, self.topic, round(value, 2), "%RH")


class PiezoHarvester:
    """Piezoelectric footstep energy harvester. See module docstring for model.

    Each `step()` call represents one footstep on the tile. The harvester
    reports instantaneous voltage and accumulated stored energy.
    """

    def __init__(self, sensor_id: str = "piezo-01",
                 d33: float = 300e-12,        # C/N, PZT mid-range
                 capacitance_f: float = 10e-9,  # F, single PZT disc
                 force_n: float = 700.0,      # N per footstep (~70 kg person)
                 num_elements: int = 8,       # discs wired in parallel per tile
                 efficiency: float = 0.7,     # rectifier + storage efficiency
                 leakage_per_s: float = 0.001,  # fraction of stored energy lost / s
                 seed: int | None = None):
        if not (0.0 < efficiency <= 1.0):
            raise ValueError("efficiency must be in (0, 1]")
        if capacitance_f <= 0 or d33 <= 0 or force_n <= 0 or num_elements < 1:
            raise ValueError("physical parameters must be positive")
        self.sensor_id = sensor_id
        self.d33 = d33
        self.capacitance_f = capacitance_f
        self.force_n = force_n
        self.num_elements = num_elements
        self.efficiency = efficiency
        self.leakage_per_s = leakage_per_s
        self._rng = random.Random(seed)
        self.topic = f"sensors/{sensor_id}/energy"
        self.voltage_topic = f"sensors/{sensor_id}/voltage"
        self._stored_j = 0.0
        self._last_t: float | None = None
        self.total_steps = 0
        self.total_generated_j = 0.0

    # -- physics -----------------------------------------------------------
    def charge_per_step(self, force_n: float | None = None) -> float:
        """Charge generated by one footstep across all elements [C]."""
        f = self.force_n if force_n is None else force_n
        return self.d33 * f * self.num_elements

    def voltage_per_step(self, force_n: float | None = None) -> float:
        """Open-circuit voltage of one element for one footstep [V].

        Elements in parallel share the same voltage, so voltage does not
        scale with element count; charge and energy do.
        """
        f = self.force_n if force_n is None else force_n
        q_one = self.d33 * f
        return q_one / self.capacitance_f

    def energy_per_step(self, force_n: float | None = None) -> float:
        """Usable stored energy from one footstep [J] (after efficiency)."""
        q_total = self.charge_per_step(force_n)
        c_total = self.capacitance_f * self.num_elements
        e_raw = q_total ** 2 / (2.0 * c_total)
        return e_raw * self.efficiency

    # -- simulation --------------------------------------------------------
    def step(self, t: float, force_n: float | None = None) -> Reading:
        """Register one footstep at time t; returns the energy reading."""
        if self._last_t is not None and t > self._last_t:
            dt = t - self._last_t
            self._stored_j *= max(0.0, 1.0 - self.leakage_per_s * dt)
        self._last_t = t
        # Small force variation per step (+/-10%) for realism.
        f = force_n if force_n is not None else self.force_n * self._rng.uniform(0.9, 1.1)
        e = self.energy_per_step(f)
        self._stored_j += e
        self.total_generated_j += e
        self.total_steps += 1
        return Reading(
            self.sensor_id, t, self.topic, self._stored_j, "J",
            extra={
                "voltage_v": round(self.voltage_per_step(f), 4),
                "charge_c": self.charge_per_step(f),
                "energy_this_step_j": e,
                "total_steps": self.total_steps,
                "total_generated_j": self.total_generated_j,
            },
        )

    @property
    def stored_j(self) -> float:
        return self._stored_j

    def sample(self, t: float) -> Reading:
        """Sample current stored energy without a footstep (applies leakage)."""
        if self._last_t is not None and t > self._last_t:
            dt = t - self._last_t
            self._stored_j *= max(0.0, 1.0 - self.leakage_per_s * dt)
        self._last_t = t
        return Reading(self.sensor_id, t, self.topic, self._stored_j, "J",
                       extra={"total_steps": self.total_steps})
