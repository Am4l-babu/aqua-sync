# AquaSync — Action Plan

The next fourteen days, concretely. Written for a solo build.

**As of Monday 31 August 2026.** Phases 0–3 are done and **Week 1 is
complete** — the twin runs, is calibrated on two episodes, and its headline
result has a measured error bar on two storms rather than a disclosed caveat.
What follows is the work that turns that into a submission — and it starts
with two things that are not engineering.

A note on dates: the previous version of this plan called 31 August a Sunday
and started Week 2 on "Mon 2 Sep", which is a Wednesday. The calendar below
is checked against the actual calendar. **Week 2 is this week.**

---

## Week 1 result

The gate was: *every headline number has a stated error bar, and the
perfect-foresight caveat is resolved rather than disclosed.* **Met, twice.**

| Question | Answer now on record |
|---|---|
| What if the forecast is wrong? | Measured at five lead times on **two storms**, on the optimiser's own objective. October 2021: a real ensemble matches hindsight **exactly to 48 h**, then ramps to about **+69%** by 90 h. August 2022: matches **to 90 h** (within +5%), then **+158%** at 120 h. Same structure, different shape — do not average them. Hedging is better in one run of ten, by 0.16 points |
| Was the model tuned to one event? | No. August 2022 replays at **0.319 m** against October 2021's 0.303 m |
| Can the two dams be scheduled jointly? | Not the way it looked. Optimising them independently puts the joint peak **126% above** what happened; retiming recovers 9%. It is an objective-function problem |
| Are K and x calibrated? | No, and now quantified: the fit fails on daily data (**r² = 0.005**). The CWC 8 h anchor stands |
| Does the runoff chain work? | It did not — it produced no runoff hourly. Fixed, pinned by a test, and the forecast study re-run. Now: volume right, amplitude not (NSE 0.07) |

Four claims were **retracted** during the week when more data broke them, and
every retraction is in the document where the claim was made. That record is
worth more to a sceptical judge than the findings would have been.

All of it is in [docs/validation.md](docs/validation.md); the two that
change the headline are in the dossier at §4.4 and §4.5. Figures, dossier,
abstract, research report and ICFOSS analysis all regenerate byte-identically
from `scripts/`.

---

## Do these two things first

Everything else can wait a day. These cannot.

### 1 · Order the V1 components — today

Open since **26 August** — five days. Delivery is 3–5 days from Robu.in and
Amazon.in, and every hardware task is blocked behind it. The full list is in
[hardware/bom/](hardware/bom/README.md) with live vendor links in
[bom.html](hardware/bom/bom.html); the minimum order is ₹6,250.

**Week 2 is this week and it is the entire rig build.** Ordering today means
parts land Wednesday to Friday, which costs the first half of the week and
is survivable. Ordering later means Week 2 has no hardware in it at all, and
EVOKE is an IoT club event — a software-only submission underperforms
regardless of how good the modelling is.

Do not sequence the build so a ₹90 part blocks a demo. Order one spare ESP32.

### 2 · Confirm the expo entry status

Registration closed on **Saturday 22 August** — nine days ago — and this has
not been answered. Before investing three more weeks, establish where the
team actually stands: whether the entry went in, whether late consideration
is possible, and what the presentation date is.

### 2b · If the answer on the expo is no

Read this before deciding the project failed. The work stands on its own: a
calibrated twin, a measured forecast-error result on two storms, a negative
cascade finding worth publishing, and four documents that regenerate from
public data. Other venues exist, and the schedule below simply loses its
deadline. What changes is *sequencing*, not value — with no expo date, the
joint cascade objective is worth more than the rig, and Weeks 2–4 invert.

---

## Monday 31 August · desk work while the parts are in transit

None of this needs hardware. In this order.

| # | Task | Output |
|---|---|---|
| 1 | Order the parts (10 minutes) | An order number |
| 2 | Ask about the expo entry | An answer, or a date for one |
| 3 | **Open Crisis Commander in a browser** — `uvicorn aquasync.api.main:app --port 8000 --app-dir backend`, then `/crisis.html` | The page has been seen by a human. Fix what looks wrong |
| 4 | Close the `.gitignore` hole: `**/data/raw/` and `**/data/external/`; delete the stray `backend/data/raw/` | `git check-ignore backend/data/raw/Idukki.json` succeeds |
| 5 | Commit the second storm and the refreshed documents. **Full** `python scripts/check.py` first — this touches `data/processed/`. `PROGRESS.md` goes on `main` directly; everything else on a branch off `development`, PR in | Ten forecast-error files and ten documents on `development`; a clean `git status` |
| 6 | Read the dossier end to end as a stranger would | Nothing in it contradicts anything else in the repository. Note where §4.4 still says "one storm" |

