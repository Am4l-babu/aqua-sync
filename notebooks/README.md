# Notebooks

Exploratory work. **Nothing here is load-bearing** — every result quoted in
the dossier is produced by a script in [`scripts/`](../scripts/), not by a
notebook, so that it can be regenerated and diffed.

None of the notebooks below exist yet. This is the suggested order for
someone picking the project up who wants to *see* the data before trusting
the scripts that summarise it.

| Notebook | Purpose | The script that owns the answer |
|---|---|---|
| `01_explore_data.ipynb` | Load the KSEB feed, print the quality report, find the corrupt 2020-09 → 2021-04 block yourself | `scripts/fetch_data.py --all` |
| `02_calibrate_reservoir.ipynb` | Fit the level–storage curve; reproduce β = 1.348, r² = 0.996 | `scripts/make_figures.py` (Figure 3) |
| `03_counterfactual.ipynb` | Replay October 2021 and vary the objective weights; watch the target level stay near 728.43 m | `scripts/lead_time_study.py` |
| `04_forecast_error.ipynb` | **Closed at the script level, open for exploration.** Ten runs across two storms are in `data/processed/forecast_error_study_*.json`. Plot both curves; do not average them — one ramps, one cliffs | `scripts/forecast_error_study.py` |
| `05_runoff_recession.ipynb` | The chain has no recession limb (NSE 0.07 on amplitude). Sketch a continuous soil-moisture store against the 722 scored days before anyone builds one | `scripts/runoff_validation.py` |

Run from the repo root so `sys.path` picks up `backend/`:

```python
import sys; sys.path.insert(0, "../backend")
from aquasync.io import load_dam
print(load_dam("Idukki", cache_dir="../data/raw").quality_report())
```

If a notebook finds something worth keeping, it becomes a script in
`scripts/` with its output in `data/processed/`, and a line in
[`docs/validation.md`](../docs/validation.md). That is the only route from
"interesting" to "quoted".
