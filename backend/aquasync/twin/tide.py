"""Tidal backwater - why the sea decides when you are allowed to release.

The lower Periyar is tide-affected from roughly Aluva to the Kochi
backwaters. At high tide the sea holds the river mouth up, the water-surface
slope flattens, and the same discharge produces a *higher* stage upstream. A
release that is perfectly safe at low tide can overtop banks at high tide.

The practical consequence is the whole point of the project: there is a
recurring, predictable, free window roughly twice a day when a given volume
can be moved downstream at materially lower flood cost. Finding and using
those windows is the "golden window" the optimiser searches for.

Tide is predicted here from harmonic constituents. Real deployment should
pull INCOIS predictions for the Kochi port station; the harmonic model is
the offline fallback and the thing that keeps the demo running without
network access.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Dominant harmonic constituents for the Kochi / Cochin port station.
# Amplitudes in metres, periods in hours, phases in degrees.
# Cochin is microtidal and mixed semi-diurnal: spring range is only about
# 1 m, but on a river already at bankfull, 1 m is decisive.
KOCHI_CONSTITUENTS = [
    # name,  amplitude_m, period_h, phase_deg
    ("M2", 0.36, 12.4206, 0.0),     # principal lunar semi-diurnal
    ("S2", 0.14, 12.0000, 25.0),    # principal solar semi-diurnal
    ("K1", 0.10, 23.9345, 300.0),   # lunisolar diurnal
    ("O1", 0.05, 25.8193, 285.0),   # principal lunar diurnal
    ("N2", 0.07, 12.6583, 340.0),   # larger lunar elliptic
]

MEAN_SEA_LEVEL_M = 0.0


@dataclass
class TidePredictor:
    """Harmonic tide prediction at the river mouth."""

    constituents: list[tuple[str, float, float, float]] = None
    datum_m: float = MEAN_SEA_LEVEL_M

    def __post_init__(self) -> None:
        if self.constituents is None:
            self.constituents = list(KOCHI_CONSTITUENTS)

    def level(self, hours_from_epoch) -> np.ndarray:
        """Tidal elevation above datum at the given hours."""
        t = np.atleast_1d(np.asarray(hours_from_epoch, dtype=float))
        total = np.full_like(t, self.datum_m)
        for _name, amp, period, phase_deg in self.constituents:
            total += amp * np.cos(2 * np.pi * t / period - np.radians(phase_deg))
        return total

    def spring_range(self) -> float:
        """Approximate spring tidal range (M2 + S2 doubled)."""
        m2 = next(c[1] for c in self.constituents if c[0] == "M2")
        s2 = next(c[1] for c in self.constituents if c[0] == "S2")
        return 2.0 * (m2 + s2)

    def low_tide_windows(
        self,
        horizon_hours: int = 72,
        start_hour: float = 0.0,
        threshold_quantile: float = 0.35,
    ) -> list[tuple[int, int]]:
        """Contiguous hour ranges where tide sits in its lowest band.

        Returns a list of ``(start_hour, end_hour)`` half-open intervals,
        relative to ``start_hour``. These are the discharge opportunities.
        """
        t = np.arange(start_hour, start_hour + horizon_hours, 1.0)
        levels = self.level(t)
        cutoff = float(np.quantile(levels, threshold_quantile))

        windows: list[tuple[int, int]] = []
        in_window = False
        w_start = 0
        for i, lv in enumerate(levels):
            if lv <= cutoff and not in_window:
                in_window, w_start = True, i
            elif lv > cutoff and in_window:
                in_window = False
                windows.append((w_start, i))
        if in_window:
            windows.append((w_start, len(levels)))
        return windows


class TidalBackwaterModel:
    """Adjusts downstream stage for the tide holding the mouth up.

    A full treatment solves the 1D Saint-Venant equations for the backwater
    profile. That is the right long-term answer and is tracked as a roadmap
    item. What is implemented here is the standard exponential decay
    approximation: the tidal influence on stage is full at the mouth and
    decays upstream with distance, on a length scale set by the reach slope
    and the flow.

        dh(x) = tide_level * exp(-x / L)

    with L the tidal intrusion length. Higher river discharge pushes the
    tide back toward the sea, so L shrinks as Q rises. That interaction -
    a big release partly defends against its own backwater - is real and
    worth keeping even in the simple model.
    """

    def __init__(
        self,
        intrusion_length_km_at_low_flow: float = 24.0,
        reference_discharge: float = 300.0,
    ) -> None:
        self.l0 = intrusion_length_km_at_low_flow
        self.q_ref = reference_discharge

    def intrusion_length_km(self, discharge_cumecs: float) -> float:
        """Tidal intrusion length shrinks as river discharge grows."""
        q = max(discharge_cumecs, 1.0)
        return float(self.l0 / np.sqrt(1.0 + q / self.q_ref))

    def stage_increment(
        self,
        tide_level_m,
        distance_from_mouth_km: float,
        discharge_cumecs,
    ) -> np.ndarray:
        """Extra stage (metres) at a point, caused by the tide."""
        tide = np.atleast_1d(np.asarray(tide_level_m, dtype=float))
        q = np.atleast_1d(np.asarray(discharge_cumecs, dtype=float))
        q = np.broadcast_to(q, tide.shape)

        lengths = np.array([self.intrusion_length_km(float(v)) for v in q])
        return tide * np.exp(-distance_from_mouth_km / lengths)

    def effective_conveyance(
        self,
        bankfull_cumecs: float,
        tide_level_m,
        distance_from_mouth_km: float,
        stage_discharge_exponent: float = 1.6,
        bankfull_depth_m: float = 6.0,
    ) -> np.ndarray:
        """How much discharge the reach can still carry, given the tide.

        Treating the reach with a power-law stage-discharge relation
        Q ~ h^b, a tidal stage rise of dh eats into the freeboard and
        reduces the discharge the channel can pass before overtopping:

            Q_safe(tide) = Q_bankfull * ((H - dh) / H)^b

        This is the number the optimiser actually cares about. When the
        tide is high, the safe release drops; when it is low, the river
        will accept far more water for free.
        """
        dh = self.stage_increment(tide_level_m, distance_from_mouth_km, bankfull_cumecs)
        remaining = np.clip((bankfull_depth_m - dh) / bankfull_depth_m, 0.05, 1.0)
        return bankfull_cumecs * remaining ** stage_discharge_exponent
