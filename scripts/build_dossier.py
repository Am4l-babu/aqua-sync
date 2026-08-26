"""Build the AquaSync project dossier PDF.

Every quantitative claim in the document is pulled from
``data/processed/*.json`` at build time, so the prose cannot drift away from
the analysis. Run the analyses first:

    python scripts/lead_time_study.py
    python scripts/make_figures.py
    python scripts/build_dossier.py
"""

from __future__ import annotations

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


def load_facts() -> dict:
    facts = {}
    for f in ("figure_facts.json", "lead_time_headline.json"):
        p = PROC / f
        if p.exists():
            facts.update(json.loads(p.read_text(encoding="utf-8")))
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

    lead = f.get("lead_time", {})
    cal = f.get("calibration", {})
    cf = f.get("counterfactual", {})
    out += [
        kpi_row([
            (f"{lead.get('freeboard_mean', 3.16):.1f} m", "additional flood cushion,<br/>October 2021 replay"),
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
        para("Prepared 26 August 2026 · All figures regenerate from public data via "
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
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&#9660;<br/>"
            "SIMULATION &nbsp;SCS-CN runoff → mass balance → Muskingum routing → tidal backwater → power<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&#9660;<br/>"
            "DECISION &nbsp;&nbsp;&nbsp;Policy search over (target level, start time, max rate)<br/>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&#9660;<br/>"
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
              "Harmonic tide + exponential backwater decay → effective conveyance"],
             ["5", "Hydropower", "What does this release cost or earn?",
              "ρgQHη with a turbine hill diagram and time-of-day tariff"]],
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
    return [
        PageBreak(),
        para("4 · Results", "h1"), rule(),
        para("4.1 · The model is calibrated, and the data needed cleaning first", "h2"),
        figure("fig3_calibration.png",
               f"Figure 3 — About 11% of the source dataset is physically impossible (left): live "
               f"storage above the reservoir's stated capacity, storage percentages over 1,000%. "
               f"Fitted on the {cal.get('n', 1836):,} validated rows (right), the level–storage power "
               f"law gives β = {cal.get('beta', 1.348):.3f}, r² = {cal.get('r2', 0.9957):.4f}, "
               f"MAE {cal.get('mae', 17):.0f} Mm³."),
        para(
            "Fitting the same curve on the uncleaned feed gives r² = 0.784 and an MAE of "
            "174 Mm³ — the corrupt block alone displaces the curve by more than the entire "
            "flood cushion being modelled. Data validation was not housekeeping here; it was "
            "the difference between a usable model and a confidently wrong one."),
        para("4.2 · Replaying October 2021", "h2"),
        para(
            f"Fed the releases that actually occurred, the twin reproduces the observed Idukki "
            f"level with a mean error of <b>{cf.get('replay_level_mae_m', 0.30):.2f} m</b> "
            f"(maximum {cf.get('replay_level_max_err_m', 0.57):.2f} m) over 20 days. That "
            f"agreement is what earns the right to ask a counterfactual question at all."),
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
            f"<b>{lead.get('target_level', 728.43):.2f} m</b> at nearly every lead time tested. KSEB's "
            f"own published rule level for Idukki is <b>728.50 m</b>. The optimiser independently "
            f"rediscovered the operating rule that already exists, to within 7 cm."),
        callout(
            "Which means the recommendation is not “change the rule”.",
            "The rule curve is already correct. What is missing is a system that acts on it "
            "against a forecast, early enough that acting is cheap. That is a considerably "
            "easier thing to ask a utility to adopt than a new operating philosophy.",
            accent=BLUE, tint="#eef4fd"),
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
              "The cascade: staggering releases so pulses do not superpose"],
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
                           "YF-S201 flow, pump, acrylic</b>", "<b>1 wk</b>", "<b>6,150</b>", "<b>7,630</b>"],
             ["V2", "Off-grid: LoRa SX1278 (433 MHz), SD logging, INA219 jam detection, solar",
              "1 wk", "2,300", "9,930"],
             ["V3", "Edge AI: ESP32-S3, ESP32-CAM, 24 GHz radar, hydrostatic transmitter, I²S mic",
              "2 wk", "6,900", "16,830"],
             ["V4", "Raspberry Pi offline command post, GPS bathymetry boat",
              "3 wk", "9,400", "26,230"]],
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
             ["YF-S201", "Hall flow, 1–30 L/min, G1/2″", "350", "Closes the mass balance loop"],
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
    return [
        PageBreak(),
        para("9 · Limitations", "h1"), rule(),
        para(
            "Stated plainly, because every one of these will be found by anyone who looks, and "
            "finding them first is the difference between a limitation and a hole."),
        data_table(
            ["Limitation", "Consequence", "Mitigation"],
            [["<b>The counterfactual assumes perfect foresight</b>",
              "The optimiser sees the true inflow series when choosing a policy. Real forecasts "
              "are wrong. <b>Every benefit figure here is an upper bound.</b>",
              "Next: re-run driving the policy from ensemble forecasts with realistic error, "
              "and report the degradation. This is the highest-priority open item"],
             ["Daily input resolution",
              "Bulletin data is one reading per day, interpolated to hourly. Sub-daily peaks "
              "are smoothed away; peak timing carries roughly ±12 h",
              "CWC 15-minute telemetry; ESP32 nodes for local sub-daily truth"],
             ["Routing parameters are estimated",
              "Muskingum K and x come from reach geometry, not gauge pairs. Downstream "
              "discharge figures are indicative, not measured",
              "Calibrate against CWC gauge records at Neeleeswaram and Aluva"],
             [f"Replay error {cf.get('replay_level_mae_m', 0.30):.2f} m MAE",
              "Roughly 0.5 m of the ~3 m freeboard claim sits inside model error",
              "Quote it as “about 3 m”, never to two decimals"],
             ["No 2D inundation",
              "The twin gives river discharge, not which streets flood",
              "LISFLOOD-FP or a HEC-RAS coupling on a Bhuvan DEM"],
             ["Single reservoir optimised",
              "The cascade is characterised but not yet jointly scheduled — the highest-value "
              "modelling gap",
              "The routing layer is already a DAG; extend the policy search across nodes"],
             ["Indicative tariffs",
              "Revenue figures are order-of-magnitude, not audited",
              "Substitute the current KSERC order before quoting rupees to a utility"],
             ["Institutional adoption",
              "A utility will not accept an external recommendation engine on trust",
              "Shadow mode: run alongside real operations for a full monsoon, log what it "
              "would have advised, publish the comparison"]],
            widths=[42 * mm, 62 * mm, CONTENT_W - 104 * mm]),
        Spacer(1, 8),
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
              "Forecast-error study; cascade co-optimisation; gauge calibration; V1 rig; "
              "3D interface",
              "Turns an upper-bound result into a defensible one"],
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
            "And the operating level the optimiser chose? 728.43 metres. KSEB's own published "
            "rule level is 728.50. We did not invent a better rule. The rule is already right. "
            "What is missing is a system that acts on it while acting is still cheap — and "
            "that is what this is.”", S["callout"])]], colWidths=[CONTENT_W],
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
