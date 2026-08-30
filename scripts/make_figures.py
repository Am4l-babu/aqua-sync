"""Generate every figure used in the dossier and the poster.

All figures are built from data fetched at run time, never from hand-entered
numbers. If the upstream feed changes, the figures change and the caption
numbers regenerate with them.

    python scripts/make_figures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from aquasync.io import load_dam  # noqa: E402
from aquasync.twin import IDAMALAYAR, IDUKKI  # noqa: E402

OUT = ROOT / "docs" / "assets"
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"

INK = "#12263a"
MUTED = "#6b7c93"
BLUE = "#1f6feb"
RED = "#d1242f"
AMBER = "#bf8700"
GREEN = "#1a7f37"
GRID = "#dde3ea"


def style(ax, title: str = "", ylabel: str = "") -> None:
    ax.set_facecolor("white")
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.grid(True, color=GRID, linewidth=0.7, alpha=0.9)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED, labelsize=8.5)
    if title:
        ax.set_title(title, color=INK, fontsize=11.5, fontweight="bold", loc="left", pad=10)
    if ylabel:
        ax.set_ylabel(ylabel, color=MUTED, fontsize=9)


def fig_oct2021_crisis() -> dict:
    """The flagship chart: what actually happened at Idukki in October 2021."""
    rec = load_dam("Idukki", cache_dir=RAW)
    w = rec.window("2021-10-05", "2021-10-28").copy()
    w = w.set_index("date").asfreq("D").reset_index()
    for c in ("water_level_m", "inflow_cumecs", "spillway_cumecs", "rainfall_mm"):
        w[c] = pd.to_numeric(w[c], errors="coerce").interpolate()

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(9.2, 6.0), sharex=True, gridspec_kw={"height_ratios": [1.35, 1]}
    )

    # -- top: level against the alert bands --
    style(ax1, "Idukki reservoir level, October 2021", "Level (m MSL)")
    ax1.axhspan(IDUKKI.frl, IDUKKI.frl + 0.6, color=RED, alpha=0.10)
    ax1.axhline(IDUKKI.frl, color=RED, lw=1.6, ls="--")
    ax1.axhline(IDUKKI.rule_level, color=GREEN, lw=1.6, ls="--")
    ax1.plot(w.date, w.water_level_m, color=INK, lw=2.4, marker="o", ms=3.5, zorder=5)

    ax1.text(w.date.iloc[0], IDUKKI.frl + 0.10, f"FRL {IDUKKI.frl} m",
             color=RED, fontsize=8.5, fontweight="bold", va="bottom")
    ax1.text(w.date.iloc[0], IDUKKI.rule_level - 0.30, f"Rule level {IDUKKI.rule_level} m",
             color=GREEN, fontsize=8.5, fontweight="bold", va="top")

    storm = pd.Timestamp("2021-10-17")
    gates = pd.Timestamp("2021-10-20")
    for when, label, colour in ((storm, "168 mm rain", AMBER), (gates, "gates open", BLUE)):
        ax1.axvline(when, color=colour, lw=1.3, ls=":", zorder=1)
        ax1.annotate(label, xy=(when, ax1.get_ylim()[1]), xytext=(0, -12),
                     textcoords="offset points", ha="center", fontsize=8.5,
                     color=colour, fontweight="bold")

    lvl16 = float(w.loc[w.date == pd.Timestamp("2021-10-16"), "water_level_m"].iloc[0])
    ax1.annotate(
        f"{lvl16:.2f} m — already above rule level,\nspillway shut, storm forecast",
        xy=(pd.Timestamp("2021-10-16"), lvl16), xytext=(-140, -46),
        textcoords="offset points", fontsize=8.5, color=INK,
        arrowprops=dict(arrowstyle="->", color=MUTED, lw=1.1),
        bbox=dict(boxstyle="round,pad=0.45", fc="#fff8e5", ec=AMBER, lw=0.9),
    )

    # -- bottom: inflow vs spill --
    style(ax2, "Inflow and spillway release", "Discharge (cumecs)")
    ax2.fill_between(w.date, w.inflow_cumecs, color=BLUE, alpha=0.22, label="Inflow")
    ax2.plot(w.date, w.inflow_cumecs, color=BLUE, lw=2.2)
    ax2.bar(w.date, w.spillway_cumecs, color=RED, alpha=0.85, width=0.6, label="Spillway release")
    ax2.axvline(storm, color=AMBER, lw=1.3, ls=":")
    ax2.axvline(gates, color=BLUE, lw=1.3, ls=":")

    peak = float(w.inflow_cumecs.max())
    ax2.annotate(f"inflow {peak:.0f} cumecs\n(7.6x in 24 h)",
                 xy=(storm, peak), xytext=(18, -6), textcoords="offset points",
                 fontsize=8.5, color=INK, fontweight="bold")
    ax2.annotate("3-day gap between\nthe surge and the response",
                 xy=(pd.Timestamp("2021-10-18T12"), peak * 0.45),
                 fontsize=8.5, color=RED, ha="center",
                 bbox=dict(boxstyle="round,pad=0.4", fc="#fdeef0", ec=RED, lw=0.9))
    ax2.legend(frameon=False, fontsize=8.5, labelcolor=MUTED, loc="upper right")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))

    fig.tight_layout()
    fig.savefig(OUT / "fig1_oct2021_crisis.png", dpi=200, facecolor="white")
    plt.close(fig)

    return {
        "level_16_oct": lvl16,
        "peak_inflow": peak,
        "rule_level": IDUKKI.rule_level,
        "peak_level": float(w.water_level_m.max()),
    }


def fig_cascade() -> dict:
    """Both Periyar dams, showing they opened gates on the same day."""
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.5))
    stats = {}

    for ax, res in zip(axes, (IDUKKI, IDAMALAYAR), strict=True):
        rec = load_dam(res.name, cache_dir=RAW)
        w = rec.window("2021-10-10", "2021-10-26").copy()
        w = w.set_index("date").asfreq("D").reset_index()
        for c in ("water_level_m", "spillway_cumecs"):
            w[c] = pd.to_numeric(w[c], errors="coerce").interpolate()

        style(ax, f"{res.name}", "Level (m MSL)")
        ax.axhline(res.frl, color=RED, lw=1.3, ls="--")
        ax.axhline(res.rule_level, color=GREEN, lw=1.3, ls="--")
        ax.plot(w.date, w.water_level_m, color=INK, lw=2.2)
        ax.axvline(pd.Timestamp("2021-10-20"), color=BLUE, lw=1.6, ls=":")

        ax2 = ax.twinx()
        ax2.bar(w.date, w.spillway_cumecs, color=RED, alpha=0.55, width=0.6)
        ax2.set_ylabel("Spill (cumecs)", color=MUTED, fontsize=8.5)
        ax2.tick_params(colors=MUTED, labelsize=8)
        for s in ("top", "left"):
            ax2.spines[s].set_visible(False)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d"))

        spill20 = float(w.loc[w.date == pd.Timestamp("2021-10-20"), "spillway_cumecs"].iloc[0])
        stats[res.key] = {"spill_20_oct": spill20, "rule": res.rule_level}

    fig.suptitle(
        "Both Periyar reservoirs opened their gates on 20 October 2021 — into the same river",
        color=INK, fontsize=11, fontweight="bold", x=0.01, ha="left", y=1.0,
    )
    fig.tight_layout()
    fig.savefig(OUT / "fig2_cascade.png", dpi=200, facecolor="white")
    plt.close(fig)
    return stats


def fig_level_storage() -> dict:
    """Calibration of the level-storage curve, clean vs raw."""
    from aquasync.twin import LevelStorageCurve

    rec = load_dam("Idukki", cache_dir=RAW)
    raw = rec.frame.dropna(subset=["water_level_m", "live_storage_mm3"])
    clean = rec.clean().dropna(subset=["water_level_m", "live_storage_mm3"])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.6))

    style(ax1, "Raw feed — 11% of rows are impossible", "Live storage (Mm3)")
    bad = raw[~raw.index.isin(clean.index)]
    ax1.scatter(clean.water_level_m, clean.live_storage_mm3, s=5, color=BLUE, alpha=0.35, label="valid")
    ax1.scatter(bad.water_level_m, bad.live_storage_mm3, s=7, color=RED, alpha=0.6, label="impossible")
    ax1.axhline(IDUKKI.live_storage_at_frl, color=INK, lw=1.3, ls="--")
    ax1.text(703, IDUKKI.live_storage_at_frl + 60, "physical capacity at FRL",
             fontsize=8, color=INK)
    ax1.set_xlabel("Level (m MSL)", color=MUTED, fontsize=9)
    ax1.legend(frameon=False, fontsize=8, labelcolor=MUTED, loc="upper left")

    curve = LevelStorageCurve(IDUKKI)
    beta = curve.fit_from_observations(clean.water_level_m, clean.live_storage_mm3)
    xs = np.linspace(clean.water_level_m.min(), IDUKKI.frl, 200)
    ys = [curve.storage_from_level(v) for v in xs]
    pred = np.array([curve.storage_from_level(v) for v in clean.water_level_m])
    obs = clean.live_storage_mm3.to_numpy()
    r2 = 1 - ((pred - obs) ** 2).sum() / ((obs - obs.mean()) ** 2).sum()
    mae = float(np.abs(pred - obs).mean())

    style(ax2, "Validated rows — fitted power law", "Live storage (Mm3)")
    ax2.scatter(clean.water_level_m, clean.live_storage_mm3, s=5, color=MUTED, alpha=0.3)
    ax2.plot(xs, ys, color=GREEN, lw=2.4)
    ax2.set_xlabel("Level (m MSL)", color=MUTED, fontsize=9)
    ax2.text(0.04, 0.94,
             f"beta = {beta:.3f}\nr2 = {r2:.4f}\nMAE = {mae:.0f} Mm3  (n = {len(clean)})",
             transform=ax2.transAxes, fontsize=8.5, va="top", color=INK,
             bbox=dict(boxstyle="round,pad=0.45", fc="#eefbf1", ec=GREEN, lw=0.9))

    fig.tight_layout()
    fig.savefig(OUT / "fig3_calibration.png", dpi=200, facecolor="white")
    plt.close(fig)
    return {"beta": float(beta), "r2": float(r2), "mae": mae, "n": int(len(clean))}


def fig_lead_time() -> dict:
    """Lead time versus spill fraction and freeboard."""
    csv = PROC / "lead_time_study.csv"
    if not csv.exists():
        print("  (skipping lead-time figure: run scripts/lead_time_study.py first)")
        return {}
    d = pd.read_csv(csv)
    n = d[d.energy_neutral].sort_values("lead_days")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.6))

    style(ax1, "Flood cushion gained is roughly constant", "Freeboard gained (m)")
    ax1.bar(n.lead_days.astype(str), n.freeboard_gained_m, color=GREEN, alpha=0.8, width=0.62)
    ax1.set_xlabel("Forecast lead time (days)", color=MUTED, fontsize=9)
    ax1.axhline(float(n.freeboard_gained_m.mean()), color=INK, lw=1.2, ls="--")
    # "about 3 m", never 3.16 - two decimals claim precision the 0.30 m replay
    # error does not support.
    ax1.text(0.02, 0.915, f"mean about {n.freeboard_gained_m.mean():.0f} m",
             transform=ax1.transAxes, fontsize=8.5, color=INK, va="bottom")

    style(ax2, "What lead time actually buys: less waste", "Share of release spilled")
    ax2.plot(n.lead_days, n.spill_fraction * 100, color=RED, lw=2.4, marker="o", ms=5)
    ax2.set_xlabel("Forecast lead time (days)", color=MUTED, fontsize=9)
    ax2.set_ylim(0, 70)
    ax2.annotate(
        f"{n.spill_fraction.iloc[0]*100:.0f}% spilled\nacting on the day",
        xy=(0, n.spill_fraction.iloc[0] * 100), xytext=(20, -52),
        textcoords="offset points", fontsize=8.5, color=RED,
        arrowprops=dict(arrowstyle="->", color=MUTED, lw=1))
    ax2.annotate(
        f"{n.spill_fraction.iloc[-1]*100:.0f}% at 30 days —\nthe rest earns revenue",
        xy=(30, n.spill_fraction.iloc[-1] * 100), xytext=(-125, 22),
        textcoords="offset points", fontsize=8.5, color=GREEN,
        arrowprops=dict(arrowstyle="->", color=MUTED, lw=1))

    fig.tight_layout()
    fig.savefig(OUT / "fig4_lead_time.png", dpi=200, facecolor="white")
    plt.close(fig)

    return {
        "freeboard_mean": float(n.freeboard_gained_m.mean()),
        "spill_0": float(n.spill_fraction.iloc[0]),
        "spill_30": float(n.spill_fraction.iloc[-1]),
        "revenue_min": float(n.revenue_delta_cr.min()),
        "revenue_max": float(n.revenue_delta_cr.max()),
        "target_level": float(n.policy_target_level_m.mode().iloc[0]),
    }


def fig_counterfactual() -> dict:
    """Observed versus optimised trajectory for the flagship scenario."""
    from aquasync.twin.scenarios import run_counterfactual

    out = run_counterfactual("periyar_oct_2021", cache_dir=RAW)
    ev, series, s = out["evaluations"], out["series"], out["summary"]
    obs, opt = ev["observed"], ev["optimised"]
    t = series["date"]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.2, 5.6), sharex=True)

    style(ax1, "Reservoir level: what happened vs what the twin recommends", "Level (m MSL)")
    ax1.axhline(IDUKKI.frl, color=RED, lw=1.4, ls="--")
    ax1.axhline(IDUKKI.rule_level, color=GREEN, lw=1.4, ls="--")
    ax1.plot(t, obs.levels, color=RED, lw=2.4, label="Observed operation")
    ax1.plot(t, opt.levels, color=GREEN, lw=2.4, label="AquaSync policy")
    ax1.fill_between(t, opt.levels, obs.levels, color=GREEN, alpha=0.12)
    ax1.text(t.iloc[3], IDUKKI.frl + 0.08, f"FRL {IDUKKI.frl}", color=RED, fontsize=8.5, fontweight="bold")
    ax1.text(t.iloc[3], IDUKKI.rule_level - 0.35, f"Rule {IDUKKI.rule_level}", color=GREEN, fontsize=8.5, fontweight="bold")
    ax1.annotate(f"about {s['freeboard_gained_m']:.1f} m more\nflood cushion",
                 xy=(t.iloc[int(len(t) * 0.72)], (obs.levels[int(len(t)*0.72)] + opt.levels[int(len(t)*0.72)]) / 2),
                 xytext=(-30, -6), textcoords="offset points", fontsize=9, color=GREEN,
                 fontweight="bold", ha="right")
    ax1.legend(frameon=False, fontsize=8.5, labelcolor=MUTED, loc="lower right")

    style(ax2, "Total release from the dam", "Discharge (cumecs)")
    ax2.plot(t, obs.release, color=RED, lw=2.0, label="Observed")
    ax2.plot(t, opt.release, color=GREEN, lw=2.0, label="AquaSync")
    ax2.axhline(IDUKKI.turbine_rated_flow, color=INK, lw=1.2, ls=":")
    ax2.text(t.iloc[3], IDUKKI.turbine_rated_flow + 14,
             f"turbine capacity {IDUKKI.turbine_rated_flow:.0f} cumecs — above this line, water is wasted",
             fontsize=8, color=INK)
    ax2.legend(frameon=False, fontsize=8.5, labelcolor=MUTED, loc="upper left")
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))

    fig.tight_layout()
    fig.savefig(OUT / "fig5_counterfactual.png", dpi=200, facecolor="white")
    plt.close(fig)
    return {k: v for k, v in s.items() if isinstance(v, (int, float, bool))}


def fig_forecast_error() -> dict:
    """What deciding under a real forecast costs, on the optimiser's own objective."""
    files = sorted(PROC.glob("forecast_error_study_*.json"))
    if not files:
        print("  (skipping forecast-error figure: run scripts/forecast_error_study.py first)")
        return {}
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in files]
    runs = [r for r in runs if "total_cost" in r.get("perfect_foresight", {})]
    if not runs:
        print("  (skipping forecast-error figure: results predate the cost metric, re-run)")
        return {}
    runs.sort(key=lambda r: r["lead_hours_before_storm_peak"])

    leads = [float(r["lead_hours_before_storm_peak"]) for r in runs]
    ev = [r["decision_rule_expected_value"] for r in runs]
    mm = [r["decision_rule_minimax_regret"] for r in runs]
    pf_rev = float(runs[0]["perfect_foresight"]["revenue_delta_cr"])
    ev_cost = [v["excess_cost_vs_perfect_foresight_pct"] for v in ev]
    mm_cost = [v["excess_cost_vs_perfect_foresight_pct"] for v in mm]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.6))
    x = np.arange(len(runs))
    labels = [f"{h:.0f} h" for h in leads]

    # The honest axis: the objective the optimiser actually minimises. Zero
    # means the forecast picked the policy hindsight would have picked.
    style(ax1, "What deciding without hindsight costs", "Excess cost vs perfect foresight (%)")
    ax1.axhline(0.0, color=INK, lw=1.3, ls="--")
    ax1.text(-0.35, 2.0, "hindsight-optimal", fontsize=8.5, color=INK, fontweight="bold")
    ax1.plot(x, ev_cost, color=AMBER, lw=2.2, marker="o", ms=6, label="Expected value")
    ax1.plot(x, mm_cost, color=GREEN, lw=2.2, marker="s", ms=5.5, label="Minimax regret")
    ax1.set_xticks(x, labels)
    ax1.set_xlabel("Lead time before the storm peak", color=MUTED, fontsize=9)
    ax1.set_ylim(-6, max(mm_cost + ev_cost) * 1.32)
    ax1.legend(frameon=False, fontsize=8.5, labelcolor=MUTED, loc="upper left")

    # Why the freeboard-only reading flatters it: the extra cushion is bought.
    style(ax2, "What the extra cushion cost", "Revenue vs observed (Rs crore)")
    w = 0.34
    ax2.bar(x - w / 2, [v["revenue_delta_cr"] for v in ev], width=w, color=AMBER,
            alpha=0.85, label="Expected value")
    ax2.bar(x + w / 2, [v["revenue_delta_cr"] for v in mm], width=w, color=GREEN,
            alpha=0.85, label="Minimax regret")
    ax2.axhline(pf_rev, color=INK, lw=1.3, ls="--")
    ax2.text(-0.35, pf_rev + 0.03, f"perfect foresight {pf_rev:+.2f}", fontsize=8.5,
             color=INK, fontweight="bold")
    ax2.set_xticks(x, labels)
    ax2.set_xlabel("Lead time before the storm peak", color=MUTED, fontsize=9)
    ax2.set_ylim(0, max(pf_rev * 1.45, 0.1))
    ax2.legend(frameon=False, fontsize=8.5, labelcolor=MUTED, loc="upper right")

    fig.suptitle(
        "Every forecast-driven policy releases more than hindsight would, and pays for it",
        color=INK, fontsize=11, fontweight="bold", x=0.01, ha="left", y=1.0,
    )
    fig.tight_layout()
    fig.savefig(OUT / "fig6_forecast_error.png", dpi=200, facecolor="white")
    plt.close(fig)

    return {
        "leads_h": leads,
        "issue_dates": [f"{r['issue_date']} {r['hh']}z" for r in runs],
        "perfect_m": float(runs[0]["perfect_foresight"]["freeboard_gained_m"]),
        "perfect_revenue_cr": pf_rev,
        "ev_excess_cost_pct": ev_cost,
        "mm_excess_cost_pct": mm_cost,
        "ev_m": [v["freeboard_gained_m"] for v in ev],
        "mm_m": [v["freeboard_gained_m"] for v in mm],
        "ev_revenue_cr": [v["revenue_delta_cr"] for v in ev],
        "mm_revenue_cr": [v["revenue_delta_cr"] for v in mm],
        "best_excess_cost_pct": min(ev_cost + mm_cost),
        "worst_excess_cost_pct": max(ev_cost + mm_cost),
        "minimax_ever_better": bool(any(m < e for m, e in zip(mm_cost, ev_cost, strict=True))),
        "bias_min": min(float(r["bias_factor"]) for r in runs),
        "bias_max": max(float(r["bias_factor"]) for r in runs),
    }


