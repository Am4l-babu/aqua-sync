"""Tests for the scale-rig MQTT bridge.

These drive the bridge's message handler directly, so they need no broker and
no hardware. What they are really guarding is the honesty rules: rig readings
must never arrive dressed as reservoir readings, a node that has gone quiet
must not still look live, and the hash chain must not claim more than it
proves.
"""

from __future__ import annotations

import hashlib
import json
import time

import pytest

from aquasync.api.rig import GENESIS, ChainVerifier, RigBridge, split_frame


class _Msg:
    """The two attributes paho hands to on_message."""

    def __init__(self, payload: bytes, topic: str = "aquasync/reservoir/01/telemetry"):
        self.payload = payload
        self.topic = topic


def frame(payload_json: str, prev: bytes = GENESIS) -> tuple[bytes, bytes]:
    """Build a wire frame the way the firmware does, returning (raw, digest).

    snprintf writes the payload, SHA-256 chains it to its predecessor, and the
    two are wrapped together - see appendAuditRecord in main.cpp.
    """
    payload = payload_json.encode()
    digest = hashlib.sha256(prev + payload).digest()
    raw = b'{"data":' + payload + b',"hash":"' + digest.hex().encode() + b'"}'
    return raw, digest


READING = (
    '{"node":"aquasync-reservoir-01","uptime_s":42,'
    '"level_m":0.2130,"variance":0.00012,'
    '"ultrasonic_m":0.2140,"pressure_m":0.2120,"temp_c":26.5,'
    '"sensors_agree":true,'
    '"gate_cmd_pct":40.0,"gate_actual_pct":39.1,'
    '"gate_homed":true,"gate_jammed":false,'
    '"flow_lpm":3.20}'
)


class TestFrameSplitting:
    def test_payload_is_sliced_not_reserialised(self):
        """The hash covers the characters the firmware printed.

        Re-encoding the parsed object would renormalise float formatting and
        every checksum would fail, so the bytes must come back verbatim.
        """
        raw, _ = frame(READING)
        payload, reported = split_frame(raw)
        assert payload == READING.encode()
        assert len(reported) == 64

    def test_handles_braces_inside_strings(self):
        raw, _ = frame('{"node":"rig{01}","level_m":0.1}')
        payload, _ = split_frame(raw)
        assert json.loads(payload)["node"] == "rig{01}"

    def test_rejects_a_frame_with_no_data_object(self):
        assert split_frame(b'{"hash":"abc"}') is None


class TestChainVerifier:
    def test_follows_a_clean_run(self):
        v = ChainVerifier()
        prev = GENESIS
        for _ in range(4):
            raw, digest = frame(READING, prev)
            payload, reported = split_frame(raw)
            assert v.check(payload, reported) is True
            prev = digest
        assert v.verified == 4
        assert v.breaks == 0

    def test_a_missing_frame_breaks_the_chain_once_then_resyncs(self):
        """A dropped packet must not condemn every frame after it.

        Over lossy Wi-Fi a gap is routine; the break is counted and the
        verifier realigns, so the next good frame verifies again.
        """
        v = ChainVerifier()
        raw1, d1 = frame(READING, GENESIS)
        p1, h1 = split_frame(raw1)
        assert v.check(p1, h1) is True

        # Frame 2 is sent but never seen; frame 3 chains from it.
        _, d2 = frame(READING, d1)
        raw3, d3 = frame(READING, d2)
        p3, h3 = split_frame(raw3)
        assert v.check(p3, h3) is False
        assert v.breaks == 1

        raw4, _ = frame(READING, d3)
        p4, h4 = split_frame(raw4)
        assert v.check(p4, h4) is True
        assert v.breaks == 1

    def test_attaching_mid_stream_is_not_counted_as_a_break(self):
        """The bridge may connect long after the node booted."""
        v = ChainVerifier()
        raw, _ = frame(READING, b"\x11" * 32)
        payload, reported = split_frame(raw)
        assert v.check(payload, reported) is False
        assert v.breaks == 0

    def test_an_altered_payload_fails_verification(self):
        v = ChainVerifier()
        raw, _ = frame(READING)
        payload, reported = split_frame(raw)
        assert v.check(payload.replace(b"0.2130", b"0.9999"), reported) is False


