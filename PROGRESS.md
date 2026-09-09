# AquaSync — Project Progress

Single source of truth for what is happening on this project. Lives on `main`
and is updated **directly on `main`**, not via PR. Read it at the start of
every session.

**Project:** AquaSync — decision-support digital twin for dam–river flood and
hydropower optimisation on the Periyar basin.
**Target:** EVOKE 26 Project Expo · Track 2, Climate Resilience & Disaster
Preparedness · MACE IoT Club, Kothamangalam.
**Scope:** advisory, permanently. **AquaSync never operates a real dam gate.**
Kerala's gates are operated by KSEB and the district administration, and there
is no path from this system to them — the API's command topic is deliberately
not wired. The only gate anything here actuates is the model sluice on the
bench rig. Every gate-control row below means that one.

**Last updated:** Wednesday 9 September 2026.

**At a glance** — as `python scripts/status.py` counts it from the tables
below (✅ rows over all rows):

| Area | Done | |
|---|---|---|
| Core infrastructure | 5 / 6 | `████████░░` |
| Simulation core | 9 / 11 | `████████░░` |
| Decision engine | 7 / 7 | `██████████` |
| Scenarios & validation | 5 / 6 | `████████░░` |
| Hardware (V1 rig) | 5 / 10 | `█████░░░░░` |
| Interface | 4 / 5 | `████████░░` |
| Documentation | 11 / 14 | `████████░░` |
| **Overall** | **46 / 59** | `████████░░` |

The software is a finished, validated, twice-retracted-and-corrected piece of
work. **Both of the things only the team could do are now done — the components
are in hand and the expo entry is confirmed — so the hardware rows are the
critical path from here.** The rig's telemetry already reaches the dashboard;
what is left is building the bench and the fault-injection switches.

As of 9 September the **Decision Engine is complete (7 / 7)** — the joint
cascade objective, the last open modelling item, is built and merged. Its
result is a null one, honestly reported: on the data as held the objective
is inert, because the combined peak never reaches bankfull. Every software
task that does not need the rig is now either merged or in review.

**All three demo paths have been driven in a real browser (9 Sep)** — the fault banner against a simulated node over MQTT, the what-if panel against `/api/whatif`, and the offline beat with no backend running at all. Two defects came out of that and are fixed: the dashboard was labelling a 2021 recording **LIVE**, and it logged a 404 every second when offline.

---

## Status Legend

| Symbol | Meaning |
|---|---|
| 📋 Todo | Not started |
| 🔄 Ongoing | Someone is actively working on this right now |
| 👀 In Review | PR open, waiting for merge |
| ✅ Done | Merged into `development` |
| 🚫 Blocked | Waiting on something else |

---

## Core Infrastructure

| Component | Status | Assigned To | Branch | Notes |
|---|---|---|---|---|
| Project setup & folder structure | ✅ Done | Am4l-babu | `feature/project-scaffold` | Python twin core + FastAPI + Three.js dashboard + PlatformIO firmware. No Next.js — this project has no need for SSR |
| Source-material analysis | ✅ Done | Am4l-babu | `feature/project-scaffold` | Analysed `analyze_1.pdf` + EVOKE chat export. Found 2 load-bearing errors in the brief — see [docs/data-sources.md](docs/data-sources.md) |
| Data ingestion (KSEB bulletin) | ✅ Done | Am4l-babu | `feature/project-scaffold` | `aquasync.io.kseb_dataset`. 18 dams, 2020-08 → 2026-08 |
| Data validation layer | ✅ Done | Am4l-babu | `feature/project-scaffold` | Found ~11% of the source feed is physically impossible. `quality_ok` flag + `quality_report()` |
| Test suite & CI | ✅ Done | Am4l-babu | `feature/api-and-validation` | **91** physics/behaviour tests passing (8 Sep). **`python scripts/check.py` is the single gate** — lint, tests, a glyph audit for characters the PDF fonts drop silently, plus regeneration and determinism of every figure and document. Runs automatically via `.githooks/pre-commit` and the CI `selfcheck` job |
| Deployment | 📋 Todo | — | — | Expo runs offline on a laptop by design. Optional: Streamlit Cloud / Fly.io free tier for a public link. **Do not** put this on paid infra |

