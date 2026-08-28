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

### 🟢 1 · Forecast-error study — all three lead times in, 28 Aug 2026

The optimiser sees the **true** inflow series when choosing a policy. Every
benefit figure in the dossier is therefore an upper bound.

This was the biggest open question in the project. The research sweep found
the data that closes it, and it has now been run at the full 24 / 90 / 120 h
set (`scripts/forecast_error_study.py`):

| Lead time | Decision rule | Freeboard gained | % of perfect foresight |
|---|---|---|---|
| 24 h (issued 15 Oct 18z) | perfect foresight | 3.11 m | 100% |
| 24 h | expected-value | 0.81 m | **26%** |
| 24 h | minimax-regret | 1.03 m | **33%** |
| 90 h (issued 13 Oct 00z) | perfect foresight | 3.11 m | 100% |
| 90 h | expected-value | 1.03 m | **33%** |
| 90 h | minimax-regret | 2.30 m | **74%** |
| 120 h (issued 11 Oct 18z) | perfect foresight | 3.11 m | 100% |
| 120 h | expected-value | 1.03 m | **33%** |
| 120 h | minimax-regret | 1.07 m | **34%** |

**One finding survives all three points; a second one had to be retracted
when the third point arrived, and that retraction is itself worth keeping
on the record.**

1. **Minimax-regret never does worse than expected-value, and at 90 h it
   did dramatically better (74% vs 33%).** Hedging against your worst
   ensemble member instead of betting on the average one is a safe default
   - it never costs you the naive result and sometimes triples it.
