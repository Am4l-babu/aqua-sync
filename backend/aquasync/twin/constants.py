"""Physical constants and reservoir registry for the AquaSync twin.

All reservoir figures are transcribed from the KSEB / KSDMA daily bulletin
fields published in the Kerala-Dam-Water-Levels dataset (see
``docs/data-sources.md``). Levels are metres above mean sea level (m MSL);
live storage is million cubic metres (Mm3); flows are cumecs (m3/s).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- Physical constants -----------------------------------------------------

G = 9.80665            # m/s^2, standard gravity
RHO_WATER = 1000.0     # kg/m^3
SECONDS_PER_DAY = 86_400
SECONDS_PER_HOUR = 3_600


@dataclass(frozen=True)
class Reservoir:
    """Static description of a reservoir in the modelled basin."""

    key: str
    name: str
    district: str
    latitude: float
    longitude: float

    frl: float                  # Full Reservoir Level, m MSL
    mwl: float                  # Maximum Water Level, m MSL
    rule_level: float           # Seasonal rule-curve level, m MSL
    red_level: float            # KSDMA red alert, m MSL
    orange_level: float         # KSDMA orange alert, m MSL
    blue_level: float           # KSDMA blue alert, m MSL
    dead_level: float           # Minimum drawdown level, m MSL

    live_storage_at_frl: float  # Mm3
    catchment_area_km2: float

    # Hydropower plant fed by this reservoir.
    installed_capacity_mw: float
    turbine_rated_flow: float   # cumecs at full load
    turbine_efficiency: float   # dimensionless, peak
    tailrace_level: float       # m MSL, for net head

    # Downstream reach this reservoir spills into.
    outlet_reach: str = ""

    @property
    def gross_head_at_frl(self) -> float:
        return self.frl - self.tailrace_level

    def freeboard(self, level: float) -> float:
        """Metres of level still available before FRL is breached."""
        return self.frl - level


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
    mwl=732.43,
    rule_level=728.50,
    red_level=728.19,
    orange_level=727.89,
    blue_level=726.06,
    dead_level=694.94,
    live_storage_at_frl=1459.49,
    catchment_area_km2=649.0,
    # Moolamattom (Idukki HEP): 6 x 130 MW, gross head about 669 m. The
    # powerhouse is underground and discharges into the Muvattupuzha, not
    # the Periyar - so Idukki generation does NOT load the Periyar, only
    # its spillway does. That asymmetry is central to the whole trade-off.
    installed_capacity_mw=780.0,
    turbine_rated_flow=138.0,
    turbine_efficiency=0.89,
    tailrace_level=63.0,
    outlet_reach="periyar_upper",
)

IDAMALAYAR = Reservoir(
    key="idamalayar",
    name="Idamalayar",
    district="Ernakulam",
    latitude=10.2219,
    longitude=76.7060,
    frl=169.00,
    mwl=169.00,
    rule_level=164.00,
    red_level=163.50,
    orange_level=162.50,
    blue_level=161.50,
    dead_level=115.00,
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


# Travel times below are first-pass estimates from reach length and a
# 1.0-1.5 m/s flood-wave celerity. calibrate_routing.py replaces them with
# values fitted to observed gauge data - do not quote these as measured.
REACHES: dict[str, Reach] = {
    "periyar_upper": Reach(
        key="periyar_upper",
        name="Idukki (Moolamattom) -> Neriamangalam -> Bhoothathankettu",
        length_km=52.0,
        k_hours=11.0,
        x=0.25,
        bankfull_cumecs=900.0,
        danger_cumecs=1400.0,
    ),
    "periyar_lower": Reach(
        key="periyar_lower",
        name="Bhoothathankettu -> Perumbavoor -> Aluva",
        length_km=38.0,
        k_hours=8.0,
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
