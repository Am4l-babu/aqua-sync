# Validation

What has been tested, what the errors are, and what is still unverified.

A model that has not been validated against something it was not fitted to is
a hypothesis. This document tracks the distance between those two states, and
is honest about how far there is still to go.

**Status as of 31 August 2026:** the reservoir model is calibrated and
replay-validated **on two independent episodes**, not just the one it was
tuned against. The runoff chain is validated and **partially fit** — storm
timing yes, storm size no — after a defect that stopped it producing runoff
was found and fixed. Routing calibration was attempted and is **blocked by
data resolution**; the CWC 8 h anchor stands. The perfect-foresight caveat
is **closed at five lead times on two storms** (ten runs). Read §4 before
quoting anything.

---

## 1 · Level–storage calibration

**Question:** does the fitted power law reproduce the published
level → live-storage relationship?

**Method:** least-squares fit of β in
`S(h) = S_frl · ((h − h_dead)/(h_frl − h_dead))^β` against every validated
Idukki bulletin row.

| | Raw feed | Validated rows |
|---|---|---|
| n | 2,056 | **1,836** |
| β | 1.302 | **1.348** |
| r² | 0.784 | **0.9957** |
| MAE | 174 Mm³ | **17 Mm³** |
| max abs error | 1,743 Mm³ | — |

Mean observed storage is 904 Mm³, so an MAE of 17 Mm³ is about **1.9%**.

The gap between the two columns is the whole argument for the validation
layer. The corrupt 2020-09 → 2021-04 block displaces the curve by more than
the flood cushion being modelled — a model fitted on the raw feed would be
confidently wrong in exactly the region that matters.

**Cross-check:** the fitted curve implies a surface area of 52.5 km² at FRL.
Published figures for Idukki are around 60 km². Same order, ~13% low, which is
consistent with a smooth power law under-representing a reservoir with
irregular arms. Good enough for mass balance; not good enough to quote as a
surveyed area.

Reproduce: `python scripts/make_figures.py` → Figure 3.

---

## 2 · Replay: does the twin reproduce what happened?

**Question:** fed the releases that actually occurred, does the twin track the
observed reservoir level?

**Method:** October 2021, 481 hourly steps (8–28 October). Initial level from
the bulletin; inflow and releases from the bulletin; no fitting to the level
series itself.

| Metric | Result |
|---|---|
| Mean absolute error | **0.303 m** |
| Maximum absolute error | **0.571 m** |
| Final-step error | +0.517 m |
| Observed peak level | 730.99 m |
| Simulated peak level | 731.54 m |

The error is **biased positive and grows through the window** — the twin ends
about half a metre high. That pattern points to an unmodelled loss rather than
random noise. The likely candidates, in order:

1. **Evaporation is a flat 4 mm/day.** Over 20 days on a ~50 km² surface
   that is roughly 4 Mm³ — real, but too small to explain 0.5 m.
2. **Interpolating daily bulletin values to hourly** smooths the inflow peak
   and mis-times it, and errors there accumulate in storage.
3. **Unreported minor outlets.** Riparian releases and leakage do not appear
   in the bulletin columns.

This is the most useful open diagnostic in the project: a 0.5 m drift over 20
days is small enough to work with and large enough to be worth explaining.

**Consequence for the headline claim:** roughly 0.5 m of the ~3 m freeboard
figure sits inside model error. Quote it as *"about 3 m"*, never to two
decimal places.

### 2b · Out-of-sample: does it hold up on an episode it has never seen?

**Question:** the calibration above (β, evaporation, spillway physics) was
fitted or checked against October 2021 data. Does the same untouched model
reproduce a *different* episode - August 2022 - to a comparable accuracy?
This is the difference between *calibrated* and *validated*.

**Method:** identical to §2, replayed against `idukki_aug_2022`
(`twin/scenarios.py`), 1–20 August 2022, 457 hourly steps. Observed inflow
and releases in, no fitting to the level series. Genuine spillway release in
this window (191 h active, peak 409 cumecs), so it also exercises the
spillway-discharge physics that October 2021 barely touched (105 cumecs
peak).

