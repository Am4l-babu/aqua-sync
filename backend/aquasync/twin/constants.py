"""Physical constants and reservoir registry for the AquaSync twin.

All reservoir figures are transcribed from the KSEB / KSDMA daily bulletin
fields published in the Kerala-Dam-Water-Levels dataset (see
``docs/data-sources.md``). Levels are metres above mean sea level (m MSL);
live storage is million cubic metres (Mm3); flows are cumecs (m3/s).
"""

from __future__ import annotations

from dataclasses import dataclass

# --- Physical constants -----------------------------------------------------

G = 9.80665            # m/s^2, standard gravity
RHO_WATER = 1000.0     # kg/m^3
SECONDS_PER_DAY = 86_400
SECONDS_PER_HOUR = 3_600


# --- Rule curves ------------------------------------------------------------
# KSEBL 2020 rule curve, transcribed from CAG Appendix 3.3 ("Rule curve framed
# in 2020 for Idukki and Idamalayar dams"), page index 121 of
# research/sources/papers/CAG_Kerala_flood_audit.pdf.
#
# This is a STEP function, not a scalar and not an interpolation. KSEB holds
# the end-of-period value across each ten-day step - confirmed against the
# KSEB July-2026 monthly workbook, which carries 2375.33 ft on BOTH 01 and
# 10 July, and against KSEBL's own reply recorded in CAG that the 11-20 August
# level is 2,386.81 ft (727.50 m), matching the "August 20th" row here.
#
# Storing only the 31-August value - as this module previously did - freezes
# the reservoir at its most permissive setting all year. The optimiser
# normalises headroom by (frl - rule_level) and searches drawdown targets
# upward from blue_level, so a frozen scalar distorts the whole search space.

RULE_CURVE_2020: dict[str, list[tuple[int, int, float]]] = {
    # (month, day-of-period-end, level m MSL)
    "idukki": [
        (6, 10, 723.29), (6, 20, 723.29), (6, 30, 723.29),
        (7, 10, 724.00), (7, 20, 724.80), (7, 31, 725.60),
        (8, 10, 726.50), (8, 20, 727.50), (8, 31, 728.50),
        (9, 10, 729.25), (9, 20, 730.00), (9, 30, 730.59),
        (10, 10, 730.84), (10, 20, 731.17), (10, 31, 731.31),
        (11, 10, 731.46), (11, 20, 731.53), (11, 30, 731.53),
    ],
    "idamalayar": [
        (6, 10, 161.00), (6, 20, 161.00), (6, 30, 161.00),
        (7, 10, 161.50), (7, 20, 161.75), (7, 31, 162.50),
        (8, 10, 163.00), (8, 20, 163.50), (8, 31, 164.00),
        (9, 10, 165.00), (9, 20, 166.00), (9, 30, 166.30),
        (10, 10, 166.60), (10, 20, 166.80), (10, 31, 167.00),
        (11, 10, 168.50), (11, 20, 168.50), (11, 30, 168.50),
    ],
}

# Alert bands sit at fixed offsets BELOW the prevailing rule level, so they
# move with it through the season. Idukki's offsets are in feet (8.00 / 2.00 /
# 1.00 ft); Idamalayar's are metric (1.50 / 1.00 / 0.50 m). Verified against
# four sheets of the KSEB July-2026 workbook and a KSDMA August-2026 bulletin.
FT = 0.3048
ALERT_OFFSETS: dict[str, tuple[float, float, float]] = {
    # (blue, orange, red) metres below the rule level
    "idukki": (8.00 * FT, 2.00 * FT, 1.00 * FT),
    "idamalayar": (1.50, 1.00, 0.50),
}


