# AquaSync — Handover

**A single self-contained brief: what exists, what it actually proves, and
what is left.** Written 30 August 2026; refreshed **Wednesday 9 September
2026**, when the software list emptied and the bench became the whole
critical path.

This file is a snapshot for someone picking the project up cold. The living
documents stay authoritative for their own areas:

| Document | Owns |
|---|---|
| [PROGRESS.md](PROGRESS.md) (on `main`) | Component-by-component status. **Single source of truth** |
| [ACTION_PLAN.md](ACTION_PLAN.md) | Standing rules and the current fortnight |
| [ROADMAP.md](ROADMAP.md) | Sequencing, and what is deliberately *not* being built |
| [docs/validation.md](docs/validation.md) | Every claim, with its error bar and its caveats |
| [CLAUDE.md](CLAUDE.md) | Working agreements for AI-assisted work — and how to think and write here |

If this file and `PROGRESS.md` disagree, `PROGRESS.md` wins.

---

## 1 · What this project is

A decision-support digital twin for the Periyar basin: it reads Kerala's
public dam bulletin and a real weather ensemble, simulates the reservoir and
the river downstream, and outputs a **three-parameter release policy** —
draw down to *this level*, starting at *this hour*, at no more than *this
rate*. Not a dashboard of gauges. Advisory permanently; a named officer
approves and the twin never operates a gate.

Target venue: EVOKE 26 Project Expo, Track 2 (Climate Resilience & Disaster
Preparedness), MACE IoT Club, Kothamangalam. **Whether the entry went in is
not known** — registration closed Saturday 22 August.

---

## 2 · What is built and working

### Simulation core — `backend/aquasync/twin/`

| Module | What it does | State |
|---|---|---|
| `reservoir.py` | Hourly mass balance, level-storage power law | Calibrated: exponent 1.348, r² 0.9957, MAE 17 Mm³ over 1,836 validated rows |
| `runoff.py` | SCS Curve Number + AMC shift + triangular unit hydrograph | **Defect found and fixed 30 Aug** — see §4. Validated on four monsoons: shape yes, amplitude no |
| `routing.py` | Muskingum, auto sub-reaching; Muskingum–Cunge for ungauged reaches | K and x are **anchored to CWC's published 8 h travel time**, not gauge-calibrated; calibration attempted and blocked |
| `power.py` | Hill-diagram turbine efficiency, time-of-day tariff | Verified: 743 MW at rated flow against 780 MW nameplate |
| `tide.py` | Kochi tidal harmonics (M2/S2/K1/O1/N2) + effective conveyance | Offline-capable, no network needed |
| `optimizer.py` | Exhaustive policy grid search, four-part objective | Deterministic, bit-for-bit |
| `scenarios.py` | Oct 2021, Nov–Dec 2021 and Aug 2022 episode definitions and loading | — |
| `crisis.py` | Crisis Commander scoring core | Built 30 Aug; hindsight search `lru_cache`d per scenario |
| `constants.py` | Reservoir geometry and limits | — |

`aquasync.twin` imports with **no web framework installed**, and CI enforces
that. Do not add a FastAPI or pydantic import to anything under `twin/`.

### Data — `backend/aquasync/io/kseb_dataset.py`

18 dams, **2020-08-13 → 2026-08-26**. There is **no 2018 data** in the public
dataset, which is why the flagship case is October 2021 and not the 2018
floods. A validation layer flags rows that are physically impossible;
**about 11% of the source feed fails**, concentrated in a corrupt block from
2020-09-25 to 2021-04-30 plus 2025-06-04. Use the `quality_ok` flag.

### API — `backend/aquasync/api/main.py`

```
GET  /api/health
GET  /api/reservoirs
GET  /api/scenarios
GET  /api/scenarios/{key}/counterfactual
POST /api/whatif
GET  /api/crisis/{key}          briefing
POST /api/crisis/{key}          score a decision
GET  /api/rig                   scale-rig telemetry, opt-in via AQUASYNC_MQTT_HOST
GET  /api/tide
WS   /ws/telemetry
```

Serves the dashboard same-origin. Long computations go through
`asyncio.to_thread` so the event loop is not blocked. Run it **from the repo
root**: `uvicorn aquasync.api.main:app --port 8000 --app-dir backend`.

### Interface — `dashboard/`

