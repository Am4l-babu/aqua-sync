"""Bake a real satellite image of the Idukki dam site for the 3D twin.

The twin's terrain is already measured - `scripts/build_terrain.py` takes the
geometry from Terrarium DEM tiles. What sits on top of it is not: the ground
is shaded procedurally, green blending to rock by steepness. This replaces
that guess with a photograph.

Source is Sentinel-2 L2A true colour (the TCI asset), 10 m, read straight
from the AWS Open Data mirror of the Copernicus archive. No key, no account,
and licensed for reuse with attribution - which matters, because the tile has
to be committed for the offline demo to work, and the imagery layers most
people reach for first (Esri, Google, Bing, Mapbox) all forbid exactly that.

Three things this does deliberately:

  1. **The scene is pinned, not searched.** A "least cloudy scene" query
     returns a different answer as the archive grows, which would make the
     build non-reproducible. SCENE_ID below is fixed; `--search` re-runs the
     query and prints candidates so a human can choose a new one on purpose.

  2. **It registers in Web Mercator, not lat/lon.** build_terrain.py samples
     its grid uniformly in tile-pixel space, so warping the image onto an
     equal-latitude grid would leave it slightly out of register with the
     heightmap it is draped on. Same projection, same window, same corners.

  3. **It never covers the water.** The image freezes the shoreline at the
     moment of capture, and the twin moves the water level. Draping the photo
     over the reservoir would paint a static shoreline that visibly disagrees
     with the moving simulated one - a measured-looking thing that is wrong.
     The alpha channel written here is zero inside the reservoir mask, so the
     existing water shader keeps ownership of that region. February is dry
     season, which keeps the captured sheet small.

Requires `rasterio` and `pyproj` (not part of the backend requirements -
`pip install rasterio pyproj Pillow`), the same extras
`scripts/catchment_geometry.py` already needs. Like that script and
`build_terrain.py`, this is a one-shot builder run by hand: it is not in
`check.py`'s regeneration set, because it needs the network and its output is
committed.

Output (committed, so the dashboard works from a clean clone with no cache):

    dashboard/assets/terrain_idukki_imagery.jpg    true-colour ground texture
    dashboard/assets/terrain_idukki_imagery.json   scene, date, licence, tone

    python scripts/build_imagery.py
    python scripts/build_imagery.py --search        # list candidate scenes
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from pyproj import Transformer
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "dashboard" / "assets"
CACHE = ROOT / "data" / "raw" / "s2_cache"

STAC = "https://earth-search.aws.element84.com/v1/search"
COGS = "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs"

# Sentinel-2 L2A, MGRS tile 43PGL, 7 February 2024, 1.28% scene cloud.
#
# 43PGL is the only tile of the four overlapping this area that contains the
# whole 18 km frame - 43PFL and 43PFM run out of longitude at about 76.914,
# and 43PGM out of latitude at about 9.851. Using one tile avoids mosaicking
# two dates with different sun angles and a seam down the middle of the frame.
#
# February is the dry season in Kerala: little cloud, and the reservoir near
# its seasonal low, which keeps the frozen shoreline in the photo well inside
# the footprint the twin animates.
SCENE_ID = "S2A_43PGL_20240207_0_L2A"
SCENE_DATE = "2024-02-07"
SCENE_CLOUD_PCT = 1.28

# Sentinel-2 is 10 m. The frame is 18 km, so 1,800 pixels is the whole of
# what the sensor actually resolves. 1792 is the nearest multiple of the
# terrain grid (448 x 4), which puts exactly four image pixels on each
# elevation sample and asks for no detail the source does not carry.
TEXTURE_PX = 1792

# Tone. TCI is scaled for a global product and comes out dark over wet
# tropical forest - this frame means about 39/49/31 raw. The stretch is a
# pooled percentile clip followed by a gamma lift, both fixed here so the
# build is reproducible, and both reported in the sidecar JSON so the
# picture is never passed off as raw radiance.
#
# The gamma is deliberately modest. Lifting further looks better as a flat
# image and worse in the scene: the twin lights this texture with a hard
# sun, and a brighter base blows out every slope facing it.
CLIP_LO_PCT, CLIP_HI_PCT = 1.0, 99.0
GAMMA = 1.08          # > 1 brightens
SATURATION = 1.10
JPEG_QUALITY = 92

LICENCE = ("Contains modified Copernicus Sentinel data 2024, processed by ESA. "
           "Free to use with attribution.")


def cog_url(scene_id: str) -> str:
    """TCI asset URL for a scene id like S2A_43PGL_20240207_0_L2A."""
    _, tile, date, *_ = scene_id.split("_")
    zone, band, square = tile[:2], tile[2], tile[3:]
    year, month = date[:4], str(int(date[4:6]))
    return f"{COGS}/{zone}/{band}/{square}/{year}/{month}/{scene_id}/TCI.tif"


def search(bounds: dict, start: str, end: str, max_cloud: float = 20.0) -> None:
    """Print candidate scenes that fully contain the frame, least cloud first.

    Discovery only - it never changes what gets built. Pin a new SCENE_ID by
    hand if one of these is better.
    """
    frame = (bounds["west"], bounds["south"], bounds["east"], bounds["north"])
    req = urllib.request.Request(
        STAC,
        data=json.dumps({
            "collections": ["sentinel-2-l2a"],
            "bbox": list(frame),
            "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z",
            "query": {"eo:cloud_cover": {"lt": max_cloud}},
            "limit": 100,
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    feats = json.load(urllib.request.urlopen(req, timeout=120))["features"]

    rows = []
    for f in feats:
        bb = f["bbox"]
        if bb[0] <= frame[0] and bb[2] >= frame[2] and bb[1] <= frame[1] and bb[3] >= frame[3]:
            rows.append((f["properties"]["eo:cloud_cover"],
                         f["properties"]["datetime"][:10], f["id"]))
    rows.sort()

    print(f"{len(feats)} scenes overlap the frame; {len(rows)} contain it whole\n")
    for cloud, date, sid in rows[:15]:
        mark = "  <- pinned" if sid == SCENE_ID else ""
        print(f"  {date}  cloud {cloud:5.2f}%  {sid}{mark}")
    if not rows:
        print("  none - widen the window or accept a mosaic")


def fetch(bounds: dict, grid: int) -> np.ndarray:
    """Warp the scene onto the terrain's own window. Returns (3, N, N) uint8.

    Cached under data/raw/, which is gitignored: the committed JPEG is the
    artefact, and re-running this should not re-download 100 MB of COG.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{SCENE_ID}_{grid}.npy"
    if cached.exists():
        print(f"  cache hit    {cached.relative_to(ROOT)}")
        return np.load(cached)

    # The terrain window is a tile-pixel rectangle, which is a rectangle in
    # Web Mercator and not quite one in lat/lon. Warp in 3857 so the image
    # lands on the heightmap pixel for pixel.
    to3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    x0, y1 = to3857.transform(bounds["west"], bounds["north"])
    x1, y0 = to3857.transform(bounds["east"], bounds["south"])

    url = cog_url(SCENE_ID)
    print(f"  reading      {url}")
    out = np.zeros((3, grid, grid), dtype="uint8")
    dst_transform = from_bounds(x0, y0, x1, y1, grid, grid)

    with rasterio.Env(AWS_NO_SIGN_REQUEST="YES",
                      GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                      GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="2"):
        with rasterio.open("/vsicurl/" + url) as src:
            if src.count < 3:
                raise SystemExit(f"expected a 3-band TCI, got {src.count}")
            for band in range(3):
                reproject(
                    source=rasterio.band(src, band + 1),
                    destination=out[band],
                    dst_transform=dst_transform,
                    dst_crs="EPSG:3857",
                    resampling=Resampling.bilinear,
                )

    np.save(cached, out)
    return out


