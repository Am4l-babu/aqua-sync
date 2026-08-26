"""Harvest completed agent results from a workflow run into research/.

The deep-research sweep is long-running, and its results live in the
workflow cache until the whole run finishes. That cache is session-scoped: if
the session ends, anything not yet written to disk is lost.

This script reads the run journal and writes every completed result out as a
file, so partial progress survives. Safe to run repeatedly at any point,
including while the workflow is still going.

    python scripts/harvest_research.py                    # newest run
    python scripts/harvest_research.py --run wf_009a6299  # a specific run
    python scripts/harvest_research.py --list             # what is on disk
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "research" / "raw"
INDEX = ROOT / "research" / "index"

WORKFLOW_ROOT = (
    Path.home() / ".claude" / "projects" / "d--aqua-sync"
)

# The stable domain keys the workflow researches. Agents report a long
# free-text dimension title, so map it back to one of these.
DOMAINS = [
    "historical-data",
    "reservoir-optimisation",
    "hydro-modeling",
    "ml-hydrology",
    "soa-limitations",
    "integration",
]

KEYMAP = [
    ("historical", "historical-data"),
    ("pre-2020", "historical-data"),
    ("firo", "reservoir-optimisation"),
    ("reservoir operation", "reservoir-optimisation"),
    ("reservoir optimis", "reservoir-optimisation"),
    ("scada", "integration"),
    ("integrat", "integration"),
    ("routing", "hydro-modeling"),
    ("hydraulic", "hydro-modeling"),
    ("inundation", "hydro-modeling"),
    ("machine learning", "ml-hydrology"),
    ("digital twin framework", "ml-hydrology"),
    ("forecasting", "ml-hydrology"),
    ("state of the art", "soa-limitations"),
    ("deployed", "soa-limitations"),
    ("limitations", "soa-limitations"),
]


def to_key(text: str) -> str:
    t = (text or "").lower()
    for needle, key in KEYMAP:
        if needle in t:
            return key
    return re.sub(r"[^a-z0-9]+", "-", t)[:40].strip("-") or "unknown"


def find_runs() -> list[Path]:
    """All workflow run directories, newest first."""
    runs = list(WORKFLOW_ROOT.glob("*/subagents/workflows/wf_*"))
    return sorted(runs, key=lambda p: p.stat().st_mtime, reverse=True)


def harvest(run_dir: Path) -> list[tuple[str, str, int]]:
    journal = run_dir / "journal.jsonl"
    if not journal.exists():
        return []

    RAW.mkdir(parents=True, exist_ok=True)
    saved: list[tuple[str, str, int]] = []

    for line in journal.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "result":
            continue

        result = entry.get("result") or entry.get("value") or {}
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                continue
        if not isinstance(result, dict):
            continue

        # The verify stage supersedes research for the same domain, so name
        # the files by stage and let the report builder prefer verified.
        stage = "verify" if "confirmed_sources" in result else (
            "synthesis" if "prioritised_upgrades" in result else "research"
        )
        key = "synthesis" if stage == "synthesis" else to_key(result.get("dimension", ""))
        result["_dimension_key"] = key
        result["_stage"] = stage
        result["_run"] = run_dir.name

        path = RAW / f"{key}.{stage}.json"
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        n = len(result.get("sources") or result.get("confirmed_sources") or [])
        saved.append((key, stage, n))

    return saved


def status() -> dict:
    """Which domains are done, and at what stage."""
    RAW.mkdir(parents=True, exist_ok=True)
    have = {d: None for d in DOMAINS}
    for f in RAW.glob("*.json"):
        parts = f.stem.rsplit(".", 1)
        if len(parts) != 2:
            continue
        key, stage = parts
        if key in have:
            # verify beats research
            if have[key] != "verify":
                have[key] = stage
    return have


def build_findings() -> Path:
    """Assemble research_findings.json for the report builder."""
    dims, synthesis = [], None
    for key in DOMAINS:
        v = RAW / f"{key}.verify.json"
        r = RAW / f"{key}.research.json"
        if v.exists():
            dims.append(json.loads(v.read_text(encoding="utf-8")))
        elif r.exists():
            # Promote an unverified research result into the same shape, and
            # label it clearly so the report cannot present it as verified.
            d = json.loads(r.read_text(encoding="utf-8"))
            dims.append({
                "dimension": d.get("dimension", key),
                "confirmed_sources": [
                    {**s, "content_matches_claim": "not independently verified"}
                    for s in d.get("sources", [])
                ],
                "rejected": [],
                "verification_notes": [
                    "This domain has NOT been through the adversarial verification "
                    "pass. URLs carry the researching agent's own reported status "
                    "only. Treat as provisional."
                ] + [f"dead end: {x}" for x in d.get("dead_ends", [])],
                "_unverified": True,
            })
    s = RAW / "synthesis.synthesis.json"
    if s.exists():
        synthesis = json.loads(s.read_text(encoding="utf-8"))

    INDEX.mkdir(parents=True, exist_ok=True)
    out = INDEX / "research_findings.json"
    out.write_text(
        json.dumps({"dimensions": dims, "synthesis": synthesis or {}},
                   indent=2, ensure_ascii=False),
        encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", help="workflow run id prefix; default is the newest")
    ap.add_argument("--list", action="store_true", help="show what is already on disk")
    args = ap.parse_args()

    if not args.list:
        runs = find_runs()
        if args.run:
            runs = [r for r in runs if r.name.startswith(args.run)]
        if not runs:
            print("no workflow runs found", file=sys.stderr)
            return 1
        run = runs[0]
        print(f"harvesting {run.name}")
        saved = harvest(run)
        for key, stage, n in saved:
            print(f"  {key:<26} {stage:<10} {n:>3} sources")
        if not saved:
            print("  (no completed results yet)")

    print("\ndomain status:")
    st = status()
    for key, stage in st.items():
        mark = {"verify": "verified", "research": "research only", None: "MISSING"}[stage]
        print(f"  {key:<26} {mark}")

    missing = [k for k, v in st.items() if v is None]
    unverified = [k for k, v in st.items() if v == "research"]

    findings = build_findings()
    print(f"\nwrote {findings}")

    if missing:
        print(f"\nstill to research: {', '.join(missing)}")
    if unverified:
        print(f"researched but NOT verified: {', '.join(unverified)}")
    if not missing and not unverified and (RAW / 'synthesis.synthesis.json').exists():
        print("\nall domains complete and verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