## Simulation Core

| Component | Status | Assigned To | Branch | Notes |
|---|---|---|---|---|
| Reservoir mass balance | ✅ Done | Am4l-babu | `feature/project-scaffold` | Hourly Euler. Level↔storage power law |
| Level–storage calibration | ✅ Done | Am4l-babu | `feature/project-scaffold` | β = 1.348, r² = 0.9957, MAE 17 Mm³ on 1,836 validated rows |
| Rainfall–runoff (SCS-CN) | ✅ Done | Am4l-babu | `feature/runoff-defect-fix` | AMC shift + triangular unit hydrograph. **Defect found and fixed 30 Aug**: the curve number's initial abstraction was charged per timestep, so the chain produced almost no runoff and its answer depended on the driving timestep. Now accumulates within a storm; invariance pinned by test |
| Muskingum river routing | ✅ Done | Am4l-babu | `feature/project-scaffold` | Auto sub-reaching for numerical stability. **K and x are anchored to CWC's published 8 h travel time, not gauge-calibrated** |
| Muskingum–Cunge (ungauged) | ✅ Done | Am4l-babu | `feature/project-scaffold` | Flow-dependent K, x from channel hydraulics |
| Tidal backwater | ✅ Done | Am4l-babu | `feature/project-scaffold` | Kochi harmonics (M2/S2/K1/O1/N2) + effective conveyance. Offline-capable |
| Hydropower & tariff | ✅ Done | Am4l-babu | `feature/project-scaffold` | Hill-diagram efficiency, ToD tariff. Verified: 743 MW at rated flow vs 780 MW nameplate |
| Routing calibration vs gauges | 🚫 Blocked | Am4l-babu | `feature/deep-research` | Attempted 28 Aug against 1,967 days of CWC Neeleeswaram discharge: **fit failed, r² = 0.005**, K hit the grid edge. Daily data (dt = 24 h) is ~3× coarser than the 8 h travel time it would need to resolve, and the bottleneck is the *release* record (KSEB is daily-only), not the gauge. K/x stay anchored to CWC's published 8 h figure. Unblocks with the CWC 15-minute telemetry feed |
| Catchment geometry from DEM | ✅ Done | Am4l-babu | `feature/deep-research` | Idukki catchment derived from a real digital elevation model, net of the Mullaperiyar diversion: 570 km² topographic against the CAG-sourced 650 km² used; channel 66 km, slope 0.0087. `scripts/catchment_geometry.py` |
| Runoff model validation | ✅ Done | Am4l-babu | `feature/runoff-defect-fix` | Four monsoon seasons (2021–2024, 722 days) of observed rainfall vs observed inflow. Pooled volume bias **−1%** but per season −7/−3/**+38**/−17%; r² 0.55 on shape, **NSE 0.07** on amplitude — no recession limb. Calibration pins at the grid floor and fails leave-one-season-out, so handbook CN 72 stays. `scripts/runoff_validation.py` |
| 2D inundation | 📋 Todo | — | — | Deferred. LISFLOOD-FP or HEC-RAS on Bhuvan DEM. Not needed for the expo |

## Decision Engine

