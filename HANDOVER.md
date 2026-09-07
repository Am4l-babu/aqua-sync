# AquaSync — Handover

**A single self-contained brief: what exists, what it actually proves, what
is on disk but not yet committed, and what is left.** Written 30 August 2026;
refreshed **Monday 31 August 2026**.

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
GET  /api/tide
WS   /ws/telemetry
```

Serves the dashboard same-origin. Long computations go through
`asyncio.to_thread` so the event loop is not blocked. Run it **from the repo
root**: `uvicorn aquasync.api.main:app --port 8000 --app-dir backend`.

### Interface — `dashboard/`

- `index.html` + `js/twin.js` — Three.js 3D twin, no build step, WebSocket
  telemetry with lerp smoothing; falls back to a bundled October 2021 replay
  when the API is down. The what-if slider is client-side only —
  `POST /api/whatif` exists and is **not wired to it**.
- `crisis.html` + `js/crisis.js` + `css/crisis.css` — Crisis Commander (§5)

### Tests, lint, and the gate

**75 tests** in `backend/tests/test_twin.py`, all passing (31 August, 25 s).

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
| `docs/AquaSync_Project_Dossier.pdf` (21 pp) | `scripts/build_dossier.py` |
| `docs/AquaSync_Abstract.pdf` (4 pp) | `scripts/build_abstract.py` |
| `docs/AquaSync_Research_Report.pdf` (59 pp, 144 sources) | `scripts/build_research_report.py` |
| `docs/AquaSync_ICFOSS_Analysis.pdf` (9 pp) | `scripts/build_icfoss_analysis.py` |
| `docs/assets/fig1..fig8*.png` | `scripts/make_figures.py` |

`docs/AquaSync.pdf` (19 pp, committed 27 August) has no builder in
`scripts/` and is not checked by `check.py`. Either it is an older export
that should go, or it needs a builder; nobody has said which.

### Hardware — `firmware/`, `hardware/bom/`

PlatformIO firmware skeleton (sensor fusion + safety interlock structure) for
`node_reservoir`; `node_downstream` is a placeholder. BOM in four tiers;
**V1 is ₹6,250** with live vendor links in `hardware/bom/bom.html`.
**Nothing is ordered**, and has not been since the BOM was written on
26 August.

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

**Where the August numbers are, as of 31 August:** `PROGRESS.md`,
`ROADMAP.md` item 1, `docs/validation.md` §4, and this file. **Not yet in the
dossier §4.4 or Figure 6**, which still read October only — a builder change
and a full `check.py` rebuild, not started.

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

> ⚠️ **Not visually verified.** There is no headless browser on the machine
> that built it. The page was checked functionally — HTML/CSS/JS all serve,
> JS syntax parses, endpoints return correct data — but **nobody has seen it
> rendered**. Open it and look at it before relying on it for a demo. It is
> the first desk task in `ACTION_PLAN.md`.

To run it:

```bash
uvicorn aquasync.api.main:app --port 8000 --app-dir backend   # from the repo root
# then open http://localhost:8000/crisis.html
```

---

## 6 · On disk but not committed, as of 31 August

```
 M data/processed/forecast_error_cross_matrix_2021-10-15_18z.csv
 M data/processed/forecast_error_study_2021-10-15_18z.json
?? data/processed/forecast_error_*_2022-08-0{3,5,6,7}_*      the second storm, ten files
?? backend/data/raw/Idukki.json                               a stray cache, see below
?? HANDOVER.md                                                this file
 M README.md ROADMAP.md PROGRESS.md ACTION_PLAN.md CLAUDE.md  refreshed 31 Aug
 M docs/validation.md docs/architecture.md docs/data-sources.md
 M data/README.md notebooks/README.md
