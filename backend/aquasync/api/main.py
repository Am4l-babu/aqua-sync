"""AquaSync API: scenario endpoints plus the telemetry WebSocket.

Two clients talk to this:

* the **3D dashboard**, over ``/ws/telemetry`` - it needs a steady ~1 Hz
  state stream and does its own interpolation;
* the **ESP32 rig node**, over MQTT rather than here, with this process
  bridging the broker into the same WebSocket fan-out.

Run it with::

    uvicorn aquasync.api.main:app --reload --port 8000

The dashboard works without this process running - it falls back to a bundled
October 2021 replay. That is deliberate: the expo venue network is not a
dependency the demo can afford.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..twin import (
    IDUKKI,
    HydropowerModel,
    LevelStorageCurve,
    ReservoirModel,
    ReservoirState,
    TidePredictor,
)
from ..twin.crisis import Decision
from ..twin.crisis import briefing as crisis_briefing
from ..twin.crisis import score as crisis_score
from ..twin.scenarios import SCENARIOS, load_scenario_series, run_counterfactual
from .rig import RigBridge
from .rig import from_env as rig_from_env

ROOT = Path(__file__).resolve().parents[3]
DATA_RAW = ROOT / "data" / "raw"
DASHBOARD = ROOT / "dashboard"


# --------------------------------------------------------------------------
# schemas
# --------------------------------------------------------------------------

class Telemetry(BaseModel):
    level: float
    inflow: float
    turbine: float
    spill: float
    gate: float
    freeboard: float
    timestamp: str
    scenario: str
    advice: str
    source: str = "REPLAY"
    """Where these numbers came from, in the dashboard's own vocabulary.

    The socket being open says the backend is reachable. It says nothing
    about whether anything is being measured, and the dashboard used to
    conflate the two - it lit a LIVE badge on connect while streaming a
    2021 replay underneath it. The provenance is decided here, by whatever
    fills the frame, and the dashboard displays what it is told.

    REPLAY   a recorded episode being played back
    LIVE     measurements arriving now, from the rig
    STALE    the rig was live and has gone quiet
    """


class WhatIfRequest(BaseModel):
    start_level: float = Field(..., ge=600.0, le=800.0)
    inflow_cumecs: float = Field(..., ge=0.0, le=5000.0)
    release_cumecs: float = Field(..., ge=0.0, le=5000.0)
    hours: int = Field(72, ge=1, le=720)


class CrisisDecision(BaseModel):
    """The three numbers the player commits to. Bounds mirror the briefing's
    controls, so a hand-rolled request cannot ask for a release the rig's
    operational limits would refuse."""

    target_level: float = Field(..., ge=600.0, le=800.0)
    start_hour: int = Field(..., ge=0, le=720)
    max_rate: float = Field(..., ge=0.0, le=1500.0)


class PolicyRequest(BaseModel):
    scenario: str = "periyar_oct_2021"
    flood_weight: float = 1.0
    revenue_weight: float = 0.05


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------

class Broadcaster:
    """Fan-out to every connected dashboard."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def add(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def drop(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def send(self, payload: dict) -> None:
        message = json.dumps(payload)
        async with self._lock:
            targets = list(self._clients)
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:  # noqa: BLE001 - a dead client must not stop the rest
                await self.drop(ws)


broadcaster = Broadcaster()
_replay_task: asyncio.Task | None = None
_rig: RigBridge | None = None


def _advice(level: float, spill: float) -> str:
    """The single sentence the operator actually reads."""
    freeboard = IDUKKI.frl - level
    if level >= IDUKKI.frl:
        return "FRL EXCEEDED. Open all gates. Downstream evacuation protocol."
    if level >= IDUKKI.red_level and spill == 0:
        return (
            f"Level {level:.2f} m is above the {IDUKKI.red_level} m red alert with "
            f"gates shut and only {freeboard:.2f} m of freeboard. Open gates now."
        )
    if level > IDUKKI.rule_level and spill == 0:
        return (
            f"Level {level:.2f} m is above the {IDUKKI.rule_level} m rule level with "
            f"gates shut. Begin staged drawdown toward the rule level."
        )
    if level > IDUKKI.rule_level:
        return f"Drawdown in progress. {freeboard:.2f} m freeboard remaining."
    return f"Within rule curve. {freeboard:.2f} m of flood cushion available."