| Metric | October 2021 (fitted-to) | August 2022 (out-of-sample) |
|---|---|---|
| Mean absolute error | 0.303 m | **0.319 m** |
| Maximum absolute error | 0.571 m | **0.744 m** |
| Final-step error | +0.517 m (grows positive) | **-0.273 m (does not)** |
| Spillway active | 216 h, 105 cumecs peak | 191 h, 409 cumecs peak |

**Finding:** mean error on the unseen episode (0.319 m) is within 5% of the
episode the model was checked against (0.303 m) - the accuracy is not an
artefact of October 2021 specifically. That is the headline result, and it
is genuinely evidence of generalisation, not overfitting.

The maximum error is worse (0.744 vs 0.571 m, at hour 120 - early in the
window, not during the spillway event), which the higher spillway discharge
is a plausible but unconfirmed cause of. More useful: **the sign of the
drift flips.** October 2021 drifts high and keeps climbing (final error
+0.517 m); August 2022 drifts low and ends there (-0.273 m). A single
unmodelled loss term (evaporation, an unreported outlet) would produce the
*same-sign* drift on both episodes. It does not, which weakens the "missing
loss term" explanation offered in §2 and points instead toward
event-specific error - most plausibly the daily-to-hourly interpolation
mistiming each storm's actual sub-daily inflow pulse differently, since that
error's sign depends on the shape of the individual event, not on a
constant physical process.

Reproduce: `python scripts/out_of_sample_replay.py --scenario idukki_aug_2022`.

---

## 3 · Counterfactual and lead time

**Question:** what release policy should have been used, and what does
forecast lead time change?

**Method:** exhaustive grid search over `DrawdownPolicy(target_level,
start_hour, max_rate)`, replayed at eight lead times, with and without a grid
offtake cap. Deterministic — no seed, no search variance.

| Lead (days) | Freeboard gained | Spill share | Revenue Δ |
|---|---|---|---|
| 0 | +2.72 m | 61% | +₹5.1 Cr |
| 3 | +3.04 m | 56% | +₹8.7 Cr |
| 5 | +3.28 m | 55% | +₹9.3 Cr |
| 7 | +3.28 m | 53% | +₹9.6 Cr |
| 10 | +3.26 m | 49% | +₹7.9 Cr |
| 14 | +3.12 m | 45% | +₹8.2 Cr |
| 21 | +3.30 m | 43% | +₹5.8 Cr |
| 30 | +3.25 m | 40% | +₹4.4 Cr |

*(energy-neutral offtake — mean turbine discharge capped at the observed mean)*

**Findings:**

1. Flood cushion gained is roughly constant at **about 3 m** regardless of
   lead time.
2. Revenue is **positive at every lead time**, by ₹4–10 crore, achieved by
   shifting the same generation volume into higher-tariff hours.
3. What lead time actually changes is **waste**: spill share falls
   monotonically from 61% to 40%.
4. The optimiser converged on a target level of **728.43 m** at nearly every
   lead time, against KSEB's published rule level of **728.50 m**.

Finding 4 is the one to lead with. Given only the physics and the objective,
the search independently rediscovered the operating rule that already exists.

### A methodological note worth keeping

The first implementation searched over N independent hourly release values and
produced results that were **non-monotonic in lead time** — 10 days beat 14,
which beat 21. That was not a finding. A 30-day window has 720 free variables,
so a fixed candidate budget covers a longer horizon ever more sparsely; the
numbers measured search luck.

Reformulating as a three-parameter policy made the space enumerable and the
results monotonic. **A stochastic optimiser reported without a convergence
check will produce a trend, and it will be a trend in your search budget.**

Reproduce: `python scripts/lead_time_study.py`.

---

## 4 · Not yet validated

Ordered by how much they undercut current claims.

### 🟢 Perfect foresight - closed at five lead times on two storms, 30 Aug 2026

The optimiser in §3 sees the **true** inflow series when choosing a policy.
Every benefit figure above is a ceiling until this is closed.

**Method:** `python scripts/forecast_error_study.py`. Fetch the 30-member NOAA
GEFS rainfall ensemble issued *before* the storm, bias-correct each member
against IMD gridded rainfall, push it through the same SCS-CN and Muskingum
chain, run the existing exhaustive policy search per member, commit to one
policy under that uncertainty, and score it against what actually happened.

