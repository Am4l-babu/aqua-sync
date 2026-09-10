"""Drive the dashboard in headless Chrome over the DevTools protocol.

The one reliable way to look at the twin without a person at the screen.
Chrome's own ``--screenshot`` fires before the terrain has loaded more often
than not; this waits for the provenance caption, runs any JavaScript steps
you give it (click Play, set the storm multiple, read a badge), and only
then captures. Every "browser-verified" claim in PROGRESS.md since 11
September 2026 was made this way.

Usage::

    python scripts/drive_dashboard.py URL OUT.png [JS ...]

    # a screenshot of the site view
    python scripts/drive_dashboard.py http://localhost:8000/ docs/assets/dashboard_twin.png

    # open the drawer at hour 300 under the AquaSync schedule, wait for the
    # optimiser, read the badge, then capture
    python scripts/drive_dashboard.py "http://localhost:8000/?sim=1&trace=opt&hour=300" out.png \
        --wait-sim "document.getElementById('link-state').textContent"

Each JS step is evaluated in the page (promises are awaited) and its value
printed, with a one-second settle between steps. ``--wait-sim`` waits for
the simulation drawer to finish loading before the steps run. Needs Chrome
and the ``websocket-client`` package; prints to stdout as UTF-8 so Malayalam
survives a cp1252 console.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

CHROME_CANDIDATES = [
    r"C:/Program Files/Google/Chrome/Application/chrome.exe",
    r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]
PORT = 9333

WAIT_SIM = (
    "new Promise(r => { const t = setInterval(() => {"
    "  const c = document.getElementById('simv-state')?.textContent || '';"
    "  if (c !== 'RUNNING' && c !== '\u2026' && c !== '') { clearInterval(t); r(c); }"
    "}, 500); })"
)


def find_chrome() -> str:
    for c in CHROME_CANDIDATES:
        if Path(c).exists():
            return c
    found = shutil.which("chrome") or shutil.which("google-chrome") or shutil.which("chromium")
    if found:
        return found
    sys.exit("no Chrome found - install it or add its path to CHROME_CANDIDATES")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("url")
    ap.add_argument("out")
    ap.add_argument("steps", nargs="*", help="JavaScript to evaluate in the page, in order")
    ap.add_argument("--wait-sim", action="store_true",
                    help="wait for the simulation drawer to finish loading first")
    ap.add_argument("--size", default="1600x900")
    args = ap.parse_args()

    try:
        import websocket  # websocket-client
    except ImportError:
        sys.exit("pip install websocket-client")

    w, h = (int(v) for v in args.size.split("x"))
    profile = tempfile.mkdtemp(prefix="aquasync-chrome-")
    proc = subprocess.Popen([
        find_chrome(), "--headless=new", "--disable-gpu", "--use-angle=swiftshader",
        "--enable-unsafe-swiftshader", "--hide-scrollbars", f"--window-size={w},{h}",
        f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}", "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        page = None
        for _ in range(50):
            try:
                targets = json.load(urllib.request.urlopen(f"http://localhost:{PORT}/json"))
                page = next(t for t in targets if t["type"] == "page")
                break
            except Exception:  # noqa: BLE001 - Chrome is still starting
                time.sleep(0.2)
        if page is None:
            sys.exit("Chrome did not expose a page target")

        ws = websocket.create_connection(page["webSocketDebuggerUrl"], suppress_origin=True)
        seq = 0

        def call(method: str, **params):
            nonlocal seq
            seq += 1
            ws.send(json.dumps({"id": seq, "method": method, "params": params}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == seq:
                    return msg.get("result", {})

        def js(expr: str):
            r = call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
            return r.get("result", {}).get("value")

        call("Page.enable")
        call("Runtime.enable")
        call("Emulation.setDeviceMetricsOverride", width=w, height=h,
             deviceScaleFactor=1, mobile=False)
        call("Page.navigate", url=args.url)

        for _ in range(300):
            note = js("document.getElementById('scene-note')?.textContent || ''")
            if note.startswith("Terrain"):
                break
            time.sleep(0.2)
        else:
            print("WARN: terrain caption never appeared; capturing anyway")
        time.sleep(1.5)

        steps = ([WAIT_SIM] if args.wait_sim else []) + list(args.steps)
        for step in steps:
            print(f"> {step[:110]}\n  = {js(step)!r}")
            time.sleep(1.0)

        shot = call("Page.captureScreenshot", format="png")
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_bytes(base64.b64decode(shot["data"]))
        print(f"saved {args.out}")
    finally:
        proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main()