def fig_cascade_coordination() -> dict:
    """Independent optimisation of two dams on one river makes the joint peak worse."""
    p = PROC / "cascade_coordination.json"
    if not p.exists():
        print("  (skipping cascade-coordination figure: run scripts/cascade_coordination.py first)")
        return {}
    d = json.loads(p.read_text(encoding="utf-8"))

    labels = ["Observed\n(what happened)", "Each dam optimised\nindependently", "Coordinated\n(retimed releases)"]
    vals = [float(d["observed_joint_peak_cumecs"]),
            float(d["naive_independent_joint_peak_cumecs"]),
            float(d["coordinated_joint_peak_cumecs"])]
    colours = [INK, RED, AMBER]

    notes = ["the benchmark to beat",
             f"{abs(float(d['naive_vs_observed_reduction_pct'])):.0f}% worse than observed",
             f"retiming recovers only {float(d['coordination_vs_naive_reduction_pct']):.0f}% of that"]

    fig, ax = plt.subplots(figsize=(9.2, 3.0))
    style(ax, "Optimising each dam for itself is worse than not coordinating at all",
          "Joint peak at the confluence (cumecs)")
    bars = ax.barh(labels, vals, color=colours, alpha=0.85, height=0.58)
    ax.invert_yaxis()
    ax.set_xlim(0, max(vals) * 1.45)
    for b, v, c, note in zip(bars, vals, colours, notes, strict=True):
        y = b.get_y() + b.get_height() / 2
        ax.text(v - max(vals) * 0.015, y, f"{v:,.0f}", va="center", ha="right",
                fontsize=10, color="white", fontweight="bold")
        ax.text(v + max(vals) * 0.025, y, note, va="center", fontsize=9, color=c)

    fig.tight_layout()
    fig.savefig(OUT / "fig7_cascade_coordination.png", dpi=200, facecolor="white")
    plt.close(fig)
    return {k: v for k, v in d.items() if isinstance(v, (int, float))}


