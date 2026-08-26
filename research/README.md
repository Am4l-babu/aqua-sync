# Research

Everything the deep-research sweep found, verified, and downloaded.

Start with **[`index/README.md`](index/README.md)** — the browsable inventory of
what is on disk — or read the full
**[deep research report](../docs/AquaSync_Research_Report.pdf)**.

## Layout

| Path | Contents | In git? |
|---|---|---|
| `index/README.md` | Browsable inventory, regenerated from the acquisition log | yes |
| `index/manifest.json` | What to fetch, and how | yes |
| `index/acquisition_log.json` | What was actually fetched, with sizes and failures | yes |
| `index/research_findings.json` | Full verified findings from all six domains | yes |
| `raw/` | Per-domain findings as JSON, one file each | yes |
| `repos/` | Snapshots of relevant open-source projects | **no** — bulk, re-fetchable |
| `sources/papers/` | Downloadable papers and reports | selectively |
| `sources/datasets/` | Data files | **no** — bulk, re-fetchable |

Bulk directories are gitignored deliberately: they are hundreds of megabytes
of third-party code that changes upstream anyway. The manifest and the log
*are* committed, so anyone can reproduce the exact collection:

```bash
python scripts/acquire.py                 # fetch the whole manifest
python scripts/acquire.py --priority high # just the important ones
python scripts/acquire.py --index-only    # rebuild the index without fetching
```

## How the research was done

Thirteen agents in three phases:

1. **Research** — six agents, one per domain, each running many distinct web
   searches and reading primary sources.
2. **Verify** — six adversarial agents that re-checked every URL independently
   and rejected anything they could not confirm.
3. **Synthesize** — one agent producing integration paths, prioritised
   upgrades, and the evidence *against* the project's thesis.

Every URL was checked with an actual HTTP request and its real status code
recorded. This was not ceremony. The planning material this project grew out
of contained one Amazon ASIN presented as five different products, and
described a dataset as containing 2018 flood data that it does not contain.
Both errors survived because nobody checked.

Sites that return 403 or 503 to automated requests but work fine for a human
(Robu.in, Amazon, several publishers) are marked as bot-blocked and confirmed
by another route, rather than being wrongly discarded.

## A note on the repo snapshots

`repos/` holds **reference snapshots**, extracted from GitHub tarballs rather
than cloned. There is no `.git` directory inside any of them.

Two reasons, both Windows-specific:

1. Some repos ship filenames that are illegal on NTFS. `NOAA-OWP/t-route`
   includes USGS timeslice files named `2023-04-02_23:30:00...ncdf` — a colon —
   which aborts a git checkout entirely and leaves an empty directory. `tar`
   skips those entries and extracts the other 1,150 files.
2. Deleting `.git` on Windows regularly fails on locked pack files, leaving
   half-removed stubs behind.

To contribute upstream, clone the project properly from its own URL.