**Scored on the objective the optimiser actually minimises** - flood, dam
safety, revenue and gate wear together, not freeboard alone. Zero excess cost
means the forecast picked the policy hindsight would have picked; the figure
can never go below it. Perfect foresight scores a total cost of
1.96, gaining 3.11 m of cushion
while earning Rs +1.94 crore against observed
operation.

| Lead time | Ensemble issued | Bias | Expected value | Minimax regret |
|---|---|---|---|---|
| 24 h | 2021-10-15 18z | 1.68x | **+0%** | +19% |
| 48 h | 2021-10-14 18z | 2.73x | **+0%** | +19% |
| 72 h | 2021-10-13 18z | 2.22x | **+37%** | +53% |
| 90 h | 2021-10-13 00z | 3.18x | **+69%** | +85% |
| 120 h | 2021-10-11 18z | 2.63x | **+69%** | +69% |

**Why not report the freeboard retention this section used to.** Because it
cannot distinguish a good decision from an over-release. Every one of these
policies ends *lower* than the hindsight optimum - they gain more cushion than
perfect foresight does - which reads as beating hindsight on a cushion-only
metric and is nothing of the sort. They buy that cushion by releasing more
than was needed, and pay for it in revenue: Rs +1.34 to +1.40 crore against
perfect foresight's +1.94. The JSON still carries
`retention_of_perfect_foresight_pct` with a `metric_note` saying exactly this;
`excess_cost_vs_perfect_foresight_pct` is the field to read.

Three findings, and one of them retracts a previous one.

1. **The forecast is as good as hindsight out to 48 hours, and then it is
   not.** At 24 h and 48 h the expected-value rule reproduces the
   hindsight-optimal policy exactly (+0%). It degrades through 72 h (+37%) to
   a plateau of about +69% at 90 and 120 h. The operational reading is that
   this system's value is concentrated in the last two days before a storm -
   which is also when a control room has least time to deliberate, and
   therefore when a pre-computed policy is worth most.

2. **Retracted: "minimax-regret never underperforms expected-value."** The
   previous version of this section said hedging against the worst ensemble
   member never costs you and sometimes triples the benefit. Across five lead
   times minimax regret is **never better and usually worse** - +19%, +19%,
   +53%, +85%, +69% against expected value's +0%, +0%, +37%, +69%, +69%.
   Hedging buys cushion by over-releasing and gives up revenue for it.

   Those earlier numbers came from a rainfall-runoff chain carrying the defect
   recorded below under "Rainfall-runoff": it applied the curve number's
   initial abstraction per timestep, so it produced almost no runoff, every
   ensemble member looked benign, and every policy under-released. The whole
   study was re-run once that was fixed. **This is the second finding this
   project has had to withdraw on its own evidence, and both retractions are
   on the record rather than quietly corrected.**

3. **It is lead time doing this, not the bias correction.** The obvious
   confound is the bias factor, a single-event multiplicative correction
   ranging 1.68x to
   3.18x, so it was tested rather than
   assumed: excess cost correlates with lead time at **r = 0.93** and with the
   bias factor at only **0.61**. The 48 h run settles it - one of the largest
   corrections in the set, and it still reproduces the hindsight-optimal
   policy exactly. An earlier three-point version of this section asserted the
   opposite, on a sample too small to separate them.

#### The second storm - August 2022, ten runs in total

The five October points were a single storm, and the 48 to 90 h transition
rested on one 72 h run. The same five lead times were therefore run against
`idukki_aug_2022` (§2b) - the same ensemble source, the same bias correction
against IMD, the same chain, the same scoring. Perfect foresight on this
episode costs 0.75, "gains" **-1.46 m** of cushion (the optimal policy ends
*higher* than the operators did) and earns Rs +1.42 crore.

| Lead time | Ensemble issued | Bias | Expected value | Minimax regret |
|---|---|---|---|---|
| 24 h | 2022-08-07 18z | 1.80x | **+0%** | +0% |
| 48 h | 2022-08-06 18z | 1.76x | **+5%** | +5% |
| 72 h | 2022-08-05 18z | 1.50x | **+5%** | +57% |
| 90 h | 2022-08-05 00z | 2.05x | **+5%** | +39% |
| 120 h | 2022-08-03 18z | 0.90x | **+158%** | +177% |

