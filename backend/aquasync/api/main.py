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
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
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
from ..twin.runoff import DEFAULT_CN_IDUKKI, RainfallRunoffModel, UnitHydrograph
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
    advice_ml: str = ""
    """The same advisory in Malayalam, for the last mile. Template wording
    keyed on the KSDMA alert band - a draft to be checked by a native speaker,
    not a translation service."""
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


def _advice_ml(level: float, spill: float) -> str:
    """The advisory in Malayalam, on the same bands as `_advice`.

    Last-mile wording for the people downstream, not the control room: it
    says what the band means and what to do, not what the operator should
    release. Template text, drafted for the expo; a native speaker should
    read it before it goes near a public channel.
    """
    freeboard = IDUKKI.frl - level
    if level >= IDUKKI.frl:
        return (
            "അപകട മുന്നറിയിപ്പ്: ഇടുക്കി അണക്കെട്ടിലെ ജലനിരപ്പ് പൂർണ്ണ സംഭരണ നിലയ്ക്ക് (FRL) "
            "മുകളിലാണ്. പെരിയാർ തീരത്തുള്ളവർ ഉടൻ സുരക്ഷിത സ്ഥലങ്ങളിലേക്ക് മാറുക."
        )
    if level >= IDUKKI.red_level and spill == 0:
        return (
            f"റെഡ് അലർട്ട്: ജലനിരപ്പ് {level:.2f} മീറ്റർ, ഷട്ടറുകൾ അടഞ്ഞിരിക്കുന്നു. "
            "ഷട്ടറുകൾ തുറക്കാൻ ശുപാർശ. പെരിയാർ തീരത്തുള്ളവർ ജാഗ്രത പാലിക്കുക."
        )
    if level > IDUKKI.rule_level and spill == 0:
        return (
            f"ഓറഞ്ച് അലർട്ട്: ജലനിരപ്പ് {level:.2f} മീറ്റർ, റൂൾ ലെവലിന് മുകളിൽ. "
            "നിയന്ത്രിത ജലനിർഗമനം ആരംഭിക്കാൻ ശുപാർശ. പുഴയോരത്ത് ജാഗ്രത."
        )
    if level > IDUKKI.rule_level:
        return (
            f"ജാഗ്രത: ഷട്ടറുകൾ തുറന്നിരിക്കുന്നു, {spill:.0f} ക്യുമെക്സ് പുറത്തുവിടുന്നു. "
            "പുഴയിൽ ഇറങ്ങരുത്; താഴ്ന്ന പ്രദേശങ്ങളിൽ ജലനിരപ്പ് ഉയരാം."
        )
    return (
        f"സാധാരണ നില: ജലനിരപ്പ് നിയന്ത്രണ പരിധിക്കുള്ളിൽ. {freeboard:.1f} മീറ്റർ "
        "സംഭരണശേഷി ബാക്കിയുണ്ട്."
    )


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
                    advice_ml=_advice_ml(level, spill),
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


@lru_cache(maxsize=16)
def _counterfactual_payload(key: str, cache_dir: str, inflow_scale: float = 1.0) -> dict:
    """The counterfactual, shaped for a client, computed once per scenario.

    The exhaustive policy search behind this takes 11-17 s on this machine and
    nothing in it depends on the request: the same scenario over the same
    cached data returns the same answer every time. Uncached, every page load
    and every reload during a demo pays that cost again - which is the same
    mistake `twin/crisis.py` made before it grew its own cache.

    ``inflow_scale`` is the storm stress test: the recorded inflow multiplied
    before either schedule sees it. At 1.0 this is the flagship replay. At
    anything else the bulletin level is no longer what is being reproduced,
    so it is not sent and the replay-error figures are dropped rather than
    left to be read as if they still applied.
    """
    out = run_counterfactual(key, cache_dir, inflow_scale=inflow_scale)
    ev = out["evaluations"]
    series = out["series"]
    summary = dict(out["summary"])
    scaled = abs(inflow_scale - 1.0) > 1e-9

    # The recorded bulletin level rides alongside the twin's replay of the
    # same releases, so a viewer can see the 0.30 m replay error rather than
    # be told about it. `observed_level` is the twin's number, not KSEB's;
    # the name stays for the clients already reading it.
    bulletin = series["water_level_m"].to_numpy(dtype=float)
    stamps = (
        series["date"].astype(str).tolist() if "date" in series.columns else []
    )
    if scaled:
        for k in ("replay_level_mae_m", "replay_level_max_err_m", "replay_final_err_m"):
            summary.pop(k, None)
        summary["stress_note"] = (
            f"Stress test: the recorded inflow multiplied by {inflow_scale:g} before "
            "either schedule saw it. A scaled copy of one storm - not a forecast, "
            "not a return period. The recorded level is not shown because it is "
            "no longer the thing being reproduced."
        )
    return {
        "summary": summary,
        "series": {
            "observed_level": ev["observed"].levels.tolist(),
            "optimised_level": ev["optimised"].levels.tolist(),
            "observed_release": ev["observed"].release.tolist(),
            "optimised_release": ev["optimised"].release.tolist(),
            "bulletin_level": (
                [] if scaled else [None if np.isnan(v) else float(v) for v in bulletin]
            ),
            "inflow": (
                series["inflow_cumecs"].fillna(0.0).astype(float) * float(inflow_scale)
            ).tolist(),
            "timestamps": stamps,
        },
        "policy": ev["optimised"].metadata.get("policy"),
    }