- `index.html` + `js/twin.js` — Three.js 3D twin, no build step, WebSocket
  telemetry with time-based easing; falls back to a bundled October 2021
  replay when the API is down. Terrain is **measured**: `build_terrain.py`
  bakes 18 km of the real Periyar valley out of the DEM tiles the catchment
  work already caches, and the reservoir footprint comes from the DEM's flat
  water sheet, so the shoreline walks up actual topography as the level moves.
  The what-if slider **is** wired to `POST /api/whatif`.
- **Provenance is declared by the server, never inferred from the socket.**
  Every telemetry frame carries `source`, defaulting to `REPLAY`; only `LIVE`
  is styled green. This was a defect — the badge lit `LIVE` on connect while
  a 2021 recording streamed underneath it — and it is pinned by tests.
- `crisis.html` + `js/crisis.js` + `css/crisis.css` — Crisis Commander (§5)

### Tests, lint, and the gate

**97 tests** across `backend/tests/` — `test_twin.py` (physics and
behaviour), `test_rig.py` (the MQTT bridge and its honesty rules) and
`test_api_telemetry.py` (provenance). All passing, 9 September. Get today's
number from `cd backend && python -m pytest --collect-only -q`, never from a
document.

```bash
python scripts/check.py           # the single gate: ruff + pytest + glyph audit
                                  # + figure/document regeneration + determinism
python scripts/check.py --fast    # source-only subset, needs no data/raw/
python scripts/status.py          # one-screen board, parsed from PROGRESS.md and disk
```

`--fast` runs automatically before every commit via `.githooks/pre-commit`
(enable once per clone with `git config core.hooksPath .githooks`) and in CI
as the `selfcheck` job.

**Run the full `check.py` before pushing anything that touches a document
builder or the twin.** The regeneration and determinism checks are the ones
that catch a committed PDF built from older code.

### Documents — all regenerate from `scripts/`, byte-identically

| File | Builder |
|---|---|
| `docs/AquaSync_Project_Dossier.pdf` (24 pp) | `scripts/build_dossier.py` |
| `docs/AquaSync_Abstract.pdf` (4 pp) | `scripts/build_abstract.py` |
| `docs/AquaSync_Research_Report.pdf` (59 pp, 144 sources) | `scripts/build_research_report.py` |
| `docs/AquaSync_ICFOSS_Analysis.pdf` (10 pp) | `scripts/build_icfoss_analysis.py` |
| `docs/assets/fig1..fig8*.png` | `scripts/make_figures.py` |

`docs/AquaSync.pdf` (19 pp, committed 27 August) has no builder in
`scripts/` and is not checked by `check.py`. Either it is an older export
that should go, or it needs a builder; nobody has said which.

### Hardware — `firmware/`, `hardware/bom/`

PlatformIO firmware skeleton (sensor fusion + safety interlock structure) for
`node_reservoir`; `node_downstream` is a placeholder. BOM in four tiers;
**V1 is ₹6,250** with live vendor links in `hardware/bom/bom.html`.
**Ordered and received 8 September** — the components are in hand, and two
SX1278 (Ra-02) 433 MHz LoRa modules followed on 9 September. The firmware has
not been flashed to real hardware yet; five defects were fixed in it first
(bare `nan` in JSON, no Wi-Fi reconnect, unguarded ISR state, the stepper
enable pin left asserted, and an undocumented air-vs-water temperature
approximation).

---

## 3 · What the project actually proves

Every number below regenerates from `scripts/`. Do not quote a figure that
does not.

### The flagship result — October 2021

Idukki sat at 728.81 m on 16 October 2021. 168 mm of rain fell on the 17th.
Inflow went 115.7 → 879.2 cumecs. The gates opened on the **20th**, three days
later, at 730.95 m.

Against that record, a policy-based release schedule delivers **about 3 m more
flood cushion while generating marginally more revenue** — it shifts the same
volume of generation into higher-tariff hours. The assumed safety-versus-power
trade-off is largely an artefact of hoarding level rather than scheduling
releases.

**Say "about 3 m", never "3.16 m".** Replay error is 0.30 m MAE, so roughly
half a metre of that figure sits inside model error.

What lead time changes is not the cushion but the **waste**: 61% of released
water is spilled at zero lead, 40% at 30 days.

### Model fidelity

- Oct 2021 replay: **0.303 m MAE**, 0.57 m max, over 20 days
- Aug 2022 out-of-sample replay: **0.319 m MAE** — within 5% on an episode
  never tuned to. Wrinkle worth volunteering: the drift *direction* flips
  between the two episodes, which weakens the single-missing-loss-term
  explanation
