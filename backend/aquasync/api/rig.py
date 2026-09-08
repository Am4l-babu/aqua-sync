"""Bridge the scale rig's MQTT telemetry into the API.

The firmware has published to `aquasync/reservoir/01/telemetry` since the
node was written, and until now nothing on this side subscribed. The two
halves of the system have never been connected.

Three things this module refuses to do, all for the same reason:

1. **It does not convert rig readings into reservoir readings.** The tank is
   400 mm deep; Idukki runs between 694 and 732 m MSL. Those numbers share a
   unit and nothing else, and quietly scaling one onto the other would put a
   fabricated reservoir level on a dashboard that a judge is being invited to
   trust. Every rig value carries `scope: "SCALE_RIG"` and its own units.

2. **It does not report a stale frame as live.** If the node goes quiet the
   state says so, with the age in seconds, rather than leaving the last
   reading on screen looking current.

3. **It does not claim the hash chain proves more than it does.** The firmware
   chains each record to its predecessor, so a break means the frames this
   bridge saw are not a contiguous run of the frames the node sent. That is
   *either* a dropped packet *or* an altered record, and over lossy Wi-Fi it
   is almost always the former. The count is reported; the interpretation is
   left to a human.

Enabled only when `AQUASYNC_MQTT_HOST` is set, so the offline demo stays
offline by default.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# The node considers itself alive at 1 Hz (TELEMETRY_INTERVAL_MS in config.h),
# so three missed frames is a generous definition of "gone quiet".
STALE_AFTER_S = 3.5

GENESIS = b"\x00" * 32

# The firmware builds its JSON with snprintf and %.4f, which emits a bare
# `nan` for a failed sensor. That is not valid JSON and json.loads rejects it,
# so a dropped ultrasonic reading would otherwise take the whole frame down.
# Rewriting it to null keeps the rest of the frame usable and surfaces the
# failed channel as missing, which is what it is.
_NAN = re.compile(rb"(?<=:)\s*-?nan", re.IGNORECASE)
_INF = re.compile(rb"(?<=:)\s*-?inf", re.IGNORECASE)


def split_frame(raw: bytes) -> tuple[bytes, str] | None:
    """Return the exact `data` bytes and the reported hash.

    The payload must be sliced out of the wire bytes rather than re-serialised
    from the parsed object: the firmware hashed the characters it printed, so
    round-tripping through a JSON encoder changes the spacing and float
    formatting and every hash check would fail.
    """
    start = raw.find(b'"data":')
    if start < 0:
        return None
    i = raw.find(b"{", start)
    if i < 0:
        return None

    depth, in_str, esc = 0, False, False
    for j in range(i, len(raw)):
        c = raw[j : j + 1]
        if in_str:
            if esc:
                esc = False
            elif c == b"\\":
                esc = True
            elif c == b'"':
                in_str = False
            continue
        if c == b'"':
            in_str = True
        elif c == b"{":
            depth += 1
        elif c == b"}":
            depth -= 1
            if depth == 0:
                payload = raw[i : j + 1]
                m = re.search(rb'"hash"\s*:\s*"([0-9a-fA-F]{64})"', raw[j:])
                return payload, (m.group(1).decode() if m else "")
    return None


@dataclass
class ChainVerifier:
    """Follows the firmware's SHA-256 record chain.

    `hash_n = SHA256(hash_(n-1) || payload_n)`, seeded with 32 zero bytes -
    see `appendAuditRecord` in firmware/node_reservoir/src/main.cpp.
    """

    prev: bytes = GENESIS
    breaks: int = 0
    verified: int = 0
    started: bool = False

    def check(self, payload: bytes, reported: str) -> bool:
        if not reported:
            return False
        digest = hashlib.sha256(self.prev + payload).digest()
        ok = digest.hex() == reported.lower()

        if ok:
            self.verified += 1
            self.prev = digest
            self.started = True
            return True

        # The node reboots from the genesis hash and this bridge may attach
        # mid-stream, so the first mismatch is expected rather than alarming.
        # Resynchronise to what was reported so one gap does not condemn every
        # frame after it, and count it.
        if self.started:
            self.breaks += 1
        self.prev = bytes.fromhex(reported)
        self.started = True
        return False


@dataclass
class RigBridge:
    """Subscribes to the node and keeps the most recent frame."""

    host: str
    port: int = 1883
    topic: str = "aquasync/reservoir/01/telemetry"

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _frame: dict[str, Any] | None = None
    _received_at: float = 0.0
    _chain: ChainVerifier = field(default_factory=ChainVerifier)
    _frames: int = 0
    _malformed: int = 0
    _connected: bool = False
    _client: Any = None

    def start(self) -> bool:
        """Connect in the background. False if paho or the broker is absent."""
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            log.info("paho-mqtt not installed; rig bridge disabled")
            return False

        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.on_message = self._on_message
            client.connect_async(self.host, self.port, keepalive=10)
            client.loop_start()
        except Exception as exc:  # noqa: BLE001 - a missing broker must not stop the API
            log.warning("rig bridge could not start: %s", exc)
            return False

        self._client = client
        return True

    def stop(self) -> None:
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None

    # ------------------------------------------------------------ callbacks
    def _on_connect(self, client, _userdata, _flags, reason_code, _props=None) -> None:
        ok = getattr(reason_code, "is_failure", False) is False
        self._connected = bool(ok)
        if ok:
            client.subscribe(self.topic, qos=0)
            log.info("rig bridge subscribed to %s", self.topic)

    def _on_disconnect(self, *_args, **_kwargs) -> None:
        self._connected = False

    def _on_message(self, _client, _userdata, msg) -> None:
        parts = split_frame(msg.payload)
        if parts is None:
            with self._lock:
                self._malformed += 1
            return
        payload, reported = parts

        cleaned = _INF.sub(b" null", _NAN.sub(b" null", payload))
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            with self._lock:
                self._malformed += 1
            return

        chain_ok = self._chain.check(payload, reported)
        with self._lock:
            self._frame = data
            self._frame["_chain_ok"] = chain_ok
            self._received_at = time.time()
            self._frames += 1

    # --------------------------------------------------------------- output
    def snapshot(self) -> dict[str, Any]:
        """The rig as the API reports it. Never empty, never pretends."""
        with self._lock:
            frame = dict(self._frame) if self._frame else None
            received_at = self._received_at
            frames, malformed = self._frames, self._malformed
            connected = self._connected
            verified, breaks = self._chain.verified, self._chain.breaks

        age = (time.time() - received_at) if received_at else None
        if frame is None:
            status = "connected, no frames yet" if connected else "no rig connected"
            source = "UNAVAILABLE"
        elif age is not None and age > STALE_AFTER_S:
            status = "node has gone quiet"
            source = "STALE"
        else:
            status = "receiving"
            source = "LIVE"

        out: dict[str, Any] = {
            "scope": "SCALE_RIG",
            "source": source,
            "status": status,
            "broker": f"{self.host}:{self.port}",
            "topic": self.topic,
            "link": {
                "broker_connected": connected,
                "frames": frames,
                "malformed": malformed,
                "last_frame_age_s": round(age, 2) if age is not None else None,
            },
            "audit_chain": {
                "mechanism": "SHA-256 record chain (not a Merkle tree)",
                "verified": verified,
                "breaks": breaks,
                "note": "a break means the frames seen here are not contiguous - "
                        "a dropped packet or an altered record, indistinguishable",
            },
            "reading": None,
        }
        if frame is None:
            return out

        gate_cmd = frame.get("gate_cmd_pct")
        gate_act = frame.get("gate_actual_pct")
        disagree = (
            isinstance(gate_cmd, (int, float))
            and isinstance(gate_act, (int, float))
            and abs(gate_cmd - gate_act) > 5.0
        )

        out["reading"] = {
            "node": frame.get("node"),
            "uptime_s": frame.get("uptime_s"),
            # Tank depth. Deliberately not converted to anything basin-scale.
            "level_m": frame.get("level_m"),
            "level_variance": frame.get("variance"),
            "ultrasonic_m": frame.get("ultrasonic_m"),
            "pressure_m": frame.get("pressure_m"),
            "temp_c": frame.get("temp_c"),
            "sensors_agree": frame.get("sensors_agree"),
            "flow_lpm": frame.get("flow_lpm"),
            "gate_commanded_pct": gate_cmd,
            "gate_verified_pct": gate_act,
            "gate_homed": frame.get("gate_homed"),
            "gate_jammed": frame.get("gate_jammed"),
            "actuator_disagreement": disagree,
            "frame_chain_ok": frame.get("_chain_ok"),
        }
        return out


def from_env() -> RigBridge | None:
    """Build a bridge from the environment, or None if none is configured."""
    host = os.environ.get("AQUASYNC_MQTT_HOST")
    if not host:
        return None
    return RigBridge(
        host=host,
        port=int(os.environ.get("AQUASYNC_MQTT_PORT", "1883")),
        topic=os.environ.get(
            "AQUASYNC_RIG_TOPIC", "aquasync/reservoir/01/telemetry"
        ),
    )
