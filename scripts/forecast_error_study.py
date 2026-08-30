"""Forecast-error study - closes the perfect-foresight gap (ROADMAP.md item 1).

Every benefit number elsewhere in this project (lead_time_study.py, the
dossier) hands the optimiser the ACTUAL observed inflow for the whole
horizon, including hours that have not happened yet at decision time. That
is an upper bound, not an operational result. This script produces the
honest number: given only a 30-member NOAA GEFS rainfall ensemble issued
before the storm, how much of that benefit survives once you (a) forecast
rainfall with real error, (b) push it through the SCS-CN + Muskingum chain
instead of reading the answer off the KSEB bulletin, (c) commit to ONE
policy chosen under that uncertainty, and (d) get scored against what
actually happened.

Method (matches ROADMAP.md item 1):

1. Fetch GEFS members gep01-gep30, issued at ``--issue-date --hh``, out to
   ``--horizon-h``, via idx-indexed S3 byte-range GETs (~270 KB/file).
   APCP resets every 6h; the 3h and 6h marks are differenced to recover a
   3-hourly rainfall series - the finest this product offers.
2. Bias-correct the ensemble by a single multiplicative factor: IMD RF25
   gridded-rainfall storm total over the Idukki box, divided by the GEFS
   ensemble-mean storm total over the same box and window. This is a
   single-event correction, not a trained one - it removes this storm's
   mean bias, nothing more, and is reported as such.
3. Push each member's rainfall through RainfallRunoffModel (SCS-CN +
   triangular unit hydrograph) to get 30 inflow trajectories, splicing onto
   OBSERVED inflow before the issue time so pre-issue skill is not credited
   to the forecast.
4. Run the existing exhaustive DrawdownPolicy search once per member,
   giving 30 candidate policies. Score every candidate against every
   member's inflow (a 30x30 cross-matrix of ScheduleEvaluation.total_cost)
   and pick the candidate with the lowest MEAN cost across members - the
   "expected value" decision rule. (CVaR / minimax regret are documented
   alternatives; the choice changes the answer, which is why it is named.)
5. Score the chosen policy against the REAL observed inflow. Compare its
   freeboard gain to the perfect-foresight freeboard gain at the same
   window (the number lead_time_study.py already reports) to get the
   fraction of benefit retained.

Requires ``eccodes`` and ``netCDF4`` (installed for this run;
``pip install eccodes cfgrib netCDF4`` to reproduce) and the IMD RF25 2021
grid already fetched by ``scripts/acquire.py`` (acquire_imd_rf25).

Usage:
    python scripts/forecast_error_study.py
    python scripts/forecast_error_study.py --issue-date 2021-10-15 --hh 12 --horizon-h 96
    python scripts/forecast_error_study.py --workers 20 --out data/processed
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace as dc_replace
from pathlib import Path

import eccodes
import netCDF4 as nc
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from aquasync.twin import (  # noqa: E402
    IDUKKI,
    REACHES,
    LevelStorageCurve,
    ObjectiveWeights,
    OperationalLimits,
    ReleaseOptimizer,
    ReservoirState,
)
from aquasync.twin.runoff import (  # noqa: E402
    DEFAULT_CN_IDUKKI,
    RainfallRunoffModel,
    UnitHydrograph,
)
from aquasync.twin.scenarios import SCENARIOS, load_scenario_series  # noqa: E402

GEFS_BUCKET = "https://noaa-gefs-pds.s3.amazonaws.com"
UA = "Mozilla/5.0 (compatible; AquaSync-research/0.1)"
MEMBERS = [f"gep{n:02d}" for n in range(1, 31)]

# Shared 0.25 deg box bracketing the Idukki catchment, used identically for
# GEFS and IMD RF25 so forecast and truth are sampled the same way.
IDUKKI_LATS = [9.5, 9.75, 10.0]
IDUKKI_LONS = [76.75, 77.0, 77.25]

# Idukki catchment geometry for the unit hydrograph. area_km2 stays at the
# CAG-sourced 650.0 (Appendix 3.1); main_channel_km and slope were an
# order-of-magnitude guess (35 km, 3.6%) until scripts/catchment_geometry.py
# replaced them with an actual watershed delineation off a public 30 m DEM:
# 66.3 km and 0.87%, net of the Mullaperiyar Dam's upstream trans-basin
# diversion (its own delineated catchment, 560.7 km2, subtracted from the
# naive Idukki figure - a DEM cannot see the diversion tunnel to the Vaigai
# basin, Tamil Nadu, only topography). That net area (570.3 km2) landing
# within 12% of the CAG figure, using nothing but elevation data and two
# dam coordinates, is what makes these channel numbers trustworthy enough
# to use. Full method and numbers: data/processed/catchment_geometry_idukki.json.
#
# This ~2x longer, ~4x gentler channel implies a materially longer
# catchment concentration time via Kirpich (~6.8 h vs the old guess's
# ~2.7 h) than the 24/90/120h forecast-error results already published in
# ROADMAP.md and docs/validation.md were run with - those predate this fix
# and have not been re-run against it.
CATCHMENT_AREA_KM2 = 650.0
CATCHMENT_MAIN_CHANNEL_KM = 66.3
CATCHMENT_SLOPE = 0.0087

CACHE_ROOT = ROOT / "research" / "raw" / "gefs_hindcast"
IMD_NC = ROOT / "research" / "raw" / "imd_rf25" / "ind2021_rfp25.nc"


# --------------------------------------------------------------------------
# GEFS fetch + decode
# --------------------------------------------------------------------------

def _gefs_idx_url(issue_date: str, hh: str, member: str, lead_h: int) -> str:
    return (f"{GEFS_BUCKET}/gefs.{issue_date.replace('-', '')}/{hh}/atmos/"
            f"pgrb2sp25/{member}.t{hh}z.pgrb2s.0p25.f{lead_h:03d}.idx")


def _gefs_file_url(issue_date: str, hh: str, member: str, lead_h: int) -> str:
    return (f"{GEFS_BUCKET}/gefs.{issue_date.replace('-', '')}/{hh}/atmos/"
            f"pgrb2sp25/{member}.t{hh}z.pgrb2s.0p25.f{lead_h:03d}")


def fetch_apcp_slice(issue_date: str, hh: str, member: str, lead_h: int) -> Path:
    """Byte-range GET of just the APCP GRIB2 message, cached to disk."""
    out_dir = CACHE_ROOT / f"{issue_date}_{hh}z" / member
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"f{lead_h:03d}.grib2"
    if out.exists() and out.stat().st_size > 0:
        return out

    idx_req = urllib.request.Request(_gefs_idx_url(issue_date, hh, member, lead_h),
                                      headers={"User-Agent": UA})
    with urllib.request.urlopen(idx_req, timeout=30) as r:
        lines = [ln for ln in r.read().decode().splitlines() if ln.strip()]
    entries = [ln.split(":") for ln in lines]
    apcp_idx = next(i for i, e in enumerate(entries) if e[3] == "APCP")
    start = int(entries[apcp_idx][1])
    end = int(entries[apcp_idx + 1][1]) - 1 if apcp_idx + 1 < len(entries) else start + 400_000

    file_req = urllib.request.Request(
        _gefs_file_url(issue_date, hh, member, lead_h),
        headers={"User-Agent": UA, "Range": f"bytes={start}-{end}"},
    )
    with urllib.request.urlopen(file_req, timeout=60) as r:
        data = r.read()
    if not data.startswith(b"GRIB"):
        raise ValueError(f"not a GRIB message: {member} f{lead_h:03d} ({len(data)} bytes)")
    out.write_bytes(data)
    return out


def decode_apcp_box_mean(grib_path: Path) -> float:
    """Mean APCP (mm) over the Idukki grid box for one GRIB2 message."""
    with open(grib_path, "rb") as f:
        gid = eccodes.codes_grib_new_from_file(f)
        try:
            lats = np.asarray(eccodes.codes_get_array(gid, "latitudes"))
            lons = np.asarray(eccodes.codes_get_array(gid, "longitudes"))
            vals = np.asarray(eccodes.codes_get_array(gid, "values"))
        finally:
            eccodes.codes_release(gid)
    mask = np.zeros(lats.shape, dtype=bool)
    for la in IDUKKI_LATS:
        for lo in IDUKKI_LONS:
            mask[int(np.argmin((lats - la) ** 2 + (lons - lo) ** 2))] = True
    return float(vals[mask].mean())


def fetch_all_members(
    issue_date: str, hh: str, horizon_h: int, workers: int,
) -> dict[str, np.ndarray]:
    """3-hourly rainfall (mm) per member, shape (horizon_h // 3,)."""
    marks = list(range(3, horizon_h + 1, 3))
    jobs = [(m, h) for m in MEMBERS for h in marks]

    print(f"fetching {len(jobs)} GEFS slices ({len(MEMBERS)} members x {len(marks)} lead hours)...")
    paths: dict[tuple[str, int], Path] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fetch_apcp_slice, issue_date, hh, m, h): (m, h) for m, h in jobs}
        done = 0
        for fut in as_completed(futs):
            m, h = futs[fut]
            paths[(m, h)] = fut.result()
            done += 1
            if done % 200 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)} fetched")

    result: dict[str, np.ndarray] = {}
    for m in MEMBERS:
        vals = {h: decode_apcp_box_mean(paths[(m, h)]) for h in marks}
        rain = np.zeros(len(marks))
        for i, h in enumerate(marks):
            rain[i] = vals[h] if h % 6 == 3 else max(0.0, vals[h] - vals[h - 3])
        result[m] = rain
    return result