- The optimiser independently converged on **728.43 m**, against KSEB's
  published rule level of 728.50 m

### Forecast error — the headline, on two storms

The optimiser originally had perfect foresight, which made every benefit
figure an upper bound. It is now re-run against **real NOAA GEFS 30-member
ensembles**, bias-corrected against IMD gridded rainfall, and scored as
**excess cost against perfect foresight on the optimiser's own four-part
objective**. Ten runs: five lead times, two storms.

**October 2021** — perfect foresight costs 1.959 and buys 3.111 m of cushion:

| Lead | Issue | Bias factor | Expected value | Minimax regret |
|---|---|---|---|---|
| 24 h | 2021-10-15 18z | 1.68 | **+0.0%** | +19.4% |
| 48 h | 2021-10-14 18z | 2.73 | **+0.0%** | +18.5% |
| 72 h | 2021-10-13 18z | 2.22 | +36.9% | +53.1% |
| 90 h | 2021-10-13 00z | 3.18 | +69.3% | +84.7% |
| 120 h | 2021-10-11 18z | 2.64 | +69.3% | +69.3% |

**August 2022** — perfect foresight costs 0.747, and its "freeboard gained" is
**−1.455 m**: the optimal policy ends *higher* than the operators did.

| Lead | Issue | Bias factor | Expected value | Minimax regret |
|---|---|---|---|---|
| 24 h | 2022-08-07 18z | 1.80 | **+0.1%** | +0.1% |
| 48 h | 2022-08-06 18z | 1.76 | **+5.5%** | +5.3% |
| 72 h | 2022-08-05 18z | 1.50 | **+5.3%** | +57.0% |
| 90 h | 2022-08-05 00z | 2.05 | **+5.3%** | +39.1% |
| 120 h | 2022-08-03 18z | 0.90 | **+157.8%** | +177.2% |

#### The degradation reproduces — and a premature reading is on record

An earlier draft of this file, written when only the first three August runs
had landed, said *"the degradation curve does not reproduce."* **That was
wrong, and it was wrong because it was written from a truncated series.**
The 120 h point had not arrived yet, and it is the one that carries the
shape.

Both storms show the same structure — a flat region where a real forecast is
as good as hindsight, then degradation. What differs is **where the break
falls and how hard it lands**:

| | Flat through | Then |
|---|---|---|
| October 2021 | 48 h (+0.0%) | ramps to +36.9% at 72 h, plateaus at +69.3% |
| August 2022 | 90 h (≤ +5.5%) | jumps to **+157.8%** at 120 h |

October's degradation is a ramp; August's is a cliff. So the finding
survives, in a more careful form: **a real ensemble matches hindsight up to
some horizon, beyond which committing to its policy costs substantially more
than doing nothing clever.** The horizon is not a constant across storms and
the penalty beyond it is not bounded by October's +69%.

This is the fourth claim on this project to be stated early and then broken
by more data — alongside the 24→90 h "cliff" that turned out to be a ramp,
the minimax-regret claim, and the bias-magnitude claim below. **Treat any
conclusion drawn from a partial run set as provisional until the set is
complete.** It is now a standing rule in `CLAUDE.md`.

#### Two things to be careful about when quoting it

**1 · The two episodes are not equally hard, and August is the easier one.**
October 2021 came within about a metre of the 732.43 m FRL — a genuine
crisis. August 2022 peaked nearly 5 m below it. The perfect-foresight cost
reflects it: 1.959 against 0.747. Part of why August stays flat for longer
is plausibly that there was less at stake, not that the forecast was better.
**Do not average the two storms into a single curve.**

**2 · Both retractions get stronger.**

1. *"Minimax regret never underperforms expected value."* False. **Across
   all ten runs, hedging is better in exactly one — by 0.16 percentage
   points** (August 48 h: +5.30% against +5.46%, a tie in everything but
   sign) — ties in two, and loses in seven, sometimes heavily: August 72 h
   costs **+57.0%** hedged against **+5.3%** on expected value.
2. *"A larger bias correction means a worse decision."* False. On October's
   five runs lead time correlates at r = 0.93, bias only at r = 0.61 — and
   the 48 h run carries a 2.73× correction yet scores +0.0%. August's 120 h
   run has the **smallest** bias factor of all ten (0.90, the only one below
   1) and the **worst** outcome (+157.8%): it drew the reservoir down 1.21 m
   when the optimal policy would have let it rise.