---

## Week 2 · Mon 31 Aug – Sun 6 Sep · Build the rig

**This week is entirely contingent on the order going in today.** Parts land
Wednesday to Friday at the earliest, so Monday and Tuesday are desk days and
the physical build compresses into the back half. If parts will not arrive
at all, do not leave the week empty — fall through to Weeks 3–4 and bring
the what-if wiring and the dossier update forward, since neither needs
hardware.

| Day | Task | Output |
|---|---|---|
| Mon 31 | Desk list above | Parts ordered; Crisis Commander seen; second storm committed |
| Tue 1 | Wire the what-if slider to `POST /api/whatif` (both ends exist) | Dragging the slider changes the level trace from the live model, not the client-side approximation |
| Wed 2 | ✅ Done 9 Sep. Second storm into dossier §4.4 and Figure 6 (October qualified, not replaced); full `check.py` green | A dossier that says "two storms" and a Figure 6 with two **rows** — separate axes, never one merged curve |
| Wed 2 – Thu 3 | **Parts land.** Bench-test every component individually before assembly | Each part confirmed working alone. Set the LM2596 to 5.0 V *before* it meets the ESP32 |
| Fri 4 | Cut and cement the acrylic tanks; plumb the pump loop | Water circulates, nothing leaks |
| Sat 5 | Sluice gate: NEMA 17, rack-and-pinion, limit switches. Level sensing: JSN-SR04T + DS18B20 compensation + EKF | Gate travels full range and homes reliably; level stable to ±2 mm on a moving surface |
| Sun 6 | Telemetry: ESP32 → MQTT → twin (Mosquitto is already installed). Close the loop **on the bench**: twin computes a policy, the rig's model sluice executes it | Live level on the 3D dashboard; the rig's gate opens ahead of a simulated storm. **This loop exists on the bench and nowhere else** — see [ROADMAP.md](ROADMAP.md) §Never in scope |

**Week 2 gate:** pour water into the upstream tank and the gate opens *before*
the reservoir tank reaches its FRL line — without anyone touching a keyboard.

Fault injection moves to the first day of Week 3. It is the most important
beat of the demo and it should not be built at midnight on a Sunday.

A note on sequencing: test each component alone before assembly. Debugging a
sensor that was never verified, inside a rig that is already glued together
and full of water, costs more than a day.

---

## Weeks 3–4 · Mon 7 – Sun 20 Sep · The demo, and the polish

| Priority | Task | Notes |
|---|---|---|
| 1 | **Fault injection**: sensor-failure and gate-jam switches (Mon 7) | The twin detects the disagreement, falls back to mass-balance state estimation, keeps controlling. Build this even if something else has to be cut |
| 2 | Crisis Commander polish, on a tablet, with a stranger | Beat 5 of the demo. If it needs the network, it is not ready |
| 3 | Full offline rehearsal | Pull the network cable and run the entire demo, twice |
| 4 | A1 poster | Figures 1, 4 and 5 carry it. Print by expo minus 3 days |
| 5 | Pitch rehearsal, out loud, ten times | Script is in the dossier §12 |
| 6 | **Joint cascade objective** | The largest open modelling item. Only worth starting if the rig is on track — or if there is no expo date, in which case it is priority 1 |

---

## The demo, and the one beat that matters

Six beats, roughly three minutes. Full sequence in the dossier §12.

1. The rig is already running when they walk up. Point, do not explain.
2. Figure 1 on screen: *"this is real, and it is public."*
3. Dump water in — a live storm. The gate opens **before** FRL.
4. **Flip the sensor-failure switch.** The twin detects the disagreement,
   falls back to mass-balance state estimation, and keeps controlling.
5. Hand over the tablet: *"You are the operator. It is 8 October 2021."*
6. Pull the network cable. Everything keeps running.

**Beat 4 is the one that wins the room.** Anyone can demo a system working.
Demonstrating a system *failing correctly* is what convinces an engineer that
it was built by someone who expected it to be used. Build the fault-injection
switches even if something else has to be cut.

### Until the rig is built: the software-only sequence

The six beats above assume the bench rig, which is 5 / 10 in
[PROGRESS.md](PROGRESS.md) — the two-tank build, level sensing and stepper
gate are still 📋 Todo. Beats 1, 3 and 4 cannot be performed today. This is
the version that can, entirely on the laptop, and every beat in it has been
driven through a real browser (9 Sep):

1. Open on the twin. The badge reads **REPLAY**, not LIVE: *"the socket
   being open only proves the backend is reachable — not that anything is
   measured."*