class TestSnapshot:
    def _bridge(self):
        return RigBridge(host="127.0.0.1")

    def test_reports_unavailable_before_any_frame(self):
        s = self._bridge().snapshot()
        assert s["source"] == "UNAVAILABLE"
        assert s["reading"] is None
        assert s["scope"] == "SCALE_RIG"

    def test_reports_live_after_a_frame(self):
        b = self._bridge()
        raw, _ = frame(READING)
        b._on_message(None, None, _Msg(raw))
        s = b.snapshot()
        assert s["source"] == "LIVE"
        assert s["link"]["frames"] == 1
        assert s["reading"]["level_m"] == pytest.approx(0.213)
        assert s["reading"]["flow_lpm"] == pytest.approx(3.2)

    def test_a_quiet_node_goes_stale_rather_than_looking_current(self):
        b = self._bridge()
        raw, _ = frame(READING)
        b._on_message(None, None, _Msg(raw))
        b._received_at = time.time() - 60
        s = b.snapshot()
        assert s["source"] == "STALE"
        assert s["link"]["last_frame_age_s"] > 30

    def test_rig_values_are_never_converted_to_reservoir_values(self):
        """The tank is 400 mm deep and Idukki runs at 694-732 m MSL.

        If a scaling ever creeps in, the level here stops being a tank depth,
        and the dashboard starts showing a reservoir reading nobody measured.
        """
        b = self._bridge()
        raw, _ = frame(READING)
        b._on_message(None, None, _Msg(raw))
        r = b.snapshot()["reading"]
        assert r["level_m"] < 1.0
        assert "level_msl_m" not in r

    def test_actuator_disagreement_is_flagged(self):
        b = self._bridge()
        jammed = READING.replace('"gate_actual_pct":39.1', '"gate_actual_pct":12.0')
        raw, _ = frame(jammed)
        b._on_message(None, None, _Msg(raw))
        r = b.snapshot()["reading"]
        assert r["actuator_disagreement"] is True
        assert r["gate_commanded_pct"] == 40.0
        assert r["gate_verified_pct"] == 12.0

    def test_agreeing_gate_is_not_flagged(self):
        b = self._bridge()
        raw, _ = frame(READING)
        b._on_message(None, None, _Msg(raw))
        assert b.snapshot()["reading"]["actuator_disagreement"] is False

    def test_a_failed_sensor_prints_nan_and_must_not_lose_the_frame(self):
        """The firmware's snprintf emits a bare `nan` for a dead channel.

        That is not valid JSON. Dropping the whole frame would mean a single
        failed ultrasonic also hid the gate position and the flow - exactly
        when the fault demo needs them most.
        """
        b = self._bridge()
        raw, _ = frame(READING.replace('"ultrasonic_m":0.2140', '"ultrasonic_m":nan'))
        b._on_message(None, None, _Msg(raw))
        s = b.snapshot()
        assert s["link"]["malformed"] == 0
        assert s["reading"]["ultrasonic_m"] is None
        assert s["reading"]["pressure_m"] == pytest.approx(0.212)

    def test_garbage_is_counted_not_crashed_on(self):
        b = self._bridge()
        b._on_message(None, None, _Msg(b"not json at all"))
        s = b.snapshot()
        assert s["link"]["malformed"] == 1
        assert s["source"] == "UNAVAILABLE"

    def test_chain_mechanism_is_described_accurately(self):
        """It is a hash chain. Calling it a Merkle tree would be a lie."""
        s = self._bridge().snapshot()
        assert "Merkle" in s["audit_chain"]["mechanism"]
        assert "not a Merkle tree" in s["audit_chain"]["mechanism"]