| Component | Status | Assigned To | Branch | Notes |
|---|---|---|---|---|
| Objective function & weights | ✅ Done | Am4l-babu | `feature/project-scaffold` | Flood / dam safety / revenue / gate wear, exposed as policy not constants |
| Rule-curve baseline | ✅ Done | Am4l-babu | `feature/project-scaffold` | Faithful model of reactive practice — the thing to beat |
| Policy search | ✅ Done | Am4l-babu | `feature/project-scaffold` | Exhaustive grid over (target level, start hour, max rate). Deterministic |
| Grid offtake constraint | ✅ Done | Am4l-babu | `feature/project-scaffold` | Without it the optimiser books revenue the grid would never take |
| **Forecast-error study** | ✅ Done | Am4l-babu | `feature/runoff-defect-fix` | **Ten runs, two storms**, five lead times each (24/48/72/90/120 h), on the fixed runoff chain, scored as excess cost against perfect foresight on the full objective. Oct 2021: matches hindsight **to 48 h**, ramps to ~**+69%** by 90 h. Aug 2022: matches **to 90 h** (≤ +5%), then **+158%** at 120 h — a cliff, not a ramp. **Do not average the two storms.** Hedging (minimax regret) is better in 1 run of 10, by 0.16 points. Never quote freeboard retention; read `excess_cost_vs_perfect_foresight_pct`. `scripts/forecast_error_study.py`, [docs/validation.md](docs/validation.md) §4 |
| Cascade co-optimisation | ✅ Done | Am4l-babu | `feature/deep-research` | Run, and **the result is a warning, not a win**: optimising the two dams independently puts the joint peak at their confluence **126% above what actually happened**, and retiming both start hours recovers only 9% of that. `scripts/cascade_coordination.py` |
| **Joint cascade objective** | ✅ Done | Am4l-babu | `feature/joint-cascade-objective` | Built 8 Sep: one shared flood term on the *combined* routed discharge at the confluence, each dam keeping its private dam-safety, revenue and gate-wear terms; same functional form and weights, so only the flood term moves. Searched by coordinate descent from the independent optima. **On the data as held it is inert** — the combined peak is 911 cumecs against a 1,100 cumec bankfull, so the shared flood term is identically zero, the objective collapses to the sum of private costs, and descent converges in **zero moves**. This *corrects* the earlier diagnosis: the blocker is not the objective's structure but the ungauged lateral inflow. An assumed-lateral sweep (an **assumption, not a measurement**) stays inert to 200 cumecs and bites at 300, where Idukki starts 42 h earlier and releases more gently. `scripts/cascade_joint_objective.py`, [PR #18](https://github.com/Am4l-babu/aqua-sync/pull/18) |

## Scenarios & Validation

