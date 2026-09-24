"""Bundle the simulation view's data so it works with no backend at all.

Demo beat 7 is "pull the network cable; nothing changes". The 3D twin and
the readouts already survive that on a bundled replay. The simulation drawer
did not - it needs the optimiser, which runs on the backend - so on a dead
network it said "Needs the API". This bakes the same payloads the API would
serve, from the same code, into ``dashboard/assets/``:

    sim_index.json          the scenario list `/api/scenarios` returns
    sim_<scenario>.json     `/api/scenarios/<key>/counterfactual` at scale 1,
                            plus the storm-multiple sweep if it is on disk

The dashboard reads these only when the API is unreachable, and says so:
the chip reads BUNDLED and the note names this script. Scaled storms are
not baked - every multiple is another optimiser run and the point of the
bundle is the flagship beat, not the stress test.

Deterministic: same input, same bytes, no timestamps. Re-run after any
change to the twin, the optimiser or the scenarios, and commit the result.

Usage::

    python scripts/bake_dashboard_data.py             # all scenarios
    python scripts/bake_dashboard_data.py --scenario periyar_oct_2021
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from aquasync.api.main import _counterfactual_payload  # noqa: E402
from aquasync.twin.scenarios import SCENARIOS  # noqa: E402

DATA_RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
ASSETS = ROOT / "dashboard" / "assets"

NOTE = (
    "Bundled by scripts/bake_dashboard_data.py from the same code the API runs. "
    "Served only when the API is unreachable. Hindsight, not live, and not a "
    "measurement."
)


def scenario_row(key: str) -> dict:
    s = SCENARIOS[key]
    return {
        "key": s.key, "title": s.title, "start": s.start, "end": s.end,
        "reservoir": s.reservoir.name, "narrative": s.narrative, "citation": s.citation,
    }


def bake(key: str) -> Path:
    payload = _counterfactual_payload(key, str(DATA_RAW), 1.0)
    sweep_path = PROCESSED / f"stress_sweep_{key}.json"
    sweep = json.loads(sweep_path.read_text(encoding="utf-8")) if sweep_path.exists() else None
    out = ASSETS / f"sim_{key}.json"
    out.write_text(json.dumps({
        "note": NOTE,
        "scenario": scenario_row(key),
        "counterfactual": payload,
        "sweep": sweep,
    }, separators=(",", ":")) + "\n", encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--scenario", choices=sorted(SCENARIOS), help="one scenario; default all")
    args = ap.parse_args()

    # Registry order, not alphabetical: the flagship comes first in
    # /api/scenarios and must come first offline too, or a dead network
    # opens the drawer on August 2022.
    keys = [args.scenario] if args.scenario else list(SCENARIOS)
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / "sim_index.json").write_text(
        json.dumps([scenario_row(k) for k in SCENARIOS], indent=2) + "\n",
        encoding="utf-8")
    for k in keys:
        p = bake(k)
        print(f"  {p.relative_to(ROOT)}  {p.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
