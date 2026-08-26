# Notebooks

Exploratory work. **Nothing here is load-bearing** — every result quoted in
the dossier is produced by a script in [`scripts/`](../scripts/), not by a
notebook, so that it can be regenerated and diffed.

Suggested order if you are picking the project up:

| Notebook | Purpose |
|---|---|
| `01_explore_data.ipynb` | Load the KSEB feed, look at the quality report, find the corrupt block yourself |
| `02_calibrate_reservoir.ipynb` | Fit the level–storage curve, reproduce r² = 0.996 |
| `03_counterfactual.ipynb` | Replay October 2021 and vary the objective weights |
| `04_forecast_error.ipynb` | **The open question.** Degrade the inflow forecast and measure what survives |

Run from the repo root so `sys.path` picks up `backend/`:

```python
import sys; sys.path.insert(0, "../backend")
from aquasync.io import load_dam
print(load_dam("Idukki", cache_dir="../data/raw").quality_report())
```
