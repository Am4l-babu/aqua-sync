# AquaSync — Roadmap

Sequencing, and — more importantly — what is deliberately **not** being built.

The planning material behind this project accumulated twenty-five candidate
upgrades. Each is individually sound. Attempting more than two produces a
table of half-working prototypes with no time left to rehearse, which is the
most common way a strong idea loses a competition. This document exists to
make the cut explicit and to stop it being relitigated every week.

---

## Phase map

| Phase | Weeks | Deliverable | Done when |
|---|---|---|---|
| **0 · Foundation** | 0.5 | Repo, ingestion, validation | Both dams load clean; quality report prints |
| **1 · Twin core** | 1.5 | Mass balance, calibration, replay | Observed Oct 2021 level reproduced to < 0.5 m |
| **2 · Routing & tide** | 1.5 | Muskingum reaches, harmonic tide | Downstream hydrograph with a stated travel time |
| **3 · Decision engine** | 1.5 | Policy search, baseline comparison | A counterfactual with a defensible headline number |
| **4 · Hardware rig** | 2 | Two-tank HIL bench | Twin drives the gate; fault injection recovers |
| **5 · Interface** | 1.5 | 3D twin, what-if, Crisis Commander | A stranger can run the demo unaided |
| **6 · Hardening** | 1 | Tests, docs, rehearsal, poster | Full demo runs with the network cable pulled |

Phases 0–3 are **complete** as of 26 August 2026. Phase 4 is blocked only on
ordering components. Phase 5 has a working 3D dashboard but no live backend.

Each phase ends in something demonstrable, so the project is presentable at
any point after Phase 2 rather than only when finished. That is deliberate:
it means a slipped week costs polish, not the demo.

---

## In scope, not yet done

Ordered by value per hour. The first item is worth more than the rest combined.

### 🟢 1 · Forecast-error study — five lead times, re-run on a fixed chain, 30 Aug 2026

The optimiser sees the **true** inflow when choosing a policy, so every
benefit figure elsewhere is a ceiling. This closes that gap.

**Run:** `python scripts/forecast_error_study.py` once per lead time
(commands in `docs/validation.md` §4). A 30-member NOAA GEFS ensemble issued
before the storm, bias-corrected against IMD gridded rainfall, pushed through
the SCS-CN and Muskingum chain, one policy committed to per member, scored
against what actually happened.

**Scored on the optimiser's own objective** — flood, dam safety, revenue and
gate wear together. Zero means the forecast picked the policy hindsight would
have picked, and the figure can never go below it:

| Lead time | Expected value | Minimax regret |
|---|---|---|
| 24 h | **+0%** | +19% |
| 48 h | **+0%** | +19% |
| 72 h | **+37%** | +53% |
| 90 h | **+69%** | +85% |
| 120 h | **+69%** | +69% |

1. **A real forecast is as good as hindsight out to 48 hours.** Exactly +0% at
   both 24 h and 48 h, degrading through 72 h to a plateau near +69% from 90 h
   on. The system's value is concentrated in the last two days before a storm.

2. **Retracted: "minimax-regret never underperforms expected-value."** Across
   five lead times hedging is never better and usually worse. It buys cushion
   by over-releasing and pays in revenue — Rs +1.34 to +1.40 crore against
   perfect foresight's +1.94.

3. **Lead time explains it, the bias correction does not** (r = 0.93 against
   0.61). The 48 h run carries one of the largest bias corrections in the set
   and still matches hindsight exactly.

**Why the numbers here changed completely.** The earlier version of this
section reported 26–74% retention of the perfect-foresight cushion and
concluded hedging was a safe default. Both came from a rainfall-runoff chain
carrying the defect in item 8 — it charged the curve number's initial
abstraction against every timestep, produced almost no runoff, and so made
every ensemble member look benign. The study was re-run end to end once that
was fixed.

**Do not quote freeboard retention from this study.** Every forecast-driven
policy ends *lower* than the hindsight optimum, so a cushion-only metric reads
above 100% and looks like beating hindsight. It is over-release. The JSON
keeps the old field with a `metric_note` saying so;
`excess_cost_vs_perfect_foresight_pct` is the one to read.

**Still open:** five points, one storm, and the 48→90 h transition rests on a
single 72 h run. A second storm in another monsoon is the next thing this
study needs.

### 🟢 2 · Cascade co-optimisation — first result in, and it is a warning, 28 Aug 2026

