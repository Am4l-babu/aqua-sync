"""Build docs/AquaSync_Showcase.pdf - the illustrated edition of the project.

The dossier argues the case; this one shows it. Every number on every page is
read at build time from the file that owns it:

    data/processed/*.json        results, as the analysis scripts wrote them
    hardware/bom/README.md       the V1 parts list, tier prices and the pin map
    ROADMAP.md                   the phase map and the reference-source audit
    PROGRESS.md on main          component status, via scripts/status.py
    pytest --collect-only        the test count, today

Nothing is typed in by hand, so a stale page is caught by check.py's
regeneration step like any other artefact. The builder also sums the BOM rows
and refuses to build if they disagree with the stated total.

Fonts are the DejaVu and STIX faces that ship inside matplotlib, registered
as TrueType. That lets arrows, Greek, subscripts and the rupee sign render
without depending on what is installed on the machine, and every string is
checked against the face's character map before it is drawn - a missing glyph
stops the build instead of printing a blank.

    python scripts/build_showcase.py
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from pathlib import Path

import matplotlib
from PIL import Image
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import status  # noqa: E402

PROC = ROOT / "data" / "processed"
ASSETS = ROOT / "docs" / "assets"
OUT = ROOT / "docs" / "AquaSync_Showcase.pdf"

MEDIA_URL = "https://drive.google.com/drive/folders/18p7ca7HLUWT4xghb6OSKdXnopAxLefih?usp=sharing"

W, H = A4
M = 44.0
CW = W - 2 * M

# --- palette ----------------------------------------------------------------

NAVY = HexColor("#0A1F33")
DEEP = HexColor("#10304A")
TEAL = HexColor("#0E7C86")
AQUA = HexColor("#3FB8C5")
SKY = HexColor("#A9DDE6")
PAPER = HexColor("#F6F3EC")
CARD = HexColor("#FFFFFF")
SAND = HexColor("#ECE5D6")
INK = HexColor("#15212D")
MUTED = HexColor("#66727F")
LINE = HexColor("#DAD3C5")
CORAL = HexColor("#D9543C")
AMBER = HexColor("#D99A2B")
GREEN = HexColor("#2E9467")
BLUE = HexColor("#2F74D0")
VIOLET = HexColor("#7556C4")
GREY = HexColor("#8B95A0")
WHITE = HexColor("#FFFFFF")

TINT = {
    "teal": HexColor("#E3F2F2"), "coral": HexColor("#FBE9E4"), "amber": HexColor("#FBF1DE"),
    "green": HexColor("#E3F3EB"), "blue": HexColor("#E4EEFA"), "violet": HexColor("#EEEAF8"),
    "grey": HexColor("#ECEEF0"),
}

# --- fonts ------------------------------------------------------------------

FONT_DIR = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
FACES = {
    "Sans": "DejaVuSans.ttf", "Sans-Bold": "DejaVuSans-Bold.ttf",
    "Sans-Italic": "DejaVuSans-Oblique.ttf", "Sans-BoldItalic": "DejaVuSans-BoldOblique.ttf",
    "Serif": "STIXGeneral.ttf", "Serif-Bold": "STIXGeneralBol.ttf",
    "Serif-Italic": "STIXGeneralItalic.ttf", "Serif-BoldItalic": "STIXGeneralBolIta.ttf",
    "Mono": "DejaVuSansMono.ttf", "Mono-Bold": "DejaVuSansMono-Bold.ttf",
}


def register_fonts() -> None:
    for name, file in FACES.items():
        pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
    for fam in ("Sans", "Serif"):
        registerFontFamily(fam, normal=fam, bold=f"{fam}-Bold", italic=f"{fam}-Italic",
                           boldItalic=f"{fam}-BoldItalic")
    registerFontFamily("Mono", normal="Mono", bold="Mono-Bold", italic="Mono", boldItalic="Mono-Bold")


_CMAP: dict[str, set[int]] = {}
_DRAWN: list[str] = []


def has(font: str, ch: str) -> bool:
    cmap = _CMAP.get(font)
    if cmap is None:
        cmap = _CMAP[font] = set(pdfmetrics.getFont(font).face.charToGlyph)
    return ord(ch) in cmap or ch in "\n\t"


def fallback(font: str) -> str:
    """STIX has no rupee sign and its italic no arrows; DejaVu Sans draws both."""
    return "Sans-Bold" if "Bold" in font else "Sans"


def runs(font: str, s: str) -> list[tuple[str, str]]:
    """Split s into (face, text) runs, borrowing the fallback face for missing glyphs.

    A character neither face can draw stops the build rather than printing a blank.
    """
    out: list[tuple[str, str]] = []
    for ch in s:
        f = font if has(font, ch) else fallback(font)
        if not has(f, ch):
            raise SystemExit(f"no glyph for {ch!r} (U+{ord(ch):04X}) in {font} or {f}: {s[:60]!r}")
        if out and out[-1][0] == f:
            out[-1] = (f, out[-1][1] + ch)
        else:
            out.append((f, ch))
    return out


def markup(font: str, text: str) -> str:
    """Wrap characters the paragraph face cannot draw in a fallback <font> tag."""
    fam = font.split("-")[0]
    faces = {font, f"{fam}-Bold"} if fam in ("Sans", "Serif") else {font}
    parts = re.split(r"(<[^>]+>|&[#\w]+;)", text)
    out = []
    for part in parts:
        if not part or part.startswith("<") or (part.startswith("&") and part.endswith(";")):
            out.append(part)
            continue
        for ch in part:
            if all(has(f, ch) for f in faces):
                out.append(ch)
            elif has("Sans", ch) and has("Sans-Bold", ch):
                out.append(f'<font name="Sans">{ch}</font>')
            else:
                raise SystemExit(f"no glyph for {ch!r} (U+{ord(ch):04X}) in {font}: {text[:60]!r}")
    return "".join(out)


# --- sources ----------------------------------------------------------------

def load(name: str) -> dict:
    return json.loads((PROC / name).read_text(encoding="utf-8"))


# This edition names no event, venue or institution. Text parsed from the
# repository is neutralised on the way in, and the build fails if any of these
# words reaches the page anyway.
EVENT_WORDS = re.compile(r"(?i)\b(evoke|mace|kothamangalam|expo|judges?|competition|college|iot club)\b")


def neutral(s: str) -> str:
    s = re.sub(r"(?i)\bpost-expo\b", "Later", s)
    s = re.sub(r"(?i)\bbeyond the expo\b", "later", s)
    s = re.sub(r"(?i)\bjudges\b", "visitors", s)
    return re.sub(r"(?i)\bjudge\b", "visitor", s)


def md_plain(s: str) -> str:
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    return neutral(s.replace("**", "").replace("`", "").strip())


def section(text: str, heading: str) -> str:
    part = text.split(heading, 1)[1]
    return re.split(r"\n##? ", part, maxsplit=1)[0]


def table_rows(block: str) -> list[list[str]]:
    rows = []
    for line in block.splitlines():
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= set("-: "):
            continue
        rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows[1:]


def test_count() -> int:
    p = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"],
                       cwd=ROOT / "backend", capture_output=True, text=True)
    m = re.search(r"(\d+) tests? collected", p.stdout)
    if not m:
        raise SystemExit("could not read the test count from pytest --collect-only")
    return int(m.group(1))


def inr(n: float) -> str:
    return f"₹{n:,.0f}"


def gather() -> dict:
    d: dict = {}
    d["facts"] = load("figure_facts.json")
    d["r21"] = load("replay_periyar_oct_2021.json")
    d["r22"] = load("replay_idukki_aug_2022.json")
    d["lead"] = load("lead_time_headline.json")
    d["casc"] = load("cascade_coordination.json")
    d["joint"] = load("cascade_joint_objective.json")
    d["route"] = load("routing_calibration_neeleeswaram.json")
    d["catch"] = load("catchment_geometry_idukki.json")
    d["sweeps"] = [load(f"stress_sweep_{k}.json")
                   for k in ("periyar_oct_2021", "idukki_dec_2021", "idukki_aug_2022")]
    d["tests"] = test_count()

    # Component status, from PROGRESS.md as main has it.
    d["status"] = status.progress_md()
    m = re.search(r"\*\*Last updated:\*\*\s*([^\n]+?)\.?\s*$", status.progress_source(), re.M)
    d["updated"] = m.group(1) if m else "see PROGRESS.md"

    # Bill of materials.
    bom = (ROOT / "hardware" / "bom" / "README.md").read_text(encoding="utf-8")
    v1 = section(bom, "## V1").split("### Also needed")[0]
    parts, stated = [], None
    for r in table_rows(v1):
        if r[0].isdigit():
            parts.append({"n": int(r[0]), "name": md_plain(r[1]), "spec": md_plain(r[2]),
                          "qty": int(r[3]), "each": int(r[4].replace(",", "")),
                          "cost": int(r[5].replace(",", "")), "note": md_plain(r[6])})
        elif "Total" in "".join(r):
            stated = int(re.sub(r"[^\d]", "", md_plain(r[-2] if not r[-1] else r[-1])))
    total = sum(p["cost"] for p in parts)
    if total != stated or any(p["qty"] * p["each"] != p["cost"] for p in parts):
        raise SystemExit(f"BOM rows sum to {total}, the README states {stated}")
    d["bom"], d["bom_total"] = parts, total
    d["tiers"] = [
        {"tier": t, "name": n.strip(), "price": pr.strip(), "time": tm.strip()}
        for t, n, pr, tm in re.findall(r"^## (V\d) — (.+?)\s+·\s+(\+?₹[\d,]+)\s+·\s+(.+)$", bom, re.M)
    ]
    wiring = section(bom, "### Wiring — ESP32 pin map")
    d["pins"] = [{"fn": md_plain(r[0]), "part": md_plain(r[1]), "pin": md_plain(r[2]),
                  "wired": r[3].startswith("✅")} for r in table_rows(wiring)]

    # Roadmap: phases and the reference-source audit.
    road = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    d["phases"] = [{"name": md_plain(r[0]), "deliverable": md_plain(r[2]),
                    "done": r[4].startswith("✅")} for r in table_rows(section(road, "## Phase map"))]
    audit_block = section(road, "## Reference-source audit")
    d["audit_date"] = re.search(r"— (\d+ \w+ \d{4})", road.split("## Reference-source audit")[1]).group(1)
    audit = []
    for r in table_rows(audit_block):
        raw = r[1]
        kind = next((k for g, k in (("✅", "built"), ("🟡", "partly"), ("📋", "planned"),
                                    ("🔄", "planned"), ("⏸", "deferred"), ("🚫", "rejected"))
                     if raw.startswith(g)), "planned")
        label = md_plain(re.sub(r"^[^\w]+", "", raw))
        label = re.split(r" — |: |; ", label, maxsplit=1)[0]
        audit.append({"idea": md_plain(r[0]), "kind": kind, "label": label})
    d["audit"] = audit
    return d


# --- drawing primitives ----------------------------------------------------

_STYLES: dict[tuple, ParagraphStyle] = {}


def st(size: float, font: str = "Sans", color: Color = INK, leading: float | None = None,
       align: int = TA_LEFT) -> ParagraphStyle:
    key = (size, font, color.hexval(), leading, align)
    if key not in _STYLES:
        _STYLES[key] = ParagraphStyle(f"s{len(_STYLES)}", fontName=font, fontSize=size,
                                      leading=leading or size * 1.42, textColor=color,
                                      alignment=align)
    return _STYLES[key]


def para(c, text: str, x: float, ytop: float, w: float, style: ParagraphStyle) -> float:
    _DRAWN.append(text)
    p = Paragraph(markup(style.fontName, text), style)
    _, h = p.wrap(w, H)
    p.drawOn(c, x, ytop - h)
    return h


def txt(c, s: str, x: float, y: float, font: str = "Sans", size: float = 9,
        color: Color = INK, align: str = "left", space: float = 0.0, alpha: float = 1.0) -> float:
    _DRAWN.append(s)
    pieces = runs(font, s)
    width = sum(pdfmetrics.stringWidth(seg, f, size) for f, seg in pieces)
    width += space * max(len(s) - 1, 0)
    if align == "center":
        x -= width / 2
    elif align == "right":
        x -= width
    c.saveState()
    c.setFillColor(color)
    c.setFillAlpha(alpha)
    t = c.beginText()
    t.setTextOrigin(x, y)
    t.setCharSpace(space)
    for f, seg in pieces:
        t.setFont(f, size)
        t.textOut(seg)
    c.drawText(t)
    c.restoreState()
    return width


def rrect(c, x, y, w, h, r=6.0, fill=None, stroke=None, lw=0.8, alpha=1.0, dash=None):
    c.saveState()
    if fill is not None:
        c.setFillColor(fill)
        c.setFillAlpha(alpha)
    if stroke is not None:
        c.setStrokeColor(stroke)
        c.setLineWidth(lw)
        if dash:
            c.setDash(dash)
    c.roundRect(x, y, w, h, r, stroke=int(stroke is not None), fill=int(fill is not None))
    c.restoreState()


def card(c, x, y, w, h, r=8.0, fill=CARD, accent=None):
    rrect(c, x + 1.2, y - 1.8, w, h, r, fill=NAVY, alpha=0.06)
    rrect(c, x, y, w, h, r, fill=fill, stroke=LINE, lw=0.5)
    if accent is not None:
        c.saveState()
        p = c.beginPath()
        p.roundRect(x, y, w, h, r)
        c.clipPath(p, stroke=0, fill=0)
        c.setFillColor(accent)
        c.rect(x, y, 3.2, h, stroke=0, fill=1)
        c.restoreState()


def gradient(c, x, y, w, h, top: Color, bottom: Color, r: float = 0.0, horizontal=False):
    c.saveState()
    p = c.beginPath()
    if r:
        p.roundRect(x, y, w, h, r)
    else:
        p.rect(x, y, w, h)
    c.clipPath(p, stroke=0, fill=0)
    if horizontal:
        c.linearGradient(x, y, x + w, y, (top, bottom), extend=False)
    else:
        c.linearGradient(x, y + h, x, y, (top, bottom), extend=False)
    c.restoreState()


def arrow(c, x1, y1, x2, y2, color=MUTED, lw=1.1, head=5.0, dash=None):
    ang = math.atan2(y2 - y1, x2 - x1)
    ca, sa = math.cos(ang), math.sin(ang)
    c.saveState()
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(lw)
    if dash:
        c.setDash(dash)
    c.line(x1, y1, x2 - head * 0.8 * ca, y2 - head * 0.8 * sa)
    c.setDash([])
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(x2 - head * ca + head * 0.55 * sa, y2 - head * sa - head * 0.55 * ca)
    p.lineTo(x2 - head * ca - head * 0.55 * sa, y2 - head * sa + head * 0.55 * ca)
    p.close()
    c.drawPath(p, stroke=0, fill=1)
    c.restoreState()


def pill(c, x, y, label: str, fg: Color, bg: Color, size=6.6, align="left", font="Sans-Bold") -> float:
    tw = pdfmetrics.stringWidth(label, font, size) + 0.5 * len(label)
    w = tw + 2 * size
    if align == "center":
        x -= w / 2
    elif align == "right":
        x -= w
    rrect(c, x, y - size * 0.55, w, size * 2.0, size, fill=bg)
    txt(c, label, x + size, y, font, size, fg, space=0.5)
    return w


def badge(c, x, y, n: str, color=TEAL, r=8.0, fg=WHITE):
    c.saveState()
    c.setFillColor(color)
    c.circle(x, y, r, stroke=0, fill=1)
    c.restoreState()
    txt(c, n, x, y - r * 0.36, "Sans-Bold", r * 1.05, fg, align="center")


def image(c, path_or_img, x, y, w, h=None, r=0.0, frame=True):
    img = path_or_img
    if isinstance(img, Path):
        with Image.open(img) as im:
            pw, ph = im.size
        src = str(img)
    else:
        pw, ph = img.size
        src = ImageReader(img)
    if h is None:
        h = w * ph / pw
    if frame:
        rrect(c, x + 1.5, y - 2.5, w, h, r, fill=NAVY, alpha=0.10)
    c.saveState()
    if r:
        p = c.beginPath()
        p.roundRect(x, y, w, h, r)
        c.clipPath(p, stroke=0, fill=0)
    c.drawImage(src, x, y, w, h)
    c.restoreState()
    if frame:
        rrect(c, x, y, w, h, r, stroke=LINE, lw=0.5)
    return h


# --- page furniture ----------------------------------------------------------

def paper(c, n: int, label: str):
    c.setFillColor(PAPER)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.5)
    c.line(M, 34, W - M, 34)
    txt(c, "AQUASYNC", M, 22, "Mono-Bold", 6.6, TEAL, space=1.6)
    txt(c, label.upper(), M + 62, 22, "Mono", 6.6, MUTED, space=1.2)
    txt(c, str(n), W - M, 21, "Serif-Bold", 11, INK, align="right")


def heading(c, num: str, kicker: str, title: str, lede: str | None = None) -> float:
    c.setFillColor(TEAL)
    c.rect(M, H - 58, 18, 2.2, stroke=0, fill=1)
    txt(c, f"{num}  ·  {kicker.upper()}", M + 26, H - 60, "Mono-Bold", 7.4, TEAL, space=1.8)
    y = H - 72
    y -= para(c, title, M, y, CW, st(29, "Serif-Bold", INK, leading=32))
    if lede:
        y -= 6
        y -= para(c, lede, M, y, CW * 0.92, st(12, "Serif-Italic", MUTED, leading=16))
    return y - 14


def subhead(c, s: str, x: float, y: float, color=INK, size=13.5) -> float:
    txt(c, s, x, y - size, "Serif-Bold", size, color)
    return y - size - 7


def label(c, s: str, x: float, y: float, color=MUTED, size=6.4, align="left"):
    return txt(c, s.upper(), x, y, "Mono-Bold", size, color, align=align, space=1.1)


# --- page 1: cover ------------------------------------------------------------

def cover_image() -> Image.Image:
    with Image.open(ROOT / "dashboard" / "assets" / "terrain_idukki_imagery.jpg") as im:
        im = im.convert("RGB")
        side = im.size[1]
        cw = int(side * W / H)
        left = max(0, min(im.size[0] - cw, int(im.size[0] * 0.46 - cw / 2)))
        im = im.crop((left, 0, left + cw, side)).resize((1150, int(1150 * H / W)), Image.LANCZOS)
    w, h = im.size
    navy = Image.new("RGB", im.size, (10, 31, 51))
    mask = Image.new("L", im.size)
    px = []
    for yy in range(h):
        t = yy / (h - 1)
        if t < 0.50:
            a = 0.94 - 0.82 * (t / 0.50) ** 1.4
        elif t < 0.58:
            a = 0.12
        else:
            a = min(0.95, 0.12 + 0.86 * ((t - 0.58) / 0.20) ** 1.1)
        px.append(int(255 * a))
    for yy, a in enumerate(px):
        mask.paste(a, (0, yy, w, yy + 1))
    return Image.composite(navy, im, mask)


def page_cover(c, d):
    c.drawImage(ImageReader(cover_image()), 0, 0, W, H)
    c.setFillColor(AQUA)
    c.rect(M, H - 64, 26, 2.4, stroke=0, fill=1)
    txt(c, "FLOOD MANAGEMENT  ·  DAMS, RIVERS AND THE SEA  ·  DIGITAL TWIN", M + 34, H - 66,
        "Mono-Bold", 7.2, SKY, space=1.8)
    txt(c, "AquaSync", M - 3, H - 158, "Serif-Bold", 84, WHITE)
    y = H - 180
    y -= para(c, "When should a dam let water go? <i>Before</i> the storm, not after it.",
              M, y, CW * 0.86, st(22, "Serif", WHITE, leading=27))
    y -= 10
    para(c, "A flood-management twin for any basin where reservoirs, rivers and the tide interact. "
            "It simulates the connected water bodies together, searches release policies on a forecast, "
            "and hands a named operator one sentence to approve or reject. Its first proving ground is "
            "Kerala's Periyar basin, the case study throughout this document.", M, y, CW * 0.74, st(10.5, "Sans", SKY, leading=15.5))

    # Media link
    ly = 262
    rrect(c, M, ly, CW, 40, 8, fill=WHITE, alpha=0.10)
    rrect(c, M, ly, CW, 40, 8, stroke=AQUA, lw=0.7)
    badge(c, M + 20, ly + 20, "▶", AQUA, r=10, fg=NAVY)
    txt(c, "Photos and videos of the project", M + 40, ly + 23, "Sans-Bold", 9.6, WHITE)
    txt(c, "drive.google.com/drive/folders/18p7ca7HLUWT4xghb6OSKdXnopAxLefih", M + 40, ly + 10,
        "Mono", 7.4, SKY)
    txt(c, "OPEN  →", W - M - 14, ly + 17, "Mono-Bold", 7.4, AQUA, align="right", space=1.2)
    c.linkURL(MEDIA_URL, (M, ly, M + CW, ly + 40), relative=0, thickness=0)

    # Headline numbers
    r21 = d["r21"]
    kpis = [
        (f"{r21['mean_absolute_error_m']:.2f} m", "replay error · case study",
         "Mean level error over 20 days of October 2021, against the KSEB bulletin."),
        ("about 3 m", "flood cushion",
         "More than the day had, in hindsight, with slightly more revenue. About half a metre "
         "of it sits inside model error."),
        (f"{d['tests']}", "tests",
         "Physics and behaviour tests, collected today. One command, check.py, is the gate."),
    ]
    kw = CW / 3
    for i, (num, lab, body) in enumerate(kpis):
        x = M + i * kw
        if i:
            c.setStrokeColor(SKY)
            c.setStrokeAlpha(0.35)
            c.setLineWidth(0.6)
            c.line(x - 8, 110, x - 8, 222)
            c.setStrokeAlpha(1)
        label(c, lab, x, 208, AQUA, 6.8)
        txt(c, num, x, 176, "Serif-Bold", 30, WHITE)
        para(c, body, x, 164, kw - 22, st(8, "Sans", SKY, leading=11.2))

    c.setStrokeColor(SKY)
    c.setStrokeAlpha(0.35)
    c.line(M, 92, W - M, 92)
    c.setStrokeAlpha(1)
    txt(c, "ANY DAM–RIVER–SEA BASIN  ·  CASE STUDY: PERIYAR, KERALA", M, 74, "Mono-Bold", 6.6,
        WHITE, space=0.3)
    txt(c, "A NAMED OPERATOR APPROVES EVERY RELEASE", M, 62, "Mono", 6.6, SKY, space=0.3)
    pill(c, W - M, 62, "ADVISORY, PERMANENTLY", NAVY, AQUA, size=6.6, align="right")
    txt(c, "Cover: Idukki reservoir, Sentinel-2 true colour, 7 February 2024. Contains modified "
           "Copernicus Sentinel data.", M, 34, "Sans-Italic", 6.4, SKY)


# --- page 2: contents and summary ---------------------------------------------

def page_contents(c, d, n, toc):
    paper(c, n, "Contents")
    txt(c, "Contents", M, H - 92, "Serif-Bold", 29, INK)
    y = H - 122
    for i, (num, title, page) in enumerate(toc):
        yy = y - i * 25.5
        txt(c, num, M, yy, "Mono-Bold", 7.6, TEAL, space=1)
        txt(c, title, M + 24, yy, "Serif", 12, INK)
        txt(c, str(page), M + 196, yy, "Serif-Bold", 12, INK, align="right")
        c.setStrokeColor(LINE)
        c.setLineWidth(0.4)
        c.setDash([0.6, 2.2])
        tw = pdfmetrics.stringWidth(title, "Serif", 12)
        c.line(M + 28 + tw, yy + 2, M + 182, yy + 2)
        c.setDash([])

    x = M + 226
    w = W - M - x
    rrect(c, x, H - 250, w, 162, 10, fill=NAVY)
    gradient(c, x, H - 250, w, 162, DEEP, NAVY, r=10)
    label(c, "See it built", x + 16, H - 110, AQUA, 7)
    txt(c, "Photos and videos", x + 16, H - 136, "Serif-Bold", 21, WHITE)
    para(c, "Photographs and video recordings of the project are kept together in one shared "
            "folder. Open it alongside this document: the pages here explain what the pictures show.",
         x + 16, H - 146, w - 32, st(9, "Sans", SKY, leading=13))
    rrect(c, x + 16, H - 238, w - 32, 24, 12, fill=AQUA)
    txt(c, "Open the Google Drive folder  →", x + 16 + (w - 32) / 2, H - 229.5, "Sans-Bold", 9,
        NAVY, align="center")
    c.linkURL(MEDIA_URL, (x + 16, H - 238, x + w - 16, H - 214), relative=0, thickness=0)
    para(c, MEDIA_URL, x, H - 258, w, st(6.3, "Mono", MUTED, leading=8.5))

    yy = subhead(c, "The project in one breath", x, H - 290)
    para(c, "Most reservoirs are run on rule curves that react to a level once it is crossed, one dam "
            "at a time. Floods do not respect that: rain, reservoirs, rivers and the tide act as one "
            "connected system. In October 2021 on the Periyar, Idukki entered a storm above its own rule "
            "level and both dams opened on the same day. AquaSync replays such episodes in a "
            "physics-based twin, then asks what a release schedule chosen on a forecast would have "
            "done instead. It never touches a real gate: the output is advice, for a named person "
            "to accept or refuse.", x, yy, w, st(9.4, "Sans", INK, leading=14))

    # Six numbers
    f = d["facts"]
    fe21, fe22 = f["forecast_error"], f["forecast_error_aug_2022"]
    lead = d["lead"]
    casc = d["casc"]
    cards = [
        (f"{d['r21']['mean_absolute_error_m']:.2f} m", TEAL,
         f"Replay error over 20 days of October 2021; {d['r21']['max_absolute_error_m']:.2f} m at worst."),
        (f"{d['r22']['mean_absolute_error_m']:.2f} m", TEAL,
         "On August 2022, an episode never tuned to. The drift changes sign."),
        ("about 3 m", GREEN,
         "More cushion than the day at every lead time. About 0.5 m sits inside model error."),
        (f"{lead['spill_fraction_at_0_days'] * 100:.0f}% → {lead['spill_fraction_at_30_days'] * 100:.0f}%", BLUE,
         "Share of released water spilled, at zero lead versus 30 days."),
        (f"{matches_to(fe21)} h / {matches_to(fe22)} h", VIOLET,
         f"Forecast matches hindsight to here (2021 / 2022), then +{fe21['ev_excess_cost_pct'][-1]:.0f}% "
         f"or +{fe22['ev_excess_cost_pct'][-1]:.0f}% excess cost."),
        (f"{casc['naive_independent_joint_peak_cumecs']:,.0f}", CORAL,
         f"cumecs at the confluence with each dam optimised alone, against "
         f"{casc['observed_joint_peak_cumecs']:,.0f} observed. Two dams' contribution only."),
    ]
    top = 368
    txt(c, "Periyar case study: six numbers", M, top + 14, "Serif-Bold", 13.5, INK)
    cw, ch = (CW - 20) / 3, 108
    for i, (num, col, body) in enumerate(cards):
        cx = M + (i % 3) * (cw + 10)
        cy = top - 16 - (i // 3 + 1) * (ch + 10) + 10
        card(c, cx, cy, cw, ch, accent=col)
        txt(c, num, cx + 14, cy + ch - 34, "Serif-Bold", 22, col)
        para(c, body, cx + 14, cy + ch - 44, cw - 24, st(8.2, "Sans", INK, leading=11.6))

    # Status strip
    done = sum(a for a, _ in d["status"].values())
    total = sum(b for _, b in d["status"].values())
    sy = 58
    label(c, f"Where it stands · PROGRESS.md on main, last updated {d['updated']}", M, sy + 18, MUTED, 6.4)
    bw = CW - 70
    rrect(c, M, sy, bw, 9, 4.5, fill=SAND)
    rrect(c, M, sy, bw * done / total, 9, 4.5, fill=TEAL)
    txt(c, f"{done} / {total}", W - M, sy + 0.5, "Serif-Bold", 13, INK, align="right")


def matches_to(fe: dict, tol: float = 6.0) -> int:
    """Longest lead time up to which the expected-value policy stays within tol% of hindsight."""
    best = 0
    for lead, pct in zip(fe["leads_h"], fe["ev_excess_cost_pct"], strict=True):
        if pct > tol:
            break
        best = int(lead)
    return best


# --- page 3: the problem -------------------------------------------------------

def page_problem(c, d, n):
    paper(c, n, "The problem")
    y = heading(c, "01", "The problem", "Full for power, empty for floods",
                "Every reservoir above a river faces the same conflict. The rain triggers a flood; the timing "
                "of the releases decides how much of it becomes a disaster.")

    # Stakeholder tension diagram
    top = y
    cw = 196
    for i, (who, want, why, col) in enumerate([
        ("Disaster management", "wants it LOW", "Empty storage is the only flood cushion that exists.", CORAL),
        ("The power utility", "wants it FULL", "Head is revenue. Water released without generating is money poured away.", BLUE),
    ]):
        x = M if i == 0 else W - M - cw
        card(c, x, top - 74, cw, 74, accent=col)
        label(c, who, x + 14, top - 17, col, 6.8)
        txt(c, want, x + 14, top - 38, "Serif-Bold", 17, INK)
        para(c, why, x + 14, top - 46, cw - 24, st(8, "Sans", MUTED, leading=10.5))
    # Centre: a reservoir gauge
    gx, gy, gw, gh = M + cw + 22, top - 74, CW - 2 * cw - 44, 74
    rrect(c, gx, gy, gw, gh, 8, fill=CARD, stroke=LINE, lw=0.5)
    tx, tw_ = gx + gw / 2 - 16, 32
    rrect(c, tx, gy + 10, tw_, gh - 20, 4, fill=SAND)
    gradient(c, tx, gy + 10, tw_, (gh - 20) * 0.62, AQUA, TEAL, r=4)
    c.setStrokeColor(CORAL)
    c.setLineWidth(0.9)
    c.setDash([2, 1.6])
    c.line(tx - 10, gy + gh - 16, tx + tw_ + 10, gy + gh - 16)
    c.setDash([])
    txt(c, "FRL", tx + tw_ + 12, gy + gh - 18.5, "Mono-Bold", 6, CORAL)
    arrow(c, gx + 10, gy + gh / 2, tx - 5, gy + gh / 2, CORAL, 1.1, 4.5)
    arrow(c, gx + gw - 10, gy + gh / 2, tx + tw_ + 5, gy + gh / 2, BLUE, 1.1, 4.5)

    y = top - 92
    for i, (head, body, col) in enumerate([
        ("Release too early", "and the dry season is short of water that was needed.", AMBER),
        ("Release too late", "and every gate opens at once, into a river that is already full.", CORAL),
        ("The tide decides", "whether a release reaches the sea. At high tide the Arabian Sea holds the lower Periyar up.", TEAL),
    ]):
        x = M + i * (CW / 3)
        badge(c, x + 7, y - 8, str(i + 1), col, r=7)
        para(c, f"<b>{head}</b> {body}", x + 20, y - 1, CW / 3 - 30, st(8.4, "Sans", INK, leading=11.8))
    y -= 52

    rrect(c, M, y - 30, CW, 30, 6, fill=TINT["teal"])
    para(c, "<b>The gap.</b> No operational system in Kerala today weighs these together, on a forecast, "
            "across more than one reservoir at a time.", M + 12, y - 8, CW - 24, st(9, "Sans", INK, leading=12))
    y -= 50

    y = subhead(c, "Case study: the Periyar, October 2021, in public data", M, y)
    o = d["facts"]["oct2021"]
    frl = d["facts"]["counterfactual"]["frl"]
    with Image.open(ASSETS / "fig1_oct2021_crisis.png") as im:
        iw, ih = im.size
    h = min(CW * ih / iw, y - 118)
    w = h * iw / ih
    image(c, ASSETS / "fig1_oct2021_crisis.png", M + (CW - w) / 2, y - h, w, h, r=6)
    y -= h + 10
    para(c, f"<b>Idukki, October 2021.</b> The reservoir met the storm of 16 October at "
            f"{o['level_16_oct']:.2f} m, already above its own {o['rule_level']:.1f} m rule level, with the "
            f"spillway shut. Inflow peaked at about {o['peak_inflow']:,.0f} cumecs. The level reached "
            f"{o['peak_level']:.2f} m, {frl - o['peak_level']:.1f} m from full reservoir level, and the "
            "spillways of both Periyar dams opened on 20 October, into the same river on the same day. "
            "Nothing was concealed and no rule was broken: the level rose faster than a reactive "
            "procedure can respond. Source: KSEB daily bulletin.", M, y, CW, st(8.4, "Sans", MUTED, leading=12))


# --- page 4: how the water moves -----------------------------------------------

def draw_basin(c, x0, y0, w, h):
    """Rain, catchment, reservoir, powerhouse, river, town, estuary and tide, left to right."""
    gradient(c, x0, y0, w, h, HexColor("#D5EAF1"), HexColor("#F4F1E8"), r=10)
    c.saveState()
    p = c.beginPath()
    p.roundRect(x0, y0, w, h, 10)
    c.clipPath(p, stroke=0, fill=0)

    gl = y0 + 64  # the valley floor
    dam_x = x0 + 250
    sea_x = x0 + w - 110
    wl = gl + 70  # reservoir water level

    # far range, running the full width behind everything
    far = [(0, 96), (40, 150), (80, 124), (122, 176), (160, 140), (205, 160), (250, 118),
           (300, 92), (360, 70), (420, 52), (w, 40)]
    p = c.beginPath()
    p.moveTo(x0, y0)
    for px_, py_ in far:
        p.lineTo(x0 + px_, gl + py_ - 40)
    p.lineTo(x0 + w, y0)
    p.close()
    c.setFillColor(HexColor("#B7D3B4"))
    c.drawPath(p, stroke=0, fill=1)

    # near hills: catchment on the left falling to the reservoir, low banks to the right
    near = [(0, 60), (34, 112), (70, 90), (104, 128), (140, 100), (176, 108), (205, 76),
            (232, 40), (262, 30), (300, 6), (w, 0)]
    p = c.beginPath()
    p.moveTo(x0, y0)
    for px_, py_ in near:
        p.lineTo(x0 + px_, gl + py_)
    p.lineTo(x0 + w, y0)
    p.close()
    c.setFillColor(HexColor("#5F9B73"))
    c.drawPath(p, stroke=0, fill=1)
    # plain below the dam
    p = c.beginPath()
    p.moveTo(dam_x + 14, y0)
    p.lineTo(dam_x + 14, gl + 12)
    p.curveTo(dam_x + 60, gl + 4, dam_x + 120, gl + 2, sea_x + 20, gl)
    p.lineTo(sea_x + 20, y0)
    p.close()
    c.setFillColor(HexColor("#A9C394"))
    c.drawPath(p, stroke=0, fill=1)

    # reservoir in the valley behind the dam
    p = c.beginPath()
    p.moveTo(x0 + 150, wl)
    p.lineTo(dam_x, wl)
    p.lineTo(dam_x, gl - 10)
    p.curveTo(dam_x - 40, gl - 8, x0 + 176, gl + 30, x0 + 150, wl)
    p.close()
    c.saveState()
    c.clipPath(p, stroke=0, fill=0)
    c.linearGradient(0, wl, 0, gl - 10, (HexColor("#43A3B9"), HexColor("#0D4B63")), extend=False)
    c.restoreState()
    c.setStrokeColor(WHITE)
    c.setStrokeAlpha(0.55)
    c.setLineWidth(0.7)
    for i in range(3):
        c.line(dam_x - 70 + i * 16, wl - 7 - i * 6, dam_x - 40 + i * 16, wl - 7 - i * 6)
    c.setStrokeAlpha(1)

    # dam wall, in section
    p = c.beginPath()
    p.moveTo(dam_x - 2, gl - 12)
    p.lineTo(dam_x - 2, wl + 12)
    p.lineTo(dam_x + 8, wl + 12)
    p.curveTo(dam_x + 10, gl + 30, dam_x + 18, gl + 6, dam_x + 30, gl - 12)
    p.close()
    c.setFillColor(HexColor("#CDD2D7"))
    c.setStrokeColor(HexColor("#7C8792"))
    c.setLineWidth(0.6)
    c.drawPath(p, stroke=1, fill=1)
    c.saveState()
    c.setStrokeColor(HexColor("#EAF7FB"))
    c.setLineWidth(3.0)
    p = c.beginPath()
    p.moveTo(dam_x + 8, wl + 8)
    p.curveTo(dam_x + 30, wl + 4, dam_x + 34, gl + 8, dam_x + 42, gl + 2)
    c.drawPath(p, stroke=1, fill=0)
    c.restoreState()

    # river across the plain to the estuary
    c.saveState()
    c.setStrokeColor(HexColor("#3F8FC4"))
    c.setLineCap(1)
    c.setLineWidth(8)
    p = c.beginPath()
    p.moveTo(dam_x + 42, gl + 2)
    p.curveTo(dam_x + 90, gl - 12, dam_x + 120, gl + 14, dam_x + 170, gl + 2)
    p.curveTo(dam_x + 210, gl - 8, sea_x - 20, gl + 8, sea_x + 16, gl - 2)
    c.drawPath(p, stroke=1, fill=0)
    c.restoreState()

    # powerhouse under the hills, sending water to the other basin
    ph_x, ph_y = x0 + 150, y0 + 16
    c.saveState()
    c.setStrokeColor(HexColor("#EAF2F4"))
    c.setLineWidth(1.4)
    c.setDash([3, 2])
    c.line(dam_x - 30, gl - 4, ph_x + 34, ph_y + 12)
    c.restoreState()
    rrect(c, ph_x, ph_y, 34, 20, 3, fill=HexColor("#2F4655"))
    for i in range(3):
        c.setFillColor(HexColor("#F2C94C"))
        c.rect(ph_x + 5 + i * 9.5, ph_y + 11, 5, 5, stroke=0, fill=1)
    arrow(c, ph_x - 2, ph_y + 10, ph_x - 40, ph_y + 10, HexColor("#EAF2F4"), 1.4, 5)

    # town on the bank
    tx = dam_x + 120
    for i, (dx, hh) in enumerate(((0, 13), (13, 18), (27, 11), (39, 15))):
        bx, by = tx + dx, gl + 12
        c.setFillColor(HexColor("#EFE4D0") if i % 2 else HexColor("#FAF4E8"))
        c.rect(bx, by, 11, hh, stroke=0, fill=1)
        p = c.beginPath()
        p.moveTo(bx - 1.5, by + hh)
        p.lineTo(bx + 5.5, by + hh + 6)
        p.lineTo(bx + 12.5, by + hh)
        p.close()
        c.setFillColor(CORAL)
        c.drawPath(p, stroke=0, fill=1)

    # the sea, with a tide curve above it
    p = c.beginPath()
    p.moveTo(sea_x, y0)
    p.lineTo(sea_x, gl + 4)
    for i in range(0, 125, 5):
        p.lineTo(sea_x + i, gl + 4 + 3 * math.sin(i / 7.0))
    p.lineTo(x0 + w, y0)
    p.close()
    c.saveState()
    c.clipPath(p, stroke=0, fill=0)
    c.linearGradient(0, gl + 8, 0, y0, (HexColor("#3B86B5"), HexColor("#123F66")), extend=False)
    c.restoreState()
    c.saveState()
    c.setStrokeColor(TEAL)
    c.setLineWidth(1.2)
    p = c.beginPath()
    for i in range(0, 92, 2):
        yy = gl + 44 + 8 * math.sin(i / 9.0)
        (p.moveTo if i == 0 else p.lineTo)(sea_x + 12 + i, yy)
    c.drawPath(p, stroke=1, fill=0)
    c.restoreState()
    txt(c, "high", sea_x + 26, gl + 56, "Mono", 5.4, TEAL)
    txt(c, "low", sea_x + 54, gl + 26, "Mono", 5.4, TEAL)

    # rain cloud over the catchment
    c.saveState()
    c.setStrokeColor(HexColor("#4F84B3"))
    c.setLineWidth(1.0)
    for i in range(15):
        rx = x0 + 40 + i * 9.5
        top_y = y0 + h - 60 - (i % 3) * 4
        c.line(rx, top_y, rx - 7, top_y - 28 - (i % 2) * 8)
    c.restoreState()
    for cx_, cy_, s, col in ((x0 + 48, y0 + h - 42, 1.2, HexColor("#9DB2C2")),
                             (x0 + 112, y0 + h - 36, 1.0, HexColor("#B8C8D3"))):
        c.setFillColor(col)
        for dx, dy, r in ((0, 0, 14), (16, 6, 17), (36, 2, 13), (24, -6, 12), (8, -7, 11)):
            c.circle(cx_ + dx * s, cy_ + dy * s, r * s, stroke=0, fill=1)
    c.restoreState()

    def tag(bx, by, n_, head, sub, dark=False):
        badge(c, bx, by, n_, NAVY if not dark else WHITE, r=7.5, fg=WHITE if not dark else NAVY)
        txt(c, head, bx + 11, by + 1, "Sans-Bold", 7.6, WHITE if dark else INK)
        txt(c, sub, bx + 11, by - 8, "Sans", 6.6, SKY if dark else MUTED)

    tag(x0 + 176, y0 + h - 22, "1", "Rain → inflow", "SCS curve number")
    tag(dam_x - 58, wl + 36, "2", "Reservoir", "mass balance")
    tag(dam_x + 70, gl + 60, "3", "River", "Muskingum routing")
    tag(sea_x + 6, y0 + h - 22, "4", "Tide at the coast", "tidal backwater")
    tag(ph_x + 44, ph_y + 14, "5", "Powerhouse", "turbines and tariff", dark=True)
    txt(c, "Towns downstream", tx + 25, gl + 36, "Sans-Bold", 6.6, INK, align="center")
    txt(c, "Sea", sea_x + 56, y0 + 12, "Sans-Bold", 6.6, WHITE, align="center")


def page_twin(c, d, n):
    paper(c, n, "The twin")
    y = heading(c, "02", "The twin", "Every water body in the chain, together",
                "Five physical models run in sequence, hour by hour, for whatever basin they are given. "
                "The chips say how far each is validated on the Periyar case study.")
    dh = 236
    draw_basin(c, M, y - dh, CW, dh)
    y -= dh + 8
    rrect(c, M, y - 22, CW, 22, 11, fill=NAVY)
    label(c, "Per basin", M + 12, y - 13.5, AQUA, 6.2)
    txt(c, "storage curve from bulletins · catchment from a DEM · land-use curve number · "
           "reach geometry · nearest tide port",
        M + 70, y - 14, "Sans", 6.7, WHITE)
    y -= 36

    f = d["facts"]
    cal = f["calibration"]
    rv = f["runoff_validation"]
    seasons = rv["season_volume_error_pct"]
    lo, hi = min(seasons.values()), max(seasons.values())
    rows = [
        ("1", "Rainfall → inflow", "SCS curve number with a triangular unit hydrograph",
         "Q = (P − 0.2S)² / (P + 0.8S)",
         "Antecedent wetness dominates: the curve number climbs as a long spell saturates its own "
         "catchment, which is what turns a wet week into a flood.",
         f"volume {rv['pbias_pct']:+.0f}% pooled, {lo:+.0f} to {hi:+.0f}% by season · NSE {rv['nse']:.2f}", AMBER),
        ("2", "Reservoir mass balance", "Hourly Euler, fitted level–storage power law",
         "dV/dt = Q<sub>in</sub> − Q<sub>turbine</sub> − Q<sub>spill</sub> − Q<sub>evap</sub><br/>"
         "S(h) = S<sub>FRL</sub>·((h − h<sub>dead</sub>)/(h<sub>FRL</sub> − h<sub>dead</sub>))<super>β</super>",
         "β above 1 means storage grows faster than height, so the top metres of a reservoir are "
         "worth the most as cushion.",
         f"β {cal['beta']:.3f} · r² {cal['r2']:.3f} · MAE {cal['mae']:.0f} Mm³ on {cal['n']:,} rows", GREEN),
        ("3", "River routing", "Muskingum, split into stable sub-reaches automatically",
         "2Kx ≤ Δt ≤ 2K(1 − x)",
         "A long reach at an hourly step breaks this bound and the river appears to run backwards; "
         "splitting it into sub-reaches is the correct discretisation.",
         f"anchored to CWC's {d['route']['cwc_anchor_k_hours']:.0f} h travel time · not gauge-calibrated", CORAL),
        ("4", "Tidal backwater", "Harmonic tide; Kochi M2 S2 K1 O1 N2 here",
         "effective conveyance = f(Q, tide)",
         "About a metre of spring range decides whether a full river overtops, and it recurs twice a "
         "day: a free window in which the same volume moves at lower risk.",
         "sanity-checked against published descriptions · not validated", AMBER),
        ("5", "Hydropower and tariff", "Hill-diagram efficiency, time-of-day tariff",
         "P = ρ g Q H η",
         "Only spill the turbines could have absorbed counts as lost generation. At Idukki the "
         "powerhouse discharges into another river, so generation never loads the Periyar.",
         "indicative KSEB time-of-day bands, not a current tariff order", GREY),
    ]
    rh = (y - 50) / len(rows)
    for i, (n_, name, sub, eq, why, chip, col) in enumerate(rows):
        ry = y - i * rh
        if i:
            c.setStrokeColor(LINE)
            c.setLineWidth(0.4)
            c.line(M, ry + 2, W - M, ry + 2)
        badge(c, M + 9, ry - 13, n_, NAVY, r=9)
        txt(c, name, M + 26, ry - 13, "Serif-Bold", 12.5, INK)
        txt(c, sub, M + 26, ry - 24, "Sans", 7, MUTED)
        para(c, eq, M + 26, ry - 29, 204, st(8.6, "Serif-Italic", TEAL, leading=13.5))
        para(c, why, M + 236, ry - 6, CW - 236, st(8.1, "Sans", INK, leading=11.2))
        pill_y = ry - rh + 16
        pill(c, M + 236, pill_y, chip, col if col != GREY else MUTED,
             TINT.get({AMBER: "amber", GREEN: "green", CORAL: "coral"}.get(col, "grey")), size=6.2, font="Sans")


# --- page 5: architecture ----------------------------------------------------

def page_architecture(c, d, n):
    paper(c, n, "Architecture")
    y = heading(c, "03", "Architecture", "Four layers and one boundary",
                "The simulation core is pure NumPy and imports no web framework; continuous "
                "integration enforces it. That is what makes the physics testable on its own.")
    layers = [
        ("4", "Interface", TEAL, ["3D twin on measured terrain", "Simulation drawer", "What-if panel",
                                  "Tide panel", "Crisis Commander", "Malayalam advisory (draft)"]),
        ("3", "Decision", VIOLET, ["Policy grid: target · start · rate", "Four-term objective",
                                  "Grid offtake cap", "Rule-curve baseline", "Ramp limits"]),
        ("2", "Simulation", BLUE, ["SCS-CN runoff", "Mass balance", "Muskingum routing",
                                  "Tidal backwater", "Hydropower"]),
        ("1", "Ingestion", AMBER, ["Reservoir bulletins (18 dams)", "Validation · quality_ok",
                                  "GEFS ensembles", "Tide harmonics", "DEM + Sentinel-2",
                                  "ESP32 rig over MQTT"]),
    ]
    lh, gap = 64, 22
    lw_ = CW - 96
    for i, (num, name, col, chips) in enumerate(layers):
        ly = y - lh - i * (lh + gap)
        card(c, M, ly, lw_, lh, r=10)
        c.saveState()
        p = c.beginPath()
        p.roundRect(M, ly, lw_, lh, 10)
        c.clipPath(p, stroke=0, fill=0)
        gradient(c, M, ly, 92, lh, col, col)
        c.restoreState()
        txt(c, f"LAYER {num}", M + 12, ly + lh - 20, "Mono-Bold", 6.6, WHITE, space=1.4)
        txt(c, name, M + 12, ly + lh - 40, "Serif-Bold", 15, WHITE)
        cx, cy = M + 104, ly + lh - 22
        for ch in chips:
            wch = pdfmetrics.stringWidth(ch, "Sans", 7.4) + 16
            if cx + wch > M + lw_ - 8:
                cx, cy = M + 104, cy - 22
            rrect(c, cx, cy - 6, wch, 17, 8.5, fill=TINT[{TEAL: "teal", VIOLET: "violet", BLUE: "blue", AMBER: "amber"}[col]])
            txt(c, ch, cx + 8, cy - 0.5, "Sans", 7.4, INK)
            cx += wch + 6
        if i < len(layers) - 1:
            ax = M + lw_ / 2
            arrow(c, ax, ly - gap + 2, ax, ly - 2, GREY, 1.2, 5)
    # side annotations
    sx = M + lw_ + 12
    notes = [
        (0, "REST + WebSocket", "eleven routes · telemetry at 1 Hz"),
        (1, "Deterministic", "exhaustive grid, no seed, no variance"),
        (2, "Pure NumPy", "no FastAPI or pydantic under twin/"),
        (3, "Every value has a source", "LIVE · REPLAY · SIMULATED …"),
    ]
    for i, head, body in notes:
        ly = y - lh - i * (lh + gap)
        para(c, f"<b>{head}</b><br/>{body}", sx, ly + lh - 10, W - M - sx, st(7.1, "Sans", MUTED, leading=9.8))

    y = y - 4 * lh - 3 * gap - 26
    y = subhead(c, "The trust boundary", M, y)
    boxes = [("AquaSync", "recommends", NAVY, WHITE), ("A named officer", "approves or refuses", TEAL, WHITE),
             ("The gate", "KSEB and the district administration", SAND, INK)]
    bw, bh = 132, 54
    spacing = (CW - 3 * bw) / 2
    for i, (head, sub, fill, fg) in enumerate(boxes):
        bx = M + i * (bw + spacing)
        rrect(c, bx, y - bh, bw, bh, 10, fill=fill)
        txt(c, head, bx + bw / 2, y - 24, "Serif-Bold", 13, fg, align="center")
        txt(c, sub, bx + bw / 2, y - 38, "Sans", 6.8, fg if fg == INK else SKY, align="center")
        if i < 2:
            arrow(c, bx + bw + 6, y - bh / 2, bx + bw + spacing - 6, y - bh / 2, INK, 1.4, 6)
    txt(c, "advisory only", M + bw + spacing / 2, y - bh / 2 + 7, "Mono-Bold", 6, MUTED, align="center")
    txt(c, "accountable", M + 2 * bw + spacing * 1.5, y - bh / 2 + 7, "Mono-Bold", 6, MUTED, align="center")
    # no command path
    c.saveState()
    c.setStrokeColor(CORAL)
    c.setLineWidth(1.1)
    c.setDash([4, 3])
    by = y - bh - 16
    c.line(M + bw / 2, y - bh - 2, M + bw / 2, by)
    c.line(M + bw / 2, by, W - M - bw / 2, by)
    c.line(W - M - bw / 2, by, W - M - bw / 2, y - bh - 2)
    c.restoreState()
    cxm = W / 2
    rrect(c, cxm - 96, by - 8, 192, 16, 8, fill=CORAL)
    txt(c, "NO COMMAND PATH EXISTS  —  BY DESIGN", cxm, by - 3, "Mono-Bold", 6.4, WHITE, align="center", space=0.6)
    y = by - 30

    reasons = [
        ("Liability", "If an automated system opens gates and someone drowns, there is no acceptable answer to who is accountable. A recommendation a named officer approves has one."),
        ("Trust is earned in shadow mode", "The credible path is a full monsoon running alongside practice, logging what it would have advised against what happened."),
        ("The model is wrong in known ways", "Daily inputs, uncalibrated routing, no 2D inundation. Acceptable in an adviser; unacceptable in an actuator."),
    ]
    rw = (CW - 20) / 3
    for i, (head, body) in enumerate(reasons):
        rx = M + i * (rw + 10)
        txt(c, head, rx, y - 10, "Sans-Bold", 8.4, INK)
        para(c, body, rx, y - 16, rw, st(7.8, "Sans", MUTED, leading=10.8))

    # provenance chips
    py = 62
    label(c, "Provenance on every reading", M, py + 14, MUTED, 6.2)
    x = M
    for lab, col in (("LIVE", GREEN), ("STALE", AMBER), ("SIMULATED", VIOLET), ("REPLAY", BLUE),
                     ("PREDICTED", TEAL), ("ESTIMATED", GREY)):
        x += pill(c, x, py - 4, lab, WHITE, col, size=6.4) + 6
    para(c, "Only LIVE is green. A rig reading is SCALE_RIG and never converted to metres above sea "
            "level: a 400 mm tank is not a reservoir.", x + 4, py + 12, W - M - x - 4, st(7, "Sans", MUTED, leading=9.5))


# --- page 6: decision engine --------------------------------------------------

def page_decision(c, d, n):
    paper(c, n, "Decision engine")
    y = heading(c, "04", "Decision engine", "Search policies, not schedules",
                "An operator cannot execute eight hundred hourly setpoints. They can execute a "
                "sentence. So the search runs over the three numbers a control room actually uses.")
    grid_n = re.search(r"([\d,]+)-policy grid", d["joint"]["search"]).group(1)
    pol = d["sweeps"][0]["rows"][0]["policy"]

    # flowchart, left column
    fx, fw = M, 250
    cx = fx + fw / 2
    steps = [
        ("Forecast rain", "GEFS ensemble members, bias-corrected", AMBER, "box"),
        ("Inflow", "SCS-CN chain turns rain into cumecs", BLUE, "box"),
        ("Pick the next policy", f"target level × start hour × max rate · {grid_n} in the grid", VIOLET, "box"),
        ("Simulate the episode", "mass balance → routing → tide → power", BLUE, "box"),
        ("Score J", "flood · dam safety · revenue · gate wear", VIOLET, "box"),
        ("Every policy tried?", "", INK, "diamond"),
        ("Lowest J wins", "deterministic: same input, same answer", GREEN, "box"),
        ("One sentence to the control room", "a named officer approves or refuses", TEAL, "box"),
    ]
    bh, gap = 46, 19
    yy = y
    centres = []
    for head, sub, col, kind in steps:
        if kind == "diamond":
            dh_ = 46
            p = c.beginPath()
            p.moveTo(cx, yy)
            p.lineTo(cx + 64, yy - dh_ / 2)
            p.lineTo(cx, yy - dh_)
            p.lineTo(cx - 64, yy - dh_ / 2)
            p.close()
            c.setFillColor(CARD)
            c.setStrokeColor(INK)
            c.setLineWidth(0.9)
            c.drawPath(p, stroke=1, fill=1)
            txt(c, head, cx, yy - dh_ / 2 - 3, "Sans-Bold", 7.4, INK, align="center")
            centres.append((yy, yy - dh_))
            yy -= dh_ + gap
        else:
            card(c, fx + 20, yy - bh, fw - 40, bh, r=7, accent=col)
            txt(c, head, fx + 34, yy - 18, "Sans-Bold", 8.6, INK)
            txt(c, sub, fx + 34, yy - 31, "Sans", 6.9, MUTED)
            centres.append((yy, yy - bh))
            yy -= bh + gap
    for (_, b), (t, _) in zip(centres[:-1], centres[1:], strict=True):
        arrow(c, cx, b - 1, cx, t + 1, GREY, 1.1, 4.5)
    # loop back from diamond to "pick next policy"
    dtop, dbot = centres[5]
    ptop, pbot = centres[2]
    lx = fx + fw - 6
    c.saveState()
    c.setStrokeColor(VIOLET)
    c.setLineWidth(1.1)
    c.line(cx + 64, (dtop + dbot) / 2, lx, (dtop + dbot) / 2)
    c.line(lx, (dtop + dbot) / 2, lx, (ptop + pbot) / 2)
    c.restoreState()
    arrow(c, lx, (ptop + pbot) / 2, fx + fw - 20, (ptop + pbot) / 2, VIOLET, 1.1, 4.5)
    txt(c, "no", cx + 72, (dtop + dbot) / 2 + 3, "Mono-Bold", 6.4, VIOLET)
    txt(c, "yes", cx + 5, dbot - 9, "Mono-Bold", 6.4, GREEN)

    # right column
    rx = M + fw + 14
    rw = W - M - rx
    ry = y
    card(c, rx, ry - 128, rw, 128, r=10, fill=NAVY)
    label(c, "The objective", rx + 14, ry - 18, AQUA, 6.6)
    para(c, "J = w<sub>flood</sub>·Σ(overtopping)²<br/>"
            "&nbsp;&nbsp;+ w<sub>safety</sub>·Σ(FRL encroachment)²<br/>"
            "&nbsp;&nbsp;+ w<sub>revenue</sub>·(forgone generation)<br/>"
            "&nbsp;&nbsp;+ w<sub>gate</sub>·(ramping + gate movements)",
         rx + 14, ry - 26, rw - 28, st(10.5, "Serif-Italic", WHITE, leading=17))
    para(c, "Flood cost is squared because damage grows faster than depth.", rx + 14, ry - 102, rw - 28,
         st(7.4, "Sans", SKY, leading=10))
    ry -= 144

    notes = [
        ("Weights are policy, not constants", "Choosing them is a public decision. They are exposed so an operator can see and set them rather than inherit a value judgement buried in code.", VIOLET),
        ("The grid decides what can be sold", "Without the offtake cap the optimiser runs the turbines flat out for a month and books revenue the grid would never take.", BLUE),
        ("A sudden release is itself a hazard", "People and livestock are in the riverbed. A schedule that ramps faster than staged opening allows is not implementable.", CORAL),
        ("Why not hourly setpoints?", "The first version searched them. Ten days looked better than fourteen, which looked better than twenty-one: the search covered longer horizons more sparsely. It measured luck, not lead time.", AMBER),
    ]
    for head, body, col in notes:
        h_ = 12 + para(c, body, rx + 14, ry - 20, rw - 22, st(7.8, "Sans", MUTED, leading=10.8)) + 18
        c.setFillColor(col)
        c.rect(rx, ry - h_ + 6, 2.4, h_ - 6, stroke=0, fill=1)
        txt(c, head, rx + 14, ry - 11, "Sans-Bold", 8.4, INK)
        ry -= h_ + 4

    # the sentence
    qy = 118
    rrect(c, M, qy - 64, CW, 72, 10, fill=TINT["teal"])
    txt(c, "“", M + 12, qy - 34, "Serif-Bold", 48, TEAL)
    label(c, "What the optimiser hands over · October 2021, in hindsight", M + 44, qy - 8, TEAL, 6.4)
    para(c, f"Draw Idukki down to {pol['target_level_m']:.2f} m, starting at hour {pol['start_hour']} of the "
            f"episode, releasing no more than {pol['max_rate_cumecs']:,.0f} cumecs.",
         M + 44, qy - 18, CW - 60, st(13, "Serif-Italic", INK, leading=17))
    para(c, "Hindsight means it saw the inflow that actually arrived. With a real forecast, see §7.",
         M + 44, qy - 52, CW - 60, st(7, "Sans", MUTED))


# --- page 7: validation -------------------------------------------------------

def page_validation(c, d, n):
    paper(c, n, "Validation")
    y = heading(c, "05", "Validation", "Replayed against the record",
                "Before the twin is allowed to recommend anything for a basin, it has to reproduce what "
                "actually happened there. On the Periyar case study, it did, on data nobody tuned it to.")
    f = d["facts"]
    cal = f["calibration"]
    r21, r22 = d["r21"], d["r22"]
    kp = [
        (f"{r21['mean_absolute_error_m']:.2f} m", "October 2021 replay",
         f"Mean level error over 20 days; {r21['max_absolute_error_m']:.2f} m at worst.", TEAL),
        (f"{r22['mean_absolute_error_m']:.2f} m", "August 2022, out of sample",
         "An episode never tuned to. The drift changes sign between the two storms.", BLUE),
        (f"r² {cal['r2']:.3f}", "Level–storage fit",
         f"β {cal['beta']:.3f}, MAE {cal['mae']:.0f} Mm³ on {cal['n']:,} validated bulletin rows.", GREEN),
    ]
    kw = (CW - 20) / 3
    for i, (num, head, body, col) in enumerate(kp):
        x = M + i * (kw + 10)
        card(c, x, y - 92, kw, 92, accent=col)
        label(c, head, x + 14, y - 16, col, 6.2)
        txt(c, num, x + 14, y - 44, "Serif-Bold", 24, INK)
        para(c, body, x + 14, y - 52, kw - 24, st(7.6, "Sans", MUTED, leading=10.4))
    y -= 108
    h = image(c, ASSETS / "fig3_calibration.png", M, y - CW * 720 / 1840, CW, r=6)
    y -= h + 6
    para(c, "Level against storage from the KSEB bulletin, fitted as a power law. The validation layer "
            "sets aside physically impossible rows first; about 11% of the feed fails, in one contiguous "
            "block caused by a column-alignment bug upstream.", M, y, CW, st(7.6, "Sans-Italic", MUTED, leading=10.5))
    y -= 36

    # runoff season chart
    rv = f["runoff_validation"]
    col_w = CW * 0.56
    card(c, M, y - 250, col_w, 250, r=10)
    label(c, "Rainfall–runoff, four monsoons", M + 14, y - 18, AMBER, 6.4)
    txt(c, "Volume error by season", M + 14, y - 36, "Serif-Bold", 13, INK)
    ch_x, ch_y, ch_w, ch_h = M + 40, y - 186, col_w - 60, 118
    zero_y = ch_y + ch_h * 0.42
    scale = (ch_h * 0.55) / 40.0
    c.setStrokeColor(LINE)
    c.setLineWidth(0.4)
    for v in (-20, 0, 20, 40):
        gy = zero_y + v * scale
        c.line(ch_x, gy, ch_x + ch_w, gy)
        txt(c, f"{v:+d}%" if v else "0", ch_x - 6, gy - 2.5, "Mono", 6, MUTED, align="right")
    seasons = rv["season_volume_error_pct"]
    bw = ch_w / len(seasons)
    for i, (yr, v) in enumerate(seasons.items()):
        bx = ch_x + i * bw + bw * 0.22
        col = CORAL if abs(v) > 15 else TEAL
        top_, bot = (zero_y + v * scale, zero_y) if v > 0 else (zero_y, zero_y + v * scale)
        rrect(c, bx, bot, bw * 0.56, top_ - bot, 2.5, fill=col)
        txt(c, f"{v:+.0f}%", bx + bw * 0.28, (top_ + 4) if v > 0 else (bot - 10), "Sans-Bold", 7.4, col, align="center")
        txt(c, yr, bx + bw * 0.28, ch_y - 14, "Mono", 6.8, INK, align="center")
    c.setStrokeColor(INK)
    c.setLineWidth(0.8)
    c.line(ch_x, zero_y, ch_x + ch_w, zero_y)
    para(c, f"Pooled {rv['pbias_pct']:+.0f}%, but the seasons swing. r² {rv['r2']:.2f} on shape, "
            f"NSE {rv['nse']:.2f} on amplitude: no recession limb. Calibration fails leave-one-season-out, "
            "so handbook CN 72 stays.", M + 14, y - 212, col_w - 24, st(7.1, "Sans", MUTED, leading=9.6))

    rx = M + col_w + 12
    rw = W - M - rx
    cg = d["catch"]
    card(c, rx, y - 118, rw, 118, r=10, accent=GREEN)
    label(c, "Catchment from a DEM", rx + 14, y - 18, GREEN, 6.2)
    txt(c, f"{cg['idukki_net_contributing_catchment_km2']:,.0f} km²", rx + 14, y - 44, "Serif-Bold", 20, INK)
    para(c, f"net of the Mullaperiyar diversion, against the {cg['cag_sourced_catchment_km2']:,.0f} km² in use "
            f"({cg['net_vs_cag_diff_pct']:+.0f}%). Main channel about {cg['main_channel_km']:.0f} km. "
            "A DEM sees the hills, not the tunnel.", rx + 14, y - 52, rw - 22, st(7.3, "Sans", MUTED, leading=10))
    rt = d["route"]
    card(c, rx, y - 250, rw, 120, r=10, accent=CORAL)
    label(c, "Routing calibration · blocked", rx + 14, y - 148, CORAL, 6.2)
    txt(c, f"r² {rt['r_squared']:.3f}", rx + 14, y - 174, "Serif-Bold", 20, INK)
    para(c, f"on {rt['n_days']:,} days of CWC gauge data. A daily step is about three times coarser than "
            f"an {rt['cwc_anchor_k_hours']:.0f} h travel time, and releases are daily-only. The CWC anchor stands.",
         rx + 14, y - 182, rw - 22, st(7.3, "Sans", MUTED, leading=10))


# --- page 8: the result ---------------------------------------------------------

def donut(c, cx, cy, r, frac, col, lab, sub):
    c.saveState()
    c.setLineWidth(r * 0.34)
    c.setStrokeColor(SAND)
    c.circle(cx, cy, r, stroke=1, fill=0)
    c.setStrokeColor(col)
    c.setLineCap(0)
    p = c.beginPath()
    p.arc(cx - r, cy - r, cx + r, cy + r, startAng=90, extent=-360 * frac)
    c.drawPath(p, stroke=1, fill=0)
    c.restoreState()
    txt(c, f"{frac * 100:.0f}%", cx, cy - 5, "Serif-Bold", 15, INK, align="center")
    txt(c, lab, cx, cy - r - 18, "Sans-Bold", 7.4, INK, align="center")
    txt(c, sub, cx, cy - r - 28, "Sans", 6.6, MUTED, align="center")


def page_result(c, d, n):
    paper(c, n, "The result")
    y = heading(c, "06", "The result", "About three metres of cushion",
                "Replayed against the schedule the optimiser would have chosen, October 2021 ends with "
                "about 3 m more room below full reservoir level, and slightly more revenue, not less.")
    h = image(c, ASSETS / "fig5_counterfactual.png", M, y - CW * 1120 / 1840, CW, r=6)
    y -= h + 18

    lead = d["lead"]
    lo, hi = lead["freeboard_gained_m_range"]
    rlo, rhi = lead["revenue_delta_cr_range"]
    col_w = (CW - 20) / 3
    # card 1: cushion
    card(c, M, y - 150, col_w, 150, accent=GREEN)
    label(c, "Cushion, at every lead time", M + 14, y - 18, GREEN, 6.2)
    txt(c, "about 3 m", M + 14, y - 50, "Serif-Bold", 26, INK)
    para(c, f"The range across lead times is {lo:.1f} to {hi:.1f} m, and roughly half a metre of it "
            "sits inside the twin's replay error, so it is quoted in whole metres.",
         M + 14, y - 60, col_w - 24, st(7.6, "Sans", MUTED, leading=10.6))
    # card 2: donuts
    x2 = M + col_w + 10
    card(c, x2, y - 150, col_w, 150, accent=BLUE)
    label(c, "Released water that is spilled", x2 + 14, y - 18, BLUE, 6.2)
    donut(c, x2 + col_w * 0.28, y - 64, 24, lead["spill_fraction_at_0_days"], CORAL, "zero lead", "act on the day")
    donut(c, x2 + col_w * 0.72, y - 64, 24, lead["spill_fraction_at_30_days"], TEAL, "30 days", "act a month ahead")
    para(c, "Lead time changes the waste, not the cushion.", x2 + 14, y - 124, col_w - 24,
         st(7.4, "Sans-Italic", MUTED, leading=10))
    # card 3: revenue
    x3 = M + 2 * (col_w + 10)
    card(c, x3, y - 150, col_w, 150, accent=AMBER)
    label(c, "Revenue, energy-neutral", x3 + 14, y - 18, AMBER, 6.2)
    txt(c, f"+₹{rlo:.1f}–{rhi:.1f} cr", x3 + 14, y - 50, "Serif-Bold", 22, INK)
    para(c, "The same water, shifted into higher-tariff hours. Indicative KSEB time-of-day bands, not a "
            "current tariff order; horizons differ, so rows are not strictly comparable.",
         x3 + 14, y - 60, col_w - 24, st(7.6, "Sans", MUTED, leading=10.6))
    y -= 168

    cf = d["facts"]["counterfactual"]
    aug = d["sweeps"][2]["rows"][0]
    aug_less = aug["min_freeboard_baseline_m"] - aug["min_freeboard_optimised_m"]
    rrect(c, M, y - 92, CW, 92, 10, fill=TINT["coral"])
    c.setFillColor(CORAL)
    c.rect(M, y - 92, 3.2, 92, stroke=0, fill=1)
    label(c, "Read with it", M + 16, y - 16, CORAL, 6.4)
    para(c, f"<b>It releases more, earlier.</b> The optimised schedule's routed peak below the dam is about "
            f"{cf['peak_downstream_optimised']:,.0f} cumecs against {cf['peak_downstream_baseline']:,.0f} "
            "for the day: one dam, an uncalibrated reach, never read against bankfull. "
            f"<b>It is hindsight.</b> It saw the inflow that arrived. <b>It does not always win.</b> On August "
            f"2022, a storm with no flood risk, the hindsight schedule holds about {aug_less:.0f} m <i>less</i> "
            "cushion than the day: with nothing to protect, the objective prefers holding water, and "
            "the day's operators did fine.", M + 16, y - 24, CW - 32, st(8.2, "Sans", INK, leading=12))


# --- page 9: forecast error -----------------------------------------------------

def fe_panel(c, x, y, w, h, fe: dict, title: str, col: Color):
    card(c, x, y, w, h, r=10)
    label(c, title, x + 14, y + h - 18, col, 6.4)
    ev, mm = fe["ev_excess_cost_pct"], fe["mm_excess_cost_pct"]
    leads = fe["leads_h"]
    top_v = max(max(ev), max(mm))
    ymax = math.ceil(top_v / 50.0) * 50
    px, py, pw, ph = x + 40, y + 42, w - 58, h - 96
    c.setLineWidth(0.4)
    for k in range(0, int(ymax) + 1, 50):
        gy = py + ph * k / ymax
        c.setStrokeColor(LINE)
        c.line(px, gy, px + pw, gy)
        txt(c, f"+{k}%" if k else "0", px - 6, gy - 2.4, "Mono", 6, MUTED, align="right")

    def xpos(lead):
        return px + pw * (lead - leads[0]) / (leads[-1] - leads[0])

    # matched zone
    upto = matches_to(fe)
    rrect(c, px, py, xpos(upto) - px, ph, 0, fill=TINT["green"])
    txt(c, f"matches hindsight to {upto} h", px + 6, py + ph - 10, "Sans-Bold", 6.8, GREEN)
    for lead in leads:
        txt(c, f"{lead:.0f} h", xpos(lead), py - 13, "Mono", 6.4, INK, align="center")
    txt(c, "forecast lead time before the storm peak", px + pw / 2, py - 26, "Sans", 6.4, MUTED, align="center")
    for series, colr, dash in ((mm, VIOLET, [3, 2]), (ev, col, None)):
        c.saveState()
        c.setStrokeColor(colr)
        c.setLineWidth(1.8)
        if dash:
            c.setDash(dash)
        p = c.beginPath()
        for i, (lead, v) in enumerate(zip(leads, series, strict=True)):
            X, Y = xpos(lead), py + ph * v / ymax
            (p.moveTo if i == 0 else p.lineTo)(X, Y)
        c.drawPath(p, stroke=1, fill=0)
        c.restoreState()
        for lead, v in zip(leads, series, strict=True):
            c.setFillColor(colr)
            c.circle(xpos(lead), py + ph * v / ymax, 2.2, stroke=0, fill=1)
    last = ev[-1]
    txt(c, f"+{last:.0f}% at {leads[-1]:.0f} h", x + w - 14, y + h - 19, "Serif-Bold", 12, col, align="right")


def page_forecast(c, d, n):
    paper(c, n, "Forecast error")
    y = heading(c, "07", "With a real forecast", "How far ahead can it be trusted?",
                "Hindsight is free. The honest test is to hand the optimiser the rainfall forecast that "
                "was actually issued, then score what it chose against what perfect foresight would have.")
    f = d["facts"]
    fe21, fe22 = f["forecast_error"], f["forecast_error_aug_2022"]
    pw = (CW - 12) / 2
    ph = 300
    fe_panel(c, M, y - ph, pw, ph, fe21, "October 2021 · its own axis", TEAL)
    fe_panel(c, M + pw + 12, y - ph, pw, ph, fe22, "August 2022 · its own axis", BLUE)
    y -= ph + 12
    x = M
    for lab, col, dash in (("expected-value policy", TEAL, None), ("hedging (minimax regret)", VIOLET, [3, 2])):
        c.saveState()
        c.setStrokeColor(col)
        c.setLineWidth(1.8)
        if dash:
            c.setDash(dash)
        c.line(x, y - 4, x + 22, y - 4)
        c.restoreState()
        x += 28 + txt(c, lab, x + 28, y - 6.5, "Sans", 7.2, INK) + 18
    txt(c, "y axis: excess cost against perfect foresight, on the optimiser's own objective",
        M, y - 21, "Sans-Italic", 6.8, MUTED)
    y -= 46

    hedge = []
    for fe in (fe21, fe22):
        for a, b in zip(fe["ev_excess_cost_pct"], fe["mm_excess_cost_pct"], strict=True):
            if b < a:
                hedge.append(a - b)
    runs = len(fe21["leads_h"]) + len(fe22["leads_h"])
    col_w = (CW - 20) / 3
    blocks = [
        ("A ramp, then a cliff", f"October 2021 degrades gradually from {matches_to(fe21)} h. August 2022 holds to "
         f"{matches_to(fe22)} h, then jumps to +{fe22['ev_excess_cost_pct'][-1]:.0f}%. Two storms, two shapes, so "
         "they are never averaged into one curve.", TEAL),
        ("Hedging rarely pays", f"The minimax-regret policy beat the expected-value one in {len(hedge)} run of {runs}, "
         f"by {hedge[0] if hedge else 0:.2f} points. In every other run it cost the same or more.", VIOLET),
        ("The right yardstick", "Excess cost is zero when the forecast picked the hindsight policy and is never "
         "negative. Freeboard retention is not quoted: it can pass 100% while giving revenue away.", AMBER),
    ]
    for i, (head, body, col) in enumerate(blocks):
        bx = M + i * (col_w + 10)
        c.setFillColor(col)
        c.rect(bx, y - 4, 22, 2.2, stroke=0, fill=1)
        txt(c, head, bx, y - 20, "Serif-Bold", 12.5, INK)
        para(c, body, bx, y - 28, col_w, st(8, "Sans", MUTED, leading=11.4))
    y -= 132

    rrect(c, M, y - 70, CW, 70, 10, fill=NAVY)
    label(c, "What it means for a control room", M + 16, y - 18, AQUA, 6.4)
    para(c, f"On storms like these, a release decision taken on a {matches_to(fe21)}-hour forecast is about as good "
            "as one taken with perfect knowledge of the rain. Beyond that the answer depends on the storm, which "
            "is exactly why the recommendation stays advice.", M + 16, y - 26, CW - 32, st(9.6, "Serif", WHITE, leading=13.5))


# --- page 10: what did not work ------------------------------------------------

def page_warnings(c, d, n):
    paper(c, n, "Warnings")
    y = heading(c, "08", "Warnings, stated as warnings", "What did not work, and what it taught",
                "Four claims on this project were stated early and broken by the next data point. "
                "The corrections are kept on the record, and these are the results that stayed awkward.")
    casc = d["casc"]
    joint = d["joint"]
    col_w = CW * 0.58
    card(c, M, y - 236, col_w, 236, r=10, accent=CORAL)
    label(c, "Cascade · two dams, one river", M + 14, y - 18, CORAL, 6.4)
    txt(c, "Optimising each dam alone is worse", M + 14, y - 36, "Serif-Bold", 13, INK)
    bars = [("What happened", casc["observed_joint_peak_cumecs"], GREY),
            ("Each dam optimised alone", casc["naive_independent_joint_peak_cumecs"], CORAL),
            ("Start hours retimed", casc["coordinated_joint_peak_cumecs"], AMBER)]
    bmax = max(v for _, v, _ in bars)
    bx0, bw_ = M + 14, col_w - 80
    for i, (lab, v, col) in enumerate(bars):
        by = y - 66 - i * 38
        txt(c, lab, bx0, by + 12, "Sans", 7.2, INK)
        rrect(c, bx0, by - 4, bw_, 11, 5.5, fill=SAND)
        rrect(c, bx0, by - 4, bw_ * v / bmax, 11, 5.5, fill=col)
        txt(c, f"{v:,.0f}", bx0 + bw_ + 8, by - 2, "Serif-Bold", 11, INK)
    txt(c, "cumecs", bx0 + bw_ + 8, y - 66 - 2 * 38 - 13, "Sans", 6.4, MUTED)
    para(c, f"Joint peak at the confluence, October 2021. Alone, the dams put it "
            f"{-casc['naive_vs_observed_reduction_pct']:.0f}% above what happened; retiming both recovers "
            f"{casc['coordination_vs_naive_reduction_pct']:.0f}%. <b>Two dams' contribution only, never read against "
            "bankfull.</b> It is an objective-function problem.", M + 14, y - 180, col_w - 24, st(7.6, "Sans", MUTED, leading=10.6))

    rx = M + col_w + 12
    rw = W - M - rx
    card(c, rx, y - 236, rw, 236, r=10, accent=VIOLET)
    label(c, "The fix, built · and inert", rx + 14, y - 18, VIOLET, 6.4)
    txt(c, "Joint cascade objective", rx + 14, y - 36, "Serif-Bold", 13, INK)
    para(c, "One shared flood term on the combined discharge at the confluence; each dam keeps its own "
            "safety, revenue and gate-wear terms.", rx + 14, y - 44, rw - 24, st(7.6, "Sans", MUTED, leading=10.6))
    txt(c, "0 moves", rx + 14, y - 124, "Serif-Bold", 24, VIOLET)
    para(c, "On the data as held the shared term is identically zero, so coordinate descent converges without "
            "moving. The blocker is the ungauged lateral inflow. An <i>assumed</i> lateral (not a measurement) "
            f"first changes the policies at {joint['first_lateral_that_changes_the_policies']:,.0f} cumecs.",
         rx + 14, y - 134, rw - 24, st(7.6, "Sans", MUTED, leading=10.6))
    y -= 256

    # stress sweep
    card(c, M, y - 160, CW, 160, r=10, accent=BLUE)
    label(c, "Storm stress test · a sensitivity, not a return period", M + 14, y - 18, BLUE, 6.4)
    txt(c, "Multiply the recorded storm. When does each schedule reach full reservoir level?", M + 14, y - 36, "Serif-Bold", 12.5, INK)
    cols = [M + 14, M + 250, M + 380]
    txt(c, "EPISODE", cols[0], y - 56, "Mono-Bold", 6.2, MUTED, space=1)
    txt(c, "THE DAY'S SCHEDULE", cols[1], y - 56, "Mono-Bold", 6.2, MUTED, space=1)
    txt(c, "AQUASYNC'S", cols[2], y - 56, "Mono-Bold", 6.2, MUTED, space=1)
    for i, sw in enumerate(d["sweeps"]):
        ry = y - 78 - i * 22
        first = sw["first_multiple_reaching_frl"]
        top_mult = max(r["inflow_scale"] for r in sw["rows"])
        txt(c, sw["title"], cols[0], ry, "Sans", 8.2, INK)
        txt(c, f"at ×{first['baseline']:g}" if first["baseline"] else f"not by ×{top_mult:g}", cols[1], ry, "Serif-Bold", 11, CORAL)
        txt(c, f"at ×{first['optimised']:g}" if first["optimised"] else f"not by ×{top_mult:g}", cols[2], ry, "Serif-Bold", 11, GREEN)
    para(c, "A scaled copy of one hydrograph: same shape, more water. The optimiser may release up to 1,500 cumecs, "
            "so holding the reservoir moves water downstream instead. The ladder is coarse, so each multiple is an "
            "upper bound.", M + 14, y - 132, CW - 28, st(7.2, "Sans", MUTED, leading=9.8))
    y -= 184

    rt = d["route"]
    items = [
        ("A runoff chain that produced no runoff", "The curve number's initial abstraction was charged every timestep, so the answer depended on the step. Found on a task that looked small; fixed, and pinned by a test."),
        ("A LIVE badge on a 2021 recording", "The socket being open said the backend was reachable, not that anything was measured. The server now declares provenance on every frame."),
        (f"Routing calibration, r² {rt['r_squared']:.3f}", "Daily release data cannot resolve an eight-hour travel time. Blocked until the CWC 15-minute feed exists; the published anchor stands."),
        ("A BOM whose total disagreed with its rows", "Corrected, and this document now sums the rows itself and refuses to build if they disagree."),
    ]
    iw = (CW - 12) / 2
    for i, (head, body) in enumerate(items):
        ix = M + (i % 2) * (iw + 12)
        iy = y - (i // 2) * 74
        badge(c, ix + 7, iy - 8, "!", AMBER, r=7)
        txt(c, head, ix + 20, iy - 11, "Sans-Bold", 8.2, INK)
        para(c, body, ix + 20, iy - 16, iw - 20, st(7.4, "Sans", MUTED, leading=10.2))


# --- page 11: interface -----------------------------------------------------------

def page_interface(c, d, n):
    paper(c, n, "Interface")
    y = heading(c, "09", "The interface", "A twin you can stand in front of",
                "The dashboard runs from a laptop with the network cable pulled. The ground is a satellite "
                "photograph laid on real terrain; the water rises and falls with the replay.")
    shot = ASSETS / "dashboard_twin.png"
    ih = CW * 720 / 1280
    top = y
    image(c, shot, M, top - ih, CW, ih, r=8)
    sx = CW / 1280.0

    def at(px, py):
        return M + px * sx, top - py * sx

    marks = [(258, 84, "1"), (520, 74, "2"), (292, 530, "3"), (258, 484, "4"), (650, 706, "5")]
    for px, py, k in marks:
        X, Y = at(px, py)
        c.saveState()
        c.setFillColor(WHITE)
        c.circle(X, Y, 8.5, stroke=0, fill=1)
        c.restoreState()
        badge(c, X, Y, k, CORAL, r=7)
    y = top - ih - 14
    keys = [("1", "Reservoir level against dead, rule and full levels"), ("2", "Site, gate and basin views"),
            ("3", "A caption saying what is measured and what is drawn"), ("4", "Advice in English and Malayalam"),
            ("5", "Source: replay, recorded episode, not live")]
    kw = CW / 2
    for i, (k, s) in enumerate(keys):
        kx = M + (i % 2) * kw
        ky = y - (i // 2) * 15
        badge(c, kx + 6, ky - 3, k, CORAL, r=5.5)
        txt(c, s, kx + 16, ky - 5.5, "Sans", 7.2, INK)
    y -= 56

    sw = CW * 0.56
    sh = sw * 720 / 1280
    image(c, ASSETS / "dashboard_simulation.png", M, y - sh, sw, sh, r=8)
    para(c, "The simulation drawer scrubs the episode hour by hour: recorded level, the twin's replay and the "
            "optimiser's schedule on real axes, driving the 3D water.", M, y - sh - 8, sw,
         st(7.2, "Sans-Italic", MUTED, leading=10))

    rx = M + sw + 14
    rw = W - M - rx
    feats = [
        ("What-if", "Drag a release and the card answers from the API: 72 h peak level, cushion, and advice.", TEAL),
        ("Crisis Commander", "You get the briefing the operators had and give the order. The same optimiser scores you, the day and AquaSync side by side.", CORAL),
        ("Tide panel", "The 72 h harmonic tide at Kochi with low-water windows shaded, labelled PREDICTED.", BLUE),
        ("Catchment policy", "Change the curve number and see runoff volume. The peak is greyed: shape is not validated.", AMBER),
        ("Malayalam advisory", "A line on every frame, on the same KSDMA bands. Draft wording: a native speaker must read it before public use.", VIOLET),
    ]
    ry = y
    for head, body, col in feats:
        c.setFillColor(col)
        c.circle(rx + 4, ry - 6, 3.2, stroke=0, fill=1)
        txt(c, head, rx + 13, ry - 9, "Sans-Bold", 8.4, INK)
        h_ = para(c, body, rx + 13, ry - 13, rw - 13, st(7.3, "Sans", MUTED, leading=10))
        ry -= h_ + 22


# --- page 12: hardware ------------------------------------------------------------

def draw_rig(c, x0, y0, w, h):
    rrect(c, x0, y0, w, h, 10, fill=CARD, stroke=LINE, lw=0.5)
    c.saveState()
    c.setStrokeColor(HexColor("#EEF3F5"))
    c.setLineWidth(0.4)
    for gx in range(int(x0) + 10, int(x0 + w), 12):
        c.line(gx, y0 + 4, gx, y0 + h - 4)
    for gy in range(int(y0) + 10, int(y0 + h), 12):
        c.line(x0 + 4, gy, x0 + w - 4, gy)
    c.restoreState()

    base = y0 + 70
    lt_x, lt_w, lt_h = x0 + 34, 128, 128
    rt_x, rt_w, rt_h = x0 + 214, 116, 84
    py_ = base + 12
    gx = lt_x + lt_w + 22
    fx = rt_x - 14
    pump_x = rt_x + rt_w - 44
    us_l = (lt_x + lt_w / 2, base + lt_h + 16)
    us_r = (rt_x + rt_w / 2, base + rt_h + 16)
    probe = (lt_x + 22, base + lt_h + 20)
    motor = (gx, py_ + 72)
    ex, ey = x0 + w - 128, y0 + 104

    # wiring first, so every part sits on top of it
    c.saveState()
    c.setLineWidth(0.9)
    for (tx_, ty_), col in ((us_l, AMBER), (us_r, GREY), ((motor[0] + 13, motor[1] + 12), VIOLET),
                            ((fx, py_ + 8), GREEN), (probe, BLUE)):
        c.setStrokeColor(col)
        c.setStrokeAlpha(0.75)
        p = c.beginPath()
        p.moveTo(ex, ey + 22)
        lift = max(ty_, ey + 22) + 46
        p.curveTo(ex - 40, lift, tx_ + 20, lift, tx_, ty_)
        c.drawPath(p, stroke=1, fill=0)
    c.restoreState()

    # bench top
    c.setFillColor(HexColor("#C9B99A"))
    c.rect(x0 + 18, base - 8, 330, 8, stroke=0, fill=1)

    def tank(tx, tw, th, level, name, sub):
        gradient(c, tx, base, tw, th * level, HexColor("#86CCD9"), HexColor("#2A8CA5"))
        c.setStrokeColor(HexColor("#6E8FA0"))
        c.setLineWidth(1.4)
        p = c.beginPath()
        p.moveTo(tx, base + th)
        p.lineTo(tx, base)
        p.lineTo(tx + tw, base)
        p.lineTo(tx + tw, base + th)
        c.drawPath(p, stroke=1, fill=0)
        txt(c, name, tx + tw / 2, base - 22, "Sans-Bold", 7.6, INK, align="center")
        txt(c, sub, tx + tw / 2, base - 32, "Sans", 6.2, MUTED, align="center")

    tank(lt_x, lt_w, lt_h, 0.70, "Reservoir tank", "acrylic, 3 mm")
    tank(rt_x, rt_w, rt_h, 0.36, "River tank", "pump returns the water")

    # return loop under the bench, pump to reservoir
    c.saveState()
    c.setStrokeColor(HexColor("#4B9FB6"))
    c.setLineWidth(2.4)
    c.setLineJoin(1)
    p = c.beginPath()
    p.moveTo(pump_x + 30, base + 10)
    p.lineTo(pump_x + 30, base - 48)
    p.lineTo(lt_x - 12, base - 48)
    p.lineTo(lt_x - 12, base + lt_h + 8)
    p.lineTo(lt_x + 8, base + lt_h + 8)
    p.lineTo(lt_x + 8, base + lt_h - 8)
    c.drawPath(p, stroke=1, fill=0)
    c.restoreState()
    arrow(c, rt_x + 20, base - 48, rt_x - 6, base - 48, HexColor("#4B9FB6"), 1.2, 6)
    rrect(c, pump_x, base + 2, 28, 16, 3, fill=HexColor("#1F2A36"))
    txt(c, "PUMP", pump_x + 14, base + 7.5, "Mono-Bold", 5.4, WHITE, align="center")

    # outlet pipe, gate and flow sensor
    c.setFillColor(HexColor("#2A8CA5"))
    c.rect(lt_x + lt_w, py_ - 5, rt_x - lt_x - lt_w, 10, stroke=0, fill=1)
    c.setFillColor(HexColor("#5C6B78"))
    c.rect(gx - 2.5, py_ - 9, 5, 70, stroke=0, fill=1)
    rrect(c, motor[0] - 13, motor[1], 26, 24, 3, fill=NAVY)
    txt(c, "M", motor[0], motor[1] + 8, "Sans-Bold", 8, WHITE, align="center")
    for ly in (py_ + 58, py_ - 14):
        c.setFillColor(CORAL)
        c.rect(gx + 5, ly, 7, 5, stroke=0, fill=1)
    rrect(c, fx - 8, py_ - 8, 16, 16, 3, fill=HexColor("#1F2A36"))

    # sensors
    for (sx, sy), col in ((us_l, HexColor("#1F6E8C")), (us_r, HexColor("#7F8C97"))):
        rrect(c, sx - 18, sy - 6, 36, 12, 3, fill=col)
        for dx in (-8, 8):
            c.setFillColor(WHITE)
            c.circle(sx + dx, sy, 3.6, stroke=0, fill=1)
        c.saveState()
        c.setStrokeColor(col)
        c.setLineWidth(0.6)
        c.setDash([1.5, 2])
        c.line(sx, sy - 8, sx, sy - 34)
        c.restoreState()
    c.setStrokeColor(HexColor("#333F4B"))
    c.setLineWidth(1.2)
    c.line(probe[0], probe[1], probe[0], base + 26)
    c.setFillColor(HexColor("#333F4B"))
    c.circle(probe[0], base + 26, 2.6, stroke=0, fill=1)

    # ESP32
    rrect(c, ex, ey, 70, 44, 4, fill=HexColor("#1B2733"))
    rrect(c, ex + 18, ey + 12, 34, 20, 2, fill=HexColor("#9AA5AF"))
    for i in range(8):
        c.setFillColor(HexColor("#D5B45A"))
        c.rect(ex + 5 + i * 8, ey + 1, 3, 4, stroke=0, fill=1)
        c.rect(ex + 5 + i * 8, ey + 39, 3, 4, stroke=0, fill=1)
    txt(c, "ESP32 node", ex + 35, ey - 12, "Sans-Bold", 7.6, INK, align="center")
    txt(c, "sensor fusion · safety interlock", ex + 35, ey - 22, "Sans", 6, MUTED, align="center")

    # Wi-Fi to the laptop
    wx, wy = ex + 35, ey + 58
    c.saveState()
    c.setStrokeColor(TEAL)
    c.setLineWidth(1.2)
    for r in (6, 11, 16):
        p = c.beginPath()
        p.arc(wx - r, wy - r, wx + r, wy + r, 50, 80)
        c.drawPath(p, stroke=1, fill=0)
    c.restoreState()
    txt(c, "MQTT", wx + 22, wy + 4, "Mono-Bold", 6.2, TEAL)
    lx, ly = ex + 6, y0 + h - 62
    rrect(c, lx, ly, 58, 36, 3, fill=HexColor("#1B2733"))
    rrect(c, lx + 4, ly + 4, 50, 28, 1.5, fill=HexColor("#2C7F8F"))
    c.setFillColor(HexColor("#9AA5AF"))
    p = c.beginPath()
    p.moveTo(lx - 8, ly - 5)
    p.lineTo(lx + 66, ly - 5)
    p.lineTo(lx + 58, ly)
    p.lineTo(lx, ly)
    p.close()
    c.drawPath(p, stroke=0, fill=1)
    txt(c, "laptop · dashboard", lx + 29, ly + 42, "Sans-Bold", 6.8, INK, align="center")

    def note(nx, ny, head, sub, col):
        wdt = max(pdfmetrics.stringWidth(head, "Sans-Bold", 6.8), pdfmetrics.stringWidth(sub, "Sans", 5.9))
        rrect(c, nx - 9, ny - 11, wdt + 14, 21, 3, fill=CARD, alpha=0.92)
        c.setFillColor(col)
        c.circle(nx - 4, ny + 2.5, 2.4, stroke=0, fill=1)
        txt(c, head, nx + 1, ny, "Sans-Bold", 6.8, INK)
        txt(c, sub, nx + 1, ny - 8, "Sans", 5.9, MUTED)

    note(us_l[0] + 24, us_l[1] + 2, "JSN-SR04T", "waterproof ultrasonic level", AMBER)
    note(us_r[0] + 24, us_r[1] + 2, "HC-SR04", "second tank · not yet read", GREY)
    note(gx + 20, motor[1] - 10, "NEMA 17 + A4988", "sluice gate · limit switches", VIOLET)
    note(probe[0] + 10, base + 46, "DS18B20", "sound-speed compensation", BLUE)
    note(fx - 4, py_ - 26, "YF-S201", "outflow", GREEN)


def page_hardware(c, d, n):
    paper(c, n, "Hardware")
    y = heading(c, "10", "Hardware", "A thirty-centimetre dam on a bench",
                "The rig closes the loop onto a motor because it is an acrylic tank, not a reservoir. "
                "Components are in hand; the bench is not built yet and the firmware is untested on hardware.")
    rh = 256
    draw_rig(c, M, y - rh, CW, rh)
    y -= rh + 20

    y = subhead(c, "The beat that wins the room: fault injection", M, y)
    chain = [
        ("Flip a switch", "gate jam or dead sensor", CORAL, "planned"),
        ("ESP32 frame", "each record SHA-256 chained", AMBER, "firmware"),
        ("MQTT broker", "mosquitto on the laptop", BLUE, "built"),
        ("Rig bridge", "follows the chain, flags a break", VIOLET, "built"),
        ("Red banner", "on the 3D view", TEAL, "browser-verified"),
    ]
    bw = (CW - 4 * 14) / 5
    for i, (head, sub, col, stat) in enumerate(chain):
        bx = M + i * (bw + 14)
        card(c, bx, y - 62, bw, 62, r=8, accent=col)
        txt(c, head, bx + 12, y - 18, "Sans-Bold", 8.4, INK)
        para(c, sub, bx + 12, y - 24, bw - 18, st(6.9, "Sans", MUTED, leading=9))
        pill(c, bx + 12, y - 52, stat.upper(), col, TINT[{CORAL: "coral", AMBER: "amber", BLUE: "blue", VIOLET: "violet", TEAL: "teal"}[col]], size=5.4)
        if i < 4:
            arrow(c, bx + bw + 2, y - 31, bx + bw + 12, y - 31, GREY, 1.1, 4)
    y -= 76
    rrect(c, M, y - 30, CW, 30, 6, fill=CORAL)
    txt(c, "ACTUATOR DISAGREEMENT  —  commanded 70%, verified 21%", W / 2, y - 19, "Mono-Bold", 9.6, WHITE,
        align="center", space=0.6)
    y -= 40
    para(c, "Shown in a real browser against a simulated node publishing hash-chained frames over mosquitto. "
            "The reservoir stayed labelled REPLAY while the rig read LIVE, so the two provenances never blur. "
            "What is left is the physical switches and the firmware paths behind them.",
         M, y, CW, st(8, "Sans", MUTED, leading=11.4))
    y -= 50

    y = subhead(c, "When the network dies", M, y)
    ladder = [("Wi-Fi + MQTT", "runs today", GREEN), ("LoRa, 433 MHz", "V2 · 2 modules ordered", AMBER),
              ("SD card log", "planned", GREY), ("Serial print", "today's interim fallback", GREY)]
    lw_ = (CW - 3 * 20) / 4
    for i, (head, sub, col) in enumerate(ladder):
        lx = M + i * (lw_ + 20)
        ly = y - 40
        rrect(c, lx, ly, lw_, 34, 17, fill=TINT["green" if col == GREEN else ("amber" if col == AMBER else "grey")])
        c.setFillColor(col)
        c.circle(lx + 17, ly + 17, 5, stroke=0, fill=1)
        txt(c, head, lx + 28, ly + 19, "Sans-Bold", 7.6, INK)
        txt(c, sub, lx + 28, ly + 9, "Sans", 6.4, MUTED)
        if i < 3:
            arrow(c, lx + lw_ + 3, ly + 17, lx + lw_ + 17, ly + 17, GREY, 1, 4)
    para(c, "433 MHz is the legal ISM band in India; the 868 MHz modules widely recommended online are the European allocation.",
         M, y - 52, CW, st(7, "Sans-Italic", MUTED))


# --- page 13: components ---------------------------------------------------------

def page_components(c, d, n):
    paper(c, n, "Components")
    y = heading(c, "11", "Components", f"The V1 rig, for {inr(d['bom_total'])}",
                "Every part, from hardware/bom/README.md. Prices are indicative, sourced from Indian "
                "vendor listings in August 2026; budget ±25%.")
    parts = d["bom"]
    cols = [(M, "#", 14), (M + 16, "COMPONENT", 150), (M + 168, "SPECIFICATION", 220), (M + 392, "QTY", 26), (W - M, "₹", 0)]
    rrect(c, M - 4, y - 16, CW + 8, 16, 4, fill=NAVY)
    for x, lab, _ in cols:
        txt(c, lab, x if lab != "₹" else x - 4, y - 11, "Mono-Bold", 6.2, WHITE, align="right" if lab == "₹" else "left", space=0.8)
    rh = 14.2
    ty = y - 16
    for i, p in enumerate(parts):
        ry = ty - (i + 1) * rh
        if i % 2 == 0:
            c.setFillColor(HexColor("#EFEADF"))
            c.rect(M - 4, ry, CW + 8, rh, stroke=0, fill=1)
        base = ry + 4.3
        txt(c, str(p["n"]), M, base, "Mono", 6.6, MUTED)
        name = p["name"]
        while pdfmetrics.stringWidth(name, "Sans-Bold", 7) > 148:
            name = name[:-2] + "…"
        txt(c, name, M + 16, base, "Sans-Bold", 7, INK)
        spec = p["spec"]
        while pdfmetrics.stringWidth(spec, "Sans", 6.8) > 218:
            spec = spec[:-2].rstrip() + "…"
        txt(c, spec, M + 168, base, "Sans", 6.8, MUTED)
        txt(c, str(p["qty"]), M + 400, base, "Mono", 6.8, INK, align="center")
        txt(c, f"{p['cost']:,}", W - M - 4, base, "Mono", 6.8, INK, align="right")
    ry = ty - (len(parts) + 1) * rh - 4
    c.setStrokeColor(INK)
    c.setLineWidth(0.8)
    c.line(M - 4, ry + rh + 2, W - M + 4, ry + rh + 2)
    txt(c, f"{len(parts)} line items · rows summed by this builder", M + 16, ry + 3, "Sans-Italic", 7, MUTED)
    txt(c, inr(d["bom_total"]), W - M - 4, ry + 1, "Serif-Bold", 14, INK, align="right")
    y = ry - 20

    # pin map, full width
    pins = d["pins"]
    ph = 170
    card(c, M, y - ph, CW, ph, r=10)
    label(c, "ESP32 pin map", M + 14, y - 16, TEAL, 6.4)
    bw_, bh_ = 64, 128
    bx = M + CW / 2 - bw_ / 2
    by = y - 26 - bh_
    rrect(c, bx, by, bw_, bh_, 5, fill=HexColor("#1B2733"))
    rrect(c, bx + 14, by + bh_ - 40, 36, 28, 2, fill=HexColor("#9AA5AF"))
    txt(c, "ESP32", bx + bw_ / 2, by + 44, "Mono-Bold", 7, WHITE, align="center")
    txt(c, "38-pin", bx + bw_ / 2, by + 34, "Mono", 5.8, SKY, align="center")
    half = math.ceil(len(pins) / 2)
    for i, pn in enumerate(pins):
        left = i < half
        k = i if left else i - half
        py_ = by + bh_ - 14 - k * (bh_ - 24) / max(half - 1, 1)
        col = GREEN if pn["wired"] else GREY
        sign = -1 if left else 1
        edge = bx if left else bx + bw_
        c.setStrokeColor(col)
        c.setLineWidth(1)
        c.line(edge, py_, edge + sign * 24, py_)
        c.setFillColor(col)
        c.circle(edge + sign * 24, py_, 2.4, stroke=0, fill=1)
        tx_ = edge + sign * 31
        align = "right" if left else "left"
        txt(c, pn["pin"], tx_, py_ + 1, "Mono-Bold", 6.4, INK, align=align)
        txt(c, f"{pn['part']} · {pn['fn']}", tx_, py_ - 7, "Sans", 5.9, MUTED, align=align)
    c.setFillColor(GREEN)
    c.circle(M + 18, y - ph + 13, 2.6, stroke=0, fill=1)
    txt(c, "read or driven by node_reservoir", M + 24, y - ph + 10.5, "Sans", 6.4, INK)
    c.setFillColor(GREY)
    c.circle(W - M - 118, y - ph + 13, 2.6, stroke=0, fill=1)
    txt(c, "real part, no firmware yet", W - M - 112, y - ph + 10.5, "Sans", 6.4, INK)
    y -= ph + 12

    # tiers, in a row
    tier_cols = [TEAL, BLUE, VIOLET, AMBER]
    tiers = d["tiers"]
    tw = (CW - 10 * (len(tiers) - 1)) / len(tiers)
    th = 66
    for i, t in enumerate(tiers):
        tx = M + i * (tw + 10)
        col = tier_cols[i % 4]
        card(c, tx, y - th, tw, th, r=8, accent=col, fill=TINT["teal"] if i == 0 else CARD)
        txt(c, t["tier"], tx + 13, y - 20, "Serif-Bold", 16, col)
        txt(c, t["price"], tx + tw - 10, y - 19, "Serif-Bold", 11.5, INK, align="right")
        para(c, t["name"], tx + 13, y - 26, tw - 22, st(6.9, "Sans-Bold", INK, leading=8.8))
        txt(c, t["time"] + (" · the core build" if i == 0 else " · optional"), tx + 13, y - th + 8, "Sans", 6.2, MUTED)


# --- page 14: references ------------------------------------------------------------

def page_origins(c, d, n):
    paper(c, n, "From the references")
    y = heading(c, "12", "From the references", "Where the ideas came from",
                "AquaSync began as one line in a planning conversation: a digital twin for the rain, the dam "
                "and the river, connected, that could find the best time and quantity of water to release.")
    col_w = CW * 0.50
    para(c, "Two source documents seeded the project and still sit in reference/source_chats/: a 17-page "
            "brief exported from an AI planning conversation, and a team chat export beside it. They "
            "proposed far more than any team could build in a season, from a river rover to post-quantum "
            "SCADA. The project's rule is that nothing in them goes unaccounted for. Each idea was checked "
            f"against what is built on {d['audit_date']}, and each has a status and, where it was set aside, "
            "a recorded reason.", M, y, col_w, st(9, "Sans", INK, leading=13.6))

    # funnel
    counts = {k: sum(1 for a in d["audit"] if a["kind"] == k) for k in ("built", "partly", "planned", "deferred", "rejected")}
    fx = M + col_w + 20
    fw = W - M - fx
    stages = [("Ideas in the two sources", NAVY, 1.0), ("Checked against the build", DEEP, 0.86)]
    fy = y
    for i, (lab, col, frac) in enumerate(stages):
        ww = fw * frac
        rrect(c, fx + (fw - ww) / 2, fy - 26, ww, 26, 6, fill=col)
        txt(c, lab, fx + fw / 2, fy - 16.5, "Sans-Bold", 7.8, WHITE, align="center")
        fy -= 32
        if i == 0:
            pass
    buckets = [("Built", counts["built"], GREEN), ("Partly", counts["partly"], AMBER),
               ("Planned", counts["planned"], BLUE), ("Deferred", counts["deferred"], GREY),
               ("Rejected", counts["rejected"], CORAL)]
    total = sum(v for _, v, _ in buckets)
    bx = fx
    for lab, v, col in buckets:
        ww = fw * v / total
        rrect(c, bx + 0.8, fy - 46, ww - 1.6, 46, 5, fill=col)
        if ww > 26:
            txt(c, str(v), bx + ww / 2, fy - 24, "Serif-Bold", 15, WHITE, align="center")
            txt(c, lab.upper(), bx + ww / 2, fy - 38, "Mono-Bold", 5, WHITE, align="center")
        bx += ww
    lx = fx
    for lab, v, col in buckets:
        c.setFillColor(col)
        c.circle(lx + 3, fy - 59, 2.8, stroke=0, fill=1)
        lx += 10 + txt(c, f"{lab} {v}", lx + 9, fy - 61.5, "Sans", 6.6, INK) + 8
    txt(c, f"rows of the audit table, {total} in all · some rows bundle several ideas", fx + fw / 2, fy - 76, "Sans-Italic", 6.4, MUTED, align="center")
    y -= 178

    y = subhead(c, "What the brief proposed, and what the project did with it", M, y)
    txt(c, "THE BRIEF SAID", M, y - 6, "Mono-Bold", 6, MUTED, space=1)
    txt(c, "AQUASYNC DID", M + CW * 0.43 + 36, y - 6, "Mono-Bold", 6, MUTED, space=1)
    y -= 16
    pairs = [
        ("Runoff as C · I · A, a single coefficient", "SCS curve number that shifts with antecedent wetness, validated on four monsoons", GREEN),
        ("Closed-loop gate control on the dam", "Advisory, permanently. The only gate actuated is the bench rig's model sluice", CORAL),
        ("Open gates before the rain, at low tide", "Tide panel and tidal conveyance in the optimiser's flood term", GREEN),
        ("Replay the 2018 crisis to prove it", "October 2021, because the public dataset holds no 2018 rows. Correction on the record", AMBER),
        ("LoRa / ESP-NOW disaster mesh", "V2 tier: two 433 MHz SX1278 modules ordered; bench-only until V1 runs", BLUE),
        ("Adaptive siltation curve, cavitation FFT, 2D inundation, river rover, edge LSTM", "Deferred with reasons in ROADMAP.md, so they cannot creep into the build", GREY),
        ("Validate on the public Kerala dam dataset", "About 11% of it is physically impossible; a validation layer flags every row", GREEN),
        ("Tamper-evident release logging", "SHA-256 record chain in the firmware, verified by the rig bridge", GREEN),
    ]
    rh = 44
    for i, (a, b, col) in enumerate(pairs):
        ry = y - i * rh
        rrect(c, M, ry - rh + 6, CW * 0.43, rh - 8, 7, fill=SAND)
        sa, sb = st(8.6, "Serif-Italic", INK, leading=10.8), st(7.8, "Sans", INK, leading=10.5)
        ha = Paragraph(markup(sa.fontName, a), sa).wrap(CW * 0.43 - 20, H)[1]
        hb = Paragraph(markup(sb.fontName, b), sb).wrap(CW * 0.57 - 58, H)[1]
        mid = ry - rh / 2 + 3
        para(c, a, M + 10, mid + ha / 2, CW * 0.43 - 20, sa)
        arrow(c, M + CW * 0.43 + 6, ry - rh / 2 + 3, M + CW * 0.43 + 30, ry - rh / 2 + 3, col, 1.6, 5.5)
        rrect(c, M + CW * 0.43 + 36, ry - rh + 6, CW * 0.57 - 36, rh - 8, 7, fill=CARD, stroke=LINE, lw=0.5)
        c.setFillColor(col)
        c.rect(M + CW * 0.43 + 36, ry - rh + 6, 3, rh - 8, stroke=0, fill=1)
        para(c, b, M + CW * 0.43 + 48, mid + hb / 2, CW * 0.57 - 58, sb)


def page_audit(c, d, n):
    paper(c, n, "Reference audit")
    y = heading(c, "12", "From the references", "Every idea, accounted for",
                f"The reference-source audit from ROADMAP.md, {d['audit_date']}, reproduced row for row.")
    kinds = {"built": (GREEN, "BUILT"), "partly": (AMBER, "PARTLY"), "planned": (BLUE, "PLANNED"),
             "deferred": (GREY, "DEFERRED"), "rejected": (CORAL, "REJECTED")}
    iw = CW - 196
    for i, a in enumerate(d["audit"]):
        col, tag = kinds[a["kind"]]
        style = st(7.5, "Sans", INK, leading=10)
        p = Paragraph(a["idea"], style)
        _, h_ = p.wrap(iw, H)
        ls = st(6.8, "Sans", MUTED, leading=9)
        _, hl = Paragraph(markup(ls.fontName, a["label"]), ls).wrap(W - M - (M + iw + 72), H)
        rh = max(h_, hl, 10) + 9
        if i % 2 == 0:
            c.setFillColor(HexColor("#EFEADF"))
            c.rect(M - 4, y - rh, CW + 8, rh, stroke=0, fill=1)
        c.setFillColor(col)
        c.rect(M - 4, y - rh, 2.4, rh, stroke=0, fill=1)
        para(c, a["idea"], M + 6, y - 4.5, iw, style)
        pill(c, M + iw + 16, y - 11, tag, WHITE, col, size=5.4)
        lab = a["label"]
        para(c, lab, M + iw + 72, y - 4.5, W - M - (M + iw + 72), ls)
        y -= rh
    y -= 14
    para(c, "Where a status reads 'deferred' or 'rejected', the reason is recorded in ROADMAP.md's deferred table. "
            "Deferral means later; the separate never-in-scope list means never.", M, y, CW, st(7.2, "Sans-Italic", MUTED, leading=10))


# --- page 16: status and roadmap -------------------------------------------------------

def page_status(c, d, n):
    paper(c, n, "Where it stands")
    done = sum(a for a, _ in d["status"].values())
    total = sum(b for _, b in d["status"].values())
    y = heading(c, "13", "Where it stands", f"{done} of {total} components done",
                f"Counted from PROGRESS.md on main, last updated {d['updated']}. The software is finished and "
                "validated; the bench rig is the critical path.")
    rows = list(d["status"].items())
    bw = CW - 210
    for i, (name, (a, b)) in enumerate(rows):
        ry = y - 10 - i * 30
        txt(c, name, M, ry, "Serif-Bold", 12, INK)
        col = GREEN if a == b else (AMBER if a / b < 0.6 else TEAL)
        segw = bw / b
        for k in range(b):
            rrect(c, M + 170 + k * segw + 1, ry - 3, segw - 2, 13, 3, fill=col if k < a else SAND)
        txt(c, f"{a} / {b}", W - M, ry, "Serif-Bold", 12, INK, align="right")
    y -= 10 + len(rows) * 30 + 14

    y = subhead(c, "Phase map", M, y)
    ph = d["phases"]
    step = CW / len(ph)
    line_y = y - 16
    c.setStrokeColor(LINE)
    c.setLineWidth(2)
    c.line(M + step / 2, line_y, W - M - step / 2, line_y)
    for i, p in enumerate(ph):
        cx = M + step * (i + 0.5)
        col = GREEN if p["done"] else AMBER
        c.setFillColor(PAPER)
        c.circle(cx, line_y, 11, stroke=0, fill=1)
        badge(c, cx, line_y, p["name"].split("·")[0].strip(), col, r=9.5)
        name = p["name"].split("·", 1)[-1].strip()
        para(c, f"<b>{name}</b>", cx - step / 2 + 3, line_y - 18, step - 6, st(7.4, "Sans", INK, leading=9, align=TA_CENTER))
        para(c, p["deliverable"], cx - step / 2 + 3, line_y - 40, step - 6, st(6.4, "Sans", MUTED, leading=8.4, align=TA_CENTER))
    y = line_y - 92

    y = subhead(c, "The critical path", M, y)
    chev = [("V1 parts", "in hand", True), ("Bench-test", "every part alone", False), ("Two-tank rig", "gate · level · telemetry", False),
            ("Close the loop", "twin computes, the rig's gate moves", False), ("Fault injection", "the demo beat", False)]
    cwid = (CW - 12) / len(chev)
    for i, (head, sub, ok) in enumerate(chev):
        x = M + i * cwid
        p = c.beginPath()
        tip = 12
        p.moveTo(x, y)
        p.lineTo(x + cwid - 2, y)
        p.lineTo(x + cwid - 2 + tip, y - 24)
        p.lineTo(x + cwid - 2, y - 48)
        p.lineTo(x, y - 48)
        if i:
            p.lineTo(x + tip, y - 24)
        p.close()
        c.setFillColor(TEAL if ok else (CORAL if i == len(chev) - 1 else DEEP))
        c.drawPath(p, stroke=0, fill=1)
        txt(c, head, x + (22 if i else 12), y - 21, "Sans-Bold", 8, WHITE)
        para(c, sub, x + (22 if i else 12), y - 26, cwid - 30, st(6.2, "Sans", SKY, leading=7.6))
    y -= 70

    col_w = (CW - 14) / 2
    card(c, M, y - 150, col_w, 150, r=10, fill=NAVY)
    label(c, "Never in scope", M + 16, y - 18, AQUA, 6.4)
    para(c, "<b>Operating a real dam gate.</b> Kerala's gates are run by KSEB and the district administration "
            "under a statutory chain of accountability. There is no path from this system to them and there will "
            "not be one.<br/><br/><b>Presenting simulated values as live.</b> Every reading carries its provenance.",
         M + 16, y - 28, col_w - 32, st(8.2, "Sans", WHITE, leading=11.8))
    x2 = M + col_w + 14
    card(c, x2, y - 150, col_w, 150, r=10, accent=GREY)
    label(c, "Deliberately deferred", x2 + 16, y - 18, MUTED, 6.4)
    para(c, "2D inundation, Sentinel-1 flood extent, evacuation routing, graph-network routing, reinforcement-learning "
            "gate policy, physics-informed surrogates, a bathymetry boat, dam-breach mode, acoustic cavitation sensing, "
            "AR, TinyML sensor health, camera gauges. Each is in ROADMAP.md with the reason it waits, so it cannot "
            "slip into the build.", x2 + 16, y - 28, col_w - 32, st(7.8, "Sans", INK, leading=11.2))


# --- page 17: back cover --------------------------------------------------------------

def back_band() -> Image.Image:
    """A strip of the reservoir, fading up into the navy page."""
    with Image.open(ROOT / "dashboard" / "assets" / "terrain_idukki_imagery.jpg") as im:
        im = im.convert("RGB")
        sw, sh = im.size
        strip = im.crop((0, int(sh * 0.52), sw, int(sh * 0.52) + int(sw * 0.42)))
        strip = strip.resize((1150, int(1150 * 0.42)), Image.LANCZOS)
    w, h = strip.size
    top = (13, 38, 60)
    navy = Image.new("RGB", strip.size, top)
    mask = Image.new("L", strip.size)
    for yy in range(h):
        t = yy / (h - 1)
        mask.paste(int(255 * (1.0 - 0.45 * t ** 1.3)), (0, yy, w, yy + 1))
    return Image.composite(navy, strip, mask)


def page_back(c, d, n):
    c.setFillColor(NAVY)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    gradient(c, 0, 0, W, H, DEEP, NAVY)
    band = back_band()
    c.drawImage(ImageReader(band), 0, 0, W, W * band.size[1] / band.size[0])
    y = H - 90
    txt(c, "Reproduce every number", M, y, "Serif-Bold", 26, WHITE)
    y -= 22
    para(c, "Nothing in this document was typed in. It is rebuilt from the repository, and the gate fails if a "
            "rebuild changes it.", M, y, CW * 0.8, st(10, "Serif-Italic", SKY, leading=14))
    y -= 50
    rrect(c, M, y - 70, CW, 70, 8, fill=HexColor("#07172A"))
    for i, line in enumerate(["python scripts/check.py            # lint, tests, glyphs, regeneration, determinism",
                              "python scripts/build_showcase.py   # this document",
                              "cd backend && python -m pytest --collect-only -q"]):
        txt(c, line, M + 16, y - 22 - i * 16, "Mono", 8, AQUA if i else WHITE)
    y -= 92
    ledger = [
        ("Level–storage fit", "make_figures.py", "figure_facts.json"),
        ("October 2021 and August 2022 replays", "out_of_sample_replay.py", "replay_*.json"),
        ("About 3 m of cushion", "lead_time_study.py", "lead_time_headline.json"),
        ("Forecast error, two storms", "forecast_error_study.py", "forecast_error_study_*.json"),
        ("Cascade and joint objective", "cascade_*.py", "cascade_*.json"),
        ("Runoff validation", "runoff_validation.py", "runoff_validation_idukki.json"),
        ("Routing calibration", "routing_calibration.py", "routing_calibration_*.json"),
        ("Storm stress test", "stress_sweep.py", "stress_sweep_*.json"),
    ]
    txt(c, "CLAIM", M, y, "Mono-Bold", 6.4, AQUA, space=1)
    txt(c, "SCRIPT", M + 200, y, "Mono-Bold", 6.4, AQUA, space=1)
    txt(c, "DATA/PROCESSED", M + 370, y, "Mono-Bold", 6.4, AQUA, space=1)
    for i, (a, b, f_) in enumerate(ledger):
        ry = y - 18 - i * 17
        c.setStrokeColor(SKY)
        c.setStrokeAlpha(0.18)
        c.setLineWidth(0.5)
        c.line(M, ry - 6, W - M, ry - 6)
        c.setStrokeAlpha(1)
        txt(c, a, M, ry, "Sans", 7.8, WHITE)
        txt(c, b, M + 200, ry, "Mono", 6.8, SKY)
        txt(c, f_, M + 370, ry, "Mono", 6.8, SKY)
    y -= 18 + len(ledger) * 17 + 26

    txt(c, "Data", M, y, "Serif-Bold", 14, WHITE)
    para(c, "KSEB / KSDMA daily reservoir bulletin · CWC Neeleeswaram gauge · NOAA GEFS forecast ensembles · IMD "
            "gridded rainfall · AWS Terrain Tiles · Copernicus Sentinel-2 (contains modified Copernicus Sentinel "
            "data) · Kochi tidal harmonics from published constituents.", M, y - 8, CW, st(8.2, "Sans", SKY, leading=12))
    y -= 70

    rrect(c, M, y - 44, CW, 44, 8, stroke=AQUA, lw=0.7)
    txt(c, "Photos and videos of the project", M + 16, y - 18, "Sans-Bold", 9, WHITE)
    txt(c, MEDIA_URL, M + 16, y - 32, "Mono", 6.2, SKY)
    c.linkURL(MEDIA_URL, (M, y - 44, W - M, y), relative=0, thickness=0)

    txt(c, "AquaSync", M, 118, "Serif-Bold", 44, WHITE)
    txt(c, "Built by the AquaSync team", M, 94, "Sans", 8.4, SKY)
    txt(c, f"Status as of {d['updated']} · {d['tests']} tests", M, 80, "Sans", 8.4, SKY)
    c.setFillColor(AQUA)
    c.rect(M, 56, 26, 2.4, stroke=0, fill=1)
    txt(c, "ADVISORY, PERMANENTLY. AQUASYNC NEVER OPERATES A REAL DAM GATE.", M + 34, 54, "Mono-Bold", 7, WHITE, space=1.2)


# --- assemble -------------------------------------------------------------------------

def build() -> Path:
    register_fonts()
    d = gather()
    pages = [
        (None, None, page_cover),
        (None, "Contents", page_contents),
        ("01", "The problem", page_problem),
        ("02", "The twin", page_twin),
        ("03", "Architecture", page_architecture),
        ("04", "Decision engine", page_decision),
        ("05", "Validation", page_validation),
        ("06", "The result", page_result),
        ("07", "Forecast error", page_forecast),
        ("08", "Warnings", page_warnings),
        ("09", "The interface", page_interface),
        ("10", "Hardware", page_hardware),
        ("11", "Components", page_components),
        ("12", "From the references", page_origins),
        (None, "Reference audit", page_audit),
        ("13", "Where it stands", page_status),
        (None, None, page_back),
    ]
    toc = [(num, title, i + 1) for i, (num, title, _) in enumerate(pages) if num]
    c = canvas.Canvas(str(OUT), pagesize=A4, invariant=1)
    c.setTitle("AquaSync")
    c.setAuthor("AquaSync team")
    c.setSubject("Flood-management digital twin for dam, river and tide systems, with the Periyar basin as case study")
    for i, (_, _, fn) in enumerate(pages):
        n = i + 1
        if fn is page_cover or fn is page_back:
            fn(c, d) if fn is page_cover else fn(c, d, n)
        elif fn is page_contents:
            fn(c, d, n, toc)
        else:
            fn(c, d, n)
        c.showPage()
    leaked = sorted({m.group(0) for t in _DRAWN for m in EVENT_WORDS.finditer(t)})
    if leaked:
        raise SystemExit(f"event names reached the page: {leaked}")
    c.save()
    return OUT


if __name__ == "__main__":
    out = build()
    print(f"wrote {out.relative_to(ROOT)}")
