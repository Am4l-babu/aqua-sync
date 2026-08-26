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

### 🔴 1 · Forecast-error study

The optimiser currently sees the true inflow series when choosing a policy.
Real forecasts are wrong, and rainfall forecasts over the Western Ghats are
wrong in specific, biased ways. **Every benefit figure in the dossier is
therefore an upper bound.**

The work: drive the policy search from perturbed inflow forecasts with
realistic error growth (say ±20% at 24 h widening to ±60% at 120 h), run an
ensemble, and report how much of the ~3 m cushion survives.

Why it matters more than anything else: the first domain-literate person to
look at this will ask "what happens when the forecast is wrong?" Having the
answer converts the project from a promising demo into a credible result.
Not having it makes every other number suspect.

### 🔴 2 · Cascade co-optimisation

Idukki and Idamalayar are currently optimised independently. The whole
evidence base (Figure 2) is that they failed *jointly* — same river, same
day. Scheduling them together so their release pulses deliberately do not
superpose is the single most valuable modelling addition.

The routing layer is already a DAG (`RiverNetwork`), so the work is extending
the policy search across nodes rather than rebuilding anything.

### 🟠 3 · Routing calibration against gauges

Muskingum K and x currently come from reach geometry, not from gauge pairs.
Downstream discharge figures are consequently indicative, not measured, and
that limits what can honestly be claimed about Aluva.

Needs CWC gauge records at Neeleeswaram and Aluva. `MuskingumReach.calibrate`
already implements the fit; it just needs data.

### 🟠 4 · V1 hardware rig

Blocked on ordering. EVOKE is an **IoT club** event — a software-only
submission will underperform regardless of how good the modelling is.

### 🟠 5 · Out-of-sample scenario (Aug 2022)

The model is calibrated on October 2021. Showing it works on an episode it
was never tuned to is the difference between "fitted" and "validated". The
scenario is already defined; it needs a run and a write-up.

### 🟡 6 · Crisis Commander demo mode

High demo value for low build cost. "You are the operator. It is 16 October
2021. What do you do?" — then show the optimiser's answer. It proves the
system's value through experience rather than explanation, and it draws a
crowd, which matters at an expo.

### 🟡 7 · FastAPI backend + live what-if

The 3D dashboard exists but replays a canned series. Wiring it to a live
backend makes the what-if panel real.

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