**Never quote `retention_of_perfect_foresight_pct` from this study.** It reads
above 100% because the policies over-release; it scores freeboard alone, one
axis of a four-part objective. Read `excess_cost_vs_perfect_foresight_pct`.

**Where the August numbers are, as of 9 September:** everywhere — the
dossier's §4.4 carries a second-storm subsection and Figure 6 grew a second
row, alongside `PROGRESS.md`, `ROADMAP.md` item 10, `docs/validation.md` §4
and this file. The two storms are drawn on **separate axes with separate
y-limits**, deliberately: they are not equally hard and the penalties past
the flat region differ by more than a factor of two, so a shared scale would
imply a point-by-point comparison the data does not support.

Landing them turned up **two more unfiltered globs** of the kind
`make_figures.py` had carried: `build_abstract.py` counted study *files* as
lead times and reported "across 10 lead times" when there are five run twice,
and `build_icfoss_analysis.py` merged both storms into a single min–max
range. Both filter by scenario now. The rule is worth carrying: **any
`glob("forecast_error_study_*")` without a scenario filter is a defect**, and
it stays invisible for as long as only one storm is on disk.

### Cascade coordination — a negative result, and it is load-bearing

Idukki and Idamalayar both opened spillways on **20 October 2021**
(83.85 + 128.13 cumecs). Optimising the two dams **independently** puts the
joint peak at their confluence at **911 cumecs against an observed 403** —
126% worse. Retiming both start hours recovers only **9%** of that (down to
828).

Do not present cascade results as a coordination win. It is an
objective-function problem, not a timing one: each dam is scored against its
own reach instead of the combined downstream discharge. A bigger timing search
will not fix it.

These are two dams' contribution only — no lateral inflow — so **never read
them against bankfull (1,100 cumecs)**.

### Rainfall–runoff validation

Four monsoon seasons (2021–2024, **722 scored days**) of observed rainfall
against observed inflow:

- Pooled volume bias **−1%**, but per-season −7 / −3 / **+38** / −17%
- **r² 0.55** on shape, **NSE 0.07** on amplitude — the model has no recession
  limb
- Calibration pins at the grid floor (CN 50) and fails leave-one-season-out,
  so **handbook CN 72 stays**

This is an honest "partially validated", not a pass.

### Routing calibration — blocked, and quantified

Attempted against 1,967 days of CWC Neeleeswaram discharge. **The fit failed:
r² = 0.005**, and K hit the grid edge. Daily data (dt = 24 h) is roughly 3×
coarser than the 8 h travel time it would need to resolve, and the bottleneck
is the *release* record (KSEB publishes daily only), not the gauge.

K and x stay anchored to CWC's published 8 h figure. **Do not quote Aluva
discharge as measured.** Unblocks with the CWC 15-minute telemetry feed.

---

## 4 · The defect that was found and fixed

`RainfallRunoffModel` applied the SCS initial abstraction **per timestep**, so
the full abstraction was charged against every hour of a storm. The chain
produced almost no runoff, and its answer depended on the driving timestep:

> 168 mm/day gives **88.97 mm** of runoff as a single daily step, and
> **0.00 mm** driven hourly.

Fixed by `storm_excess()`, which accumulates rainfall within a storm, applies
the abstraction once at storm onset, and separates storms on a configurable
dry gap (default 6 h). Timestep invariance is now pinned by a test across
1/8/24/48 sub-steps.

**Every forecast-error number in §3 was re-run on the fixed chain.** The
headline result reversed direction in the process.

A related correction worth remembering: an early test asserted that splitting
a storm across a dry gap *reduces* runoff. That premise was wrong — on a dry
catchment it *increases* it, because the second storm starts wetter through
the AMC feedback. The test now seeds an antecedent 200 mm so both storms sit
at AMC-III, with the AMC effect itself covered separately.

---

## 5 · Crisis Commander — built 30 August

`dashboard/crisis.html`. You get the duty desk at Idukki on 8 October 2021 at
727.72 m, set three numbers, and your order is played forward against the
inflow that actually arrived — scored by **the same optimiser and the same
objective** as everything else, so your result, the operators' result and
AquaSync's sit in one table meaning the same thing.

