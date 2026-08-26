# AquaSync — Project Progress

Single source of truth for what is happening on this project. Lives on `main`
and is updated **directly on `main`**, not via PR. Read it at the start of
every session.

**Project:** AquaSync — decision-support digital twin for dam–river flood and
hydropower optimisation on the Periyar basin.
**Target:** EVOKE 26 Project Expo · Track 2, Climate Resilience & Disaster
Preparedness · MACE IoT Club, Kothamangalam.

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
| Test suite & CI | ✅ Done | Am4l-babu | `feature/api-and-validation` | 46 physics/behaviour tests passing; CI runs tests + ruff + a guard that the twin core stays web-framework-free |
| Deployment | 📋 Todo | — | — | Expo runs offline on a laptop by design. Optional: Streamlit Cloud / Fly.io free tier for a public link. **Do not** put this on paid infra |

## Simulation Core

| Component | Status | Assigned To | Branch | Notes |
|---|---|---|---|---|
| Reservoir mass balance | ✅ Done | Am4l-babu | `feature/project-scaffold` | Hourly Euler. Level↔storage power law |
| Level–storage calibration | ✅ Done | Am4l-babu | `feature/project-scaffold` | β = 1.348, r² = 0.9957, MAE 17 Mm³ on 1,836 validated rows |
| Rainfall–runoff (SCS-CN) | ✅ Done | Am4l-babu | `feature/project-scaffold` | AMC shift + triangular unit hydrograph. **Not yet validated against observed inflow** |
| Muskingum river routing | ✅ Done | Am4l-babu | `feature/project-scaffold` | Auto sub-reaching for numerical stability. **K and x are geometry estimates, not gauge-calibrated** |
| Muskingum–Cunge (ungauged) | ✅ Done | Am4l-babu | `feature/project-scaffold` | Flow-dependent K, x from channel hydraulics |
| Tidal backwater | ✅ Done | Am4l-babu | `feature/project-scaffold` | Kochi harmonics (M2/S2/K1/O1/N2) + effective conveyance. Offline-capable |
| Hydropower & tariff | ✅ Done | Am4l-babu | `feature/project-scaffold` | Hill-diagram efficiency, ToD tariff. Verified: 743 MW at rated flow vs 780 MW nameplate |
| Routing calibration vs gauges | 📋 Todo | — | — | **Highest-value modelling gap.** Needs CWC gauge data at Neeleeswaram / Aluva |
| Runoff model validation | 📋 Todo | — | — | Compare SCS-CN predicted inflow against observed bulletin inflow |
| 2D inundation | 📋 Todo | — | — | Deferred. LISFLOOD-FP or HEC-RAS on Bhuvan DEM. Not needed for the expo |

## Decision Engine

| Component | Status | Assigned To | Branch | Notes |
|---|---|---|---|---|
| Objective function & weights | ✅ Done | Am4l-babu | `feature/project-scaffold` | Flood / dam safety / revenue / gate wear, exposed as policy not constants |
| Rule-curve baseline | ✅ Done | Am4l-babu | `feature/project-scaffold` | Faithful model of reactive practice — the thing to beat |
| Policy search | ✅ Done | Am4l-babu | `feature/project-scaffold` | Exhaustive grid over (target level, start hour, max rate). Deterministic |
| Grid offtake constraint | ✅ Done | Am4l-babu | `feature/project-scaffold` | Without it the optimiser books revenue the grid would never take |
| **Forecast-error study** | 📋 Todo | — | — | 🔴 **Top priority.** Optimiser currently has perfect foresight, so every benefit figure is an upper bound. Must re-run with realistic forecast error |
| Cascade co-optimisation | 📋 Todo | — | — | Idukki + Idamalayar scheduled jointly. Routing layer is already a DAG |

## Scenarios & Validation

| Component | Status | Assigned To | Branch | Notes |
|---|---|---|---|---|
| Oct 2021 flagship scenario | ✅ Done | Am4l-babu | `feature/project-scaffold` | Replay MAE 0.30 m / max 0.57 m over 20 days |
| Cascade evidence (2 dams) | ✅ Done | Am4l-babu | `feature/project-scaffold` | Both dams opened gates 20 Oct 2021, same river, same day |
| Lead-time study | ✅ Done | Am4l-babu | `feature/project-scaffold` | ~3 m cushion at every lead time; spill share 61% → 40% |
| Aug 2022 out-of-sample | 📋 Todo | — | — | Scenario defined, not yet run. Needed to show the model was not tuned to one event |
| Sentinel-1 SAR validation | 📋 Todo | — | — | Optional. Validates flood *extent*, never timing (6–12 day revisit) |

## Hardware (V1 rig)

