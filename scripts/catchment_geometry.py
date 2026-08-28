"""Idukki catchment geometry from a real DEM - replaces a guess with a fit.

`forecast_error_study.py` needed a main channel length and slope for the
Idukki unit hydrograph and had none - CATCHMENT_MAIN_CHANNEL_KM and
CATCHMENT_SLOPE were order-of-magnitude estimates, explicitly flagged as
"not calibrated to Idukki". This script replaces the guess with an actual
watershed delineation off a public 30 m DEM.

Data: AWS Terrarium elevation tiles (`s3://elevation-tiles-prod`,
anonymous, no key), zoom 12, mosaicked and reprojected to UTM 43N at 30 m
resolution. Delineation: pysheds (fill pits/depressions, resolve flats, D8
flow direction and accumulation, `catchment()` from the Idukki dam pour
point).

**The one-line naive answer (1,131 km2) is wrong, and the reason why is
the actual finding.** The Mullaperiyar Dam sits upstream on the same
Periyar and diverts its entire catchment through a tunnel to the Vaigai
basin in Tamil Nadu - water that a DEM has no way to know never reaches
Idukki. A second delineation with a pour point at Mullaperiyar (560.7 km2,
close to its commonly cited ~600 km2) subtracted from the naive Idukki
figure gives a net contributing area of 570.3 km2 - within 12% of the
CAG-sourced 650.0 km2 already in `constants.py`, using nothing but public
elevation data and two dam coordinates. That agreement, not the raw
delineation, is what makes the derived channel length and slope trustworthy
enough to replace a guess.

Requires `rasterio`, `pysheds`, `pyproj`, `Pillow` (not part of the
project's normal dependencies - installed for this analysis:
`pip install rasterio pysheds pyproj Pillow`). pysheds 0.5 predates
numpy's removal of `np.in1d` (numpy >= 2.4); this script shims it.

Usage:
    python scripts/catchment_geometry.py
    python scripts/catchment_geometry.py --tile-dir data/raw/dem_tiles --keep-dem
"""

from __future__ import annotations

import argparse
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np

if not hasattr(np, "in1d"):
    np.in1d = np.isin  # pysheds 0.5 needs this; removed in numpy 2.4

import rasterio
from PIL import Image
from pyproj import Transformer
from pysheds.grid import Grid
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, calculate_default_transform, reproject

ROOT = Path(__file__).resolve().parents[1]
UA = "Mozilla/5.0 (compatible; AquaSync-research/0.1)"
ZOOM = 12
LAT_MIN, LAT_MAX = 9.4, 10.4
LON_MIN, LON_MAX = 76.5, 77.6

IDUKKI_LONLAT = (76.9762, 9.8436)       # dam coordinates, constants.py
MULLAPERIYAR_LONLAT = (77.1367, 9.5273)  # upstream, diverts via tunnel to Vaigai
UTM_43N = "EPSG:32643"                   # covers Kerala


def latlon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    lat_rad = math.radians(lat)
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def tile_bounds(x: int, y: int, z: int) -> tuple[float, float, float, float]:
    n = 2**z
    lon_left = x / n * 360.0 - 180.0
    lon_right = (x + 1) / n * 360.0 - 180.0
    lat_top = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    lat_bottom = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return lon_left, lat_bottom, lon_right, lat_top


def fetch_tile(x: int, y: int, tile_dir: Path) -> Path:
    out = tile_dir / f"{x}_{y}.png"
    if out.exists() and out.stat().st_size > 0:
        return out
    url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{ZOOM}/{x}/{y}.png"
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=30) as r:  # noqa: S310
        data = r.read()
    out.write_bytes(data)
    return out


def build_mosaic(tile_dir: Path, out_tif: Path, workers: int) -> None:
    x1, y1 = latlon_to_tile(LAT_MAX, LON_MIN, ZOOM)
    x2, y2 = latlon_to_tile(LAT_MIN, LON_MAX, ZOOM)
    tile_dir.mkdir(parents=True, exist_ok=True)
    jobs = [(x, y) for x in range(x1, x2 + 1) for y in range(y1, y2 + 1)]
    print(f"fetching {len(jobs)} DEM tiles...")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fetch_tile, x, y, tile_dir): (x, y) for x, y in jobs}
        for fut in as_completed(futs):
            fut.result()

    ts = 256
    nx, ny = x2 - x1 + 1, y2 - y1 + 1
    mosaic = np.zeros((ny * ts, nx * ts), dtype=np.float32)
    for x in range(x1, x2 + 1):
        for y in range(y1, y2 + 1):
            arr = np.asarray(Image.open(tile_dir / f"{x}_{y}.png").convert("RGB"), dtype=np.float64)
            r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
            elev = (r * 256 + g + b / 256.0) - 32768.0
            row, col = y - y1, x - x1
            mosaic[row * ts:(row + 1) * ts, col * ts:(col + 1) * ts] = elev.astype(np.float32)

    # A handful of tiles carry isolated Terrarium encoding artefacts far
    # outside any plausible Western Ghats elevation; Anamudi (2,695 m,
    # highest peak in south India) bounds the real range.
    mosaic = np.clip(mosaic, -10.0, 2800.0)

    west, _, _, north = tile_bounds(x1, y1, ZOOM)
    _, south, east, _ = tile_bounds(x2, y2, ZOOM)
    transform = from_bounds(west, south, east, north, mosaic.shape[1], mosaic.shape[0])
    with rasterio.open(
        out_tif, "w", driver="GTiff", height=mosaic.shape[0], width=mosaic.shape[1],
        count=1, dtype=mosaic.dtype, crs="EPSG:4326", transform=transform, nodata=-32768.0,
    ) as dst:
        dst.write(mosaic, 1)


