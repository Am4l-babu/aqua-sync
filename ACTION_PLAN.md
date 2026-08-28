# AquaSync — Action Plan

The next fourteen days, concretely. Written for a solo build.

**As of 26 August 2026.** Phases 0–3 are done; the twin runs, is calibrated,
and produces a defensible counterfactual. What follows is the work that turns
that into a submission.

---

## Do these three things first

Everything else can wait a day. These cannot.

### 1 · Order the V1 components — today

Delivery is 3–5 days from Robu.in and Amazon.in, and every hardware task is
blocked behind it. The full list is in [hardware/bom/](hardware/bom/README.md);
the minimum order is ₹6,250.

Do not sequence the build so a ₹90 part blocks a demo. Order one spare ESP32.

### 2 · Confirm the expo entry status

Registration closed on **22 August 2026** and today is the 26th. Before
investing four more weeks, establish where the team actually stands: whether
the entry went in, whether late consideration is possible, and what the
presentation date is.

If the answer is no, the work is not wasted — the project stands on its own
and there are other venues — but the *schedule* changes completely, and it is
worth knowing before optimising for a deadline that may not apply.

### 3 · Start the forecast-error study

This is the highest-value remaining piece of analysis and it needs no
hardware. See [ROADMAP.md](ROADMAP.md) §1 for why it matters more than
anything else on the list.

---

## Week 1 (26 Aug – 1 Sep) · Make the results defensible

| Day | Task | Output |
|---|---|---|
| Tue 26 | Order V1 components. Confirm expo status | Order placed |
| Tue 26 | Read [docs/data-sources.md](docs/data-sources.md) end to end | You can explain both data corrections from memory |
| Wed 27 | **Forecast-error study**: perturb inflow with growing error, re-run the policy search as an ensemble | `scripts/forecast_error_study.py`, a figure, a number |
| Thu 28 | Run the Aug 2022 out-of-sample scenario | Proof the model was not tuned to one event |
| Fri 29 | Write `docs/validation.md`: replay + lead time + out-of-sample + forecast error, in one place | The document a sceptical judge is handed |
| Sat 30 | Cascade co-optimisation: extend the policy search across both dams | The Figure 2 failure, solved |
| Sun 31 | Regenerate figures and the dossier; read the PDF as a stranger would | Updated `AquaSync_Project_Dossier.pdf` |

**Week 1 gate:** every headline number has a stated error bar, and the
perfect-foresight caveat is resolved rather than disclosed.

---

## Week 2 (2 – 8 Sep) · Build the rig

Components should have arrived by 30 August.

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
| 2 | FastAPI backend + live what-if panel | Makes the dashboard real rather than canned |
| 3 | Full offline rehearsal | Pull the network cable and run the entire demo |
| 4 | A1 poster | Figures 1, 4 and 5 carry it. Print by expo minus 3 days |
| 5 | Pitch rehearsal, out loud, ten times | Script is in the dossier §12 |
| 6 | Test suite and CI | Protects against a late refactor breaking the demo |

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
| *"What if the forecast is wrong?"* | The forecast-error study. **Do the study first** — this is the question that exposes an unfinished project |
| *"KSEB will never adopt this."* | Correct, not on trust. Shadow mode for one monsoon, publish the comparison |
| *"Why not use 2018 data?"* | Because it is not in the public dataset — and finding that out is why the flagship case is October 2021. This answer earns credit rather than losing it |
| *"Isn't this just a dashboard?"* | The output is a three-parameter release policy, not a screen of gauges |
| *"What about the towns — which streets flood?"* | Out of scope, deliberately. 1D routing gives river discharge; 2D inundation is the roadmap |
| *"Who is liable if it is wrong?"* | Advisory permanently. A named officer approves; the twin never operates a gate |

---

## Standing rules

- **Follow the git workflow.** Update `PROGRESS.md` on `main` before branching.
  Branch from `development`, never from `main`. PR into `development`.
- **No new features.** The scope is Phases 0–3 plus the V1 rig plus two chosen
  upgrades. New ideas go in [ROADMAP.md](ROADMAP.md), not the build.
- **Never quote a number the code cannot regenerate.** Every figure in the
  dossier comes from `scripts/`. Keep it that way.
- **Say "about 3 m", never "3.16 m".** Replay error is 0.30 m MAE; two
  decimal places claim precision that is not there.