Four things follow, and the first is a correction.

1. **A premature reading is on record.** With three of the five runs in, an
   earlier draft said the degradation "does not reproduce." The 120 h run
   reversed that - it is the point that carries the shape. This is the
   fourth claim on this project stated early and broken by the next data
   point (the others: the 24 to 90 h "cliff" that was a ramp, and findings
   2 and 3 above). **Treat any conclusion drawn from a partial run set as
   provisional until the set is complete.**

2. **The structure reproduces; the shape does not.** Both storms have a flat
   region where a real ensemble is as good as hindsight, then degradation.
   October ramps from 48 h (+37% at 72 h) to a +69% plateau. August holds
   within +5% out to 90 h and then jumps to +158% in a single 30-hour step.
   So the honest general statement is: *a real ensemble matches hindsight up
   to some horizon, beyond which committing to its policy costs
   substantially more than doing nothing clever.* The horizon is not a
   constant across storms and the penalty beyond it is not bounded by
   October's +69%. **Do not describe the degradation as gradual, and do not
   average the two storms into one curve.**

3. **The two episodes are not equally hard, and August is the easier one.**
   October 2021 came within about a metre of FRL; August 2022 peaked nearly
   5 m below it. The perfect-foresight cost reflects it - 1.96 against
   0.75 - and August's optimal policy ends higher than the operators did.
   Part of why August stays flat for longer is plausibly that less was at
   stake, not that the forecast was better. Qualify by reservoir state when
   quoting.

4. **Both retractions get stronger.** Across all ten runs, minimax regret is
   better than expected value in exactly one - August 48 h, by 0.16
   percentage points (+5.30% against +5.46%), a tie in everything but sign -
   ties in two, and is worse in seven, sometimes heavily (August 72 h: +57%
   hedged against +5%). And the 120 h August run has the **smallest bias
   factor of all ten** (0.90x, the only one below 1) and the **worst
   outcome** (+158%): it drew the reservoir down 1.21 m when the optimal
   policy would have let it rise. Bias magnitude does not predict decision
   quality.

**What is still open.** Two storms, ten runs, and the break point differs
between them by about two days. A third storm - ideally a harder one, with
the reservoir near FRL as in October - is what would say whether the horizon
tracks reservoir state, lead time, or something else. Note also that the
whole study inherits whatever error the rainfall-runoff chain carries, and
that chain scores NSE 0.07 on daily amplitude - see below.

**The August results are now in the dossier as well**, as of 8 September
2026: §4.4 carries a second-storm subsection with this table and these four
findings, and Figure 6 grew a second row. The two storms are drawn on
separate axes with separate y-limits, deliberately — they are not equally
hard, and the penalties beyond the flat region differ by more than a factor
of two, so a shared scale would imply a point-by-point comparison the data
does not support.

Fixing that turned up **two more unfiltered globs of the same kind** as the
one `make_figures.py` carried. `build_abstract.py` counted study *files* as
lead times and reported "across 10 lead times" when there are five, run
twice; `build_icfoss_analysis.py` merged both storms' excess-cost values into
a single min-max range. Both now filter by scenario and quote the two storms
separately. The pattern is worth naming: **any `glob("forecast_error_study_*")`
without a scenario filter is a defect**, and it stayed invisible for as long
as only one storm was on disk.

Reproduce, one run per lead time:

```bash
# October 2021
python scripts/forecast_error_study.py --issue-date 2021-10-15 --hh 18 --horizon-h 102  # 24 h
python scripts/forecast_error_study.py --issue-date 2021-10-14 --hh 18 --horizon-h 126  # 48 h
python scripts/forecast_error_study.py --issue-date 2021-10-13 --hh 18 --horizon-h 150  # 72 h
python scripts/forecast_error_study.py --issue-date 2021-10-13 --hh 00 --horizon-h 168  # 90 h
python scripts/forecast_error_study.py --issue-date 2021-10-11 --hh 18 --horizon-h 198  # 120 h
# August 2022
python scripts/forecast_error_study.py --scenario idukki_aug_2022 --issue-date 2022-08-07 --hh 18 --horizon-h 102  # 24 h
python scripts/forecast_error_study.py --scenario idukki_aug_2022 --issue-date 2022-08-06 --hh 18 --horizon-h 126  # 48 h
python scripts/forecast_error_study.py --scenario idukki_aug_2022 --issue-date 2022-08-05 --hh 18 --horizon-h 150  # 72 h
python scripts/forecast_error_study.py --scenario idukki_aug_2022 --issue-date 2022-08-05 --hh 00 --horizon-h 168  # 90 h
python scripts/forecast_error_study.py --scenario idukki_aug_2022 --issue-date 2022-08-03 --hh 18 --horizon-h 198  # 120 h
```

Each run fetches about 450 MB of GEFS GRIB2 slices into
`research/raw/gefs_hindcast/` (gitignored, cached, skipped if already
present) and took ten to twenty minutes each on first fetch. Results:
`data/processed/forecast_error_study_*.json`, ten files, with the full
policy-by-member cross matrix beside each as CSV.

### 🔴 Cascade - the two dams are not jointly scheduled, and optimising them separately is worse than not coordinating at all, 28 Aug 2026

Everywhere in §3 each reservoir is optimised on its own. The evidence the
whole project rests on (Figure 2) is that the two failed *jointly* - same
river, same day - so scheduling them together looked like the single most
valuable modelling addition left. It was run, and the result contradicts the
premise of the item.

**Method:** `python scripts/cascade_coordination.py`. `RiverNetwork` - the DAG
router already implemented and exported, but never used outside its own module
before this - routes Idukki's release through periyar_upper then periyar_lower,
and Idamalayar's directly into periyar_lower at the confluence, over the same
481-hour October 2021 window, both dams.

| Scenario | Joint peak at periyar_lower |
|---|---|
| Observed (what actually happened) | 403 cumecs |
| Each dam optimised alone, existing single-dam tooling unchanged | **911 cumecs - 126% worse than observed** |
| Coordinated: timing search over both dams' `start_hour` | 828 cumecs - 9% better than naive, still 105% worse than observed |

**1 - Independent optimisation is not a simplification that degrades
gracefully.** Idukki's own optimum releases at the ceiling of its rate grid
(828 cumecs) because, scored against periyar_lower's 1,100-cumec bankfull
threshold *alone*, that is comfortably safe. It stops being safe once
Idamalayar's simultaneous 314 cumecs arrives at the same confluence - a
combination neither dam's objective function can see, because each scores
itself as though the shared reach belonged to it.

**2 - Retiming does not fix it.** The coordination search swept both start
hours, the most direct reading of "make the pulses not superpose", and
recovered 9% of the gap it opened. The fix implied by this section's own name
is not the fix. It is an objective-function problem: each dam's policy has to
be scored against the actual *combined* downstream discharge. That is a
redesign, not a bigger search, and it is the largest open modelling item in
the project.

**Caveat that governs how the cumec figures may be read.** These are the two
dams' contribution only. `RiverNetwork.route_all` accepts a `lateral_inflows`
parameter for the ungauged catchment between the dams and Aluva and it was not
populated - no tributary or local-runoff series exists in this project's data
holdings. **Do not compare these numbers to bankfull or danger thresholds as
if they were total river discharge**, which is also why even the 911-cumec
naive figure sits below bankfull despite representing what the evidence says
was a real near-miss at Aluva. The relative comparison between the three
scenarios is valid; the absolute values are not a flood-risk verdict.

**What would validate it:** a joint objective, then the same three-way
comparison. Until then the honest statement is that AquaSync optimises one
reservoir at a time and that this is a real limitation, not a deferred
feature.

Reproduce: `python scripts/cascade_coordination.py`. Result:
`data/processed/cascade_coordination.json`.

### 🔴 River routing - calibration attempted and blocked, 28 Aug 2026

Muskingum K and x for periyar_upper + periyar_lower are anchored to CWC's
published 8-hour Idukki-to-Neeleeswaram travel time (December 2018
report) - not pure geometry, but also not a gauge-pair fit: CWC derived it
from a MIKE-11 model run "only for 2018."