```

The two modified October files differ only in two provenance fields
(`scenario`, `storm_peak`) added by the scenario-awareness refactor. Every
computed value reproduced exactly; this was checked.

**Committing them:** `PROGRESS.md` goes on `main` directly, per the workflow.
Everything else goes on a branch off `development` and in by PR. Run the
**full** `python scripts/check.py` first — the regeneration check walks
`data/processed/`.

### ⚠️ A `.gitignore` hole worth closing first

Something run with a relative `data/raw` default from inside `backend/`
left a stray **`backend/data/raw/Idukki.json`** (740 KB) — and **it is not
ignored:**

```bash
$ git check-ignore -v backend/data/raw/Idukki.json
$ echo $?
1        # not matched by any ignore rule
```

The rule in `.gitignore` is `data/raw/`. A pattern with a slash in the middle
is anchored to the directory holding the `.gitignore`, so it matches
`/data/raw/` and **not** `backend/data/raw/`. The project's stated invariant is
that `data/raw/` is never committed while `data/processed/` is committed on
purpose; this hole quietly breaks it, and a `git add -A` would commit a raw
third-party cache.

**Still not fixed** — it is a repo-config change and nobody has asked for one.
The fix is one line (`**/data/raw/`, and the same for `data/external/`), and
the stray file is re-fetchable, so deleting it costs nothing.

---

## 7 · What is left

### Blocked on the team, and both are urgent

| # | Task | Why it is urgent |
|---|---|---|
| 1 | **Order the ₹6,250 of V1 components** | 3–5 day delivery. Every hardware task is behind it, and Week 2 — **this week, Mon 31 Aug – Sun 6 Sep** — is the rig build. Open since 26 August. Order a spare ESP32 — do not let a ₹90 part block a demo |
| 2 | **Confirm the expo entry status** | Registration closed **Saturday 22 August**; nine days without an answer. Whether the entry went in changes the whole schedule |

If the expo answer is no, the work is not wasted — the schedule simply loses
its deadline, and the joint cascade objective becomes worth more than the rig.

### Immediate technical work

| # | Task | Notes |
|---|---|---|
| 3 | ~~Finish the Aug 2022 runs~~ | **Done.** All ten runs complete, 30 Aug |
| 4 | ~~Interpret the second storm honestly~~ | **Done.** §3 above; PROGRESS, ROADMAP item 1, validation.md §4 |
| 5 | Put the second storm into dossier §4.4 and Figure 6 | `_forecast_error_block` in `build_dossier.py` and `fig6` in `make_figures.py` read October only. Qualify, do not replace |
| 6 | `python scripts/check.py` (full), commit, push | See §6 for what is uncommitted and where each piece goes |
| 7 | **Look at Crisis Commander in a browser** | See §5 |
| 8 | Wire the what-if panel to `/api/whatif` | Slider and endpoint both exist, unconnected. The only `🔄 Ongoing` engineering item |
| 9 | Close the `.gitignore` hole | One line. See §6 — `backend/data/raw/` is currently committable |
| 10 | Decide what `docs/AquaSync.pdf` is | No builder, not gated. Delete it or give it one |

### Largest open modelling item

**Joint cascade objective.** Score each dam's policy against the *combined*
downstream discharge rather than its own reach. §3 shows this is an
objective-function problem; a bigger timing search will not fix it. A joint
six-parameter grid at the current density is 1,344² combinations and not
tractable, so the design question is which parameters to hold. Worth
starting only if the rig is on track, or if there is no expo date.

### Expo deliverables not started

- Fault injection on the rig — the beat that wins the room (needs the parts)
- A1 poster (figures 1, 4 and 5 carry it; print by expo minus 3 days)
- Pitch rehearsal out loud, ten times (script is in dossier §12)
- Full offline rehearsal — pull the network cable and run the whole demo

### Deliberately not being built

2D inundation (LISFLOOD-FP / HEC-RAS), Sentinel-1 SAR extent validation,
Malayalam alerting, a continuous soil-moisture runoff model, paid deployment
infrastructure. See [ROADMAP.md](ROADMAP.md) for each reason.

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
| Expo entry status unknown | 🔴 High | Nine days since registration closed. Changes the whole schedule |
| Hardware ordering delay blocks the rig | 🔴 High | Still unordered on Monday 31 Aug — the rig-build week. Software is fully demonstrable without it, but EVOKE is an IoT club event |
| Independent per-dam optimisation makes the shared downstream peak worse | 🔴 High | Measured at 126% above observed. Do not ship per-dam optimisation as if it degrades gracefully. Fix is a joint objective |
| Forecast-error result rests on two storms of very different difficulty | 🟠 Medium | Degradation reproduces in both, but Oct 2021 breaks at 48 h and plateaus at +69%, while Aug 2022 stays flat to 90 h then jumps to +158%. Aug 2022 sat nearly 5 m below FRL. Qualify by reservoir state; never average the two |
| Crisis Commander never seen rendered | 🟠 Medium | Functionally checked. Open it before any demo |
| Routing K/x anchored, not calibrated, so downstream discharge is indicative | 🟠 Medium | Calibration failed on daily data (r² = 0.005); the CWC 8 h anchor stands. Needs the 15-minute feed |
| Runoff amplitude unvalidated (NSE 0.07, no recession limb) | 🟠 Medium | Disclosed in validation.md. Shape is usable, amplitude is not |
| `backend/data/raw/` is committable | 🟠 Medium | One-line `.gitignore` fix, see §6 |
| Feature creep across 25 candidate upgrades | 🟠 Medium | Phases 0–3 plus the V1 rig is the scope |
| Upstream dataset changes or disappears | 🟢 Low | `data/processed/` is committed |
