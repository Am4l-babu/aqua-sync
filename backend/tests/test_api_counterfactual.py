"""The counterfactual payload carries what the simulation view draws.

The dashboard's simulation view scrubs through the episode hour by hour and
drives the 3D twin from it, so the payload must ship the driving inflow and
the recorded bulletin level next to the twin's own replay - the recorded
line is what makes the 0.30 m replay error visible instead of merely stated.
These tests build the payload from a stub search so they run in
milliseconds and without ``data/raw``.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("fastapi")

from aquasync.api import main  # noqa: E402


def _stub_counterfactual(key: str, cache_dir, inflow_scale: float = 1.0):
    hours = 6
    series = pd.DataFrame({
        "date": pd.date_range("2021-10-08", periods=hours, freq="1h"),
        "water_level_m": [727.7, 727.8, np.nan, 728.1, 728.3, 728.4],
        "inflow_cumecs": [116.0, 120.0, np.nan, 130.0, 140.0, 150.0],
    })
    ev = SimpleNamespace(
        levels=np.linspace(727.7, 728.4, hours),
        release=np.full(hours, 60.0),
        metadata={"policy": {"target_level_m": 727.9, "start_hour": 2,
                             "max_rate_cumecs": 300.0}},
    )
    return {
        "scenario": key,
        "series": series,
        "evaluations": {"observed": ev, "optimised": ev},
        "summary": {
            "freeboard_gained_m": 3.0, "headline_note": "note",
            "replay_level_mae_m": 0.3, "replay_level_max_err_m": 0.57,
            "replay_final_err_m": 0.5, "inflow_scale": inflow_scale,
        },
    }


@pytest.fixture
def payload(monkeypatch):
    monkeypatch.setattr(main, "run_counterfactual", _stub_counterfactual)
    # A key no real call uses, so the lru_cache cannot hand back a stale
    # real payload from another test.
    return main._counterfactual_payload("__stub__", "nowhere")


@pytest.fixture
def scaled(monkeypatch):
    monkeypatch.setattr(main, "run_counterfactual", _stub_counterfactual)
    return main._counterfactual_payload("__stub_scaled__", "nowhere", 1.5)


class TestStormStressTest:
    def test_scaled_inflow_is_what_the_client_sees(self, scaled):
        assert scaled["series"]["inflow"][0] == pytest.approx(116.0 * 1.5)
        assert scaled["summary"]["inflow_scale"] == 1.5

    def test_a_scaled_storm_drops_the_replay_error(self, scaled):
        """0.30 m MAE is against the recorded storm. It does not carry over
        to a storm that never happened, and must not be shown as if it did."""
        for k in ("replay_level_mae_m", "replay_level_max_err_m", "replay_final_err_m"):
            assert k not in scaled["summary"]
        assert scaled["series"]["bulletin_level"] == []
        assert "not a forecast" in scaled["summary"]["stress_note"]

    def test_unscaled_keeps_the_replay_error(self, payload):
        assert payload["summary"]["replay_level_mae_m"] == 0.3
        assert "stress_note" not in payload["summary"]

    def test_the_twin_refuses_a_non_positive_scale(self):
        from aquasync.twin.scenarios import run_counterfactual
        with pytest.raises(ValueError):
            run_counterfactual("periyar_oct_2021", "nowhere", inflow_scale=0.0)


class TestCounterfactualPayload:
    def test_carries_inflow_and_bulletin_level(self, payload):
        s = payload["series"]
        assert len(s["inflow"]) == len(s["observed_level"]) == 6
        assert len(s["bulletin_level"]) == 6
        assert s["inflow"][0] == 116.0
        assert s["bulletin_level"][0] == 727.7

    def test_a_missing_bulletin_hour_is_null_not_a_number(self, payload):
        """NaN is not JSON, and inventing a level for a gap would be worse."""
        assert payload["series"]["bulletin_level"][2] is None
        assert payload["series"]["inflow"][2] == 0.0
        json.dumps(payload)   # must serialise

    def test_timestamps_line_up_with_the_hourly_grid(self, payload):
        stamps = payload["series"]["timestamps"]
        assert len(stamps) == 6
        assert stamps[0].startswith("2021-10-08 00:00")
        assert stamps[-1].startswith("2021-10-08 05:00")

    def test_existing_keys_are_unchanged(self, payload):
        """Clients already reading the old shape must keep working."""
        for key in ("observed_level", "optimised_level",
                    "observed_release", "optimised_release"):
            assert key in payload["series"]
        assert payload["policy"]["start_hour"] == 2
        assert payload["summary"]["headline_note"] == "note"
