"""Named scenarios - the reproducible case studies the demo is built on.

The flagship is **October 2021**, not 2018. That is a deliberate correction
to the original project brief and the reason is worth stating clearly:

The Kerala-Dam-Water-Levels dataset that the brief identified as the source
of "2018 Idukki data" actually begins in **August 2020**. It contains no
2018 record at all. Building the headline demo on data that does not exist
is the kind of thing that collapses under the first question from a judge
who knows the domain.

October 2021 is a better case anyway, and it is fully documented in free,
publicly downloadable data:

  * 16 Oct 2021: Idukki sits at 728.80 m - already *above* its 728.50 m
    rule level - with the spillway shut.
  * 17 Oct 2021: 168 mm of rain. Inflow jumps from 116 to 879 cumecs, a
    7.6x step in 24 hours. Level climbs 1.3 m in a single day. Spillway
    still shut.
  * 20 Oct 2021: only now do the gates open, at 83.8 cumecs, with the
    reservoir at 731.0 m - 1.4 m from FRL.
  * Idamalayar does the same thing on the same days and opens on the *same
    day*, 20 Oct, at 128.1 cumecs.

So the two reservoirs that jointly control the Periyar both absorbed the
storm into their freeboard, then released together into an already-swollen
river. That is the coordination failure the twin exists to prevent, and
every number above is checkable from a public URL.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from ..io.kseb_dataset import daily_to_hourly, load_dam
from .constants import IDAMALAYAR, IDUKKI, REACHES, Reach, Reservoir
from .optimizer import (
    ObjectiveWeights,
    OperationalLimits,
    ReleaseOptimizer,
    summarise_improvement,
)
from .reservoir import LevelStorageCurve, ReservoirState


@dataclass
class Scenario:
    """A reproducible historical episode the twin is replayed against."""

    key: str
    title: str
    reservoir: Reservoir
    reach: Reach
    start: str
    end: str
    narrative: str
    citation: str


SCENARIOS: dict[str, Scenario] = {
    "periyar_oct_2021": Scenario(
        key="periyar_oct_2021",
        title="Periyar cascade, October 2021",
        reservoir=IDUKKI,
        reach=REACHES["periyar_lower"],
        start="2021-10-08",
        end="2021-10-28",
        narrative=(
            "Idukki entered a 168 mm rain day already above its rule level with "
            "gates shut, absorbed a 7.6x inflow surge into freeboard, and opened "
            "the spillway three days later at 731.0 m - the same day Idamalayar "
            "opened its own gates into the same river."
        ),
        citation="KSEB daily dam bulletin via amith-vp/Kerala-Dam-Water-Levels",
    ),
    "idukki_dec_2021": Scenario(
        key="idukki_dec_2021",
        title="Idukki riding FRL, Nov-Dec 2021",
        reservoir=IDUKKI,
        reach=REACHES["periyar_lower"],
        start="2021-11-20",
        end="2021-12-15",
        narrative=(
            "Idukki held between 731.6 and 732.0 m for three weeks - inside "
            "0.5 m of FRL - with essentially no flood cushion left, purely to "
            "protect end-of-year generation."
        ),
        citation="KSEB daily dam bulletin via amith-vp/Kerala-Dam-Water-Levels",
    ),
    "idukki_aug_2022": Scenario(
        key="idukki_aug_2022",
        title="Idukki monsoon spill, August 2022",
        reservoir=IDUKKI,
        reach=REACHES["periyar_lower"],
        start="2022-08-01",
        end="2022-08-20",
        narrative=(
            "A cleaner, smaller monsoon episode with a genuine multi-day "
            "spillway release. Useful as an out-of-sample validation case "
            "once the model has been calibrated on October 2021."
        ),
        citation="KSEB daily dam bulletin via amith-vp/Kerala-Dam-Water-Levels",
    ),
}


def load_scenario_series(
    scenario: Scenario,
    cache_dir: Path | str = "data/raw",
    hourly: bool = True,
) -> pd.DataFrame:
    """Fetch and prepare the observed series for a scenario window."""
    record = load_dam(scenario.reservoir.name, cache_dir=cache_dir)
    frame = record.window(scenario.start, scenario.end)

    cols = [
        "water_level_m",
        "live_storage_mm3",
        "inflow_cumecs",
        "powerhouse_cumecs",
        "spillway_cumecs",
        "rainfall_mm",
    ]
    frame = frame.copy()
    for c in cols:
        frame[c] = pd.to_numeric(frame[c], errors="coerce")
    # A missing bulletin day (19 Oct 2021 is absent) must be filled, or the
    # hourly grid silently shifts the flood peak by a day.
    frame[cols] = frame[cols].interpolate(limit_direction="both")

    if not hourly:
        return frame

    out = daily_to_hourly(frame, cols)
    # Rainfall is a daily total; spreading it evenly is wrong but bounded.
    out["rainfall_mm"] = out["rainfall_mm"] / 24.0
    return out


def run_counterfactual(
    scenario_key: str = "periyar_oct_2021",
    cache_dir: Path | str = "data/raw",
    weights: ObjectiveWeights | None = None,
    method: str = "policy",
    seed: int = 7,
) -> dict:
    """Replay a scenario, then re-run it under an optimised release policy.

    Forecast lead time is the honest lever, and sweeping it is the single
    most persuasive sensitivity study in the project - that lives in
    scripts/lead_time_study.py rather than here, because it needs to be
    reproducible from the command line.
    """
    scenario = SCENARIOS[scenario_key]
    series = load_scenario_series(scenario, cache_dir=cache_dir, hourly=True)

    inflow = series["inflow_cumecs"].to_numpy(dtype=float)
    observed_level = series["water_level_m"].to_numpy(dtype=float)
    observed_release = (
        series["powerhouse_cumecs"].fillna(0).to_numpy(dtype=float)
        + series["spillway_cumecs"].fillna(0).to_numpy(dtype=float)
    )

    res = scenario.reservoir
    curve = LevelStorageCurve(res)
    initial = ReservoirState(
        level=float(observed_level[0]),
        storage=curve.storage_from_level(float(observed_level[0])),
    )

    limits = OperationalLimits(
        max_release_cumecs=1500.0,
        max_ramp_cumecs_per_hour=60.0,
        max_level=res.frl,
    )
    opt = ReleaseOptimizer(
        res,
        scenario.reach,
        weights=weights or ObjectiveWeights.monsoon_peak(),
        limits=limits,
        seed=seed,
    )

    observed_eval = opt.evaluate(observed_release, initial, inflow)
    result = opt.compare(initial, inflow, method=method)
    result["observed"] = observed_eval

    summary = summarise_improvement(observed_eval, result["optimised"], reservoir=res)
    summary["scenario"] = scenario.key
    summary["title"] = scenario.title
    summary["narrative"] = scenario.narrative
    summary["citation"] = scenario.citation
    summary["hours_simulated"] = int(len(inflow))
    summary["observed_peak_level"] = float(np.nanmax(observed_level))
    # Model validation: how closely the twin reproduces the observed level
    # when fed the observed releases. This is the number that earns the
    # right to make any counterfactual claim at all.
    sim_level = observed_eval.levels
    resid = sim_level - observed_level
    summary["replay_level_mae_m"] = float(np.nanmean(np.abs(resid)))
    summary["replay_level_max_err_m"] = float(np.nanmax(np.abs(resid)))
    summary["replay_final_err_m"] = float(resid[-1])
    summary["frl"] = res.frl
    summary["rule_level"] = res.rule_level

    return {"scenario": scenario, "series": series, "evaluations": result, "summary": summary}


def cascade_summary(cache_dir: Path | str = "data/raw") -> pd.DataFrame:
    """Idukki and Idamalayar side by side across the October 2021 event.

    Produces the table behind the central claim: both dams above rule level
    going in, both opening gates on 20 October, into the same river.
    """
    frames = []
    for res in (IDUKKI, IDAMALAYAR):
        rec = load_dam(res.name, cache_dir=cache_dir)
        w = rec.window("2021-10-12", "2021-10-25")[
            ["date", "water_level_m", "inflow_cumecs", "spillway_cumecs", "rainfall_mm"]
        ].copy()
        w["dam"] = res.name
        w["rule_level_m"] = res.rule_level
        w["frl_m"] = res.frl
        w["above_rule"] = w["water_level_m"] > res.rule_level
        frames.append(w)

    combined = pd.concat(frames, ignore_index=True)
    return combined.sort_values(["date", "dam"]).reset_index(drop=True)
