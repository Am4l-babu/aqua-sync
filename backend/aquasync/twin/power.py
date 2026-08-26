"""Hydropower value - the other half of the trade-off.

Every cubic metre sent through the spillway instead of the turbines is
electricity that was never generated. Quantifying that loss precisely is
what converts the twin from a safety tool that the power utility resists
into a scheduling tool it has a reason to adopt.

Two things make the accounting non-trivial:

1. **Head varies with level.** Drawing the reservoir down reduces the head
   on every subsequent cubic metre, so early release is more expensive than
   the naive volume ratio suggests.
2. **Price varies with time of day.** Kerala's evening peak (roughly 18:00
   to 22:00) is worth substantially more than off-peak. Water held six hours
   and released into the peak can be worth more than water released now,
   *even after* accounting for the extra flood risk of holding it.

The optimiser uses this module to price each candidate release schedule.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .constants import RHO_WATER, G, Reservoir


@dataclass
class TariffProfile:
    """Time-of-day energy value, INR per kWh.

    Defaults approximate the KSEB ToD structure for bulk supply. They are
    indicative and belong in config, not in a pitch deck, until confirmed
    against the current KSERC tariff order.
    """

    off_peak: float = 3.20      # 22:00-06:00
    normal: float = 4.50        # 06:00-18:00
    peak: float = 7.80          # 18:00-22:00

    def rate_at_hour(self, hour_of_day) -> np.ndarray:
        h = np.atleast_1d(np.asarray(hour_of_day, dtype=float)) % 24
        rate = np.full_like(h, self.normal)
        rate = np.where((h >= 22) | (h < 6), self.off_peak, rate)
        rate = np.where((h >= 18) & (h < 22), self.peak, rate)
        return rate


class HydropowerModel:
    """Converts turbine discharge and head into MW and rupees."""

    def __init__(self, reservoir: Reservoir, tariff: TariffProfile | None = None) -> None:
        self.res = reservoir
        self.tariff = tariff or TariffProfile()

    # -- physics ------------------------------------------------------------

    def net_head(self, level, penstock_loss_fraction: float = 0.03):
        """Net head in metres, after penstock friction losses."""
        gross = np.asarray(level, dtype=float) - self.res.tailrace_level
        return np.maximum(0.0, gross * (1.0 - penstock_loss_fraction))

    def turbine_efficiency(self, discharge, head):
        """Efficiency from the turbine hill diagram, approximated.

        Real turbines have a peak-efficiency island and fall off sharply at
        part load. A parabola in the load ratio, capped at the rated peak,
        captures the important behaviour: running one unit near full load
        beats running three units at a third load each.
        """
        q = np.atleast_1d(np.asarray(discharge, dtype=float))
        load = np.clip(q / self.res.turbine_rated_flow, 0.0, 1.2)

        # Peak near 85% of rated flow, falling away either side.
        eta = self.res.turbine_efficiency * (1.0 - 2.2 * (load - 0.85) ** 2)
        eta = np.where(load < 0.05, 0.0, eta)     # below cut-in, no output
        return np.clip(eta, 0.0, self.res.turbine_efficiency)

    def power_mw(self, discharge, level):
        """P = rho * g * Q * H_net * eta, in megawatts."""
        q = np.atleast_1d(np.asarray(discharge, dtype=float))
        h = self.net_head(level)
        eta = self.turbine_efficiency(q, h)
        watts = RHO_WATER * G * q * h * eta
        return watts / 1e6

    def energy_mwh(self, discharge, level, dt_hours: float = 1.0):
        return self.power_mw(discharge, level) * dt_hours

    def revenue_inr(self, discharge, level, hour_of_day, dt_hours: float = 1.0):
        """Rupees earned by this discharge, at the time-of-day tariff."""
        mwh = self.energy_mwh(discharge, level, dt_hours)
        rate = self.tariff.rate_at_hour(hour_of_day)
        return mwh * 1000.0 * rate     # MWh -> kWh -> INR

    # -- decision support ---------------------------------------------------

    def spill_opportunity_cost(
        self, spill_cumecs, level, hour_of_day, dt_hours: float = 1.0
    ):
        """Rupees of generation forgone by spilling instead of turbining.

        Only the part of the spill that the turbines could actually have
        absorbed counts. Water above the turbine rating had to be spilled
        regardless, and charging that against the flood decision would
        overstate the cost of acting - a mistake that biases an operator
        toward holding water.
        """
        spill = np.atleast_1d(np.asarray(spill_cumecs, dtype=float))
        usable = np.minimum(spill, self.res.turbine_rated_flow)
        return self.revenue_inr(usable, level, hour_of_day, dt_hours)

    def best_generation_hours(
        self, horizon_hours: int, start_hour_of_day: float = 0.0
    ) -> np.ndarray:
        """Hours in the horizon ranked by tariff, best first.

        Used by the golden-window search: if flood risk permits both, release
        into the hours where the water is worth the most.
        """
        hours = (np.arange(horizon_hours) + start_hour_of_day) % 24
        rates = self.tariff.rate_at_hour(hours)
        return np.argsort(-rates)