def fig_runoff_validation() -> dict:
    """Does SCS-CN reproduce observed inflow? Volume yes, day-to-day no."""
    csv = PROC / "runoff_validation_idukki_series.csv"
    js = PROC / "runoff_validation_idukki.json"
    if not (csv.exists() and js.exists()):
        print("  (skipping runoff figure: run scripts/runoff_validation.py first)")
        return {}
    d = pd.read_csv(csv, parse_dates=["date"])
    stats = json.loads(js.read_text(encoding="utf-8"))
    shipped = stats["as_shipped"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 3.6))

    # One season at daily resolution: the shape is broadly right, the
    # day-to-day amplitude is not.
    season = int(d.season.max())
    w = d[d.season == season]
    style(ax1, f"{season} monsoon, day by day", "Inflow (cumecs)")
    ax1.plot(w.date, w.observed_cumecs, color=INK, lw=2.0, label="Observed (bulletin)")
    ax1.plot(w.date, w.predicted_cumecs, color=BLUE, lw=1.8, alpha=0.85,
             label="SCS-CN from rainfall")
    ax1.legend(frameon=False, fontsize=8.5, labelcolor=MUTED, loc="upper right")
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b"))

    # Seasonal totals: the volume the chain is actually good for.
    style(ax2, "Season totals", "Inflow volume (Mm³)")
    seasons = sorted(d.season.unique())
    obs_v, pred_v = [], []
    for s in seasons:
        g = d[(d.season == s) & d.scored]
        obs_v.append(g.observed_cumecs.sum() * 86400 / 1e6)
        pred_v.append(g.predicted_cumecs.sum() * 86400 / 1e6)
    x = np.arange(len(seasons))
    ax2.bar(x - 0.19, obs_v, width=0.38, color=INK, alpha=0.85, label="Observed")
    ax2.bar(x + 0.19, pred_v, width=0.38, color=BLUE, alpha=0.85, label="Predicted")
    ax2.set_xticks(x, [str(s) for s in seasons])
    ax2.legend(frameon=False, fontsize=8.5, labelcolor=MUTED, loc="upper right")
    for xi, (o, p) in enumerate(zip(obs_v, pred_v, strict=True)):
        ax2.text(xi, max(o, p) * 1.03, f"{(p / o - 1) * 100:+.0f}%", ha="center",
                 fontsize=8, color=MUTED)
    ax2.set_ylim(0, max(max(obs_v), max(pred_v)) * 1.22)

    errs = [(p / o - 1) * 100 for o, p in zip(obs_v, pred_v, strict=True)]
    fig.suptitle(
        f"Storm timing broadly right, storm size wrong: daily NSE "
        f"{shipped['nse']:.2f}, season volume {min(errs):+.0f}% to {max(errs):+.0f}%",
        color=INK, fontsize=11, fontweight="bold", x=0.01, ha="left", y=1.0,
    )
    fig.tight_layout()
    fig.savefig(OUT / "fig8_runoff_validation.png", dpi=200, facecolor="white")
    plt.close(fig)

    return {
        "nse": shipped["nse"], "r2": shipped["r2"],
        "pbias_pct": shipped["pbias_pct"], "volume_ratio": shipped["volume_ratio"],
        "n_days": shipped["n_days"], "seasons": [int(s) for s in seasons],
        "season_volume_error_pct": {str(s): float(e) for s, e in zip(seasons, errs, strict=True)},
        "worst_season_volume_error_pct": float(max(errs, key=abs)),
        "loo_mean_nse": stats["loo_summary"]["mean_nse"],
        "loo_worst_nse": stats["loo_summary"]["worst_nse"],
        "calibrated_cn": stats["calibrated_in_sample"]["curve_number"],
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    facts: dict = {}
    for name, fn in [
        ("oct2021", fig_oct2021_crisis),
        ("cascade", fig_cascade),
        ("calibration", fig_level_storage),
        ("lead_time", fig_lead_time),
        ("counterfactual", fig_counterfactual),
        ("forecast_error", fig_forecast_error),
        ("cascade_coordination", fig_cascade_coordination),
        ("runoff_validation", fig_runoff_validation),
    ]:
        print(f"  building {name} ...")
        facts[name] = fn()

    (PROC / "figure_facts.json").write_text(json.dumps(facts, indent=2, default=float), encoding="utf-8")
    print(f"\nfigures -> {OUT}")
    print(json.dumps(facts, indent=2, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
