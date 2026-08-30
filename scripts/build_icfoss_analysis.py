"""Build the ICFOSS portfolio analysis PDF.

    python scripts/build_icfoss_analysis.py  ->  docs/AquaSync_ICFOSS_Analysis.pdf

A deep read of the 54 projects published at icfoss.in/projects and the ~120
repositories behind them on gitlab.com/icfoss, assessed for one question:
what does the International Centre for Free and Open Source Software already
have that AquaSync should stand on, and what does AquaSync give back?

Visual language is deliberately identical to build_abstract.py and
build_dossier.py so the documents read as one set.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "AquaSync_ICFOSS_Analysis.pdf"
PROC = ROOT / "data" / "processed"

# -- palette (shared with build_abstract.py) -------------------------------
NAVY = colors.HexColor("#08243D")
DEEP = colors.HexColor("#0E3E63")
BLUE = colors.HexColor("#1F6FEB")
AQUA = colors.HexColor("#2F9FC4")
TEAL = colors.HexColor("#0E8F86")
GREEN = colors.HexColor("#1A7F37")
AMBER = colors.HexColor("#B4690E")
PLUM = colors.HexColor("#6B4FA8")
INK = colors.HexColor("#12263A")
BODY = colors.HexColor("#25384C")
MUTED = colors.HexColor("#5B6B7F")
FAINT = colors.HexColor("#8496A8")
RULE = colors.HexColor("#DFE6EE")
CARD = colors.HexColor("#F7FAFC")
WHITE = colors.white
SKY = colors.HexColor("#7FD3EA")
PALE = colors.HexColor("#C4DFF3")
TINT_AMBER = colors.HexColor("#FDF5E9")

PAGE_W, PAGE_H = A4
MARGIN = 40.0
CONTENT_W = PAGE_W - 2 * MARGIN
TOP = PAGE_H - 56.0
BOTTOM = 54.0

_DJ = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"
pdfmetrics.registerFont(TTFont("Glyph", str(_DJ)))
RS = "₹"


def forecast_excess_cost() -> tuple[float, float]:
    """Best and worst excess cost against perfect foresight, across every lead
    time in data/processed. Typed numbers go stale; this does not."""
    costs = []
    for q in PROC.glob("forecast_error_study_*.json"):
        d = json.loads(q.read_text(encoding="utf-8"))
        for rule in ("decision_rule_expected_value", "decision_rule_minimax_regret"):
            v = d.get(rule, {}).get("excess_cost_vs_perfect_foresight_pct")
            if v is not None:
                costs.append(v)
    return (min(costs), max(costs)) if costs else (0.0, 84.7)


# --------------------------------------------------------------------------
# low-level drawing
# --------------------------------------------------------------------------
def wave(c, y0, amp, wl, phase, colour, alpha, depth):
    c.saveState()
    c.setFillColor(colour)
    try:
        c.setFillAlpha(alpha)
    except Exception:
        pass
    p = c.beginPath()
    p.moveTo(0, y0 - depth)
    x, step = 0.0, wl / 24.0
    while x <= PAGE_W + step:
        p.lineTo(x, y0 + amp * math.sin(2 * math.pi * (x / wl) + phase))
        x += step
    p.lineTo(PAGE_W, y0 - depth)
    p.close()
    c.drawPath(p, stroke=0, fill=1)
    c.restoreState()


def gradient_panel(c, x, y, w, h, radius=6, waves=True):
    c.saveState()
    p = c.beginPath()
    p.roundRect(x, y, w, h, radius)
    c.clipPath(p, stroke=0, fill=0)
    c.linearGradient(x, y + h, x + w, y, (NAVY, DEEP, colors.HexColor("#12558C")))
    if waves:
        wave(c, y + min(28, h * 0.35), 9, 230, 1.1, SKY, 0.13, h)
        wave(c, y + min(16, h * 0.20), 6, 155, 3.6, WHITE, 0.08, h)
    c.restoreState()


def soft_card(c, x, y, w, h, fill=CARD, stroke=RULE, radius=5, accent=None):
    c.saveState()
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(0.6)
    c.roundRect(x, y, w, h, radius, stroke=1, fill=1)
    if accent is not None:
        p = c.beginPath()
        p.roundRect(x, y, w, h, radius)
        c.clipPath(p, stroke=0, fill=0)
        c.setFillColor(accent)
        c.rect(x, y, 3.0, h, stroke=0, fill=1)
    c.restoreState()


def text_w(s, font, size):
    return pdfmetrics.stringWidth(s, font, size)


def wrap(s, font, size, width):
    words, lines, cur = s.split(), [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if text_w(trial, font, size) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines or [""]


def draw_para(c, s, x, y, width, font="Helvetica", size=8.6, leading=11.4,
              colour=BODY):
    """Draw wrapped text, swapping fonts for the rupee glyph. Returns new y."""
    c.setFillColor(colour)
    for ln in wrap(s, font, size, width):
        if RS in ln:
            cx = x
            for i, part in enumerate(ln.split(RS)):
                if i:
                    c.setFont("Glyph", size)
                    c.drawString(cx, y, RS)
                    cx += text_w(RS, "Glyph", size)
                c.setFont(font, size)
                c.drawString(cx, y, part)
                cx += text_w(part, font, size)
        else:
            c.setFont(font, size)
            c.drawString(x, y, ln)
        y -= leading
    return y


def para_h(s, font, size, leading, width):
    return len(wrap(s, font, size, width)) * leading


# --------------------------------------------------------------------------
# document shell
# --------------------------------------------------------------------------
class Doc:
    def __init__(self, path):
        self.c = rl_canvas.Canvas(str(path), pagesize=A4, invariant=1)
        self.c.setTitle("AquaSync x ICFOSS - Portfolio Analysis")
        self.c.setAuthor("AquaSync / MACE IoT Club")
        self.c.setSubject(
            "Analysis of the ICFOSS project portfolio as a foundation for AquaSync")
        self.page = 0
        self.y = TOP
        self.section = ""

    def start_page(self, section=None):
        if self.page:
            self.footer()
            self.c.showPage()
        self.page += 1
        if section is not None:
            self.section = section
        self.y = TOP
        return self.y

    def footer(self):
        c = self.c
        c.setStrokeColor(RULE)
        c.setLineWidth(0.6)
        c.line(MARGIN, BOTTOM - 10, PAGE_W - MARGIN, BOTTOM - 10)
        c.setFont("Helvetica", 7.0)
        c.setFillColor(FAINT)
        c.drawString(MARGIN, BOTTOM - 21, "AquaSync  ·  ICFOSS portfolio analysis")
        c.drawCentredString(PAGE_W / 2, BOTTOM - 21, self.section)
        c.drawRightString(PAGE_W - MARGIN, BOTTOM - 21, str(self.page))

    def need(self, h, section=None):
        if self.y - h < BOTTOM:
            self.start_page(section)
            return True
        return False

    # -- blocks ------------------------------------------------------------
    def band(self, kicker, title):
        c = self.c
        h = 44.0
        y = self.y - h
        gradient_panel(c, MARGIN, y, CONTENT_W, h, radius=5)
        c.setFillColor(SKY)
        c.setFont("Helvetica-Bold", 7.0)
        c.drawString(MARGIN + 14, y + h - 16, kicker.upper())
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 15.0)
        c.drawString(MARGIN + 13, y + 10, title)
        self.y = y - 17
        return self.y

    def h2(self, s, colour=INK, size=11.0, gap=8):
        self.need(36)
        c = self.c
        c.setFillColor(colour)
        c.setFont("Helvetica-Bold", size)
        c.drawString(MARGIN, self.y - size, s)
        self.y -= size + 4
        c.setStrokeColor(RULE)
        c.setLineWidth(0.7)
        c.line(MARGIN, self.y, PAGE_W - MARGIN, self.y)
        self.y -= gap
        return self.y

    def body(self, s, size=8.8, leading=11.8, colour=BODY, font="Helvetica",
             gap=7, indent=0.0):
        w = CONTENT_W - indent
        self.need(para_h(s, font, size, leading, w) + 6)
        self.y = draw_para(self.c, s, MARGIN + indent, self.y - size, w,
                           font=font, size=size, leading=leading, colour=colour)
        self.y -= gap
        return self.y

    def lead(self, s):
        return self.body(s, size=9.9, leading=13.4, colour=INK, gap=10)

    def tail(self, s, size=7.2, leading=9.4):
        """A closing note pinned just above the footer of the current page.

        Anchored rather than flowed, so a two-line source note can never
        spill onto a page of its own.
        """
        n = len(wrap(s, "Helvetica-Oblique", size, CONTENT_W))
        top = BOTTOM + 5 + n * leading
        if top > self.y - 4:          # would collide with the last block
            self.start_page()
            top = self.y
        draw_para(self.c, s, MARGIN, top - size, CONTENT_W,
                  font="Helvetica-Oblique", size=size, leading=leading,
                  colour=FAINT)
        return self.y


# --------------------------------------------------------------------------
# composite components
# --------------------------------------------------------------------------
def masthead(c):
    band = 156.0
    top, bot = PAGE_H, PAGE_H - band
    c.saveState()
    p = c.beginPath()
    p.rect(0, bot, PAGE_W, band)
    c.clipPath(p, stroke=0, fill=0)
    c.linearGradient(0, top, PAGE_W, bot, (NAVY, DEEP, colors.HexColor("#12558C")))
    wave(c, bot + 40, 15, 300, 0.4, SKY, 0.14, 200)
    wave(c, bot + 24, 11, 210, 2.2, WHITE, 0.09, 200)
    wave(c, bot + 10, 8, 160, 4.1, colors.HexColor("#4FB6DC"), 0.20, 200)
    c.restoreState()

    x = MARGIN
    c.setFillColor(SKY)
    c.setFont("Helvetica-Bold", 7.4)
    c.drawString(x, top - 36,
                 "P O R T F O L I O   A N A L Y S I S    ·    "
                 "O P E N   S O U R C E   R E U S E    ·    K E R A L A")
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 30)
    c.drawString(x - 2, top - 72, "AquaSync  ×  ICFOSS")
    c.setFillColor(PALE)
    c.setFont("Helvetica", 10.8)
    c.drawString(x, top - 93,
                 "What Kerala's open-source institute has already built — and how "
                 "AquaSync should stand on it")
    c.setFillColor(colors.HexColor("#8FC3E4"))
    c.setFont("Helvetica-Oblique", 8.6)
    c.drawString(x, top - 110,
                 "A deep review of 54 published projects and the ~120 public "
                 "repositories behind them, at icfoss.in and gitlab.com/icfoss")
    c.setFillColor(colors.HexColor("#6FB0D8"))
    c.setFont("Helvetica", 7.6)
    c.drawString(x, top - 130,
                 "EVOKE 26  ·  Track 2, Climate Resilience & Disaster "
                 "Preparedness   ·   MACE IoT Club, Kothamangalam")
    return bot


def kpi_strip(c, y, items, h=50.0):
    n = len(items)
    gap = 9.0
    w = (CONTENT_W - gap * (n - 1)) / n
    for i, (big, small, col) in enumerate(items):
        x = MARGIN + i * (w + gap)
        soft_card(c, x, y - h, w, h, fill=CARD, accent=col)
        c.setFillColor(col)
        size = 17.0
        while text_w(big, "Helvetica-Bold", size) > w - 22 and size > 9:
            size -= 0.5
        c.setFont("Helvetica-Bold", size)
        c.drawString(x + 11, y - h + 24, big)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 6.8)
        for k, ln in enumerate(wrap(small, "Helvetica", 6.8, w - 19)[:2]):
            c.drawString(x + 11, y - h + 13 - k * 7.8, ln)
    return y - h


def asset_card(doc, tag, tag_col, title, repo, rows, verdict):
    """A detailed project card: what it is, and what it gives AquaSync."""
    c = doc.c
    w = CONTENT_W
    inner = w - 26
    lab_w = 80.0

    body_h = 0.0
    for _label, txt in rows:
        body_h += max(10.6, para_h(txt, "Helvetica", 8.1, 10.5, inner - lab_w - 6)) + 3.2
    vh = para_h(verdict, "Helvetica-Bold", 8.2, 10.9, inner)
    h = 31.0 + body_h + 10.0 + vh + 9.0

    doc.need(h + 11)
    y = doc.y - h
    soft_card(c, MARGIN, y, w, h, fill=WHITE, accent=tag_col)

    c.setFillColor(tag_col)
    tw = text_w(tag, "Helvetica-Bold", 6.5) + 12
    c.roundRect(MARGIN + 13, y + h - 21, tw, 12, 3, stroke=0, fill=1)
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString(MARGIN + 13 + tw / 2, y + h - 17.4, tag)

    title_x = MARGIN + 13 + tw + 9
    t_size = 9.8
    while text_w(title, "Helvetica-Bold", t_size) > inner - (tw + 22) - 96 \
            and t_size > 8.4:
        t_size -= 0.2
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", t_size)
    c.drawString(title_x, y + h - 18.4, title)

    # the repo path takes whatever room the title leaves, shrinking then eliding
    avail = (PAGE_W - MARGIN - 13) - (title_x + text_w(title, "Helvetica-Bold",
                                                       t_size) + 14)
    r_size = 6.7
    shown = repo
    if text_w(shown, "Helvetica-Oblique", r_size) > avail:
        shown = repo.rsplit("/", 1)[-1]
    while shown and text_w(shown, "Helvetica-Oblique", r_size) > avail:
        if r_size > 5.6:
            r_size -= 0.2
        else:
            shown = shown[:-2] + "…"
    if avail > 24:
        c.setFillColor(FAINT)
        c.setFont("Helvetica-Oblique", r_size)
        c.drawRightString(PAGE_W - MARGIN - 13, y + h - 17.4, shown)

    yy = y + h - 32
    for label, txt in rows:
        l_size = 7.0
        while text_w(label.upper(), "Helvetica-Bold", l_size) > lab_w - 6 \
                and l_size > 5.6:
            l_size -= 0.1
        c.setFillColor(tag_col)
        c.setFont("Helvetica-Bold", l_size)
        c.drawString(MARGIN + 14, yy, label.upper())
        end = draw_para(c, txt, MARGIN + 14 + lab_w, yy, inner - lab_w - 6,
                        size=8.1, leading=10.5, colour=BODY)
        yy = min(yy - 10.6, end) - 3.2

    c.setStrokeColor(RULE)
    c.setLineWidth(0.6)
    c.line(MARGIN + 14, yy + 3, PAGE_W - MARGIN - 14, yy + 3)
    draw_para(c, verdict, MARGIN + 14, yy - 7, inner,
              font="Helvetica-Bold", size=8.2, leading=10.9, colour=tag_col)

    doc.y = y - 11
    return doc.y


def _table_head(c, y, cols, W, hh, head_col, size, pad):
    c.setFillColor(head_col)
    c.rect(MARGIN, y, CONTENT_W, hh, stroke=0, fill=1)
    x = MARGIN
    for i, t in enumerate(cols):
        draw_para(c, str(t), x + pad, y + hh - 8.2, W[i] - 2 * pad,
                  font="Helvetica-Bold", size=size, leading=size + 3.0,
                  colour=WHITE)
        x += W[i]


def table(doc, cols, widths, rows, head_col=DEEP, size=7.7, pad=5.0):
    c = doc.c
    W = [f * CONTENT_W for f in widths]

    def row_h(cells, fnt="Helvetica", sz=size):
        return max(para_h(str(t), fnt, sz, sz + 3.0, W[i] - 2 * pad)
                   for i, t in enumerate(cells)) + 6.5

    hh = row_h(cols, "Helvetica-Bold", size)
    doc.need(hh + row_h(rows[0]) + 12)

    y = doc.y - hh
    _table_head(c, y, cols, W, hh, head_col, size, pad)

    for r, cells in enumerate(rows):
        h = row_h(cells)
        if y - h < BOTTOM:
            doc.footer()
            c.showPage()
            doc.page += 1
            doc.y = TOP
            y = doc.y - hh
            _table_head(c, y, cols, W, hh, head_col, size, pad)
        y -= h
        if r % 2 == 0:
            c.setFillColor(CARD)
            c.rect(MARGIN, y, CONTENT_W, h, stroke=0, fill=1)
        c.setStrokeColor(RULE)
        c.setLineWidth(0.5)
        c.line(MARGIN, y, PAGE_W - MARGIN, y)
        x = MARGIN
        for i, t in enumerate(cells):
            fnt = "Helvetica-Bold" if i == 0 else "Helvetica"
            col = INK if i == 0 else BODY
            draw_para(c, str(t), x + pad, y + h - 8.2, W[i] - 2 * pad,
                      font=fnt, size=size, leading=size + 3.0, colour=col)
            x += W[i]
    doc.y = y - 12
    return doc.y


def bullets(doc, items, colour=AQUA, size=8.6, leading=11.4, gap=4.0):
    c = doc.c
    for it in items:
        w = CONTENT_W - 15
        doc.need(para_h(it, "Helvetica", size, leading, w) + 5)
        c.setFillColor(colour)
        c.circle(MARGIN + 4.0, doc.y - size + 3.0, 2.0, stroke=0, fill=1)
        doc.y = draw_para(c, it, MARGIN + 15, doc.y - size, w,
                          size=size, leading=leading, colour=BODY) - gap
    return doc.y


def callout(doc, title, text, colour=AMBER, tint=TINT_AMBER):
    c = doc.c
    inner = CONTENT_W - 30
    h = 21 + para_h(text, "Helvetica", 8.5, 11.3, inner) + 11
    doc.need(h + 10)
    y = doc.y - h
    soft_card(c, MARGIN, y, CONTENT_W, h, fill=tint, stroke=colour, accent=colour)
    c.setFillColor(colour)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(MARGIN + 15, y + h - 15, title)
    draw_para(c, text, MARGIN + 15, y + h - 29, inner, size=8.5, leading=11.3,
              colour=INK)
    doc.y = y - 11
    return doc.y


# --------------------------------------------------------------------------
# the integration diagram
# --------------------------------------------------------------------------
LAYERS = [
    ("LAYER 4", "INTERFACE", BLUE,
     "3D twin · what-if panel · Crisis Commander · Malayalam alerts",
     ["Flood Monitoring Technopark — threshold alerts, SMS/email, admin roles",
      "Spatial DECM — browser GIS viewer beside the Three.js twin",
      "RescueRoute — width-aware evacuation routing",
      "Malayalam Computing — OCR, corpus, summarisation for alert text"]),
    ("LAYER 3", "DECISION", TEAL,
     "Policy search over target level, start time, max release rate",
     ["QNetPlanner — the same multi-criteria optimisation pattern, in QGIS",
      "No ICFOSS equivalent exists. This layer is AquaSync's own contribution."]),
    ("LAYER 2", "SIMULATION", AQUA,
     "SCS-CN runoff · mass balance · Muskingum · tidal backwater · hydropower",
     ["Water Current Meter — the velocity observations Muskingum needs to calibrate",
      "Acoustic Rain Gauge + Kaggle dataset — labelled rainfall for the runoff model",
      "OpenSDI / stream mapping — catchment and channel geometry"]),
    ("LAYER 1", "INGESTION", DEEP,
     "KSEB bulletin · IMD/Open-Meteo · INCOIS tide · Sentinel-1 · field nodes",
     ["ALMS radar station — VEGAPULS C 11, 8 m, solar, MIT-licensed",
      "Davis LoRaWAN rain gauge — 15-min and daily rainfall",
      "C1-Dev / ULP LoRa boards, ChirpStack, LoraLink API, gateway designs"]),
]


def integration_map(doc):
    """AquaSync's four layers with the ICFOSS assets that feed each."""
    c = doc.c
    row_h = 74.0
    total = row_h * len(LAYERS) + 8 * (len(LAYERS) - 1)
    doc.need(total + 14)
    y0 = doc.y

    left_w = 176.0
    right_w = CONTENT_W - left_w - 26.0

    for i, (tag, name, col, sub, assets) in enumerate(LAYERS):
        y = y0 - (i + 1) * row_h - i * 8

        # left: the AquaSync layer
        gradient_panel(c, MARGIN, y, left_w, row_h, radius=5, waves=(i == 3))
        c.setFillColor(SKY)
        c.setFont("Helvetica-Bold", 6.6)
        c.drawString(MARGIN + 12, y + row_h - 15, tag)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 12.4)
        c.drawString(MARGIN + 12, y + row_h - 31, name)
        c.setFillColor(PALE)
        yy = y + row_h - 43
        for ln in wrap(sub, "Helvetica", 6.7, left_w - 24)[:4]:
            c.setFont("Helvetica", 6.7)
            c.drawString(MARGIN + 12, yy, ln)
            yy -= 8.0

        # connector
        cx = MARGIN + left_w
        c.setStrokeColor(col)
        c.setLineWidth(1.1)
        c.line(cx + 3, y + row_h / 2, cx + 19, y + row_h / 2)
        c.setFillColor(col)
        p = c.beginPath()
        p.moveTo(cx + 19, y + row_h / 2)
        p.lineTo(cx + 13, y + row_h / 2 + 3.4)
        p.lineTo(cx + 13, y + row_h / 2 - 3.4)
        p.close()
        c.drawPath(p, stroke=0, fill=1)

        # right: what ICFOSS supplies
        rx = MARGIN + left_w + 26
        soft_card(c, rx, y, right_w, row_h, fill=CARD, accent=col)
        c.setFillColor(col)
        c.setFont("Helvetica-Bold", 6.6)
        c.drawString(rx + 12, y + row_h - 15, "WHAT ICFOSS ALREADY SUPPLIES")
        yy = y + row_h - 27
        for a in assets:
            c.setFillColor(col)
            c.circle(rx + 14.5, yy + 2.6, 1.7, stroke=0, fill=1)
            for k, ln in enumerate(wrap(a, "Helvetica", 7.3, right_w - 34)):
                c.setFillColor(BODY if k or "No ICFOSS" not in a else AMBER)
                c.setFont("Helvetica-Oblique" if "No ICFOSS" in a else "Helvetica",
                          7.3)
                c.drawString(rx + 23, yy, ln)
                yy -= 9.0
            yy -= 1.6

    doc.y = y0 - total - 12
    return doc.y


