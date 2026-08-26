"""Fetch and cache the public Kerala dam dataset.

Prints a data-quality report for every dam, because roughly 11% of this feed
is physically impossible and using it unvalidated silently corrupts the
level-storage calibration. See docs/data-sources.md.

    python scripts/fetch_data.py
    python scripts/fetch_data.py --dams Idukki Idamalayar --refresh
    python scripts/fetch_data.py --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from aquasync.io.kseb_dataset import load_dam, load_live  # noqa: E402

ALL_DAMS = [
    "Anathode", "Anayirankal", "Banasura_Sagar", "Chenkulam", "Erattayar",
    "Idamalayar", "Idukki", "Kakkayam", "Kallar", "Kallarkutty", "Kundala",
    "Mattupetty", "Moozhiyar", "Pamba", "Pambla", "Ponmudi", "Poringalkuthu",
    "Sholayar",
]

# The Periyar basin pair - the two reservoirs this project actually models.
DEFAULT_DAMS = ["Idukki", "Idamalayar"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dams", nargs="+", default=DEFAULT_DAMS)
    ap.add_argument("--all", action="store_true", help="fetch every dam in the feed")
    ap.add_argument("--refresh", action="store_true", help="ignore the local cache")
    ap.add_argument("--cache-dir", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--skip-live", action="store_true")
    args = ap.parse_args()

    dams = ALL_DAMS if args.all else args.dams
    args.cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"cache: {args.cache_dir}\n")
    failures = 0

    for dam in dams:
        try:
            rec = load_dam(dam, cache_dir=args.cache_dir, refresh=args.refresh)
        except Exception as exc:  # noqa: BLE001 - one bad dam must not stop the rest
            print(f"  {dam:<16} FAILED: {exc}")
            failures += 1
            continue

        q = rec.quality_report()
        usable = q["usable_range"] or ("-", "-")
        flag = "!" if q["failed_pct"] > 5 else " "
        print(
            f"{flag} {rec.name:<16} {q['total_rows']:>5} rows  "
            f"{usable[0]} to {usable[1]}  "
            f"| {q['failed_validation']:>4} invalid ({q['failed_pct']:>5.2f}%)"
            f"  {q['unparseable_dates_dropped']} bad dates"
        )

    if not args.skip_live:
        try:
            live = load_live(cache_dir=args.cache_dir)
            print(f"\nlive bulletin: {len(live)} dams, as of {live['as_of'].iloc[0]}")
            spilling = live[live["spillway_cumecs"].fillna(0) > 0]
            if len(spilling):
                print("  currently spilling:")
                for _, r in spilling.iterrows():
                    print(f"    {r['name']:<16} {r['spillway_cumecs']:>8.1f} cumecs"
                          f"  ({r['storage_pct']:.1f}% full)")
            else:
                print("  no dam is currently spilling")
        except Exception as exc:  # noqa: BLE001
            print(f"\nlive bulletin unavailable: {exc}")

    print(
        "\nNote: rows marked invalid report live storage above the reservoir's\n"
        "physical capacity, or storage percentages over 100%. They are flagged,\n"
        "not dropped - call .clean() for the usable subset. Fitting on the raw\n"
        "feed degrades the Idukki level-storage curve from r2 0.996 to 0.784.\n"
        "See docs/data-sources.md."
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