**`python scripts/routing_calibration.py` was run against real data for
the first time** - combined Idukki + Idamalayar daily release (KSEB
bulletin, 2020-08-13 onward) as inflow, CWC's Neeleeswaram daily discharge
record (2001-2025) as outflow, `MuskingumReach.calibrate()` (implemented,
previously only unit-tested against synthetic data) doing the fit over the
1,967-day overlap.

**Result: the fit failed, and it failed for a diagnosable, useful reason.**
K = 263 h, x = 0.50 (the edge of the allowed range, not an interior
optimum), r² = 0.005 - essentially no signal. **The CWC anchor is
unchanged; this negative result does not replace it, and nothing in
`constants.py` was touched.**

Why it failed: the fit needs a timestep resolving the quantity it is
trying to measure, and daily data (dt = 24 h) is roughly 3x coarser than
the 8-hour travel time itself. By the time a day's combined release shows
up in that day's Neeleeswaram reading, the flood wave has already fully
transited the reach - there is no timing signal left in daily-vs-daily
data for a Muskingum fit to find. This is not a bug or a tuning choice
(the interpolation of the 217 missing Neeleeswaram days, the averaging of
140 duplicate-date readings, and the `x` search grid were all checked and
are not the cause) - it is a genuine resolution mismatch between the data
available and the parameter being estimated.

**This also rules out the tempting workaround.** GUARDIAN rating curves
(`research/sources/datasets/guardian_rating_curves.xlsx`) could convert
the CWC hourly water-level record at Neeleeswaram into hourly discharge,
raising the *outflow* side to a resolution well below 8 hours. It would
not help: KSEB's own bulletin is daily, so the *inflow* side would still
be linear interpolation of a daily reading, carrying no genuine sub-day
variation to correlate against. The bottleneck is the release record, not
the gauge record, and `docs/data-sources.md` already names the fix: **the
CWC 15-minute telemetry feed, "the single highest-value upgrade to the
data layer."** This calibration attempt is independent confirmation of
that claim, with a number attached (r² = 0.005) rather than just an
assertion.

Consequence, unchanged from before this attempt: **downstream discharge
figures are indicative, not measured.** Do not quote a predicted discharge
at Aluva as though it were validated.

Reproduce: `python scripts/routing_calibration.py`. Result:
`data/processed/routing_calibration_neeleeswaram.json`.

### 🟠 Rainfall–runoff - validated at last, and it found a defect, 30 Aug 2026

This section carried the note "implemented and unit-tested for volume
conservation, but never compared against observed inflow" from the day the
model was written. That was the last unvalidated link in the chain, and it
gates any genuinely forward-looking forecast - including the forecast-error
study above, which drives exactly this code.

**Run:** `python scripts/runoff_validation.py`. The KSEB bulletin publishes
daily rainfall *and* daily inflow for the same reservoir, so the comparison
needed no new data at all: four complete monsoon seasons (2021-2024, 722
scored days, mean observed inflow 103 cumecs) of observed rainfall pushed
through the chain and scored against observed inflow. 2020 is excluded as
more than half of it sits inside the known corrupt block; 2025 and 2026 miss
the 95% coverage bar.

#### The first run found a defect, not a calibration error

Scored as the model shipped, it returned **NSE -1.14 with a -100% volume
bias**: across four monsoons it produced essentially *no runoff at all*. A
bias of -100% is not a model that needs tuning, it is a model that is not
running.

The cause is that the curve-number equation is an **event-total** relation.
Its initial abstraction Ia is the depth a catchment absorbs once, at the start
of a storm, before any runoff occurs. `RainfallRunoffModel.inflow_series`
applied it to **each timestep independently**, so every increment was charged
the whole of Ia - and for Idukki's CN 72 that is 19.8 mm, more than an hour of
even extreme rain. The effective rainfall from a given storm therefore
depended on the timestep it happened to be handed at:

| 168 mm on 17 Oct 2021, driven as | Effective rainfall |
|---|---|
| one 24 h step | 88.97 mm |
| 8 x 3 h steps | 0.12 mm |
| 24 x 1 h steps | **0.00 mm** |