def portfolio_chart(doc):
    """Composition of the 54 published projects, and the relevance funnel."""
    c = doc.c
    h = 128.0
    doc.need(h + 14)
    y = doc.y - h

    half = (CONTENT_W - 16) / 2

    # ---- left: portfolio composition
    soft_card(c, MARGIN, y, half, h, fill=WHITE)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 8.6)
    c.drawString(MARGIN + 13, y + h - 17, "The published portfolio")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 6.8)
    c.drawString(MARGIN + 13, y + h - 27, "54 projects listed at icfoss.in/projects")

    bars = [("IoT & open hardware", 18, AQUA),
            ("GIS, drone & mapping", 19, TEAL),
            ("Language technology", 11, PLUM),
            ("Assistive technology", 6, MUTED)]
    bx, bw = MARGIN + 118, half - 150
    by = y + h - 45
    for label, n, col in bars:
        c.setFillColor(BODY)
        c.setFont("Helvetica", 7.2)
        c.drawRightString(bx - 7, by, label)
        c.setFillColor(colors.HexColor("#E8EEF4"))
        c.roundRect(bx, by - 2.5, bw, 8.5, 2, stroke=0, fill=1)
        c.setFillColor(col)
        c.roundRect(bx, by - 2.5, bw * n / 19.0, 8.5, 2, stroke=0, fill=1)
        c.setFillColor(col)
        c.setFont("Helvetica-Bold", 7.2)
        c.drawString(bx + bw + 6, by, str(n))
        by -= 17.0

    c.setFillColor(FAINT)
    c.setFont("Helvetica-Oblique", 6.6)
    c.drawString(MARGIN + 13, y + 13,
                 "Behind them: ~120 public repositories in 9 GitLab groups,")
    c.drawString(MARGIN + 13, y + 5.5,
                 "roughly 80 of which sit in the OpenIoT group alone.")

    # ---- right: the relevance funnel
    fx = MARGIN + half + 16
    soft_card(c, fx, y, half, h, fill=WHITE)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 8.6)
    c.drawString(fx + 13, y + h - 17, "Filtered for AquaSync")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 6.8)
    c.drawString(fx + 13, y + h - 27, "How much of it actually bears on this project")

    steps = [("54", "published projects reviewed", DEEP, 1.00),
             ("31", "touch water, weather or terrain", AQUA, 0.62),
             ("14", "directly reusable here", TEAL, 0.40),
             ("5", "drop-in today, MIT-licensed", GREEN, 0.24)]
    sy = y + h - 44
    fw = (half - 26) * 0.44
    for big, label, col, frac in steps:
        bw2 = fw * frac
        c.setFillColor(col)
        c.roundRect(fx + 13, sy - 3, bw2, 15, 3, stroke=0, fill=1)
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 8.4)
        c.drawString(fx + 20, sy + 1.5, big)
        c.setFillColor(BODY)
        c.setFont("Helvetica", 6.8)
        c.drawString(fx + 13 + bw2 + 7, sy + 1.8, label)
        sy -= 22.0

    doc.y = y - 12
    return doc.y


