"""Extract a real elevation model of the Idukki dam site for the 3D twin.

The dashboard used box primitives for terrain. This replaces them with the
actual topography of the Periyar valley, taken from the same Terrarium DEM
tiles `scripts/catchment_geometry.py` already caches in `data/raw/dem_tiles/`.

Two honest limitations, both of which the dashboard states rather than hides:

  1. The DEM is a *surface* model captured around 2000. The reservoir appears
     in it as a flat sheet at whatever level it held that day, so what sits
     under the water is the historical water surface, not bathymetry. Real
     bed geometry needs a survey - it is a known gap, on the roadmap, and the
     twin never claims to know it.
  2. The dam itself is present in the DEM as built, so the impounded valley is
     already separated from the tailwater by a real barrier. The flood mask
     below relies on that rather than on any drawn geometry.

Output (committed, so the dashboard works from a clean clone with no cache):

    dashboard/assets/terrain_idukki.png    Terrarium-encoded RGB heightmap
    dashboard/assets/terrain_idukki.json   bounds, scale, reservoir mask stats

    python scripts/build_terrain.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
TILES = ROOT / "data" / "raw" / "dem_tiles"
OUT = ROOT / "dashboard" / "assets"

ZOOM = 12
TILE_PX = 256

# Idukki arch dam. Same coordinates as twin/constants.py.
DAM_LAT, DAM_LON = 9.8436, 76.9762

# Window half-width in metres. 9 km each way frames the dam, its gorge and a
# useful reach of the impounded valley. The reservoir runs off-frame to the
# north-east; this is a dam-site view, not a whole-reservoir map.
HALF_SPAN_M = 9000.0

# Output grid. 448 samples across 18 km is a 40 m posting - close to the 37 m
# the source tiles actually carry at this latitude. Finer would be
# interpolation dressed up as detail.
GRID = 448

# Distance from shore, in metres, at which water is shaded as fully 'deep'.
# Purely a visual ramp - there is no bathymetry behind it.
DEPTH_SCALE_M = 900.0

# Full Reservoir Level and Maximum Water Level, m MSL, from twin/constants.py.
FRL = 732.43
MWL = 734.11


def deg2num(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Slippy-map tile coordinates, kept fractional so we can sample sub-tile."""
    n = 2.0**zoom
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def num2deg(x: float, y: float, zoom: int) -> tuple[float, float]:
    n = 2.0**zoom
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n))))
    return lat, lon


def load_mosaic(x0: int, x1: int, y0: int, y1: int) -> np.ndarray:
    """Decode a block of Terrarium tiles into a single elevation array.

    Terrarium packs elevation as (R * 256 + G + B / 256) - 32768 metres.
    """
    rows = []
    for ty in range(y0, y1 + 1):
        cols = []
        for tx in range(x0, x1 + 1):
            path = TILES / f"{tx}_{ty}.png"
            if not path.exists():
                raise FileNotFoundError(
                    f"missing DEM tile {path.name} - run scripts/catchment_geometry.py "
                    f"to populate data/raw/dem_tiles/"
                )
            rgb = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64)
            cols.append(rgb[:, :, 0] * 256.0 + rgb[:, :, 1] + rgb[:, :, 2] / 256.0 - 32768.0)
        rows.append(np.hstack(cols))
    return np.vstack(rows)