The fix accumulates rainfall within a storm, applies the curve-number relation
to the cumulative depth, and takes the per-step increment - which is how the
method is defined. Storms are separated by a rainless gap (6 h by default),
each paying its own initial abstraction, and the antecedent-moisture shift is
evaluated once at storm onset rather than drifting mid-storm. Effective
rainfall is now identical at 30 min, 1 h, 3 h and 24 h resolution, and
`backend/tests/test_twin.py::TestStormExcess` pins that invariance so the
defect cannot come back.

**This is why the forecast-error study's results were re-run** - it drives
this chain at an hourly step, which was the worst case for the defect.

#### What the fixed chain is actually worth

| Configuration | NSE | r² | Volume bias |
|---|---|---|---|
| Handbook CN 72, no baseflow (as shipped) | **0.07** | 0.55 | **-1%** |
| Handbook CN 72 + per-season baseflow | -0.06 | 0.58 | +34% |
| Curve number calibrated on all four seasons | 0.25 | 0.60 | -17% |

Read carefully, because the headline number flatters it:

1. **The pooled -1% volume bias is partly seasons cancelling out.** Per
   season the error is -7%, -3%, **+38%** and -17%. The chain gets the
   climatological volume right and any individual monsoon's volume only
   roughly.
2. **Timing is broadly right, size is not.** r² = 0.55 says the model rises
   and falls with the observed hydrograph; NSE = 0.07 says the amplitude is
   wrong. Figure 8 shows both at once - predicted peaks overshoot badly (900
   against 550 cumecs in 2024) and predicted inflow returns to *zero* between
   storms, because an event-based curve number has no recession limb and no
   soil-moisture store to drain.
3. **Adding a baseflow term makes it worse, not better** (+34% volume). The
   direct-runoff term is already carrying the whole water balance, so a
   baseflow constant double-counts. That is itself evidence the chain is
   compensating: it is over-producing storm runoff and under-producing
   everything between storms, and the two errors cancel in the total.
4. **Calibration does not generalise, so it was not adopted.** The best-fit
   curve number pins at **50, the bottom edge of the search grid** - the same
   grid-edge signature the routing calibration produced, and the same
   diagnosis: a structural mismatch being absorbed by a parameter. It buys
   in-sample NSE (0.07 to 0.25) and pays for it in volume bias (-1% to -17%),
   and leave-one-season-out it collapses: **mean NSE -0.02, worst -0.91**. A
   curve number fitted on three seasons does not predict the fourth. The
   handbook 72 stays.

#### What this settles, and what it does not

The chain is fit for what the twin actually asks of it - "roughly how much
water will a storm of this size deliver, and roughly when" - and is not fit
for day-ahead inflow prediction to a useful tolerance. Any claim of the second
kind would need a continuous soil-moisture model with a recession limb, not a
better curve number.

Two caveats govern all of the above and neither can be resolved from this
dataset. Bulletin rainfall is a **station reading at the dam**, not a
catchment areal mean, and in steep orographic terrain those differ
substantially. Bulletin inflow is itself **derived by KSEB from a reservoir
mass balance**, not gauged. This is a comparison of two estimates, not of a
model against truth, and a fair share of the residual may belong to either.

Reproduce: `python scripts/runoff_validation.py`. Results:
`data/processed/runoff_validation_idukki.json` and `..._series.csv`.


### 🟡 Tide

Harmonic constituents for Kochi are literature values, never compared against
INCOIS predictions. The spring range the model produces (1.00 m) and the
dominant period (12.63 h) are both consistent with published descriptions of
Cochin as microtidal mixed semi-diurnal — a sanity check, not a validation.

### 🔴 Storm stress test — not validated, by construction

The simulation view can multiply the recorded inflow by 1.25, 1.5 or 2 before
either schedule sees it (`inflow_scale` on `/api/scenarios/{key}/counterfactual`,
added 11 September 2026). It is a scaled copy of one hydrograph: the same shape,
more water. It is **not** a forecast, **not** a return period, and there is no
observed storm to score it against — which is why the API drops the replay-error
figures and the recorded level from a scaled run rather than leave a 0.30 m MAE
on screen beside a storm that never happened. Read it as a comparison between
two schedules under the same larger storm, and nothing more.