# --------------------------------------------------------------------------
# pages
# --------------------------------------------------------------------------
def page_1(doc):
    c = doc.c
    doc.start_page("Executive summary")
    bot = masthead(c)
    doc.y = bot - 20

    doc.y = kpi_strip(c, doc.y, [
        ("54", "published ICFOSS projects reviewed", DEEP),
        ("~120", "public repositories behind them", BLUE),
        ("14", "directly reusable by AquaSync", TEAL),
        ("5", "drop-in today, MIT-licensed", GREEN),
    ]) - 16

    doc.h2("The finding, in one paragraph", colour=INK)
    doc.lead(
        "ICFOSS has spent roughly a decade building the sensing and telemetry "
        "layer of a Kerala-wide environmental monitoring system, and publishing "
        "almost all of it under MIT. There are solar-powered radar water-level "
        "stations built explicitly for flood monitoring, LoRaWAN rain gauges, a "
        "river current meter, an acoustic rain gauge with a public labelled "
        "dataset, gateway designs, a network server stack, a QGIS coverage "
        "planner, a GeoNode geoportal carrying Kerala's stream network, and a "
        "live flood-alerting web portal on a canal in Thiruvananthapuram. What "
        "does not exist anywhere in that portfolio is a model that looks "
        "forward. Every ICFOSS water project answers what the level is now and "
        "whether it has crossed a line. None of them answers what the level "
        "will be in eighteen hours, or what release schedule to run to change "
        "that. AquaSync is exactly that missing layer — and it should be built "
        "to sit on top of their hardware rather than beside it.")

    doc.h2("Why this matters more than a reading list")
    bullets(doc, [
        "AquaSync's field node is currently a ₹6,250 ESP32 rig with a JSN-SR04T "
        "ultrasonic sensor. ICFOSS publishes a complete, field-deployed, "
        "solar-autonomous alternative using a VEGAPULS C 11 radar with 8 m range "
        "and a month of battery endurance — schematics, firmware and wiring "
        "diagrams included. Citing it turns a hobby build into a credible "
        "deployment plan without spending a rupee more on the demonstrator.",

        "The git history of this repository records that routing calibration "
        "against Neeleeswaram was blocked by data resolution. ICFOSS's LoRaWAN "
        "water current meter measures river velocity directly. That is the "
        "specific instrument the Muskingum layer needs, and it already exists.",

        "ICFOSS mapped 14 lakh+ 11 kV poles for KSEB and displaced a "
        "₹200 crore proprietary estimate doing it. KSEB is the utility that "
        "operates Idukki. A working relationship with the exact counterparty "
        "AquaSync's recommendations are addressed to is worth more than any "
        "single component.",

        "Their Ini Njan Ozhukkate stream mapping covered 249 highland "
        "panchayats and pushed the result to OpenStreetMap. Idukki is a "
        "highland district. The channel network for this catchment is already "
        "public, and can be cross-checked against the DEM-derived geometry "
        "AquaSync computed independently.",
    ], colour=BLUE)

    callout(doc, "The strategic reading",
            "Treat ICFOSS not as a source of parts but as the other half of a "
            "system. They own the nervous system — sensors, radio, gateways, "
            "geodata, and a relationship with the state. AquaSync is proposing "
            "the brain. Positioning the project that way at EVOKE 26 is stronger "
            "than positioning it as a self-contained build, because it is both "
            "more honest about what is already solved and more ambitious about "
            "what is not.",
            colour=BLUE, tint=colors.HexColor("#EEF4FD"))


