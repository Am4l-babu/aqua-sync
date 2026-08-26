# Data sources

Everything AquaSync runs on is free and public. This document records what
each source actually contains — as opposed to what it is commonly claimed to
contain — because two widely repeated assumptions turned out to be wrong when
checked against the live files.

**Verification date: 26 August 2026.** Re-verify before quoting any figure
here in a submission.

---

## Corrections to the original project brief

Both of these were carried forward from the planning conversations in
[`reference/source_chats/`](../reference/source_chats/). Both are wrong.

### 1. The Kerala dam dataset does not contain 2018 data

The brief identified `amith-vp/Kerala-Dam-Water-Levels` as the source of
"exactly the 2018 Idukki dam data you need to validate your model."

It is not. The historical files begin on **13 August 2020**.

```
$ python -c "from aquasync.io import load_dam; r=load_dam('Idukki'); \
    print(r.frame.date.min(), r.frame.date.max())"
2020-08-13 00:00:00 2026-08-26 00:00:00
```

There is no 2018 record in the repository at all. Any demo built on a "2018
replay" using this source would have failed on contact with the data — and
would have failed publicly, in front of judges, at the worst possible moment.

**What we did instead:** moved the flagship case study to **October 2021**,
which is fully covered, complete in every field, and is a *better* case
(see [validation.md](validation.md)). The 2018 flood remains the narrative
framing — it is why anyone cares — but no quantitative claim depends on it.

**If you still want 2018 data**, the real acquisition routes are:

| Route | What you get | Effort |
|---|---|---|
| India-WRIS / National Water Data Portal (`nwdp.nwic.gov.in`) | CWC daily reservoir levels, 2018 included | API registration; data is daily, not sub-daily |
| KSDMA formal data request | Official Idukki/Idamalayar 2018 operation log | Written request, weeks of lead time |
| Published literature | Digitised 2018 Idukki inflow/outflow hydrographs | Free, immediate, but second-hand — cite the paper |
| CWC Flood Forecasting (`ffs.india-water.gov.in`) | Gauge records at Periyar stations | Coverage for 2018 is patchy |

For the literature route, the standard reference is the *Current Science*
analysis of the role of dams in the August 2018 Periyar floods, which
publishes the reservoir operation curves directly. Digitising a published
figure is legitimate provided it is cited as such.

### 2. About 11% of the dataset is corrupt, in one contiguous block

Rows between **2020-09-25 and 2021-04-30** report physically impossible
values: live storage above the stated capacity at FRL, and storage
percentages over 1,000%.

```
2020-09-25   level 727.69   live storage 1736.139 Mm3   storage 1199.3%
             (stated capacity at FRL: 1459.49 Mm3)
```

The flow columns in the same block are equally wrong — sustained four-figure
"inflow" through the dry season with zero rainfall is not a daily mean
discharge. The signature is consistent with a column-alignment bug in the
upstream scraper against an older bulletin layout. A few isolated rows
elsewhere (2025-06-04) show the same thing.

This matters more than it sounds. Fitting the reservoir level–storage curve
on the raw feed versus the validated subset:

| | raw feed | validated rows |
|---|---|---|
| fitted beta | 1.302 | **1.348** |
| r² | 0.784 | **0.996** |
| MAE | 174 Mm3 | **17 Mm3** |

The corrupt block alone shifts the storage curve by more than the entire
flood cushion being modelled. Anyone using this dataset without validation is
building on sand.

`aquasync.io.kseb_dataset` flags every such row in a `quality_ok` column and
exposes `.clean()` and `.quality_report()`. It flags rather than drops,
because a scenario that silently loses a third of its window is more
dangerous than one that complains.

#### It is not uniform across dams

Running the validator over all 18 reservoirs (`python scripts/fetch_data.py
--all`) shows the corruption rate varies enormously. Check your dam before
trusting it:

| Dam | Invalid rows | Dam | Invalid rows |
|---|---|---|---|
| Chenkulam | **41.3%** | Moozhiyar | 2.1% |
| Banasura Sagar | **36.8%** | Ponmudi | 1.3% |
| Idukki | 10.7% | Pambla | 0.7% |
| Anathode | 10.5% | Kallar | 0.6% |
| Idamalayar | 10.5% | Pamba | 0.5% |
| Sholayar | 8.4% | Kallarkutty | 0.4% |
| Anayirankal | 8.1% | Poringalkuthu | 0.2% |
| | | Erattayar, Kundala, Mattupetty | < 0.1% |
| | | Kakkayam | 0.0% |

Two further coverage notes: **Banasura Sagar** starts 2021-01-23 and
**Kakkayam** starts 2021-08-08, both later than the rest. Every dam has two
unparseable dates.

For the Periyar work this is tolerable — Idukki and Idamalayar lose about a
tenth of their rows, all in one contiguous early block, well outside the
October 2021 study window. Anyone extending this to Chenkulam or Banasura
Sagar needs a different plan.

---

## Primary sources

### Reservoir telemetry — KSEB / KSDMA daily bulletin

- **Repository:** <https://github.com/amith-vp/Kerala-Dam-Water-Levels>
- **Dashboard:** <https://dams.keralam.co/>
- **Live:** `https://raw.githubusercontent.com/amith-vp/Kerala-Dam-Water-Levels/main/live.json`
- **Historical:** `…/main/historic_data/{Dam}.json`
- **Licence:** derived from public government bulletins; check the repo before redistributing.