2. **What did NOT survive: "the minimax advantage grows with lead time."**
   That claim was written after the 24 h and 90 h runs (7-point gap
   growing to 41 points) and looked like a mechanistically sensible trend
   - more lead time, more ensemble spread, more to gain from hedging. The
   120 h run breaks it: the gap collapses back to 1 point (33% vs 34%),
   barely different from 24 h's naive result. **Three points from one
   storm do not make a decay curve**, and forcing a monotonic story onto
   them would have been the same mistake the lead-time study's methodology
   note already warns about (see §3's "search luck" note) - a coincidence
   in a small, noisy sample dressed up as a trend. The likely confound: the
   bias correction is a single-event multiplicative factor and it swings a
   lot between runs (1.68x at 24 h, 3.18x at 90 h, 2.64x at 120 h) - that
   alone can move which member the optimiser treats as the worst case, and
   with it whether the minimax pick happens to be strong or unremarkable.
   A genuine skill-decay curve needs many storms averaged, not one storm
   sampled at three lead times - flagged as real future work rather than
   claimed as already answered.

Full method and other caveats (catchment geometry for the unit hydrograph
is estimated, not calibrated) in `docs/validation.md` §4 "Perfect
foresight".

**A bug was caught and fixed between the first and second pass at the 24 h
and 90 h leads**, worth stating rather than quietly overwriting: the first
version of the script only fetched GEFS rainfall out to the forecast
horizon but let the optimiser's evaluation window run to the scenario's
full default end (2021-10-28), zero-padding the ungoverned days. Real
observed inflow there is 130-240 cumecs, not near-zero, so the padding
fabricated a low-inflow tail that skewed every policy ranking that used
it. The fix truncates the evaluation window to exactly `[scenario start,
issue + horizon]` for every run, including 120 h, which was only ever run
post-fix.

The rest of this section is the original method spec, kept for
reproducibility.

**The source: NOAA GEFS operational archive on AWS** — `s3://noaa-gefs-pds`,
free, no credentials, no registration.

```
gefs.20211015/00/atmos/pgrb2sp25/gep01..gep30 .t00z.pgrb2s.0p25.f000..f240
```

30 perturbed members plus control, 0.25°, 4 cycles/day, out to 240 h, with an
archive reaching back to 2017 — so it covers the October 2021 case study. The
`.idx` sidecar names `APCP:surface:18-24 hour acc fcst:ENS=+1` at a byte
offset, and a Range GET of that slice returns HTTP 206 with GRIB magic bytes.
About 270 kB per member per lead hour, so a whole 30-member October 2021
hindcast is a few hundred MB of range reads, not terabytes.

GEFSv12 has been operational since September 2020, so October 2021 runs the
**same model generation as today** — skill measured on the hindcast transfers
to present-day operation. That is a genuinely strong argument for the case
study.

**The method:**

1. For each 00z issue date across the event, range-fetch APCP for `gep01`–`gep30`
2. Bias-correct against IMD gridded rainfall or the SLDC daily rainfall column
3. Push each member through the existing SCS-CN + Muskingum chain → 30 inflow
   trajectories
4. Run the existing exhaustive policy search per member; pick by a **declared**
   rule (expected value, CVaR, or minimax regret — the choice changes the
   answer, so state it)
5. Score the chosen policy against observed inflow from the Kerala SLDC form,
   which serves arbitrary historical dates via
   `POST sldckerala.com/index.php?id=7` with `date1_day/date1_month/date1_year`
   plus `sbtstore=SHOW` (numeric month; posting "October," or omitting
   `sbtstore`, silently returns today's data instead of an error)

   **Verified 28 Aug 2026** (`scripts/acquire.py`, `acquire_sldc_storage`):
   October 2021 returns all 31 days cleanly, 331 dam-day rows including
   IDUKKI and IDAMALAYAR — this works for the flagship case study. August
   2018 returns **zero** days — every date in that window comes back with
   no data table, confirming the manifest's own note that the archive
   starts 2019-08-08. The August 2018 CAG comparison (§ item 3 below) must
   therefore be scored against IMD gridded rainfall or the CWC discharge
   series, never SLDC.

**The deliverable is one honest number**: the fraction of the perfect-foresight
benefit that survives, reported separately at 24 / 72 / 120 h, because the
literature says those are very different regimes.

#### A trap that would have silently faked this

Open-Meteo's Historical Forecast API returns hourly precipitation for October
2021 and *looks* like a hindcast. It is not. The lead-time variable
`precipitation_previous_day3` is **100% null** for 2021-10-15 (0 of 24 hours)
while the identical request for 2024-07-15 returns 24 of 24. The lead-time
archive begins in early 2024; for 2021 that endpoint serves what is
effectively an analysis — near-perfect foresight. Building the
"forecast-driven" comparison on it would reproduce the perfect-foresight
result *while appearing to have fixed it*.

#### Free bonus: a second, independent route

Google's **GRRR** (Runoff Reanalysis & Reforecast) sits in an anonymously
readable GCS bucket, no key and no waitlist:
`gs://flood-forecasting/hydrologic_predictions/model_id_8583a5c2_v0/`.
Its reforecast is [1,031,646 gauges × 2,738 issue times × 8 lead days],
2016-01-01 to 2023-06-30 — so it spans October 2021. Virtual gauge
`hybas_4121152880` sits **0.61 km from Idukki dam**, and its reanalysis
reproduces the August 2018 flood (peak 239.65 m³/s on 16 Aug, against its own
2/5/10-year thresholds of 173.2 / 214.9 / 242.2).

Running both matters: GEFS gives error-bearing **rainfall** through AquaSync's
own model; GRRR gives error-bearing **discharge** from a global ML model. The
gap between them separates *"the rainfall forecast was wrong"* from *"my
rainfall-runoff model was wrong"* — two error sources the project currently
cannot tell apart.

Caveat to state: GRRR is a **reforecast**, a modern model re-run over past
dates, so it flatters the result relative to what an operator actually had.
GEFS operational is the stricter test.

**Second caveat, verified 28 Aug 2026:** the "8 lead days" run from **0 to 7**,
and lead 0 is not a forecast — Google's own documentation gives the identity
`Reanalysis[T] == Reforecast[T+1, lead=0]`. Lead 0 is the reanalysis value,
driven by observed CPC/IMERG rainfall for the day that has just ended. A
benefit-retention curve that starts at lead 0 will show a suspiciously strong
first point that is really perfect-foresight discharge in disguise — the
exact leak this whole exercise exists to remove. **Score from lead 1 upward.**
Separately, GRRR's reforecast is driven by "HRES and GraphCast weather
forecasts issued until time T" — GraphCast did not exist in 2021, so the
reforecast is a legitimately causal 2023-generation model re-run over 2021,
not a contemporary one. Treat it as an optimistic bound, with GEFS as the
stricter test, as already stated above.

#### The ceiling this work will run into

Two published numbers bound what any forecast-driven system can deliver here:

- **Durai et al. (2015), Mausam 66(3)**: day-3 ensemble-mean rainfall RMSE is
  10–15 mm/day over most of India but **25–30 mm/day along the west coast** —
  in all four of ECMWF, UKMO, NCEP and JMA. **Correction, 28 Aug 2026**: this
  is an absolute error, not a skill ranking — the same paper gives an
  observed seasonal mean of ~15 mm/day over the Konkan coast, so RMSE is
  largest exactly where rainfall is largest. Durai's own skill metric says
  the opposite: anomaly correlation is *highest* on the west coast of any
  region measured, in all four EPS. The honest claim is that absolute
  forecast error here is roughly double the all-India figure because the
  rainfall itself is roughly double — not that the Western Ghats are
  uniquely hard to forecast. (Nitha et al. 2025, Atmosphere 16(4) 372, is
  consistent with this once read in full — CSI 0.49–0.57, ECMWF FAR 0.41 at
  day 1–3 over Kerala — but it only measures day 1–3, JJAS only, so it
  cannot speak to the 3–7 day window this project needs, or to October.)
- **Sudheer et al. (2019)**: even pre-emptively emptying Periyar reservoirs to
  25–50% capacity bought only **16–21% peak attenuation** at Neeleeswaram,
  against an **observed** peak of 8,800 m³/s (9,965 m³/s in the same source
  is the HEC-HMS *modelled* peak — do not quote it as observed).

So the target framing is not "X% benefit" but: *"X% under perfect foresight,
Y% with the 30-member ensemble that was actually available, decaying from 24 h
to 120 h as follows."* That turns the project's biggest methodological
weakness into its most credible result.

### 🔴 2 · Cascade co-optimisation

Idukki and Idamalayar are currently optimised independently. The whole
evidence base (Figure 2) is that they failed *jointly* — same river, same
day. Scheduling them together so their release pulses deliberately do not
superpose is the single most valuable modelling addition.

The routing layer is already a DAG (`RiverNetwork`), so the work is extending
the policy search across nodes rather than rebuilding anything.

### 🟠 3 · Routing calibration against gauges — data now in the repo

K and x are no longer pure geometry: they are anchored to CWC's published
8-hour Idukki→Neeleeswaram travel time. But that is one number from a MIKE-11
model run "only for 2018", not a gauge-pair calibration.

The data to do it properly is now on disk:

- `research/sources/datasets/cwc_kerala_daily_discharge_2001_2025.csv` —
  **NEELEESWARAM, 8,478 daily readings 2001–2025**, plus VANDIPERIYAR and
  ARANGALI
- `…_1950_2000.csv` — Neeleeswaram back to 1971, giving 19,362 daily values
  across 54 years

`MuskingumReach.calibrate` already implements the fit.

**The catch, and it is a real one:** Neeleeswaram is missing 2018-08-16 to
08-22 *and* 08-24 to 08-27 — 13 of 31 August days. The last pre-gap reading is
6,166 m³/s on 15 August; the next is 924 on 23 August. **The 2018 flood peak
was never gauged at the point the twin routes to.** Calibrate on ordinary
monsoon events, then state plainly that the extreme is extrapolation.

CAMELS-IND v2.2 (`10.5281/zenodo.14999580`) carries the same Neeleeswaram
gauge as catchment 15021 with matched IMD forcings 1980–2020, and
NeuralHydrology already ships `datasetzoo/camelsind.py`. Use v2.2, not the
v2.1 DOI the paper cites — the v2.2 changelog specifically corrects the gauge
id mapping for basin code 15, which is this basin.

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
