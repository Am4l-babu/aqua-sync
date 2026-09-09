"""The telemetry frame must never call a recording live.

The dashboard used to light a green LIVE badge the moment the WebSocket
opened, while the stream underneath it was a recorded October 2021 episode.
Connecting proves the backend is reachable; it says nothing about whether
anything is being measured. These tests pin the two halves of the fix: the
server declares provenance on every frame, and the client does not invent it
from the transport.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from aquasync.api.main import Telemetry  # noqa: E402

DASHBOARD = Path(__file__).resolve().parents[2] / "dashboard"


def frame(**over) -> Telemetry:
    base = dict(level=730.9, inflow=222.0, turbine=115.0, spill=89.0, gate=22.0,
                freeboard=1.48, timestamp="2021-10-20 07:00:00",
                scenario="periyar_oct_2021", advice="Drawdown in progress.")
    return Telemetry(**{**base, **over})


class TestProvenance:
    def test_a_frame_that_does_not_say_defaults_to_replay(self):
        """The safe default is the honest one.

        If a future code path forgets to set `source`, the frame must under-
        claim rather than over-claim. Defaulting to LIVE would mean a silent
        bug presents simulated water as measured water.
        """
        assert frame().source == "REPLAY"

    def test_source_survives_serialisation(self):
        payload = json.loads(json.dumps(frame().model_dump()))
        assert payload["source"] == "REPLAY"

    def test_a_live_frame_can_still_say_so(self):
        assert frame(source="LIVE").source == "LIVE"


class TestDashboardDoesNotInferLiveness:
    """Guards the client half. The bug was one line in `ws.onopen`."""

    def _twin_js(self) -> str:
        return (DASHBOARD / "js" / "twin.js").read_text(encoding="utf-8")

    def test_opening_the_socket_does_not_claim_live(self):
        js = self._twin_js()
        onopen = js[js.index("ws.onopen"):]
        onopen = onopen[:onopen.index("\n")]
        assert "LIVE" not in onopen, (
            "ws.onopen must not label the stream LIVE - an open socket is not "
            f"a measurement. Found: {onopen.strip()}"
        )

    def test_the_badge_is_driven_by_the_declared_source(self):
        js = self._twin_js()
        assert "SOURCE_STYLE" in js
        assert "t.source" in js

    def test_only_live_is_styled_as_live(self):
        """REPLAY and STALE must both be visibly not-live."""
        js = self._twin_js()
        block = js[js.index("const SOURCE_STYLE"):]
        block = block[:block.index("};")]
        for line in block.splitlines():
            if "REPLAY" in line or "STALE" in line or "SIMULATED" in line:
                assert "'ok'" not in line, f"non-live source styled as live: {line.strip()}"