@dataclass(frozen=True)
class Reservoir:
    """Static description of a reservoir in the modelled basin."""

    key: str
    name: str
    district: str
    latitude: float
    longitude: float

    frl: float                  # Full Reservoir Level, m MSL
    mwl: float                  # Maximum Water Level, m MSL - ABOVE FRL
    rule_level: float           # Rule level at end of monsoon; see rule_level_on()
    red_level: float            # KSDMA red alert at that rule level, m MSL
    orange_level: float         # KSDMA orange alert, m MSL
    blue_level: float           # KSDMA blue alert, m MSL
    dead_level: float           # Minimum drawdown level, m MSL
    spillway_crest: float       # Spillway crest, m MSL - NOT the alert level

    live_storage_at_frl: float  # Mm3
    catchment_area_km2: float

    # Hydropower plant fed by this reservoir.
    installed_capacity_mw: float
    turbine_rated_flow: float   # cumecs at full load
    turbine_efficiency: float   # dimensionless, peak
    tailrace_level: float       # m MSL, for net head

    # Spillway geometry, for the free-flow discharge relation.
    n_gates: int = 5
    gate_width_m: float = 12.19
    design_discharge_cumecs: float = 0.0

    # Downstream reach this reservoir spills into.
    outlet_reach: str = ""

    @property
    def gross_head_at_frl(self) -> float:
        return self.frl - self.tailrace_level

    @property
    def surcharge_range(self) -> float:
        """Metres of storage above FRL, up to MWL.

        Modelling this as zero - which it was until the CAG figures were
        checked - hides roughly 90 MCM at Idukki. That is comparable to the
        entire flood cushion CWC says operators actually had in August 2018,
        so it is not a rounding detail.
        """
        return max(0.0, self.mwl - self.frl)

    def freeboard(self, level: float) -> float:
        """Metres of level still available before FRL is breached."""
        return self.frl - level

    def rule_level_on(self, month: int, day: int) -> float:
        """Rule level applying on a given date, as a step function.

        Outside the June-November curve the reservoir is not under monsoon
        rule and the end-of-season level applies.
        """
        steps = RULE_CURVE_2020.get(self.key)
        if not steps:
            return self.rule_level
        for m, d, level in steps:
            if (month, day) <= (m, d):
                return level
        return steps[-1][2]

    def alert_levels_on(self, month: int, day: int) -> tuple[float, float, float]:
        """(blue, orange, red) alert levels for a date, from the rule curve."""
        rule = self.rule_level_on(month, day)
        blue_off, orange_off, red_off = ALERT_OFFSETS.get(self.key, (0.0, 0.0, 0.0))
        return rule - blue_off, rule - orange_off, rule - red_off


# --- Basin registry ---------------------------------------------------------
# The Periyar basin pair. These two reservoirs jointly control the flood that
# reaches Aluva and Kochi, and they are the subject of the Oct-2021 case study.

IDUKKI = Reservoir(
    key="idukki",
    name="Idukki",
    district="Idukki",
    latitude=9.8436,
    longitude=76.9762,
    frl=732.43,
    # MWL is ABOVE FRL. CAG Appendix 3.1 gives 734.11 m; the live KSEB
    # July-2026 workbook independently lists 2408.5 ft (733.91 m). Setting
    # this equal to FRL - as it was - models zero surcharge storage.
    mwl=734.11,
    # End-of-monsoon value only. Use rule_level_on(month, day) for the real
    # step curve; this scalar is the 31-August row of CAG Appendix 3.3.
    rule_level=728.50,
    red_level=728.19,
    orange_level=727.89,
    blue_level=726.06,
    dead_level=694.94,
    # Chute spillway crest, 2373 ft. NOT the red alert level: using
    # red_level here understated Idukki discharge capacity roughly threefold.
    spillway_crest=723.29,
    live_storage_at_frl=1459.49,
    catchment_area_km2=650.0,   # CAG Appendix 3.1
    # Moolamattom (Idukki HEP): 6 x 130 MW, gross head about 669 m. The
    # powerhouse is underground and discharges into the Muvattupuzha, not
    # the Periyar - so Idukki generation does NOT load the Periyar, only
    # its spillway does. That asymmetry is central to the whole trade-off.
    installed_capacity_mw=780.0,
    turbine_rated_flow=138.0,
    turbine_efficiency=0.89,
    tailrace_level=63.0,
    n_gates=5,
    gate_width_m=12.19,         # 5 radial gates, 12.19 x 10.36 m
    design_discharge_cumecs=5012.0,
    outlet_reach="periyar_upper",
)