def page_2(doc):
    doc.start_page("The portfolio")
    doc.band("Section 01", "What ICFOSS is, and what is actually in the portfolio")

    doc.body(
        "The International Centre for Free and Open Source Software is an "
        "autonomous body established by the Government of Kerala in 2009, and "
        "the state's nodal organisation for free software. It runs the "
        "Swatantra Incubator — a Kerala Startup Mission associate incubator — "
        "and hosts a LoRaWAN Centre of Excellence and an Open-FPGA Centre of "
        "Excellence, the former established with support from Hardware Mission "
        "Kerala. Practically, this means three things for a student project: "
        "the work is genuinely open-licensed, it is built against Kerala's own "
        "terrain and institutions rather than imported assumptions, and there "
        "are formal doors — incubation, the CoE, internships — that a good "
        "project can walk through.")

    portfolio_chart(doc)

    doc.h2("The nine GitLab groups, and where the substance sits")
    table(doc,
          ["Group", "Scale", "What is in it", "Bearing on AquaSync"],
          [0.185, 0.085, 0.375, 0.355],
          [["OpenIoT", "~80 repos",
            "LoRaWAN nodes, boards, gateways, energy harvesting, water level, "
            "rain, flow, air and soil sensing; ChirpStack and Grafana stacks",
            "Decisive. Contains the field-node reference designs, the flood "
            "portal, and the network plumbing AquaSync's Layer 1 needs."],
           ["gis_and_mapping", "10 repos",
            "OpenSDI / Kerala Geoportal (GeoNode), QNetPlanner QGIS plugin, "
            "Spatial DECM browser GIS, RescueRoute, tile server, ClusterODM",
            "High. Catchment geometry, gateway siting, evacuation routing and "
            "a lightweight map viewer for the dashboard."],
           ["drone", "10 repos",
            "Thermal imaging drone, hexacopter documentation, Kole wetland "
            "canal mapping, LiDAR configuration, RC and toolchain notes",
            "Moderate. Post-event inundation validation and high-resolution "
            "terrain capture for the reach downstream of the dam."],
           ["Malayalam-Computing", "11 repos",
            "Malayalam OCR (incl. handwritten-text recognition), spell check, "
            "morpheme generator, root extractor, tagged corpus",
            "Higher than it looks. Layer 4 promises Malayalam alerts — and OCR "
            "is the route to the pre-2020 bulletin data this project lacks."],
           ["Assistive_Tech", "~60 repos",
            "Braille learners, tactile Kerala map, adaptive input devices, "
            "exoskeleton, wheelchair",
            "Low for function, useful as precedent: a rigorous open-hardware "
            "documentation pattern worth imitating in hardware/."],
           ["openfpga · incubation · Internship-projects · website", "—",
            "Chisel bootcamp and Chipyard, incubation material, internship NLP "
            "projects, the public site",
            "Contextual. Mainly relevant as evidence of the routes by which a "
            "student project can engage the institution."]])

    callout(doc, "A caveat on sourcing",
            "The project pages at icfoss.in are short marketing summaries; the "
            "engineering detail lives in the GitLab READMEs, and the two do not "
            "always agree. Everything asserted in this document about hardware, "
            "licensing or specifications was read from the repository itself, "
            "not from the project page. Where a repository is silent — deployment "
            "sites, calibration records, current operational status — this "
            "document says so rather than inferring.",
            colour=MUTED, tint=colors.HexColor("#F4F7FA"))


