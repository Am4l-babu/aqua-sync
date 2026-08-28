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

### 🟢 Perfect foresight - two lead times in, 28 Aug 2026

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

**Results:**

| Lead time | Decision rule | Freeboard gained | % of perfect foresight |
|---|---|---|---|
| 24 h (issued 15 Oct 18z) | perfect foresight | 3.11 m | 100% |
| 24 h | expected-value | 0.81 m | **26%** |
| 24 h | minimax-regret | 1.03 m | **33%** |
| 90 h (issued 13 Oct 00z) | perfect foresight | 3.11 m | 100% |
| 90 h | expected-value | 1.03 m | **33%** |
| 90 h | minimax-regret | 2.30 m | **74%** |

**Two findings:**

1. **The decision rule matters more than the forecast skill does.**
   Committing to the ensemble member that looks best on average picks a
   policy tuned to a light-rain story; when the actual storm arrives, that
   policy has already released too little too late. Committing to the
   policy that performs best against its *worst* member sacrifices some
   upside in the average case but survives the real event far better at
   both lead times tested.
2. **The minimax advantage grows with lead time.** The gap between the two
   rules is 7 points at 24 h (26 vs 33%) and 41 points at 90 h (33 vs 74%).
   This is mechanistically sensible rather than a fluke: more lead time
   means more spread in how the ensemble members disagree about the
   storm's evolution, so there is more to gain from hedging against the
   worst case instead of betting on the average one. Close to the event
   the members converge and the rule matters less; far from it, the rule
   is most of what separates a good outcome from a bad one. **Report the
   pair at each lead time - "26/33% at 24 h, 33/74% at 90 h" - never a
   single number, since which one you'd quote depends entirely on which
   rule you assume the operator uses.**

**A bug was caught and fixed between the first and second pass, and it is
worth narrating rather than quietly overwriting the earlier numbers.** The
first version of the script fetched GEFS rainfall only out to the forecast
horizon, but let the optimiser's evaluation window run to the scenario's
full default end (2021-10-28) regardless - so every hour past the fetched
horizon was silently zero-padded. Real observed inflow in that gap is
130-240 cumecs, not near-zero (checked directly against the KSEB bulletin),
so the padding fabricated over a week of fictitious near-drought and
distorted every policy ranking that used it. The fix truncates the
evaluation window to exactly `[scenario start, issue time + horizon]` for
*both* the forecast-driven and perfect-foresight runs, so no hour in either
comparison is fabricated. The qualitative finding (minimax beats
expected-value, more so at longer lead) survived the fix unchanged; the
exact percentages moved by 5-8 points. The numbers in the table above are
post-fix.

**Other honest caveats, most serious first:**

1. **The bias correction is large and single-event.** GEFS's ensemble-mean
   rainfall for this storm needed a correction factor of 3.18x at 90 h lead
   and 1.68x at 24 h. Neither is a small nudge - both rescale one sample,
   not a trained correction, and neither should be assumed to generalise to
   the next event. A proper fix needs the correction fit across many
   storms, which is future work.
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
4. **Two issue times so far.** ROADMAP.md asks for 24 / 72 / 120 h reported
   separately, because the literature says skill decays very differently
   across that range. 24 h and 90 h (close to the 72 h bucket) are covered;
   120 h is the next run - see ROADMAP.md item 1.

Reproduce: `python scripts/forecast_error_study.py --issue-date 2021-10-13
--hh 00 --horizon-h 168` (90 h) or `--issue-date 2021-10-15 --hh 18
--horizon-h 102` (24 h). Results: `data/processed/forecast_error_study_2021-10-13_00z.json`
and `..._2021-10-15_18z.json`.

### 🔴 River routing

Muskingum K and x come from reach geometry and an assumed flood-wave
celerity — **not from gauge data.** `MuskingumReach.calibrate()` implements
the fit and is unit-tested against synthetic data, but has never been run
against a real gauge pair.

Consequence: **downstream discharge figures are indicative, not measured.** Do
not quote a predicted discharge at Aluva as though it were validated. Needs
CWC gauge records at Neeleeswaram and Aluva.

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
