# Bench test procedure

One standalone PlatformIO project per component, so a fault shows up on the
desk — not inside a rig that is already glued and full of water. This is
[ACTION_PLAN.md](../../ACTION_PLAN.md)'s "test each component alone before
assembly" step, made concrete.

Each subfolder is a complete, independent project:

```bash
cd firmware/bench/02_ultrasonic
pio run -t upload -e esp32dev
pio device monitor
```

Do them in order. Each one either shares a pin with, or is a prerequisite
for trusting, the one after it.

## ⚠️ Read this before wiring anything to GPIO36

**There is no bench test here for the water-pressure sensor `main.cpp`
depends on, because the V1 BOM does not include one.** `readPressureDepth()`
in [`node_reservoir/src/main.cpp`](../node_reservoir/src/main.cpp) reads
`PIN_PRESSURE` (GPIO36) expecting a 0–5 V hydrostatic transducer, and uses it
to **seed the entire boot-time level estimate** and as the **more trustworthy
fallback** whenever it disagrees with the ultrasonic reading. That
transducer is a `hardware/bom/bom.html` **V3** line item (₹1,800,
"Hydrostatic level transmitter... Independent physics → real sensor
fusion") — the BOM's own words say plainly that genuine sensor fusion needs
it, and V1 does not have it.

Left as-is, GPIO36 floats. A floating ESP32 ADC pin does not fail loudly —
it can land inside the plausible 0–0.45 m range from RF/PWM noise alone, so
the firmware's `pr_ok` check can pass on nothing, and `sensors_agree` can
flip on its own with no fault switch touched. That directly undermines the
one demo beat everyone is counting on. **Do not wire anything to GPIO36
until this is resolved** — see the open question logged in
[PROGRESS.md](../../PROGRESS.md) under Hardware (V1 rig).

None of the six tests below touch that pin. They cover everything that *is*
in the V1 kit.

## Before any of this: set the LM2596

Multimeter only, no firmware, no ESP32 connected yet.

1. Power the LM2596 from the 12 V 5 A adapter (BOM item 10), input side only.
2. Multimeter on its output terminals.
3. Turn the trim pot until it reads **5.00 V**, not "close enough."
4. Only then connect anything 3.3 V/5 V-side — the ESP32, sensors, the A4988
   logic rail — to its output.

An unregulated or mis-set buck converter is the single fastest way to lose
a ₹450 board on day one.

## The six tests

| # | Folder | Covers | Needs |
|---|---|---|---|
| 1 | [`01_esp32_selftest/`](01_esp32_selftest/) | The board, the USB cable, Wi-Fi | Nothing wired |
| 2 | [`02_ultrasonic/`](02_ultrasonic/) | JSN-SR04T *and* HC-SR04 (same protocol) | Trig/echo + the 3.3 V divider on ECHO |
| 3 | [`03_ds18b20/`](03_ds18b20/) | The 1-Wire temperature probe | The 4.7 kΩ pull-up — BOM calls this out by name |
| 4 | [`04_bmp280/`](04_bmp280/) | Barometric squall pre-detection | I2C wiring; **needs internet once** to fetch its library |
| 5 | [`05_stepper_gate/`](05_stepper_gate/) | NEMA 17 + A4988 + both limit switches | The mechanism off the tank, on open bench |
| 6 | [`06_flow_sensor/`](06_flow_sensor/) | YF-S201 pulse counting | 5 V + a pull-up on the interrupt line |

Each project's `src/main.cpp` carries its own wiring diagram, pass/fail
criteria and — where it matters — a pointer to which `config.h` constant it
is standing in for. None of the numbers here are new: they are copied from
`node_reservoir`'s own source so a bench pass means what it says.

## Test 4 is not test-for-the-missing-sensor

BMP280 reads **air** pressure over **I2C** for squall pre-detection. It has
nothing to do with the missing **water-column** pressure transducer on an
**analog** line above. A pass on test 4 says nothing about the sensor-fusion
gap — see the warning at the top of this file.

## After all six pass

Wiring the tested parts into `node_reservoir`'s real firmware and flashing
it as one node is Thursday's task in `ACTION_PLAN.md`, not this one. Keep
these bench projects around — they are the fastest way to isolate a fault
that shows up later during assembly.
