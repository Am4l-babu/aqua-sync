"""Fetch everything in the research manifest into research/, and index it.

Reads ``research/index/manifest.json`` (produced by the deep-research
workflow, or hand-edited) and acquires each entry by the method it declares:

    git-shallow-clone   depth-1 clone, history discarded
    curl                direct file download
    api                 JSON API call, pretty-printed to disk
    manual-registration recorded but NOT fetched - a human must sign up

Everything is verified before it is recorded: a clone must produce files, a
download must be non-empty and match its expected type. Failures are logged
rather than swallowed, because a research index that silently lists things it
did not actually get is worse than no index.

    python scripts/acquire.py                 # fetch everything
    python scripts/acquire.py --priority high # only the important ones
    python scripts/acquire.py --dry-run
    python scripts/acquire.py --index-only    # rebuild the index, fetch nothing
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import textwrap
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"
INDEX_DIR = RESEARCH / "index"
MANIFEST = INDEX_DIR / "manifest.json"
LOG = INDEX_DIR / "acquisition_log.json"

UA = "Mozilla/5.0 (compatible; AquaSync-research/0.1)"
MAX_CLONE_MB = 150        # cap on the COMPRESSED tarball, not the extracted tree
TIMEOUT = 120


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def human(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024 or unit == "GB":
            return f"{nbytes:.0f} {unit}" if unit == "B" else f"{nbytes:.1f} {unit}"
        nbytes /= 1024.0
    return f"{nbytes:.1f} GB"


def dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def run(cmd: list[str], cwd: Path | None = None, timeout: int = TIMEOUT) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
        return p.returncode, (p.stdout + p.stderr)[-2000:]
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except FileNotFoundError as exc:
        return 127, str(exc)


# --------------------------------------------------------------------------
# acquisition methods
# --------------------------------------------------------------------------

def _github_slug(url: str) -> str | None:
    """OWNER/NAME from a GitHub URL, or None if it is not GitHub."""
    u = url.rstrip("/").removesuffix(".git")
    if "github.com/" not in u:
        return None
    parts = u.split("github.com/", 1)[1].split("/")
    return "/".join(parts[:2]) if len(parts) >= 2 else None


def acquire_clone(entry: dict, dest: Path) -> dict:
    """Snapshot a repository by extracting its tarball, not by cloning.

    Two Windows-specific reasons this beats ``git clone --depth 1``:

    1. Repos containing filenames illegal on Windows abort the whole
       checkout. NOAA-OWP/t-route ships USGS timeslice files named
       ``2023-04-02_23:30:00...ncdf`` - a colon, which NTFS forbids - and
       git leaves an empty directory rather than the other 1,150 files.
       ``tar`` skips the offending entries and extracts the rest.
    2. No ``.git`` directory is created, so nothing has to be deleted
       afterwards. Deleting ``.git`` on Windows frequently fails on locked
       pack files, which previously left half-removed stubs behind.

    These are reference snapshots, not working checkouts. To contribute
    upstream, clone the project properly from its own URL.
    """
    if dest.exists() and sum(1 for _ in dest.rglob("*") if _.is_file()) > 3:
        return {"status": "already-present", "bytes": dir_size(dest)}

    slug = _github_slug(entry["url"])
    if slug is None:
        return {"status": "failed", "error": "not a GitHub URL; fetch manually"}

    tarball = f"https://api.github.com/repos/{slug}/tarball/HEAD"
    tmp = dest.parent / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    archive = tmp / f"{dest.name}.tar.gz"

    req = urllib.request.Request(tarball, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            archive.write_bytes(resp.read())
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "error": f"tarball download failed: {type(exc).__name__}: {exc}"}

    if archive.stat().st_size > MAX_CLONE_MB * 1024 * 1024:
        size = archive.stat().st_size
        archive.unlink(missing_ok=True)
        return {
            "status": "skipped-too-large",
            "bytes": size,
            "error": f"compressed tarball is {human(size)}, over the {MAX_CLONE_MB} MB cap",
        }

    dest.mkdir(parents=True, exist_ok=True)
    # tar reports the entries it had to skip on stderr but still exits
    # non-zero, so the file count is the real success signal, not the code.
    run(["tar", "-xzf", str(archive), "-C", str(dest), "--strip-components=1"], timeout=300)
    archive.unlink(missing_ok=True)

    files = sum(1 for _ in dest.rglob("*") if _.is_file())
    if files == 0:
        return {"status": "failed", "error": "archive extracted no files"}

    return {"status": "ok", "bytes": dir_size(dest), "files": files}


def acquire_curl(entry: dict, dest: Path) -> dict:
    """Direct download of a single file."""
    if dest.exists() and dest.stat().st_size > 0:
        return {"status": "already-present", "bytes": dest.stat().st_size}

    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(entry["url"], headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            payload = resp.read()
            ctype = resp.headers.get("Content-Type", "")
    except Exception as exc:  # noqa: BLE001 - one bad URL must not stop the run
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    if not payload:
        return {"status": "failed", "error": "empty response"}

    # A PDF that is actually an HTML login page is the classic silent failure.
    if dest.suffix.lower() == ".pdf" and not payload.startswith(b"%PDF"):
        return {
            "status": "failed",
            "error": f"expected a PDF, got {ctype or 'unknown type'} "
                     f"(likely a login or landing page - needs manual download)",
        }

    dest.write_bytes(payload)
    return {"status": "ok", "bytes": len(payload), "content_type": ctype}


def acquire_api(entry: dict, dest: Path) -> dict:
    """JSON API call, pretty-printed so it is readable and diffable."""
    if dest.exists() and dest.stat().st_size > 0:
        return {"status": "already-present", "bytes": dest.stat().st_size}

    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(entry["url"], headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"status": "ok", "bytes": dest.stat().st_size}


METHODS = {
    "git-shallow-clone": acquire_clone,
    "git": acquire_clone,
    "clone": acquire_clone,
    "curl": acquire_curl,
    "download": acquire_curl,
    "api": acquire_api,
}


# --------------------------------------------------------------------------
# index
# --------------------------------------------------------------------------

def build_index(manifest: list[dict], results: dict) -> str:
    """Render research/index/README.md - the browsable front door."""
    by_status: dict[str, list] = {}
    for e in manifest:
        st = results.get(e["name"], {}).get("status", "not-attempted")
        by_status.setdefault(st, []).append(e)

    got = by_status.get("ok", []) + by_status.get("already-present", [])
    manual = by_status.get("manual-registration", [])
    failed = by_status.get("failed", []) + by_status.get("skipped-too-large", [])

    total_bytes = sum(results.get(e["name"], {}).get("bytes", 0) for e in got)

    lines = [
        "# Research index",
        "",
        "Everything the deep-research sweep found, acquired and verified.",
        "Regenerate with `python scripts/acquire.py --index-only`.",
        "",
        f"**{len(got)} acquired** ({human(total_bytes)}) · "
        f"**{len(manual)} need manual registration** · "
        f"**{len(failed)} unavailable**",
        "",
        f"Last run: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "---",
        "",
        "## Acquired",
        "",
        "| Resource | Kind | Local path | Size | Source |",
        "|---|---|---|---|---|",
    ]
    for e in sorted(got, key=lambda x: (x.get("priority", "z"), x["name"])):
        r = results.get(e["name"], {})
        lines.append(
            f"| {e['name']} | {e.get('kind', '—')} | `{e['destination']}` | "
            f"{human(r.get('bytes', 0))} | [link]({e['url']}) |"
        )

    if manual:
        lines += [
            "", "---", "",
            "## Needs manual registration",
            "",
            "These require a human to create an account or accept terms. The URL and",
            "what to ask for are recorded so the step is quick.",
            "",
            "| Resource | What to get | Where |",
            "|---|---|---|",
        ]
        for e in sorted(manual, key=lambda x: x["name"]):
            lines.append(f"| {e['name']} | {e.get('note', e.get('kind', '—'))} | [link]({e['url']}) |")

    if failed:
        lines += [
            "", "---", "",
            "## Unavailable",
            "",
            "Recorded so the same ground is not covered twice.",
            "",
            "| Resource | Why | Source |",
            "|---|---|---|",
        ]
        for e in sorted(failed, key=lambda x: x["name"]):
            r = results.get(e["name"], {})
            why = r.get("error", r.get("status", "unknown"))
            lines.append(f"| {e['name']} | {why} | [link]({e['url']}) |")

    lines += [
        "", "---", "",
        "## Layout",
        "",
        "```",
        "research/",
        "  index/        this index, the manifest, and the acquisition log",
        "  raw/          per-dimension research findings as JSON",
        "  repos/        shallow snapshots of relevant open-source projects",
        "  sources/",
        "    papers/     downloadable papers and reports",
        "    datasets/   data files small enough to keep in the repo",
        "```",
        "",
        "`.git` directories are stripped from cloned snapshots - these are",
        "reference copies, not working checkouts. To contribute upstream, clone",
        "the project properly from its own URL.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--priority", choices=["high", "medium", "low"], default=None,
                    help="only fetch at or above this priority")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--index-only", action="store_true")
    args = ap.parse_args()

    if not args.manifest.exists():
        print(f"no manifest at {args.manifest}", file=sys.stderr)
        return 1

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if isinstance(manifest, dict):
        manifest = manifest.get("download_manifest", [])

    rank = {"high": 0, "medium": 1, "low": 2}
    if args.priority:
        cutoff = rank[args.priority]
        manifest = [e for e in manifest if rank.get(e.get("priority", "low"), 2) <= cutoff]

    results: dict[str, dict] = {}
    if LOG.exists() and args.index_only:
        results = json.loads(LOG.read_text(encoding="utf-8"))

    if not args.index_only:
        print(f"acquiring {len(manifest)} resources into {RESEARCH}\n")
        for i, entry in enumerate(manifest, 1):
            name = entry["name"]
            method = entry.get("method", "curl")
            dest = ROOT / entry["destination"]

            if method == "manual-registration":
                results[name] = {"status": "manual-registration"}
                print(f"[{i:>2}/{len(manifest)}] {name:<44} needs registration")
                continue

            fn = METHODS.get(method)
            if fn is None:
                results[name] = {"status": "failed", "error": f"unknown method: {method}"}
                print(f"[{i:>2}/{len(manifest)}] {name:<44} unknown method {method}")
                continue

            if args.dry_run:
                print(f"[{i:>2}/{len(manifest)}] {name:<44} would {method} -> {entry['destination']}")
                continue

            res = fn(entry, dest)
            results[name] = res
            mark = {"ok": "ok", "already-present": "cached"}.get(res["status"], res["status"])
            detail = human(res["bytes"]) if res.get("bytes") else res.get("error", "")
            print(f"[{i:>2}/{len(manifest)}] {name:<44} {mark:<18} {detail[:70]}")

        if not args.dry_run:
            INDEX_DIR.mkdir(parents=True, exist_ok=True)
            LOG.write_text(json.dumps(results, indent=2), encoding="utf-8")

    if not args.dry_run:
        (INDEX_DIR / "README.md").write_text(build_index(manifest, results), encoding="utf-8")
        ok = sum(1 for r in results.values() if r.get("status") in ("ok", "already-present"))
        print(f"\n{ok}/{len(manifest)} acquired")
        print(f"index -> {INDEX_DIR / 'README.md'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
