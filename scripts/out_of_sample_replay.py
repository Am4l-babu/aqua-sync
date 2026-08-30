"""Out-of-sample replay validation - closes ROADMAP.md item 5.

docs/validation.md flags a real gap: every calibration and replay number in
this project is October 2021. The August 2022 scenario is defined in
``twin/scenarios.py`` but has never been run. Until it has, the model is
*calibrated*, not *validated* - a domain-literate judge will make exactly
that distinction.

Method, mirroring validation.md section 2 (the Oct 2021 replay) exactly so
the two are comparable: feed the OBSERVED inflow, powerhouse discharge and
spillway discharge for the scenario window into the mass-balance model with
no fitting to the level series itself, and compare simulated level to the
observed bulletin level, hour by hour. This checks the physics engine
(reservoir.py), not the forecast chain - it answers "does dV/dt = Qin -
Qturbine - Qspill - Qevap track reality on an episode the model has never
seen," which is a different and prior question to the forecast-error study.

Usage:
    python scripts/out_of_sample_replay.py
    python scripts/out_of_sample_replay.py --scenario periyar_oct_2021
        # sanity check: should reproduce validation.md section 2's numbers
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from aquasync.twin.reservoir import LevelStorageCurve, ReservoirModel, ReservoirState  # noqa: E402
from aquasync.twin.scenarios import SCENARIOS, load_scenario_series  # noqa: E402


def run(scenario_key: str, cache_dir: Path) -> dict:
    scenario = SCENARIOS[scenario_key]
    series = load_scenario_series(scenario, cache_dir=cache_dir, hourly=True)

    res = scenario.reservoir
    curve = LevelStorageCurve(res)
    model = ReservoirModel(res, curve)

    observed_level = series["water_level_m"].to_numpy(dtype=float)
    inflow = series["inflow_cumecs"].to_numpy(dtype=float)
    turbine = series["powerhouse_cumecs"].fillna(0).to_numpy(dtype=float)
    spill = series["spillway_cumecs"].fillna(0).to_numpy(dtype=float)

    initial = ReservoirState(level=float(observed_level[0]),
                              storage=curve.storage_from_level(float(observed_level[0])))
    states = model.simulate(initial, inflow, turbine, spill, dt_seconds=3600.0)
    simulated_level = np.array([s.level for s in states])

    error = simulated_level - observed_level
    abs_error = np.abs(error)

    return {
        "scenario": scenario_key,
        "window": f"{scenario.start} to {scenario.end}",
        "n_hours": int(len(observed_level)),
        "mean_absolute_error_m": round(float(abs_error.mean()), 3),
        "max_absolute_error_m": round(float(abs_error.max()), 3),
        "max_absolute_error_at_hour": int(abs_error.argmax()),
        "final_step_error_m": round(float(error[-1]), 3),
        "error_biased_positive": bool(error.mean() > 0),
        "observed_peak_level_m": round(float(observed_level.max()), 3),
        "simulated_peak_level_m": round(float(simulated_level.max()), 3),
        "observed_min_level_m": round(float(observed_level.min()), 3),
        "simulated_min_level_m": round(float(simulated_level.min()), 3),
        "spillway_active_hours": int((spill > 0).sum()),
        "spillway_peak_cumecs": round(float(spill.max()), 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--scenario", default="idukki_aug_2022", choices=list(SCENARIOS))
    ap.add_argument("--cache-dir", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "processed")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    result = run(args.scenario, args.cache_dir)

    print(f"scenario:  {result['scenario']}  "
          f"({result['window']}, {result['n_hours']} hourly steps)")
    print(f"mean absolute error:  {result['mean_absolute_error_m']:.3f} m")
    print(f"max absolute error:   {result['max_absolute_error_m']:.3f} m "
          f"(hour {result['max_absolute_error_at_hour']})")
    print(f"final-step error:     {result['final_step_error_m']:+.3f} m "
          f"({'grows' if result['error_biased_positive'] else 'does not grow'} positive)")
    print(f"observed peak level:  {result['observed_peak_level_m']:.2f} m")
    print(f"simulated peak level: {result['simulated_peak_level_m']:.2f} m")
    print(f"spillway active:      {result['spillway_active_hours']} h, "
          f"peak {result['spillway_peak_cumecs']:.0f} cumecs")

    out_json = args.out / f"replay_{args.scenario}.json"
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nwritten -> {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
