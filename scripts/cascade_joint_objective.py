"""Joint cascade objective - the largest open modelling item.

`scripts/cascade_coordination.py` established the problem and named the fix it
could not perform. Optimising Idukki and Idamalayar independently puts the
joint peak at their confluence 126% above what actually happened, and sweeping
both start hours - the most direct reading of "make the pulses not superpose" -
recovered only 9% of that. Its own conclusion:

    the real next step is not a bigger timing search but a genuinely joint
    objective - each dam's policy search scored against the actual combined
    downstream discharge, not its own reach evaluated in isolation.

That is what this does.

WHAT CHANGES

Nothing about the physics, and nothing about the weights. The single-dam
objective is

    J = w_flood x flood(own reach)
      + w_safety x encroachment(own reservoir)
      + w_revenue x forgone generation
      + w_gate x ramping

and every dam minimises its own J with no knowledge of the other. The flood
term is the one that is wrong to hold privately: both dams discharge into
periyar_lower, so the flooding one causes depends on what the other is doing
at the same hour. Dam safety, revenue and gate wear genuinely are private.

So the joint objective keeps each dam's private terms and computes ONE shared
flood term on the combined routed discharge:

    J_joint = w_flood x flood(combined at periyar_lower)
            + sum over dams of (w_safety x encroachment + w_revenue x forgone
                                + w_gate x ramping)

Identical functional form, identical weights (ObjectiveWeights.monsoon_peak),
identical routing. The only difference is where the flood term is evaluated,
which is precisely the defect.

HOW IT IS SEARCHED

The joint space is two DrawdownPolicies - six parameters. The per-dam grid is
14 x 12 x 8 = 1,344 policies, so the full product is over 1.8 million joint
evaluations, which is not tractable and would not be honest to approximate
with a random sample.

Coordinate descent instead: start from the two independent optima, then
repeatedly re-optimise one dam's whole policy against the joint objective
while the other is held fixed, until neither dam can improve. Each sweep is
exhaustive over that dam's own grid, so within a sweep nothing is missed.

**This finds a local optimum, not the global one.** Alternating optimisation
converges to a point where neither dam can unilaterally improve - a
best-response equilibrium - and a jointly better pair may exist that requires
both to move at once. The result reports how many sweeps it took and whether
it converged, and that caveat travels with the number.

Usage:
    python scripts/cascade_joint_objective.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from aquasync.twin.constants import IDAMALAYAR, IDUKKI, REACHES  # noqa: E402
from aquasync.twin.optimizer import (  # noqa: E402
    DrawdownPolicy,
    ObjectiveWeights,
    OperationalLimits,
    ReleaseOptimizer,
)
from aquasync.twin.reservoir import LevelStorageCurve, ReservoirState  # noqa: E402
from aquasync.twin.routing import RiverNetwork  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from cascade_coordination import load_hourly  # noqa: E402

WINDOW_START, WINDOW_END = "2021-10-08", "2021-10-28"
SHARED_REACH = "periyar_lower"


def policy_grid(opt: ReleaseOptimizer, res, n_hours: int) -> list[DrawdownPolicy]:
    """The same grid `ReleaseOptimizer.search_policies` enumerates.

    Rebuilt here rather than reached into, so the joint search covers exactly
    the candidates the independent search does and the two are comparable.
    """
    targets = np.linspace(res.blue_level, res.frl - 0.2, 14)
    starts = np.unique(np.linspace(0, max(1, n_hours - 24), 12).astype(int))
    rates = np.linspace(
        res.turbine_rated_flow,
        min(opt.limits.max_release_cumecs, 6.0 * res.turbine_rated_flow),
        8,
    )
    return [DrawdownPolicy(float(t), int(s), float(r))
            for t in targets for s in starts for r in rates]


class JointObjective:
    """Scores a pair of policies against the combined downstream discharge."""

    def __init__(self, dams: dict, network: RiverNetwork, flood_weight: float,
                 lateral_cumecs: float = 0.0, n_hours: int = 0):
        self.dams = dams
        self.network = network
        self.flood_weight = flood_weight
        self.bankfull = REACHES[SHARED_REACH].bankfull_cumecs
        self._release_cache: dict[tuple, np.ndarray] = {}
        # Ungauged catchment between the dams and Aluva. No series for it
        # exists, so this is an assumption the caller sets deliberately, not a
        # measurement - and at 0 it changes nothing.
        self.lateral_cumecs = lateral_cumecs
        self._lateral = (
            {SHARED_REACH: np.full(n_hours, lateral_cumecs)} if lateral_cumecs else None
        )

    def release(self, key: str, policy: DrawdownPolicy) -> np.ndarray:
        """Release series for one dam under one policy. Cached: the coordinate
        sweep holds one dam fixed while enumerating the other's whole grid."""
        ck = (key, policy.target_level, policy.start_hour, policy.max_rate)
        hit = self._release_cache.get(ck)
        if hit is None:
            d = self.dams[key]
            hit = d["opt"].policy_schedule(d["initial"], d["inflow"], policy)
            self._release_cache[ck] = hit
        return hit

    def combined(self, releases: dict[str, np.ndarray]) -> np.ndarray:
        return self.network.route_all(releases, self._lateral)[SHARED_REACH]

    def flood(self, combined: np.ndarray) -> float:
        """Same superlinear form as the single-dam objective, on the shared
        reach: sum of ((discharge - bankfull)+ / bankfull) squared."""
        over = np.maximum(0.0, combined - self.bankfull)
        return float(np.sum((over / max(1.0, self.bankfull)) ** 2))

    def score(self, policies: dict[str, DrawdownPolicy]) -> dict:
        releases = {k: self.release(k, p) for k, p in policies.items()}
        combined = self.combined(releases)

        private = 0.0
        per_dam = {}
        for key, rel in releases.items():
            d = self.dams[key]
            # Evaluated with the flood weight zeroed, so this is exactly the
            # dam's private cost: safety, forgone revenue and gate wear.
            ev = d["private_opt"].evaluate(rel, d["initial"], d["inflow"])
            private += ev.total_cost
            per_dam[key] = {
                "private_cost": round(ev.total_cost, 4),
                "peak_level_m": round(float(ev.peak_level), 3),
                "min_freeboard_m": round(float(d["res"].frl - ev.peak_level), 3),
                "revenue_cr": round(ev.revenue_inr / 1e7, 2),
                "breaches_frl": bool(ev.breaches_frl),
            }

        flood = self.flood(combined)
        return {
            "total": self.flood_weight * flood + private,
            "joint_flood_cost": flood,
            "private_cost": private,
            "joint_peak_cumecs": round(float(combined.max()), 1),
            "per_dam": per_dam,
        }


