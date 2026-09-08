# What-if panel wiring — design

**Date:** Tuesday 8 September 2026
**Component:** Interface → What-if panel (`PROGRESS.md`, currently 🔄 Ongoing)
**Scope:** Connect the dashboard's existing release slider to the existing
`POST /api/whatif` endpoint so moving it produces a 72-hour forecast, not just
a gate animation. No new features, no backend change.

---

## Problem

- `POST /api/whatif` ([backend/aquasync/api/main.py:260](../../../backend/aquasync/api/main.py#L260))
  works: it takes `{start_level, inflow_cumecs, release_cumecs, hours}`, runs a
  constant-inflow / constant-release forward simulation on the Idukki model,
  and returns `{levels[], final_level, peak_level, breaches_frl,
  hours_to_frl, revenue_inr, spill_cumecs, advice}`.
- `bindControls()` ([dashboard/js/twin.js:337](../../../dashboard/js/twin.js#L337))
  only mutates local `target.spill` / `target.turbine` / `target.gate` and
  re-renders the 3D scene. It never calls the endpoint.
- Result: the slider animates the sluice gate but tells the operator nothing
  about what the reservoir *does* over the next three days — which is the
  point of a what-if.

## Approach (chosen: minimal wire-up)

Add a debounced request in the frontend only. No backend edit. No new files.
Keep the existing 3D gate animation as immediate feedback.

### Trigger

- On the slider's `change` event (fires when the user releases the handle),
  not `input` (fires every pixel). The forward sim is a 72-step NumPy loop
  per call and the venue runs offline on one laptop — one request per
  settle is right.
- Debounce 250 ms so a quick drag-and-release fires once.
- The existing `input` listener stays untouched: label + 3D gate update live.

### Request body

| Field | Value |
|---|---|
| `start_level` | current `target.level` (last value from telemetry or the replay) |
| `inflow_cumecs` | current `target.inflow` |
| `release_cumecs` | slider value |
| `hours` | `72` |

`target` is the module-level live-state object already in `twin.js`. Reading
from it means the sandbox always starts from whatever the dashboard is
currently showing.

### Response rendering

New output block inside the existing **What-if** card in
[dashboard/index.html](../../../dashboard/index.html) (a `<dl class="kv">`
matching the telemetry panel's style), populated by a new
`renderWhatIf(result)` function:

| Row | Source | Format |
|---|---|---|
| Peak level (72 h) | `peak_level` | `732.41 m` |
| Cushion at peak | `RES.frl - peak_level` | `0.02 m` |
| Breaches FRL | `breaches_frl` | `yes` / `no`, `yes` styled as alert |
| Time to FRL | `hours_to_frl` | `41 h` or `—` if null/negative |
| Note | `advice` | the returned string, verbatim |

`revenue_inr`, `levels[]` and `spill_cumecs` are returned but not shown — the
card is about flood risk, and the 3D scene already shows spill. Not adding a
revenue figure keeps the card focused; if the team wants it later it is one
row.

### States

- **Before first move:** output block hidden (or a muted "Move the slider to
  test a release.").
- **In flight:** the block shows a muted "…" — the call is sub-second locally
  but the venue laptop may be loaded.
- **API down:** `fetch` rejects. Show "Sandbox needs the API running." in the
  card. This is the same failure the whole dashboard already tolerates (it
  falls back to the bundled replay for telemetry); the what-if simply cannot
  work without the endpoint, and says so rather than going silently dead.
- **Reset button:** already sets the slider to 0 and the label to "0". Extend
  it to hide the output block.

### API base URL

`twin.js` builds `WS_URL` from `location.hostname`. The dashboard is served
same-origin by the API (`StaticFiles` mount), so the fetch is a relative
`fetch('/api/whatif', …)` — no host constant, works whether opened via the
API or a static file server on the same host. If opened as a bare `file://`
with no server, the fetch fails and the "API down" state covers it.

## Files touched

| File | Change |
|---|---|
| `dashboard/js/twin.js` | `bindControls()`: add debounced `change` listener that POSTs and calls `renderWhatIf`; add `renderWhatIf(result)` and a small `postWhatIf()` helper; extend the reset handler to hide output |
| `dashboard/index.html` | ~6 lines of markup: an output `<dl>` + status line inside the existing What-if `<section class="card">` |

No backend file changes. No new files.

## Testing

- `python scripts/check.py --fast` — ruff + the 75-test suite + glyph audit.
  Nothing under `backend/` or a builder changes, so the full regeneration
  gate is not required, but `--fast` must pass.
- Manual, with the API running (`uvicorn aquasync.api.main:app --port 8000`,
  from repo root): open `http://localhost:8000/`, move the slider, confirm
  the card fills with a plausible peak level and the `advice` string; move it
  to 0 and to 900 and confirm the numbers move the right way (more release →
  lower peak); stop the API and confirm the card shows "Sandbox needs the API
  running."
- The dashboard has no automated browser test and there is no headless
  browser on the machine — the manual check is the verification, and the
  final report will label it as such.

## Out of scope

- Any backend change to `/api/whatif`.
- Showing the level curve as a chart (the endpoint returns `levels[]`; a
  sparkline is a later nice-to-have, not "wiring together").
- Revenue display.
- Wiring the what-if into the 3D scene beyond the gate animation that already
  responds to the slider.

## PROGRESS.md / docs update

On completion, on `main`:

- `PROGRESS.md`: What-if panel row 🔄 Ongoing → ✅ Done, note rewritten to
  "Slider POSTs to `/api/whatif` on release; card shows 72 h peak level,
  cushion, FRL breach and the advice string. Manually verified against a
  running API; no automated browser test." Recount the Interface table
  (3/5 → 4/5) and the at-a-glance / overall totals.
- No number in the numbers ledger changes. `docs/validation.md` and
  `ROADMAP.md` do not carry this item's status — no edit needed there. (Will
  re-check both at completion.)