def tone(rgb: np.ndarray) -> np.ndarray:
    """Percentile clip, gamma lift, mild saturation. Deterministic.

    One stretch for all three channels, taken from the pooled distribution.
    Clipping each channel against its own percentiles re-balances the colour,
    and on a frame this dominated by green it dragged every forested ridge
    magenta - a picture that looks measured and is not. TCI already carries
    ESA's colour balance; the only thing wanted here is brightness.
    """
    arr = rgb.astype(np.float32)
    lo = float(np.percentile(arr, CLIP_LO_PCT))
    hi = float(np.percentile(arr, CLIP_HI_PCT))
    out = np.clip((arr - lo) / max(hi - lo, 1e-6), 0.0, 1.0)

    out = np.power(out, 1.0 / GAMMA)

    grey = out.mean(axis=0, keepdims=True)
    out = np.clip(grey + (out - grey) * SATURATION, 0.0, 1.0)

    tone.clip_points = [round(lo, 2), round(hi, 2)]   # reported in the sidecar
    return (out * 255.0 + 0.5).astype(np.uint8)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--search", action="store_true",
                    help="list candidate scenes and exit; changes nothing")
    ap.add_argument("--from", dest="start", default="2023-12-01")
    ap.add_argument("--to", dest="end", default="2024-05-31")
    args = ap.parse_args()

    meta_path = ASSETS / "terrain_idukki.json"
    if not meta_path.exists():
        raise SystemExit("run scripts/build_terrain.py first - no terrain metadata")
    terrain = json.loads(meta_path.read_text(encoding="utf-8"))
    bounds = terrain["bounds"]

    if args.search:
        search(bounds, args.start, args.end)
        return

    print("Idukki ground imagery")
    print(f"  scene        {SCENE_ID}  ({SCENE_DATE}, {SCENE_CLOUD_PCT}% cloud)")

    rgb = fetch(bounds, TEXTURE_PX)
    print(f"  raw mean     {rgb.reshape(3, -1).mean(axis=1).round(1).tolist()}")

    toned = tone(rgb)
    print(f"  toned mean   {toned.reshape(3, -1).mean(axis=1).round(1).tolist()}")

    img = Image.fromarray(np.transpose(toned, (1, 2, 0)), mode="RGB")
    jpg = ASSETS / "terrain_idukki_imagery.jpg"
    img.save(jpg, quality=JPEG_QUALITY, optimize=True, subsampling=0)

    metres_per_px = terrain["span_m"] / TEXTURE_PX
    (ASSETS / "terrain_idukki_imagery.json").write_text(json.dumps({
        "source": "Sentinel-2 L2A true colour (TCI), AWS Open Data mirror",
        "scene_id": SCENE_ID,
        "captured": SCENE_DATE,
        "scene_cloud_cover_pct": SCENE_CLOUD_PCT,
        "licence": LICENCE,
        "native_gsd_m": 10.0,
        "texture_px": TEXTURE_PX,
        "metres_per_pixel": round(metres_per_px, 3),
        "registration": "EPSG:3857, same window as terrain_idukki.png, pixel-aligned",
        "bounds": bounds,
        "tone": {
            "note": "Contrast and brightness only. No pixel is moved, and no "
                    "colour is invented - but this is a stretched picture, not "
                    "raw radiance, and nothing quantitative is read off it.",
            "percentile_clip": [CLIP_LO_PCT, CLIP_HI_PCT],
            "clip_points": getattr(tone, "clip_points", None),
            "gamma": GAMMA,
            "saturation": SATURATION,
            "jpeg_quality": JPEG_QUALITY,
        },
        "caveat": "A photograph of one morning. The shoreline in it is frozen at "
                  "the level the reservoir held on that date, so the twin does not "
                  "draw it over the water: inside the reservoir mask the dynamic "
                  "water surface keeps ownership, and only the land is textured.",
    }, indent=2) + "\n", encoding="utf-8")

    size_mb = jpg.stat().st_size / 1e6
    print(f"  resolution   {TEXTURE_PX}x{TEXTURE_PX} at {metres_per_px:.2f} m/px "
          f"(sensor is 10 m)")
    print(f"  wrote        {jpg.relative_to(ROOT)}  ({size_mb:.2f} MB)")
    print(f"  wrote        {(ASSETS / 'terrain_idukki_imagery.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
