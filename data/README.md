# Data

| Directory | Contents | Committed? |
|---|---|---|
| `raw/` | Third-party snapshots (KSEB dam JSON, DEM tiles) | **No** — re-fetch with `scripts/fetch_data.py` |
| `processed/` | Derived results the dossier quotes — replays, the lead-time study, ten forecast-error runs, the cascade, routing and runoff results, `figure_facts.json` | **Yes** |
| `external/` | Large downloads: DEM tiles, SAR scenes | **No** |
| `reference/` | Small static lookups checked in by hand | Yes |

`processed/` is committed on purpose. The upstream feed changes daily and
could disappear; committed derived artefacts mean a number quoted in the
report can still be checked next year. `scripts/check.py` regenerates every
figure and document and fails if anything here is stale.

**Before using anything in `raw/`, read
[../docs/data-sources.md](../docs/data-sources.md).** Roughly 11% of the
Idukki and Idamalayar records are physically impossible, and some other dams
in the same feed are far worse — Chenkulam is 41% invalid. The loader flags
these; it does not silently drop them.

```bash
python scripts/fetch_data.py --all      # fetch + print the quality report
```

**Run everything from the repository root.** The `.gitignore` rule is
`data/raw/`, which is anchored to the root. A script run with a relative
`data/raw` default from inside `backend/` writes to `backend/data/raw/`,
which is *not* ignored — there is one such stray file on disk as of
31 August 2026, and `git add -A` would commit it.
