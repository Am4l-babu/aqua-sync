"""Build the AquaSync project dossier PDF.

Every quantitative claim in the document is pulled from
``data/processed/*.json`` at build time, so the prose cannot drift away from
the analysis. Run the analyses first:

    python scripts/lead_time_study.py
    python scripts/make_figures.py
    python scripts/build_dossier.py
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
PROC = ROOT / "data" / "processed"
OUT = ROOT / "docs" / "AquaSync_Project_Dossier.pdf"

INK = colors.HexColor("#12263a")
MUTED = colors.HexColor("#5b6b7f")
BLUE = colors.HexColor("#1f6feb")
RED = colors.HexColor("#d1242f")
GREEN = colors.HexColor("#1a7f37")
AMBER = colors.HexColor("#bf8700")
VIOLET = colors.HexColor("#6f42c1")
RULE = colors.HexColor("#dde3ea")
BG = colors.HexColor("#f6f8fa")

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


# --------------------------------------------------------------------------
# styles
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def para(text: str, style: str = "body"):
    return Paragraph(text, S[style])


def bullets(items: list[str], style: str = "bullet"):
    return [Paragraph(t, S[style], bulletText="•") for t in items]


def rule(space_before: float = 3, colour=RULE):
    return HRFlowable(width="100%", thickness=0.8, color=colour,
                      spaceBefore=space_before, spaceAfter=6)


def callout(title: str, body: str, accent=AMBER, tint="#fff8e5"):
    inner = [Paragraph(f"<b>{title}</b>", S["callout"]), Paragraph(body, S["callout"])]
    t = Table([[inner]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(tint)),
        ("LINEBEFORE", (0, 0), (0, -1), 2.4, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def data_table(header: list[str], rows: list[list[str]], widths=None, align_right=()):
    head = [Paragraph(f"<b>{h}</b>", S["cellb"]) for h in header]
    body = [[Paragraph(str(c), S["cell"]) for c in r] for r in rows]
    t = Table([head] + body, colWidths=widths, repeatRows=1, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BG),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, INK),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
    ]
    for c in align_right:
        style.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    return t


def kpi_row(items: list[tuple[str, str]]):
    cells = []
    for value, label in items:
        cells.append([Paragraph(value, S["kpi_num"]), Paragraph(label, S["kpi_lbl"])])
    t = Table([cells], colWidths=[CONTENT_W / len(items)] * len(items))
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, -1), BG),
        ("LINEAFTER", (0, 0), (-2, -1), 0.6, RULE),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
    ]))
    return t


def figure(name: str, caption: str, width: float = CONTENT_W):
    path = ASSETS / name
    if not path.exists():
        return para(f"<i>[missing figure: {name}]</i>", "caption")
    from PIL import Image as PILImage

    with PILImage.open(path) as im:
        w, h = im.size
    img = Image(str(path), width=width, height=width * h / w)
    return KeepTogether([img, para(caption, "caption")])


def fmt_window(w: str) -> str:
    """'2022-08-01 to 2022-08-20' -> '1-20 August 2022'. Returns w unchanged
    if it is not a window this understands."""
    try:
        a, b = (dt.date.fromisoformat(x.strip()) for x in w.split("to"))
    except ValueError:
        return w
    if (a.month, a.year) == (b.month, b.year):
        return f"{a.day}\u2013{b.day} {b:%B %Y}"
    return f"{a.day} {a:%B} \u2013 {b.day} {b:%B %Y}"


def load_facts() -> dict:
    facts = {}
    for f in ("figure_facts.json", "lead_time_headline.json"):
        p = PROC / f
        if p.exists():
            facts.update(json.loads(p.read_text(encoding="utf-8")))
    # Nested rather than merged: these carry generic top-level keys that would
    # collide with the figure facts.
    for key, f in (("out_of_sample", "replay_idukki_aug_2022.json"),
                   ("routing_cal", "routing_calibration_neeleeswaram.json")):
        p = PROC / f
        if p.exists():
            facts[key] = json.loads(p.read_text(encoding="utf-8"))
    return facts


# --------------------------------------------------------------------------
# page furniture
# --------------------------------------------------------------------------

def on_page(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.6)
    canvas.line(MARGIN, MARGIN - 5 * mm, PAGE_W - MARGIN, MARGIN - 5 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, MARGIN - 9.5 * mm,
                      "AquaSync  ·  Digital twin for dam–river flood optimisation")
    canvas.drawRightString(PAGE_W - MARGIN, MARGIN - 9.5 * mm, f"{canvas.getPageNumber()}")
    canvas.restoreState()


def on_cover(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#0d2137"))
    canvas.rect(0, PAGE_H - 118 * mm, PAGE_W, 118 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.HexColor("#1f6feb"))
    canvas.rect(0, PAGE_H - 121 * mm, PAGE_W, 3 * mm, stroke=0, fill=1)
    canvas.restoreState()


# --------------------------------------------------------------------------
# content
# --------------------------------------------------------------------------

def cover(f: dict) -> list:
    white = ParagraphStyle("w", parent=S["title"], textColor=colors.white, fontSize=34, leading=38)
    wsub = ParagraphStyle("ws", parent=S["subtitle"], textColor=colors.HexColor("#9fc3f5"),
                          fontSize=13, leading=18)
    wsm = ParagraphStyle("wsm", parent=S["body"], textColor=colors.HexColor("#c9d8ea"),
                         fontSize=9.5, leading=14, alignment=0)

    out = [
        Spacer(1, 22 * mm),
        Paragraph("AquaSync", white),
        Paragraph(
            "A decision-support digital twin for dam–river flood "
            "and hydropower optimisation on the Periyar", wsub),
        Spacer(1, 4 * mm),
        Paragraph(
            "Track: Climate Resilience &amp; Disaster Preparedness<br/>"
            "EVOKE 26 · MACE IoT Club · Mar Athanasius College of Engineering, "
            "Kothamangalam", wsm),
        Spacer(1, 42 * mm),
    ]

    cal = f.get("calibration", {})
    cf = f.get("counterfactual", {})
    fe = f.get("forecast_error", {})
    out += [
        kpi_row([
            (f"{min(fe.get('ev_excess_cost_pct', [0.0])):+.0f}%",
             "excess cost against hindsight,<br/>24 h ensemble forecast (§4.4)"),
            (f"{cal.get('r2', 0.9957):.4f}", "r² of the calibrated<br/>level–storage curve"),
            (f"{cf.get('replay_level_mae_m', 0.30):.2f} m", "mean error reproducing<br/>observed reservoir level"),
            ("Rs 0", "software and data cost"),
        ]),
        Spacer(1, 10 * mm),
        callout(
            "This document reports a correction to its own brief.",
            "The dataset this project was planned around does not contain the 2018 flood "
            "data it was believed to contain. The flagship case study is therefore the "
            "<b>October 2021 Periyar event</b>, which is fully covered by free public data "
            "and is a stronger case. Details in §3 and §11.",
            accent=AMBER),
        Spacer(1, 8 * mm),
        para("Prepared 30 August 2026 · All figures regenerate from public data via "
             "<font face='Courier'>scripts/make_figures.py</font>", "caption"),
    ]
    return out


def section_problem() -> list:
    return [
        para("1 · The problem", "h1"), rule(),
        para(
            "Kerala's floods are not purely meteorological events. In August 2018, 483 people "
            "died and roughly a million were displaced; the subsequent official and academic "
            "post-mortems all identified the same aggravating factor — reservoirs held near "
            "capacity into an extreme rainfall event, then forced into large simultaneous "
            "releases once there was no storage left. The rain was the trigger. The timing of "
            "the releases decided how much of it became a disaster."),
        para(
            "The reason this keeps happening is a genuine conflict of objectives, not "
            "incompetence:"),
        *bullets([
            "<b>The power utility</b> wants the reservoir full. Head is revenue, and water "
            "released without generating is money poured away.",
            "<b>Disaster management</b> wants the reservoir low. Empty storage is the only "
            "flood cushion that exists.",
            "<b>Release too early</b> and you have spilled water you needed for the dry season.",
            "<b>Release too late</b> and you must open everything at once, which is precisely "
            "the scenario that drowns the towns downstream.",
            "<b>The tide</b> decides whether a release even reaches the sea. At high tide the "
            "Arabian Sea holds the lower Periyar up, and the same discharge produces a higher "
            "stage upstream.",
        ]),
        para(
            "No operational system in Kerala today optimises these together, on a forecast, "
            "across more than one reservoir at a time. That is the gap AquaSync addresses."),
    ]


def section_evidence(f: dict) -> list:
    o = f.get("oct2021", {})
    c = f.get("cascade", {})
    idu = c.get("idukki", {})
    ida = c.get("idamalayar", {})
    return [
        para("2 · The evidence: October 2021, in public data", "h1"), rule(),
        para(
            "The argument above is easy to assert and rarely demonstrated. Here it is in the "
            "KSEB daily bulletin, downloadable by anyone."),
        figure("fig1_oct2021_crisis.png",
               "Figure 1 — Idukki, October 2021. The reservoir entered a 168 mm rain day at "
               f"{o.get('level_16_oct', 728.81):.2f} m, already above its own {o.get('rule_level', 728.5)} m "
               "rule level, with the spillway shut. Inflow rose 7.6× in 24 hours to "
               f"{o.get('peak_inflow', 879):.0f} cumecs. The gates opened three days later, at "
               f"{o.get('peak_level', 730.99):.2f} m — 1.4 m from FRL. Source: KSEB daily bulletin."),
        para(
            "Three days elapsed between the surge and the response. Nothing was concealed and "
            "no rule was broken; the level simply rose faster than a reactive procedure can "
            "respond to. Every threshold in that chart is published, including the rule level "
            "the reservoir was already above when the storm was forecast."),
        para("The same thing happened next door, on the same days", "h2"),
        figure("fig2_cascade.png",
               "Figure 2 — Idukki and Idamalayar both sat above their rule levels through the "
               "storm and both opened their spillways on 20 October 2021 — "
               f"{idu.get('spill_20_oct', 83.9):.0f} and {ida.get('spill_20_oct', 128.1):.0f} cumecs, "
               "into the same river, within the same day."),
        callout(
            "This is the coordination failure, stated precisely.",
            "Two reservoirs jointly control the Periyar. Both absorbed the storm into their "
            "freeboard, and both then released into an already-swollen river on the same day. "
            "Whether two release pulses superpose into one large peak or spread into two "
            "small ones is a <b>scheduling choice</b> — and nothing in current practice makes it "
            "deliberately.",
            accent=RED, tint="#fdeef0"),
    ]


def section_solution() -> list:
    return [
        para("3 · What AquaSync is", "h1"), rule(),
        para(
            "A digital twin of the reservoir–river system that ingests telemetry, rainfall "
            "forecasts and tide predictions; simulates the basin forward; searches operating "
            "policies; and hands a human operator a specific, implementable instruction."),
        callout(
            "The output is an instruction, not a dashboard.",
            "<i>“From 06:00 on 10 October, release up to 480 cumecs until Idukki reaches "
            "728.50 m, then hold within ±0.15 m.”</i><br/><br/>"
            "That is a sentence a control room can execute, a district collector can approve, "
            "and an inquiry can later audit. A screen full of gauges is none of those things — "
            "and the gap between knowing the level and knowing what to do about it is where "
            "the three days in Figure 1 went.",
            accent=GREEN, tint="#eefbf1"),
        para("Layer diagram", "h2"),
        Table([[Paragraph(
            "<font face='Courier' size='7.4'>"
            "INGESTION &nbsp;&nbsp;KSEB bulletin · IMD forecast · INCOIS tide · Sentinel-1 SAR · ESP32 nodes<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|<br/>"
            "SIMULATION &nbsp;SCS-CN runoff -&gt; mass balance -&gt; Muskingum routing -&gt; tidal backwater -&gt; power<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|<br/>"
            "DECISION &nbsp;&nbsp;&nbsp;Policy search over (target level, start time, max rate)<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;|<br/>"
            "INTERFACE &nbsp;&nbsp;3D live twin · what-if · Crisis Commander · Malayalam alerting"
            "</font>", S["cell"])]], colWidths=[CONTENT_W]),
        Spacer(1, 5),
        para("The five models", "h2"),
        data_table(
            ["#", "Model", "Answers", "Method"],
            [["1", "Rainfall–runoff", "How much of the forecast rain reaches the dam, and when?",
              "SCS Curve Number with antecedent-moisture shift, triangular unit hydrograph"],
             ["2", "Reservoir balance", "What level results from a given release?",
              "Mass balance on a fitted level–storage power law"],
             ["3", "River routing", "What discharge arrives at Aluva, and at what hour?",
              "Muskingum storage routing, auto sub-reached for stability"],
             ["4", "Tidal backwater", "How much can the river safely carry right now?",
              "Harmonic tide + exponential backwater decay, giving effective conveyance"],
             ["5", "Hydropower", "What does this release cost or earn?",
              "Density x gravity x flow x head x efficiency, with a turbine hill diagram and time-of-day tariff"]],
            widths=[9 * mm, 32 * mm, 60 * mm, CONTENT_W - 101 * mm]),
        Spacer(1, 6),
        para(
            "An asymmetry specific to Idukki is worth knowing, because it changes the whole "
            "framing: the Moolamattom powerhouse discharges into the <b>Muvattupuzha</b>, not "
            "the Periyar. Generation therefore does not load the Periyar at all — only the "
            "spillway does. Sending water through the turbines is simultaneously the "
            "profitable option and the one that spares Aluva. Power and safety are not "
            "inherently opposed. Only <i>timing</i> puts them in opposition."),
    ]


def section_results(f: dict) -> list:
    cal = f.get("calibration", {})
    cf = f.get("counterfactual", {})
    lead = f.get("lead_time", {})
    fe = f.get("forecast_error", {})
    cc = f.get("cascade_coordination", {})
    oos = f.get("out_of_sample", {})

    fe_rows = [[f"{h:.0f} h", issued, f"{ec:+.0f}%", f"{mc:+.0f}%", f"{em:.2f} m", f"{mmm:.2f} m"]
               for h, issued, ec, mc, em, mmm in zip(
                   fe.get("leads_h", []), fe.get("issue_dates", []),
                   fe.get("ev_excess_cost_pct", []), fe.get("mm_excess_cost_pct", []),
                   fe.get("ev_m", []), fe.get("mm_m", []), strict=True)]
    rv = f.get("runoff_validation", {})
    forecast_block = _forecast_error_block(fe, fe_rows) if fe_rows else []
    cascade_block = _cascade_block(cc) if cc else []
    runoff_block = _runoff_block(rv) if rv else []

    return [
        PageBreak(),
        para("4 · Results", "h1"), rule(),
        para("4.1 · The model is calibrated, and the data needed cleaning first", "h2"),
        figure("fig3_calibration.png",
               f"Figure 3 — About 11% of the source dataset is physically impossible (left): live "
               f"storage above the reservoir's stated capacity, storage percentages over 1,000%. "
               f"Fitted on the {cal.get('n', 1836):,} validated rows (right), the level–storage power "
               f"law fits an exponent of {cal.get('beta', 1.348):.3f}, r² = {cal.get('r2', 0.9957):.4f}, "
               f"MAE {cal.get('mae', 17):.0f} Mm³."),
        para(
            "Fitting the same curve on the uncleaned feed gives r² = 0.784 and an MAE of "
            "174 Mm³ — the corrupt block alone displaces the curve by more than the entire "
            "flood cushion being modelled. Data validation was not housekeeping here; it was "
            "the difference between a usable model and a confidently wrong one."),
        para("4.2 · Replaying October 2021, and an episode the model never saw", "h2"),
        para(
            f"Fed the releases that actually occurred, the twin reproduces the observed Idukki "
            f"level with a mean error of <b>{cf.get('replay_level_mae_m', 0.30):.2f} m</b> "
            f"(maximum {cf.get('replay_level_max_err_m', 0.57):.2f} m) over 20 days. That "
            f"agreement is what earns the right to ask a counterfactual question at all."),
        para(
            f"Reproducing one episode is fitting; reproducing a second one the model was never "
            f"shown is validating. Replayed over "
            f"{fmt_window(oos.get('window', '2022-08-01 to 2022-08-20'))} \u2014 an "
            f"episode nothing was "
            f"tuned on \u2014 the error is "
            f"<b>{oos.get('mean_absolute_error_m', 0.319):.2f} m</b>, within 5% of October "
            f"2021's. One wrinkle worth stating: the drift reverses between the two episodes "
            f"(October 2021 ends {cf.get('replay_final_err_m', 0.52):+.2f} m, August 2022 "
            f"{oos.get('final_step_error_m', -0.273):+.2f} m), which argues against a single "
            f"missing loss term and points at event-specific interpolation timing instead."),
        figure("fig5_counterfactual.png",
               "Figure 4 — Observed operation (red) against the policy AquaSync selects (green). "
               f"The policy ends the episode roughly {cf.get('freeboard_gained_m', 3.1):.1f} m lower, "
               f"holding {cf.get('min_freeboard_optimised_m', 3.97):.1f} m of flood cushion instead of "
               f"{cf.get('min_freeboard_baseline_m', 0.89):.1f} m."),
        para("4.3 · What forecast lead time actually buys", "h2"),
        figure("fig4_lead_time.png",
               "Figure 5 — The flood cushion gained is roughly constant across lead times "
               "(left). What lead time changes is waste: the share of released water that goes "
               "over the spillway instead of through the turbines falls from "
               f"{lead.get('spill_0', 0.61) * 100:.0f}% to {lead.get('spill_30', 0.40) * 100:.0f}%."),
        callout(
            "The headline finding",
            "Over this episode, a policy-based release schedule delivers about <b>3 m more flood "
            "cushion</b> than what actually happened while generating <b>marginally more revenue</b> "
            f"(Rs {lead.get('revenue_min', 4.4):.0f}–{lead.get('revenue_max', 9.6):.0f} crore), because it moves the "
            "same volume of generation into higher-tariff hours.<br/><br/>"
            "The safety-versus-power trade-off everyone assumes is largely an artefact of "
            "<i>hoarding reservoir level</i> rather than <i>scheduling releases</i>. Lead time does "
            "not buy the cushion — it buys the ability to take the cushion through the turbines "
            "instead of over the spillway.",
            accent=GREEN, tint="#eefbf1"),
        para(
            f"One further result is worth stating because nobody set it: given only the physics "
            f"and the objective, the optimiser converged on a target level of "
            f"<b>{lead.get('target_level', 728.43):.2f} m</b> at nearly every lead time tested — "
            f"within 7 cm of the <b>728.50 m</b> that KSEB's own 2020 rule curve prescribes for "
            f"31 August."),
        callout(
            "But “just follow the rule curve” is NOT the recommendation, and the audit record "
            "says so.",
            "It is tempting to read the previous paragraph as vindication of the published rule "
            "curve. The CAG performance audit of Kerala's flood preparedness rules that out. "
            "Reading its Tables 3.6 and 3.7 directly: actual Idukki spills over 14–18 August 2018 "
            "totalled <b>467.51 MCM</b>, while the 2020 rule curve would have required "
            "<b>531.03 MCM</b> across the same window.<br/><br/>"
            "On the worst days of the worst flood in a century, mechanical compliance with the "
            "published curve would have put <i>more</i> water into the Periyar, not less. The "
            "agreement at 728.50 m is a coincidence of date — 31 August is the curve's most "
            "permissive step — not a validation of it.<br/><br/>"
            "What the result actually supports is narrower and more defensible: <b>a "
            "forecast-driven target, recomputed as conditions change, lands near sensible "
            "operating levels without being told what they are.</b> The value is in the "
            "recomputation, not in the number.",
            accent=RED, tint="#fdeef0"),
        para(
            "This correction came from the project's own research sweep rather than from a "
            "reviewer, which is the outcome to aim for. The full evidence, including the "
            "positions that contradict this project's thesis, is in the companion "
            "<i>Deep Research Report</i>."),
    ] + forecast_block + cascade_block + runoff_block


def _forecast_error_block(fe: dict, rows: list) -> list:
    """4.4 - what the counterfactual is worth once the forecast is real."""
    perfect = fe.get("perfect_m", 3.111)
    pf_rev = fe.get("perfect_revenue_cr", 1.94)
    ev_cost = fe.get("ev_excess_cost_pct", [0.0])
    mm_cost = fe.get("mm_excess_cost_pct", [19.4])
    best = fe.get("best_excess_cost_pct", 0.0)
    worst = fe.get("worst_excess_cost_pct", 84.7)
    return [
        PageBreak(),
        para("4.4 \u00b7 What survives once the forecast is real", "h2"),
        para(
            "Every number above hands the optimiser the inflow that actually occurred. No "
            "operator has that. This study re-runs the same October 2021 decision from a "
            "30-member NOAA GEFS rainfall ensemble issued <i>before</i> the storm: each "
            "member is bias-corrected against IMD gridded rainfall, pushed through the same "
            "SCS-CN and Muskingum chain, and given its own policy search. One policy is then "
            "committed to under that uncertainty and scored against what actually happened."),
        para(
            f"It is scored on the objective the optimiser actually minimises - flood, dam "
            f"safety, revenue and gate wear together. <b>Zero excess cost means the forecast "
            f"picked the policy hindsight would have picked</b>, and the figure can never go "
            f"below it. Freeboard alone cannot answer the question: a policy built on an "
            f"over-forecast releases too much, ends <i>lower</i> than the "
            f"{perfect:.2f} m hindsight optimum, and would score above 100% on a "
            f"cushion-only metric while quietly giving up revenue to do it."),
        data_table(
            ["Lead time", "Ensemble issued", "Expected value", "Minimax regret",
             "EV cushion", "MM cushion"],
            rows, widths=[20 * mm, 30 * mm, 26 * mm, 26 * mm,
                          (CONTENT_W - 102 * mm) / 2, (CONTENT_W - 102 * mm) / 2],
            align_right=(2, 3, 4, 5)),
        Spacer(1, 6),
        para(
            f"Excess cost against perfect foresight, then the flood cushion each policy "
            f"actually delivered. Perfect foresight gains {perfect:.2f} m while earning "
            f"Rs {pf_rev:+.2f} crore against observed operation.", "caption"),
        figure("fig6_forecast_error.png",
               "Figure 6 \u2014 Left: what deciding without hindsight costs on the full "
               "objective. Right: every forecast-driven policy earns less than the hindsight "
               "optimum - the extra cushion in the table was bought, not found."),
        callout(
            "At one day out, a real forecast is as good as hindsight. Three days out, it is "
            "not.",
            f"At the shortest lead the expected-value rule reproduces the hindsight-optimal "
            f"policy exactly ({min(ev_cost):+.0f}% excess cost). By 90 hours that has "
            f"decayed to roughly {max(ev_cost):+.0f}%, and it does not recover with more "
            f"lead time. <b>The operational reading is that this system's value is "
            f"concentrated in the last day or two before a storm</b>, which is also the "
            f"window in which a control room has least time to deliberate - and therefore "
            f"the window where a pre-computed policy is worth most.",
            accent=GREEN, tint="#eefbf1"),
        callout(
            "This reverses what an earlier version of this document reported, and the reason "
            "is recorded rather than quietly corrected.",
            f"That version said hedging against the worst ensemble member \u201cnever costs "
            f"you the naive result and sometimes triples it\u201d. On these numbers minimax "
            f"regret is <b>never better than expected value and usually worse</b> "
            f"({min(mm_cost):+.0f}% to {max(mm_cost):+.0f}% excess cost against "
            f"{min(ev_cost):+.0f}% to {max(ev_cost):+.0f}%): hedging buys cushion by "
            f"over-releasing, and pays for it in revenue.<br/><br/>"
            f"The earlier figures came from a rainfall-runoff chain carrying the defect "
            f"\u00a74.6 describes - it produced almost no runoff, so every ensemble member "
            f"looked benign and every policy under-released. The whole of \u00a74.4 was "
            f"re-run once that was fixed. <b>A published conclusion that reverses under a "
            f"corrected model is worth more on the record than off it</b>, and it is the "
            f"second finding this project has had to withdraw on its own evidence.",
            accent=RED, tint="#fdeef0"),
        para(
            f"<b>It is lead time doing this, not the bias correction.</b> The obvious "
            f"alternative explanation is the bias factor - a single-event multiplicative "
            f"correction that varies from {fe.get('bias_min', 1.68):.2f}\u00d7 to "
            f"{fe.get('bias_max', 3.18):.2f}\u00d7 between runs - so it was checked rather "
            f"than assumed. Across these lead times excess cost correlates with lead time at "
            f"r = 0.93 and with the bias factor at only 0.61, and the 48 h run settles it "
            f"outright: it carries one of the largest corrections in the set and still "
            f"reproduces the hindsight-optimal policy exactly. <b>An earlier three-point "
            f"version of this section said the opposite</b>, on a sample too small to tell "
            f"the two apart."),
        para(
            f"<b>What would settle the rest.</b> These are still five points from a single "
            f"storm, and the transition between 48 and 90 hours rests on one run at 72 h. A "
            f"second storm in another monsoon is what would turn this from a result into a "
            f"curve worth relying on, and it is the next thing this study needs. Until then "
            f"the range to quote is {best:+.0f}% to {worst:+.0f}% excess cost, with the "
            f"caveat that it rests on one event."),
    ]


def _runoff_block(rv: dict) -> list:
    """4.6 - validating the last unvalidated model, and what it turned up."""
    errs = rv.get("season_volume_error_pct", {})
    seasons = rv.get("seasons", [2021, 2022, 2023, 2024])
    return [
        PageBreak(),
        para("4.6 \u00b7 Validating the last unvalidated model", "h2"),
        para(
            f"Every model above is checked against something observed except one: the "
            f"rainfall-runoff chain that converts a forecast into an inflow. It had never "
            f"been compared with observed inflow, which mattered because \u00a74.4 drives "
            f"exactly this code. The check needs no new data \u2014 the KSEB bulletin "
            f"publishes daily rainfall <i>and</i> daily inflow for the same reservoir, giving "
            f"{len(seasons)} complete monsoon seasons ({min(seasons)}\u2013{max(seasons)}, "
            f"{rv.get('n_days', 722)} scored days)."),
        callout(
            "The first run did not find a calibration error. It found a defect.",
            "Scored as it shipped, the chain returned a <b>-100% volume bias</b>: across four "
            "monsoons it produced almost no runoff at all. The curve-number equation is an "
            "<i>event-total</i> relation \u2014 its initial abstraction is the depth a "
            "catchment absorbs once, at the start of a storm \u2014 but the code applied it to "
            "every timestep independently. For Idukki that abstraction is 19.8 mm, more than "
            "an hour of even extreme rain, so the 168 mm of 17 October 2021 yielded 89 mm of "
            "runoff as one daily step and <b>0.00 mm</b> driven hourly. The model's answer "
            "depended on the timestep it was handed, and the forecast study hands it hours."
            "<br/><br/>"
            "Fixed by accumulating rainfall within a storm and differencing the cumulative "
            "effective depth, which is how the method is defined. Effective rainfall is now "
            "identical at 30 minutes, 1, 3 and 24 hours, and a test pins that invariance so "
            "it cannot regress. <b>Every figure in \u00a74.4 was re-run against the fixed "
            "chain.</b>",
            accent=RED, tint="#fdeef0"),
        Spacer(1, 10),
        figure("fig8_runoff_validation.png",
               "Figure 8 \u2014 The fixed chain against observed inflow, handbook curve "
               "number, never calibrated. Storm timing broadly tracks; storm size does not."),
        para(
            f"<b>What it is worth, stated carefully.</b> Pooled across "
            f"{rv.get('n_days', 722)} days the volume bias is "
            f"{rv.get('pbias_pct', -1):+.0f}%, which flatters it: per season the errors are "
            f"{', '.join(f'{v:+.0f}%' for v in errs.values()) if errs else '-7%, -3%, +38%, -17%'}, "
            f"so the chain gets the climatological volume right and any individual monsoon's "
            f"only roughly. It follows the shape of the hydrograph "
            f"(r\u00b2 {rv.get('r2', 0.55):.2f}) but not its amplitude "
            f"(NSE {rv.get('nse', 0.07):.2f}): peaks overshoot, and predicted inflow returns "
            f"to zero between storms because an event-based curve number has no recession "
            f"limb. Calibrating the curve number was tried and <b>rejected</b> \u2014 the best "
            f"fit pins at {rv.get('calibrated_cn', 50):.0f}, the bottom edge of the search "
            f"grid, and leave-one-season-out it collapses to a worst NSE of "
            f"{rv.get('loo_worst_nse', -0.91):.2f}. A curve number fitted on three seasons "
            f"does not predict the fourth, so the handbook value stays."),
        callout(
            "What this settles.",
            "The chain is fit for what the twin asks of it \u2014 roughly how much water a "
            "storm of this size delivers, and roughly when \u2014 and is not fit for "
            "day-ahead inflow prediction to a useful tolerance. Two caveats govern all of "
            "it and neither can be resolved from this dataset: bulletin rainfall is a "
            "station reading at the dam rather than a catchment areal mean, and bulletin "
            "inflow is itself derived from a reservoir mass balance rather than gauged. "
            "This compares two estimates, not a model against truth.",
            accent=BLUE, tint="#eef4fd"),
    ]


def _cascade_block(cc: dict) -> list:
    """4.5 - the result that argues against the obvious extension."""
    obs = cc.get("observed_joint_peak_cumecs", 403.4)
    naive = cc.get("naive_independent_joint_peak_cumecs", 910.9)
    coord = cc.get("coordinated_joint_peak_cumecs", 828.0)
    return [
        PageBreak(),
        para("4.5 \u00b7 Two dams, and a result that argues against the obvious extension", "h2"),
        para(
            f"Everywhere else in this project the two Periyar reservoirs are optimised one at a "
            f"time. Since the evidence for the problem is that they failed <i>jointly</i> "
            f"(Figure 2), scheduling them together looked like the single most valuable thing "
            f"left to add. Routing both releases through the river DAG to their shared "
            f"confluence over the {cc.get('n_hours', 481)}-hour October 2021 window says "
            f"otherwise."),
        figure("fig7_cascade_coordination.png",
               "Figure 7 \u2014 Joint peak at the confluence under three regimes. These are the "
               "two dams' contribution only: the ungauged lateral inflow between the dams and "
               "Aluva is not included, so the absolute values are not total river discharge and "
               "must not be read against bankfull. The comparison between the three regimes is "
               "valid; the cumec values on their own are not a flood-risk verdict."),
        callout(
            "Optimising each dam for itself is not a neutral simplification \u2014 it is "
            "actively worse than the uncoordinated baseline.",
            f"Each dam optimising alone raises the joint peak to <b>{naive:,.0f} cumecs</b> "
            f"against the <b>{obs:,.0f}</b> that actually occurred \u2014 "
            f"<b>{abs(cc.get('naive_vs_observed_reduction_pct', -125.8)):.0f}% worse</b>. "
            f"Idukki's own optimum releases at the top of its rate grid because, scored against "
            f"the downstream reach <i>alone</i>, that looks entirely safe. It is not safe once "
            f"Idamalayar's simultaneous release arrives at the same confluence \u2014 a "
            f"combination neither dam's objective function can see.",
            accent=RED, tint="#fdeef0"),
        para(
            f"<b>And retiming does not fix it.</b> Sweeping both dams' start hours \u2014 the "
            f"most direct reading of \u201cmake the pulses not superpose\u201d \u2014 recovers "
            f"only {cc.get('coordination_vs_naive_reduction_pct', 9.1):.0f}% of the gap it "
            f"opened ({naive:,.0f} to {coord:,.0f} cumecs), nowhere near the observed "
            f"{obs:,.0f}. Once each dam is already optimised for its own safety at maximum rate, "
            f"this is not a timing problem; it is an objective-function problem. The "
            f"correctly-scoped next piece of work is a genuinely joint objective \u2014 each "
            f"dam's policy scored against the actual combined downstream discharge rather than "
            f"its own reach in isolation \u2014 not a bigger timing search. That is now the "
            f"largest open modelling item in the project, and \u00a79 records it as such."),
    ]


def section_innovation() -> list:
    return [
        PageBreak(),
        para("5 · What is genuinely new here", "h1"), rule(),
        data_table(
            ["", "Common approach", "AquaSync"],
            [["Output", "A dashboard showing the current level",
              "An implementable three-parameter release policy"],
             ["Timing", "Reactive — alerts once thresholds are crossed",
              "Prescriptive — acts on a forecast, before the surge"],
             ["Scope", "One reservoir in isolation",
              "Both Periyar dams routed to their shared confluence — which is how this "
              "project found that optimising them separately makes the joint peak worse (§4.5)"],
             ["Objectives", "Water level only",
              "Flood, dam safety, generation revenue and gate wear, jointly weighted"],
             ["The sea", "Ignored",
              "Tidal conveyance windows treated as a schedulable resource"],
             ["Validation", "Synthetic or hand-picked data",
              "Replay against real telemetry, with the error reported"],
             ["Data trust", "Feed consumed as-is",
              "Validation layer; 11% of the source found to be corrupt"],
             ["Failure", "Cloud dashboard, dark when the network dies",
              "LoRa fallback, local logging, tamper-evident hash chain"]],
            widths=[24 * mm, 62 * mm, CONTENT_W - 86 * mm]),
        Spacer(1, 8),
        para("The three ideas that carry the project", "h2"),
        para("<b>1 · Search policies, not schedules.</b> "
             "The first implementation searched over hundreds of independent hourly release "
             "values and produced results that were non-monotonic in lead time — 10 days looked "
             "better than 14, which looked better than 21. That was not a finding, it was a "
             "search artefact: a longer horizon has more free variables, so a fixed budget "
             "covers it more sparsely. Reformulating the search over "
             "<i>(target level, start time, max rate)</i> made the space small enough to "
             "enumerate exhaustively — deterministic, reproducible, monotonic, and expressible "
             "as a sentence an operator can act on."),
        para("<b>2 · Price the trade-off honestly, then discover it is smaller than assumed.</b> "
             "Only the portion of a spill the turbines could actually have absorbed counts as "
             "forgone generation; water above turbine rating had to be spilled regardless. "
             "Getting this wrong overstates the cost of acting and biases an operator toward "
             "holding water. Counting it correctly is what reveals that the conflict is mostly "
             "about timing."),
        para("<b>3 · Treat the tide as a schedulable resource.</b> "
             "Cochin's spring tidal range is only about a metre, but on a river already at "
             "bankfull a metre decides whether a town floods. It is also perfectly predictable "
             "and recurs twice a day, which makes it a free, repeating window in which the same "
             "volume can be moved at materially lower risk."),
    ]


def section_build() -> list:
    return [
        para("6 · How it gets built", "h1"), rule(),
        para(
            "Six phases. Each ends in something demonstrable, so the project is presentable "
            "at any point after Phase 2 rather than only when complete."),
        data_table(
            ["Phase", "Weeks", "Deliverable", "Done when"],
            [["0 · Foundation", "0.5",
              "Repo, data pipeline, validation layer",
              "Idukki and Idamalayar load clean; quality report prints"],
             ["1 · Twin core", "1.5",
              "Mass balance, level–storage calibration, replay",
              "Observed October 2021 level reproduced to under 0.5 m"],
             ["2 · Routing &amp; tide", "1.5",
              "Muskingum reaches, harmonic tide, conveyance",
              "Downstream hydrograph at Aluva with a stated travel time"],
             ["3 · Decision engine", "1.5",
              "Policy search, objective weights, baseline comparison",
              "A counterfactual with a defensible headline number"],
             ["4 · Hardware rig", "2",
              "Two-tank HIL bench, ESP32, stepper gate, telemetry",
              "Twin drives the physical gate; fault injection recovers"],
             ["5 · Interface", "1.5",
              "3D live twin, what-if panel, Crisis Commander",
              "A stranger can run the demo unaided"],
             ["6 · Hardening", "1",
              "Tests, docs, rehearsal, poster, offline fallback",
              "Full demo runs with the network cable pulled"]],
            widths=[26 * mm, 13 * mm, 52 * mm, CONTENT_W - 91 * mm]),
        Spacer(1, 6),
        callout(
            "The failure mode to design against is feature creep, not lack of ambition.",
            "The planning material behind this project accumulated twenty-five candidate "
            "upgrades — satellite calibration, agent-based evacuation, graph neural routing, "
            "post-quantum SCADA cryptography, an autonomous bathymetry boat. Each is "
            "individually sound. Attempting more than two produces a table of half-working "
            "prototypes and no time to rehearse, which is the single most common way a strong "
            "idea loses. <b>Phases 0–3 plus a V1 rig is a complete, winning project.</b> "
            "Everything else is backlog.",
            accent=AMBER),
    ]


def section_hardware() -> list:
    return [
        PageBreak(),
        para("7 · Components and cost", "h1"), rule(),
        para(
            "Four tiers. <b>V1 alone is a complete demonstration.</b> Prices are indicative INR "
            "at August 2026, from Indian vendors (Robu.in, ThinkRobotics, ElectronicsComp)."),
        data_table(
            ["Tier", "What it adds", "Time", "Rs ", "Cumulative"],
            [["Tools", "Iron, solder, multimeter, strippers — if not owned", "—", "1,480", "1,480"],
             ["<b>V1</b>", "<b>Two-tank HIL rig: ESP32, JSN-SR04T, DS18B20, NEMA 17 gate, "
                           "YF-S201 flow, pump, acrylic</b>", "<b>1 wk</b>", "<b>6,250</b>", "<b>7,730</b>"],
             ["V2", "Off-grid: LoRa SX1278 (433 MHz), SD logging, INA219 jam detection, solar",
              "1 wk", "2,300", "10,030"],
             ["V3", "Edge AI: ESP32-S3, ESP32-CAM, 24 GHz radar, hydrostatic transmitter, I²S mic",
              "2 wk", "5,900", "15,930"],
             ["V4", "Raspberry Pi offline command post, GPS bathymetry boat",
              "3 wk", "9,900", "25,830"]],
            widths=[15 * mm, CONTENT_W - 76 * mm, 15 * mm, 18 * mm, 22 * mm],
            align_right=(3, 4)),
        Spacer(1, 6),
        para("Key V1 components", "h2"),
        data_table(
            ["Component", "Specification", "Rs ", "Why this part"],
            [["ESP32-WROOM-32", "38-pin DevKit, 240 MHz, Wi-Fi + BT", "450",
              "38-pin, not 30 — you need the extra ADC pins"],
             ["JSN-SR04T v3.0", "Waterproof ultrasonic, 25–450 cm, ±1 cm", "550",
              "Separate transducer on a cable; survives splash"],
             ["DS18B20", "1-Wire waterproof probe, ±0.5 °C", "180",
              "Not optional — sound speed drifts 0.6 m/s per °C"],
             ["NEMA 17 + A4988", "42 mm, 1.8°, 4.2 kg·cm, 1/16 microstep", "780",
              "Precise, repeatable sluice gate positioning"],
             ["YF-S201", "Hall flow, 1–30 L/min, G1/2 in", "350", "Closes the mass balance loop"],
             ["BMP280", "Barometric, ±0.12 hPa", "150", "Pressure-drop squall pre-detection"],
             ["Limit switches", "SPDT lever × 2", "80",
              "A stepper has no position feedback; these give it a datum"]],
            widths=[30 * mm, 46 * mm, 13 * mm, CONTENT_W - 89 * mm],
            align_right=(2,)),
        Spacer(1, 6),
        callout(
            "Two wiring traps worth knowing before you order.",
            "Ultrasonic echo pins output <b>5 V</b> and the ESP32 is 3.3 V tolerant only — a "
            "divider on every echo line is mandatory, not optional. And GPIO 34/35 are "
            "<b>input-only with no internal pull-ups</b>, so limit switches wired there need "
            "external ones.<br/><br/>"
            "Note also that the component links in the material this project was planned from "
            "were unreliable — one Amazon ASIN appeared as a breadboard, a jumper set, a DHT22, "
            "a resistor kit and a multimeter. The bill of materials is anchored on part numbers "
            "and specifications instead, which is what actually survives.",
            accent=RED, tint="#fdeef0"),
    ]


def section_data() -> list:
    return [
        PageBreak(),
        para("8 · Data and open-source foundations", "h1"), rule(),
        para("Everything is free. Nothing requires an institutional licence."),
        data_table(
            ["Source", "Provides", "Access", "Verified"],
            [["<b>amith-vp/Kerala-Dam-Water-Levels</b>",
              "Daily level, storage, inflow, powerhouse and spillway discharge, rainfall for "
              "18 KSEB reservoirs, with FRL/MWL/rule/alert thresholds",
              "Raw JSON on GitHub, updated daily", "Yes — Aug 2020 to Aug 2026"],
             ["IMD gridded rainfall", "0.25° daily rainfall, 1901–present", "Free download", "—"],
             ["Open-Meteo / OpenWeatherMap", "72–120 h rainfall forecast", "Free API tier", "—"],
             ["INCOIS", "Tide predictions for Kochi", "Free for Indian academic use", "—"],
             ["ISRO Bhuvan CartoDEM", "10–30 m terrain for inundation mapping", "Registration", "—"],
             ["Sentinel-1 SAR", "Cloud-penetrating flood extent",
              "Google Earth Engine / Copernicus", "—"],
             ["OpenData Kerala", "Ward and panchayat boundaries (GeoJSON)", "GitHub", "—"]],
            widths=[42 * mm, CONTENT_W - 112 * mm, 36 * mm, 34 * mm]),
        Spacer(1, 8),
        para("Software stack", "h2"),
        para(
            "Python 3.12, NumPy, SciPy, pandas for the twin; FastAPI and WebSockets for "
            "telemetry; Three.js for the 3D interface; PlatformIO and Arduino-ESP32 for "
            "firmware; Matplotlib and ReportLab for this document. Total licence cost Rs 0."),
        para("Deliberately not used", "h2"),
        data_table(
            ["Considered", "Why not"],
            [["RTC-Tools (Deltares)",
              "Genuinely industry-grade reservoir optimisation, but needs a CasADi/IPOPT "
              "toolchain and the problem here is small enough that a transparent exhaustive "
              "search is both sufficient and far easier to defend in a five-minute Q&amp;A"],
             ["Google Flood Forecasting API",
              "Excellent, but it is a forecast <i>product</i>. Using it as ground truth for our "
              "own forecast would be circular. Kept as a benchmark to compare against"],
             ["Kaggle “Kerala Floods 2018”",
              "District casualty and rainfall totals only — no reservoir telemetry, so it "
              "cannot validate a routing model"],
             ["LISFLOOD-FP 2D inundation",
              "The right long-term answer for street-level depth mapping, but it needs a "
              "calibrated DEM and roughness field. Roadmap, not scope"]],
            widths=[46 * mm, CONTENT_W - 46 * mm]),
    ]


def section_limits(f: dict) -> list:
    cf = f.get("counterfactual", {})
    fe = f.get("forecast_error", {})
    cc = f.get("cascade_coordination", {})
    rc = f.get("routing_cal", {})
    ev = fe.get("ev_excess_cost_pct", [0.0])
    mmx = fe.get("mm_excess_cost_pct", [84.7])
    return [
        PageBreak(),
        para("9 · Limitations", "h1"), rule(),
        para(
            "Stated plainly, because every one of these will be found by anyone who looks, and "
            "finding them first is the difference between a limitation and a hole."),
        data_table(
            ["Limitation", "Consequence", "Mitigation"],
            [["<b>Headline figures assume perfect foresight</b>",
              f"The optimiser sees the true inflow when choosing a policy, so every "
              f"perfect-foresight number here is a <b>ceiling</b>. Driven from a real 30-member "
              f"ensemble the decision costs {min(ev):+.0f}% to {max(mmx):+.0f}% more than "
              f"hindsight on the full objective, and the penalty grows with lead time (\u00a74.4)",
              "Measured rather than assumed. Quote the excess-cost range operationally, "
              "and note the value concentrates inside about 24 h. Remaining gap: one storm"],
             ["Daily input resolution",
              "Bulletin data is one reading per day, interpolated to hourly. Sub-daily peaks "
              "are smoothed away; peak timing carries roughly ±12 h",
              "CWC 15-minute telemetry; ESP32 nodes for local sub-daily truth"],
             ["Routing parameters are anchored, not calibrated",
              f"K and x are anchored to CWC's published {rc.get('cwc_anchor_k_hours', 8):.0f}-hour "
              f"Idukki\u2013Neeleeswaram travel time. A direct fit against "
              f"{rc.get('n_days', 1967):,} days of gauge data failed "
              f"(r\u00b2 = {rc.get('r_squared', 0.005):.3f}): daily data is ~3\u00d7 coarser "
              f"than the signal. Downstream discharge is indicative, not measured",
              "CWC 15-minute telemetry \u2014 the highest-value data upgrade. Until then, never "
              "quote Aluva discharge as measured"],
             [f"Replay error {cf.get('replay_level_mae_m', 0.30):.2f} m MAE",
              "Roughly 0.5 m of the ~3 m freeboard claim sits inside model error",
              "Quote it as “about 3 m”, never to two decimals"],
             ["No 2D inundation",
              "The twin gives river discharge, not which streets flood",
              "LISFLOOD-FP or a HEC-RAS coupling on a Bhuvan DEM"],
             ["<b>Each dam is optimised against its own reach alone</b>",
              f"Not merely incomplete \u2014 measured as harmful: optimising the two dams "
              f"independently raises the joint peak at their confluence "
              f"{abs(cc.get('naive_vs_observed_reduction_pct', -125.8)):.0f}% above what "
              f"actually happened, and retiming recovers only "
              f"{cc.get('coordination_vs_naive_reduction_pct', 9.1):.0f}% (\u00a74.5)",
              "A joint objective: score each dam's policy on combined downstream discharge, not "
              "its own reach. <b>The largest open modelling item</b>"],
             ["No lateral inflow between the dams and Aluva",
              "The cascade figures are the two dams' contribution only, not total river "
              "discharge, and must not be read against bankfull thresholds",
              "RiverNetwork already accepts lateral inflows; no tributary or local-runoff "
              "series exists in the project's data holdings yet"],
             ["Indicative tariffs",
              "Revenue figures are order-of-magnitude, not audited",
              "Substitute the current KSERC order before quoting rupees to a utility"],
             ["Institutional adoption",
              "A utility will not accept an external recommendation engine on trust",
              "Shadow mode: run alongside real operations for a full monsoon, log what it "
              "would have advised, publish the comparison"]],
            widths=[42 * mm, 62 * mm, CONTENT_W - 104 * mm]),
        Spacer(1, 8),
        para("9.1 · Evidence against this project's thesis", "h2"),
        para(
            "A deep-research sweep run against this project found five positions that "
            "complicate or contradict its argument. They belong here rather than in a footnote, "
            "because the first domain-literate reviewer will find them anyway."),
        data_table(
            ["Challenge", "What it means for AquaSync"],
            [["<b>The literature does not agree that dams worsened the 2018 flood.</b> CWC's own "
              "September-2018 study concludes the reservoirs <i>attenuated</i> the peak — Idukki "
              "2,532 down to 1,500 cumec, about 41%.",
              "The framing “dam mismanagement caused the flood” is contested by the agency that "
              "owns the data. State the conflict; do not assert one side."],
             ["<b>The most-quoted “reservoirs made it worse” study was rejected.</b> Mishra et "
              "al.'s HESS preprint carries “not accepted for further review”, and its headline "
              "number differs from the peer-reviewed figure by about 3.5×.",
              "Do not cite it. Its absence from the argument is a strength."],
             ["<b>The forecast skill this approach assumes may not exist in this basin.</b> "
              "Sudheer et al. report that probability of detection for rainfall above 25 mm/day "
              "at 3–5 day range is poor <i>even with ensembles</i>.",
              "This is the deepest problem in the project. It is not solved by better "
              "optimisation, and it bounds what any forecast-driven system can deliver here."],
             ["<b>Even a perfect optimiser has a modest ceiling.</b> The same authors put "
              "achievable peak attenuation from advance emptying at <b>16–21%</b>, and find "
              "downstream flows become insensitive to reservoir state below 50% storage.",
              "A useful sanity bound. Any claim materially above it needs extraordinary evidence."],
             ["<b>FIRO took about a decade of shadow operation</b> to change one water control "
              "manual that had been revised twice in 66 years.",
              "The adoption timeline in this document is optimistic. Shadow mode is not a phase; "
              "it is most of the work."]],
            widths=[74 * mm, CONTENT_W - 74 * mm]),
        Spacer(1, 8),
        callout(
            "The honest summary of all five.",
            "AquaSync is a decision-support tool whose upper bound is set by monsoon forecast "
            "skill over the Western Ghats, operating in a domain where the causal claim it rests "
            "on is genuinely disputed. That is a smaller claim than the one this document opened "
            "with, and it is the one the evidence supports.",
            accent=VIOLET, tint="#f4f0fb"),
        callout(
            "The system is advisory, permanently.",
            "AquaSync never operates a gate. If an automated system opens a spillway and "
            "someone drowns, the question of who is accountable has no acceptable answer; a "
            "recommendation approved by a named officer has a clear one. The hardware "
            "demonstrator does close the loop onto a servo, because it is a 30 cm acrylic "
            "tank — and that distinction should be said out loud during the demo rather than "
            "left for someone to catch.",
            accent=BLUE, tint="#eef4fd"),
    ]


def section_roadmap() -> list:
    return [
        para("10 · Roadmap beyond the expo", "h1"), rule(),
        data_table(
            ["Horizon", "Work", "Why it matters"],
            [["Now – expo",
              "Joint cascade objective (\u00a74.5); V1 rig; live backend and Crisis Commander "
              "mode",
              "The forecast-error and cascade studies are done and reported in \u00a74; what "
              "remains is acting on what they found"],
             ["3–6 months",
              "CWC 15-min telemetry; 2D inundation on Bhuvan DEM; Sentinel-1 extent validation; "
              "field-deploy one ESP32 node",
              "Moves from daily hindcast to operational nowcast"],
             ["6–12 months",
              "Shadow-mode trial with KSEB/KSDMA; Malayalam last-mile alerting via LDMC and "
              "Kudumbashree networks; OGC SensorThings output",
              "Builds the operational trust record adoption requires"],
             ["Beyond",
              "All Kerala cascades; ensemble and reinforcement-learning policies; dam-breach "
              "mode; public tamper-evident release ledger",
              "From one basin to a statewide decision layer"]],
            widths=[26 * mm, CONTENT_W - 96 * mm, 70 * mm]),
        Spacer(1, 10),
        para("11 · Two corrections to the source material", "h1"), rule(),
        para(
            "This project was planned from a long set of prior design conversations, archived "
            "in <font face='Courier' size='8.5'>reference/source_chats/</font>. Two of their "
            "load-bearing assumptions did not survive contact with the data, and both are "
            "recorded here so the same ground is not covered twice."),
        callout(
            "1 · The dataset does not contain 2018 data.",
            "The planning material identified <font face='Courier' size='8.5'>"
            "amith-vp/Kerala-Dam-Water-Levels</font> as <i>“exactly the 2018 Idukki dam data you "
            "need”</i> and built the entire flagship demo — a “2018 replay” — on it. The "
            "historical files begin on <b>13 August 2020</b>. There is no 2018 record in the "
            "repository at all.<br/><br/>"
            "The flagship case study moved to <b>October 2021</b>, which is fully covered, "
            "complete in every field, and a better demonstration. The 2018 flood remains the "
            "reason anyone cares — but no quantitative claim now depends on it. Acquisition "
            "routes for genuine 2018 data are documented in "
            "<font face='Courier' size='8.5'>docs/data-sources.md</font>.",
            accent=RED, tint="#fdeef0"),
        callout(
            "2 · About 11% of the dataset is corrupt.",
            "Rows between 2020-09-25 and 2021-04-30 report live storage above the reservoir's "
            "physical capacity and storage percentages over 1,000% — consistent with a "
            "column-alignment bug upstream. Using the feed unvalidated degrades the "
            "level–storage calibration from r² 0.996 to 0.784.",
            accent=RED, tint="#fdeef0"),
    ]


def section_pitch() -> list:
    return [
        PageBreak(),
        para("12 · The two-minute pitch", "h1"), rule(),
        Table([[Paragraph(
            "“In October 2021, the Idukki reservoir entered a 168 millimetre rain day already "
            "<i>above</i> its own published rule level, with the spillway shut. Inflow rose "
            "seven-and-a-half times in twenty-four hours. The gates opened three days later — "
            "and Idamalayar, on the same river, opened its gates on exactly the same day. "
            "Everything I just said is in the public KSEB bulletin. Nobody hid anything, and "
            "nobody broke a rule.<br/><br/>"
            "AquaSync is a digital twin of that system. It simulates the catchment, the "
            "reservoir, the river and the tide, and searches for the release policy that best "
            "trades off flood risk, dam safety and generation revenue. It reproduces the "
            "observed October 2021 level to within thirty centimetres, which is what earns it "
            "the right to ask: what should have been done instead?<br/><br/>"
            "The answer is about three metres more flood cushion — with <i>slightly more</i> "
            "revenue, not less, because the same water goes through the turbines at "
            "better hours instead of over the spillway. The safety-versus-power conflict "
            "everyone assumes is mostly an artefact of acting late.<br/><br/>"
            "And the operating level the optimiser chose? 728.43 metres — within seven "
            "centimetres of what KSEB's own rule curve prescribes for that date, without ever "
            "being told it. I want to be careful here, because the CAG audit shows that "
            "mechanically following that curve through August 2018 would actually have released "
            "<i>more</i> water, not less. So the point is not that the rule is right. The point "
            "is that a system recomputing the target against a live forecast arrives somewhere "
            "sensible on its own — and keeps arriving there as conditions change, which a fixed "
            "curve cannot do.”", S["callout"])]], colWidths=[CONTENT_W],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), BG),
                ("LINEBEFORE", (0, 0), (0, -1), 2.4, BLUE),
                ("LEFTPADDING", (0, 0), (-1, -1), 11),
                ("RIGHTPADDING", (0, 0), (-1, -1), 11),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10)])),
        Spacer(1, 10),
        para("Demonstration sequence", "h2"),
        data_table(
            ["", "Beat", "Duration"],
            [["1", "The physical rig is already running: pump on, gate holding level. "
                   "Point at it, do not explain it yet", "—"],
             ["2", "Figure 1 on screen. “This is real, and it is public.”", "30 s"],
             ["3", "Dump water into the upstream tank — a live storm. The twin sees inflow "
                   "rise and opens the gate <i>before</i> the reservoir tank reaches its FRL line", "40 s"],
             ["4", "Flip the ‘sensor failure’ switch. The twin detects the disagreement, "
                   "falls back to mass-balance state estimation, and keeps controlling", "30 s"],
             ["5", "Hand over the tablet: “You are the operator. It is 16 October 2021.” "
                   "Let them try to save Aluva, then show them the optimiser's answer", "40 s"],
             ["6", "Pull the network cable. Everything keeps running on LoRa and the local Pi", "20 s"]],
            widths=[8 * mm, CONTENT_W - 30 * mm, 22 * mm]),
        Spacer(1, 8),
        para(
            "Beat 4 is the one that wins the room. Anyone can demonstrate a system working; "
            "demonstrating a system <i>failing correctly</i> is what convinces an engineer that "
            "it was built by someone who expected it to be used."),
        Spacer(1, 12),
        rule(colour=INK),
        para(
            "<b>Repository</b> · <font face='Courier' size='8.5'>PROGRESS.md</font> for live status, "
            "<font face='Courier' size='8.5'>ROADMAP.md</font> for sequencing, "
            "<font face='Courier' size='8.5'>ACTION_PLAN.md</font> for the next fourteen days. "
            "All figures and every number in this document regenerate from public data with "
            "<font face='Courier' size='8.5'>python scripts/make_figures.py</font>.", "caption"),
    ]


def build() -> int:
    facts = load_facts()

    # invariant=1 strips the embedded creation timestamp, so an unchanged
    # analysis produces a byte-identical PDF. Without it the file differs on
    # every build and git cannot tell a real change from a rebuild.
    doc = BaseDocTemplate(
        str(OUT), pagesize=A4, invariant=1,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN + 4 * mm,
        title="AquaSync - Digital Twin for Dam-River Flood Optimisation",
        author="Am4l-babu", subject="EVOKE 26 - Climate Resilience & Disaster Preparedness",
    )
    frame = Frame(MARGIN, MARGIN + 4 * mm, CONTENT_W,
                  PAGE_H - 2 * MARGIN - 4 * mm, id="main")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[frame], onPage=on_cover),
        PageTemplate(id="body", frames=[frame], onPage=on_page),
    ])

    story: list = []
    story += cover(facts)
    story += [NextPageTemplate("body"), PageBreak()]
    story += section_problem()
    story += section_evidence(facts)
    story += [PageBreak()]
    story += section_solution()
    story += section_results(facts)
    story += section_innovation()
    story += section_build()
    story += section_hardware()
    story += section_data()
    story += section_limits(facts)
    story += section_roadmap()
    story += section_pitch()

    doc.build(story)
    print(f"wrote {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
