"""Build the AquaSync deep-research report PDF.

Renders whatever the multi-agent research sweep produced. Input is
``research/index/research_findings.json`` with the shape:

    {
      "dimensions": [
        {"dimension": str,
         "confirmed_sources": [{name, url, kind, what_it_provides,
                                relevance, http_status,
                                content_matches_claim, license,
                                last_activity, stars, caveat}],
         "rejected": [{name, url, reason}],
         "verification_notes": [str]}
      ],
      "synthesis": {
        "executive_summary": [str],
        "integration_paths": [{target_system, approach, standard_or_protocol,
                               effort, blockers, regulatory_note}],
        "prioritised_upgrades": [{upgrade, closes_which_gap, uses, effort,
                                  value, verdict}],
        "download_manifest": [...],
        "honest_challenges": [str]
      }
    }

The acquisition state is read separately from
``research/index/acquisition_log.json``, so the report says what was actually
downloaded rather than what was merely intended.

    python scripts/build_research_report.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _pdfkit import (  # noqa: E402
    AMBER,
    BG,
    BLUE,
    CONTENT_W,
    MARGIN,
    PAGE_H,
    RED,
    RULE_C,
    TINT_AMBER,
    TINT_BLUE,
    TINT_RED,
    VIOLET,
    S,
    badge,
    bullets,
    callout,
    data_table,
    kpi_row,
    para,
    rule,
)

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "research" / "index"
FINDINGS = INDEX / "research_findings.json"
ACQ_LOG = INDEX / "acquisition_log.json"
MANIFEST = INDEX / "manifest.json"
OUT = ROOT / "docs" / "AquaSync_Research_Report.pdf"

DIMENSION_TITLES = {
    "historical-data": "Historical data: what exists, and what does not",
    "reservoir-optimisation": "Reservoir optimisation software",
    "hydro-modeling": "Routing, hydraulics and 2D inundation",
    "ml-hydrology": "Machine learning and forecasting",
    "soa-limitations": "State of the art, and where it fails",
    "integration": "Integrating with existing systems",
}

DIMENSION_INTROS = {
    "historical-data":
        "The project's single largest data gap is the absence of genuine 2018 "
        "Idukki and Idamalayar operational records. This sweep established what "
        "is actually obtainable, and by what route.",
    "reservoir-optimisation":
        "Whether any existing framework would be faster to adopt than the "
        "policy search AquaSync already has. The honest answer matters more "
        "than the impressive one.",
    "hydro-modeling":
        "Closing the two modelling gaps: Muskingum parameters that have never "
        "been gauge-calibrated, and the absence of any 2D inundation output.",
    "ml-hydrology":
        "Everything here is judged against one question: does it help replace "
        "the perfect-foresight assumption with realistic forecast ensembles?",
    "soa-limitations":
        "What is genuinely deployed and operational worldwide, how long it took "
        "to get there, and the evidence that complicates this project's thesis.",
    "integration":
        "How a system like AquaSync would actually reach KSEB, KSDMA and CWC - "
        "where the blockers are institutional rather than technical.",
}


def human(nbytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024 or unit == "GB":
            return f"{nbytes:.0f} {unit}" if unit == "B" else f"{nbytes:.1f} {unit}"
        nbytes /= 1024.0
    return f"{nbytes:.1f} GB"


def short(text: str, limit: int = 190) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


def link(url: str, label: str | None = None) -> str:
    label = label or url
    safe = url.replace("&", "&amp;")
    return f'<link href="{safe}"><font color="#1f6feb">{label}</font></link>'


def status_badge(code: str) -> str:
    c = str(code or "").strip()
    if c.startswith("2"):
        return badge("200", "ok")
    if "bot" in c.lower() or c.startswith("40") or c.startswith("50"):
        return badge(c, "medium")
    return badge(c or "?", "neutral")


# --------------------------------------------------------------------------
# sections
# --------------------------------------------------------------------------

def cover(data: dict, acq: dict) -> list:
    dims = data.get("dimensions", [])

    n_sources = sum(len(d.get("confirmed_sources", [])) for d in dims)
    n_rejected = sum(len(d.get("rejected", [])) for d in dims)
    n_got = sum(1 for r in acq.values() if r.get("status") in ("ok", "already-present"))
    total_bytes = sum(r.get("bytes", 0) for r in acq.values() if r.get("status") in ("ok", "already-present"))

    white = ParagraphStyle("w", parent=S["title"], textColor="white", fontSize=32, leading=36)
    wsub = ParagraphStyle("ws", parent=S["subtitle"], textColor="#9fc3f5", fontSize=13, leading=18)
    wsm = ParagraphStyle("wsm", parent=S["body"], textColor="#c9d8ea",
                         fontSize=9.5, leading=14, alignment=0)

    return [
        Spacer(1, 22 * mm),
        Paragraph("Deep research report", white),
        Paragraph(
            "Data, open-source projects, current technology and integration "
            "paths for the AquaSync dam–river digital twin", wsub),
        Spacer(1, 4 * mm),
        Paragraph(
            "Produced by a 13-agent research sweep across six domains.<br/>"
            "Every URL curl-verified; every claim checked by a second, "
            "adversarial agent.", wsm),
        Spacer(1, 40 * mm),
        kpi_row([
            (str(n_sources), "sources confirmed<br/>after verification"),
            (str(n_rejected), "claims rejected<br/>as unverifiable"),
            (str(n_got), "resources downloaded<br/>into research/"),
            (human(total_bytes), "acquired and<br/>indexed locally"),
        ]),
        Spacer(1, 9 * mm),
        callout(
            "Why every link in this document was verified by curl.",
            "The planning material this project grew out of was full of confident, "
            "wrong references: one Amazon ASIN appeared as five different products, "
            "and a dataset was described as containing 2018 flood data it does not "
            "contain. Both errors survived because nobody checked.<br/><br/>"
            "So each research agent was required to run "
            "<font face='Courier' size='8.5'>curl -o /dev/null -w \"%{http_code}\"</font> "
            "against every URL and record the real status, and a second agent then "
            "re-checked the list adversarially and rejected what it could not confirm. "
            + (f"{n_rejected} claimed source{'s' if n_rejected != 1 else ''} did not "
               f"survive that pass." if n_rejected else
               "Every claimed source survived that pass."),
            accent=AMBER, tint=TINT_AMBER),
        Spacer(1, 7 * mm),
        para(f"Generated {datetime.now(UTC).strftime('%d %B %Y')} · "
             "Regenerate with <font face='Courier'>scripts/build_research_report.py</font> · "
             "Local index at <font face='Courier'>research/index/README.md</font>", "caption"),
    ]


def executive_summary(synth: dict) -> list:
    items = synth.get("executive_summary") or []
    if not items:
        return []
    return [
        para("1 · Executive summary", "h1"), rule(),
        para("The findings that change what AquaSync should do next."),
        *[Paragraph(f"<b>{i}.</b> {t}", S["body"]) for i, t in enumerate(items, 1)],
    ]


def challenges(synth: dict) -> list:
    items = synth.get("honest_challenges") or []
    if not items:
        return []
    return [
        para("2 · Evidence that complicates the thesis", "h1"), rule(),
        para(
            "The most useful part of any research sweep is what it finds against "
            "the hypothesis. These are the points a domain-literate reviewer will "
            "raise, and it is far better to have raised them first."),
        *[callout(f"Challenge {i}", t, accent=RED, tint=TINT_RED)
          for i, t in enumerate(items, 1)],
    ]


def upgrades(synth: dict) -> list:
    items = synth.get("prioritised_upgrades") or []
    if not items:
        return []

    order = {"do-now": 0, "do-next": 1, "later": 2, "reject": 3}
    items = sorted(items, key=lambda u: order.get(str(u.get("verdict", "")).split()[0].lower(), 9))

    rows = [
        [badge(str(u.get("verdict", "")).split()[0], str(u.get("verdict", "")).split()[0]),
         f"<b>{u.get('upgrade', '')}</b><br/>"
         f"<font color='#5b6b7f'>closes: {short(u.get('closes_which_gap', ''), 110)}</font>",
         short(u.get("uses", ""), 120),
         u.get("effort", ""),
         short(u.get("value", ""), 130)]
        for u in items
    ]
    return [
        PageBreak(),
        para("3 · Prioritised upgrades", "h1"), rule(),
        para(
            "What to build next, each tied to a specific verified project or "
            "dataset. Ordered by verdict, not by how interesting it sounds."),
        data_table(
            ["", "Upgrade", "Builds on", "Effort", "Why it is worth it"],
            rows,
            widths=[16 * mm, 52 * mm, 40 * mm, 20 * mm, CONTENT_W - 128 * mm],
            small=True, zebra=True),
        Spacer(1, 6),
        para(
            "A <b>reject</b> verdict is a result, not a gap. The failure mode this "
            "project is most exposed to is feature creep across twenty-five "
            "plausible upgrades, and a list that never says no is no help against it.",
            "caption"),
    ]


def integration(synth: dict) -> list:
    items = synth.get("integration_paths") or []
    if not items:
        return []

    out = [
        PageBreak(),
        para("4 · Integration paths", "h1"), rule(),
        para(
            "How AquaSync would reach the systems KSEB, KSDMA and CWC already run. "
            "The technical routes are mostly solved problems; the blockers are "
            "institutional, and are recorded as such."),
    ]
    for p in items:
        body = (
            f"<b>Approach.</b> {p.get('approach', '')}<br/><br/>"
            f"<b>Protocol or standard.</b> {p.get('standard_or_protocol', '')}<br/>"
            f"<b>Effort.</b> {p.get('effort', '')}<br/>"
            f"<b>Blockers.</b> {p.get('blockers', '')}"
        )
        if p.get("regulatory_note"):
            body += f"<br/><br/><b>Regulatory.</b> {p['regulatory_note']}"
        out.append(callout(p.get("target_system", "Target system"), body,
                           accent=BLUE, tint=TINT_BLUE))
    return out


def dimension_section(d: dict, number: int) -> list:
    key = d.get("dimension", "")
    title = DIMENSION_TITLES.get(key, key.replace("-", " ").title())
    intro = DIMENSION_INTROS.get(key, "")

    confirmed = d.get("confirmed_sources") or []
    rejected = d.get("rejected") or []
    notes = d.get("verification_notes") or []

    out = [PageBreak(), para(f"{number} · {title}", "h1"), rule()]
    if intro:
        out.append(para(intro))

    if confirmed:
        rows = []
        for s in confirmed:
            meta = []
            if s.get("stars") and str(s["stars"]) not in ("", "-", "unknown"):
                meta.append(f"{s['stars']} stars")
            if s.get("last_activity") and s["last_activity"] != "unknown":
                meta.append(str(s["last_activity"])[:10])
            if s.get("license") and s["license"] not in ("", "unknown", "none"):
                meta.append(s["license"])
            meta_line = " · ".join(meta)

            cell = f"<b>{s.get('name', '')}</b>"
            if meta_line:
                cell += f"<br/><font color='#5b6b7f' size='6.8'>{meta_line}</font>"
            cell += f"<br/>{link(s.get('url', ''), short(s.get('url', ''), 58))}"

            desc = short(s.get("what_it_provides", ""), 200)
            if s.get("caveat"):
                desc += f"<br/><font color='#bf8700'>caveat: {short(s['caveat'], 140)}</font>"

            rows.append([
                cell,
                s.get("kind", ""),
                desc,
                short(s.get("relevance", ""), 90),
                status_badge(s.get("http_status", "")),
            ])

        out += [
            para(f"Confirmed sources ({len(confirmed)})", "h2"),
            data_table(
                ["Source", "Kind", "What it provides", "Relevance", "HTTP"],
                rows,
                widths=[46 * mm, 14 * mm, CONTENT_W - 128 * mm, 52 * mm, 16 * mm],
                small=True, zebra=True),
        ]

    if notes:
        out += [
            para("Verification notes", "h2"),
            *bullets([short(n, 400) for n in notes]),
        ]

    if rejected:
        out += [
            para(f"Rejected ({len(rejected)})", "h2"),
            para("Recorded so the same ground is not covered twice.", "caption"),
            data_table(
                ["Claimed source", "Why it was rejected"],
                [[r.get("name", ""), short(r.get("reason", ""), 220)] for r in rejected],
                widths=[52 * mm, CONTENT_W - 52 * mm],
                small=True),
        ]

    return out


def whats_local(acq: dict, manifest: list) -> list:
    by_name = {e["name"]: e for e in manifest}
    got = [(n, r) for n, r in acq.items() if r.get("status") in ("ok", "already-present")]
    manual = [(n, r) for n, r in acq.items() if r.get("status") == "manual-registration"]
    failed = [(n, r) for n, r in acq.items() if r.get("status") in ("failed", "skipped-too-large")]

    out = [
        PageBreak(),
        para("What is now on disk", "h1"), rule(),
        para(
            "Everything below was downloaded into <font face='Courier'>research/</font> "
            "and verified non-empty. Bulk snapshots are gitignored - they are large "
            "and re-fetchable - while the manifest, index and findings are committed "
            "so the research is reproducible."),
        para(
            "Repository snapshots are extracted from GitHub tarballs rather than "
            "cloned. Two of them ship filenames containing colons, which are illegal "
            "on Windows and abort a git checkout entirely; tar skips those entries "
            "and extracts the remaining files.", "caption"),
    ]

    if got:
        rows = [
            [f"<b>{n}</b>",
             by_name.get(n, {}).get("kind", "—"),
             f"<font face='Courier' size='7'>{by_name.get(n, {}).get('destination', '—')}</font>",
             human(r.get("bytes", 0)),
             short(by_name.get(n, {}).get("note", ""), 150)]
            for n, r in sorted(got, key=lambda x: -x[1].get("bytes", 0))
        ]
        out += [
            para(f"Acquired ({len(got)})", "h2"),
            data_table(
                ["Resource", "Kind", "Local path", "Size", "Why it is here"],
                rows,
                widths=[38 * mm, 15 * mm, 46 * mm, 17 * mm, CONTENT_W - 116 * mm],
                small=True, zebra=True, align_right=(3,)),
        ]

    if manual:
        out += [
            para(f"Needs manual registration ({len(manual)})", "h2"),
            para(
                "These require a human to create an account or accept terms. "
                "Recorded with what to ask for, so the step is quick.", "caption"),
            data_table(
                ["Resource", "Where", "What to get"],
                [[n, link(by_name.get(n, {}).get("url", ""), short(by_name.get(n, {}).get("url", ""), 46)),
                  short(by_name.get(n, {}).get("note", ""), 150)] for n, _ in manual],
                widths=[42 * mm, 58 * mm, CONTENT_W - 100 * mm],
                small=True),
        ]

    if failed:
        out += [
            para(f"Unavailable ({len(failed)})", "h2"),
            data_table(
                ["Resource", "Why"],
                [[n, short(r.get("error", r.get("status", "")), 200)] for n, r in failed],
                widths=[42 * mm, CONTENT_W - 42 * mm],
                small=True),
        ]

    out += [
        Spacer(1, 8),
        para("Refresh everything", "h2"),
        Table([[Paragraph(
            "<font face='Courier' size='8'>"
            "python scripts/acquire.py                 # fetch the whole manifest<br/>"
            "python scripts/acquire.py --priority high # just the important ones<br/>"
            "python scripts/acquire.py --index-only    # rebuild the index only<br/>"
            "python scripts/build_research_report.py   # rebuild this report"
            "</font>", S["cell"])]], colWidths=[CONTENT_W],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), BG),
                ("BOX", (0, 0), (-1, -1), 0.6, RULE_C),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8)])),
    ]
    return out


def method(data: dict) -> list:
    dims = data.get("dimensions", [])
    return [
        PageBreak(),
        para("Method", "h1"), rule(),
        para(
            "Thirteen agents in three phases. Six searched one domain each; six "
            "adversarial verifiers re-checked those findings; one synthesised."),
        data_table(
            ["Phase", "Agents", "What they did"],
            [["Research", "6",
              "One per domain. Many distinct web searches, primary sources preferred, "
              "every URL curl-verified with the real HTTP status recorded, GitHub repos "
              "checked against the API for stars, licence and last push."],
             ["Verify", "6",
              "Adversarial. Re-checked every URL independently, deep-read the most "
              "important sources to confirm they provide what was claimed, and rejected "
              "anything unconfirmable. Bot-blocked sites (403/503 to automated requests) "
              "were confirmed by another route rather than discarded."],
             ["Synthesize", "1",
              "Cross-domain integration paths, prioritised upgrades tied to specific "
              "verified projects, a download manifest, and the evidence against the thesis."]],
            widths=[24 * mm, 15 * mm, CONTENT_W - 39 * mm], small=True),
        Spacer(1, 8),
        para("Domains covered", "h2"),
        data_table(
            ["Domain", "Confirmed", "Rejected"],
            [[DIMENSION_TITLES.get(d.get("dimension", ""), d.get("dimension", "")),
              str(len(d.get("confirmed_sources", []))),
              str(len(d.get("rejected", [])))] for d in dims],
            widths=[CONTENT_W - 46 * mm, 23 * mm, 23 * mm],
            small=True, align_right=(1, 2)),
        Spacer(1, 10),
        callout(
            "What this method does not guarantee.",
            "Verification confirms that a URL resolves and that its content matches "
            "what was claimed about it. It does not constitute a peer review of the "
            "underlying science, and it cannot detect a source that is internally "
            "consistent but wrong. Anything load-bearing for a decision should still "
            "be read in full before it is relied on.",
            accent=VIOLET, tint="#f4f0fb"),
    ]


# --------------------------------------------------------------------------

def build() -> int:
    if not FINDINGS.exists():
        print(f"no findings at {FINDINGS}", file=sys.stderr)
        print("run the deep-research workflow first", file=sys.stderr)
        return 1

    data = json.loads(FINDINGS.read_text(encoding="utf-8"))
    acq = json.loads(ACQ_LOG.read_text(encoding="utf-8")) if ACQ_LOG.exists() else {}
    manifest = []
    if MANIFEST.exists():
        m = json.loads(MANIFEST.read_text(encoding="utf-8"))
        manifest = m.get("download_manifest", m) if isinstance(m, dict) else m

    synth = data.get("synthesis") or {}
    dims = data.get("dimensions") or []

    doc = BaseDocTemplate(
        str(OUT), pagesize=A4, invariant=1,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN + 4 * mm,
        title="AquaSync - Deep Research Report",
        author="Am4l-babu",
        subject="Data, open-source projects, technology and integration for the AquaSync digital twin",
    )
    frame = Frame(MARGIN, MARGIN + 4 * mm, CONTENT_W, PAGE_H - 2 * MARGIN - 4 * mm, id="main")

    from _pdfkit import make_cover_banner, make_page_footer

    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[frame], onPage=make_cover_banner()),
        PageTemplate(id="body", frames=[frame],
                     onPage=make_page_footer("AquaSync  ·  Deep research report")),
    ])

    story: list = []
    story += cover(data, acq)
    story += [NextPageTemplate("body"), PageBreak()]
    story += executive_summary(synth)
    story += challenges(synth)
    story += upgrades(synth)
    story += integration(synth)

    for i, d in enumerate(dims, start=5):
        story += dimension_section(d, i)

    story += whats_local(acq, manifest)
    story += method(data)

    doc.build(story)
    print(f"wrote {OUT}  ({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
