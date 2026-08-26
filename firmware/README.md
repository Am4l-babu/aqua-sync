# Firmware

ESP32 nodes for the AquaSync scale rig and field deployment.

| Node | Role | Status |
|---|---|---|
| `node_reservoir/` | Level sensing, sensor fusion, sluice gate control, telemetry | Skeleton complete, untested on hardware |
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

## Design notes

**Two sensors, different physics.** Ultrasonic time-of-flight and hydrostatic
pressure fail differently and for different reasons. Two ultrasonic sensors
that agree tell you nothing; they fail together. The Kalman filter fuses them,
and their disagreement is the fault signal.

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
