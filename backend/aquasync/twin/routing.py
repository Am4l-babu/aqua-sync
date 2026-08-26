"""River flood routing - how a release at the dam becomes a level downstream.

Water released from Idukki does not reach Aluva instantly. It travels as a
flood wave that both *lags* (arrives hours later) and *attenuates* (spreads
out and lowers its peak). Getting this right is what lets the twin say
"release now and the peak reaches Aluva at 03:00 tomorrow at 1,180 cumecs"
instead of just "a lot of water is coming".

Two methods are provided:

* ``MuskingumReach``  - the classical 1938 storage-routing method. Two
  parameters (K, x), fast, and adequate for a single reach with a known
  travel time. This is the workhorse.
* ``MuskingumCungeReach`` - derives K and x from channel geometry and the
  discharge itself, so the parameters vary with flow. Slower but does not
  need gauge data to calibrate, which matters for the ungauged reaches.

A reach network is assembled into a directed acyclic graph so that
tributaries and cascading dams combine correctly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .constants import Reach


class MuskingumReach:
    """Classical Muskingum routing for one river reach.

    Storage in the reach is modelled as

        S = K * (x*I + (1-x)*O)

    Combining with continuity gives the recursion

        O[t+1] = C0*I[t+1] + C1*I[t] + C2*O[t]

    K is the flood-wave travel time, x is a dimensionless weighting between
    inflow and outflow control (0 = pure reservoir storage with maximum
    attenuation, 0.5 = pure translation with none). Natural river reaches
    almost always fall between 0.15 and 0.35.
    """

    def __init__(
        self,
        k_hours: float,
        x: float,
        dt_hours: float = 1.0,
        n_subreaches: int | None = None,
    ) -> None:
        if not 0.0 <= x <= 0.5:
            raise ValueError(f"Muskingum x must be in [0, 0.5], got {x}")
        self.k_total = k_hours
        self.x = x
        self.dt = dt_hours
        self.n_sub = n_subreaches or self._required_subreaches(k_hours, x, dt_hours)
        self.k = k_hours / self.n_sub

    @staticmethod
    def _required_subreaches(k_hours: float, x: float, dt_hours: float) -> int:
        """Number of sub-reaches needed for a numerically stable solution.

        The scheme is well behaved only when  2*K*x <= dt <= 2*K*(1-x).
        Outside that band C0 or C2 turns negative and the routed hydrograph
        oscillates - it can even dip below zero before the wave arrives,
        which looks like the river running backwards.

        A long reach at an hourly step almost always violates the lower
        bound. The textbook fix is to split the reach into N equal
        sub-reaches, each with K/N, and route through them in series. That
        is physically the same reach, just discretised properly, and it also
        happens to be a better representation of a long river anyway.
        """
        if k_hours <= 0 or dt_hours <= 0:
            return 1
        # Need 2*(K/N)*x <= dt  ->  N >= 2*K*x/dt
        n_lower = int(np.ceil(2.0 * k_hours * x / dt_hours)) if x > 0 else 1
        # Need dt <= 2*(K/N)*(1-x)  ->  N <= 2*K*(1-x)/dt
        n_upper = int(np.floor(2.0 * k_hours * (1.0 - x) / dt_hours))
        n = max(1, n_lower)
        if n_upper >= n:
            return n
        # No integer N satisfies both: the timestep is too coarse for this
        # reach. Prefer the stable-attenuation side and accept the lag error.
        return max(1, n_upper)

    @property
    def coefficients(self) -> tuple[float, float, float]:
        k, x, dt = self.k, self.x, self.dt
        denom = 2.0 * k * (1.0 - x) + dt
        c0 = (dt - 2.0 * k * x) / denom
        c1 = (dt + 2.0 * k * x) / denom
        c2 = (2.0 * k * (1.0 - x) - dt) / denom
        return c0, c1, c2

    @property
    def is_stable(self) -> bool:
        return 2.0 * self.k * self.x <= self.dt <= 2.0 * self.k * (1.0 - self.x)

    def route(self, inflow, initial_outflow: float | None = None) -> np.ndarray:
        """Route an inflow hydrograph through the reach."""
        inflow = np.asarray(inflow, dtype=float)
        if inflow.size == 0:
            return inflow.copy()

        c0, c1, c2 = self.coefficients
        current = inflow

        for sub in range(self.n_sub):
            out = np.empty_like(current)
            out[0] = current[0] if initial_outflow is None or sub > 0 else initial_outflow
            for t in range(1, len(current)):
                out[t] = c0 * current[t] + c1 * current[t - 1] + c2 * out[t - 1]
            # Physical floor: a river reach cannot discharge negative water.
            current = np.maximum(out, 0.0)

        return current

    # -- calibration --------------------------------------------------------

    @staticmethod
    def calibrate(inflow, outflow, dt_hours: float = 1.0,
                  x_grid=None) -> tuple[float, float, float]:
        """Fit K and x to an observed inflow/outflow pair.

        Uses the standard graphical method turned into a grid search: for
        each trial x, the weighted-flow vs storage plot should collapse to a
        straight line whose slope is K. We pick the x that makes that
        relationship most linear (highest R^2) and read K off the fit.

        Returns ``(k_hours, x, r_squared)``.
        """
        inflow = np.asarray(inflow, dtype=float)
        outflow = np.asarray(outflow, dtype=float)
        if inflow.shape != outflow.shape:
            raise ValueError("inflow and outflow must have the same shape")
        if x_grid is None:
            x_grid = np.arange(0.0, 0.51, 0.01)

        # Cumulative storage from continuity, in cumec-hours.
        net = inflow - outflow
        storage = np.concatenate([[0.0], np.cumsum((net[:-1] + net[1:]) / 2.0) * dt_hours])

        best = (None, None, -np.inf)
        for x in x_grid:
            weighted = x * inflow + (1.0 - x) * outflow
            # Fit storage = K * weighted (through the origin is not required;
            # an offset absorbs the unknown initial storage).
            a = np.vstack([weighted, np.ones_like(weighted)]).T
            coef, residuals, *_ = np.linalg.lstsq(a, storage, rcond=None)
            k = coef[0]
            if k <= 0:
                continue
            pred = a @ coef
            ss_res = float(((storage - pred) ** 2).sum())
            ss_tot = float(((storage - storage.mean()) ** 2).sum())
            r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else -np.inf
            if r2 > best[2]:
                best = (float(k), float(x), float(r2))

        if best[0] is None:
            raise ValueError("calibration failed: no positive K found")
        return best


class MuskingumCungeReach:
    """Muskingum-Cunge: K and x derived from channel hydraulics, not gauges.

    For a wide rectangular channel with Manning roughness n, bed slope S0 and
    width B, the kinematic wave celerity is c = (5/3) * v and

        K = dx / c
        x = 0.5 * (1 - Q / (B * S0 * c * dx))

    Both depend on the discharge, so they are recomputed each step. This is
    the method to use on reaches where no gauge pair exists to calibrate
    against - which is most of them.
    """

    def __init__(
        self,
        length_m: float,
        width_m: float,
        slope: float,
        manning_n: float = 0.035,
        dt_hours: float = 1.0,
        n_subreaches: int = 1,
    ) -> None:
        self.dx = length_m / n_subreaches
        self.width = width_m
        self.slope = slope
        self.n = manning_n
        self.dt = dt_hours
        self.n_sub = n_subreaches

    def _params(self, q: float) -> tuple[float, float]:
        """Flow-dependent (K in hours, x) for a discharge of ``q`` cumecs."""
        q = max(q, 1e-3)
        # Normal depth for a wide channel from Manning:
        # q/B = (1/n) * y^(5/3) * S^(1/2)  ->  y = ((q n)/(B sqrt(S)))^(3/5)
        y = ((q * self.n) / (self.width * np.sqrt(self.slope))) ** 0.6
        v = q / (self.width * y)
        celerity = (5.0 / 3.0) * v

        k_h = self.dx / celerity / 3600.0
        x = 0.5 * (1.0 - q / (self.width * self.slope * celerity * self.dx))
        return k_h, float(np.clip(x, 0.0, 0.5))

    def route(self, inflow) -> np.ndarray:
        inflow = np.asarray(inflow, dtype=float)
        current = inflow.copy()

        for _ in range(self.n_sub):
            out = np.empty_like(current)
            out[0] = current[0]
            for t in range(1, len(current)):
                # Reference discharge for this step: 3-point average.
                q_ref = (current[t] + current[t - 1] + out[t - 1]) / 3.0
                k, x = self._params(q_ref)
                denom = 2.0 * k * (1.0 - x) + self.dt
                c0 = (self.dt - 2.0 * k * x) / denom
                c1 = (self.dt + 2.0 * k * x) / denom
                c2 = (2.0 * k * (1.0 - x) - self.dt) / denom
                out[t] = c0 * current[t] + c1 * current[t - 1] + c2 * out[t - 1]
            current = np.maximum(out, 0.0)

        return current


@dataclass
class RiverNetwork:
    """A directed acyclic graph of reaches, routed from headwaters to sea.

    Nodes are release points, confluences and control points; edges are
    reaches. Routing walks the graph in topological order so that a
    confluence sums the already-routed hydrographs of everything upstream.

    This is what makes the cascade case work: Idukki and Idamalayar release
    into different reaches of the same river, and their pulses arrive at
    Aluva with different lags. Whether they superpose into one big peak or
    spread into two small ones is a *scheduling* choice - and it is the
    single most valuable thing the twin can optimise.
    """

    reaches: dict[str, Reach] = field(default_factory=dict)
    # child -> list of parent node keys feeding it
    topology: dict[str, list[str]] = field(default_factory=dict)
    dt_hours: float = 1.0

    def route_all(
        self,
        source_hydrographs: dict[str, np.ndarray],
        lateral_inflows: dict[str, np.ndarray] | None = None,
    ) -> dict[str, np.ndarray]:
        """Route every source hydrograph to every downstream node.

        ``source_hydrographs`` maps a node key (a dam outlet) to its release
        series. ``lateral_inflows`` optionally adds ungauged tributary flow
        entering a reach. Returns discharge at each node.
        """
        lateral_inflows = lateral_inflows or {}
        results: dict[str, np.ndarray] = dict(source_hydrographs)

        for node in self._topological_order():
            if node in results:
                continue
            parents = self.topology.get(node, [])
            if not parents:
                continue

            total = None
            for parent in parents:
                if parent not in results:
                    continue
                reach = self.reaches.get(node)
                series = results[parent]
                if reach is not None:
                    series = MuskingumReach(
                        reach.k_hours, reach.x, self.dt_hours
                    ).route(series)
                total = series if total is None else total + series

            if total is not None:
                lat = lateral_inflows.get(node)
                if lat is not None:
                    total = total + np.asarray(lat, dtype=float)[: len(total)]
                results[node] = total

        return results

    def _topological_order(self) -> list[str]:
        """Kahn topological sort over the node graph."""
        nodes = set(self.topology) | {p for ps in self.topology.values() for p in ps}
        indegree = {n: 0 for n in nodes}
        for child, parents in self.topology.items():
            indegree[child] = len(parents)

        queue = [n for n, d in indegree.items() if d == 0]
        order: list[str] = []
        while queue:
            n = queue.pop(0)
            order.append(n)
            for child, parents in self.topology.items():
                if n in parents:
                    indegree[child] -= 1
                    if indegree[child] == 0:
                        queue.append(child)

        if len(order) != len(nodes):
            raise ValueError("river network contains a cycle")
        return order


def peak_arrival(hydrograph, dt_hours: float = 1.0) -> tuple[int, float]:
    """Index and value of the hydrograph peak. Returns ``(hours, cumecs)``."""
    h = np.asarray(hydrograph, dtype=float)
    if h.size == 0:
        return 0, 0.0
    i = int(np.argmax(h))
    return int(i * dt_hours), float(h[i])
