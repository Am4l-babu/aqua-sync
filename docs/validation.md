# Validation

What has been tested, what the errors are, and what is still unverified.

A model that has not been validated against something it was not fitted to is
a hypothesis. This document tracks the distance between those two states, and
is honest about how far there is still to go.

**Status as of 28 August 2026:** the reservoir model is calibrated and
replay-validated **on two independent episodes**, not just the one it was
tuned against. The routing and runoff models are **not yet validated**, and
the headline counterfactual assumes **perfect foresight**. Read §4 before
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

### 🟢 Perfect foresight - all three lead times in, 28 Aug 2026

The optimiser in §3 sees the **true** inflow series when choosing a policy.
Every benefit figure above is an upper bound until this is closed.

**Method:** `python scripts/forecast_error_study.py`. Fetch the 30-member
NOAA GEFS ensemble issued before the 17 October 2021 storm, bias-correct
against IMD RF25 gridded rainfall (a single multiplicative factor - see
caveat below), push each member through the SCS-CN + unit-hydrograph chain
to get 30 candidate inflow trajectories, search a `DrawdownPolicy` per
member, score the full 30x30 candidate-vs-member cross-matrix over the
*same* window as the perfect-foresight baseline, and commit to ONE policy
under a declared rule. Verify that policy against what actually happened.

**Results, the full 24 / 90 / 120 h set ROADMAP.md asked for:**

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

**One finding survives all three points. A second one was written after two
points, looked mechanistically sensible, and had to be retracted when the
third arrived - keeping that retraction visible is more useful than
deleting it.**

1. **Survives: minimax-regret never underperforms expected-value, and at
   90 h it did dramatically better (74% vs 33%).** Committing to whichever
   ensemble member looks best on average picks a policy tuned to a
   light-rain story that under-releases when the real storm hits;
   committing to the policy that survives its own worst member is a safe
   default across all three lead times - it costs nothing when the gap is
   small (120 h: 33 vs 34%) and pays off hugely when it is large (90 h).
2. **Retracted: "the minimax advantage grows with lead time."** After 24 h
   (7-point gap) and 90 h (41-point gap) this looked like a real trend -
   more lead time, more ensemble spread, more to gain from hedging. The
   120 h run breaks it outright: the gap collapses back to 1 point (33 vs
   34%), statistically indistinguishable from 24 h's. **Three points from
   one storm do not make a decay curve.** The most likely confound is the
   bias-correction factor itself, which swings between runs for reasons
   that have nothing to do with lead time (1.68x at 24 h, 3.18x at 90 h,
   2.64x at 120 h, from a single-event multiplicative correction) - that
   swing alone can change which ensemble member the optimiser treats as
   the worst case, and with it whether the minimax pick happens to be
   strong or unremarkable. A genuine skill-decay curve needs many storms
   averaged together, not one storm sampled at three lead times; that is
   real future work, not something these three runs already answer. This
   is the same discipline the methodological note in §3 already insists
   on: a trend measured with too small a sample is not a finding, it is
   sample noise wearing a trend's clothes.

**A bug was caught and fixed between the first and second pass at the 24 h
and 90 h leads, and it is worth narrating rather than quietly overwriting
the earlier numbers.** The first version of the script fetched GEFS
rainfall only out to the forecast horizon, but let the optimiser's
evaluation window run to the scenario's full default end (2021-10-28)
regardless - so every hour past the fetched horizon was silently
zero-padded. Real observed inflow in that gap is 130-240 cumecs, not
near-zero (checked directly against the KSEB bulletin), so the padding
fabricated over a week of fictitious near-drought and distorted every
policy ranking that used it. The fix truncates the evaluation window to
exactly `[scenario start, issue time + horizon]` for every run, so no hour
in any comparison is fabricated; 120 h was only ever run post-fix. The
qualitative finding that survives (minimax never underperforms
expected-value) held before and after the fix; the specific claim that did
not survive (growing advantage) was retracted for an unrelated reason - a
third data point, not the bug.

**Other honest caveats, most serious first:**