You are told what the duty engineer was told: level now, rain so far, and that
heavy rain is forecast. You are **not** told the inflow that is coming. That
is the whole problem.

It reproduces the project's thesis by making it felt (regenerated from
`aquasync.twin.crisis.score` on 31 August — these are not cached on disk):

| Your order | Peak | vs the day | Revenue |
|---|---|---|---|
| Hoard (731 m, hour 200, 60 cumecs) | 732.41 m | **0.87 m less cushion** | −21 cr |
| Release early (727.5 m, hour 0, 400 cumecs) | 728.59 m | **2.95 m more cushion** | **+45 cr** |
| AquaSync's own answer (727.96 m, hour 207, 828 cumecs) | 728.46 m | 3.08 m more cushion | +45 cr |

Early and hard wins on *both* axes.

Implementation notes for whoever touches it next:

- Logic lives in `aquasync.twin.crisis`, **not** the API, so the core stays
  importable with no web framework
- References (observed outcome + hindsight-optimal search) are cached per
  scenario with `lru_cache`. The search takes seconds; re-running it on every
  slider move made the demo feel broken. Caching also cut the test suite from
  73 s to about 25 s
- The page **says the backend is down** rather than inventing numbers. A demo
  that fabricates results is worse than one that admits the API is off, and
  the expo network is not a dependency worth trusting
- Validation returns 422 on out-of-range, 404 on unknown scenario

> ✅ **Visually verified 8 September**, driven through a real browser over
> the DevTools protocol: the briefing loads, the sliders take an order, and
> committing renders the three-way outcome table with its verdict and colour
> coding. Re-checked 9 September with zero console errors.
>
> An earlier version of this note said there was **no headless browser on
> this machine**. That was wrong — Chrome is installed, and so are cached
> Playwright binaries. The claim went unchecked for over a week and was the
> stated reason two features shipped unverified. Check before you record an
> impossibility.

To run it:

```bash
uvicorn aquasync.api.main:app --port 8000 --app-dir backend   # from the repo root
# then open http://localhost:8000/crisis.html
```

---

## 6 · Everything is committed

As of 9 September the working tree is clean and nothing of value sits
uncommitted. The backlog this section used to track — the second storm's ten
forecast-error files, the refreshed planning documents, this file — all
landed between 7 and 9 September.

Two things worth carrying forward from it:

**The `.gitignore` hole is closed.** The rule was `data/raw/`, and a pattern
with a slash in the middle is anchored to the directory holding the
`.gitignore` — so it matched `/data/raw/` and **not** `backend/data/raw/`,
where a stray 740 KB third-party cache had been left by something run with a
relative default from inside `backend/`. It is now `**/data/raw/` and
`**/data/external/`. This is why the standing rule says never `git add -A`.

**PROGRESS.md lives on `main` and only on `main`.** A feature branch's copy is
however stale that branch is, so read it with `git show main:PROGRESS.md`.
`scripts/status.py` used to read the working tree and reported a finished test
suite as Todo; it now reads `main` too.

---

## 7 · What is left

### Nothing is blocked on anyone but the bench

Both items this section used to list as urgent and blocked on the team closed
on 8 September: the components were ordered and received, and the expo entry
was confirmed. Every software task that does not need the rig is done.

### The critical path

| # | Task | Notes |
|---|---|---|
| 1 | **Build the two-tank bench** | Acrylic tanks, pump loop, sluice gate. Test each component alone *before* assembly — debugging a sensor that was never verified, inside a rig already glued and full of water, costs more than a day |
| 2 | **Flash the firmware to real hardware** | The five defects are fixed; nothing has been on a board yet. Success is `GET /api/rig` showing `source: LIVE`, chain verified, 0 breaks — the first time that badge will be *true* |
| 3 | **Fault injection** | Sensor-failure and gate-jam switches. **The beat that wins the room.** The dashboard half is done and verified in a browser against a simulated node; what is left is the physical switches and the firmware paths behind them |
| 4 | A1 poster, pitch rehearsal, offline rehearsal | Expo deliverables, not started. Print by expo minus 3 days |

### What was finished since the last refresh