# --------------------------------------------------------------------------
# IMD RF25 truth field (bias correction + antecedent moisture)
# --------------------------------------------------------------------------

def imd_daily_box_mean(nc_path: Path) -> pd.Series:
    """Daily Idukki-box mean rainfall (mm) for the whole year, indexed by date."""
    d = nc.Dataset(nc_path)
    lat = np.asarray(d.variables["LATITUDE"][:])
    lon = np.asarray(d.variables["LONGITUDE"][:])
    t = d.variables["TIME"]
    raw_times = nc.num2date(t[:], t.units, only_use_cftime_datetimes=False)
    times = pd.to_datetime([str(x) for x in raw_times])
    lat_mask = np.isin(lat.round(2), IDUKKI_LATS)
    lon_mask = np.isin(lon.round(2), IDUKKI_LONS)
    rain = np.asarray(d.variables["RAINFALL"][:])[:, lat_mask][:, :, lon_mask]
    return pd.Series(rain.mean(axis=(1, 2)), index=times)


def bias_factor(imd_daily: pd.Series, member_rain_3h: dict[str, np.ndarray],
                 issue_dt: pd.Timestamp, horizon_h: int) -> float:
    obs_total = float(imd_daily.loc[issue_dt: issue_dt + pd.Timedelta(hours=horizon_h)].sum())
    ens_mean_total = float(np.mean([r.sum() for r in member_rain_3h.values()]))
    if ens_mean_total <= 0:
        return 1.0
    return obs_total / ens_mean_total