async def _replay_loop() -> None:
    """Stream the flagship scenario when no live rig is connected.

    A real deployment replaces this with the MQTT bridge. Until the hardware
    exists, this keeps the dashboard honest rather than blank.
    """
    try:
        series = load_scenario_series(SCENARIOS["periyar_oct_2021"], cache_dir=DATA_RAW)
    except Exception:  # noqa: BLE001 - no cached data yet
        return

    while True:
        for _, row in series.iterrows():
            level = float(row["water_level_m"])
            spill = float(row.get("spillway_cumecs") or 0.0)
            turbine = float(row.get("powerhouse_cumecs") or 0.0)
            await broadcaster.send(
                Telemetry(
                    level=level,
                    inflow=float(row.get("inflow_cumecs") or 0.0),
                    turbine=turbine,
                    spill=spill,
                    gate=min(100.0, spill / 400.0 * 100.0),
                    freeboard=IDUKKI.frl - level,
                    timestamp=str(row["date"]),
                    scenario="periyar_oct_2021",
                    advice=_advice(level, spill),
                    # October 2021, recorded. Never labelled live.
                    source="REPLAY",
                ).model_dump()
            )
            await asyncio.sleep(0.25)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _replay_task, _rig
    _replay_task = asyncio.create_task(_replay_loop())

    # The rig bridge is opt-in: without AQUASYNC_MQTT_HOST the demo runs
    # exactly as it did, offline, with no broker anywhere near it.
    _rig = rig_from_env()
    if _rig is not None and not _rig.start():
        _rig = None

    yield

    if _replay_task:
        _replay_task.cancel()
    if _rig is not None:
        _rig.stop()


