"""Reservoir mass balance - the core state equation of the digital twin.

    dV/dt = Q_in - Q_turbine - Q_spill - Q_evap

Integrated with an explicit Euler step. At an hourly step and the storage
scales involved (Idukki holds 1459 Mm3 live), Euler error is far below the
measurement error of the level gauge, so a higher-order integrator would be
false precision. The step size is validated in tests/test_reservoir.py.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .constants import SECONDS_PER_HOUR, Reservoir


@dataclass
class ReservoirState:
    """Instantaneous state of one reservoir."""

    level: float            # m MSL
    storage: float          # Mm3 live storage
    inflow: float = 0.0     # cumecs
    turbine_flow: float = 0.0
    spill_flow: float = 0.0

    @property
    def total_outflow(self) -> float:
        return self.turbine_flow + self.spill_flow


class LevelStorageCurve:
    """Bidirectional level to live-storage mapping for a reservoir.

    Real reservoirs use a surveyed elevation-capacity table. We do not have
    the surveyed table for Idukki, so we fit a power law

        S(h) = S_frl * ((h - h_dead) / (h_frl - h_dead)) ** beta

    to the (level, liveStorage, storagePercentage) triples that appear in
    every daily KSEB bulletin row. ``fit_from_observations`` recovers beta by
    least squares. Fitted against the 1,836 validated Idukki bulletin rows
    (2020-2026) this gives beta = 1.348, r2 = 0.9957, MAE 17 Mm3 against a
    mean storage of 904 Mm3. Beta above 1 means storage grows faster than
    linearly with height, which is what makes the top two metres of a
    reservoir so disproportionately valuable as flood cushion.

    Fitting on the raw feed instead of the validated subset gives beta =
    1.302 and r2 = 0.784 - the corrupt 2020-21 block alone moves the curve
    by more than the cushion being modelled. See io/kseb_dataset.py.

    Siltation makes the true curve drift downward year on year. Refitting
    against recent bulletin rows is how the twin performs the adaptive
    siltation calibration described in docs/architecture.md.
    """

    def __init__(self, reservoir: Reservoir, beta: float = 1.348) -> None:
        self.res = reservoir
        self.beta = beta

    # -- conversions --------------------------------------------------------

    def storage_from_level(self, level: float) -> float:
        span = self.res.frl - self.res.dead_level
        frac = np.clip((level - self.res.dead_level) / span, 0.0, None)
        return float(self.res.live_storage_at_frl * frac ** self.beta)

    def level_from_storage(self, storage: float) -> float:
        span = self.res.frl - self.res.dead_level
        frac = np.clip(storage / self.res.live_storage_at_frl, 0.0, None)
        return float(self.res.dead_level + span * frac ** (1.0 / self.beta))

    def surface_area_km2(self, level: float) -> float:
        """dV/dh, converted to km2. Used for evaporation and rain-on-lake."""
        span = self.res.frl - self.res.dead_level
        frac = np.clip((level - self.res.dead_level) / span, 1e-6, None)
        dv_dh = (self.res.live_storage_at_frl * self.beta / span) * frac ** (self.beta - 1.0)
        return float(dv_dh)  # Mm3 per m == km2

    # -- calibration --------------------------------------------------------

    def fit_from_observations(self, levels, storages) -> float:
        """Least-squares fit of beta to observed (level, live storage) pairs.

        Returns the fitted beta and stores it on the instance. Rows at or
        below dead level carry no information and are dropped.
        """
        levels = np.asarray(levels, dtype=float)
        storages = np.asarray(storages, dtype=float)

        span = self.res.frl - self.res.dead_level
        frac = (levels - self.res.dead_level) / span
        ratio = storages / self.res.live_storage_at_frl

        ok = (frac > 1e-6) & (ratio > 1e-6) & np.isfinite(frac) & np.isfinite(ratio)
        if ok.sum() < 3:
            raise ValueError("need at least 3 valid observations to fit beta")

        # log(S/S_frl) = beta * log((h - h_dead)/span) -> slope through origin
        x = np.log(frac[ok])
        y = np.log(ratio[ok])
        self.beta = float((x @ y) / (x @ x))
        return self.beta


class ReservoirModel:
    """Steps a single reservoir forward in time under a release schedule."""

    def __init__(self, reservoir: Reservoir, curve: LevelStorageCurve | None = None) -> None:
        self.res = reservoir
        self.curve = curve or LevelStorageCurve(reservoir)

    def step(
        self,
        state: ReservoirState,
        inflow: float,
        turbine_flow: float,
        spill_flow: float,
        dt_seconds: float = SECONDS_PER_HOUR,
        evaporation_mm_day: float = 4.0,
        rain_on_lake_mm: float = 0.0,
    ) -> ReservoirState:
        """Advance the reservoir by one timestep.

        Flows are cumecs and are treated as constant across the step. Returns
        a new state; the input state is not mutated.
        """
        area_km2 = self.curve.surface_area_km2(state.level)

        # mm/day over km2 -> cumecs: mm/day * km2 * 1e3 m3 / 86400 s
        evap_cumecs = evaporation_mm_day * area_km2 * 1e3 / 86_400.0
        rain_cumecs = rain_on_lake_mm * area_km2 * 1e3 / dt_seconds

        net_cumecs = inflow + rain_cumecs - turbine_flow - spill_flow - evap_cumecs

        # cumecs * s -> m3 -> Mm3
        delta_storage = net_cumecs * dt_seconds / 1e6

        storage = max(0.0, state.storage + delta_storage)
        level = self.curve.level_from_storage(storage)

        return ReservoirState(
            level=level,
            storage=storage,
            inflow=inflow,
            turbine_flow=turbine_flow,
            spill_flow=spill_flow,
        )

    def simulate(
        self,
        initial: ReservoirState,
        inflow_series,
        turbine_series,
        spill_series,
        dt_seconds: float = SECONDS_PER_HOUR,
        rain_on_lake_series=None,
        evaporation_mm_day: float = 4.0,
    ) -> list[ReservoirState]:
        """Run a full trajectory. All series must be the same length."""
        inflow_series = np.asarray(inflow_series, dtype=float)
        turbine_series = np.asarray(turbine_series, dtype=float)
        spill_series = np.asarray(spill_series, dtype=float)

        n = len(inflow_series)
        if not (len(turbine_series) == len(spill_series) == n):
            raise ValueError("inflow, turbine and spill series must be equal length")
        if rain_on_lake_series is None:
            rain_on_lake_series = np.zeros(n)
        rain_on_lake_series = np.asarray(rain_on_lake_series, dtype=float)

        state = replace(initial)
        out: list[ReservoirState] = []
        for i in range(n):
            state = self.step(
                state,
                inflow=inflow_series[i],
                turbine_flow=turbine_series[i],
                spill_flow=spill_series[i],
                dt_seconds=dt_seconds,
                evaporation_mm_day=evaporation_mm_day,
                rain_on_lake_mm=rain_on_lake_series[i],
            )
            out.append(state)
        return out

    # -- diagnostics --------------------------------------------------------

    def spill_capacity(
        self,
        level: float,
        gates_open: int,
        gate_width_m: float = 12.2,
        n_gates: int = 5,
        discharge_coeff: float = 0.6,
    ) -> float:
        """Free-flow discharge through ``gates_open`` fully-raised gates.

        Broad-crested weir relation Q = C * L * sqrt(2g) * H^1.5, with head H
        measured above the spillway crest. Below the crest, spilling is not
        physically possible at all.
        """
        crest = self.res.red_level
        head = max(0.0, level - crest)
        if head == 0.0 or gates_open <= 0:
            return 0.0
        width = gate_width_m * min(gates_open, n_gates)
        return float(discharge_coeff * width * np.sqrt(2 * 9.80665) * head ** 1.5)

    def time_to_frl(self, state: ReservoirState, net_inflow_cumecs: float) -> float:
        """Hours until FRL is reached at a sustained net inflow.

        Returns ``inf`` when the reservoir is draining or holding. This is the
        single number a dam operator most wants during a storm.
        """
        if net_inflow_cumecs <= 0:
            return float("inf")
        headroom_mm3 = self.curve.storage_from_level(self.res.frl) - state.storage
        if headroom_mm3 <= 0:
            return 0.0
        return float(headroom_mm3 * 1e6 / net_inflow_cumecs / 3600.0)