IDAMALAYAR = Reservoir(
    key="idamalayar",
    name="Idamalayar",
    district="Ernakulam",
    latitude=10.2219,
    longitude=76.7060,
    frl=169.00,
    mwl=171.20,                 # CAG Appendix 3.1; KSEB workbook lists 171 m
    rule_level=164.00,          # 31-August row; see rule_level_on()
    # Alert bands are rule minus 1.50 / 1.00 / 0.50 m. Blue and orange were
    # previously set an extra 1.0 m and 0.5 m low, so both fired late.
    red_level=163.50,
    orange_level=163.00,
    blue_level=162.50,
    dead_level=115.00,
    spillway_crest=161.00,
    live_storage_at_frl=1017.80,
    catchment_area_km2=381.0,
    # Idamalayar HEP: 2 x 37.5 MW, gross head about 89 m.
    installed_capacity_mw=75.0,
    turbine_rated_flow=100.0,
    turbine_efficiency=0.90,
    tailrace_level=80.0,
    outlet_reach="periyar_lower",
)

REGISTRY: dict[str, Reservoir] = {r.key: r for r in (IDUKKI, IDAMALAYAR)}


@dataclass(frozen=True)
class Reach:
    """A river reach between a release point and a downstream control point."""

    key: str
    name: str
    length_km: float
    # Muskingum parameters, calibrated in scripts/calibrate_routing.py
    k_hours: float              # travel time of the flood wave
    x: float                    # weighting factor, 0.0-0.5
    bankfull_cumecs: float      # discharge at which the reach starts spilling
    danger_cumecs: float        # discharge at which the town floods
    tidal: bool = False         # is this reach tide-affected?


# Travel times are now anchored to the ONLY official published figure for
# this river: CWC's December-2018 report states an 8-hour travel time for
# combined Idukki + Idamalayar dam discharges to reach Neeleeswaram, which
# sits between Bhoothathankettu and Aluva on the lower Periyar.
#
# The previous values were geometry estimates from reach length and an assumed
# 1.0-1.5 m/s celerity, and summed to K = 19 h from Idukki to Aluva - roughly
# 2x too slow against that anchor. A twin that thinks the flood wave takes 19
# hours when it takes 8 will recommend acting far too late.
#
# Three honest caveats, none of which this comment lets you skip:
#   1. CWC derived the 8 hours "only for 2018", from a calibrated MIKE-11
#      model - not from a gauge pair, and not for other flow regimes.
#   2. Travel time is flow-dependent; a single K cannot be right at both
#      150 and 5,000 cumec. MuskingumCungeReach exists for that reason.
#   3. Neeleeswaram is upstream of Aluva, so the split of the 8 hours between
#      the two reaches below is apportioned by length, not measured.
#
# This is still NOT gauge-calibrated routing. The CWC daily discharge record
# for NEELEESWARAM (research/sources/datasets/) is the data to calibrate
# against - but it is missing 2018-08-16 to 08-22 and 08-24 to 08-27, so the
# flood peak itself was never gauged at the point the twin routes to.
REACHES: dict[str, Reach] = {
    "periyar_upper": Reach(
        key="periyar_upper",
        name="Idukki (Moolamattom) -> Neriamangalam -> Bhoothathankettu",
        length_km=52.0,
        k_hours=4.6,        # 8 h Idukki->Neeleeswaram, apportioned by length
        x=0.25,
        bankfull_cumecs=900.0,
        danger_cumecs=1400.0,
    ),
    "periyar_lower": Reach(
        key="periyar_lower",
        name="Bhoothathankettu -> Perumbavoor -> Aluva",
        length_km=38.0,
        k_hours=3.4,        # completes the CWC 8-hour anchor
        x=0.20,
        bankfull_cumecs=1100.0,
        danger_cumecs=1600.0,
    ),
    "periyar_estuary": Reach(
        key="periyar_estuary",
        name="Aluva -> Eloor -> Kochi backwaters",
        length_km=22.0,
        k_hours=5.0,
        x=0.15,
        bankfull_cumecs=1300.0,
        danger_cumecs=1800.0,
        tidal=True,
    ),
}

# Downstream control points where flood damage is evaluated.
CONTROL_POINTS: dict[str, dict] = {
    "neriamangalam": {"reach": "periyar_upper", "lat": 10.0500, "lon": 76.7833},
    "bhoothathankettu": {"reach": "periyar_upper", "lat": 10.1167, "lon": 76.6167},
    "perumbavoor": {"reach": "periyar_lower", "lat": 10.1100, "lon": 76.4750},
    "aluva": {"reach": "periyar_lower", "lat": 10.1075, "lon": 76.3517},
    "eloor": {"reach": "periyar_estuary", "lat": 10.0700, "lon": 76.3050},
}