Idukki and Idamalayar are currently optimised independently everywhere else
in this project. The whole evidence base (Figure 2) is that they failed
*jointly* — same river, same day. Scheduling them together so their release
pulses deliberately do not superpose looked like it should be the single
most valuable modelling addition.

**Run:** `python scripts/cascade_coordination.py`. `RiverNetwork` — a DAG
router already implemented and exported, but never used outside its own
module, not even in a test — routes Idukki's release through periyar_upper
then periyar_lower and Idamalayar's release directly into periyar_lower at
the confluence, over the October 2021 window (481 hourly steps, both dams).

| Scenario | Joint peak at periyar_lower |
|---|---|
| Observed (what actually happened) | 403 cumecs |
| Each dam optimises alone (existing single-dam tooling, unchanged) | **911 cumecs — 126% worse than observed** |
| Coordinated (timing search over both dams' `start_hour`) | 828 cumecs — 9% better than naive, still 105% worse than observed |

**This is not the finding the section header used to promise, and saying
so plainly is more useful than reframing it as one.** Two things:

1. **Independently optimising each dam is not neutral — it can actively
   make the shared downstream peak worse than doing nothing coordinated at
   all.** Idukki's own optimum releases up to 828 cumecs (the ceiling of
   its rate grid) because, evaluated against periyar_lower's 1,100-cumec
   bankfull threshold *alone*, that looks completely safe. It is not safe
   once Idamalayar's simultaneous 314 cumecs is added at the same
   confluence — a combination neither dam's own objective function can see,
   because each one scores itself as if the shared reach belonged to it
   alone. Generalising single-reservoir optimisation to two coupled
   reservoirs without giving each one visibility into the other is not a
   simplification that degrades gracefully; it degrades to something worse
   than the historical, uncoordinated baseline.
2. **Retiming alone does not fix it.** The coordination search swept both
   dams' `start_hour` — the most direct reading of "make the pulses not
   superpose" — and recovered only 9% of the gap it opened (911 to 828),
   nowhere close to the observed 403. That means the fix this section's
   name implies (schedule them together) is not primarily a timing
   problem once each dam is already independently optimised for its own
   safety at maximum rate; it is an objective-function problem. The real
   next step is not a bigger timing search but a genuinely joint
   objective — each dam's policy search scored against the actual combined
   downstream discharge, not its own reach evaluated in isolation. That is
   a bigger redesign than this script attempts and is the correctly-scoped
   next piece of work, not something to also cram in here.

**Caveat that matters for reading the cumec figures above:** these are the
two dams' combined contribution only. `RiverNetwork.route_all` supports a
`lateral_inflows` parameter for the ungauged catchment between the dams and
Aluva, and it was not populated — no tributary or local-runoff series exists
in this project's data holdings. **Do not compare these numbers to
periyar_lower's bankfull/danger thresholds as if they represented total
river discharge; they do not**, which is also why even the "naive" 911-cumec
figure sits below bankfull (1,100) despite representing what the evidence
says was a real near-miss at Aluva. The relative comparison between the
three scenarios is valid; the absolute cumec values are not a flood-risk
verdict on their own.

Method, full numbers and the independent-policy parameters in
`data/processed/cascade_coordination.json`.

### 🟠 3 · Routing calibration against gauges — attempted, blocked by data resolution, 28 Aug 2026

K and x are no longer pure geometry: they are anchored to CWC's published
8-hour Idukki→Neeleeswaram travel time. But that is one number from a MIKE-11
model run "only for 2018", not a gauge-pair calibration.

**Run:** `python scripts/routing_calibration.py`, combined Idukki +
Idamalayar daily release (KSEB bulletin, 2020-08-13 onward) against CWC's
Neeleeswaram daily discharge (`cwc_kerala_daily_discharge_2001_2025.csv`,
1,967-day overlap). `MuskingumReach.calibrate` — implemented, previously
only unit-tested against synthetic data — ran against real gauge data for
the first time.