def page_3(doc):
    doc.start_page("Tier 1 — direct reuse")
    doc.band("Section 02",
             "Tier 1 — the five assets AquaSync can use immediately")

    doc.body(
        "These are MIT-licensed, documented to the wiring-diagram level, and "
        "map one-to-one onto a component AquaSync either has as a weak "
        "placeholder or does not have at all. Each card states what the thing "
        "is, what it gives this project, and what it costs to adopt.")

    asset_card(
        doc, "LAYER 1", DEEP,
        "Automatic Level Monitoring Station — radar, solar, LoRaWAN",
        "OpenIoT/c1_dev_lorawan_automatic_level_monitoring_station",
        [("What it is",
          "A non-contact water level station built on the VEGAPULS C 11 radar "
          "sensor (8 m range) and ICFOSS's own C1-Dev board — an STM32 design "
          "around Murata's CMWX1ZZABZ-091 LoRaWAN module. A 100 W panel and "
          "50 Ah Li-ion pack give over a month of endurance on battery alone, "
          "recharging from flat in about two days."),
         ("What it sends",
          "Water level; the last sixteen transmitted levels; rate of change in "
          "m/hr; and solar and battery voltage and current. The rate-of-change "
          "field is the notable one — it is a derived quantity computed on the "
          "node, not reconstructed later from a level series."),
         ("Why it matters",
          "The repository states it was developed specifically as a component "
          "of a flood monitoring station. It is the same problem AquaSync's "
          "Layer 1 field node addresses, solved to a standard the ₹6,250 rig "
          "cannot reach: no contact with the water, no drift with air "
          "temperature, and no mains power."),
         ("Cost to adopt",
          "Zero for the demonstrator. The ESP32 rig stays as the "
          "hardware-in-the-loop model; this becomes the documented field "
          "specification, with the BOM gaining a fifth tier that is a citation "
          "rather than a purchase.")],
        "Adopt as the reference field node. It converts AquaSync's weakest "
        "claim — that a hobby ultrasonic rig represents a deployable sensor — "
        "into a sourced, costed, already-built answer.")

    asset_card(
        doc, "LAYER 4", BLUE,
        "Flood Monitoring System for Technopark — the operational sibling",
        "OpenIoT/flood-monitoring-technopark",
        [("What it is",
          "A live flood monitoring portal for the Thettiyar canal at "
          "Technopark, Thiruvananthapuram. React, Tailwind and Chart.js on the "
          "front; Node/Express, MongoDB and JWT behind; LoRaWAN sensors via "
          "ChirpStack; deployed with Docker Compose behind Nginx. It sends "
          "email and SMS when levels cross admin-configured thresholds, and "
          "ships separate user, admin and super-admin manuals."),
         ("What it proves",
          "That the alerting half of AquaSync's Layer 4 — thresholds, roles, "
          "notification, historical charts — is a solved and deployed pattern "
          "in Kerala, not a speculative feature. It also shows the governance "
          "shape: a named admin sets the thresholds."),
         ("The contrast",
          "It is purely reactive. It reports the level now and alerts when a "
          "line is crossed. There is no forecast, no simulation and no release "
          "policy — because a canal has no gate to operate. This is the "
          "clearest single illustration of where AquaSync begins."),
         ("Cost to adopt",
          "Do not fork it. Read the three manuals and mirror their role model "
          "and threshold semantics in the Crisis Commander, and cite the system "
          "as the operational precedent AquaSync extends.")],
        "Use as precedent and as contrast: the strongest available evidence "
        "that the alerting layer is understood, and that the decision layer is "
        "the open problem.")

    asset_card(
        doc, "LAYER 2", AQUA,
        "LoRaWAN Water Current Meter — the instrument routing calibration needs",
        "OpenIoT/ulplora_lorawan_water_current_meter_v1.0",
        [("What it is",
          "A Savonius rotor velocity sensor on a wading rod, read by the ULP "
          "LoRa board and reported over LoRaWAN. MIT-licensed, with BOM, "
          "schematics, firmware and a setup guide."),
         ("The problem it solves",
          "This repository's own history records an attempt to calibrate river "
          "routing against Neeleeswaram that was abandoned because the "
          "available data resolution could not resolve the wave. Muskingum's K "
          "and x are properties of a reach, and inferring them from stage alone "
          "at daily resolution is close to hopeless. Direct velocity at a known "
          "section is the measurement that makes the fit identifiable."),
         ("Honest limit",
          "One rotor at one section does not calibrate a 38 km reach. It "
          "constrains the celerity, which converts K from a free parameter "
          "into a bounded one — enough to turn an unconstrained fit into a "
          "checked one.")],
        "The single highest-value item for model credibility: it addresses a "
        "failure this project has already documented rather than a gap it has "
        "merely noticed.")