@app.get("/api/scenarios/{key}/counterfactual")
async def counterfactual(
    key: str,
    inflow_scale: float = Query(1.0, ge=0.5, le=3.0),
) -> dict:
    if key not in SCENARIOS:
        raise HTTPException(404, f"unknown scenario: {key}")
    try:
        return await asyncio.to_thread(
            _counterfactual_payload, key, str(DATA_RAW), float(inflow_scale),
        )
    except FileNotFoundError as exc:
        raise HTTPException(503, f"data not cached - run scripts/fetch_data.py ({exc})") from exc


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
        "advice_ml": _advice_ml(float(levels[-1]), spill),
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


@lru_cache(maxsize=8)
def _scenario_rain_mm_per_hour(key: str, cache_dir: str) -> tuple[float, ...]:
    series = load_scenario_series(SCENARIOS[key], cache_dir=cache_dir, hourly=True)
    return tuple(float(v) for v in series["rainfall_mm"].fillna(0.0).to_numpy())


def _catchment_geometry() -> tuple[float, float, float]:
    """Area, main channel length, slope for Idukki - the DEM-derived values
    `scripts/catchment_geometry.py` wrote, with the same fallbacks the runoff
    validation uses when that file is absent."""
    area = IDUKKI.catchment_area_km2
    channel_km, slope = 66.3, 0.0087
    geom = ROOT / "data" / "processed" / "catchment_geometry_idukki.json"
    if geom.exists():
        g = json.loads(geom.read_text(encoding="utf-8"))
        channel_km = float(g.get("main_channel_km", channel_km))
        slope = float(g.get("channel_slope", slope))
    return area, channel_km, slope


def runoff_whatif(rain_mm_per_hour, curve_number: float) -> dict:
    """What a different curve number does to this storm's runoff *volume*.

    The land-use "policy mode" the brief asked for, in the only shape the
    validated chain can carry. The runoff validation found the SCS-CN chain
    right on volume (-1% pooled over four seasons, -7 to +38% by season) and
    wrong on shape (NSE 0.07, no recession limb), so the answer here is a
    volume and a fraction, and the hydrograph peak is reported as
    shape-unvalidated. The mapping from land use to curve number is the
    handbook's, and the handbook is what CN 72 came from.
    """
    rain = np.asarray(rain_mm_per_hour, dtype=float)
    area, channel_km, slope = _catchment_geometry()
    uh = UnitHydrograph.from_catchment(area, channel_km, slope)

    def run(cn: float) -> tuple[float, float, float]:
        model = RainfallRunoffModel(area, cn, uh)
        q = model.inflow_series(rain, dt_hours=1.0)
        excess_mm = float(model.storm_excess(rain, dt_hours=1.0).sum())
        return float(q.sum() * 3600.0 / 1e6), float(q.max()), excess_mm

    vol, peak, excess = run(curve_number)
    vol0, peak0, excess0 = run(DEFAULT_CN_IDUKKI)
    total_mm = float(rain.sum())
    return {
        "curve_number": float(curve_number),
        "handbook_curve_number": DEFAULT_CN_IDUKKI,
        "rain_total_mm": total_mm,
        "runoff_volume_mm3": vol,
        "runoff_volume_handbook_mm3": vol0,
        "runoff_volume_change_pct": (vol / vol0 - 1.0) * 100.0 if vol0 > 0 else None,
        "runoff_fraction": excess / total_mm if total_mm > 0 else None,
        "runoff_fraction_handbook": excess0 / total_mm if total_mm > 0 else None,
        "peak_inflow_cumecs_shape_unvalidated": peak,
        "peak_inflow_handbook_cumecs_shape_unvalidated": peak0,
        "catchment": {"area_km2": area, "main_channel_km": channel_km, "slope": slope},
        "caveat": (
            "Volume only. The SCS-CN chain reproduces seasonal runoff volume to "
            "within -7 to +38% and does not reproduce hydrograph shape (NSE 0.07), "
            "so the peak is shown for orientation and is not validated. The "
            "curve number is a handbook land-use lookup, not a measurement of "
            "this catchment; CN 72 is the value the validation kept."
        ),
    }


@app.get("/api/scenarios/{key}/runoff")
async def runoff(key: str, cn: float = Query(DEFAULT_CN_IDUKKI, ge=40.0, le=98.0)) -> dict:
    """Catchment policy what-if: this scenario's rain through the runoff
    chain at a chosen curve number, against the handbook value."""
    if key not in SCENARIOS:
        raise HTTPException(404, f"unknown scenario: {key}")
    try:
        rain = await asyncio.to_thread(_scenario_rain_mm_per_hour, key, str(DATA_RAW))
    except FileNotFoundError as exc:
        raise HTTPException(503, f"data not cached - run scripts/fetch_data.py ({exc})") from exc
    return {"scenario": key, **runoff_whatif(rain, cn)}


@app.get("/api/scenarios/{key}/stress_sweep")
async def stress_sweep(key: str) -> dict:
    """The storm-multiple sweep `scripts/stress_sweep.py` wrote for this
    scenario, if it has been run. Served from disk: seven optimiser runs are
    a couple of minutes, which no page load should pay."""
    if key not in SCENARIOS:
        raise HTTPException(404, f"unknown scenario: {key}")
    path = ROOT / "data" / "processed" / f"stress_sweep_{key}.json"
    if not path.exists():
        raise HTTPException(404, f"no sweep on disk - run scripts/stress_sweep.py --scenario {key}")
    return json.loads(path.read_text(encoding="utf-8"))


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