**Result: the fit failed cleanly, and the failure is itself the finding.**
K = 263 h, x = 0.50 (the search grid's edge, not an interior optimum),
r² = 0.005. **The CWC 8-hour anchor is unchanged — nothing in
`constants.py` was touched.** Daily data (dt = 24 h) is ~3x coarser than
the 8-hour signal it would need to resolve; by the time a day's release
shows up in that day's Neeleeswaram reading, the flood wave has already
fully transited the reach, leaving no timing signal for a day-to-day fit
to find. Converting Neeleeswaram to hourly via the GUARDIAN rating curves
already on disk would not fix this — the bottleneck is the *release*
record (KSEB is daily-only), not the gauge record. `docs/data-sources.md`
already named the actual fix before this attempt: the **CWC 15-minute
telemetry feed**, "the single highest-value upgrade to the data layer."
This result is independent, quantified confirmation of that claim
(r² = 0.005), not a new open question.

Full method and reasoning in `docs/validation.md` §4 "River routing".

**The 2018 gauge gap is now moot for this specific attempt** (the KSEB
release record starts 2020-08-13, after the 2018 flood, so 2018 was never
in the calibration window regardless of the Neeleeswaram gap at
2018-08-16 to 08-27) but remains true and worth keeping on record: the 2018
flood peak was never gauged at Neeleeswaram at all, so any future
2018-specific work is extrapolation, not interpolation.

CAMELS-IND v2.2 (`10.5281/zenodo.14999580`) and its matched IMD rainfall
forcing were considered as an alternative route, and are not — CAMELS-IND
solves a rainfall-runoff calibration problem (ROADMAP item on the
rainfall–runoff chain, `docs/validation.md` §4 "Rainfall–runoff"), not
this routing problem, since it does not carry dam release records either.

### 🟠 4 · V1 hardware rig

Blocked on ordering. EVOKE is an **IoT club** event — a software-only
submission will underperform regardless of how good the modelling is.

### ✅ 5 · Out-of-sample scenario (Aug 2022) - done, 28 Aug 2026

`python scripts/out_of_sample_replay.py --scenario idukki_aug_2022`. Mean
absolute error 0.319 m against October 2021's 0.303 m - within 5% on an
episode never tuned to, which is the "fitted" vs "validated" distinction
this item existed to close. One honest wrinkle: the drift direction flips
between episodes (Oct 2021 ends +0.517 m high, Aug 2022 ends -0.273 m low),
which weakens the single-missing-loss-term explanation in
`docs/validation.md` §2 and points at event-specific interpolation timing
instead. Full comparison table in `docs/validation.md` §2b.

### 🟡 6 · Crisis Commander demo mode

High demo value for low build cost. "You are the operator. It is 16 October
2021. What do you do?" — then show the optimiser's answer. It proves the
system's value through experience rather than explanation, and it draws a
crowd, which matters at an expo.

### 🟡 7 · FastAPI backend + live what-if

The 3D dashboard exists but replays a canned series. Wiring it to a live
backend makes the what-if panel real.

### 🟢 8 · Rainfall–runoff validation — done, and it found a defect, 30 Aug 2026

The last unvalidated link in the twin, and the one under everything item 1
claims: the forecast-error study drives this chain, so its retention figures
inherit whatever error lives here.

**Run:** `python scripts/runoff_validation.py`. No new data was needed — the
KSEB bulletin publishes daily rainfall *and* daily inflow for the same
reservoir, giving four complete monsoon seasons (2021–2024, 722 scored days).

**The first run returned NSE −1.14 at −100% volume bias: the model produced
essentially no runoff at all.** The curve-number equation is an event-total
relation whose initial abstraction is charged once per storm, but
`inflow_series` was applying it to every timestep independently. Since Ia for
CN 72 is 19.8 mm — more than an hour of even extreme rain — the same 168 mm
that fell on 17 October 2021 yielded 88.97 mm of runoff as one daily step and
**0.00 mm** driven hourly. The chain's answer depended on the timestep it was
handed, and the forecast-error study drives it hourly.

Fixed by accumulating rainfall within a storm and differencing the cumulative
effective depth, with storms separated by a rainless gap. Effective rainfall
is now identical at 30 min, 1 h, 3 h and 24 h, and
`TestStormExcess::test_excess_is_independent_of_driving_timestep` pins it.
**Item 1 was re-run against the fixed chain.**

With the defect gone the honest scoring is mixed, and worth stating as such:

| | |
|---|---|
| Pooled volume bias, handbook CN 72 | **−1%** — but per season −7%, −3%, **+38%**, −17% |
| Shape (r²) | 0.55 — rises and falls with the observed hydrograph |
| Amplitude (NSE) | **0.07** — peaks overshoot, and inflow returns to zero between storms |
| Calibrated curve number | Pins at **50, the grid floor**; leave-one-season-out mean NSE −0.02, worst −0.91 |

The grid-edge optimum is the same signature the routing calibration produced
(item 3), and the same diagnosis: a structural mismatch being absorbed by a
parameter. Calibration was **not adopted** — it buys in-sample fit and pays in
volume bias and generalisation. The handbook 72 stays.

So the chain is fit for "roughly how much water, roughly when", and not for
day-ahead inflow to a useful tolerance. Fixing that is a continuous
soil-moisture model with a recession limb, not a better curve number — which
is a genuine piece of work, and squarely in the "beyond the expo" column.

Full method, caveats and the per-season table in `docs/validation.md` §4
"Rainfall–runoff".

---

## Explicitly deferred

Not rejected — deferred, with the reason recorded so it is not re-argued.

| Idea | Why deferred |
|---|---|
| **2D inundation (LISFLOOD-FP / HEC-RAS)** | The right long-term answer for street-level depth, and the natural successor to 1D routing. Needs a calibrated DEM and roughness field — a project in itself. Post-expo |
| **Sentinel-1 SAR auto-calibration** | Validates flood *extent* but never *timing*, because the revisit is 6–12 days. Genuinely impressive, but it does not improve a decision made on a 72-hour horizon |
| **Graph neural network routing** | Would need years of multi-station training data we do not have. Muskingum with honest error bars beats a GNN trained on 2,000 daily rows |
| **Agent-based evacuation simulation** | Excellent idea, entirely separate project. The twin must first be trusted about water before anyone models people |
| **Reinforcement-learning gate policy** | The policy space here is three parameters and enumerable. RL would add opacity and remove the explainability that makes the recommendation adoptable |
| **Post-quantum SCADA cryptography** | Solving a problem the project does not have yet. Revisit if a utility integration becomes real |
| **Autonomous bathymetry boat** | Real data gap (riverbed geometry shifts each monsoon), genuinely cool, and a three-week build that competes directly with rehearsal time |
| **Thermal seepage / hydrophone leak detection** | Dam *structural* health is a different problem from dam *operation*. Conflating them weakens both stories |
| **Blockchain release ledger** | A SHA-256 hash chain gives the tamper-evidence needed at a fraction of the complexity. Already in the firmware design |
| **WebXR / AR overlay** | Pure spectacle. Considered only if everything else is finished and rehearsed |
| **PINN / learned hydraulic surrogates** | Verified reject. Surrogates pay when the physics model is the bottleneck — hours per run. AquaSync's forward model is a power law plus SCS-CN plus Muskingum, effectively instantaneous, which is the only reason the exhaustive policy search is tractable. PINN accuracy for shallow-water problems is still below conventional solvers. Revisit only if 2D inundation is added |
| **Eclipse Ditto / Azure Digital Twins / NVIDIA Omniverse** | Verified reject, all three. Healthy products aimed at problems this project does not have: device-shadow sync across IoT fleets, a DTDL graph over many-noded assets, GPU physics-ML at CFD scale. AquaSync is two reservoirs and one river. "Digital twin" in the title describes what the model *does*, not a mandate to buy a product with the phrase in its marketing |
| **Google Flood Forecasting API for the hindcast** | Verified reject *for historical work*. India is a supported country and the feed is genuinely useful for live operation, but `queryGaugeForecasts` imposes a hard floor: "Start time cannot be earlier than 2023-10-01". October 2021 is permanently unreachable. Access also needs waitlist approval Google warns "might take several months". Use GRRR instead |
| **Malayalam NLP social sentinel** | Interesting validation signal, but it confirms a flood after it starts — the twin exists to act before |
| **Dam-breach mode** | Different hazard class, different regulatory context. Post-expo |

---

## Beyond the expo

| Horizon | Work | Why |
|---|---|---|
| 3–6 months | CWC 15-minute telemetry; 2D inundation; field-deploy one ESP32 node; SAR extent validation | Moves from daily hindcast to operational nowcast |
| 6–12 months | Shadow-mode trial with KSEB/KSDMA; Malayalam last-mile alerting via LDMC and Kudumbashree; OGC SensorThings output | Builds the operational trust record adoption requires |
| Beyond | All Kerala cascades; ensemble policies; public tamper-evident release ledger | From one basin to a statewide decision layer |

**Shadow mode is the only realistic adoption path.** No utility will accept an
external recommendation engine on trust. Running alongside real operations for
a full monsoon, logging what it would have advised, and publishing the
comparison is slow, unglamorous, and the only thing that would actually work.

---

## The scope rule

> **Phases 0–3 plus a working V1 rig is a complete, winning project.**

If a new idea arrives, it goes in the deferred table above. It does not go
into the build. The two upgrades already chosen are the **fault-injection
demo** (Phase 4) and the **Crisis Commander mode** (Phase 5), and those are
the last two.