def page_4(doc):
    doc.start_page("Tier 1 — direct reuse")

    asset_card(
        doc, "LAYER 2", TEAL,
        "Acoustic Rain Gauge with edge ML — and a public labelled dataset",
        "OpenIoT/rainfall-acoustic-sensing  ·  Kaggle: Rain_Data_Master_2023",
        [("What it is",
          "Rainfall estimated from sound. A USB microphone on a Raspberry Pi "
          "records timestamped WAV files; a deep model maps audio to rainfall, "
          "trained against a Davis AeroCone 6466M mechanical gauge as ground "
          "truth. Live data is published to Grafana."),
         ("The asset",
          "The training data is on Kaggle as Rain_Data_Master_2023 — audio "
          "paired with mechanical-gauge rainfall, collected in Kerala. Paired "
          "rainfall observations from this state, openly licensed, are not easy "
          "to come by."),
         ("Use in AquaSync",
          "The SCS-CN runoff layer is driven by forecast rainfall and validated "
          "against almost nothing local. This gives an independent local "
          "rainfall series to sanity-check depths against, and a second, "
          "cheaper sensing modality for the field node."),
         ("Watch out",
          "The published accuracy of these non-mechanical instruments is "
          "modest — the companion ultrasonic anemometer reports 72.6% against "
          "its mechanical reference. Cite them as a research direction and as a "
          "data source, not as calibrated instruments.")],
        "Take the dataset now; treat the sensor as a Phase 2 research thread.")

    asset_card(
        doc, "LAYER 1", GREEN,
        "Davis LoRaWAN Rain Gauge Station — deployed, and framed for dams",
        "OpenIoT/lorawan_based_rain_gauge_davis",
        [("What it is",
          "A Davis AeroCone tipping-bucket gauge on the C1-Dev board, solar "
          "powered, transmitting 15-minute rainfall continuously and a daily "
          "total at 08:00. Deployed at the Greenfield Stadium site in "
          "Thiruvananthapuram. Firmware sits on ST's I-CUBE-LRWAN package; both "
          "ABP and OTAA activation are documented."),
         ("The framing",
          "The repository's own opening line describes the purpose as flood "
          "warning and reservoir management. ICFOSS built this instrument with "
          "AquaSync's use case in mind — the reservoir application is stated, "
          "the decision support to act on it is not."),
         ("Use in AquaSync",
          "Pair it with the ALMS radar station to complete the field kit: "
          "rainfall in, level out, both on one LoRaWAN network, both solar, "
          "both MIT. The daily-total-at-08:00 convention also aligns neatly "
          "with the KSEB bulletin's own daily cadence.")],
        "Adopt alongside the ALMS station as the second half of the documented "
        "field specification.")

    doc.h2("Tier 1, summarised")
    table(doc,
          ["Asset", "Plugs into", "Replaces or fills", "Effort", "Licence"],
          [0.255, 0.13, 0.315, 0.15, 0.15],
          [["ALMS radar level station", "Layer 1",
             "The ESP32 + JSN-SR04T placeholder, for field use", "Cite now; build later", "MIT"],
           ["Davis LoRaWAN rain gauge", "Layer 1",
            "No local rainfall observation exists today", "Cite now; build later", "MIT"],
           ["Water current meter", "Layer 2",
            "Muskingum K and x, currently unconstrained", "Design work", "MIT"],
           ["Acoustic rain gauge dataset", "Layer 2",
            "Local rainfall ground truth for SCS-CN", "Download and analyse", "Kaggle terms"],
           ["Flood portal (Technopark)", "Layer 4",
            "Threshold, role and notification semantics", "Read the manuals", "Unstated"]])

    callout(doc, "Read the licences before you lean on them",
            "The ALMS station, the current meter, the rain gauge and the C1-Dev "
            "board all carry MIT, which is compatible with AquaSync's own MIT "
            "licence. Several other repositories — including the Technopark "
            "flood portal — carry no licence file at all. An unlicensed public "
            "repository is not open source; it is all-rights-reserved code you "
            "can read. Cite those, learn from them, and ask before reusing.",
            colour=AMBER)


def page_5(doc):
    doc.start_page("The integration map")
    doc.band("Section 03",
             "Where each ICFOSS asset attaches to AquaSync's architecture")

    doc.body(
        "AquaSync is built in four layers, and the ICFOSS portfolio maps onto "
        "them with a striking asymmetry. Layers 1 and 4 — getting data in, and "
        "getting decisions out to people — are densely covered by work that "
        "already exists and runs. Layer 2 is partially covered, mostly by "
        "instruments rather than models. Layer 3, the decision layer, is "
        "essentially empty. That asymmetry is the argument for this project.")

    integration_map(doc)

    callout(doc, "The gap is the thesis",
            "Across 54 published projects and roughly 120 repositories, there "
            "is no forward simulation of a water body, no optimisation over an "
            "operating policy, and no counterfactual analysis of a past event. "
            "The closest structural analogue is QNetPlanner — a QGIS plugin "
            "that selects a minimum set of gateways under weighted cost and "
            "elevation criteria. It is genuine multi-criteria optimisation, but "
            "over static infrastructure placement, not over a time-varying "
            "control policy. AquaSync's Layer 3 has no counterpart in the "
            "portfolio, which is precisely why it is worth building.",
            colour=TEAL, tint=colors.HexColor("#EBF6F4"))


