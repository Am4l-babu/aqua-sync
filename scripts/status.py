"""AquaSync project status - one command, one screen.

    python scripts/status.py            # full board
    python scripts/status.py --watch    # refresh every 5s
    python scripts/status.py --brief    # one-line summary

Reads the real state of the repo rather than a hand-maintained checklist:
PROGRESS.md for component status, research/raw for the research sweep,
research/index/acquisition_log.json for downloads, and git for sync state.
If a thing is not actually on disk, it does not show as done.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "research" / "raw"
INDEX = ROOT / "research" / "index"

# The Windows console still defaults to cp1252, which cannot encode the block
# and bullet characters below. Try to switch the stream to UTF-8; if that is
# refused, fall back to an ASCII glyph set rather than crashing. A status tool
# that dies on its own output is worse than an ugly one.
UNICODE_OK = True
try:
    sys.stdout.reconfigure(encoding="utf-8")
    "█░●○·─".encode(sys.stdout.encoding or "utf-8")
except (AttributeError, LookupError, UnicodeEncodeError, ValueError):
    UNICODE_OK = False


class G:
    """Glyphs, with an ASCII fallback for legacy consoles."""

    FULL = "█" if UNICODE_OK else "#"
    EMPTY = "░" if UNICODE_OK else "."
    DASH = "─" if UNICODE_OK else "-"
    DOT = "·" if UNICODE_OK else "-"
    ON = "●" if UNICODE_OK else "*"
    OFF = "○" if UNICODE_OK else "o"

# ANSI. Windows Terminal and modern conhost handle these; --no-colour opts out.
class C:
    R = "\033[0m"
    B = "\033[1m"
    DIM = "\033[2m"
    GRN = "\033[38;5;35m"
    AMB = "\033[38;5;178m"
    RED = "\033[38;5;167m"
    BLU = "\033[38;5;75m"
    GRY = "\033[38;5;245m"
    VIO = "\033[38;5;140m"

    @classmethod
    def off(cls):
        for k in dir(cls):
            if k.isupper():
                setattr(cls, k, "")


DOMAINS = [
    "historical-data", "reservoir-optimisation", "hydro-modeling",
    "ml-hydrology", "soa-limitations", "integration",
]

WIDTH = 68


def bar(done: int, total: int, width: int = 28, colour: str | None = None) -> str:
    """A progress bar that shows the fraction, not just a vibe."""
    if total == 0:
        return f"{C.GRY}{'─' * width}{C.R}  n/a"
    filled = round(width * done / total)
    pct = 100 * done / total
    shade = C.GRN if pct >= 99 else C.AMB if pct >= 50 else C.RED
    if colour is not None:
        shade = colour
    return (f"{shade}{'█' * filled}{C.GRY}{'░' * (width - filled)}{C.R} "
            f"{C.B}{done}/{total}{C.R} {C.GRY}({pct:.0f}%){C.R}")


def sh(cmd: list[str]) -> str:
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=20)
        return p.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def head(title: str) -> str:
    return f"\n{C.B}{title}{C.R}\n{C.GRY}{G.DASH * WIDTH}{C.R}"


# --------------------------------------------------------------------------
# collectors
# --------------------------------------------------------------------------

def progress_md() -> dict[str, tuple[int, int]]:
    """Parse PROGRESS.md tables into per-section (done, total) counts."""
    p = ROOT / "PROGRESS.md"
    if not p.exists():
        return {}
    out: dict[str, tuple[int, int]] = {}
    section = None
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            if section.lower().startswith(("status legend", "open risks", "verified facts")):
                section = None
        elif section and line.startswith("| ") and "|" in line[2:]:
            if "---" in line or line.startswith("| Component"):
                continue
            done, total = out.get(section, (0, 0))
            total += 1
            if "✅" in line:
                done += 1
            out[section] = (done, total)
    return out


def research_state() -> dict[str, str]:
    state = {d: "missing" for d in DOMAINS}
    if RAW.exists():
        for f in RAW.glob("*.json"):
            parts = f.stem.rsplit(".", 1)
            if len(parts) == 2 and parts[0] in state:
                key, stage = parts
                if stage == "verify":
                    state[key] = "verified"
                elif state[key] == "missing":
                    state[key] = "research"
    return state


def acquisition() -> tuple[int, int, float]:
    log = INDEX / "acquisition_log.json"
    man = INDEX / "manifest.json"
    total = 0
    if man.exists():
        m = json.loads(man.read_text(encoding="utf-8"))
        total = len(m.get("download_manifest", m) if isinstance(m, dict) else m)
    if not log.exists():
        return 0, total, 0.0
    d = json.loads(log.read_text(encoding="utf-8"))
    got = [r for r in d.values() if r.get("status") in ("ok", "already-present")]
    return len(got), total, sum(r.get("bytes", 0) for r in got) / 1e6


def tests() -> tuple[int, str]:
    """Count test functions statically - running pytest here would be slow."""
    f = ROOT / "backend" / "tests" / "test_twin.py"
    if not f.exists():
        return 0, "no test file"
    n = len(re.findall(r"^\s+def test_", f.read_text(encoding="utf-8"), re.M))
    return n, "run: cd backend && python -m pytest tests/ -q"


def git_state() -> dict:
    branch = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    dirty = len([x for x in sh(["git", "status", "--porcelain"]).splitlines() if x])
    unpushed = len(sh(["git", "log", f"origin/{branch}..{branch}", "--oneline"]).splitlines()) \
        if branch else 0
    ahead = sh(["git", "rev-list", "--count", "origin/main..origin/development"]) or "0"
    return {"branch": branch, "dirty": dirty, "unpushed": unpushed, "ahead_of_main": ahead}


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------

def render() -> str:
    L: list[str] = []
    L.append(f"\n{C.B}{C.BLU}  AquaSync{C.R}{C.GRY}  ·  Periyar dam-river digital twin{C.R}")

    # -- components -----------------------------------------------------
    L.append(head("COMPONENTS"))
    secs = progress_md()
    tot_d = tot_t = 0
    for name, (d, t) in secs.items():
        tot_d += d
        tot_t += t
        L.append(f"  {name:<22} {bar(d, t)}")
    if tot_t:
        L.append(f"  {C.DIM}{'overall':<22}{C.R} {bar(tot_d, tot_t)}")

    # -- research -------------------------------------------------------
    L.append(head("DEEP RESEARCH"))
    rs = research_state()
    ver = sum(1 for v in rs.values() if v == "verified")
    res = sum(1 for v in rs.values() if v == "research")
    L.append(f"  {'domains verified':<22} {bar(ver, len(DOMAINS))}")
    for k, v in rs.items():
        mark = {"verified": f"{C.GRN}verified{C.R}",
                "research": f"{C.AMB}unverified{C.R}",
                "missing": f"{C.RED}missing{C.R}"}[v]
        L.append(f"    {C.GRY}·{C.R} {k:<24} {mark}")
    if res:
        L.append(f"  {C.AMB}{res} domain(s) researched but not adversarially verified{C.R}")

    syn = (RAW / "synthesis.synthesis.json").exists()
    L.append(f"  {'synthesis':<22} "
             f"{C.GRN + 'complete' + C.R if syn else C.RED + 'pending' + C.R}")

    got, total, mb = acquisition()
    L.append(f"  {'downloads':<22} {bar(got, total)}  {C.GRY}{mb:,.0f} MB{C.R}")

    # -- deliverables ---------------------------------------------------
    L.append(head("DELIVERABLES"))
    for label, rel in [
        ("Project dossier", "docs/AquaSync_Project_Dossier.pdf"),
        ("Research report", "docs/AquaSync_Research_Report.pdf"),
        ("Figures", "docs/assets"),
        ("Research index", "research/index/README.md"),
    ]:
        p = ROOT / rel
        if p.is_dir():
            n = len(list(p.glob("*.png")))
            ok, detail = n > 0, f"{n} figures"
        else:
            ok = p.exists()
            detail = f"{p.stat().st_size / 1024:.0f} KB" if ok else "not built"
        dot = f"{C.GRN}●{C.R}" if ok else f"{C.RED}○{C.R}"
        L.append(f"  {dot} {label:<20} {C.GRY}{detail}{C.R}")

    n_tests, hint = tests()
    L.append(f"  {C.GRN}●{C.R} {'Tests':<20} {C.GRY}{n_tests} defined · {hint}{C.R}")

    # -- git ------------------------------------------------------------
    g = git_state()
    L.append(head("GIT"))
    clean = f"{C.GRN}clean{C.R}" if not g["dirty"] else f"{C.AMB}{g['dirty']} uncommitted{C.R}"
    push = f"{C.GRN}pushed{C.R}" if not g["unpushed"] else f"{C.AMB}{g['unpushed']} unpushed{C.R}"
    L.append(f"  branch {C.B}{g['branch']}{C.R}   {clean}   {push}")
    if g["ahead_of_main"] != "0":
        L.append(f"  {C.AMB}development is {g['ahead_of_main']} commit(s) ahead of main{C.R}")

    # -- next -----------------------------------------------------------
    L.append(head("NEXT"))
    nxt = []
    if rs.get("ml-hydrology") == "missing":
        nxt.append("ml-hydrology research still missing")
    if res:
        nxt.append(f"{res} domain(s) need verification")
    if g["dirty"]:
        nxt.append(f"{g['dirty']} uncommitted change(s)")
    if g["unpushed"]:
        nxt.append(f"{g['unpushed']} commit(s) to push")
    if g["ahead_of_main"] != "0":
        nxt.append(f"open PR development -> main ({g['ahead_of_main']} commits)")
    nxt.append("order V1 hardware (Rs 6,150, 3-5 day delivery)")
    nxt.append("forecast-error study - closes the perfect-foresight gap")
    for i, t in enumerate(nxt[:6], 1):
        L.append(f"  {C.GRY}{i}.{C.R} {t}")

    L.append("")
    return "\n".join(L)


def brief() -> str:
    rs = research_state()
    ver = sum(1 for v in rs.values() if v == "verified")
    got, total, mb = acquisition()
    secs = progress_md()
    d = sum(x[0] for x in secs.values())
    t = sum(x[1] for x in secs.values())
    g = git_state()
    return (f"components {d}/{t} · research {ver}/{len(DOMAINS)} verified · "
            f"downloads {got}/{total} ({mb:,.0f} MB) · "
            f"git {g['branch']} {'clean' if not g['dirty'] else str(g['dirty']) + ' dirty'}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--watch", action="store_true", help="refresh every 5 seconds")
    ap.add_argument("--brief", action="store_true", help="one line")
    ap.add_argument("--no-colour", action="store_true")
    args = ap.parse_args()

    if args.no_colour or not sys.stdout.isatty():
        C.off()

    if args.brief:
        print(brief())
        return 0

    if not args.watch:
        print(render())
        return 0

    try:
        while True:
            out = render()
            print("\033[2J\033[H" + out + f"\n{C.GRY}  watching · ctrl-c to stop{C.R}")
            time.sleep(5)
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
