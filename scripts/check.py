"""One command that verifies everything this project promises about itself.

    python scripts/check.py           # everything
    python scripts/check.py --fast    # source-only checks (no data/raw needed)

The project makes four claims in its own documentation. Each is checked here
rather than trusted:

1. **The code is clean.** ruff over backend/ and scripts/, and the full test
   suite. Same gates CI runs.
2. **No document silently drops characters.** The dossier and the research
   report render through reportlab's base-14 fonts, which have no glyph for
   arrows, Greek or stars - and drop them *without erroring*. That is not
   hypothetical: the layer diagram on page 5 lost every arrow and connector,
   the hydropower formula rendered as "gQH", and GitHub star counts appeared
   as bare numbers, all silently. Scripts that register a Unicode font are
   exempt automatically.
3. **Every figure and document regenerates from scripts/.** Regenerating must
   not change anything on disk. If it does, the committed artefact is stale -
   somebody edited a builder and did not rebuild.
4. **The builders are deterministic.** Building twice must produce
   byte-identical files, so a diff means a real change rather than a rebuild.

Checks 3 and 4 need the bulletin cache in data/raw/, which is gitignored, so
they run locally and are skipped by --fast (which is what CI uses).
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FIGURES = ROOT / "scripts" / "make_figures.py"
BUILDERS = [
    ROOT / "scripts" / "build_dossier.py",
    ROOT / "scripts" / "build_abstract.py",
    ROOT / "scripts" / "build_icfoss_analysis.py",
    ROOT / "scripts" / "build_research_report.py",
]
ARTEFACTS = [
    ROOT / "docs" / "assets",
    ROOT / "docs",
    ROOT / "data" / "processed",
]
ARTEFACT_SUFFIXES = {".png", ".pdf", ".json", ".csv"}

GREEN, RED, DIM, OFF = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def say(ok: bool, label: str, detail: str = "") -> bool:
    mark = f"{GREEN}PASS{OFF}" if ok else f"{RED}FAIL{OFF}"
    print(f"  [{mark}] {label}" + (f"\n         {detail}" if detail else ""))
    return ok


def run(cmd: list[str], label: str) -> bool:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if p.returncode == 0:
        return say(True, label)
    tail = (p.stdout + p.stderr).strip().splitlines()
    return say(False, label, "\n         ".join(tail[-12:]))


# --------------------------------------------------------------------------
# 2 - glyphs the base-14 fonts would drop without saying so
# --------------------------------------------------------------------------

def check_glyphs() -> bool:
    ok = True
    for script in BUILDERS:
        if not script.exists():
            continue
        src = script.read_text(encoding="utf-8")
        if "registerFont" in src:
            continue  # embeds a Unicode face, so it can render anything
        bad: dict[int, list[int]] = {}
        for i, line in enumerate(src.splitlines(), 1):
            for ch in line:
                try:
                    ch.encode("cp1252")
                except UnicodeEncodeError:
                    bad.setdefault(ord(ch), []).append(i)
        if bad:
            detail = "; ".join(
                f"U+{cp:04X} on line{'s' if len(ls) > 1 else ''} "
                f"{', '.join(str(x) for x in sorted(set(ls))[:5])}"
                for cp, ls in sorted(bad.items())
            )
            ok = say(False, f"glyphs renderable: {script.name}",
                     f"{detail}\n         these render as nothing at all - say it in words, "
                     f"or register a Unicode font")
        else:
            ok = say(True, f"glyphs renderable: {script.name}") and ok
    return ok


# --------------------------------------------------------------------------
# 3 and 4 - regeneration and determinism
# --------------------------------------------------------------------------

def snapshot() -> dict[Path, str]:
    out: dict[Path, str] = {}
    for d in ARTEFACTS:
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if f.is_file() and f.suffix in ARTEFACT_SUFFIXES:
                out[f] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def rebuild(label: str) -> bool:
    for script in [FIGURES, *BUILDERS]:
        if not script.exists():
            continue
        p = subprocess.run([sys.executable, str(script)], cwd=ROOT,
                           capture_output=True, text=True)
        if p.returncode != 0:
            tail = (p.stdout + p.stderr).strip().splitlines()[-10:]
            say(False, f"{label}: {script.name} failed", "\n         ".join(tail))
            return False
    return True


def changed(before: dict[Path, str], after: dict[Path, str]) -> list[str]:
    names = []
    for f, h in after.items():
        if f not in before:
            names.append(f"{f.name} (new)")
        elif before[f] != h:
            names.append(f.name)
    return sorted(names)


def check_regeneration() -> bool:
    before = snapshot()
    if not rebuild("regeneration"):
        return False
    diff = changed(before, snapshot())
    # A brand-new artefact is expected the first time a study is added.
    stale = [d for d in diff if not d.endswith("(new)")]
    if stale:
        return say(False, "artefacts match their source",
                   f"regenerating changed: {', '.join(stale)}\n         "
                   f"the committed version was built from older code - commit the rebuild")
    return say(True, "artefacts match their source")


def check_determinism() -> bool:
    before = snapshot()
    if not rebuild("determinism"):
        return False
    diff = changed(before, snapshot())
    if diff:
        return say(False, "builders are deterministic",
                   f"a second identical build changed: {', '.join(diff)}\n         "
                   f"something embeds a timestamp - pass invariant=1 to the canvas")
    return say(True, "builders are deterministic")


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fast", action="store_true",
                    help="source-only checks; skips anything needing data/raw")
    args = ap.parse_args()

    print(f"\n{DIM}AquaSync self-check{OFF}\n")
    results = [
        run([sys.executable, "-m", "ruff", "check", "backend/", "scripts/"], "lint"),
        run([sys.executable, "-m", "pytest", "backend/tests", "-q"], "tests"),
        check_glyphs(),
    ]

    if args.fast:
        print(f"\n{DIM}  skipped (--fast): regeneration, determinism{OFF}")
    else:
        results += [check_regeneration(), check_determinism()]

    failed = results.count(False)
    print()
    if failed:
        print(f"{RED}{failed} check(s) failed{OFF}\n")
        return 1
    print(f"{GREEN}all checks passed{OFF}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
