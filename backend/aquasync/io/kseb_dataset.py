"""Loader for the Kerala dam daily bulletin dataset.

Source: https://github.com/amith-vp/Kerala-Dam-Water-Levels (scraped daily
from the KSEB / KSDMA dam bulletin, published as JSON via GitHub Actions).

Read docs/data-sources.md before trusting any field from this feed. The
short version, verified against the live files:

* Coverage starts in **August 2020**, not 2018. There is no 2018 flood data
  in this repository. Any plan that depends on a "2018 replay" needs a
  different source - see docs/data-sources.md for the acquisition route.
* Dates appear in several formats and a handful are corrupt
  (e.g. ``09.04.2.23``). ``parse_date`` handles the known variants and
  returns ``None`` rather than guessing.
* Numeric fields arrive as strings, sometimes with unit suffixes, sometimes
  with a stray ``%``, sometimes empty.
* Rows between **2020-09-25 and 2021-04-30** are corrupt: reported live
  storage exceeds the physical capacity at FRL (1,736 Mm3 against a stated
  1,459 Mm3 maximum) and storage percentage reads 1,199%. The flow columns
  in the same block are equally wrong - sustained four-figure dry-season
  "inflow" with zero rainfall is not a daily mean discharge. This looks like
  a column-alignment bug in the upstream scraper against an older bulletin
  layout. A handful of isolated rows elsewhere (e.g. 2025-06-04) show the
  same signature.

``load_dam`` marks every such row in a ``quality_ok`` column rather than
dropping it silently, because a scenario that quietly loses a third of its
window is far more dangerous than one that says so. Call ``.clean()`` to
get only the trustworthy rows.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pandas as pd

RAW_BASE = "https://raw.githubusercontent.com/amith-vp/Kerala-Dam-Water-Levels/main"
LIVE_URL = f"{RAW_BASE}/live.json"
HISTORIC_URL = f"{RAW_BASE}/historic_data/{{dam}}.json"

# Flow columns are unreliable before this date; see module docstring.
FLOW_TRUSTED_FROM = date(2021, 6, 1)

DATE_FORMATS = ("%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d")


def parse_date(raw: str) -> date | None:
    """Parse a bulletin date string, returning None if it is unrecoverable."""
    if not raw:
        return None
    s = str(raw).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_number(raw) -> float | None:
    """Parse a bulletin numeric field, stripping units and stray symbols."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s in {"-", "--", "NA", "N/A"}:
        return None
    for junk in ("m3/s", "m³/s", "cumecs", "MCM", "Mm3", "mm", "%", "m", ","):
        s = s.replace(junk, "")
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        return None


def _validate(frame: pd.DataFrame, capacity_mm3: float, frl_m: float) -> pd.Series:
    """Physical-plausibility mask over bulletin rows.

    A row fails if it asserts something the reservoir cannot do: more live
    storage than it physically holds, a storage percentage outside 0-101,
    or a water level above the maximum water level. A 1% tolerance absorbs
    routine bulletin rounding.
    """
    ok = pd.Series(True, index=frame.index)

    storage = pd.to_numeric(frame.get("live_storage_mm3"), errors="coerce")
    pct = pd.to_numeric(frame.get("storage_pct"), errors="coerce")
    level = pd.to_numeric(frame.get("water_level_m"), errors="coerce")

    ok &= ~(storage > capacity_mm3 * 1.02).fillna(False)
    ok &= ~((pct > 101.0) | (pct < -0.5)).fillna(False)
    ok &= ~(level > frl_m + 1.0).fillna(False)
    ok &= ~(storage < 0).fillna(False)
    return ok


@dataclass
class DamRecord:
    """A dam plus its parsed daily time series."""

    key: str
    name: str
    official_name: str
    district: str
    latitude: float
    longitude: float
    frl: float
    mwl: float
    rule_level: float | None
    red_level: float | None
    orange_level: float | None
    blue_level: float | None
    live_storage_at_frl: float
    frame: pd.DataFrame
    dropped_rows: int

    def window(self, start: str, end: str, clean_only: bool = False) -> pd.DataFrame:
        """Rows between two ISO dates, inclusive, sorted ascending."""
        f = self.clean() if clean_only else self.frame
        mask = (f["date"] >= pd.Timestamp(start)) & (f["date"] <= pd.Timestamp(end))
        return f.loc[mask].sort_values("date").reset_index(drop=True)

    def clean(self) -> pd.DataFrame:
        """Only the rows that survive the physical-plausibility checks."""
        return self.frame[self.frame["quality_ok"]].reset_index(drop=True)

    def quality_report(self) -> dict:
        """Counts and date ranges of the rows that failed validation.

        Worth printing at the top of any notebook. The corrupt block is
        large enough that silently including it would shift a fitted
        level-storage curve by more than the flood cushion being modelled.
        """
        bad = self.frame[~self.frame["quality_ok"]]
        return {
            "total_rows": int(len(self.frame)),
            "unparseable_dates_dropped": int(self.dropped_rows),
            "failed_validation": int(len(bad)),
            "failed_pct": round(100.0 * len(bad) / max(1, len(self.frame)), 2),
            "bad_range": (
                (str(bad["date"].min().date()), str(bad["date"].max().date()))
                if len(bad)
                else None
            ),
            "usable_range": (
                (str(self.clean()["date"].min().date()), str(self.clean()["date"].max().date()))
                if len(self.clean())
                else None
            ),
        }


