# Validation

What has been tested, what the errors are, and what is still unverified.

A model that has not been validated against something it was not fitted to is
a hypothesis. This document tracks the distance between those two states, and
is honest about how far there is still to go.

**Status as of 26 August 2026:** the reservoir model is calibrated and
replay-validated. The routing and runoff models are **not yet validated**, and
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

### 🔴 Perfect foresight

The optimiser sees the **true** inflow series when choosing a policy. Real
forecasts are wrong, and Western Ghats rainfall forecasts are wrong in
specific, biased ways.

**Every benefit figure above is therefore an upper bound.** Nothing in this
document should be presented as an achievable operational result until the
forecast-error study is done.

Planned: drive the policy search from perturbed forecasts with realistic error
growth (±20% at 24 h widening to ±60% at 120 h), run an ensemble, and report
how much of the ~3 m survives.

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

### 🟠 Out-of-sample scenario

Everything above is October 2021. The August 2022 scenario is defined in
`twin/scenarios.py` and has not been run. Until it has, the model is
*calibrated*, not *validated*, and the distinction is one a domain-literate
judge will make.

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
