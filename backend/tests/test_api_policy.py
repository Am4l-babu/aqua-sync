"""The catchment what-if, the Malayalam advisory and the sweep reader.

Three things the reference brief asked for, each built in the only shape the
validated model can carry. These tests pin the shape, not the hydrology -
the hydrology is pinned in test_twin.py and scored in
scripts/runoff_validation.py.
"""

from __future__ import annotations

import asyncio
import json
import re

import numpy as np
import pytest

pytest.importorskip("fastapi")

from aquasync.api import main  # noqa: E402
from aquasync.twin import IDUKKI  # noqa: E402

MALAYALAM = re.compile(r"[ഀ-ൿ]")


def _storm(hours: int = 96, total_mm: float = 168.0) -> np.ndarray:
    """One 24 h storm of `total_mm`, then a dry tail long enough to drain."""
    rain = np.zeros(hours)
    rain[12:36] = total_mm / 24.0
    return rain


class TestCatchmentWhatIf:
    def test_handbook_cn_changes_nothing(self):
        d = main.runoff_whatif(_storm(), main.DEFAULT_CN_IDUKKI)
        assert d["runoff_volume_change_pct"] == pytest.approx(0.0)
        assert d["runoff_volume_mm3"] == pytest.approx(d["runoff_volume_handbook_mm3"])

    def test_more_paved_ground_runs_off_more(self):
        """A higher curve number is less infiltration, so more of the same
        rain becomes runoff - the one direction the handbook lookup must
        never get backwards."""
        lo = main.runoff_whatif(_storm(), 60.0)
        hi = main.runoff_whatif(_storm(), 85.0)
        assert hi["runoff_volume_mm3"] > lo["runoff_volume_mm3"]
        assert hi["runoff_fraction"] > lo["runoff_fraction"]
        assert 0.0 < lo["runoff_fraction"] < hi["runoff_fraction"] <= 1.0

    def test_the_peak_is_labelled_unvalidated(self):
        d = main.runoff_whatif(_storm(), 72.0)
        assert "shape_unvalidated" in "".join(k for k in d if "peak" in k)
        assert "not validated" in d["caveat"]

    def test_no_rain_no_runoff_and_no_division_by_zero(self):
        d = main.runoff_whatif(np.zeros(48), 72.0)
        assert d["runoff_volume_mm3"] == 0.0
        assert d["runoff_fraction"] is None
        json.dumps(d)


class TestMalayalamAdvisory:
    BANDS = [
        (IDUKKI.frl + 0.1, 0.0),               # FRL exceeded
        (IDUKKI.red_level + 0.05, 0.0),        # red, gates shut
        (IDUKKI.rule_level + 0.05, 0.0),       # above rule, gates shut
        (IDUKKI.rule_level + 0.05, 120.0),     # above rule, spilling
        (IDUKKI.rule_level - 1.0, 0.0),        # within rule
    ]

    def test_every_band_has_a_line_in_malayalam_script(self):
        for level, spill in self.BANDS:
            text = main._advice_ml(level, spill)
            assert text and MALAYALAM.search(text), (level, spill, text)

    def test_bands_are_distinct(self):
        lines = {main._advice_ml(lvl, sp) for lvl, sp in self.BANDS}
        assert len(lines) == len(self.BANDS)

    def test_bands_follow_the_english_advice(self):
        """Same thresholds as `_advice`: the two must not disagree about
        which band the reservoir is in."""
        for level, spill in self.BANDS:
            en = main._advice(level, spill)
            ml = main._advice_ml(level, spill)
            if "FRL EXCEEDED" in en:
                assert "FRL" in ml
            elif "red alert" in en:
                assert "റെഡ്" in ml
            elif "Begin staged drawdown" in en:
                assert "ഓറഞ്ച്" in ml
            elif "Drawdown in progress" in en:
                assert "ഷട്ടറുകൾ തുറന്നിരിക്കുന്നു" in ml
            else:
                assert "സാധാരണ" in ml

    def test_the_frame_carries_it(self):
        t = main.Telemetry(level=730.0, inflow=1.0, turbine=1.0, spill=0.0, gate=0.0,
                           freeboard=2.43, timestamp="t", scenario="s", advice="a",
                           advice_ml=main._advice_ml(730.0, 0.0))
        assert MALAYALAM.search(json.dumps(t.model_dump(), ensure_ascii=False))


class TestStressSweepRoute:
    def test_reads_the_file_the_script_wrote(self, tmp_path, monkeypatch):
        out = tmp_path / "data" / "processed"
        out.mkdir(parents=True)
        payload = {"scenario": "periyar_oct_2021", "ladder": [1.0, 1.25],
                   "first_multiple_reaching_frl": {"baseline": 1.25, "optimised": None}}
        (out / "stress_sweep_periyar_oct_2021.json").write_text(
            json.dumps(payload), encoding="utf-8")
        monkeypatch.setattr(main, "ROOT", tmp_path)
        assert asyncio.run(main.stress_sweep("periyar_oct_2021")) == payload

    def test_missing_file_is_a_404_not_a_crash(self, tmp_path, monkeypatch):
        from fastapi import HTTPException
        monkeypatch.setattr(main, "ROOT", tmp_path)
        with pytest.raises(HTTPException) as exc:
            asyncio.run(main.stress_sweep("periyar_oct_2021"))
        assert exc.value.status_code == 404

    def test_unknown_scenario_is_a_404(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            asyncio.run(main.stress_sweep("nope"))