def antecedent_5day_mm(imd_daily: pd.Series, issue_dt: pd.Timestamp) -> float:
    window = imd_daily.loc[issue_dt - pd.Timedelta(days=5): issue_dt - pd.Timedelta(hours=1)]
    return float(window.sum())


# --------------------------------------------------------------------------
# Inflow construction
# --------------------------------------------------------------------------

def build_member_inflow(
    observed_hourly: pd.DataFrame,
    issue_dt: pd.Timestamp,
    rain_3h_mm: np.ndarray,
    bias: float,
    antecedent_mm: float,
) -> np.ndarray:
    """Observed inflow before issue_dt, model-derived inflow after it."""
    dates = observed_hourly["date"]
    inflow = observed_hourly["inflow_cumecs"].to_numpy(dtype=float).copy()
    post_mask = (dates >= issue_dt).to_numpy()
    n_post = int(post_mask.sum())
    if n_post == 0:
        return inflow

    hourly_rain = np.repeat(rain_3h_mm * bias / 3.0, 3)
    if len(hourly_rain) < n_post:
        hourly_rain = np.pad(hourly_rain, (0, n_post - len(hourly_rain)))
    hourly_rain = hourly_rain[:n_post]

    pre_idx = np.where(~post_mask)[0]
    baseflow = float(inflow[pre_idx[-1]]) if len(pre_idx) else float(inflow[0])

    uh = UnitHydrograph.from_catchment(
        CATCHMENT_AREA_KM2, CATCHMENT_MAIN_CHANNEL_KM, CATCHMENT_SLOPE,
    )
    rrm = RainfallRunoffModel(CATCHMENT_AREA_KM2, DEFAULT_CN_IDUKKI, uh, baseflow_cumecs=baseflow)
    forecast_inflow = rrm.inflow_series(
        hourly_rain, dt_hours=1.0, antecedent_rain_mm=antecedent_mm, growing_season=True,
    )
    inflow[post_mask] = forecast_inflow[:n_post]
    return inflow


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--issue-date", default="2021-10-13")
    ap.add_argument("--hh", default="00", choices=["00", "06", "12", "18"])
    ap.add_argument("--horizon-h", type=int, default=168)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--cache-dir", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "processed")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    if not IMD_NC.exists():
        print(f"missing {IMD_NC} - run: python scripts/acquire.py", file=sys.stderr)
        return 1

    issue_dt = pd.Timestamp(f"{args.issue_date} {args.hh}:00:00")
    window_end = issue_dt + pd.Timedelta(hours=args.horizon_h)

    # Truncate the scenario to [scenario.start, issue + horizon] so BOTH the
    # perfect-foresight baseline and the forecast-driven runs are scored
    # over the identical window. Using the untruncated default scenario end
    # (2021-10-28) here would silently need rainfall for days the GEFS fetch
    # never covered - the first version of this script zero-padded that gap,
    # which fabricated an 8-day near-zero-inflow tail against an observed
    # 130-240 cumecs and biased every policy ranking that used it.
    base_scenario = SCENARIOS["periyar_oct_2021"]
    scenario = dc_replace(base_scenario, end=str(window_end))
    series = load_scenario_series(scenario, cache_dir=args.cache_dir, hourly=True)

    lead_hours_before_storm = (pd.Timestamp("2021-10-16 18:00") - issue_dt).total_seconds() / 3600.0
    print(f"issue: {issue_dt} UTC  ({lead_hours_before_storm:.0f} h before the 17 Oct storm peak)")
    print(f"horizon: {args.horizon_h} h -> window [{scenario.start}, {window_end}]")

    member_rain = fetch_all_members(args.issue_date, args.hh, args.horizon_h, args.workers)

    imd_daily = imd_daily_box_mean(IMD_NC)
    bias = bias_factor(imd_daily, member_rain, issue_dt, args.horizon_h)
    antecedent = antecedent_5day_mm(imd_daily, issue_dt)
    print(f"bias factor (IMD storm total / GEFS ensemble-mean storm total): {bias:.3f}")
    print(f"5-day antecedent rainfall before issue: {antecedent:.1f} mm")

    res, reach = IDUKKI, REACHES["periyar_lower"]
    curve = LevelStorageCurve(res)
    start_level = float(series["water_level_m"].iloc[0])
    initial = ReservoirState(level=start_level, storage=curve.storage_from_level(start_level))

    observed_release = (
        series["powerhouse_cumecs"].fillna(0).to_numpy(dtype=float)
        + series["spillway_cumecs"].fillna(0).to_numpy(dtype=float)
    )
    observed_inflow = series["inflow_cumecs"].to_numpy(dtype=float)
    observed_turbine_mean = float(np.minimum(observed_release, res.turbine_rated_flow).mean())

    limits = OperationalLimits(
        max_release_cumecs=1500.0, max_ramp_cumecs_per_hour=60.0,
        max_level=res.frl, max_mean_turbine_cumecs=observed_turbine_mean,
    )
    opt = ReleaseOptimizer(
        res, reach, weights=ObjectiveWeights.monsoon_peak(), limits=limits, seed=7,
    )

    observed_eval = opt.evaluate(observed_release, initial, observed_inflow)
    perfect_best, _ = opt.search_policies(initial, observed_inflow)
    perfect_freeboard_gain = observed_eval.peak_level - perfect_best.peak_level
    print(f"\nperfect-foresight freeboard gain at this window: {perfect_freeboard_gain:.2f} m")

    print(f"\nsearching a policy per member ({len(MEMBERS)} exhaustive grid searches)...")
    member_inflow: dict[str, np.ndarray] = {}
    candidates: dict[str, object] = {}
    for i, m in enumerate(MEMBERS, 1):
        inflow_m = build_member_inflow(series, issue_dt, member_rain[m], bias, antecedent)
        member_inflow[m] = inflow_m
        _, policy_m = opt.search_policies(initial, inflow_m)
        candidates[m] = policy_m
        if i % 10 == 0 or i == len(MEMBERS):
            print(f"  {i}/{len(MEMBERS)} member policies found")

    print(f"\nscoring the {len(MEMBERS)}x{len(MEMBERS)} candidate-vs-member cross-matrix...")
    scores = pd.DataFrame(index=MEMBERS, columns=MEMBERS, dtype=float)
    for cand_m, policy in candidates.items():
        for eval_m, inflow_n in member_inflow.items():
            release = opt.policy_schedule(initial, inflow_n, policy)
            ev = opt.evaluate(release, initial, inflow_n)
            scores.loc[cand_m, eval_m] = ev.total_cost

    expected_cost = scores.mean(axis=1)
    worst_case_cost = scores.max(axis=1)
    chosen_expected = expected_cost.idxmin()
    chosen_minimax = worst_case_cost.idxmin()

    def score_policy_on_truth(policy) -> dict:
        release = opt.policy_schedule(initial, observed_inflow, policy)
        ev = opt.evaluate(release, initial, observed_inflow)
        gain = observed_eval.peak_level - ev.peak_level
        pf_cost = float(perfect_best.total_cost)
        return {
            "peak_level_m": float(ev.peak_level),
            "freeboard_gained_m": float(gain),
            "retention_of_perfect_foresight_pct":
                float(gain / perfect_freeboard_gain * 100) if perfect_freeboard_gain else None,
            "revenue_delta_cr": float((ev.revenue_inr - observed_eval.revenue_inr) / 1e7),
            # The measure that can actually be read as "how much worse was
            # deciding under uncertainty": the optimiser's own objective,
            # scored against what really happened. Zero means the forecast
            # picked the hindsight-optimal policy; positive is always worse.
            "total_cost": float(ev.total_cost),
            "excess_cost_vs_perfect_foresight_pct":
                float((ev.total_cost - pf_cost) / abs(pf_cost) * 100) if pf_cost else None,
        }

    result = {
        "issue_date": args.issue_date, "hh": args.hh, "horizon_h": args.horizon_h,
        "lead_hours_before_storm_peak": round(lead_hours_before_storm, 1),
        "bias_factor": round(bias, 4),
        "antecedent_5day_mm": round(antecedent, 1),
        "catchment_geometry": {
            "area_km2": CATCHMENT_AREA_KM2, "main_channel_km": CATCHMENT_MAIN_CHANNEL_KM,
            "slope": CATCHMENT_SLOPE,
            "caveat": "area is sourced (CAG Appendix 3.1); channel length and slope are "
                      "from scripts/catchment_geometry.py's DEM watershed delineation, "
                      "net of the Mullaperiyar diversion (see that script's docstring)",
        },
        "perfect_foresight": {
            "freeboard_gained_m": round(perfect_freeboard_gain, 3),
            "peak_level_m": round(float(perfect_best.peak_level), 3),
            "total_cost": float(perfect_best.total_cost),
            "revenue_delta_cr":
                float((perfect_best.revenue_inr - observed_eval.revenue_inr) / 1e7),
        },
        "metric_note":
            "retention_of_perfect_foresight_pct can exceed 100% and that does NOT mean "
            "the forecast beat hindsight. It scores freeboard alone, one axis of a "
            "four-part objective (flood, dam safety, revenue, gate wear). A policy built "
            "on an over-forecast releases too much, ends lower than the hindsight optimum "
            "and scores above 100% while giving up revenue to do it. Read "
            "excess_cost_vs_perfect_foresight_pct instead: it is the optimiser's own "
            "objective, it is zero when the forecast picked the hindsight-optimal policy, "
            "and it is never negative.",
        "observed": {
            "peak_level_m": round(float(observed_eval.peak_level), 3),
            "revenue_cr": round(float(observed_eval.revenue_inr / 1e7), 1),
        },
        "decision_rule_expected_value": {
            "chosen_member": chosen_expected,
            **score_policy_on_truth(candidates[chosen_expected]),
        },
        "decision_rule_minimax_regret": {
            "chosen_member": chosen_minimax,
            **score_policy_on_truth(candidates[chosen_minimax]),
        },
        "ensemble_spread": {
            "freeboard_gain_if_policy_matched_verifying_member_m":
                [round(float(observed_eval.peak_level - opt.evaluate(
                    opt.policy_schedule(initial, member_inflow[m], candidates[m]),
                    initial, member_inflow[m]).peak_level), 3) for m in MEMBERS],
        },
    }

    out_json = args.out / f"forecast_error_study_{args.issue_date}_{args.hh}z.json"
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    scores.to_csv(args.out / f"forecast_error_cross_matrix_{args.issue_date}_{args.hh}z.csv")

    print(f"\n=== RESULT ({lead_hours_before_storm:.0f} h lead) ===")
    print(f"perfect-foresight freeboard gain:  {perfect_freeboard_gain:.2f} m")
    ev = result["decision_rule_expected_value"]
    print(f"forecast-driven (expected-value):  {ev['freeboard_gained_m']:.2f} m  "
          f"({ev['retention_of_perfect_foresight_pct']:.0f}% retained)"
          if ev["retention_of_perfect_foresight_pct"] is not None else "n/a")
    mm = result["decision_rule_minimax_regret"]
    print(f"forecast-driven (minimax regret):  {mm['freeboard_gained_m']:.2f} m  "
          f"({mm['retention_of_perfect_foresight_pct']:.0f}% retained)"
          if mm["retention_of_perfect_foresight_pct"] is not None else "n/a")
    print(f"\nwritten -> {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