def reproject_to_utm(src_tif: Path, dst_tif: Path, resolution_m: float = 30.0) -> None:
    with rasterio.open(src_tif) as src:
        transform, width, height = calculate_default_transform(
            src.crs, UTM_43N, src.width, src.height, *src.bounds, resolution=resolution_m,
        )
        profile = src.profile.copy()
        profile.update(crs=UTM_43N, transform=transform, width=width, height=height)
        with rasterio.open(dst_tif, "w", **profile) as dst:
            reproject(
                source=rasterio.band(src, 1), destination=rasterio.band(dst, 1),
                src_transform=src.transform, src_crs=src.crs,
                dst_transform=transform, dst_crs=UTM_43N, resampling=Resampling.bilinear,
            )


def delineate(dem_tif: Path) -> dict:
    grid = Grid.from_raster(str(dem_tif))
    dem = grid.read_raster(str(dem_tif))
    to_utm = Transformer.from_crs("EPSG:4326", UTM_43N, always_xy=True)
    to_ll = Transformer.from_crs(UTM_43N, "EPSG:4326", always_xy=True)

    fdir = grid.flowdir(grid.resolve_flats(grid.fill_depressions(grid.fill_pits(dem))))
    acc = grid.accumulation(fdir)
    cell_area_km2 = (grid.affine.a * -grid.affine.e) / 1e6

    def snap_and_delineate(lonlat: tuple[float, float]) -> tuple[np.ndarray, float, tuple]:
        x, y = to_utm.transform(*lonlat)
        sx, sy = grid.snap_to_mask(acc > 500, (x, y))
        catch = grid.catchment(x=sx, y=sy, fdir=fdir, xytype="coordinate").astype(bool)
        return catch, float(catch.sum()) * cell_area_km2, (sx, sy)

    idukki_catch, idukki_topo_km2, idukki_snap = snap_and_delineate(IDUKKI_LONLAT)
    mp_catch, mp_km2, _ = snap_and_delineate(MULLAPERIYAR_LONLAT)
    net_mask = idukki_catch & ~mp_catch
    net_km2 = float(net_mask.sum()) * cell_area_km2

    cdist = grid.cell_distances(fdir)
    dist_to_outlet = grid.distance_to_outlet(
        x=idukki_snap[0], y=idukki_snap[1], fdir=fdir, weights=cdist, xytype="coordinate",
    )
    net_dist = np.where(net_mask, dist_to_outlet, np.nan)
    far_idx = np.unravel_index(np.nanargmax(net_dist), net_dist.shape)
    main_channel_km = float(np.nanmax(net_dist)) / 1000.0

    dem_arr = grid.view(dem)
    row, col = grid.nearest_cell(*idukki_snap)[::-1]
    elev_dam = float(dem_arr[row, col])
    elev_far = float(dem_arr[far_idx])
    slope = (elev_far - elev_dam) / (main_channel_km * 1000.0)

    far_lon, far_lat = to_ll.transform(
        grid.affine.c + far_idx[1] * grid.affine.a,
        grid.affine.f + far_idx[0] * grid.affine.e,
    )

    return {
        "idukki_topographic_catchment_km2": round(idukki_topo_km2, 1),
        "mullaperiyar_topographic_catchment_km2": round(mp_km2, 1),
        "idukki_net_contributing_catchment_km2": round(net_km2, 1),
        "cag_sourced_catchment_km2": 650.0,
        "net_vs_cag_diff_pct": round(100 * (net_km2 - 650.0) / 650.0, 1),
        "main_channel_km": round(main_channel_km, 1),
        "headwater_point_lonlat": [round(far_lon, 4), round(far_lat, 4)],
        "headwater_elevation_m": round(elev_far, 0),
        "dam_pool_elevation_m": round(elev_dam, 0),
        "channel_slope": round(slope, 4),
        "dem_source": "AWS Terrarium (elevation-tiles-prod), zoom 12, ~30-38 m native, "
                       "resampled to 30 m in UTM 43N",
        "method": "pysheds D8 flow accumulation; catchment from Idukki dam pour point "
                  "minus catchment from Mullaperiyar dam pour point (upstream trans-basin "
                  "diversion to the Vaigai basin, Tamil Nadu, via tunnel - invisible to a "
                  "DEM, which sees only topography, not the tunnel)",
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--tile-dir", type=Path, default=ROOT / "data" / "raw" / "dem_tiles")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "processed")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--keep-dem", action="store_true", help="keep the mosaicked GeoTIFFs")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    mosaic_tif = args.out / "idukki_dem_mosaic.tif"
    utm_tif = args.out / "idukki_dem_utm43n.tif"

    if not utm_tif.exists():
        build_mosaic(args.tile_dir, mosaic_tif, args.workers)
        print("reprojecting to UTM 43N, 30 m...")
        reproject_to_utm(mosaic_tif, utm_tif)

    print("delineating catchments (Idukki, Mullaperiyar)...")
    result = delineate(utm_tif)

    for k, v in result.items():
        print(f"  {k}: {v}")

    out_json = args.out / "catchment_geometry_idukki.json"
    out_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nwritten -> {out_json}")

    if not args.keep_dem:
        mosaic_tif.unlink(missing_ok=True)
        utm_tif.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