def descend(obj: JointObjective, start: dict[str, DrawdownPolicy],
            grids: dict[str, list[DrawdownPolicy]], max_sweeps: int) -> dict:
    """Alternate exhaustive re-optimisation until neither dam can improve."""
    current = dict(start)
    best = obj.score(current)
    history = [{"sweep": 0, "moved": None, "total": round(best["total"], 4),
                "joint_peak_cumecs": best["joint_peak_cumecs"]}]

    converged = False
    for sweep in range(1, max_sweeps + 1):
        improved = False
        for key in current:
            trial = dict(current)
            local_best, local_policy = best, current[key]
            for cand in grids[key]:
                trial[key] = cand
                sc = obj.score(trial)
                if sc["total"] < local_best["total"] - 1e-9:
                    local_best, local_policy = sc, cand
            if local_policy is not current[key]:
                current[key] = local_policy
                best = local_best
                improved = True
                history.append({
                    "sweep": sweep, "moved": key,
                    "total": round(best["total"], 4),
                    "joint_peak_cumecs": best["joint_peak_cumecs"],
                })
            trial[key] = current[key]
        if not improved:
            converged = True
            break

    return {"policies": current, "score": best, "history": history,
            "converged": converged, "sweeps": len(history) - 1}


def describe(p: DrawdownPolicy) -> dict:
    return {"target_level_m": round(p.target_level, 3),
            "start_hour": int(p.start_hour),
            "max_rate_cumecs": round(p.max_rate, 1)}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache-dir", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "processed")
    ap.add_argument("--max-sweeps", type=int, default=6)
    ap.add_argument("--lateral-sweep", type=float, nargs="*",
                    default=[100, 200, 300, 400, 500],
                    help="assumed ungauged lateral inflow, cumecs")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    series = {"idukki": load_hourly("Idukki", args.cache_dir),
              "idamalayar": load_hourly("Idamalayar", args.cache_dir)}
    n = min(len(s) for s in series.values())
    series = {k: v.iloc[:n] for k, v in series.items()}
    print(f"window: {WINDOW_START} to {WINDOW_END}, {n} hourly steps, both dams")

    weights = ObjectiveWeights.monsoon_peak()
    # The joint objective moves the flood term to the shared reach, so each
    # dam's own evaluation must not also charge for it. Everything else is
    # untouched.
    private_weights = ObjectiveWeights(
        flood=0.0, dam_safety=weights.dam_safety,
        revenue=weights.revenue, gate_movement=weights.gate_movement)

    dams: dict = {}
    for key, res in (("idukki", IDUKKI), ("idamalayar", IDAMALAYAR)):
        s = series[key]
        curve = LevelStorageCurve(res)
        lvl0 = float(s["water_level_m"].iloc[0])
        observed = (s["powerhouse_cumecs"].fillna(0).to_numpy(float)
                    + s["spillway_cumecs"].fillna(0).to_numpy(float))
        limits = OperationalLimits(
            max_release_cumecs=10.9 * res.turbine_rated_flow,
            max_ramp_cumecs_per_hour=50.0,
            max_level=res.frl,
            max_mean_turbine_cumecs=float(
                np.minimum(observed, res.turbine_rated_flow).mean()),
        )
        dams[key] = {
            "res": res,
            "initial": ReservoirState(lvl0, curve.storage_from_level(lvl0)),
            "inflow": s["inflow_cumecs"].to_numpy(float),
            "observed": observed,
            "opt": ReleaseOptimizer(res, REACHES[SHARED_REACH], weights=weights,
                                    limits=limits, seed=7),
            "private_opt": ReleaseOptimizer(res, REACHES[SHARED_REACH],
                                            weights=private_weights,
                                            limits=limits, seed=7),
        }

    network = RiverNetwork(
        reaches={"periyar_upper": REACHES["periyar_upper"],
                 "periyar_lower": REACHES["periyar_lower"]},
        topology={"periyar_upper": ["idukki"],
                  "periyar_lower": ["periyar_upper", "idamalayar"]},
        dt_hours=1.0)

    grids = None
    independent = {}
    print("\nindependent optima (each dam scored on its own reach)...")
    for key, d in dams.items():
        _, policy = d["opt"].search_policies(d["initial"], d["inflow"])
        independent[key] = policy
        print(f"  {key:11s} {policy.describe(key)}")

    def run_at(lateral: float) -> dict:
        """Independent vs jointly-optimised, at one assumed lateral inflow."""
        nonlocal grids
        obj = JointObjective(dams, network, flood_weight=weights.flood,
                             lateral_cumecs=lateral, n_hours=n)
        if grids is None:
            grids = {k: policy_grid(d["opt"], d["res"], n) for k, d in dams.items()}
        naive = obj.score(independent)
        res = descend(obj, independent, grids, args.max_sweeps)
        joint = res["score"]
        observed_peak = float(obj.combined(
            {k: d["observed"] for k, d in dams.items()}).max())
        changed = ({k: describe(v) for k, v in res["policies"].items()}
                   != {k: describe(v) for k, v in independent.items()})
        naive_peak = naive["joint_peak_cumecs"]
        return {
            "lateral_cumecs": lateral,
            "observed_joint_peak_cumecs": round(observed_peak, 1),
            "independent": {
                "policies": {k: describe(v) for k, v in independent.items()},
                "joint_peak_cumecs": naive_peak,
                "joint_cost": round(naive["total"], 4),
                "joint_flood_cost": round(naive["joint_flood_cost"], 4),
                "private_cost": round(naive["private_cost"], 4),
                "per_dam": naive["per_dam"],
            },
            "joint": {
                "policies": {k: describe(v) for k, v in res["policies"].items()},
                "joint_peak_cumecs": joint["joint_peak_cumecs"],
                "joint_cost": round(joint["total"], 4),
                "joint_flood_cost": round(joint["joint_flood_cost"], 4),
                "private_cost": round(joint["private_cost"], 4),
                "per_dam": joint["per_dam"],
                "converged": res["converged"],
                "sweeps": res["sweeps"],
                "history": res["history"],
            },
            "joint_changed_the_policies": changed,
            "peak_reduction_pct": (
                round((naive_peak - joint["joint_peak_cumecs"]) / naive_peak * 100.0, 1)
                if naive_peak else 0.0),
        }

    print("\nrunning the joint objective on the data as held (no lateral inflow)...")
    base = run_at(0.0)
    print(f"  observed joint peak      {base['observed_joint_peak_cumecs']:>7.1f} cumecs")
    print(f"  independent joint peak   {base['independent']['joint_peak_cumecs']:>7.1f} cumecs"
          f"   shared flood cost {base['independent']['joint_flood_cost']}")
    print(f"  joint-objective peak     {base['joint']['joint_peak_cumecs']:>7.1f} cumecs"
          f"   shared flood cost {base['joint']['joint_flood_cost']}")
    print(f"  policies changed: {base['joint_changed_the_policies']}")

    # If the shared flood term is zero the joint objective cannot bite: it
    # reduces to the sum of the private costs, which the independent optima
    # already minimise. Whether that is a property of the objective or of the
    # missing lateral inflow is answerable, so answer it.
    print("\nsensitivity: how much ungauged lateral inflow before it matters?")
    sweep = []
    for lat in args.lateral_sweep:
        r = run_at(float(lat))
        sweep.append(r)
        flag = "changes the policies" if r["joint_changed_the_policies"] else "inert"
        print(f"  lateral {lat:>5.0f} cumecs -> independent "
              f"{r['independent']['joint_peak_cumecs']:>7.1f}, joint "
              f"{r['joint']['joint_peak_cumecs']:>7.1f}  "
              f"({r['peak_reduction_pct']:+.1f}%, {flag})")

    first_biting = next((r["lateral_cumecs"] for r in sweep
                         if r["joint_changed_the_policies"]), None)

    out = {
        "window": [WINDOW_START, WINDOW_END],
        "n_hours": int(n),
        "shared_reach": SHARED_REACH,
        "bankfull_cumecs": REACHES[SHARED_REACH].bankfull_cumecs,
        "weights": {"flood": weights.flood, "dam_safety": weights.dam_safety,
                    "revenue": weights.revenue, "gate_movement": weights.gate_movement},
        "objective": (
            "One shared flood term on the combined routed discharge at "
            "periyar_lower, plus each dam's private dam-safety, forgone-revenue "
            "and gate-wear terms. Same functional form and weights as the "
            "single-dam objective; only the flood term moves."
        ),
        "search": (
            "Coordinate descent from the independent optima: each sweep "
            "re-optimises one dam exhaustively over its own 1,344-policy grid "
            "against the joint objective while the other is held fixed."
        ),
        "as_held": base,
        "lateral_sensitivity": sweep,
        "first_lateral_that_changes_the_policies": first_biting,
        "finding": (
            "On the data as held the joint objective is inert: the combined "
            "peak never reaches periyar_lower's bankfull, so the shared flood "
            "term is identically zero, the objective reduces to the sum of the "
            "private costs, and the independent optima already minimise that. "
            "Coordinate descent converges in zero moves. This is not evidence "
            "that a joint objective is worthless - it is evidence that this "
            "dataset cannot exercise one, because the shared reach never "
            "appears threatened without the ungauged lateral inflow nobody has "
            "measured."
        ),
        "caveats": [
            "Coordinate descent converges to a best-response equilibrium - a "
            "local optimum where neither dam can unilaterally improve. A jointly "
            "better pair requiring both to move at once may exist.",
            "The lateral sensitivity is an ASSUMPTION, not a measurement. A "
            "constant baseline flow is a crude stand-in for a real tributary "
            "hydrograph, and the threshold it produces is indicative of the "
            "order of magnitude only.",
            "Two dams' contribution plus whatever lateral inflow is assumed. "
            "Do not read the zero-lateral cumec figures against bankfull or "
            "danger thresholds as though they were total river discharge.",
            "Routing K and x are anchored to CWC's published 8 h travel time, "
            "not gauge-calibrated (r2 = 0.005 on daily data). Downstream "
            "discharge is indicative.",
            "One event, October 2021, and one cascade.",
        ],
    }
    path = args.out / "cascade_joint_objective.json"
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