app = FastAPI(
    title="AquaSync",
    description="Decision-support digital twin for dam-river flood optimisation",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # local demo only; tighten before any deployment
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# routes
# --------------------------------------------------------------------------

@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0", "data_cached": DATA_RAW.exists()}


@app.get("/api/reservoirs")
async def reservoirs() -> list[dict]:
    from ..twin import REGISTRY

    return [
        {
            "key": r.key, "name": r.name, "district": r.district,
            "lat": r.latitude, "lon": r.longitude,
            "frl": r.frl, "mwl": r.mwl, "rule_level": r.rule_level,
            "red": r.red_level, "orange": r.orange_level, "blue": r.blue_level,
            "dead": r.dead_level,
            "live_storage_at_frl_mm3": r.live_storage_at_frl,
            "installed_capacity_mw": r.installed_capacity_mw,
        }
        for r in REGISTRY.values()
    ]


@app.get("/api/scenarios")
async def scenarios() -> list[dict]:
    return [
        {
            "key": s.key, "title": s.title, "start": s.start, "end": s.end,
            "reservoir": s.reservoir.name, "narrative": s.narrative,
            "citation": s.citation,
        }
        for s in SCENARIOS.values()
    ]


@app.get("/api/scenarios/{key}/counterfactual")
async def counterfactual(key: str) -> dict:
    if key not in SCENARIOS:
        raise HTTPException(404, f"unknown scenario: {key}")
    try:
        out = await asyncio.to_thread(run_counterfactual, key, DATA_RAW)
    except FileNotFoundError as exc:
        raise HTTPException(503, f"data not cached - run scripts/fetch_data.py ({exc})") from exc

    ev = out["evaluations"]
    return {
        "summary": out["summary"],
        "series": {
            "observed_level": ev["observed"].levels.tolist(),
            "optimised_level": ev["optimised"].levels.tolist(),
            "observed_release": ev["observed"].release.tolist(),
            "optimised_release": ev["optimised"].release.tolist(),
        },
        "policy": ev["optimised"].metadata.get("policy"),
    }


@app.post("/api/whatif")
async def whatif(req: WhatIfRequest) -> dict:
    """Constant-inflow, constant-release sandbox behind the dashboard slider."""
    curve = LevelStorageCurve(IDUKKI)
    model = ReservoirModel(IDUKKI, curve)
    power = HydropowerModel(IDUKKI)

    state = ReservoirState(req.start_level, curve.storage_from_level(req.start_level))
    turbine = min(req.release_cumecs, IDUKKI.turbine_rated_flow)
    spill = max(0.0, req.release_cumecs - IDUKKI.turbine_rated_flow)

    states = model.simulate(
        state,
        np.full(req.hours, req.inflow_cumecs),
        np.full(req.hours, turbine),
        np.full(req.hours, spill),
    )
    levels = np.array([s.level for s in states])
    hours = np.arange(req.hours)

    return {
        "levels": levels.tolist(),
        "final_level": float(levels[-1]),
        "peak_level": float(levels.max()),
        "breaches_frl": bool((levels >= IDUKKI.frl).any()),
        "hours_to_frl": model.time_to_frl(state, req.inflow_cumecs - req.release_cumecs),
        "revenue_inr": float(power.revenue_inr(turbine, levels, hours).sum()),
        "spill_cumecs": spill,
        "advice": _advice(float(levels[-1]), spill),
    }


@app.get("/api/crisis/{key}")
async def crisis_brief(key: str) -> dict:
    """The briefing. Everything the operator had, and nothing they did not -
    in particular, not the inflow that is about to arrive."""
    if key not in SCENARIOS:
        raise HTTPException(404, f"unknown scenario: {key}")
    try:
        return await asyncio.to_thread(crisis_briefing, key, DATA_RAW)
    except FileNotFoundError as exc:
        raise HTTPException(503, f"data not cached - run scripts/fetch_data.py ({exc})") from exc


@app.post("/api/crisis/{key}")
async def crisis_play(key: str, decision: CrisisDecision) -> dict:
    """Play the decision forward against the inflow that actually arrived.

    The first call for a scenario runs the exhaustive policy search for the
    hindsight reference and takes a few seconds; it is cached after that, so a
    judge moving a slider gets an answer immediately.
    """
    if key not in SCENARIOS:
        raise HTTPException(404, f"unknown scenario: {key}")
    try:
        return await asyncio.to_thread(
            crisis_score,
            Decision(decision.target_level, decision.start_hour, decision.max_rate),
            key,
            DATA_RAW,
        )
    except FileNotFoundError as exc:
        raise HTTPException(503, f"data not cached - run scripts/fetch_data.py ({exc})") from exc


@app.get("/api/rig")
async def rig_state() -> dict:
    """The scale rig, in the rig's own units.

    Always answers, whether or not a node is connected - a dashboard that
    shows nothing when the hardware is absent cannot tell you the hardware is
    absent. Values are tank-scale and labelled `SCALE_RIG`; nothing here is
    converted into a reservoir reading.
    """
    if _rig is None:
        return {
            "scope": "SCALE_RIG",
            "source": "UNAVAILABLE",
            "status": "bridge not configured - set AQUASYNC_MQTT_HOST to enable",
            "link": {"broker_connected": False, "frames": 0,
                     "malformed": 0, "last_frame_age_s": None},
            "reading": None,
        }
    return _rig.snapshot()


@app.get("/api/tide")
async def tide(hours: int = 72) -> dict:
    t = TidePredictor()
    grid = np.arange(hours, dtype=float)
    return {
        "hours": grid.tolist(),
        "level_m": t.level(grid).tolist(),
        "low_tide_windows": t.low_tide_windows(horizon_hours=hours),
        "spring_range_m": t.spring_range(),
    }


@app.websocket("/ws/telemetry")
async def telemetry_socket(ws: WebSocket) -> None:
    await broadcaster.add(ws)
    try:
        while True:
            # Keep the socket open; the broadcaster does the sending.
            await ws.receive_text()
    except WebSocketDisconnect:
        await broadcaster.drop(ws)
    except Exception:  # noqa: BLE001
        await broadcaster.drop(ws)


# Serve the dashboard from the same origin, so no CORS or file:// issues.
if DASHBOARD.exists():
    app.mount("/", StaticFiles(directory=str(DASHBOARD), html=True), name="dashboard")