18 KSEB reservoirs plus a separate irrigation set, updated daily by GitHub
Actions. Per-dam static metadata (FRL, MWL, rule level, KSDMA blue/orange/red
alert levels, live storage at FRL, coordinates, district) plus a daily series
of level, live storage, storage percentage, inflow, powerhouse discharge,
spillway release, total outflow, rainfall and free-text remarks.

Available dams:
`Anathode, Anayirankal, Banasura_Sagar, Chenkulam, Erattayar, Idamalayar,
Idukki, Kakkayam, Kallar, Kallarkutty, Kundala, Mattupetty, Moozhiyar, Pamba,
Pambla, Ponmudi, Poringalkuthu, Sholayar`

**Known issues, all handled in the loader:**

| Issue | Handling |
|---|---|
| Date formats vary (`26.08.2026`, `07-12-2025`) | `parse_date` tries known formats |
| A few dates are corrupt (`09.04.2.23`) | returned as `None`, row dropped, counted |
| Numbers arrive as strings with unit suffixes | `parse_number` strips and coerces |
| Empty strings in flow fields | become `None`, not `0.0` |
| Corrupt 2020-09 → 2021-04 block | `quality_ok = False` |
| Missing days (19 Oct 2021 absent) | interpolated, flagged |
| **Daily resolution only** | see below |

**The resolution limit is the single biggest constraint on the project.**
The bulletin is one reading per day. The twin runs hourly, so daily values
are linearly interpolated. Two consequences, which must be stated whenever a
number from this pipeline is quoted:

- Reported peak inflows are **lower bounds** on the true instantaneous peak.
- Any claim about the **timing** of a peak carries roughly ±12 hours.

Sub-daily data requires the CWC 15-minute telemetry feed. That is the single
highest-value upgrade to the data layer and it is on the roadmap.

### Rainfall

| Source | Coverage | Use |
|---|---|---|
| Bulletin `rainfall` field | Daily, at the dam | Already aligned with the reservoir series; use this first |
| IMD gridded rainfall (0.25°) | 1901–present, daily | Catchment-average rainfall, long-record calibration |
| IMD district daily | All 14 Kerala districts | Cross-check |
| Open-Meteo / OpenWeatherMap | Forecast, free tier | Live 72–120 h forecast for the operational mode |
| `kerala.csv` (1901–2018, monthly + flood flag) | Long record | Climatology only — monthly resolution is useless for flood routing |

### Tides

- **INCOIS** — <https://incois.gov.in/> — official predictions for Kochi. Free
  for Indian academic use; requires registration.
- **Offline fallback** — `aquasync.twin.tide` carries harmonic constituents
  for Kochi (M2, S2, K1, O1, N2) and predicts without network access. This is
  what keeps the expo demo running when the venue Wi-Fi does not.

Cochin is microtidal: spring range is about 1 m. On a river already at
bankfull, 1 m decides whether a town floods.

### Terrain

| Source | Resolution | Notes |
|---|---|---|
| ISRO Bhuvan CartoDEM | 10–30 m | Best for Kerala; registration required |
| SRTM 30 m | 30 m | Global, immediate, no registration |
| Copernicus DEM GLO-30 | 30 m | Better vertical accuracy than SRTM |

### Satellite flood extent — Sentinel-1 SAR

Kerala is fully overcast during the monsoon, so optical imagery is useless
exactly when it is needed. Sentinel-1 C-band SAR penetrates cloud.

- **Google Earth Engine** — `COPERNICUS/S1_GRD`, free for research
- **Copernicus Data Space** — <https://dataspace.copernicus.eu/>
- Revisit is ~6–12 days, so SAR validates *extent*, never *timing*.

A caution on the widely-copied approach of thresholding VV backscatter at a
fixed value to detect water: the threshold is scene-dependent. Use Otsu or a
histogram split per scene, and always difference against a pre-flood
baseline composite rather than classifying a single image.

### Administrative boundaries

- **OpenData Kerala** — <https://github.com/opendatakerala/lsg-kerala-data> —
  ward and panchayat boundaries as GeoJSON, with Wikidata IDs.
- **OpenStreetMap** — road network for evacuation routing, building
  footprints for exposure counts.

---

## Sources that were checked and rejected

Recorded so the same ground is not covered twice.

| Source | Why not |
|---|---|
| Kaggle "Kerala Floods 2018" | District casualty and rainfall totals only. No reservoir telemetry — cannot validate a routing model. Useful for impact framing. |
| `kerala.csv` (1901–2018) | Monthly rainfall with a boolean flood flag. Far too coarse for flood routing; suited to long-run climatology. |
| Google Flood Forecasting API | Genuinely excellent, but it is a *forecast product*, not raw data. Using it as ground truth for our own forecast would be circular. Good as a benchmark to compare against. |
| CWC daily reservoir bulletin (national) | Real and useful, but for Kerala dams it is the same underlying data as the KSEB bulletin with more friction. |
| RTC-Tools | Deltares reservoir optimisation framework, genuinely used in industry. Rejected for now: heavyweight, needs a CasADi/IPOPT toolchain, and the optimisation here is small enough that a transparent local search is both sufficient and far easier to defend in a five-minute Q&A. Revisit if the problem grows to a multi-reservoir cascade with hard constraints. |

---

## Reproducing the raw cache

```bash
python scripts/fetch_data.py --dams Idukki Idamalayar --refresh
python scripts/lead_time_study.py
```

Cached JSON lands in `data/raw/` and is **not** committed — it is a
third-party snapshot that changes daily. `data/processed/` holds derived
artefacts that *are* committed, so results stay reproducible even if the
upstream feed changes or disappears.
