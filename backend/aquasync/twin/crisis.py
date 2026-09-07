"""Crisis Commander - hand the operator the decision, then score what they did.

Every other output of this project explains the system. This one makes someone
*use* it: you are the duty engineer at Idukki, the window opens on 8 October
2021 with the reservoir at 727.72 m, and the 168 mm that defines the episode
falls on the 17th. What do you release, starting when, and how fast?

Nine days of runway is not a contrivance - it is what the operators actually
had. The record shows the gates opening on the 20th, three days after the
rain.

The point is not the game. It is that the trade-off stops being an argument
and becomes something the player feels: hold water and the level runs at the
spillway; dump it early and you spill through the turbines' capacity and burn
revenue that the tariff would have paid you for. Nearly everyone plays it too
late the first time, which is exactly what the historical record did.

Scored against the inflow that actually happened, using the same optimiser and
the same objective as everything else in the project - so the player's number,
the historical number and AquaSync's number are directly comparable.

No web dependencies here on purpose: `aquasync.twin` has to stay importable
with no framework installed, and CI enforces that.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from .constants import Reservoir
from .optimizer import (
    DrawdownPolicy,
    ObjectiveWeights,
    OperationalLimits,
    ReleaseOptimizer,
)
from .reservoir import LevelStorageCurve, ReservoirState
from .scenarios import SCENARIOS, load_scenario_series

MAX_RELEASE_CUMECS = 1500.0
MAX_RAMP_CUMECS_PER_HOUR = 60.0


@dataclass(frozen=True)
class Decision:
    """The three numbers an operator actually gets to choose."""

    target_level: float      # m MSL - draw down towards this
    start_hour: int          # hours from the decision point before releasing
    max_rate: float          # cumecs - ceiling on the release

    def to_policy(self) -> DrawdownPolicy:
        return DrawdownPolicy(
            target_level=self.target_level,
            start_hour=self.start_hour,
            max_rate=self.max_rate,
        )


def _setup(scenario_key: str, cache_dir: Path | str):
    scenario = SCENARIOS[scenario_key]
    series = load_scenario_series(scenario, cache_dir=cache_dir, hourly=True)
    res: Reservoir = scenario.reservoir

    inflow = series["inflow_cumecs"].to_numpy(dtype=float)
    level = series["water_level_m"].to_numpy(dtype=float)
    release = (
        series["powerhouse_cumecs"].fillna(0).to_numpy(dtype=float)
        + series["spillway_cumecs"].fillna(0).to_numpy(dtype=float)
    )

    curve = LevelStorageCurve(res)
    initial = ReservoirState(level=float(level[0]),
                             storage=curve.storage_from_level(float(level[0])))
    opt = ReleaseOptimizer(
        res, scenario.reach,
        weights=ObjectiveWeights.monsoon_peak(),
        limits=OperationalLimits(
            max_release_cumecs=MAX_RELEASE_CUMECS,
            max_ramp_cumecs_per_hour=MAX_RAMP_CUMECS_PER_HOUR,
            max_level=res.frl,
        ),
        seed=7,
    )
    return scenario, series, res, inflow, level, release, initial, opt


def briefing(scenario_key: str = "periyar_oct_2021",
             cache_dir: Path | str = "data/raw") -> dict:
    """Everything the player is allowed to know at the decision point.

    Deliberately excludes the inflow that is about to arrive. They get what an
    operator had: the level now, the rain so far, and a forecast.
    """
    scenario, series, res, inflow, level, _, _, _ = _setup(scenario_key, cache_dir)

    rain = (series["rainfall_mm"].fillna(0).to_numpy(dtype=float)
            if "rainfall_mm" in series else np.zeros_like(inflow))
    hours_known = min(24, len(inflow))

    return {
        "scenario": scenario_key,
        "title": scenario.title,
        "opens": str(series["date"].iloc[0]),
        "reservoir": res.name,
        "level_now_m": round(float(level[0]), 2),
        "rule_level_m": res.rule_level,
        "frl_m": res.frl,
        "freeboard_now_m": round(res.frl - float(level[0]), 2),
        "inflow_now_cumecs": round(float(inflow[0]), 1),
        "rain_last_24h_mm": round(float(rain[:hours_known].sum()), 1),
        "turbine_capacity_cumecs": res.turbine_rated_flow,
        "hours": int(len(inflow)),
        # The knobs, and the range each is allowed to take.
        "controls": {
            "target_level": {"min": round(res.rule_level - 4.0, 2),
                             "max": round(res.frl - 0.5, 2),
                             "step": 0.05,
                             "default": res.rule_level},
            "start_hour": {"min": 0, "max": int(len(inflow) // 2), "step": 1,
                           "default": 24},
            "max_rate": {"min": 0.0, "max": MAX_RELEASE_CUMECS, "step": 10.0,
                         "default": res.turbine_rated_flow},
        },
        "narrative": scenario.narrative,
    }


def _outcome(ev, res: Reservoir, observed_rev: float | None = None) -> dict:
    return {
        "peak_level_m": round(float(ev.peak_level), 2),
        "min_freeboard_m": round(float(res.frl - ev.peak_level), 2),
        "breaches_frl": bool(ev.breaches_frl),
        "exceeds_danger": bool(ev.exceeds_danger),
        "peak_downstream_cumecs": round(float(ev.peak_downstream), 1),
        "revenue_cr": round(float(ev.revenue_inr) / 1e7, 2),
        "revenue_delta_cr": (None if observed_rev is None
                             else round(float(ev.revenue_inr - observed_rev) / 1e7, 2)),
        "total_cost": round(float(ev.total_cost), 3),
    }


@lru_cache(maxsize=8)
def _references(scenario_key: str, cache_dir: str):
    """Observed and hindsight-optimal outcomes for a scenario.

    Neither depends on the player's decision, and the exhaustive search behind
    the second takes seconds, so it is computed once per scenario and reused.
    """
    _, _, res, inflow, _, observed_release, initial, opt = _setup(scenario_key, cache_dir)
    observed_eval = opt.evaluate(observed_release, initial, inflow)
    best_eval, best_policy = opt.search_policies(initial, inflow)
    return res, inflow, initial, opt, observed_eval, best_eval, best_policy


def score(decision: Decision,
          scenario_key: str = "periyar_oct_2021",
          cache_dir: Path | str = "data/raw") -> dict:
    """Play the decision forward against the inflow that actually arrived.

    Returns the player's outcome beside the two references that matter: what
    the operators did on the day, and what the optimiser would have chosen.
    """
    res, inflow, initial, opt, observed_eval, best_eval, best_policy = _references(
        scenario_key, str(cache_dir))

    player_release = opt.policy_schedule(initial, inflow, decision.to_policy())
    player_eval = opt.evaluate(player_release, initial, inflow)

    obs_rev = float(observed_eval.revenue_inr)
    you = _outcome(player_eval, res, obs_rev)
    happened = _outcome(observed_eval, res, obs_rev)
    aquasync = _outcome(best_eval, res, obs_rev)

    return {
        "you": you,
        "what_happened": happened,
        "aquasync": aquasync,
        "aquasync_policy": {
            "target_level": round(float(best_policy.target_level), 2),
            "start_hour": int(best_policy.start_hour),
            "max_rate": round(float(best_policy.max_rate), 1),
        },
        "verdict": verdict(you, happened, aquasync),
    }


def verdict(you: dict, happened: dict, aquasync: dict) -> str:
    """One sentence the player reads first. Blunt on purpose."""
    if you["breaches_frl"]:
        return ("You went over the Full Reservoir Level. In October 2021 that is the "
                "point where the decision stops being yours.")

    gained = happened["peak_level_m"] - you["peak_level_m"]
    vs_best = you["total_cost"] - aquasync["total_cost"]
    more = "more" if gained > 0 else "less"
    cushion = f"{abs(gained):.2f} m {more} cushion than the operators held"

    if vs_best <= 0.05:
        return f"You matched the optimiser, and took {cushion}."
    if gained > 0 and you["revenue_delta_cr"] is not None and you["revenue_delta_cr"] < 0:
        return (f"You took {cushion}, and paid Rs {abs(you['revenue_delta_cr']):.2f} crore "
                f"of generation for it. Safer, and more expensive than it needed to be.")
    if gained > 0:
        return f"Better than the day: {cushion}, without giving up revenue to get it."
    return (f"You held more water than the operators did - {cushion}. "
            f"That is the instinct the record shows, and it is the one that cost them.")
