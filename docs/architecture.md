# AquaSync architecture

## What the system is

A decision-support digital twin for a dam–river system. It ingests reservoir
telemetry, rainfall forecasts and tide predictions; simulates the reservoir
and the river downstream; searches operating policies; and recommends a
release schedule that a human operator approves or rejects.

**It never operates a gate.** That boundary is deliberate and permanent for
anything resembling a real deployment — see [Trust boundary](#trust-boundary).

## Layer diagram

```
                          ┌──────────────────────────────────────┐
                          │      LAYER 4 - INTERFACE             │
                          │  3D twin (Three.js) · what-if panel  │
                          │  Crisis Commander · Malayalam alerts  │
                          └──────────────▲───────────────────────┘
                                         │ WebSocket (telemetry, 1 Hz)
                                         │ REST (scenarios, policies)
                          ┌──────────────┴───────────────────────┐
                          │      LAYER 3 - DECISION              │
                          │  Policy search over (target level,   │
                          │  start time, max rate)               │
                          │  Objective: flood · dam safety ·     │
                          │  revenue · gate wear                 │
                          └──────────────▲───────────────────────┘
                                         │
                          ┌──────────────┴───────────────────────┐
                          │      LAYER 2 - SIMULATION            │
                          │  ① SCS-CN runoff  → inflow           │
                          │  ② Mass balance   → level            │
                          │  ③ Muskingum      → downstream Q     │
                          │  ④ Tidal backwater→ safe conveyance  │
                          │  ⑤ Hydropower     → MW and rupees    │
                          └──────────────▲───────────────────────┘
                                         │
                          ┌──────────────┴───────────────────────┐
                          │      LAYER 1 - INGESTION             │
                          │  KSEB bulletin · IMD/Open-Meteo      │
                          │  INCOIS tide · Sentinel-1 SAR        │
                          │  ESP32 field nodes (MQTT/LoRa)       │
                          └──────────────────────────────────────┘
```

Layer 2 is pure NumPy with no web, no I/O and no framework dependencies.
That is what makes it testable, and it is why `backend/aquasync/twin/`
imports nothing from `api/`.

---

## Layer 2 — the simulation core

### ① Rainfall → inflow (`twin/runoff.py`)

SCS Curve Number for losses, synthetic triangular unit hydrograph for
timing.

The governing insight is that **antecedent wetness dominates**. The same
100 mm produces wildly different runoff on a dry June catchment versus a
saturated October one, so the curve number is shifted between AMC-I/II/III
using a rolling five-day antecedent depth that updates *as the storm
proceeds*. A long monsoon spell progressively saturates its own catchment
and the runoff coefficient climbs hour by hour. That feedback is what turns
a wet week into a flood.

Catchment response time comes from the Kirpich formula. For the steep
Western Ghats catchments feeding Idukki, the lag is short — well under a
day. **That is precisely why pre-emptive release must be driven by a
forecast and not by an observed inflow rise.** By the time inflow is
visibly climbing, the decision window has closed.

### ② Reservoir mass balance (`twin/reservoir.py`)

```
dV/dt = Q_in + Q_rain − Q_turbine − Q_spill − Q_evap
```

Explicit Euler at an hourly step. At Idukki's scale (1,459 Mm³ live) the
integration error is orders of magnitude below the level-gauge resolution, so
anything fancier would be false precision.

Level ↔ storage uses a fitted power law rather than a surveyed
elevation–capacity table, which we do not have:

```
S(h) = S_frl · ((h − h_dead)/(h_frl − h_dead))^β
```

Fitted on 1,836 validated Idukki bulletin rows: **β = 1.348, r² = 0.9957,
MAE 17 Mm³** against a mean storage of 904 Mm³. β > 1 means storage grows
faster than linearly with height — which is exactly why the top two metres
of a reservoir are worth so much more as flood cushion than the bottom
twenty.

Refitting this curve against recent rows is also how the twin detects
**siltation**: as sediment accumulates, real capacity drifts below the
design curve, and a curve refitted annually tracks that drift without a
bathymetric survey.

### ③ River routing (`twin/routing.py`)

Muskingum storage routing, with Muskingum–Cunge available for ungauged
reaches where K and x must come from channel geometry instead of gauge
pairs.

One implementation detail matters enough to call out. The scheme is stable
only when `2Kx ≤ dt ≤ 2K(1−x)`. A 38 km reach with K = 8 h at an hourly step
violates the lower bound, and the routed hydrograph oscillates — it can dip
below zero before the wave arrives, which reads as the river running
backwards. The fix is to split the reach into N sub-reaches of K/N and route
in series; `MuskingumReach` computes the required N automatically. This is
not a workaround, it is the correct discretisation of a long reach.

### ④ Tidal backwater (`twin/tide.py`)

Harmonic tide prediction (M2, S2, K1, O1, N2 for Kochi) plus an exponential
backwater decay upstream from the mouth. Higher river discharge pushes the
tide seaward, so intrusion length shrinks as Q rises — a big release partly
defends against its own backwater.

The output the optimiser consumes is **effective conveyance**: how much
discharge the reach can pass before overtopping, *given* the tide. Cochin's
spring range is only about 1 m, but on a river already at bankfull, 1 m
decides whether a town floods. This produces a recurring, free, twice-daily
window in which the same volume can be moved at materially lower risk.

### ⑤ Hydropower (`twin/power.py`)

`P = ρ·g·Q·H_net·η`, with η from an approximated turbine hill diagram (peak
near 85% of rated flow, falling away either side) and revenue at KSEB
time-of-day bands.

A subtlety that changes the answer: only the part of a spill that the
turbines *could* have absorbed counts as forgone generation. Water above
turbine rating had to be spilled regardless, and charging it against the
flood decision overstates the cost of acting — which biases an operator
toward holding water. Getting this wrong makes safety look more expensive
than it is.

One asymmetry specific to Idukki is worth knowing: **the Moolamattom
powerhouse discharges into the Muvattupuzha, not the Periyar.** Generation
therefore does not load the Periyar at all — only the spillway does. Sending
water through the turbines is both the profitable option *and* the one that
spares Aluva. They are not in conflict; only *timing* puts them in conflict.

---

## Layer 3 — the decision engine

### Why policy search, not schedule search

The first implementation searched over N independent hourly release values.
It produced results that were **non-monotonic in lead time** — 10 days
looked better than 14, which looked better than 21. That was not a finding.
It was an artefact: a 30-day window has 720 free variables, and a fixed
candidate budget covers a longer horizon ever more sparsely, so the numbers
measured search luck rather than lead time.

The fix was to search the space operators actually work in. A
`DrawdownPolicy` is three numbers:

```
target_level   — draw down to this level
start_hour     — begin acting at this time
max_rate       — release no faster than this
```

with a proportional controller tracking the target inside a deadband. The
grid over those three is small enough to **enumerate exhaustively**, so the
result is deterministic and reproducible — no seed, no variance.

It is also the only form that can be handed to a control room:

> *From 06:00 on 10 October, release up to 480 cumecs until Idukki reaches
> 728.50 m, then hold within ±0.15 m.*

An 800-element vector of hourly setpoints is not an instruction, is not
auditable, and no operator would ever execute it.

### The objective

```
J = w_flood·Σ(overtopping)²
  + w_safety·Σ(FRL encroachment)²
  + w_revenue·(forgone generation)
  + w_gate·(ramping + gate movements)
```

Flood cost is superlinear because depth–damage curves are convex — twice the
overtopping is far more than twice the damage.

The weights are **exposed and contestable on purpose**. Choosing them is a
policy decision, not an engineering one. Peak-monsoon posture and dry-season
posture invert the ranking, and the honest thing is to let the operator see
and set them rather than bury a value judgement in a constant.

### Operational limits

`max_ramp_cumecs_per_hour` matters more than it looks. A sudden large
release is itself a hazard — people and livestock are in the riverbed, and
Kerala protocol requires staged opening with siren warning. A schedule that
is mathematically optimal but ramps at 400 cumecs/hour is not implementable,
and proposing it destroys credibility with the only people who could adopt
it.

`max_mean_turbine_cumecs` caps grid offtake. Without it the optimiser runs
the turbines flat out for a month and books the revenue, because nothing in
the *physics* stops it. The *grid* stops it — Idukki is a peaking station on
a system with its own merit order. Omitting this constraint inflates the
apparent benefit substantially, so results are reported both ways and the
constrained figures are the ones quoted.

---

## Trust boundary

```
   AquaSync ────► recommendation ────► human operator ────► gate
              (advisory only)         (accountable)
```

The system is **advisory**, permanently. Three reasons, all of which a judge
or an official will raise:

1. **Liability.** If an automated system opens gates and someone drowns, the
   question of who is accountable has no acceptable answer. A recommendation
   that a named officer approves has a clear one.
2. **Trust is earned in shadow mode.** The credible deployment path is to
   run alongside existing practice for a full monsoon, logging what it would
   have recommended and what actually happened, and to publish the
   comparison. Anything faster will be — correctly — refused.
3. **The model is wrong in known ways.** Daily input data, uncalibrated
   routing parameters, no 2D inundation. Those are acceptable in an advisory
   tool and unacceptable in an actuator.

The hardware demonstrator does close the loop onto a servo, because it is a
30 cm acrylic tank. That distinction should be stated out loud during the
demo rather than left for someone to catch.

---

## Layer 1 — ingestion and the field node

The ESP32 node exists to answer one question that software alone cannot:
*where does the data come from when the government feed is a day stale and
the network is down?*

```
  ┌────────────────────────────────────────────┐
  │ ESP32 reservoir node                       │
  │  JSN-SR04T ultrasonic ──┐                  │
  │  Hydrostatic pressure ──┼─► EKF fusion     │
  │  BMP280 barometric ─────┘   → level state  │
  │  DS18B20 temperature (sound-speed comp.)   │
  │                                            │
  │  Wi-Fi/MQTT  (primary)                     │
  │  LoRa SX1278 (fallback, no infrastructure) │
  │  SD card     (last resort, always logs)    │
  └────────────────────────────────────────────┘
```

Three things make it more than a sensor demo:

**Sensor fusion, not a single reading.** Ultrasonic sensors flutter ±2 cm on
a wavy surface and their speed of sound drifts with temperature. A 1-D
Kalman filter fusing ultrasonic with hydrostatic pressure, temperature-
compensated, yields a level estimate stable enough to act on, and — more
usefully — a *disagreement signal* that flags a failing sensor.

**Degradation, not failure.** Wi-Fi → LoRa → local SD, and if telemetry is
lost entirely the node falls back to a conservative worst-case profile. A
tool that only works when the internet is up is not a disaster-management
tool.

**Tamper-evident logging.** Each record is chained by SHA-256 to its
predecessor. After the 2018 floods there were public disputes about whether
reservoir levels had been reported accurately and promptly. A hash chain
does not prevent misreporting, but it makes silent retrospective editing
detectable, which is the part that matters in an inquiry.

---

## Repository layout

```
backend/aquasync/
  twin/         simulation + optimisation (pure NumPy, no web deps)
  io/           data adapters, with validation
  api/          FastAPI: REST + telemetry WebSocket
dashboard/      Three.js 3D twin, no build step
firmware/       ESP32 nodes (PlatformIO)
hardware/       BOM, wiring, CAD for the scale rig
scripts/        reproducible analyses
data/raw/       third-party cache (gitignored)
data/processed/ derived results (committed — reproducibility)
docs/           this
```

`data/processed/` is committed on purpose. The upstream feed changes daily
and could disappear; committed derived artefacts mean a result quoted in the
report can still be checked next year.
