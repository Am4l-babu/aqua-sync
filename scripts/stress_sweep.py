"""Storm-multiple sweep: at what size of this storm does each schedule reach FRL?

The brief asked for "synthetic 500-year storms" and a Monte Carlo probability
of failure. Six years of daily bulletins cannot train a storm generator, and a
probability from invented storms would be a number nobody could defend. This
is the version the data can carry: the recorded inflow of one episode, scaled
by a fixed ladder of multiples, run through the same replay and the same
exhaustive policy search as everything else. For each multiple it records the
peak level and minimum freeboard under the day's releases and under the
optimiser's, and reports the first multiple on the ladder at which each
reaches FRL.

It is a sensitivity, not a return period. Nothing here says how likely a
1.5x storm is - only what would have happened to the two schedules if it had
come.

Usage::

    python scripts/stress_sweep.py                      # flagship scenario
    python scripts/stress_sweep.py --scenario idukki_aug_2022

Writes data/processed/stress_sweep_<scenario>.json. Seven optimiser runs,
about two minutes on this machine. Deterministic: same input, same file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from aquasync.twin.scenarios import SCENARIOS, run_counterfactual  # noqa: E402

LADDER = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)
DATA_RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"


def sweep(key: str, ladder=LADDER) -> dict:
    res = SCENARIOS[key].reservoir
    rows = []
    for scale in ladder:
        out = run_counterfactual(key, DATA_RAW, inflow_scale=scale)
        s = out["summary"]
        rows.append({
            "inflow_scale": scale,
            "peak_level_baseline_m": s["peak_level_baseline"],
            "peak_level_optimised_m": s["peak_level_optimised"],
            "min_freeboard_baseline_m": s["min_freeboard_baseline_m"],
            "min_freeboard_optimised_m": s["min_freeboard_optimised_m"],
            "baseline_reaches_frl": bool(s["baseline_breached_frl"]),
            "optimised_reaches_frl": bool(s["optimised_breached_frl"]),
            "peak_downstream_baseline_cumecs": s["peak_downstream_baseline"],
            "peak_downstream_optimised_cumecs": s["peak_downstream_optimised"],
            "policy": out["evaluations"]["optimised"].metadata.get("policy"),
        })
        print(f"  x{scale:<5} day {s['peak_level_baseline']:7.2f} m  "
              f"AquaSync {s['peak_level_optimised']:7.2f} m  "
              f"FRL {res.frl}")

    def first(flag: str):
        return next((r["inflow_scale"] for r in rows if r[flag]), None)

    return {
        "scenario": key,
        "title": SCENARIOS[key].title,
        "frl_m": res.frl,
        "ladder": list(ladder),
        "rows": rows,
        "first_multiple_reaching_frl": {
            "baseline": first("baseline_reaches_frl"),
            "optimised": first("optimised_reaches_frl"),
        },
        "caveat": (
            "A sensitivity, not a return period. Each row is the recorded inflow "
            "multiplied by a constant and run through the same replay and the "
            "same exhaustive policy search as the flagship counterfactual. The "
            "ladder is coarse (0.25 steps to 2, then 0.5), so 'first multiple' "
            "is an upper bound on the threshold, not the threshold. Nothing "
            "here says how likely any multiple is. Levels carry the replay "
            "error of the twin, about 0.3 m MAE on the recorded storm. A level "
            "above the crest is the mass balance continuing past it: the twin "
            "has no overtopping physics, so read anything above MWL as 'the "
            "dam would have been overtopped', not as a depth. The optimiser "
            "may release up to 1,500 cumecs; a schedule that holds the "
            "reservoir under FRL at large multiples does so by releasing more, "
            "and what that does below the dam is in the downstream columns - "
            "one dam's routed contribution on an uncalibrated reach."
        ),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--scenario", default="periyar_oct_2021", choices=sorted(SCENARIOS))
    args = ap.parse_args()

    print(f"stress sweep: {args.scenario}")
    result = sweep(args.scenario)
    path = OUT / f"stress_sweep_{args.scenario}.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    f = result["first_multiple_reaching_frl"]
    print(f"first multiple reaching FRL: day x{f['baseline']}, AquaSync x{f['optimised']}")
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
