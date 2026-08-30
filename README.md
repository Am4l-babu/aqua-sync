# AquaSync

**A decision-support digital twin for dam–river flood and hydropower
optimisation on the Periyar basin, Kerala.**

Built for EVOKE 26 · Track 2, Climate Resilience & Disaster Preparedness ·
MACE IoT Club, Kothamangalam.

---

## The one-paragraph version

In October 2021 the Idukki reservoir entered a 168 mm rain day already
*above* its own published rule level, with the spillway shut. Inflow rose 7.6×
in twenty-four hours. The gates opened three days later — and Idamalayar, on
the same river, opened its gates on exactly the same day. All of that is in
the public KSEB bulletin. AquaSync simulates that system, replays what
happened to within **0.30 m** of the observed reservoir level, and searches
for the release policy that should have been used instead. The answer is about
**3 m more flood cushion** with *slightly more* generation revenue, not less.

## Quick start

```bash
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -r backend/requirements.txt

python scripts/fetch_data.py                # cache the public dam dataset
python scripts/lead_time_study.py           # the central analysis
python scripts/make_figures.py              # all figures
python scripts/build_dossier.py             # the PDF dossier
```

Then open `dashboard/index.html` in a browser for the 3D twin.

```python
from aquasync.twin.scenarios import run_counterfactual
out = run_counterfactual("periyar_oct_2021")
print(out["summary"]["headline_note"])
```

## What is here

| Path | What |
|---|---|
| [`backend/aquasync/twin/`](backend/aquasync/twin/) | Simulation and optimisation core — pure NumPy, no web dependencies |
| [`backend/aquasync/io/`](backend/aquasync/io/) | Data adapters, with a validation layer that matters (see below) |
| [`backend/aquasync/api/`](backend/aquasync/api/) | FastAPI: REST + telemetry WebSocket |
| [`dashboard/`](dashboard/) | Three.js 3D twin — no build step, opens from the filesystem |
| [`firmware/`](firmware/) | ESP32 field and rig nodes (PlatformIO) |
| [`hardware/`](hardware/) | BOM, wiring, CAD for the scale rig |
| [`scripts/`](scripts/) | Reproducible analyses — every published number comes from here |
| [`docs/`](docs/) | Architecture, data sources, and the PDF dossier |
| [`reference/source_chats/`](reference/source_chats/) | The original planning material this was built from |

## Key documents

| Document | Read it for |
|---|---|
| [**Project dossier (PDF)**](docs/AquaSync_Project_Dossier.pdf) | The complete 15-page case: problem, method, results, BOM, limitations, pitch |
| [**ICFOSS analysis (PDF)**](docs/AquaSync_ICFOSS_Analysis.pdf) | What Kerala's open-source institute has already built, which fourteen of their projects AquaSync can stand on, and what goes back |
| [PROGRESS.md](PROGRESS.md) | Live status of every component |
| [ROADMAP.md](ROADMAP.md) | What is next, and what is deliberately *not* being built |
| [ACTION_PLAN.md](ACTION_PLAN.md) | The next fourteen days |
| [docs/architecture.md](docs/architecture.md) | How the five models fit together and why each was chosen |
| [docs/data-sources.md](docs/data-sources.md) | Every data source, verified — including two corrections to the brief |
| [hardware/bom/](hardware/bom/README.md) | Components, specs, costs, and two wiring traps |

## Two things worth knowing before you trust anything here

**The dataset does not contain 2018 data.** This project was planned around
`amith-vp/Kerala-Dam-Water-Levels` as the source of "exactly the 2018 Idukki
data you need". Its historical files begin on **13 August 2020**. The flagship
case study is therefore October 2021 — fully covered, complete, and a better
demonstration. The 2018 flood remains the reason anyone cares, but no
quantitative claim depends on it.

**About 11% of that dataset is corrupt.** Rows between 2020-09-25 and
2021-04-30 report live storage above the reservoir's physical capacity and
storage percentages over 1,000%. Fitting the level–storage curve on the raw
feed gives r² = 0.784; on validated rows, r² = 0.996. The corrupt block alone
displaces the curve by more than the flood cushion being modelled.

```python
from aquasync.io import load_dam
print(load_dam("Idukki").quality_report())
```

Both are documented in full in [docs/data-sources.md](docs/data-sources.md).

## Results

| | |
|---|---|
| Level–storage calibration | β = 1.348, **r² = 0.9957**, MAE 17 Mm³ (n = 1,836) |
| October 2021 replay | **0.30 m** mean error, 0.57 m max, over 20 days |
| Flood cushion gained | **about 3 m** |
| Revenue effect | **+₹4–10 crore** — positive, via time-of-day shifting |
| Optimiser's chosen target level | **728.43 m** vs KSEB's published rule level of **728.50 m** |

That last line is the one to notice. Given only the physics and the
objective, the optimiser independently rediscovered the operating rule that
already exists, to within 7 cm. The recommendation is not "change the rule" —
the rule is already right. What is missing is a system that acts on it against
a forecast, early enough that acting is cheap.

### The honest caveat

The counterfactual assumes **perfect foresight** of inflow. Real forecasts are
wrong, so every benefit figure above is an **upper bound**. Closing that gap
is the top open item in [ROADMAP.md](ROADMAP.md), and it should be done before
these numbers are presented anywhere that matters.

## Design commitments

- **Advisory, permanently.** The system never operates a gate. A named officer
  approves every release. The scale rig does close the loop onto a servo,
  because it is a 30 cm acrylic tank — and that distinction gets said out loud.
- **Every number regenerates.** No figure is hand-entered. If the upstream
  data changes, the figures and the dossier change with it.
- **Offline-capable.** Tide prediction, the twin, and the dashboard all run
  with no network. A tool that only works when the internet is up is not a
  disaster-management tool.
- **Simulation core has no framework dependencies.** `twin/` imports nothing
  from `api/`. That is what makes it testable.

## Licence

MIT for the code. Data belongs to its sources — see
[docs/data-sources.md](docs/data-sources.md) before redistributing anything
under `data/`.
