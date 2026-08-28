"""Routing calibration against the Neeleeswaram gauge - ROADMAP.md item 3.

The Muskingum K and x for periyar_upper + periyar_lower are anchored to a
single published number - CWC's December-2018 report states an 8-hour
travel time for combined Idukki + Idamalayar discharge to reach
Neeleeswaram, derived from a MIKE-11 model run "only for 2018", not from a
gauge pair. This script replaces that anchor with an actual fit against
CWC's own Neeleeswaram daily discharge record (2001-2025) and the KSEB
daily bulletin releases from both dams (2020-08-13 onward - the KSEB feed
does not go back further, so 2018 itself cannot be calibrated against
regardless of gauge availability).

Method: `MuskingumReach.calibrate` (already implemented, already
unit-tested against synthetic data, never run against real gauge data
before now). Inflow = combined Idukki + Idamalayar release (powerhouse +
spillway, both dams summed); outflow = observed Neeleeswaram discharge.
Both daily. The calibration therefore fits ONE combined K/x for the whole
Idukki-to-Neeleeswaram path (periyar_upper + periyar_lower together) - it
cannot separate the two sub-reaches without a gauge between
Bhoothathankettu and Neeleeswaram, which does not exist in this dataset.
The existing length-based 4.6h/3.4h split is kept for the two sub-reaches;
what changes is the combined total they are anchored to.

Usage:
    python scripts/routing_calibration.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from aquasync.io.kseb_dataset import load_dam  # noqa: E402
from aquasync.twin.constants import REACHES  # noqa: E402
from aquasync.twin.routing import MuskingumReach  # noqa: E402

NEELEESWARAM_CSV = (ROOT / "research" / "sources" / "datasets"
                    / "cwc_kerala_daily_discharge_2001_2025.csv")


def load_neeleeswaram_discharge() -> pd.Series:
    df = pd.read_csv(NEELEESWARAM_CSV)
    n = df[df["Station"].str.upper() == "NEELEESWARAM"].copy()
    n["date"] = pd.to_datetime(
        n["Data Acquisition Time"], format="%d-%m-%Y %H:%M", errors="coerce",
    ).dt.normalize()
    n = n.dropna(subset=["date"])
    col = "Manual Daily River Water Discharge (m3/sec)"
    # A handful of dates carry two independent readings that differ by a few
    # percent (re-processing, not a data-entry duplicate) - average them.
    return n.groupby("date")[col].mean()


def load_combined_release(cache_dir: Path) -> pd.Series:
    """Daily powerhouse + spillway discharge, Idukki and Idamalayar summed."""
    total = None
    for name in ("Idukki", "Idamalayar"):
        rec = load_dam(name, cache_dir=cache_dir)
        f = rec.clean().set_index("date")
        release = (pd.to_numeric(f["powerhouse_cumecs"], errors="coerce").fillna(0)
                   + pd.to_numeric(f["spillway_cumecs"], errors="coerce").fillna(0))
        total = release if total is None else total.add(release, fill_value=0)
    return total


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--cache-dir", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "processed")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    if not NEELEESWARAM_CSV.exists():
        print(f"missing {NEELEESWARAM_CSV} - run: python scripts/acquire.py", file=sys.stderr)
        return 1

    outflow_raw = load_neeleeswaram_discharge()
    inflow_raw = load_combined_release(args.cache_dir)

    start = max(inflow_raw.index.min(), outflow_raw.index.min())
    end = min(inflow_raw.index.max(), outflow_raw.index.max())
    idx = pd.date_range(start, end, freq="D")
    print(f"calibration window: {start.date()} to {end.date()} ({len(idx)} days)")

    outflow = outflow_raw.reindex(idx)
    inflow = inflow_raw.reindex(idx)

    missing_out = int(outflow.isna().sum())
    gaps = outflow.isna()
    longest_gap = 0
    if gaps.any():
        run = 0
        for v in gaps:
            run = run + 1 if v else 0
            longest_gap = max(longest_gap, run)
    print(f"Neeleeswaram missing {missing_out}/{len(idx)} days "
          f"({100 * missing_out / len(idx):.1f}%), longest gap {longest_gap} days")

    outflow = outflow.interpolate(limit_direction="both")
    inflow = inflow.interpolate(limit_direction="both")

    k_hours, x, r2 = MuskingumReach.calibrate(
        inflow.to_numpy(), outflow.to_numpy(), dt_hours=24.0,
    )

    old_k = REACHES["periyar_upper"].k_hours + REACHES["periyar_lower"].k_hours
    old_x_upper, old_x_lower = REACHES["periyar_upper"].x, REACHES["periyar_lower"].x

    print(f"\nfitted:    K = {k_hours:.1f} h, x = {x:.2f}, r2 = {r2:.3f}")
    print(f"CWC anchor: K = {old_k:.1f} h (periyar_upper {REACHES['periyar_upper'].k_hours}h "
          f"+ periyar_lower {REACHES['periyar_lower'].k_hours}h), "
          f"x = {old_x_upper}/{old_x_lower} (length-apportioned, unmeasured)")

    result = {
        "window": [str(start.date()), str(end.date())],
        "n_days": len(idx),
        "neeleeswaram_missing_days": missing_out,
        "neeleeswaram_longest_gap_days": longest_gap,
        "fitted_k_hours": round(float(k_hours), 2),
        "fitted_x": round(float(x), 3),
        "r_squared": round(float(r2), 3),
        "cwc_anchor_k_hours": old_k,
        "cwc_anchor_x_upper": old_x_upper,
        "cwc_anchor_x_lower": old_x_lower,
        "dt_hours": 24.0,
        "caveat": "daily resolution cannot precisely resolve an ~8h travel "
                  "time (dt=24h is ~3x coarser than the quantity being "
                  "measured); this fit is an order-of-magnitude and "
                  "attenuation-shape check, not an hour-level replacement "
                  "for the CWC anchor",
    }
    out_json = args.out / "routing_calibration_neeleeswaram.json"
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nwritten -> {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