| Component | Status | Assigned To | Branch | Notes |
|---|---|---|---|---|
| Oct 2021 flagship scenario | ✅ Done | Am4l-babu | `feature/project-scaffold` | Replay MAE 0.30 m / max 0.57 m over 20 days |
| Cascade evidence (2 dams) | ✅ Done | Am4l-babu | `feature/project-scaffold` | Both dams opened gates 20 Oct 2021, same river, same day |
| Lead-time study | ✅ Done | Am4l-babu | `feature/project-scaffold` | ~3 m cushion at every lead time; spill share 61% → 40% |
| Aug 2022 out-of-sample | ✅ Done | Am4l-babu | `feature/deep-research` | 0.319 m MAE against October 2021's 0.303 m — within 5% on an episode never tuned to. Wrinkle: the drift direction flips between episodes, which weakens the single-missing-loss-term explanation. `scripts/out_of_sample_replay.py` |
| Aug 2022 as the second forecast-error storm | ✅ Done | Am4l-babu | `feature/second-storm-and-doc-refresh` | All five runs complete on disk 30 Aug – 6 Sep and interpreted (see the Decision Engine row and [HANDOVER.md](HANDOVER.md) §6). Committed 7 Sep — [PR #8](https://github.com/Am4l-babu/aqua-sync/pull/8), pending review |
| Sentinel-1 SAR validation | 📋 Todo | — | — | Optional. Validates flood *extent*, never timing (6–12 day revisit) |

## Hardware (V1 rig)

| Component | Status | Assigned To | Branch | Notes |
|---|---|---|---|---|
| BOM & sourcing | ✅ Done | Am4l-babu | `feature/project-scaffold` | 4 tiers, ₹6,250 for V1 (corrected 28 Aug 2026 — was ₹6,150, didn't match its own line items). Shoppable HTML with live vendor links. See [hardware/bom/](hardware/bom/) |
| Firmware skeleton | ✅ Done | Am4l-babu | `fix/firmware-defects` | PlatformIO, sensor fusion + safety interlock structure. Still untested on hardware. **Five defects fixed 8 Sep before the board is flashed:** non-finite floats printed as bare `nan` (invalid JSON) now emit `null`; Wi-Fi never reconnected after a drop; gate state shared with an ISR was neither `volatile` nor `portMUX`-guarded; the stepper enable pin was left asserted after a move; and the air-vs-water temperature approximation is now documented rather than implied. [PR #17](https://github.com/Am4l-babu/aqua-sync/pull/17) |
| Order V1 components | ✅ Done | Am4l-babu | — | **Ordered and received — components in hand, confirmed 8 Sep.** Unblocks every remaining hardware row. **9 Sep: two SX1278 LoRa modules and further components ordered**, which pulls the V2 radio link forward — see the LoRa row |
| Bench-test firmware | ✅ Done | Am4l-babu | `fix/bench-tests-and-sensor-fusion-gap` | Six standalone PlatformIO projects, one per V1 sensor/actuator, each with a wiring diagram and pass/fail criteria copied from `node_reservoir`'s own constants — Wednesday's "test every part alone" now has something to flash. All six compile clean. See [`firmware/bench/`](firmware/bench/). [PR #28](https://github.com/Am4l-babu/aqua-sync/pull/28) |
| Two-tank rig build | 📋 Todo | — | — | Acrylic tanks, pump loop, sluice gate |
| Level sensing + EKF | 🚫 Blocked | — | — | JSN-SR04T + DS18B20 temperature compensation. **🔴 Decision needed before wiring GPIO36.** `main.cpp`'s `readPressureDepth()` expects a 0–5 V hydrostatic pressure transducer to seed the boot-time level estimate and to act as the fallback the code trusts *more* than the ultrasonic reading when the two disagree — but **that transducer is not in the V1 BOM**. It is a V3 line item (`hardware/bom/bom.html`, ₹1,800), which says in its own words that it is "what makes fault detection possible." Left unwired, the ADC pin floats and can pass its own sanity check on RF/PWM noise alone, so `sensors_agree` can flip with no fault switch touched — undermining the fault-injection demo's central beat. Two ways out: order the ₹1,800 part, or redesign the fault story around the one real sensor and disable the pressure path honestly. Found 9 Sep writing the bench-test suite; not fixed pending this call. [PR #28](https://github.com/Am4l-babu/aqua-sync/pull/28) |
| Stepper gate control | 📋 Todo | — | — | NEMA 17 + A4988 + limit switches. **This actuates the bench rig's model sluice gate and nothing else.** Kerala's dam gates are operated by KSEB and the district administration; AquaSync has no path to them, is advisory permanently, and the command topic on the live API is deliberately not wired |
| Telemetry (MQTT/WebSocket) | ✅ Done | Am4l-babu | `feature/rig-mqtt-bridge` | The firmware had published to `aquasync/reservoir/01/telemetry` since it was written and nothing subscribed. `aquasync.api.rig` now parses the frames, follows the SHA-256 record chain and serves `GET /api/rig`; opt-in via `AQUASYNC_MQTT_HOST` so the offline demo stays offline. Rig values carry `scope: SCALE_RIG` and are never converted to m MSL — a 400 mm tank is not a reservoir. Verified end to end against mosquitto: chain 2/2, 0 breaks, a jammed frame reporting commanded 70% vs verified 21%. Receive-only; the command topic is deliberately not wired. [PR #14](https://github.com/Am4l-babu/aqua-sync/pull/14) |
| Fault injection demo | 🔄 Ongoing | Am4l-babu | — | Sensor-failure and gate-jam switches. **This is the beat that wins the room.** The dashboard side is done and now **verified in a browser, 9 Sep**: a simulated ESP32 published hash-chained frames over mosquitto with a gate jam and a dead ultrasonic injected, the bridge verified 12/12 frames with 0 breaks, and the red banner rendered across the 3D view reading *ACTUATOR DISAGREEMENT — commanded 70%, verified 21%*. The reservoir stayed labelled REPLAY while the rig showed LIVE, so the two provenances do not blur. **What is left is only the physical switches and the firmware paths behind them** — the software they will drive is proven |
| LoRa fallback (V2) | 🔄 Ongoing | Am4l-babu | — | **Two SX1278 (Ra-02) modules ordered 9 Sep** — 433 MHz, the legal ISM band in India, not the 868 MHz modules widely recommended online, which are the European allocation. Two is the right count: a radio link needs both ends. Deferred to V2 by [ROADMAP.md](ROADMAP.md), so this is bench-only until the V1 rig runs end to end — it must not displace fault injection |

## Interface

| Component | Status | Assigned To | Branch | Notes |
|---|---|---|---|---|
| 3D twin dashboard | ✅ Done | Am4l-babu | `feature/real-terrain-3d-twin` | Rebuilt 8 Sep on **measured ground**: `scripts/build_terrain.py` bakes 18 km of the real Periyar valley from the DEM tiles the catchment work already caches (448², 40 m posting), and the reservoir footprint is derived from the DEM's flat water sheet rather than drawn, so the shoreline walks up actual topography as the level moves. Shader water, sky, fog, and a procedural arch dam sized off the real 365.85 m crest. A caption states which parts are measured and which are schematic. Verified in headless Chrome. [PR #13](https://github.com/Am4l-babu/aqua-sync/pull/13). **Defect found and fixed 9 Sep:** the badge lit green **LIVE** the moment the WebSocket opened, while the stream underneath was a recorded October 2021 episode — the socket being open says the backend is reachable, not that anything is measured. Provenance is now declared by the server on every frame (`source`, defaulting to `REPLAY` so a forgetful path under-claims) and the dashboard displays what it is told; only LIVE is green. Six tests pin it. [PR #24](https://github.com/Am4l-babu/aqua-sync/pull/24). **Offline demo verified 9 Sep** — served with no backend at all, the scene renders, the bundled replay drives it and the recommendation still comes out, which is demo beat 6. That exposed `pollRig` logging a 404 per second when offline; it now backs off to 15 s and recovers without a reload. [PR #25](https://github.com/Am4l-babu/aqua-sync/pull/25) |
| FastAPI backend | ✅ Done | Am4l-babu | `feature/api-and-validation` | Eight REST routes (health, reservoirs, scenarios, counterfactual, what-if, crisis briefing, crisis score, tide) + telemetry WebSocket fan-out. Serves the dashboard same-origin |
| What-if panel | ✅ Done | Am4l-babu | `feature/whatif-wiring` | Wired 8 Sep — the slider POSTs to `/api/whatif` on release and the card shows the 72 h peak level, cushion at peak, whether it reaches FRL, and the advice sentence. Contract checked with curl against a running API (higher release → lower peak, larger cushion). **Browser-verified 8 Sep** — the card renders and hides correctly. [PR #10](https://github.com/Am4l-babu/aqua-sync/pull/10), merged into `development` |
| Crisis Commander mode | ✅ Done | Am4l-babu | `feature/crisis-commander` | Built 30 Aug. `dashboard/crisis.html` scored by `twin/crisis.py` with the same optimiser and objective as everything else. Hoard → 0.87 m less cushion than the day and −₹21 cr; release early → 2.95 m more and +₹45 cr (regenerated 31 Aug). **Visually verified end to end 8 Sep**, driven through a real browser over the DevTools protocol: the briefing loads, the sliders take an order, and committing renders the three-way outcome table (you / the operators / AquaSync) with the verdict and the colour coding. There *is* a headless browser on this machine — Chrome, plus cached Playwright binaries — which earlier notes wrongly said there was not |
| Malayalam alerting | 📋 Todo | — | — | Last-mile. Nice-to-have, not expo-critical |

## Documentation

| Component | Status | Assigned To | Branch | Notes |
|---|---|---|---|---|
| Project dossier (PDF) | ✅ Done | Am4l-babu | `feature/project-scaffold` | [docs/AquaSync_Project_Dossier.pdf](docs/AquaSync_Project_Dossier.pdf) — **24 pp**, regenerates from data. §4.4 forecast error (**both storms**, on separate axes), §4.5 cascade, §4.6 runoff |
| Architecture | ✅ Done | Am4l-babu | `feature/project-scaffold` | [docs/architecture.md](docs/architecture.md) — now carries a per-layer status note |
| Data sources & corrections | ✅ Done | Am4l-babu | `feature/project-scaffold` | [docs/data-sources.md](docs/data-sources.md) — plus the sources the research sweep acquired |
| Roadmap | ✅ Done | Am4l-babu | `feature/project-scaffold` | [ROADMAP.md](ROADMAP.md) — refreshed 31 Aug: ten items, a timeline, a dependency map |
| Action plan | ✅ Done | Am4l-babu | `feature/project-scaffold` | [ACTION_PLAN.md](ACTION_PLAN.md) — re-dated 31 Aug; the earlier plan had Week 2 starting on a Wednesday |
| Validation report | ✅ Done | Am4l-babu | `feature/api-and-validation` | [docs/validation.md](docs/validation.md) — every claim with its error bar; the second storm added 31 Aug; explicit list of what is **not** validated |
| Project abstract (PDF) | ✅ Done | Am4l-babu | `feature/docs-corrections` | [docs/AquaSync_Abstract.pdf](docs/AquaSync_Abstract.pdf) — 4 pp, the one-sitting version |
| ICFOSS portfolio analysis (PDF) | ✅ Done | Am4l-babu | `feature/docs-corrections` | [docs/AquaSync_ICFOSS_Analysis.pdf](docs/AquaSync_ICFOSS_Analysis.pdf) — 10 pp: what Kerala's open-source institute has already built, and which of it AquaSync can stand on |
| Deep research report (PDF) | ✅ Done | Am4l-babu | `feature/deep-research` | [docs/AquaSync_Research_Report.pdf](docs/AquaSync_Research_Report.pdf) — 59 pp, 144 verified sources, including the five that contradict this project's thesis. **Determinism fixed 8 Sep:** it embedded the day it was built, so every rebuild produced a different PDF and `check.py`'s regeneration check failed on a document nobody had changed. The date is now an 8-character digest of the parsed index files. [PR #16](https://github.com/Am4l-babu/aqua-sync/pull/16) |
| Working agreements (CLAUDE.md) | ✅ Done | Am4l-babu | `feature/contributor-rule` | [CLAUDE.md](CLAUDE.md) — human contributors only, the gate, and (31 Aug) an operating loop, a writing guide, a numbers ledger and a definition of done |
| Handover brief | ✅ Done | Am4l-babu | `feature/second-storm-and-doc-refresh` | [HANDOVER.md](HANDOVER.md) — written 30 Aug, refreshed 31 Aug, committed 7 Sep |
| Second storm into dossier §4.4 + Figure 6 | 👀 In Review | Am4l-babu | `feature/second-storm-into-dossier` | Written 9 Sep. §4.4 now carries a second-storm subsection and Figure 6 a second row — **separate axes and separate y-limits, never one shared curve**, because the two episodes are not equally hard and the penalties past the flat region differ by more than a factor of two. The structure reproduces but the shape does not: October ramps to a +69% plateau, August holds within +5% to 90 h then jumps to +158% in one 30-hour step. Perfect foresight on August *gains* **−1.46 m** of cushion — the hindsight-optimal policy ends higher than the operators did. **Two more unfiltered globs found and fixed:** `build_abstract.py` counted study *files* as lead times and said "across 10 lead times" (there are five, run twice), and `build_icfoss_analysis.py` merged both storms into one excess-cost range. Any `glob("forecast_error_study_*")` without a scenario filter is a defect. Full `check.py` green. [PR #20](https://github.com/Am4l-babu/aqua-sync/pull/20) |
| Poster (A1) | 📋 Todo | — | — | Figures 1, 4 and 5 carry it. Print by expo minus 3 days |
| Pitch rehearsal | 📋 Todo | — | — | Script is in the dossier §12 |

---

## Open risks

| Risk | Severity | Mitigation |
|---|---|---|
| Expo entry status unknown | 🟢 Closed | **Confirmed 8 Sep: the entry is in.** The schedule in [ACTION_PLAN.md](ACTION_PLAN.md) applies |
| Hardware ordering delay blocks the rig | 🔴 High | Still unordered on Monday 31 Aug, and this is the rig-build week. 3–5 day delivery. Software is fully demonstrable without it, but EVOKE is an IoT club event |
| Independent per-dam optimisation makes the shared downstream peak worse | 🔴 High | Measured at 126% above observed. Do not present cascade results as a coordination win, and do not ship per-dam optimisation as if it degrades gracefully. Fix is a joint objective |
| Forecast-error result rests on two storms of very different difficulty | 🟠 Medium | Degradation reproduces in both, but Oct 2021 breaks at 48 h and plateaus at +69% while Aug 2022 holds to 90 h then jumps to +158%; Aug 2022 sat nearly 5 m below FRL. Qualify by reservoir state; never average the two. A third, harder storm is the next thing the study needs |
| Crisis Commander has never been seen rendered | 🟢 Closed | Driven through a real browser 8 Sep; the briefing, the order and the outcome table all render. Nothing needed fixing |
| Routing K/x anchored, not calibrated → downstream discharge is indicative | 🟠 Medium | Calibration attempted and failed on daily data (r² = 0.005); the CWC 8 h anchor stands. Do not quote Aluva discharge as measured. Needs the 15-minute telemetry feed |
| Runoff amplitude unvalidated (NSE 0.07, no recession limb) | 🟠 Medium | Disclosed in validation.md. Shape is usable, amplitude is not |
| `backend/data/raw/` is committable | 🟢 Low | Fixed 7 Sep: `.gitignore` anchored with `**/data/raw/` and `**/data/external/`; the stray 740 KB `backend/data/raw/Idukki.json` deleted |
| Feature creep across 25 candidate upgrades | 🟠 Medium | Phases 0–3 + V1 rig is the scope. Everything else is [ROADMAP.md](ROADMAP.md) backlog |
| Perfect-foresight assumption inflates every benefit figure | 🟢 Low | **Measured, ten runs, two storms.** Quote excess cost, never freeboard retention |
| Upstream dataset changes or disappears | 🟢 Low | `data/processed/` is committed, so results stay reproducible |

## Verified facts worth not re-deriving

- **31 August 2026 is a Monday.** Registration closed Saturday 22 August.
- Dataset coverage: **2020-08-13 → 2026-08-26**. There is **no 2018 data**.
- Corrupt block: **2020-09-25 → 2021-04-30** (~11% of rows), plus 2025-06-04.
- Idukki: FRL 732.43 m, rule 728.50 m, live storage at FRL 1,459.49 Mm³.
- Idamalayar: FRL 169.00 m, rule 164.00 m, live storage at FRL 1,017.80 Mm³.
- Oct 2021: level 728.81 m on the 16th → 168 mm rain on the 17th → inflow
  115.7 → 879.2 cumecs → gates open on the 20th at 730.95 m.
- Both dams opened spillways on **20 Oct 2021**: 83.85 + 128.13 cumecs.
- Forecast-driven excess cost against perfect foresight (expected value),
  Oct 2021: **+0%** at 24 h and 48 h, **+37%** at 72 h, **+69%** at 90 h and
  120 h. Perfect foresight buys 3.11 m of cushion at a total cost of 1.96
  and Rs +1.94 crore.
- Same, Aug 2022: **+0%**, **+5%**, **+5%**, **+5%**, **+158%**. Perfect
  foresight costs 0.75, ends **1.46 m higher** than the operators did, earns
  Rs +1.42 crore. Minimax regret beats expected value in exactly one of the
  ten runs (Aug 48 h, by 0.16 points) and loses in seven.
- Runoff chain: 168 mm/day gives 88.97 mm of runoff as one daily step and
  **0.00 mm** driven hourly if initial abstraction is charged per step.
  That was the bug; effective rainfall is now timestep-invariant.
- Cascade joint peak at the confluence: observed **403**, each dam optimised
  alone **911**, coordinated retiming **828** cumecs. Two dams' contribution
  only — no lateral inflow, so never read these against bankfull (1,100).
- Aug 2022 out-of-sample replay: **0.319 m MAE** vs Oct 2021's 0.303 m.
- Neeleeswaram routing fit: **r² = 0.005** on 1,967 days. Daily is too coarse.
- Crisis Commander, Oct 2021 desk: hoard (731 m, h200, 60 cumecs) → peak
  732.41 m, 0.87 m less cushion than the day, −₹21 cr; release early
  (727.5 m, h0, 400 cumecs) → 728.59 m, 2.95 m more, +₹45 cr. Regenerated
  from `aquasync.twin.crisis.score` on 31 Aug; not cached on disk.
- Documents: dossier **24 pp**, abstract 4, ICFOSS analysis 10, research
  report 59. Tests: **91**.
- The optimiser independently converged on 728.43 m, against KSEB's published
  rule level of 728.50 m.