def page_6(doc):
    doc.start_page("Hardware path")
    doc.band("Section 04",
             "Tier 2 — the hardware and network path, from expo rig to field")

    doc.body(
        "AquaSync's V1 rig is correct for what it is: a ₹6,250 tabletop "
        "demonstrator that closes a control loop onto a servo in a 30 cm "
        "acrylic tank. It is not a field node, and the project already says so. "
        "ICFOSS's open hardware line is what a field node looks like, and "
        "showing both — the rig you can touch, and the station you would "
        "actually install — is a stronger position than either alone.")

    doc.h2("Field node: what changes between the rig and a deployment")
    table(doc,
          ["", "AquaSync V1 rig (today)", "ICFOSS field station (the target)"],
          [0.20, 0.40, 0.40],
          [["Controller", "ESP32-WROOM-32, dual-core 240 MHz, Wi-Fi",
            "C1-Dev v1.0 — STM32 with Murata CMWX1ZZABZ-091; or ULP LoRa"],
           ["Level sensing", "JSN-SR04T ultrasonic, 25–450 cm, ±1 cm, needs a "
            "DS18B20 to correct sound speed",
            "VEGAPULS C 11 radar, 8 m, non-contact, no temperature correction "
            "needed"],
           ["Link", "Wi-Fi with LoRa fallback",
            "LoRaWAN to ChirpStack, via ICFOSS gateway designs"],
           ["Power", "12 V 5 A mains adapter",
            "100 W solar with MPPT and a 50 Ah Li-ion pack; >1 month of "
            "battery-only endurance"],
           ["Telemetry", "Level, temperature, pressure, flow",
            "Level, last 16 levels, rate of change in m/hr, plus solar and "
            "battery voltage and current"],
           ["Honest status", "Built, demonstrable, closes a loop on a servo",
            "Published and documented by ICFOSS; not built or verified by this "
            "project"]])

    doc.h2("The supporting network stack, all published")
    bullets(doc, [
        "LoRaWAN_in_a_Box and rpi-with-rak831-gateway — packet forwarder plus "
        "network server, and a Raspberry Pi gateway build. Enough to stand up a "
        "private LoRaWAN network without depending on anyone's infrastructure, "
        "which matters for a system that claims to work offline.",

        "gateway_docking_station_v1.0, solar-charge-controller-mppt and "
        "solar-battery-pack-monitoring-system-v1.0 — the unglamorous half of a "
        "remote deployment: keeping the gateway alive on a hill through a "
        "monsoon, and knowing when it will not be.",

        "LoraLink (api-lorawan.openiot.in) — a REST layer over ChirpStack that "
        "reads from InfluxDB rather than the LoRaWAN stack directly, with token "
        "and user administration. This is the shape of the seam between "
        "AquaSync's ingestion layer and someone else's sensor network.",

        "lorawan-range-mapper_v1.0 and TriLocate — coverage measurement and "
        "fine-timestamp triangulation, for verifying that a planned gateway "
        "site actually reaches the nodes you placed.",
    ], colour=AQUA)

    doc.h2("Gateway siting: a solved method for an unsolved AquaSync question")
    doc.body(
        "AquaSync has never answered where sensors and gateways should go in "
        "the Idukki catchment. ICFOSS has answered that class of question "
        "twice. Their viewshed methodology takes DEMs from ASF Alaska, treats "
        "candidate gateway sites as observer points at a stated antenna height, "
        "computes visibility in QGIS, and reads coverage off the result — the "
        "same approach they used to site air-quality sensors in "
        "Thiruvananthapuram and, notably, for water level monitoring at CET and "
        "Barton Hill. QNetPlanner then automates the selection: given candidate "
        "sites, a cost field normalised 1–10 and an elevation weighting, it "
        "returns a minimum set of gateways and sensors covering the area. "
        "AquaSync already derives Idukki's catchment from a DEM, so the input "
        "layer exists. This is a weekend of QGIS work that would produce a "
        "genuinely new figure: a defensible sensor network design for the "
        "catchment, with the number of gateways it needs.")

    callout(doc, "A concrete, cheap, high-yield next figure",
            "Run QNetPlanner over the existing DEM-derived Idukki catchment and "
            "publish the resulting gateway and node layout. It costs no "
            "hardware, uses a published open-source method that ICFOSS has "
            "already validated on Kerala terrain, and turns 'ESP32 field nodes' "
            "in the architecture diagram into a specific, sited, countable "
            "network.",
            colour=GREEN, tint=colors.HexColor("#EDF6EF"))


def page_7(doc):
    doc.start_page("Geodata and language")
    doc.band("Section 05",
             "Tier 3 — geodata, routing, and an unexpected route to the 2018 data")

    doc.h2("Geospatial: the catchment is already mapped")
    table(doc,
          ["ICFOSS asset", "What it holds", "Use in AquaSync"],
          [0.24, 0.38, 0.38],
          [["OpenSDI / Kerala Geoportal",
            "GeoNode-based open replacement for the proprietary KSDI stack; "
            "road networks, stream networks, administrative boundaries, freely "
            "licensed",
            "Authoritative channel and boundary geometry for the Periyar reach, "
            "and the natural place to publish AquaSync's own catchment layer"],
           ["Ini Njan Ozhukkate (stream mapping)",
            "Small watercourses across 249 highland panchayats, mapped with "
            "Nava Keralam Mission and contributed to OpenStreetMap",
            "An independent check on the DEM-derived Idukki catchment geometry; "
            "the tributary network the runoff model implicitly assumes"],
           ["Viewshed / QNetPlanner",
            "DEM-driven visibility analysis (ASF Alaska) and a QGIS plugin for "
            "minimum-set gateway and sensor selection",
            "Sensor network design for the catchment — see Section 04"],
           ["Spatial DECM",
            "A browser-based GIS viewer and editor; drag-and-drop GeoJSON, "
            "multiple basemaps, no installation, runs entirely client-side",
            "A map pane for the dashboard that keeps the no-build-step, "
            "opens-from-the-filesystem constraint intact"],
           ["RescueRoute",
            "Optimal routing that accounts for vehicle size against road width, "
            "built for fire services; live tracking and reachability reporting",
            "The evacuation half of the Crisis Commander. A release schedule "
            "implies who must move and by which road — this computes it"],
           ["Thermal drone / UAV disaster work",
            "Tarot X6 hexacopter, FLIR Vue Pro R on a 3-axis gimbal, 20 min "
            "endurance, YOLOv5 human detection, Mission Planner and QGC",
            "Post-event validation of modelled inundation extent, and search "
            "support once a release has happened"]])

    doc.h2("The Malayalam stack — and the 2018 problem")
    doc.body(
        "AquaSync's Layer 4 promises Malayalam alerts, and ICFOSS is the "
        "single best source in the state for that: OCR (Dhriti and Lekha), a "
        "tagged corpus, a morphological analyser, a root extractor, a "
        "LibreOffice spell checker and Malayalam text summarisation, all "
        "public. Any of it improves the alert path. But there is a second, less "
        "obvious use that is worth more.")

    callout(doc, "OCR as a route to the missing 2018 flood data",
            "This project's most-stated limitation is that its dataset begins "
            "on 13 August 2020, so the 2018 flood — the reason anyone cares — "
            "cannot be modelled quantitatively. That is a limitation of one "
            "GitHub scraper, not of the historical record: KSEB and KSDMA "
            "published daily dam bulletins throughout 2018, as documents. "
            "ICFOSS's OCR stack, including a Malayalam OCR with integrated "
            "handwritten-text recognition, is built precisely to turn published "
            "Kerala documents into structured data. Recovering even a partial "
            "2018 Idukki series would let AquaSync replay the flood everyone "
            "actually remembers — and would be a genuine contribution back, not "
            "just a borrowing. It is speculative until the bulletins are "
            "located and their quality assessed, and it should be scoped after "
            "the current deliverables are safe.",
            colour=PLUM, tint=colors.HexColor("#F3F0FA"))

    doc.h2("What AquaSync gives back")
    doc.body(
        "A reuse analysis that only takes is a weak proposal. The reciprocal "
        "case is unusually clear, because the thing AquaSync has is the thing "
        "the portfolio lacks.")
    bullets(doc, [
        "A decision layer for sensor networks ICFOSS has already deployed. "
        "Their level stations, rain gauges and flood portal produce readings "
        "and thresholds; AquaSync produces a forward simulation and a "
        "recommended action from the same inputs.",

        "A validated Kerala reservoir model — level–storage fitted at r² = "
        "0.9957 over 1,836 validated rows, an October 2021 replay to 0.30 m "
        "mean error, and an independent August 2022 replay. Reusable for any "
        "Kerala reservoir with published bulletins.",

        "A documented data-quality finding: roughly 11% of the widely-used "
        "public Kerala dam dataset is corrupt, with storage above physical "
        "capacity between September 2020 and April 2021. Fitting on the raw "
        "feed gives r² = 0.784 against 0.996 on validated rows. Anyone else "
        "building on that feed needs to know.",

        "Malayalam alert templates for reservoir operations, which the "
        "Malayalam Computing group could fold into a domain corpus.",
    ], colour=TEAL)