`scripts/stress_sweep.py` walks the multiples 1, 1.25, 1.5, 1.75, 2, 2.5, 3 and
writes `data/processed/stress_sweep_periyar_oct_2021.json`. On the October
2021 episode the day's schedule first reaches FRL at **×1.25** and the
optimiser's schedule does not by ×3 — because it may release up to 1,500
cumecs, and the routed downstream peak in the same file is where that water
goes (one dam's contribution, uncalibrated reach, never against bankfull).
Levels above the crest are the mass balance continuing past it; the twin has
no overtopping physics. Coarse ladder, so "first multiple" is an upper bound.

### 🟡 Catchment policy (curve-number what-if) — volume only

`/api/scenarios/{key}/runoff?cn=` runs the episode's recorded rain through the
SCS-CN chain at a chosen curve number and reports runoff **volume** against
handbook CN 72. That is inside what §4's runoff validation supports: pooled
volume bias −1%, −7 to +38% by season. The hydrograph peak the same call
returns is labelled `shape_unvalidated` and greyed on the card, because the
chain's NSE on shape is 0.07 and has no recession limb. The curve number is
a handbook land-use lookup, not a measurement of this catchment.

### 🟡 Malayalam advisory — wording not reviewed

`advice_ml` on every telemetry frame and what-if answer is template text on
the same KSDMA bands as the English advice, pinned to them by test. It has
**not** been read by a native speaker and must be before any public use.

---

## 5 · Unit and physics tests

`python -m pytest backend/tests/ -q` — **75 passing** as of 31 August 2026.
The count moves; `python -m pytest backend/tests --collect-only -q` prints
the current one.

These are mostly physics tests rather than unit tests. A hydrological model
that passes its unit tests but does not conserve water is worse than no model,
because it is wrong in a way that looks right.

| Group | Asserts |
|---|---|
| Level–storage | Round-trip, monotonicity, anchoring at FRL and dead level, area = dS/dh, β recovery from synthetic data |
| Mass balance | Volume conservation to 1e-9, hourly vs 6-minute agreement < 1 mm, storage never negative, spill zero below crest |
| Runoff | Runoff ≤ rainfall always, unit hydrograph conserves volume to 2%, steeper catchments peak sooner |
| Storm excess | Effective rainfall identical whether a storm is driven in 1, 8, 24 or 48 sub-steps (the defect in §4 cannot come back); a dry gap splits storms and each pays its own abstraction; the AMC feedback is covered separately |
| Routing | C0+C1+C2 = 1, auto sub-reaching restores stability, volume conserved to 2%, attenuation and lag both present, never negative, calibration recovers known K |
| Tide | Dominant period in the semi-diurnal band, ~2 highs/day, spring range plausible for Cochin, discharge shortens intrusion |
| Hydropower | Rated flow at FRL within 15% of nameplate for both plants, no output below cut-in, efficiency never exceeds peak, peak tariff worth more, spill above turbine rating not charged as lost revenue |
| Optimiser | Bounds and ramp limits respected, drawdown converges on target, **policy search is bit-for-bit deterministic**, optimised beats baseline, offtake cap reduces revenue |

---

## 6 · Reproducing all of it

```bash
python scripts/fetch_data.py --all         # cache + quality report
python scripts/check.py                    # the gate: lint, 75 tests, glyphs, regeneration, determinism
python scripts/lead_time_study.py          # §3
python scripts/out_of_sample_replay.py --scenario idukki_aug_2022   # §2b
python scripts/forecast_error_study.py     # §4, one lead time per run, ten runs in all
python scripts/cascade_coordination.py     # §4
python scripts/routing_calibration.py      # §4
python scripts/runoff_validation.py        # §4
python scripts/make_figures.py             # all figures + figure_facts.json
python scripts/build_dossier.py            # the PDF
```

The five build scripts are deterministic: rebuilding without a content
change produces a byte-identical file, so git only shows a diff when a
number actually moved.

Every number in this document and in the dossier is regenerated by those
commands. None is hand-entered. If the upstream feed changes, the numbers
change — which is the point.
