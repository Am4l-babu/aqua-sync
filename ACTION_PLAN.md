# AquaSync — Action Plan

The next fourteen days, concretely. Written for a solo build.

**As of 30 August 2026.** Phases 0–3 are done and **Week 1 is complete** —
the twin runs, is calibrated, and its headline result now has a measured
error bar rather than a disclosed caveat. What follows is the work that turns
that into a submission.

---

## Week 1 result

The gate was: *every headline number has a stated error bar, and the
perfect-foresight caveat is resolved rather than disclosed.* **Met.**

| Question | Answer now on record |
|---|---|
| What if the forecast is wrong? | Measured at five lead times on the optimiser's own objective: a real ensemble matches hindsight **exactly at 24 and 48 h**, then degrades to about **+69%** excess cost by 90 h. Hedging (minimax-regret) is never better and usually worse |
| Was the model tuned to one event? | No. August 2022 replays at **0.319 m** against October 2021's 0.303 m |
| Can the two dams be scheduled jointly? | Not the way it looked. Optimising them independently puts the joint peak **126% above** what happened; retiming recovers 9%. It is an objective-function problem |
| Are K and x calibrated? | No, and now quantified: the fit fails on daily data (**r² = 0.005**). The CWC 8 h anchor stands |

One claim was **retracted** mid-week when a third data point broke it, and
the retraction is in the dossier rather than quietly dropped. That record is
worth more to a sceptical judge than the finding would have been.

All four are written up in [docs/validation.md](docs/validation.md) §2b and
§4, and the two that change the headline are in the dossier at §4.4 and
§4.5. Figures, dossier, abstract and ICFOSS analysis all regenerate
byte-identically from `scripts/`.

---

## Do these two things first

Everything else can wait a day. These cannot — and they have now been open
since 26 August.

### 1 · Order the V1 components — today, and this is now urgent

Delivery is 3–5 days from Robu.in and Amazon.in, and every hardware task is
blocked behind it. The full list is in [hardware/bom/](hardware/bom/README.md)
with live vendor links in [bom.html](hardware/bom/bom.html); the minimum order
is ₹6,250.

**Week 2 starts on Monday and it is the entire rig build.** Ordering today
means parts land Wed–Fri, which costs the first half of that week. Ordering
later means Week 2 has no hardware in it at all, and EVOKE is an IoT club
event — a software-only submission underperforms regardless of how good the
modelling is.

Do not sequence the build so a ₹90 part blocks a demo. Order one spare ESP32.

### 2 · Confirm the expo entry status

Registration closed on **22 August 2026** and today is the 30th — this has
now been unanswered for eight days. Before investing four more weeks,
establish where the team actually stands: whether
the entry went in, whether late consideration is possible, and what the
presentation date is.

If the answer is no, the work is not wasted — the project stands on its own
and there are other venues — but the *schedule* changes completely, and it is
worth knowing before optimising for a deadline that may not apply.

### 2b · If the answer on the expo is no

Read this before deciding the project failed. The work stands on its own: a
calibrated twin, a measured forecast-error result, a negative cascade finding
worth publishing, and four documents that regenerate from public data. Other
venues exist, and the schedule below simply loses its deadline. What changes
is *sequencing*, not value — with no expo date, the joint cascade objective
(§Weeks 3–4) is worth more than the rig.

---

## Sunday 31 August · the one task left in Week 1

| Task | Output |
|---|---|
| Read the dossier end to end as a stranger would | Nothing in it contradicts anything else in it |

Everything else on Week 1's list is done and committed. If the components
have not been ordered by tonight, do that instead of reading the PDF.

---

## Week 2 (2 – 8 Sep) · Build the rig

**This week is entirely contingent on the order going in.** If parts arrive
mid-week, compress: bench-test and tanks on the day they land, gate and level
sensing the next, and cut the EKF refinement rather than the fault injection.
If they will not arrive at all, do not leave the week empty — fall through to
Weeks 3–4 and bring Crisis Commander forward, since it needs no hardware.

| Day | Task | Output |
|---|---|---|
| Mon 2 | Bench-test every component individually before assembly | Each part confirmed working alone |
| Tue 3 | Cut and cement the acrylic tanks; plumb the pump loop | Water circulates, nothing leaks |
| Wed 4 | Sluice gate: NEMA 17, rack-and-pinion, limit switches | Gate travels full range, homes reliably |
| Thu 5 | Level sensing: JSN-SR04T + DS18B20 compensation + EKF | Level stable to ±2 mm on a moving surface |
| Fri 6 | Telemetry: ESP32 → MQTT → twin (Mosquitto is already installed) | Live level on the 3D dashboard |
| Sat 7 | Close the loop: twin computes a policy, gate executes it | Physical gate opens ahead of a simulated storm |
| Sun 8 | **Fault injection**: sensor-failure and gate-jam switches | System detects, degrades, keeps controlling |

**Week 2 gate:** pour water into the upstream tank and the gate opens *before*
the reservoir tank reaches its FRL line — without anyone touching a keyboard.

A note on sequencing: test each component alone before assembly. Debugging a
sensor that was never verified, inside a rig that is already glued together
and full of water, costs more than a day.

---

## Weeks 3–4 · Interface, rehearsal, polish

| Priority | Task | Notes |
|---|---|---|
| 1 | Crisis Commander mode | Highest demo value per hour of work |
| 2 | Wire the what-if panel to the live backend | The API and the slider both exist; they are not connected |
| 3 | Full offline rehearsal | Pull the network cable and run the entire demo |
| 4 | A1 poster | Figures 1, 4 and 5 carry it. Print by expo minus 3 days |
| 5 | Pitch rehearsal, out loud, ten times | Script is in the dossier §12 |
| 6 | **Joint cascade objective** | The largest open modelling item. Only worth starting if the rig is on track — or if there is no expo date |

---

## The demo, and the one beat that matters

Six beats, roughly three minutes. Full sequence in the dossier §12.

1. The rig is already running when they walk up. Point, do not explain.
2. Figure 1 on screen: *"this is real, and it is public."*
3. Dump water in — a live storm. The gate opens **before** FRL.
4. **Flip the sensor-failure switch.** The twin detects the disagreement,
   falls back to mass-balance state estimation, and keeps controlling.
5. Hand over the tablet: *"You are the operator. It is 16 October 2021."*
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
| *"How do you know the model is right?"* | 0.30 m MAE reproducing observed Idukki level over 20 days, on data it was not fitted to |
| *"What if the forecast is wrong?"* | **Answered, at five lead times.** Inside 48 h a real GEFS ensemble picks the same policy hindsight would; by 90 h it costs about 69% more on the full objective. So the value sits in the last two days — which is also when a control room has least time to think |
| *"You optimise two dams on one river — do they interact?"* | Badly, and it is measured: optimising them independently puts the joint peak 126% above what happened. Volunteering this is stronger than being caught by it |
| *"KSEB will never adopt this."* | Correct, not on trust. Shadow mode for one monsoon, publish the comparison |
| *"Why not use 2018 data?"* | Because it is not in the public dataset — and finding that out is why the flagship case is October 2021. This answer earns credit rather than losing it |
| *"Isn't this just a dashboard?"* | The output is a three-parameter release policy, not a screen of gauges |
| *"What about the towns — which streets flood?"* | Out of scope, deliberately. 1D routing gives river discharge; 2D inundation is the roadmap |
| *"Who is liable if it is wrong?"* | Advisory permanently. A named officer approves; the twin never operates a gate |

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
