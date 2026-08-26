# Data

| Directory | Contents | Committed? |
|---|---|---|
| `raw/` | Third-party snapshots (KSEB dam JSON) | **No** — re-fetch with `scripts/fetch_data.py` |
| `processed/` | Derived results the dossier quotes | **Yes** |
| `external/` | Large downloads: DEM tiles, SAR scenes | **No** |
| `reference/` | Small static lookups checked in by hand | Yes |

`processed/` is committed on purpose. The upstream feed changes daily and
could disappear; committed derived artefacts mean a number quoted in the
report can still be checked next year.

**Before using anything in `raw/`, read
[../docs/data-sources.md](../docs/data-sources.md).** Roughly 11% of the
Idukki and Idamalayar records are physically impossible, and some other dams
in the same feed are far worse — Chenkulam is 41% invalid. The loader flags
these; it does not silently drop them.

```bash
python scripts/fetch_data.py --all      # fetch + print the quality report
```