2. Point at the terrain caption: measured DEM, measured Sentinel-2 ground,
   schematic structures.
3. **Twin simulation panel.** *"About 3 m more cushion than the day, with
   more revenue, not less."* Volunteer the weak metric before anyone asks
   for it: peak reduction is −277% on this episode and means nothing,
   because neither schedule reached bankfull. Then press **Simulation** over
   the 3D view (or open `?sim=1&trace=opt`): the same episode hour by hour,
   recorded level against the twin's replay so the 0.30 m error is visible,
   with the scrubber moving the water on the dam. Switch the storm to
   **× 1.5**: the day's schedule reaches FRL, AquaSync's does not — say
   "a scaled copy of one storm, not a forecast" in the same breath.
4. **Tide panel.** *"Twice a day the sea lets you move the same water
   cheaply."* One chart carries the whole thesis on release timing.
5. Hand over the what-if slider, then Crisis Commander: *"You have the duty
   desk. It's 8 October 2021."*
6. **Fault injection over MQTT.** A simulated node publishes a hash-chained
   gate jam; the commanded/verified bars separate blue and red, and the
   banner fires. *"The switches are what's left — the software they will
   drive is already proven."* This is the substitute for beat 4 above.
7. Pull the network cable. Nothing changes — the simulation drawer included,
   which now reads the bundle `scripts/bake_dashboard_data.py` writes and
   says **BUNDLED** on its chip. For an unattended screen, open
   `?sim=1&demo=1`: it plays and loops.

Roughly three and a half minutes. Lead with credibility (1–2), volunteer the
weak result before being caught by it (3), close with failure and resilience
(6–7) — the ordering the rig-based sequence already gets right.

---

## Anticipated questions

Have an answer ready. Several of these are already answered in the code.

| Question | Answer |
|---|---|
| *"Where is the hardware? This is an IoT club."* | The rig, running in front of them. Sensor fusion, LoRa fallback, tamper-evident logging |
| *"How do you know the model is right?"* | 0.30 m MAE reproducing observed Idukki level over 20 days; 0.32 m on an August 2022 episode it was never fitted to |
| *"What if the forecast is wrong?"* | **Measured, on two storms.** Inside 48 h a real GEFS ensemble picks the same policy hindsight would; in the easier August 2022 case that holds to 90 h. Beyond the horizon it costs 69% and 158% more. So the value sits in the last two days — which is also when a control room has least time to think |
| *"Two storms is not a curve."* | Correct, and we say so. The shapes differ — one ramps, one cliffs — which is exactly why they are not averaged. A third, harder storm is the next thing the study needs |
| *"You optimise two dams on one river — do they interact?"* | Badly, and it is measured: optimising them independently puts the joint peak 126% above what happened. Volunteering this is stronger than being caught by it |
| *"KSEB will never adopt this."* | Correct, not on trust. Shadow mode for one monsoon, publish the comparison |
| *"Why not use 2018 data?"* | Because it is not in the public dataset — and finding that out is why the flagship case is October 2021. This answer earns credit rather than losing it |
| *"Isn't this just a dashboard?"* | The output is a three-parameter release policy, not a screen of gauges |
| *"What about the towns — which streets flood?"* | Out of scope, deliberately. 1D routing gives river discharge; 2D inundation is the roadmap |
| *"Who is liable if it is wrong?"* | Advisory permanently. A named officer approves; the twin never operates a gate |
| *"What did you get wrong?"* | Four claims, all retracted where they were made, and two defects — one of which made the runoff chain produce no runoff. Then the page number |

---

## Standing rules

- **Follow the git workflow.** Update `PROGRESS.md` on `main` before branching.
  Branch from `development`, never from `main`. PR into `development`.
- **Human contributors only.** No `Co-Authored-By:` trailer for an AI
  assistant, on any commit, ever. GitHub promotes those addresses to
  repository contributors, and the contributor list should show the people
  accountable for the work. Full rule in [CLAUDE.md](CLAUDE.md).
- **No new features.** The scope is Phases 0–3 plus the V1 rig plus two chosen
  upgrades. New ideas go in [ROADMAP.md](ROADMAP.md), not the build.
- **Never quote a number the code cannot regenerate.** Every figure in the
  dossier comes from `scripts/`. Keep it that way.
- **Say "about 3 m", never "3.16 m".** Replay error is 0.30 m MAE; two
  decimal places claim precision that is not there.
- **Treat any conclusion from a partial run set as provisional** until the
  set is complete. Four retractions in one week earned this rule.
- **`python scripts/check.py` before every push** that touched a builder or
  the twin. The `--fast` subset runs itself before every commit.
