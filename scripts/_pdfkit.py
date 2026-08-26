"""Shared PDF styling and flowable helpers for AquaSync reports.

Both the project dossier and the research report render from here, so they
look like one publication rather than two documents that happen to be about
the same project.

Deliberately plain: reportlab base-14 fonts only, no embedded typefaces, no
external assets. The rupee sign is the one glyph worth knowing about - it is
absent from Helvetica and renders as a black box, so use ``rs()`` rather than
the literal character.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    Table,
    TableStyle,
)

# --- palette ---------------------------------------------------------------

INK = colors.HexColor("#12263a")
MUTED = colors.HexColor("#5b6b7f")
BLUE = colors.HexColor("#1f6feb")
RED = colors.HexColor("#d1242f")
GREEN = colors.HexColor("#1a7f37")
AMBER = colors.HexColor("#bf8700")
VIOLET = colors.HexColor("#6f42c1")
RULE_C = colors.HexColor("#dde3ea")
BG = colors.HexColor("#f6f8fa")

TINT_AMBER = "#fff8e5"
TINT_RED = "#fdeef0"
TINT_GREEN = "#eefbf1"
TINT_BLUE = "#eef4fd"
TINT_VIOLET = "#f4f0fb"

# --- geometry --------------------------------------------------------------

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


def rs(amount: str | float) -> str:
    """Format rupees. Helvetica has no U+20B9 glyph, so never use the sign."""
    return f"Rs&nbsp;{amount}"


# --- styles ----------------------------------------------------------------

def build_styles() -> dict:
    ss = getSampleStyleSheet()
    s = {}
    s["title"] = ParagraphStyle("title", parent=ss["Title"], fontName="Helvetica-Bold",
                                fontSize=30, leading=34, textColor=INK, spaceAfter=4)
    s["subtitle"] = ParagraphStyle("subtitle", parent=ss["Normal"], fontName="Helvetica",
                                   fontSize=13.5, leading=18, textColor=MUTED, spaceAfter=16)
    s["h1"] = ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold",
                             fontSize=17, leading=21, textColor=INK,
                             spaceBefore=16, spaceAfter=7)
    s["h2"] = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold",
                             fontSize=12.5, leading=16, textColor=INK,
                             spaceBefore=12, spaceAfter=5)
    s["h3"] = ParagraphStyle("h3", parent=ss["Heading3"], fontName="Helvetica-Bold",
                             fontSize=10.5, leading=14, textColor=BLUE,
                             spaceBefore=9, spaceAfter=3)
    s["body"] = ParagraphStyle("body", parent=ss["BodyText"], fontName="Helvetica",
                               fontSize=9.6, leading=14.2, textColor=INK,
                               alignment=TA_JUSTIFY, spaceAfter=7)
    s["bullet"] = ParagraphStyle("bullet", parent=s["body"], leftIndent=12,
                                 bulletIndent=2, spaceAfter=3.5)
    s["caption"] = ParagraphStyle("caption", parent=ss["Normal"], fontName="Helvetica-Oblique",
                                  fontSize=8.2, leading=11.5, textColor=MUTED,
                                  spaceBefore=3, spaceAfter=11)
    s["cell"] = ParagraphStyle("cell", parent=ss["Normal"], fontName="Helvetica",
                               fontSize=8.3, leading=11, textColor=INK)
    s["cellb"] = ParagraphStyle("cellb", parent=s["cell"], fontName="Helvetica-Bold")
    s["cellsm"] = ParagraphStyle("cellsm", parent=ss["Normal"], fontName="Helvetica",
                                 fontSize=7.4, leading=9.6, textColor=INK)
    s["mono"] = ParagraphStyle("mono", parent=ss["Normal"], fontName="Courier",
                               fontSize=7.6, leading=10, textColor=INK)
    s["callout"] = ParagraphStyle("callout", parent=s["body"], fontSize=9.6, leading=14,
                                  leftIndent=9, rightIndent=9, spaceBefore=5, spaceAfter=5)
    s["kpi_num"] = ParagraphStyle("kpi_num", parent=ss["Normal"], fontName="Helvetica-Bold",
                                  fontSize=19, leading=22, textColor=INK, alignment=TA_CENTER)
    s["kpi_lbl"] = ParagraphStyle("kpi_lbl", parent=ss["Normal"], fontName="Helvetica",
                                  fontSize=7.6, leading=9.6, textColor=MUTED, alignment=TA_CENTER)
    s["footer"] = ParagraphStyle("footer", parent=ss["Normal"], fontName="Helvetica",
                                 fontSize=7.5, textColor=MUTED)
    return s


S = build_styles()


# --- flowables -------------------------------------------------------------

def para(text: str, style: str = "body"):
    return Paragraph(text, S[style])


def bullets(items: list[str], style: str = "bullet"):
    return [Paragraph(t, S[style], bulletText="•") for t in items]


def rule(space_before: float = 3, colour=RULE_C):
    return HRFlowable(width="100%", thickness=0.8, color=colour,
                      spaceBefore=space_before, spaceAfter=6)


def callout(title: str, body: str, accent=AMBER, tint=TINT_AMBER, width=CONTENT_W):
    inner = [Paragraph(f"<b>{title}</b>", S["callout"]), Paragraph(body, S["callout"])]
    t = Table([[inner]], colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(tint)),
        ("LINEBEFORE", (0, 0), (0, -1), 2.4, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def data_table(header: list[str], rows: list[list[str]], widths=None,
               align_right=(), small: bool = False, zebra: bool = False):
    style_key = "cellsm" if small else "cell"
    head = [Paragraph(f"<b>{h}</b>", S["cellb"]) for h in header]
    body = [[Paragraph(str(c), S[style_key]) for c in r] for r in rows]
    t = Table([head] + body, colWidths=widths, repeatRows=1, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BG),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, INK),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, RULE_C),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
    ]
    if zebra:
        for i in range(1, len(body) + 1, 2):
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#fbfcfd")))
    for c in align_right:
        style.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    return t


def kpi_row(items: list[tuple[str, str]], width=CONTENT_W):
    cells = [[Paragraph(v, S["kpi_num"]), Paragraph(lbl, S["kpi_lbl"])] for v, lbl in items]
    t = Table([cells], colWidths=[width / len(items)] * len(items))
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, -1), BG),
        ("LINEAFTER", (0, 0), (-2, -1), 0.6, RULE_C),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE_C),
    ]))
    return t


def figure(path: Path, caption: str, width: float = CONTENT_W):
    if not path.exists():
        return para(f"<i>[missing figure: {path.name}]</i>", "caption")
    from PIL import Image as PILImage

    with PILImage.open(path) as im:
        w, h = im.size
    img = Image(str(path), width=width, height=width * h / w)
    return KeepTogether([img, para(caption, "caption")])


def badge(text: str, kind: str = "neutral") -> str:
    """Inline coloured label for use inside a table cell."""
    palette = {
        "high": "#1a7f37", "do-now": "#1a7f37", "yes": "#1a7f37", "ok": "#1a7f37",
        "medium": "#bf8700", "do-next": "#bf8700", "partly": "#bf8700",
        "low": "#5b6b7f", "later": "#5b6b7f", "neutral": "#5b6b7f",
        "reject": "#d1242f", "no": "#d1242f", "blocked": "#d1242f",
    }
    colour = palette.get(str(text).strip().lower().split()[0] if text else "neutral", "#5b6b7f")
    return f'<font color="{colour}"><b>{text}</b></font>'


# --- page furniture --------------------------------------------------------

def make_page_footer(label: str):
    """Returns an onPage callback drawing a footer rule and page number."""

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(RULE_C)
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN, MARGIN - 5 * mm, PAGE_W - MARGIN, MARGIN - 5 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, MARGIN - 9.5 * mm, label)
        canvas.drawRightString(PAGE_W - MARGIN, MARGIN - 9.5 * mm, f"{canvas.getPageNumber()}")
        canvas.restoreState()

    return on_page


def make_cover_banner(height_mm: float = 118, fill: str = "#0d2137", accent: str = "#1f6feb"):
    """Returns an onPage callback painting the cover banner."""

    def on_cover(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor(fill))
        canvas.rect(0, PAGE_H - height_mm * mm, PAGE_W, height_mm * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor(accent))
        canvas.rect(0, PAGE_H - (height_mm + 3) * mm, PAGE_W, 3 * mm, stroke=0, fill=1)
        canvas.restoreState()

    return on_cover