| Component | Status | Assigned To | Branch | Notes |
|---|---|---|---|---|
| BOM & sourcing | ✅ Done | Am4l-babu | `feature/project-scaffold` | 4 tiers, ₹6,150 for V1. See [hardware/bom/](hardware/bom/) |
| Firmware skeleton | ✅ Done | Am4l-babu | `feature/project-scaffold` | PlatformIO, sensor fusion + safety interlock structure |
| Order V1 components | 📋 Todo | — | — | 🔴 **Blocks all hardware work.** 3–5 day delivery |
| Two-tank rig build | 📋 Todo | — | — | Acrylic tanks, pump loop, sluice gate |
| Level sensing + EKF | 📋 Todo | — | — | JSN-SR04T + DS18B20 temperature compensation |
| Stepper gate control | 📋 Todo | — | — | NEMA 17 + A4988 + limit switches |
| Telemetry (MQTT/WebSocket) | 📋 Todo | — | — | Mosquitto is already installed locally |
| Fault injection demo | 📋 Todo | — | — | Sensor-failure and gate-jam switches. **This is the beat that wins the room** |
| LoRa fallback (V2) | 📋 Todo | — | — | SX1278 @ 433 MHz — India ISM band, not the 868 MHz usually recommended online |

## Interface

| Component | Status | Assigned To | Branch | Notes |
|---|---|---|---|---|
| 3D twin dashboard | ✅ Done | Am4l-babu | `feature/project-scaffold` | Three.js, no build step, WebSocket telemetry with lerp smoothing |
| FastAPI backend | ✅ Done | Am4l-babu | `feature/api-and-validation` | Scenario / what-if / tide endpoints + telemetry WebSocket fan-out. Serves the dashboard same-origin |
| What-if panel | 🔄 Ongoing | Am4l-babu | — | Slider works client-side and `/api/whatif` exists; they need wiring together |
| Crisis Commander mode | 📋 Todo | — | — | "You are the operator, it is 16 Oct 2021." High demo value, low build cost |
| Malayalam alerting | 📋 Todo | — | — | Last-mile. Nice-to-have, not expo-critical |

## Documentation

| Component | Status | Assigned To | Branch | Notes |
|---|---|---|---|---|
| Project dossier (PDF) | ✅ Done | Am4l-babu | `feature/project-scaffold` | [docs/AquaSync_Project_Dossier.pdf](docs/AquaSync_Project_Dossier.pdf) — 15 pp, regenerates from data |
| Architecture | ✅ Done | Am4l-babu | `feature/project-scaffold` | [docs/architecture.md](docs/architecture.md) |
| Data sources & corrections | ✅ Done | Am4l-babu | `feature/project-scaffold` | [docs/data-sources.md](docs/data-sources.md) |
| Roadmap | ✅ Done | Am4l-babu | `feature/project-scaffold` | [ROADMAP.md](ROADMAP.md) |
| Action plan | ✅ Done | Am4l-babu | `feature/project-scaffold` | [ACTION_PLAN.md](ACTION_PLAN.md) |
| Validation report | ✅ Done | Am4l-babu | `feature/api-and-validation` | [docs/validation.md](docs/validation.md) — includes an explicit list of what is **not** yet validated |
| Poster (A1) | 📋 Todo | — | — | Figures 1, 4 and 5 carry it. Print by expo minus 3 days |
| Pitch rehearsal | 📋 Todo | — | — | Script is in the dossier §12 |

---

## Open risks

| Risk | Severity | Mitigation |
|---|---|---|
| Perfect-foresight assumption inflates every benefit figure | 🔴 High | Forecast-error study is the top open item. Until then, present results as an upper bound and say so |
| Routing K/x uncalibrated → downstream discharge is indicative | 🟠 Medium | Do not quote Aluva discharge as measured. Calibrate against CWC gauges |
| Hardware ordering delay blocks the rig | 🟠 Medium | Order V1 today; software is fully demonstrable without it |
| Feature creep across 25 candidate upgrades | 🟠 Medium | Phases 0–3 + V1 rig is the scope. Everything else is [ROADMAP.md](ROADMAP.md) backlog |
| Upstream dataset changes or disappears | 🟢 Low | `data/processed/` is committed, so results stay reproducible |

## Verified facts worth not re-deriving

- Dataset coverage: **2020-08-13 → 2026-08-26**. There is **no 2018 data**.
- Corrupt block: **2020-09-25 → 2021-04-30** (~11% of rows), plus 2025-06-04.
- Idukki: FRL 732.43 m, rule 728.50 m, live storage at FRL 1,459.49 Mm³.
- Idamalayar: FRL 169.00 m, rule 164.00 m, live storage at FRL 1,017.80 Mm³.
- Oct 2021: level 728.81 m on the 16th → 168 mm rain on the 17th → inflow
  115.7 → 879.2 cumecs → gates open on the 20th at 730.95 m.
- Both dams opened spillways on **20 Oct 2021**: 83.85 + 128.13 cumecs.
- The optimiser independently converged on 728.43 m, against KSEB's published
  rule level of 728.50 m.
