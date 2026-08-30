"""Cascade co-optimisation - ROADMAP.md item 2.

Idukki and Idamalayar are currently optimised independently everywhere else
in this project (`scripts/lead_time_study.py`, `scripts/forecast_error_study.py`).
The evidence this project already has - both dams opened their gates on the
same day in October 2021, into the same river - is that independent
optimisation is exactly the failure mode: nothing stops two well-run
reservoirs from releasing their own well-timed pulses straight into each
other downstream.

`RiverNetwork` (backend/aquasync/twin/routing.py) already implements the
DAG routing this needs - Idukki's release travels periyar_upper then
periyar_lower to reach Aluva; Idamalayar's release enters periyar_lower
directly, at the confluence with Idukki's already-routed flow - but it has
never been used outside its own module (no test, no script). This script
is the first real use of it, and the first real answer to whether
"scheduling them together so their pulses do not superpose" is worth
anything beyond the two independently-optimal schedules.

Method:

1. Each dam's own independently-optimal DrawdownPolicy, via the existing
   exhaustive `search_policies` - unchanged from how every other study in
   this project treats a single reservoir.
2. Route the OBSERVED (historical) releases for both dams jointly through
   RiverNetwork - this reproduces the actual October 2021 superposition
   and is the ground-truth baseline.
3. Route each dam's own independently-optimal release jointly through
   RiverNetwork - "what happens if both dams optimise for themselves,
   knowing nothing about each other." If this alone fixes the superposition,
   coordination adds nothing; if it does not, there is a real gap to close.
4. A coordination search over (idukki_start_hour, idamalayar_start_hour),
   holding each dam's own optimal target_level and max_rate fixed, choosing
   the pair that minimises PEAK COMBINED DISCHARGE at the periyar_lower
   node (the "does it superpose" metric ROADMAP names directly) rather than
   either dam's own individual objective.

Usage:
    python scripts/cascade_coordination.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from aquasync.io.kseb_dataset import daily_to_hourly, load_dam  # noqa: E402
from aquasync.twin.constants import IDAMALAYAR, IDUKKI, REACHES  # noqa: E402
from aquasync.twin.optimizer import (  # noqa: E402
    DrawdownPolicy,
    ObjectiveWeights,
    OperationalLimits,
    ReleaseOptimizer,
)
from aquasync.twin.reservoir import LevelStorageCurve, ReservoirState  # noqa: E402
from aquasync.twin.routing import RiverNetwork  # noqa: E402

WINDOW_START, WINDOW_END = "2021-10-08", "2021-10-28"
COLS = ["water_level_m", "live_storage_mm3", "inflow_cumecs",
        "powerhouse_cumecs", "spillway_cumecs", "rainfall_mm"]


def load_hourly(dam_name: str, cache_dir: Path) -> pd.DataFrame:
    rec = load_dam(dam_name, cache_dir=cache_dir)
    frame = rec.window(WINDOW_START, WINDOW_END).copy()
    for c in COLS:
        frame[c] = pd.to_numeric(frame[c], errors="coerce")
    frame[COLS] = frame[COLS].interpolate(limit_direction="both")
    out = daily_to_hourly(frame, COLS)
    out["rainfall_mm"] = out["rainfall_mm"] / 24.0
    return out


def build_optimizer(
    res, series: pd.DataFrame, reach,
) -> tuple[ReleaseOptimizer, ReservoirState, np.ndarray]:
    curve = LevelStorageCurve(res)
    start_level = float(series["water_level_m"].iloc[0])
    initial = ReservoirState(level=start_level, storage=curve.storage_from_level(start_level))
    observed_release = (
        series["powerhouse_cumecs"].fillna(0).to_numpy(dtype=float)
        + series["spillway_cumecs"].fillna(0).to_numpy(dtype=float)
    )
    observed_turbine_mean = float(np.minimum(observed_release, res.turbine_rated_flow).mean())
    limits = OperationalLimits(
        max_release_cumecs=10.9 * res.turbine_rated_flow,  # same ratio as the Idukki-solo studies
        max_ramp_cumecs_per_hour=50.0,
        max_level=res.frl,
        max_mean_turbine_cumecs=observed_turbine_mean,
    )
    opt = ReleaseOptimizer(
        res, reach, weights=ObjectiveWeights.monsoon_peak(), limits=limits, seed=7,
    )
    return opt, initial, observed_release


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--cache-dir", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "processed")
    ap.add_argument("--n-offsets", type=int, default=10, help="grid steps per dam's start_hour")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    idukki_series = load_hourly("Idukki", args.cache_dir)
    idamalayar_series = load_hourly("Idamalayar", args.cache_dir)
    n = min(len(idukki_series), len(idamalayar_series))
    idukki_series, idamalayar_series = idukki_series.iloc[:n], idamalayar_series.iloc[:n]
    print(f"window: {WINDOW_START} to {WINDOW_END}, {n} hourly steps, both dams")

    # Both dams evaluate their OWN policy against periyar_lower - the same
    # simplification the single-dam studies elsewhere in this project use
    # (it is Idamalayar's real outlet reach; for Idukki it skips the
    # periyar_upper leg for THIS step only - the joint routing below is
    # where the full multi-reach path is used).
    idukki_opt, idukki_initial, idukki_observed = build_optimizer(
        IDUKKI, idukki_series, REACHES["periyar_lower"],
    )
    idamalayar_opt, idamalayar_initial, idamalayar_observed = build_optimizer(
        IDAMALAYAR, idamalayar_series, REACHES["periyar_lower"],
    )

    idukki_inflow = idukki_series["inflow_cumecs"].to_numpy(dtype=float)
    idamalayar_inflow = idamalayar_series["inflow_cumecs"].to_numpy(dtype=float)

    print("searching each dam's own independent optimum...")
    idukki_best, idukki_policy = idukki_opt.search_policies(idukki_initial, idukki_inflow)
    idamalayar_best, idamalayar_policy = idamalayar_opt.search_policies(
        idamalayar_initial, idamalayar_inflow,
    )
    print(f"  Idukki:     {idukki_policy.describe('Idukki')}")
    print(f"  Idamalayar: {idamalayar_policy.describe('Idamalayar')}")

    network = RiverNetwork(
        reaches={"periyar_upper": REACHES["periyar_upper"],
                 "periyar_lower": REACHES["periyar_lower"]},
        topology={"periyar_upper": ["idukki"],
                  "periyar_lower": ["periyar_upper", "idamalayar"]},
        dt_hours=1.0,
    )

    def joint_peak(idukki_release: np.ndarray, idamalayar_release: np.ndarray) -> float:
        routed = network.route_all({"idukki": idukki_release, "idamalayar": idamalayar_release})
        return float(routed["periyar_lower"].max())

    observed_peak = joint_peak(idukki_observed, idamalayar_observed)
    print(f"\nobserved (historical) joint peak at periyar_lower: {observed_peak:.1f} cumecs")

    idukki_own_release = idukki_opt.policy_schedule(idukki_initial, idukki_inflow, idukki_policy)
    idamalayar_own_release = idamalayar_opt.policy_schedule(
        idamalayar_initial, idamalayar_inflow, idamalayar_policy,
    )
    naive_peak = joint_peak(idukki_own_release, idamalayar_own_release)
    print(f"naive (each dam optimises alone) joint peak:      {naive_peak:.1f} cumecs")

    print(f"\ncoordination search over start_hour x start_hour "
          f"({args.n_offsets}x{args.n_offsets} = {args.n_offsets**2} combos)...")
    starts = np.unique(np.linspace(0, max(1, n - 24), args.n_offsets).astype(int))
    best_peak = naive_peak
    best_pair = (idukki_policy.start_hour, idamalayar_policy.start_hour)
    for i_start in starts:
        i_policy = DrawdownPolicy(idukki_policy.target_level, int(i_start), idukki_policy.max_rate)
        i_release = idukki_opt.policy_schedule(idukki_initial, idukki_inflow, i_policy)
        for a_start in starts:
            a_policy = DrawdownPolicy(
                idamalayar_policy.target_level, int(a_start), idamalayar_policy.max_rate,
            )
            a_release = idamalayar_opt.policy_schedule(
                idamalayar_initial, idamalayar_inflow, a_policy,
            )
            peak = joint_peak(i_release, a_release)
            if peak < best_peak:
                best_peak = peak
                best_pair = (int(i_start), int(a_start))

    coord_idukki = DrawdownPolicy(idukki_policy.target_level, best_pair[0], idukki_policy.max_rate)
    coord_idamalayar = DrawdownPolicy(
        idamalayar_policy.target_level, best_pair[1], idamalayar_policy.max_rate,
    )
    print(f"\ncoordinated joint peak: {best_peak:.1f} cumecs")
    print(f"  Idukki:     {coord_idukki.describe('Idukki')}")
    print(f"  Idamalayar: {coord_idamalayar.describe('Idamalayar')}")

    bankfull = REACHES["periyar_lower"].bankfull_cumecs
    danger = REACHES["periyar_lower"].danger_cumecs
    result = {
        "window": [WINDOW_START, WINDOW_END],
        "n_hours": n,
        "periyar_lower_bankfull_cumecs": bankfull,
        "periyar_lower_danger_cumecs": danger,
        "observed_joint_peak_cumecs": round(observed_peak, 1),
        "naive_independent_joint_peak_cumecs": round(naive_peak, 1),
        "coordinated_joint_peak_cumecs": round(best_peak, 1),
        "naive_vs_observed_reduction_pct":
            round(100 * (observed_peak - naive_peak) / observed_peak, 1),
        "coordination_vs_naive_reduction_pct":
            round(100 * (naive_peak - best_peak) / naive_peak, 1),
        "coordination_vs_observed_reduction_pct":
            round(100 * (observed_peak - best_peak) / observed_peak, 1),
        "idukki_independent_policy": {
            "target_level_m": idukki_policy.target_level,
            "start_hour": idukki_policy.start_hour,
            "max_rate_cumecs": idukki_policy.max_rate,
        },
        "idamalayar_independent_policy": {
            "target_level_m": idamalayar_policy.target_level,
            "start_hour": idamalayar_policy.start_hour,
            "max_rate_cumecs": idamalayar_policy.max_rate,
        },
        "idukki_coordinated_start_hour": best_pair[0],
        "idamalayar_coordinated_start_hour": best_pair[1],
        "idukki_own_peak_level_m": round(float(idukki_best.peak_level), 3),
        "idamalayar_own_peak_level_m": round(float(idamalayar_best.peak_level), 3),
        "caveat": "coordination search sweeps start_hour only, holding each dam's own "
                  "independently-optimal target_level and max_rate fixed - a joint "
                  "6-parameter search was not run (1344^2 combinations is not tractable "
                  "at this grid density)",
    }
    out_json = args.out / "cascade_coordination.json"
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"\nbankfull {bankfull:.0f} / danger {danger:.0f} cumecs at periyar_lower")
    print(f"observed exceeds bankfull by {max(0, observed_peak - bankfull):.0f} cumecs")
    print(f"coordinated exceeds bankfull by {max(0, best_peak - bankfull):.0f} cumecs")
    print(f"\nwritten -> {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
