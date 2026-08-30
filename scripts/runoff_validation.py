"""Runoff validation - does the SCS-CN chain reproduce observed inflow?

The last unvalidated link in the twin. `docs/validation.md` §4 has carried the
note "the SCS-CN chain is implemented and unit-tested for volume conservation,
but has never been compared against observed inflow ... it does gate any
genuinely forward-looking forecast" since the model was written. The
forecast-error study IS a forward-looking forecast - it pushes GEFS ensemble
rainfall through this chain - so its headline retention figures inherit
whatever error lives here.

Method:

1. The KSEB bulletin publishes daily rainfall AND daily inflow for the same
   reservoir, so the comparison needs no new data. Monsoon seasons (1 Jun -
   30 Nov) with near-complete clean coverage are used: 2021-2025 in full,
   2026 partial. 2020 is excluded - it is more than half inside the known
   corrupt block.
2. Each day's rainfall is spread uniformly across 24 hours and pushed through
   `RainfallRunoffModel` at an hourly step (the same way the forecast-error
   study drives it), then the predicted hourly inflow is averaged back to a
   daily mean so it is comparable with the bulletin's daily figure.
3. Scored three ways: the model exactly as it ships (handbook CN, no
   baseflow), with a per-season baseflow constant, and with the curve number
   calibrated.
4. The calibrated number is then re-scored **leave-one-season-out** - fit on
   four seasons, test on the fifth - because a curve number fitted and
   reported on the same data says nothing about whether it generalises. That
   is the same fitted-vs-validated distinction §2b draws for the replay.

What this can and cannot settle is in the "caveats" block of the JSON and in
docs/validation.md - in short, bulletin rainfall is a station reading at the
dam rather than a catchment areal mean, and bulletin inflow is itself derived
from a reservoir mass balance rather than gauged. This is a comparison of two
estimates, not of a model against truth.

    python scripts/runoff_validation.py
    python scripts/runoff_validation.py --dam Idukki --out data/processed
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from aquasync.io import load_dam  # noqa: E402
from aquasync.twin import IDUKKI  # noqa: E402
from aquasync.twin.runoff import (  # noqa: E402
    DEFAULT_CN_IDUKKI,
    RainfallRunoffModel,
    UnitHydrograph,
)

RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
GEOM = PROC / "catchment_geometry_idukki.json"

SEASON_START = (6, 1)
SEASON_END = (11, 30)
MIN_CLEAN_FRACTION = 0.95
CN_GRID = np.arange(50.0, 96.0, 1.0)


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------

def season_frame(record, year: int) -> pd.DataFrame | None:
    """One monsoon season of paired rainfall and inflow, or None if too gappy."""
    start = pd.Timestamp(year, *SEASON_START)
    end = pd.Timestamp(year, *SEASON_END)
    w = record.window(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")).copy()
    if w.empty:
        return None

    w = w.set_index("date").asfreq("D").reset_index()
    for c in ("rainfall_mm", "inflow_cumecs"):
        w[c] = pd.to_numeric(w[c], errors="coerce")

    # A row the validation layer rejected is not evidence either way.
    if "quality_ok" in w.columns:
        # object dtype in the feed, so coerce before negating
        rejected = ~w["quality_ok"].fillna(False).astype(bool)
        w.loc[rejected, "inflow_cumecs"] = np.nan

    clean = w.inflow_cumecs.notna() & w.rainfall_mm.notna()
    if clean.mean() < MIN_CLEAN_FRACTION:
        return None

    # Short gaps are interpolated so the convolution sees a continuous series;
    # the scoring mask below still excludes them.
    w["scored"] = clean
    w["rainfall_mm"] = w.rainfall_mm.interpolate().fillna(0.0)
    w["inflow_cumecs"] = w.inflow_cumecs.interpolate()
    return w


def antecedent_before(record, year: int) -> float:
    """5-day rainfall depth immediately before the season opens."""
    start = pd.Timestamp(year, *SEASON_START)
    prior = record.window(
        (start - pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
        (start - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
    )
    if prior.empty:
        return 0.0
    return float(pd.to_numeric(prior.rainfall_mm, errors="coerce").fillna(0.0).sum())


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------

def geometry() -> tuple[float, float, float]:
    """Area, main channel length, slope - DEM-derived where available."""
    area = IDUKKI.catchment_area_km2
    if GEOM.exists():
        g = json.loads(GEOM.read_text(encoding="utf-8"))
        return area, float(g["main_channel_km"]), float(g["channel_slope"])
    return area, 35.0, 0.036


def predict_daily(rain_daily_mm: np.ndarray, cn: float, antecedent_mm: float,
                  baseflow: float = 0.0) -> np.ndarray:
    """Daily-mean predicted inflow, run internally at an hourly step."""
    area, channel_km, slope = geometry()
    uh = UnitHydrograph.from_catchment(area, channel_km, slope)
    rrm = RainfallRunoffModel(area, cn, uh, baseflow_cumecs=baseflow)

    hourly_rain = np.repeat(np.asarray(rain_daily_mm, dtype=float) / 24.0, 24)
    hourly_q = rrm.inflow_series(
        hourly_rain, dt_hours=1.0, antecedent_rain_mm=antecedent_mm, growing_season=True,
    )
    return hourly_q.reshape(-1, 24).mean(axis=1)


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------

def metrics(obs: np.ndarray, pred: np.ndarray) -> dict:
    obs = np.asarray(obs, dtype=float)
    pred = np.asarray(pred, dtype=float)
    resid = pred - obs
    denom = ((obs - obs.mean()) ** 2).sum()
    return {
        "n_days": int(obs.size),
        "nse": float(1.0 - (resid ** 2).sum() / denom) if denom > 0 else float("nan"),
        "r2": float(np.corrcoef(obs, pred)[0, 1] ** 2) if obs.size > 2 else float("nan"),
        "pbias_pct": float(100.0 * resid.sum() / obs.sum()) if obs.sum() else float("nan"),
        "mae_cumecs": float(np.abs(resid).mean()),
        "rmse_cumecs": float(np.sqrt((resid ** 2).mean())),
        "volume_ratio": float(pred.sum() / obs.sum()) if obs.sum() else float("nan"),
        "mean_observed_cumecs": float(obs.mean()),
        "mean_predicted_cumecs": float(pred.mean()),
    }


def pooled(seasons: dict, cn: float, use_baseflow: bool) -> tuple[np.ndarray, np.ndarray]:
    obs_all, pred_all = [], []
    for s in seasons.values():
        bf = s["baseflow"] if use_baseflow else 0.0
        pred = predict_daily(s["frame"].rainfall_mm.to_numpy(), cn, s["antecedent"], bf)
        m = s["frame"].scored.to_numpy()
        obs_all.append(s["frame"].inflow_cumecs.to_numpy()[m])
        pred_all.append(pred[m])
    return np.concatenate(obs_all), np.concatenate(pred_all)


def best_cn(seasons: dict, use_baseflow: bool = False) -> tuple[float, float]:
    """Curve number maximising pooled NSE over the given seasons."""
    scores = []
    for cn in CN_GRID:
        obs, pred = pooled(seasons, float(cn), use_baseflow)
        scores.append(metrics(obs, pred)["nse"])
    i = int(np.nanargmax(scores))
    return float(CN_GRID[i]), float(scores[i])


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dam", default="Idukki")
    ap.add_argument("--out", default=str(PROC))
    args = ap.parse_args()

    record = load_dam(args.dam, cache_dir=RAW)
    area, channel_km, slope = geometry()
    print(f"{args.dam}: {area:.0f} km2, channel {channel_km:.1f} km, slope {slope:.4f}")
    print(f"unit hydrograph time to peak: "
          f"{UnitHydrograph.from_catchment(area, channel_km, slope).time_to_peak_h:.1f} h\n")

    seasons: dict[int, dict] = {}
    for year in range(2020, 2027):
        f = season_frame(record, year)
        if f is None:
            print(f"  {year}: skipped (coverage below {MIN_CLEAN_FRACTION:.0%})")
            continue
        obs = f.inflow_cumecs.to_numpy()[f.scored.to_numpy()]
        seasons[year] = {
            "frame": f,
            "antecedent": antecedent_before(record, year),
            # A per-season constant standing in for baseflow and any other
            # inflow the rainfall-runoff chain does not generate.
            "baseflow": float(np.percentile(obs, 10)),
        }
        print(f"  {year}: {int(f.scored.sum())} scored days, "
              f"baseflow proxy {seasons[year]['baseflow']:.1f} cumecs")

    if len(seasons) < 3:
        print("\nnot enough clean seasons to validate against")
        return 1

    results: dict = {}

    # 1 - the model exactly as it ships
    obs, pred = pooled(seasons, DEFAULT_CN_IDUKKI, use_baseflow=False)
    results["as_shipped"] = metrics(obs, pred)
    print(f"\nas shipped (CN {DEFAULT_CN_IDUKKI:.0f}, no baseflow): "
          f"NSE {results['as_shipped']['nse']:.2f}, "
          f"bias {results['as_shipped']['pbias_pct']:+.0f}%")

    # 2 - same curve number, with the baseflow the chain cannot generate
    obs, pred = pooled(seasons, DEFAULT_CN_IDUKKI, use_baseflow=True)
    results["handbook_cn_with_baseflow"] = metrics(obs, pred)
    print(f"+ baseflow: NSE {results['handbook_cn_with_baseflow']['nse']:.2f}, "
          f"bias {results['handbook_cn_with_baseflow']['pbias_pct']:+.0f}%")

    # 3 - calibrated on everything (reported, but see 4). Fitted against the
    # configuration that ships: direct runoff alone already carries the volume,
    # so the baseflow term double-counts rather than filling a gap.
    cn_fit, nse_fit = best_cn(seasons)
    obs, pred = pooled(seasons, cn_fit, use_baseflow=False)
    results["calibrated_in_sample"] = {"curve_number": cn_fit, **metrics(obs, pred)}
    print(f"calibrated CN {cn_fit:.0f} (fitted on all seasons): NSE {nse_fit:.2f}")

    # 4 - the number that actually means something
    loo = {}
    for held in seasons:
        others = {y: s for y, s in seasons.items() if y != held}
        cn_o, _ = best_cn(others)
        obs_h, pred_h = pooled({held: seasons[held]}, cn_o, use_baseflow=False)
        loo[str(held)] = {"fitted_cn_excluding_this_season": cn_o, **metrics(obs_h, pred_h)}
        print(f"  hold out {held}: CN {cn_o:.0f} from the others -> "
              f"NSE {loo[str(held)]['nse']:.2f}, bias {loo[str(held)]['pbias_pct']:+.0f}%")
    results["leave_one_season_out"] = loo

    nses = [v["nse"] for v in loo.values()]
    results["loo_summary"] = {
        "mean_nse": float(np.mean(nses)),
        "worst_nse": float(np.min(nses)),
        "cn_spread": sorted({v["fitted_cn_excluding_this_season"] for v in loo.values()}),
    }

    results["setup"] = {
        "dam": args.dam,
        "seasons": sorted(seasons),
        "season_window": "1 Jun - 30 Nov",
        "handbook_cn": DEFAULT_CN_IDUKKI,
        "catchment": {"area_km2": area, "main_channel_km": channel_km, "slope": slope},
        "caveats": [
            "Bulletin rainfall is a station reading at the dam, not a catchment areal "
            "mean. In steep orographic terrain the catchment mean is usually the larger "
            "number, so a positive-bias result may be the rain gauge, not the model.",
            "Bulletin inflow is itself derived by KSEB from a reservoir mass balance, "
            "not gauged. This compares two estimates, not a model against truth.",
            "Each day's rainfall is spread uniformly over 24 hours; the bulletin does "
            "not publish sub-daily rainfall, so storm intensity within a day is lost.",
            "Baseflow is a per-season constant (10th percentile of observed inflow), "
            "standing in for every inflow the rainfall-runoff chain does not generate.",
        ],
    }

    out = Path(args.out) / f"runoff_validation_{args.dam.lower()}.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    # Per-day series, so the figure is drawn from the same run that produced
    # the metrics rather than recomputing them.
    rows = []
    for year, sea in seasons.items():
        f = sea["frame"]
        pred = predict_daily(f.rainfall_mm.to_numpy(), DEFAULT_CN_IDUKKI, sea["antecedent"])
        rows.append(pd.DataFrame({
            "date": f.date, "season": year, "scored": f.scored,
            "rainfall_mm": f.rainfall_mm,
            "observed_cumecs": f.inflow_cumecs, "predicted_cumecs": pred,
        }))
    series = Path(args.out) / f"runoff_validation_{args.dam.lower()}_series.csv"
    pd.concat(rows).to_csv(series, index=False)
    print(f"written -> {series}")
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