1. **The bias correction is large and single-event, and its run-to-run
   variability (1.68x / 3.18x / 2.64x) is itself the leading suspect for
   why the minimax gap does not follow a clean trend** (see finding 2
   above). Every factor rescales one storm, not a trained correction, and
   none should be assumed to generalise. A proper fix needs the correction
   fit across many storms, which is future work.
2. **Catchment geometry for the unit hydrograph is estimated, not
   calibrated** (35 km channel, 3.6% slope - order-of-magnitude for a
   compact Western Ghats headwater catchment, not fitted to Idukki). This
   is the same gap as the routing calibration item below, one level
   upstream.
3. **GEFS's native 3-hourly resolution cannot resolve Idukki's own
   concentration time** (Kirpich estimate ~2.7 h from the same unmeasured
   geometry) - a flashy sub-3h rise is smoothed into the 3-hourly bucket it
   falls in. This affects peak *timing* more than peak *volume*, since SCS-CN
   mass balance is conserved regardless of the disaggregation.
4. **One storm.** All three lead times replay the same October 2021 event.
   Everything in findings 1 and 2 above is a property of this one storm's
   ensemble, not yet shown to generalise to another.

Reproduce: `python scripts/forecast_error_study.py --issue-date 2021-10-15
--hh 18 --horizon-h 102` (24 h), `--issue-date 2021-10-13 --hh 00
--horizon-h 168` (90 h), or `--issue-date 2021-10-11 --hh 18 --horizon-h
198` (120 h). Results: `data/processed/forecast_error_study_2021-10-1{5_18,3_00,1_18}z.json`.

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

### 🟠 Rainfall–runoff

The SCS-CN chain is implemented and unit-tested for volume conservation, but
has never been compared against observed inflow. Curve numbers (72 for Idukki,
74 for Idamalayar) are handbook values for Western Ghats terrain on hydrologic
soil group C, not calibrated.

This does not affect the replay results — those use *observed* inflow directly
— but it does gate any genuinely forward-looking forecast.

### 🟡 Tide

Harmonic constituents for Kochi are literature values, never compared against
INCOIS predictions. The spring range the model produces (1.00 m) and the
dominant period (12.63 h) are both consistent with published descriptions of
Cochin as microtidal mixed semi-diurnal — a sanity check, not a validation.

---

## 5 · Unit and physics tests

`python -m pytest backend/tests/ -q` — **46 passing.**

These are mostly physics tests rather than unit tests. A hydrological model
that passes its unit tests but does not conserve water is worse than no model,
because it is wrong in a way that looks right.

| Group | Asserts |
|---|---|
| Level–storage | Round-trip, monotonicity, anchoring at FRL and dead level, area = dS/dh, β recovery from synthetic data |
| Mass balance | Volume conservation to 1e-9, hourly vs 6-minute agreement < 1 mm, storage never negative, spill zero below crest |
| Runoff | Runoff ≤ rainfall always, unit hydrograph conserves volume to 2%, steeper catchments peak sooner |
| Routing | C0+C1+C2 = 1, auto sub-reaching restores stability, volume conserved to 2%, attenuation and lag both present, never negative, calibration recovers known K |
| Tide | Dominant period in the semi-diurnal band, ~2 highs/day, spring range plausible for Cochin, discharge shortens intrusion |
| Hydropower | Rated flow at FRL within 15% of nameplate for both plants, no output below cut-in, efficiency never exceeds peak, peak tariff worth more, spill above turbine rating not charged as lost revenue |
| Optimiser | Bounds and ramp limits respected, drawdown converges on target, **policy search is bit-for-bit deterministic**, optimised beats baseline, offtake cap reduces revenue |

---

## 6 · Reproducing all of it

```bash
python scripts/fetch_data.py --all      # cache + quality report
python -m pytest backend/tests/ -q      # 46 tests
python scripts/lead_time_study.py       # §3
python scripts/make_figures.py          # all figures + figure_facts.json
python scripts/build_dossier.py         # the PDF
```

Every number in this document and in the dossier is regenerated by those
commands. None is hand-entered. If the upstream feed changes, the numbers
change — which is the point.
