# AquaSync — Action Plan

The next fourteen days, concretely. Written for a solo build.

**As of Wednesday 9 September 2026.** Every software task that does not need
the rig is finished. The Decision Engine is 7 / 7, the last open modelling
item is closed, and the twin, the API, the 3D dashboard, Crisis Commander and
the what-if panel have all been driven end to end in a real browser. **The
bench is now the entire critical path**, and it has not been started.

A note on dates: this calendar is checked against the actual calendar. An
earlier version of this plan dated Week 2 to "Mon 2 Sep", which is a
Wednesday.

---

## What closed since 31 August

Both of the things only the team could do are done, and the software list
emptied behind them.

| Was blocking | Closed |
|---|---|
| Order the V1 components | Ordered and **received 8 Sep**. Two SX1278 LoRa modules and further components followed on 9 Sep |
| Confirm the expo entry | **Confirmed 8 Sep** |
| Crisis Commander never seen rendered | Driven through a real browser over the DevTools protocol, 8 Sep. There *is* a headless browser on this machine — earlier notes were wrong |
| What-if slider unwired | Wired to `POST /api/whatif` and browser-verified, 8 Sep |
| 3D twin drawn, not measured | Rebuilt on real DEM terrain, 8 Sep |
| Rig telemetry unsubscribed | `aquasync.api.rig` bridges MQTT, follows the SHA-256 record chain, serves `GET /api/rig`. Receive-only |
| Second storm not in the dossier | §4.4 and Figure 6 carry both storms, 9 Sep — separate axes, never one merged curve |
| Joint cascade objective | Built 8 Sep. Inert on the data as held, and that is the finding |

---

## The one open question

**What is the presentation date?** The entry is confirmed but the date is not
recorded anywhere in this repository, and three deadlines below hang on it:
when the poster must go to print (expo minus 3 days), when the offline
rehearsal has to be finished, and how much slack the bench build actually
has. Everything downstream of "expo minus N" is written relative until
somebody writes the date into [PROGRESS.md](PROGRESS.md).

If it turns out to be sooner than three weeks, cut in this order: the LoRa
link first, then Crisis Commander polish, then the poster's third figure.
**Do not cut fault injection.**

---

## Week 2 result · Mon 31 Aug – Sun 6 Sep

The gate was: *pour water in and the gate opens before FRL, untouched.* **Not
met — the bench was not built.** The week went into software instead, which
was worth doing and is now finished, but it means the rig build starts a week
late with the same amount of work in front of it.

That is the honest position and it should shape the fortnight below: there is
no longer a software task to fall back on when the hardware is frustrating.

---

## Week 3 · Wed 9 – Sun 13 Sep · Build the bench

Parts are in hand, so nothing here waits on delivery. Test each component
alone **before** assembly: debugging a sensor that was never verified, inside
a rig that is already glued and full of water, costs more than a day.

| Day | Task | Output |
|---|---|---|
| Wed 9 | Bench-test every component individually. Set the LM2596 to **5.0 V before it meets the ESP32** | Each part confirmed working alone, on the desk |
| Thu 10 | Flash the fixed firmware to the ESP32; confirm it publishes to `aquasync/reservoir/01/telemetry` and the bridge verifies the hash chain | `GET /api/rig` shows `source: LIVE`, chain verified, 0 breaks — against real hardware for the first time |
| Fri 11 | Cut and cement the acrylic tanks; plumb the pump loop | Water circulates, nothing leaks. Leave the glue to cure overnight |
| Sat 12 | Sluice gate: NEMA 17, A4988, rack-and-pinion, limit switches | The gate travels its full range and homes reliably from either end |
| Sun 13 | Level sensing: JSN-SR04T + DS18B20 compensation + EKF | Level stable to ±2 mm on a *moving* surface, not a still one |

**Week 3 gate:** pour water into the upstream tank and the rig's gate opens
*before* the reservoir tank reaches its FRL line — without anyone touching a
keyboard. This is the bench loop only; see [ROADMAP.md](ROADMAP.md) §Never in
scope.

---

## Week 4 · Mon 14 – Sun 20 Sep · The beat that wins the room, then rehearse

| Priority | Day | Task | Notes |
|---|---|---|---|
| **1** | Mon 14 | **Fault injection**: sensor-failure and gate-jam switches | The twin detects the disagreement, falls back to mass-balance state estimation, and keeps controlling. The dashboard half is already built — a rig fault raises a banner across the 3D view, and `sensors_agree` / `gate_jammed` / commanded-vs-verified already arrive over MQTT. What is left is the physical switches and the firmware paths behind them. **Build this even if something else has to be cut** |
| 2 | Tue 15 | Close the bench loop: twin computes a policy, the rig's model sluice executes it | Live level on the 3D dashboard, driven by real water |
| 3 | Wed 16 | Full offline rehearsal — pull the network cable and run the whole demo, twice | Everything keeps running. If it needs the network, it is not ready |
| 4 | Thu 17 | Crisis Commander on a tablet, with a stranger who has not seen it | Beat 5. Watch where they hesitate; fix that, not what you assumed |
| 5 | Fri 18 | A1 poster — Figures 1, 4 and 5 carry it | **Print by expo minus 3 days**, whenever that turns out to be |
| 6 | Sat 19 – Sun 20 | Pitch, out loud, ten times. Script is in the dossier §12 | Out loud, timed. Reading it silently does not count |

**Slack:** the LoRa link is the only thing in the fortnight that can be
dropped without weakening the demo. It is a V2 item and stays bench-only.

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