def page_8(doc):
    _FC_LO, _FC_HI = forecast_excess_cost()
    doc.start_page("Engagement plan")
    doc.band("Section 06", "What to actually do, in order")

    doc.body(
        "Ordered by ratio of credibility gained to time spent, and scoped so "
        "that nothing here competes with the deliverables already committed in "
        "ACTION_PLAN.md. The first three items cost no hardware and no travel.")

    table(doc,
          ["#", "Action", "Why it pays", "Effort", "When"],
          [0.045, 0.275, 0.36, 0.145, 0.175],
          [["1", "Add an ICFOSS references section to hardware/ and "
            "docs/data-sources.md",
            "Turns the field-node claim from aspiration into a sourced, "
            "MIT-licensed, already-built specification. Pure documentation.",
            "An afternoon", "Immediately"],
           ["2", "Download Rain_Data_Master_2023 and cross-check local "
            "rainfall depths",
            "The only openly licensed paired rainfall dataset from Kerala found "
            "in this review. Gives the runoff layer a local reference.",
            "A day", "This week"],
           ["3", "Run QNetPlanner over the DEM-derived Idukki catchment",
            "Produces a new, defensible figure — a sited sensor and gateway "
            "network — using a method ICFOSS validated on Kerala terrain.",
            "A weekend", "Before the expo"],
           ["4", "Read the Technopark flood portal manuals; align Crisis "
            "Commander roles and thresholds",
            "Matches the governance semantics of a system already running in "
            "Kerala, which is what a reviewer will ask about.",
            "A day", "Before the expo"],
           ["5", "Write to info@icfoss.in describing the project and the reuse",
            "They publish an Express Interest route on every project page and "
            "run an incubator. The worst case is no reply; the best case is a "
            "conversation with the people who mapped KSEB's network.",
            "An hour", "Now — lead time is long"],
           ["6", "Pull the OSM stream network for the Idukki highland "
            "panchayats",
            "Independent validation of catchment geometry this project derived "
            "from a DEM alone.",
            "A few days", "Post-expo"],
           ["7", "Scope the 2018 bulletin OCR recovery",
            "Potentially removes this project's largest stated limitation. "
            "Speculative — assess document availability first.",
            "Unknown; scope first", "Post-expo"],
           ["8", "Explore the LoRaWAN CoE and Swatantra Incubator routes",
            "The institutional path from an expo project to a deployed one, "
            "with Hardware Mission Kerala behind it.",
            "Ongoing", "Post-expo"]],
          size=7.3)

    doc.h2("Risks worth naming before you build on any of this")
    bullets(doc, [
        "Several repositories carry no licence file. Public is not open. The "
        "Technopark flood portal in particular should be cited and learned "
        "from, not forked, until its licence is clarified.",

        "Repository activity is uneven — some were last touched in 2024, and "
        "documentation quality varies from wiring-diagram-complete to a stub "
        "README. Verify a repository is alive before making it a dependency.",

        "No ICFOSS repository reviewed here documents a deployment in the "
        "Idukki catchment. Their water-level work is in Thiruvananthapuram "
        "(Thettiyar canal, CET, Barton Hill) and Kattakkada. Coverage in the "
        "Periyar basin should be treated as an open question, not an assumption.",

        "The non-mechanical instruments are research-grade: the ultrasonic "
        "anemometer reports 72.6% accuracy against its mechanical reference, "
        "and the acoustic rain gauge's operational accuracy is not stated. "
        "Present them as directions, not as calibrated sensors.",

        "Nothing here changes AquaSync's central constraint. Deciding from a real "
        f"ensemble costs {_FC_LO:+.0f}% to {_FC_HI:+.0f}% more than hindsight, and the "
        "penalty grows with lead time. Better sensors improve the present state; they "
        "do not supply the forecast.",
    ], colour=AMBER, size=8.3, leading=10.6, gap=2.4)

    doc.h2("The one-line version")
    doc.body(
        "ICFOSS has built Kerala's environmental sensing nervous system and "
        "given it away under MIT. Nobody has built the brain. AquaSync should "
        "be that brain, should say so plainly, and should be engineered from "
        "the outset to plug into their nerves rather than grow its own.",
        size=9.7, leading=13.0, colour=DEEP, gap=4,
        font="Helvetica-Bold")

    doc.tail(
        "Sources: icfoss.in/projects and its 54 project detail pages; the "
        "icfoss GitLab organisation and its nine subgroups, read at the "
        "repository-README level; openiot.in. Reviewed 30 August 2026. "
        "Specifications quoted here come from the repositories, not the "
        "marketing pages.")


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = Doc(OUT)
    page_1(doc)
    page_2(doc)
    page_3(doc)
    page_4(doc)
    page_5(doc)
    page_6(doc)
    page_7(doc)
    page_8(doc)
    doc.footer()
    doc.c.showPage()
    doc.c.save()
    print(f"wrote {OUT.relative_to(ROOT)}  ({doc.page} pages)")


if __name__ == "__main__":
    main()
