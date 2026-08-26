# Research index

Everything the deep-research sweep found, acquired and verified.
Regenerate with `python scripts/acquire.py --index-only`.

**14 acquired** (561.0 MB) · **0 need manual registration** · **0 unavailable**

Last run: 2026-08-26 12:59 UTC

---

## Acquired

| Resource | Kind | Local path | Size | Source |
|---|---|---|---|---|
| Kerala-Dam-Water-Levels | dataset | `research/repos/Kerala-Dam-Water-Levels` | 15.4 MB | [link](https://github.com/amith-vp/Kerala-Dam-Water-Levels) |
| NOAA-t-route | repo | `research/repos/t-route` | 81.7 MB | [link](https://github.com/NOAA-OWP/t-route) |
| google-flood-forecasting | repo | `research/repos/google-flood-forecasting` | 140.1 MB | [link](https://github.com/google-research/flood-forecasting) |
| idukki-live-bulletin | dataset | `research/sources/datasets/kerala_dams_live.json` | 16.9 KB | [link](https://raw.githubusercontent.com/amith-vp/Kerala-Dam-Water-Levels/main/live.json) |
| neuralhydrology | repo | `research/repos/neuralhydrology` | 22.9 MB | [link](https://github.com/neuralhydrology/neuralhydrology) |
| opendatakerala-lsg-boundaries | dataset | `research/repos/lsg-kerala-data` | 30.2 MB | [link](https://github.com/opendatakerala/lsg-kerala-data) |
| rtc-tools | repo | `research/repos/rtc-tools` | 6.5 MB | [link](https://github.com/rtc-tools/rtc-tools) |
| LFPtools | repo | `research/repos/LFPtools` | 24.0 MB | [link](https://github.com/jsosa/LFPtools) |
| pastas | repo | `research/repos/pastas` | 164.0 MB | [link](https://github.com/pastas/pastas) |
| AI4Water | repo | `research/repos/AI4Water` | 26.3 MB | [link](https://github.com/AtrCheema/AI4Water) |
| Sentinel1-Flood-Finder | repo | `research/repos/Sentinel1-Flood-Finder` | 42.9 MB | [link](https://github.com/cordmaur/Sentinel1-Flood-Finder) |
| dMC-Juniata-hydroDL2 | repo | `research/repos/dMC-Juniata` | 159.6 KB | [link](https://github.com/mhpi/dMC-Juniata-hydroDL2) |
| pyflwdir | repo | `research/repos/pyflwdir` | 2.4 MB | [link](https://github.com/Deltares/pyflwdir) |
| pywr | repo | `research/repos/pywr` | 4.3 MB | [link](https://github.com/pywr/pywr) |

---

## Layout

```
research/
  index/        this index, the manifest, and the acquisition log
  raw/          per-dimension research findings as JSON
  repos/        shallow snapshots of relevant open-source projects
  sources/
    papers/     downloadable papers and reports
    datasets/   data files small enough to keep in the repo
```

`.git` directories are stripped from cloned snapshots - these are
reference copies, not working checkouts. To contribute upstream, clone
the project properly from its own URL.