| Item | Outcome |
|---|---|
| Joint cascade objective | Built — and **inert on the data as held**. The combined peak never reaches bankfull, so the shared flood term is identically zero and coordinate descent converges in zero moves. The blocker is the ungauged lateral inflow, not the objective's structure |
| Second storm into the dossier | §4.4 and Figure 6 carry both storms, on separate axes. Two more unfiltered globs found and fixed on the way |
| What-if panel | Wired to `/api/whatif`, browser-verified |
| Crisis Commander | Seen rendered, driven end to end |
| 3D twin | Rebuilt on measured DEM terrain |
| Rig telemetry | MQTT bridge, SHA-256 record chain, `GET /api/rig`. Receive-only — the command topic is deliberately not wired |
| Research report determinism | It embedded its build date, so every rebuild differed. Now an 8-character digest of the parsed index files |

### One open question nobody has answered

**What is the expo presentation date?** The entry is confirmed but the date is
recorded nowhere in this repository, and three deadlines hang on it — poster
print, offline rehearsal, and how much slack the bench build has.

### One standing decision

`docs/AquaSync.pdf` (19 pp, committed 27 August) has no builder in `scripts/`
and is not checked by `check.py`. Audited 9 September: it carries no
contradicted claims and its trust-boundary diagram correctly says a gate
command is *never issued by the system*. But it is unmaintained and predates
the second storm, the joint cascade result and the rig bridge. Either delete
it or give it a builder; nobody has said which.

### Deliberately not being built

2D inundation (LISFLOOD-FP / HEC-RAS), Sentinel-1 SAR extent validation,
Malayalam alerting, a continuous soil-moisture runoff model, paid deployment
infrastructure. **And, permanently: operating a real dam gate.** Kerala's
gates are KSEB's and the district administration's; the only gate anything
here actuates is the model sluice on the bench. See [ROADMAP.md](ROADMAP.md)
§Never in scope.

---

## 8 · The demo

Six beats, roughly three minutes. Full sequence in dossier §12.

1. The rig is already running when they walk up. Point, do not explain.
2. Figure 1 on screen: *"this is real, and it is public."*
3. Dump water in — a live storm. The gate opens **before** FRL.
4. **Flip the sensor-failure switch.** The twin detects the disagreement,
   falls back to mass-balance state estimation, and keeps controlling.
5. Hand over the tablet: *"You are the operator. It is 8 October 2021."*
6. Pull the network cable. Everything keeps running.

**Beat 4 is the one that wins the room.** Anyone can demo a system working.
Demonstrating a system *failing correctly* is what convinces an engineer it
was built by someone who expected it to be used. Build the fault-injection
switches even if something else has to be cut.

---

## 9 · Questions to have an answer ready for

| Question | Answer |
|---|---|
| *"Where is the hardware? This is an IoT club."* | The rig, running in front of them. Sensor fusion, LoRa fallback, tamper-evident logging |
| *"How do you know the model is right?"* | 0.30 m MAE reproducing observed Idukki level over 20 days; 0.32 m on an episode it was never fitted to |
| *"What if the forecast is wrong?"* | Measured on two storms. Inside 48 h a real GEFS ensemble picks the same policy hindsight would; on the easier August 2022 episode that holds to 90 h. Beyond the horizon it costs 69% and 158% more. The value sits in the last two days — which is when a control room has least time to think |
| *"Two storms is not a curve."* | Correct, and we say so. One ramps, one cliffs, which is exactly why they are not averaged. A third, harder storm is next |
| *"You optimise two dams on one river — do they interact?"* | Badly, and it is measured: independently optimising puts the joint peak 126% above what happened. Volunteering this is stronger than being caught by it |
| *"KSEB will never adopt this."* | Correct, not on trust. Shadow mode for one monsoon, publish the comparison |
| *"Why not use 2018 data?"* | It is not in the public dataset — and finding that out is why the flagship case is October 2021 |
| *"Isn't this just a dashboard?"* | The output is a three-parameter release policy, not a screen of gauges |
| *"What about the towns — which streets flood?"* | Out of scope deliberately. 1D routing gives river discharge; 2D inundation is the roadmap |
| *"Who is liable if it is wrong?"* | Advisory permanently. A named officer approves; the twin never operates a gate |
| *"What did you get wrong?"* | Four claims, retracted where they were made; two defects, one of which stopped the runoff chain producing runoff. Then the page numbers |

---

## 10 · Rules that are not negotiable

