# Firmware

ESP32 nodes for the AquaSync scale rig and field deployment.

> **The gate this firmware drives is the scale rig's model sluice.** AquaSync
> never operates a real dam gate. Kerala's gates are operated by KSEB and the
> district administration; there is no path from this firmware to them. The
> MQTT command topic is deliberately not subscribed on the API side, and the
> bridge in `aquasync.api.rig` is receive-only.

| Node | Role | Status |
|---|---|---|
| `node_reservoir/` | Level sensing, sensor fusion, **bench-rig** sluice gate control, telemetry | Skeleton complete, untested on hardware |
| `node_downstream/` | Downstream stage and flow, LoRa relay | Planned |

## Build

```bash
pip install platformio
cd firmware/node_reservoir
pio run -t upload
pio device monitor
```

Edit `src/config.h` before the first flash. `SENSOR_MOUNT_HEIGHT_M` must be
*measured*, not estimated - every depth reading is differenced against it.

**Test each part alone first.** [`firmware/bench/`](bench/) has six
standalone PlatformIO projects, one per sensor/actuator in the V1 BOM, each
with a wiring diagram and pass/fail criteria lifted from this firmware's own
constants. Flash and pass all six before wiring anything into
`node_reservoir` as one assembled node.

## Design notes

**Two sensors, different physics — on paper.** Ultrasonic time-of-flight and
hydrostatic pressure fail differently and for different reasons. Two
ultrasonic sensors that agree tell you nothing; they fail together. The
Kalman filter fuses them, and their disagreement is the fault signal.
⚠️ **The V1 BOM does not include the pressure transducer.** It is a V3 line
item (`hardware/bom/bom.html`, ₹1,800). Until that is resolved,
`PIN_PRESSURE` floats and must not be wired to anything — see
[`firmware/bench/README.md`](bench/README.md) for what that means and why
none of the six bench tests touch it.

**Temperature compensation is mandatory.** The speed of sound changes about
0.6 m/s per degree C - a ~2.5% range error across a 15 C day. That is
centimetres at rig scale and much worse at reservoir scale. The DS18B20 is
not an optional extra.

**The safety interlock runs below the network.** A hardcoded bounds check on
a hardware timer ISR overrides any commanded position. No cloud message, no
parser bug, and no crashed main loop can drive the gate somewhere unsafe.

**Homing failure means refusing to operate.** A stepper has no absolute
position feedback. If the gate cannot find its closed limit switch, its
position is unknown, and moving a gate whose position is unknown is worse
than not moving it.

## Two wiring traps

1. **Ultrasonic echo pins output 5 V.** The ESP32 is 3.3 V tolerant only. A
   divider on every echo line is mandatory.
2. **GPIO 34 and 35 are input-only with no internal pull-ups.** Limit
   switches wired there need external ones.

Full pin map: [`hardware/bom/README.md`](../hardware/bom/README.md).
