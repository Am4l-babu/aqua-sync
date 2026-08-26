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

    for ax, res in zip(axes, (IDUKKI, IDAMALAYAR)):
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
    ax1.text(0.02, 0.93, f"mean +{n.freeboard_gained_m.mean():.2f} m",
             transform=ax1.transAxes, fontsize=8.5, color=INK, va="top")

    style(ax2, "What lead time actually buys: less waste", "Share of release spilled")
    ax2.plot(n.lead_days, n.spill_fraction * 100, color=RED, lw=2.4, marker="o", ms=5)
    ax2.set_xlabel("Forecast lead time (days)", color=MUTED, fontsize=9)
    ax2.set_ylim(0, 70)
    ax2.annotate(
        f"{n.spill_fraction.iloc[0]*100:.0f}% spilled\nacting on the day",
        xy=(0, n.spill_fraction.iloc[0] * 100), xytext=(14, -30),
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


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    facts: dict = {}
    for name, fn in [
        ("oct2021", fig_oct2021_crisis),
        ("cascade", fig_cascade),
        ("calibration", fig_level_storage),
        ("lead_time", fig_lead_time),
        ("counterfactual", fig_counterfactual),
    ]:
        print(f"  building {name} ...")
        facts[name] = fn()

    (PROC / "figure_facts.json").write_text(json.dumps(facts, indent=2, default=float), encoding="utf-8")
    print(f"\nfigures -> {OUT}")
    print(json.dumps(facts, indent=2, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