- **Human contributors only.** No `Co-Authored-By:` trailer for an AI
  assistant on any commit, ever — no "generated by" footers, no bot
  signatures, no assistant names in `--author`, `AUTHORS`, README credits or
  PR descriptions. GitHub promotes those addresses to repository
  **contributors**, where they appear in the graph and Insights alongside the
  people who built the project. This is a student project entered in a
  competition and the contributor list is part of how it is judged. Full rule
  in [CLAUDE.md](CLAUDE.md).
- **Follow the git workflow.** Update `PROGRESS.md` on `main`. Branch from
  `development`, never from `main`. PR into `development`.
- **Never quote a number the code cannot regenerate.** Every figure and
  headline number comes from `scripts/`.
- **Say "about 3 m", never "3.16 m".** Two decimals claim precision that is
  not there.
- **No new features.** New ideas go in [ROADMAP.md](ROADMAP.md).
- **Say it in words, or register a Unicode font.** reportlab's base-14 fonts
  drop characters they cannot draw *without erroring*. That is how the layer
  diagram lost every arrow, the hydropower formula rendered as "gQH", and
  GitHub star counts became bare numbers — in documents that built cleanly.
  The glyph audit in `check.py` exists because of this.
- **Treat any conclusion from a partial run set as provisional** until the
  set is complete. Four retractions in one week earned this rule.

---

## 11 · Running it from a cold clone

```bash
git config core.hooksPath .githooks     # once per clone

pip install -e backend[dev]
python scripts/fetch_data.py            # populates data/raw/ (gitignored)

python scripts/check.py                 # full gate
python scripts/status.py                # the board
python scripts/make_figures.py          # docs/assets/fig1..fig8
python scripts/build_dossier.py         # docs/AquaSync_Project_Dossier.pdf

uvicorn aquasync.api.main:app --port 8000 --app-dir backend   # from the repo root
```

`data/processed/` is committed, so results stay reproducible even if the
upstream dataset changes or disappears. Run everything from the repo root —
a relative `data/raw` resolved from inside `backend/` is how the stray cache
in §6 happened.

---

## 12 · Open risks

| Risk | Severity | Where it stands |
|---|---|---|
| ~~Expo entry status unknown~~ | ✅ Closed | **Confirmed 8 September** |
| Expo presentation date unknown | 🟠 Medium | The entry is in; the date is recorded nowhere. Poster print, rehearsal and bench slack all hang on it |
| ~~Hardware ordering delay blocks the rig~~ | ✅ Closed | **Received 8 September**, LoRa modules 9 September |
| The bench is now the whole critical path | 🔴 High | Every software task that does not need the rig is done, so there is nothing left to fall back on when the hardware is frustrating. The build has not started, and it starts a week later than planned |
| Firmware has never run on real hardware | 🟠 Medium | Five defects fixed before flashing, but nothing has been on a board. First contact is the risk |
| Independent per-dam optimisation makes the shared downstream peak worse | 🟠 Medium | Measured at 126% above observed. Do not ship per-dam optimisation as if it degrades gracefully. A joint objective was built on 8 September and is **inert on the data as held** — the combined peak never reaches bankfull, so the shared flood term is identically zero. The blocker is the ungauged lateral inflow, not the objective |
| Forecast-error result rests on two storms of very different difficulty | 🟠 Medium | Degradation reproduces in both, but Oct 2021 breaks at 48 h and plateaus at +69%, while Aug 2022 stays flat to 90 h then jumps to +158%. Aug 2022 sat nearly 5 m below FRL. Qualify by reservoir state; never average the two |
| ~~Crisis Commander never seen rendered~~ | ✅ Closed | Driven through a real browser 8 September; re-checked 9 September with zero console errors |
| The dashboard labelled a recording LIVE | ✅ Closed | The badge lit on socket-open, not on measurement. Provenance is now declared per frame and pinned by tests |
| Routing K/x anchored, not calibrated, so downstream discharge is indicative | 🟠 Medium | Calibration failed on daily data (r² = 0.005); the CWC 8 h anchor stands. Needs the 15-minute feed |
| Runoff amplitude unvalidated (NSE 0.07, no recession limb) | 🟠 Medium | Disclosed in validation.md. Shape is usable, amplitude is not |
| ~~`backend/data/raw/` is committable~~ | ✅ Closed | Now `**/data/raw/` and `**/data/external/`. The rule against `git add -A` stands anyway |
| Feature creep across 25 candidate upgrades | 🟠 Medium | Phases 0–3 plus the V1 rig is the scope |
| Upstream dataset changes or disappears | 🟢 Low | `data/processed/` is committed |
