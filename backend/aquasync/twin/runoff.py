"""Rainfall-to-inflow conversion (SCS Curve Number + unit hydrograph).

Rain that falls on a catchment does not arrive at the dam instantly, and not
all of it arrives at all. Two things happen:

1. *Losses*  - some rain infiltrates, some is intercepted by canopy, some is
   held in depressions. The SCS Curve Number method converts total rainfall
   depth to effective rainfall (the part that becomes runoff).
2. *Timing*  - the runoff that does occur is spread over hours as it travels
   down hillslopes and tributaries. A synthetic unit hydrograph does this.

The catchment wetness at the start of the storm dominates everything. The
same 100 mm falling on a dry June catchment and a saturated October catchment
produce completely different inflows. That is modelled through the antecedent
moisture condition (AMC), which shifts the curve number.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Curve numbers for AMC-II (average wetness), from the SCS/NRCS handbook.
# The Idukki and Idamalayar catchments are steep, forested Western Ghats
# terrain on mostly hydrologic soil group C.
CURVE_NUMBERS = {
    "forest_good_C": 70,
    "forest_fair_C": 73,
    "plantation_C": 78,      # tea / cardamom estates
    "grassland_C": 74,
    "built_up_C": 90,
    "bare_rock": 96,
}

DEFAULT_CN_IDUKKI = 72.0      # mostly protected forest + cardamom estates
DEFAULT_CN_IDAMALAYAR = 74.0  # slightly more disturbed


def adjust_cn_for_amc(cn2: float, five_day_rain_mm: float, growing_season: bool = True) -> float:
    """Shift an AMC-II curve number to AMC-I (dry) or AMC-III (wet).

    Thresholds are the standard NRCS antecedent-rainfall bands. During the
    monsoon a Western Ghats catchment sits at AMC-III for weeks at a time,
    which is exactly why a mid-monsoon storm produces so much more runoff
    than the same storm in May.
    """
    if growing_season:
        dry_limit, wet_limit = 35.0, 53.0
    else:
        dry_limit, wet_limit = 12.0, 28.0

    if five_day_rain_mm < dry_limit:
        # AMC-I, drier than average
        return 4.2 * cn2 / (10.0 - 0.058 * cn2)
    if five_day_rain_mm > wet_limit:
        # AMC-III, wetter than average
        return 23.0 * cn2 / (10.0 + 0.13 * cn2)
    return cn2


def scs_effective_rainfall(rain_mm, curve_number: float, initial_abstraction_ratio: float = 0.2):
    """Convert rainfall depth to effective (runoff-producing) depth.

        S  = 25400 / CN - 254                (mm, potential retention)
        Ia = lambda * S                      (initial abstraction)
        Pe = (P - Ia)^2 / (P - Ia + S)       for P > Ia, else 0

    The classic lambda is 0.2; more recent Indian catchment studies favour
    0.1-0.3, so it is exposed as a calibration knob rather than hard-coded.
    """
    rain = np.atleast_1d(np.asarray(rain_mm, dtype=float))
    s = 25400.0 / curve_number - 254.0
    ia = initial_abstraction_ratio * s

    excess = np.where(
        rain > ia,
        (rain - ia) ** 2 / (rain - ia + s),
        0.0,
    )
    return excess if excess.size > 1 else float(excess[0])


@dataclass
class UnitHydrograph:
    """Synthetic triangular unit hydrograph (SCS dimensionless form).

    Defined by the time to peak. For a catchment of area A km2, 1 mm of
    effective rainfall produces a triangular hydrograph whose volume is
    exactly A * 1 mm.
    """

    time_to_peak_h: float
    recession_ratio: float = 1.67  # SCS standard: t_base = 2.67 * t_peak

    @property
    def base_time_h(self) -> float:
        return self.time_to_peak_h * (1.0 + self.recession_ratio)

    def ordinates(self, dt_hours: float = 1.0, area_km2: float = 1.0) -> np.ndarray:
        """Cumecs per mm of effective rainfall, at ``dt_hours`` spacing."""
        tb = self.base_time_h
        tp = self.time_to_peak_h

        # Peak discharge of the triangle so that its area equals the volume:
        # V = A_km2 * 1mm = A * 1e6 m2 * 1e-3 m = A * 1e3 m3
        # V = 0.5 * q_peak * tb * 3600  ->  q_peak = 2V / (tb * 3600)
        volume_m3 = area_km2 * 1e3
        q_peak = 2.0 * volume_m3 / (tb * 3600.0)

        t = np.arange(0.0, tb + dt_hours, dt_hours)
        q = np.where(
            t <= tp,
            q_peak * t / tp,
            q_peak * np.maximum(0.0, (tb - t) / (tb - tp)),
        )
        return q

    @staticmethod
    def from_catchment(area_km2: float, main_channel_km: float, slope: float) -> UnitHydrograph:
        """Estimate time to peak from catchment geometry (SCS lag equation).

        lag = 0.6 * Tc, with Tc from the Kirpich formula. Steep Western Ghats
        catchments give short lags - Idukki responds in well under a day,
        which is precisely why pre-emptive release must start from a forecast
        rather than from an observed inflow rise.
        """
        # Kirpich: Tc (hours) = 0.0195 * L^0.77 * S^-0.385, L in metres
        length_m = main_channel_km * 1000.0
        tc_min = 0.0195 * length_m ** 0.77 * slope ** -0.385
        tc_h = tc_min / 60.0
        lag_h = 0.6 * tc_h
        # SCS: t_peak = dt/2 + lag, taking dt = 1 h
        return UnitHydrograph(time_to_peak_h=max(1.0, 0.5 + lag_h))


class RainfallRunoffModel:
    """Full rainfall -> reservoir inflow chain for one catchment."""

    def __init__(
        self,
        area_km2: float,
        curve_number: float,
        unit_hydrograph: UnitHydrograph,
        baseflow_cumecs: float = 0.0,
        initial_abstraction_ratio: float = 0.2,
    ) -> None:
        self.area_km2 = area_km2
        self.cn2 = curve_number
        self.uh = unit_hydrograph
        self.baseflow = baseflow_cumecs
        self.ia_ratio = initial_abstraction_ratio

    def inflow_series(
        self,
        rain_mm_per_step,
        dt_hours: float = 1.0,
        antecedent_rain_mm: float = 0.0,
        growing_season: bool = True,
    ) -> np.ndarray:
        """Convolve effective rainfall with the unit hydrograph.

        Antecedent wetness is updated as the storm proceeds, so a long storm
        progressively saturates its own catchment - the runoff coefficient
        rises hour by hour. That feedback is what turns a multi-day monsoon
        spell into a flood.
        """
        rain = np.asarray(rain_mm_per_step, dtype=float)
        n = len(rain)

        # Rolling 5-day antecedent depth, seeded with the supplied prior.
        window = max(1, int(round(120.0 / dt_hours)))  # 5 days
        excess = np.zeros(n)
        for i in range(n):
            prior = antecedent_rain_mm + rain[max(0, i - window):i].sum()
            cn = adjust_cn_for_amc(self.cn2, prior, growing_season)
            excess[i] = scs_effective_rainfall(rain[i], cn, self.ia_ratio)

        uh = self.uh.ordinates(dt_hours=dt_hours, area_km2=self.area_km2)
        direct = np.convolve(excess, uh)[:n]
        return direct + self.baseflow

    def runoff_coefficient(self, rain_mm: float, antecedent_rain_mm: float = 0.0) -> float:
        """Fraction of rainfall that becomes runoff. Useful for the UI."""
        if rain_mm <= 0:
            return 0.0
        cn = adjust_cn_for_amc(self.cn2, antecedent_rain_mm)
        return float(scs_effective_rainfall(rain_mm, cn, self.ia_ratio) / rain_mm)