def reservoir_masks(elev: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Find the reservoir, and the ground it is allowed to advance onto.

    Filling every cell below FRL does not work. At a 36 m posting the arch dam
    is thinner than one sample, so the dam column averages down to about 705 m
    - below the water it holds back - and a naive flood fill walks straight
    through it into the tailwater gorge, putting water on both faces at the
    same elevation.

    What the DEM does resolve is the reservoir itself: a large, genuinely flat
    sheet, because it was water on the day the data was captured. So key off
    flatness rather than depth. The biggest connected patch of near-level
    ground in the plausible band is the reservoir, and its median height is the
    level it held then.

    Returns (core, allowed, sheet_level):
      core     always water - the captured sheet, whose bed is unknown
      allowed  real land next to it, where the shoreline may advance if the
               level rises. Bounded below so the gorge can never be included.
    """
    from scipy import ndimage

    band = (elev >= 718.0) & (elev <= MWL)
    labels, n = ndimage.label(band)
    if n == 0:
        raise ValueError("no cells in the reservoir elevation band")
    sizes = ndimage.sum(band, labels, range(1, n + 1))
    core = labels == (int(np.argmax(sizes)) + 1)
    sheet = float(np.median(elev[core]))

    # Shoreline may climb onto adjoining land, but never drop into the gorge:
    # the floor keeps the tailwater (610-670 m here) permanently excluded.
    #
    # Both bounds are deliberately tight. A wide reach lets the fringe jump a
    # saddle onto ground that is low enough to qualify but not actually
    # continuous with the reservoir, which renders as a slab of water hanging
    # in a side valley - water where no water can be.
    near = ndimage.binary_dilation(core, iterations=8)
    allowed = near & (elev >= sheet - 6.0)
    return core, allowed, sheet


def dam_axis(
    elev: np.ndarray, core: np.ndarray, sheet: float
) -> tuple[tuple[float, float], float]:
    """Which way the valley drains at the dam, and so which way the dam faces.

    Derived rather than assumed: near the dam the impounded water sits on one
    side and the tailwater gorge on the other, so the vector between their
    centroids is the flow direction and the dam stands across it. Guessing this
    would put the wall along the valley instead of blocking it.
    """
    g = elev.shape[0]
    c = g // 2
    r = max(8, g // 12)
    sl = (slice(c - r, c + r), slice(c - r, c + r))

    rows, cols = np.mgrid[0:g, 0:g]
    near_core = core[sl]
    near_gorge = (elev[sl] < sheet - 20.0)
    if not near_core.any() or not near_gorge.any():
        return (1.0, 0.0), 0.0

    res_c = np.array([rows[sl][near_core].mean(), cols[sl][near_core].mean()])
    tail_c = np.array([rows[sl][near_gorge].mean(), cols[sl][near_gorge].mean()])
    d = tail_c - res_c
    n = float(np.hypot(*d))
    if n < 1e-6:
        return (1.0, 0.0), 0.0
    d = d / n
    # Grid rows increase southward, columns eastward. Report the flow heading
    # in scene terms (x east, z south) and the wall angle perpendicular to it.
    flow = (float(d[1]), float(d[0]))
    return flow, float(math.degrees(math.atan2(flow[1], flow[0])))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    fx, fy = deg2num(DAM_LAT, DAM_LON, ZOOM)
    # Ground resolution of one pixel at this latitude and zoom.
    m_per_px = 156543.03392 * math.cos(math.radians(DAM_LAT)) / (2**ZOOM)
    half_px = HALF_SPAN_M / m_per_px

    # Pixel coordinates of the dam in the global pixel grid, then the window.
    px, py = fx * TILE_PX, fy * TILE_PX
    left, right = px - half_px, px + half_px
    top, bottom = py - half_px, py + half_px

    tx0, tx1 = int(left // TILE_PX), int(right // TILE_PX)
    ty0, ty1 = int(top // TILE_PX), int(bottom // TILE_PX)
    mosaic = load_mosaic(tx0, tx1, ty0, ty1)

    # Window offset within the mosaic.
    ox, oy = left - tx0 * TILE_PX, top - ty0 * TILE_PX
    side = 2.0 * half_px

    # Bilinear resample onto the output grid.
    gx = np.linspace(ox, ox + side, GRID)
    gy = np.linspace(oy, oy + side, GRID)
    x0 = np.clip(np.floor(gx).astype(int), 0, mosaic.shape[1] - 2)
    y0 = np.clip(np.floor(gy).astype(int), 0, mosaic.shape[0] - 2)
    dx = (gx - x0)[None, :]
    dy = (gy - y0)[:, None]
    e00 = mosaic[np.ix_(y0, x0)]
    e10 = mosaic[np.ix_(y0, x0 + 1)]
    e01 = mosaic[np.ix_(y0 + 1, x0)]
    e11 = mosaic[np.ix_(y0 + 1, x0 + 1)]
    elev = (e00 * (1 - dx) * (1 - dy) + e10 * dx * (1 - dy)
            + e01 * (1 - dx) * dy + e11 * dx * dy)

    core, allowed, sheet = reservoir_masks(elev)
    flow, axis_deg = dam_axis(elev, core, sheet)

    # Terrarium-encode the window so the browser can decode it the same way.
    enc = np.clip(elev, -32768.0, 32767.0) + 32768.0
    r = np.floor(enc / 256.0)
    g = np.floor(enc - r * 256.0)
    b = np.floor((enc - r * 256.0 - g) * 256.0)
    rgb = np.stack([r, g, b], axis=-1).astype(np.uint8)
    Image.fromarray(rgb, mode="RGB").save(OUT / "terrain_idukki.png", optimize=True)

    # Blue carries distance from the shoreline, normalised over DEPTH_SCALE_M.
    # The renderer has no bathymetry to shade with, so it shades by how far
    # inside the water body a point is instead - which is honest about being a
    # visual cue rather than a depth, and puts foam where the bank actually is.
    from scipy import ndimage

    dist_cells = ndimage.distance_transform_edt(core)
    dist_m = dist_cells * (2.0 * HALF_SPAN_M / GRID)
    shore = np.clip(dist_m / DEPTH_SCALE_M, 0.0, 1.0)

    mask_rgb = np.stack(
        [core * 255, allowed * 255, (shore * 255).astype(np.uint8)], axis=-1
    ).astype(np.uint8)
    Image.fromarray(mask_rgb, mode="RGB").save(OUT / "terrain_idukki_mask.png", optimize=True)

    lat_n, lon_w = num2deg(left / TILE_PX, top / TILE_PX, ZOOM)
    lat_s, lon_e = num2deg(right / TILE_PX, bottom / TILE_PX, ZOOM)

    meta = {
        "source": "AWS Terrain Tiles (Terrarium encoding), zoom 12",
        "encoding": "elevation_m = (R * 256 + G + B / 256) - 32768",
        "grid": GRID,
        "span_m": round(2.0 * HALF_SPAN_M, 1),
        "metres_per_sample": round(2.0 * HALF_SPAN_M / GRID, 3),
        "dam": {
            "lat": DAM_LAT, "lon": DAM_LON,
            "grid_x": GRID // 2, "grid_y": GRID // 2,
            "flow_dir_xz": [round(flow[0], 4), round(flow[1], 4)],
            "flow_heading_deg": round(axis_deg, 1),
            "note": "flow_dir_xz points downstream in scene axes (x east, z south); "
                    "the dam wall stands perpendicular to it",
        },
        "bounds": {
            "north": round(lat_n, 6), "south": round(lat_s, 6),
            "west": round(lon_w, 6), "east": round(lon_e, 6),
        },
        "elevation_m": {
            "min": round(float(elev.min()), 1),
            "max": round(float(elev.max()), 1),
            "dam_site": round(float(elev[GRID // 2, GRID // 2]), 1),
        },
        "reservoir": {
            "mask_channels": (
                "red = captured sheet (always water); "
                "green = shoreline may advance; "
                "blue = distance from shore, normalised over DEPTH_SCALE_M"
            ),
            "captured_sheet_level_m": round(sheet, 1),
            "core_cells": int(core.sum()),
            "core_area_km2": round(float(core.sum()) * (2.0 * HALF_SPAN_M / GRID) ** 2 / 1e6, 2),
            "allowed_area_km2": round(
                float(allowed.sum()) * (2.0 * HALF_SPAN_M / GRID) ** 2 / 1e6, 2
            ),
            "published_area_at_frl_km2": 60.0,
            "frl_m": FRL,
            "mwl_m": MWL,
        },
        "caveat": (
            "Surface model, not bathymetry. The reservoir appears in the DEM as a flat "
            "sheet at the level it held when the data was captured, so the bed beneath "
            "it is unknown and the twin does not claim otherwise - water inside that "
            "footprint is drawn at the reported level, not computed from depth. "
            "Structures (dam, spillway) are schematic; the terrain is real."
        ),
    }
    (OUT / "terrain_idukki.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print(f"  window        {2 * HALF_SPAN_M / 1000:.1f} km across, {GRID}x{GRID} samples "
          f"({meta['metres_per_sample']:.1f} m each)")
    print(f"  elevation     {meta['elevation_m']['min']:.0f} - {meta['elevation_m']['max']:.0f} m "
          f"(dam site {meta['elevation_m']['dam_site']:.0f} m)")
    print(f"  reservoir     captured sheet at {sheet:.1f} m, "
          f"{meta['reservoir']['core_area_km2']:.1f} km2 "
          f"(published {meta['reservoir']['published_area_at_frl_km2']:.0f} km2 at FRL)")
    print(f"  wrote         {OUT / 'terrain_idukki.png'}")
    print(f"                {OUT / 'terrain_idukki_mask.png'}")
    print(f"                {OUT / 'terrain_idukki.json'}")


if __name__ == "__main__":
    main()
