"""Release scheduling - the part that makes the twin prescriptive.

Given a forecast inflow, a starting reservoir level, and a tide series, find
the hourly release schedule over the next N hours that best trades off:

  * downstream flood damage,
  * dam safety (never approach FRL, never overtop),
  * generation revenue forgone,
  * operational realism (gates cannot slam, crews cannot be called hourly).

This is a constrained multi-objective problem. Three solvers are provided,
in increasing order of cost:

  * ``greedy_rule_curve``  - the baseline. What current practice does:
    hold to the rule curve, spill when you must. Used as the comparison
    against which improvement is measured. Never present the twin without
    this baseline - a number with nothing to beat is not a result.
  * ``search_schedules``   - randomised + local search over piecewise
    release plans. Robust, embarrassingly parallel, no dependencies beyond
    NumPy, and fast enough to run live in a demo.
  * ``optimise_scipy``     - SLSQP on a smoothed objective. Sharper optima
    when the problem is well behaved; falls back to the search when it is
    not.

The objective weights are deliberately exposed and deliberately contestable.
Choosing them is a policy decision, not an engineering one, and the honest
thing to do is let the operator see and set them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .constants import Reach, Reservoir
from .power import HydropowerModel
from .reservoir import LevelStorageCurve, ReservoirModel, ReservoirState
from .routing import MuskingumReach
from .tide import TidalBackwaterModel, TidePredictor


@dataclass
class ObjectiveWeights:
    """Relative importance of each objective. These are a policy choice.

    Defaults reflect peak-monsoon posture: flood damage dominates, revenue
    is a tiebreak. In the dry season the sensible weighting inverts, and the
    twin should be run with a different profile - which is the point of
    keeping them in data rather than in code.
    """

    flood: float = 1.0
    dam_safety: float = 2.0
    revenue: float = 0.15
    gate_movement: float = 0.05

    @staticmethod
    def monsoon_peak() -> ObjectiveWeights:
        return ObjectiveWeights(flood=1.0, dam_safety=3.0, revenue=0.05, gate_movement=0.05)

    @staticmethod
    def dry_season() -> ObjectiveWeights:
        return ObjectiveWeights(flood=0.4, dam_safety=1.0, revenue=1.0, gate_movement=0.1)


@dataclass
class OperationalLimits:
    """Hard constraints the schedule must respect.

    ``max_ramp_cumecs_per_hour`` matters more than it looks. A sudden large
    release is itself a hazard downstream - people and livestock are in the
    riverbed - and Kerala protocol requires staged opening with siren
    warning. A schedule that is mathematically optimal but ramps at 400
    cumecs/hour is not implementable, and proposing it damages credibility.
    """

    max_release_cumecs: float = 1500.0
    min_release_cumecs: float = 0.0       # ecological / riparian minimum
    max_ramp_cumecs_per_hour: float = 100.0
    max_level: float = float("inf")       # set to FRL by the optimiser
    min_level: float = 0.0                # dead storage floor
    max_gate_changes: int = 12            # per 72-hour horizon

    # Grid offtake ceiling, as a mean turbine discharge over the horizon.
    #
    # Without this the optimiser will happily run the turbines flat out for
    # a month and book the revenue, because nothing in the physics stops it.
    # The grid does. Idukki is a peaking station on a system with its own
    # merit order - it cannot simply sell 780 MW of extra baseload because
    # the reservoir would prefer to be emptier.
    #
    # Leaving this at None reproduces the unconstrained (optimistic) result;
    # set it to the observed mean generation to get the conservative,
    # energy-neutral comparison. Both are reported in the counterfactual.
    max_mean_turbine_cumecs: float | None = None


@dataclass
class DrawdownPolicy:
    """An implementable operating instruction, in three numbers.

    "From 06:00 on 10 October, release up to 480 cumecs until Idukki reaches
    728.5 m, then hold." That is a policy a dam operator can be handed, a
    control room can execute, and a court can later audit. An 800-element
    vector of hourly setpoints is none of those things.
    """

    target_level: float        # m MSL to draw down to
    start_hour: int            # hours from the start of the horizon
    max_rate: float            # cumecs ceiling while drawing down
    hold_band: float = 0.15    # m deadband, stops gate hunting
    response_hours: float = 48.0  # spread the correction over this long

    def describe(self, reservoir_name: str = "the reservoir") -> str:
        return (
            f"From hour {self.start_hour}, release up to "
            f"{self.max_rate:.0f} cumecs until {reservoir_name} reaches "
            f"{self.target_level:.2f} m, then hold within "
            f"+/-{self.hold_band:.2f} m."
        )


@dataclass
class ScheduleEvaluation:
    """Everything computed about one candidate schedule."""

    release: np.ndarray
    levels: np.ndarray
    downstream: np.ndarray
    flood_cost: float
    safety_cost: float
    revenue_inr: float
    revenue_cost: float
    movement_cost: float
    total_cost: float
    peak_downstream: float
    peak_level: float
    breaches_frl: bool
    exceeds_danger: bool
    metadata: dict = field(default_factory=dict)


class ReleaseOptimizer:
    """Searches release schedules for one reservoir and its downstream reach."""

    def __init__(
        self,
        reservoir: Reservoir,
        reach: Reach,
        weights: ObjectiveWeights | None = None,
        limits: OperationalLimits | None = None,
        tide: TidePredictor | None = None,
        dt_hours: float = 1.0,
        seed: int = 0,
    ) -> None:
        self.res = reservoir
        self.reach = reach
        self.weights = weights or ObjectiveWeights()
        self.limits = limits or OperationalLimits()
        if self.limits.max_level == float("inf"):
            self.limits.max_level = reservoir.frl
        self.dt = dt_hours

        self.curve = LevelStorageCurve(reservoir)
        self.model = ReservoirModel(reservoir, self.curve)
        self.power = HydropowerModel(reservoir)
        self.router = MuskingumReach(reach.k_hours, reach.x, dt_hours)
        self.tide = tide or TidePredictor()
        self.backwater = TidalBackwaterModel()
        self.rng = np.random.default_rng(seed)

    # -- evaluation ---------------------------------------------------------

    def evaluate(
        self,
        release: np.ndarray,
        initial: ReservoirState,
        inflow: np.ndarray,
        start_hour_of_day: float = 0.0,
        baseline_inflow_downstream: np.ndarray | None = None,
    ) -> ScheduleEvaluation:
        """Simulate one schedule end to end and price it."""
        release = np.clip(np.asarray(release, dtype=float),
                          self.limits.min_release_cumecs,
                          self.limits.max_release_cumecs)
        inflow = np.asarray(inflow, dtype=float)
        n = len(inflow)

        # Split the release between turbines (revenue) and spillway (waste).
        turbine = np.minimum(release, self.res.turbine_rated_flow)
        spill = np.maximum(0.0, release - self.res.turbine_rated_flow)

        # Grid offtake ceiling. Energy the grid will not take is not revenue,
        # so the excess is reclassified as spill rather than silently sold.
        cap = self.limits.max_mean_turbine_cumecs
        if cap is not None and turbine.mean() > cap:
            scale = cap / turbine.mean()
            shed = turbine * (1.0 - scale)
            turbine = turbine * scale
            spill = spill + shed

        states = self.model.simulate(initial, inflow, turbine, spill, self.dt * 3600.0)
        levels = np.array([s.level for s in states])

        # Route the release downstream and add ungauged/tributary flow.
        routed = self.router.route(release, initial_outflow=float(release[0]))
        if baseline_inflow_downstream is not None:
            routed = routed + np.asarray(baseline_inflow_downstream, dtype=float)[:n]

        # Tide reduces how much the downstream reach can safely carry.
        hours = np.arange(n) * self.dt + start_hour_of_day
        tide_levels = self.tide.level(hours)
        if self.reach.tidal:
            safe_capacity = self.backwater.effective_conveyance(
                self.reach.bankfull_cumecs, tide_levels, distance_from_mouth_km=8.0
            )
        else:
            safe_capacity = np.full(n, self.reach.bankfull_cumecs)

        # --- costs ---------------------------------------------------------
        # Flood cost is superlinear: twice the overtopping is much more than
        # twice the damage, because depth-damage curves are convex.
        over = np.maximum(0.0, routed - safe_capacity)
        flood_cost = float(np.sum((over / max(1.0, self.reach.bankfull_cumecs)) ** 2))

        # Dam safety: penalise approaching FRL, hard-penalise breaching it.
        headroom = self.res.frl - levels
        encroach = np.maximum(0.0, 1.0 - headroom / max(1e-6, self.res.frl - self.res.rule_level))
        safety_cost = float(np.sum(encroach ** 2))
        breaches = bool(np.any(levels >= self.res.frl))
        if breaches:
            safety_cost += 100.0 * float(np.sum(np.maximum(0.0, levels - self.res.frl)))

        # Revenue: what we earned, and what we gave up versus turbining all.
        revenue = float(np.sum(self.power.revenue_inr(turbine, levels, hours, self.dt)))
        forgone = float(np.sum(self.power.spill_opportunity_cost(spill, levels, hours, self.dt)))
        # Normalised so it is commensurate with the dimensionless flood term.
        revenue_cost = forgone / 1e7

        # Operational: penalise ramping and frequent gate changes.
        ramp = np.abs(np.diff(release, prepend=release[0]))
        overramp = np.maximum(0.0, ramp - self.limits.max_ramp_cumecs_per_hour)
        movement_cost = float(np.sum((overramp / 100.0) ** 2) + 0.001 * np.sum(ramp > 1.0))

        w = self.weights
        total = (
            w.flood * flood_cost
            + w.dam_safety * safety_cost
            + w.revenue * revenue_cost
            + w.gate_movement * movement_cost
        )

        return ScheduleEvaluation(
            release=release,
            levels=levels,
            downstream=routed,
            flood_cost=flood_cost,
            safety_cost=safety_cost,
            revenue_inr=revenue,
            revenue_cost=revenue_cost,
            movement_cost=movement_cost,
            total_cost=float(total),
            peak_downstream=float(routed.max()) if n else 0.0,
            peak_level=float(levels.max()) if n else 0.0,
            breaches_frl=breaches,
            exceeds_danger=bool(np.any(routed > self.reach.danger_cumecs)),
            metadata={
                "forgone_revenue_inr": forgone,
                "total_released_mm3": float(release.sum() * self.dt * 3600.0 / 1e6),
                "spill_fraction": float(spill.sum() / max(1e-9, release.sum())),
            },
        )

    # -- baseline -----------------------------------------------------------

    def greedy_rule_curve(
        self,
        initial: ReservoirState,
        inflow: np.ndarray,
        start_hour_of_day: float = 0.0,
    ) -> ScheduleEvaluation:
        """Reproduce conventional practice: hold to rule curve, spill reactively.

        This is not a strawman. It is a faithful model of how the level is
        actually managed: generate at whatever the load needs, let the level
        rise, and open gates only once the level crosses the alert bands.
        Its whole failure mode is that it never acts on a forecast.
        """
        inflow = np.asarray(inflow, dtype=float)
        n = len(inflow)
        release = np.zeros(n)
        state = ReservoirState(initial.level, initial.storage)

        for t in range(n):
            level = state.level
            # Baseline generation follows demand, not hydrology.
            daytime = 6 <= (t + start_hour_of_day) % 24 < 22
            turbine = self.res.turbine_rated_flow * (0.55 if daytime else 0.30)

            # Reactive spill: only once past the alert bands.
            if level >= self.res.red_level:
                frac = (level - self.res.red_level) / max(1e-6, self.res.frl - self.res.red_level)
                gates = int(np.clip(np.ceil(frac * 5), 1, 5))
                spill = self.model.spill_capacity(level, gates)
            else:
                spill = 0.0

            release[t] = turbine + spill
            state = self.model.step(
                state, inflow[t],
                min(release[t], self.res.turbine_rated_flow),
                max(0.0, release[t] - self.res.turbine_rated_flow),
                self.dt * 3600.0,
            )

        return self.evaluate(release, initial, inflow, start_hour_of_day)

    # -- search -------------------------------------------------------------

    def _random_schedule(self, n: int, n_blocks: int, max_release: float) -> np.ndarray:
        """A piecewise-constant schedule, which is how gates actually move."""
        edges = np.sort(
            self.rng.choice(np.arange(1, n), size=min(n_blocks - 1, n - 1), replace=False)
        )
        bounds = np.concatenate([[0], edges, [n]])
        out = np.zeros(n)
        for a, b in zip(bounds[:-1], bounds[1:], strict=True):
            out[a:b] = self.rng.uniform(0.0, max_release)
        return out

    def _enforce_ramp(self, release: np.ndarray) -> np.ndarray:
        """Clamp a schedule to the ramp limit, forward then backward."""
        out = release.copy()
        lim = self.limits.max_ramp_cumecs_per_hour * self.dt
        for t in range(1, len(out)):
            out[t] = np.clip(out[t], out[t - 1] - lim, out[t - 1] + lim)
        return np.clip(out, self.limits.min_release_cumecs, self.limits.max_release_cumecs)

    def search_schedules(
        self,
        initial: ReservoirState,
        inflow: np.ndarray,
        n_candidates: int = 4000,
        n_refine: int = 300,
        n_blocks: int = 6,
        start_hour_of_day: float = 0.0,
        seed_schedules: list[np.ndarray] | None = None,
    ) -> ScheduleEvaluation:
        """Randomised search plus hill-climbing refinement.

        Deliberately not a black box. The candidate pool is seeded with the
        rule-curve baseline and with tide-aware schedules, so the search
        starts from operationally sensible plans rather than noise, and the
        refinement is a plain local search that can be explained to a judge
        or an operator in one sentence.
        """
        inflow = np.asarray(inflow, dtype=float)
        n = len(inflow)
        max_release = min(self.limits.max_release_cumecs, float(inflow.max()) * 2.5 + 200.0)

        candidates: list[np.ndarray] = []

        # Seed 1: the baseline itself.
        candidates.append(self.greedy_rule_curve(initial, inflow, start_hour_of_day).release)

        # Seed 2: constant release equal to mean inflow (pure pass-through).
        candidates.append(np.full(n, float(inflow.mean())))

        # Seed 3-N: tide-aware pre-release. Push volume into low-tide windows.
        hours = np.arange(n) * self.dt + start_hour_of_day
        tide_levels = self.tide.level(hours)
        tide_rank = (tide_levels.max() - tide_levels) / max(1e-6, np.ptp(tide_levels))
        for scale in (0.6, 1.0, 1.4, 1.8):
            candidates.append(self._enforce_ramp(tide_rank * float(inflow.mean()) * scale))

        if seed_schedules:
            candidates.extend(seed_schedules)

        for _ in range(n_candidates):
            candidates.append(self._enforce_ramp(self._random_schedule(n, n_blocks, max_release)))

        best = min(
            (self.evaluate(c, initial, inflow, start_hour_of_day) for c in candidates),
            key=lambda e: e.total_cost,
        )

        # Hill-climb: perturb a random block of the best schedule.
        for _ in range(n_refine):
            trial = best.release.copy()
            a = int(self.rng.integers(0, n))
            b = int(min(n, a + self.rng.integers(1, max(2, n // 4))))
            trial[a:b] += self.rng.normal(0.0, max_release * 0.12)
            trial = self._enforce_ramp(trial)

            cand = self.evaluate(trial, initial, inflow, start_hour_of_day)
            if cand.total_cost < best.total_cost:
                best = cand

        return best

    # -- policy search (preferred) ------------------------------------------

    def policy_schedule(
        self,
        initial: ReservoirState,
        inflow: np.ndarray,
        policy: DrawdownPolicy,
    ) -> np.ndarray:
        """Turn a drawdown policy into an hourly release series.

        Free search over N independent hourly releases is the wrong shape for
        this problem. It scales badly - a 30-day window has 720 free
        variables, so a fixed candidate budget covers a longer horizon ever
        more sparsely, and the "result" becomes a measure of search luck
        rather than of lead time. That artefact is easy to mistake for a
        finding.

        It is also operationally meaningless. No dam operator sets 720
        independent hourly values. They set a *policy*: draw down to this
        level, starting on this date, at no more than this rate. Three
        numbers. Searching that space is smaller, smoother, monotonic in
        lead time, and directly implementable as a written instruction.
        """
        inflow = np.asarray(inflow, dtype=float)
        n = len(inflow)
        release = np.zeros(n)
        state = ReservoirState(initial.level, initial.storage)

        for t in range(n):
            if t < policy.start_hour:
                # Business as usual until the policy activates.
                target_release = min(inflow[t], self.res.turbine_rated_flow)
            else:
                excess_m = state.level - policy.target_level
                if excess_m > policy.hold_band:
                    # Proportional drawdown: convert the level error into a
                    # volume, then spread it over the response time.
                    area_km2 = self.curve.surface_area_km2(state.level)
                    excess_m3 = excess_m * area_km2 * 1e6
                    corrective = excess_m3 / (policy.response_hours * 3600.0)
                    target_release = min(policy.max_rate, inflow[t] + corrective)
                elif excess_m < -policy.hold_band:
                    target_release = min(inflow[t], self.res.turbine_rated_flow) * 0.5
                else:
                    target_release = min(inflow[t], policy.max_rate)

            target_release = float(
                np.clip(target_release, self.limits.min_release_cumecs,
                        self.limits.max_release_cumecs)
            )
            # Ramp limit applies to the physical gates, always.
            lim = self.limits.max_ramp_cumecs_per_hour * self.dt
            prev = release[t - 1] if t else target_release
            release[t] = float(np.clip(target_release, prev - lim, prev + lim))

            state = self.model.step(
                state,
                inflow[t],
                min(release[t], self.res.turbine_rated_flow),
                max(0.0, release[t] - self.res.turbine_rated_flow),
                self.dt * 3600.0,
            )

        return release

    def search_policies(
        self,
        initial: ReservoirState,
        inflow: np.ndarray,
        start_hour_of_day: float = 0.0,
        n_targets: int = 14,
        n_starts: int = 12,
        n_rates: int = 8,
    ) -> tuple[ScheduleEvaluation, DrawdownPolicy]:
        """Exhaustive grid search over drawdown policies.

        The grid is small enough to enumerate completely, which means the
        result is deterministic and reproducible - no seed, no search
        variance, and no risk of reporting a lucky sample as a trend.
        """
        inflow = np.asarray(inflow, dtype=float)
        n = len(inflow)

        targets = np.linspace(self.res.blue_level, self.res.frl - 0.2, n_targets)
        starts = np.unique(np.linspace(0, max(1, n - 24), n_starts).astype(int))
        rates = np.linspace(
            self.res.turbine_rated_flow,
            min(self.limits.max_release_cumecs, self.res.turbine_rated_flow * 6),
            n_rates,
        )

        best_eval: ScheduleEvaluation | None = None
        best_policy: DrawdownPolicy | None = None

        for target in targets:
            for start in starts:
                for rate in rates:
                    policy = DrawdownPolicy(
                        target_level=float(target),
                        start_hour=int(start),
                        max_rate=float(rate),
                    )
                    release = self.policy_schedule(initial, inflow, policy)
                    ev = self.evaluate(release, initial, inflow, start_hour_of_day)
                    if best_eval is None or ev.total_cost < best_eval.total_cost:
                        best_eval, best_policy = ev, policy

        assert best_eval is not None and best_policy is not None
        best_eval.metadata["policy"] = {
            "target_level_m": best_policy.target_level,
            "start_hour": best_policy.start_hour,
            "max_rate_cumecs": best_policy.max_rate,
        }
        return best_eval, best_policy

    def compare(
        self,
        initial: ReservoirState,
        inflow: np.ndarray,
        start_hour_of_day: float = 0.0,
        method: str = "policy",
        **search_kwargs,
    ) -> dict[str, ScheduleEvaluation]:
        """Run baseline and optimised side by side. This is the money shot."""
        baseline = self.greedy_rule_curve(initial, inflow, start_hour_of_day)
        if method == "policy":
            optimised, _ = self.search_policies(
                initial, inflow, start_hour_of_day=start_hour_of_day, **search_kwargs
            )
        else:
            optimised = self.search_schedules(
                initial, inflow, start_hour_of_day=start_hour_of_day, **search_kwargs
            )
        return {"baseline": baseline, "optimised": optimised}


def summarise_improvement(
    baseline: ScheduleEvaluation,
    optimised: ScheduleEvaluation,
    reservoir: Reservoir | None = None,
) -> dict:
    """Headline numbers for the dashboard and the pitch.

    The important discipline here is refusing to quote a metric that does
    not mean anything for the episode being replayed.

    For a moderate event where neither schedule ever exceeds bankfull, a
    "peak flow reduction" percentage is noise - and it can even come out
    *negative* for the better schedule, because deliberately moving water
    early raises the peak flow while lowering the risk. Quoting it would be
    both wrong and self-defeating.

    What actually improves in those episodes is **flood cushion**: how much
    empty reservoir is standing by when the next storm arrives. That is the
    metric this returns as ``headline_metric``, and it is chosen from the
    data rather than fixed in advance.
    """

    def pct(a: float, b: float) -> float | None:
        return None if a == 0 else (a - b) / a * 100.0

    any_flooding = baseline.exceeds_danger or optimised.exceeds_danger or (
        baseline.flood_cost > 0 or optimised.flood_cost > 0
    )

    out = {
        "peak_downstream_baseline": baseline.peak_downstream,
        "peak_downstream_optimised": optimised.peak_downstream,
        "peak_reduction_pct": pct(baseline.peak_downstream, optimised.peak_downstream),
        "peak_level_baseline": baseline.peak_level,
        "peak_level_optimised": optimised.peak_level,
        "baseline_breached_frl": baseline.breaches_frl,
        "optimised_breached_frl": optimised.breaches_frl,
        "baseline_exceeded_danger": baseline.exceeds_danger,
        "optimised_exceeded_danger": optimised.exceeds_danger,
        "revenue_baseline_inr": baseline.revenue_inr,
        "revenue_optimised_inr": optimised.revenue_inr,
        "revenue_delta_inr": optimised.revenue_inr - baseline.revenue_inr,
        "flood_cost_baseline": baseline.flood_cost,
        "flood_cost_optimised": optimised.flood_cost,
        "flood_cost_reduction_pct": pct(baseline.flood_cost, optimised.flood_cost),
        "any_bankfull_exceedance": any_flooding,
    }

    if reservoir is not None:
        cushion_base = reservoir.frl - baseline.peak_level
        cushion_opt = reservoir.frl - optimised.peak_level
        out.update(
            {
                "min_freeboard_baseline_m": cushion_base,
                "min_freeboard_optimised_m": cushion_opt,
                "freeboard_gained_m": cushion_opt - cushion_base,
            }
        )

    # Pick the metric that is actually meaningful for this episode.
    if any_flooding:
        out["headline_metric"] = "peak_reduction_pct"
        out["headline_note"] = (
            "Downstream bankfull was exceeded, so peak-flow reduction is the "
            "meaningful measure of benefit."
        )
    elif reservoir is not None:
        out["headline_metric"] = "freeboard_gained_m"
        out["headline_note"] = (
            "Neither schedule exceeded downstream bankfull in this episode, so "
            "peak-flow reduction is not a meaningful benefit measure. The gain "
            "is flood cushion held in reserve for the next storm. Quote "
            "freeboard, not peak reduction, for this case."
        )
    else:
        out["headline_metric"] = None
        out["headline_note"] = "Pass the reservoir to compute freeboard metrics."

    return out