def fetch_json(url: str, cache_path: Path | None = None, refresh: bool = False) -> dict:
    """Fetch JSON, caching to disk so the demo works without a network."""
    if cache_path and cache_path.exists() and not refresh:
        return json.loads(cache_path.read_text(encoding="utf-8"))

    with urllib.request.urlopen(url, timeout=60) as resp:
        payload = resp.read().decode("utf-8")

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(payload, encoding="utf-8")
    return json.loads(payload)


def load_dam(
    dam: str = "Idukki",
    cache_dir: Path | str = "data/raw",
    refresh: bool = False,
) -> DamRecord:
    """Load one dam's full historical record into a tidy DataFrame."""
    cache_dir = Path(cache_dir)
    payload = fetch_json(
        HISTORIC_URL.format(dam=dam),
        cache_path=cache_dir / f"{dam}.json",
        refresh=refresh,
    )

    rows, dropped = [], 0
    for entry in payload.get("data", []):
        d = parse_date(entry.get("date", ""))
        if d is None:
            dropped += 1
            continue
        rows.append(
            {
                "date": pd.Timestamp(d),
                "water_level_m": parse_number(entry.get("waterLevel")),
                "live_storage_mm3": parse_number(entry.get("liveStorage")),
                "storage_pct": parse_number(entry.get("storagePercentage")),
                "inflow_cumecs": parse_number(entry.get("inflow")),
                "powerhouse_cumecs": parse_number(entry.get("powerHouseDischarge")),
                "spillway_cumecs": parse_number(entry.get("spillwayRelease")),
                "total_outflow_cumecs": parse_number(entry.get("totalOutflow")),
                "rainfall_mm": parse_number(entry.get("rainfall")),
                "remarks": (entry.get("remarks") or "").strip(),
            }
        )

    frame = (
        pd.DataFrame(rows)
        .drop_duplicates(subset="date", keep="first")
        .sort_values("date")
        .reset_index(drop=True)
    )

    capacity = parse_number(payload.get("liveStorageAtFRL")) or float("inf")
    frl = parse_number(payload.get("FRL")) or float("inf")
    frame["quality_ok"] = _validate(frame, capacity, frl)

    return DamRecord(
        key=dam.lower(),
        name=payload.get("name", dam),
        official_name=payload.get("officialName", dam),
        district=payload.get("district", ""),
        latitude=float(payload.get("latitude") or 0.0),
        longitude=float(payload.get("longitude") or 0.0),
        frl=parse_number(payload.get("FRL")) or 0.0,
        mwl=parse_number(payload.get("MWL")) or 0.0,
        rule_level=parse_number(payload.get("ruleLevel")),
        red_level=parse_number(payload.get("redLevel")),
        orange_level=parse_number(payload.get("orangeLevel")),
        blue_level=parse_number(payload.get("blueLevel")),
        live_storage_at_frl=parse_number(payload.get("liveStorageAtFRL")) or 0.0,
        frame=frame,
        dropped_rows=dropped,
    )


def load_live(cache_dir: Path | str = "data/raw", refresh: bool = True) -> pd.DataFrame:
    """Today's bulletin for every dam in the feed."""
    payload = fetch_json(
        LIVE_URL, cache_path=Path(cache_dir) / "live.json", refresh=refresh
    )
    rows = []
    for dam in payload.get("dams", []):
        latest = (dam.get("data") or [{}])[0]
        rows.append(
            {
                "name": dam.get("name"),
                "district": dam.get("district"),
                "latitude": dam.get("latitude"),
                "longitude": dam.get("longitude"),
                "frl_m": parse_number(dam.get("FRL")),
                "rule_level_m": parse_number(dam.get("ruleLevel")),
                "red_level_m": parse_number(dam.get("redLevel")),
                "water_level_m": parse_number(latest.get("waterLevel")),
                "storage_pct": parse_number(latest.get("storagePercentage")),
                "spillway_cumecs": parse_number(latest.get("spillwayRelease")),
                "rainfall_mm": parse_number(latest.get("rainfall")),
                "remarks": (latest.get("remarks") or "").strip(),
                "as_of": payload.get("lastUpdate"),
            }
        )
    return pd.DataFrame(rows)


def daily_to_hourly(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Interpolate daily bulletin rows to an hourly grid.

    The bulletin is a single daily reading; the twin runs hourly. Linear
    interpolation between daily values is an assumption, not data, and it
    smooths away exactly the sub-daily peak the flood is made of.

    Two consequences worth stating plainly rather than hiding:
      * Reported peak inflows are lower bounds on the true instantaneous peak.
      * Any claim about the *timing* of a peak carries at best +/- 12 hours.

    Sub-daily resolution needs the CWC 15-minute telemetry feed, which is the
    upgrade path documented in docs/data-sources.md.
    """
    f = frame.set_index("date").sort_index()
    hourly = f[columns].resample("1h").interpolate("linear")
    hourly = hourly.reset_index()
    hourly["interpolated"] = True
    return hourly
