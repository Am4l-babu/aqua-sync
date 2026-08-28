# Bill of materials

Four build tiers. **V1 is the only one required** for a working expo
demonstration; V2–V4 are optional depth, and every one of them is a way to
lose. Read [Choosing a tier](#choosing-a-tier) before ordering anything.

Prices are indicative INR as of **August 2026**, sourced from Indian
vendor listings. They move; treat them as ±25% for budgeting.

## A note on the links

Component links in the planning conversations that seeded this project were
unreliable — the same Amazon ASIN (`B07DDKZ5KJ`) appeared as a breadboard, a
jumper wire set, a DHT22, a resistor kit and a multimeter. Those have not
been carried forward.

What is given here instead is the **exact part number and specification**,
which is what you actually search on, plus the vendor's stable search URL.
Product page URLs churn constantly on Indian electronics sites; part numbers
do not.

Vendors, in rough order of preference:

| Vendor | Best for | Search pattern |
|---|---|---|
| **Robu.in** | Sensors, ESP32/Pi boards, motors — genuine parts, fast | `https://robu.in/?s=<part>` |
| **ThinkRobotics** | Modules, cameras, Pi accessories | `https://thinkrobotics.com/search?q=<part>` |
| **ElectronicsComp** | Passives, ICs, cheap basics | `https://www.electronicscomp.com/catalogsearch/result/?q=<part>` |
| **Amazon.in / Flipkart** | Cables, batteries, enclosures, tanks | standard search |
| **Local market** (SP Road Bengaluru, Broadway Kochi) | Acrylic, plumbing, tools — cheaper and immediate | — |

---

## V1 — Hardware-in-the-loop scale rig  ·  ₹6,250  ·  1 week

The complete physical demonstrator: a two-tank recirculating model with a
motorised sluice gate, level sensing, and live telemetry to the twin.
**This alone is a strong expo build.**

| # | Component | Specification | Qty | ₹ ea | ₹ | Notes |
|---|---|---|---|---|---|---|
| 1 | ESP32-WROOM-32 DevKit | 38-pin, dual-core 240 MHz, Wi-Fi + BT | 1 | 450 | 450 | Get the 38-pin, not 30-pin — you need the extra ADC pins |
| 2 | JSN-SR04T v3.0 | Waterproof ultrasonic, 25–450 cm, ±1 cm | 1 | 550 | 550 | Separate transducer on a cable; survives splash |
| 3 | HC-SR04 | Ultrasonic 2–400 cm | 1 | 90 | 90 | Second tank, dry location |
| 4 | DS18B20 (waterproof probe) | 1-Wire, −55…125 °C, ±0.5 °C | 1 | 180 | 180 | **Not optional** — sound speed drifts 0.6 m/s per °C |
| 5 | BMP280 | Barometric, 300–1100 hPa, ±0.12 hPa | 1 | 150 | 150 | Squall pre-detection |
| 6 | NEMA 17 stepper | 42×42 mm, 1.8°, 4.2 kg·cm | 1 | 650 | 650 | Sluice gate |
| 7 | A4988 driver + heatsink | 1/16 microstep, 2 A | 1 | 130 | 130 | DRV8825 also fine |
| 8 | YF-S201 | Hall flow sensor, 1–30 L/min, G1/2" | 1 | 350 | 350 | Outflow measurement |
| 9 | 12 V submersible pump | 800–1000 L/h | 1 | 300 | 300 | Simulates inflow |
| 10 | 12 V 5 A adapter | Barrel jack | 1 | 450 | 450 | Steppers are hungry |
| 11 | LM2596 buck | 12 V→5 V, 3 A, adjustable | 1 | 120 | 120 | **Set to 5.0 V before connecting the ESP32** |
| 12 | Micro limit switches | SPDT lever | 2 | 40 | 80 | Gate end-stops; stepper has no position feedback |
| 13 | Acrylic sheet, 3 mm | 2 × (600×450 mm) | 2 | 450 | 900 | Two tanks + gate |
| 14 | Acrylic solvent cement | Dichloromethane, 50 ml | 1 | 200 | 200 | Local plastics shop |
| 15 | Silicone tubing + fittings | 8 mm ID, 2 m, elbows, clamps | 1 | 350 | 350 | |
| 16 | Perfboard + headers | 10×15 cm, assorted headers | 1 | 200 | 200 | |
| 17 | Jumper wires | M-M / M-F / F-F, 120 pc | 1 | 200 | 200 | |
| 18 | Breadboard | 830 point | 1 | 150 | 150 | |
| 19 | Micro-USB data cable | **Data**, not charge-only | 2 | 100 | 200 | Charge-only cables cost hours of debugging |
| 20 | IP65 enclosure | 150×100×60 mm | 1 | 350 | 350 | |
| 21 | Assorted R/C kit | 1/4 W resistors, ceramics | 1 | 200 | 200 | 4.7 kΩ needed for DS18B20 pull-up |
| | | | | **Total** | **₹6,250** | |

### Also needed if you do not already own them

| Tool | ₹ |
|---|---|
| Soldering iron, 25–40 W | 400 |
| Solder wire, 0.8 mm 100 g | 180 |
| Digital multimeter | 450 |
| Wire stripper | 200 |
| Hot glue gun | 250 |
| **Tools subtotal** | **₹1,480** |

### Wiring — ESP32 pin map

| Function | Part | ESP32 pin | Note |
|---|---|---|---|
| Reservoir level trig | JSN-SR04T | GPIO 5 | |
| Reservoir level echo | JSN-SR04T | GPIO 18 | 5 V→3.3 V divider **required** |
| Tailwater trig/echo | HC-SR04 | GPIO 17 / 16 | divider on echo |
| Water temperature | DS18B20 | GPIO 4 | 4.7 kΩ pull-up to 3.3 V |
| Barometric | BMP280 | I²C: SDA 21, SCL 22 | |
| Gate step / dir / enable | A4988 | GPIO 19 / 21 / 23 | 21 is shared with I²C SDA — **move dir to GPIO 25** |
| Gate limit switches | SPDT ×2 | GPIO 34, 35 | input-only pins, external pull-ups needed |
| Flow sensor | YF-S201 | GPIO 27 | hardware interrupt; 5 V→3.3 V divider |
| Pump relay | Relay/MOSFET | GPIO 26 | |

> **Two traps worth flagging.** Ultrasonic echo pins output 5 V and the
> ESP32 is 3.3 V tolerant only — a divider is not optional. And GPIO 34/35
> are input-only with no internal pull-ups, so limit switches need external
> ones.

---

## V2 — Off-grid resilience  ·  +₹2,300  ·  +1 week

Proves the system survives the conditions it is built for. **The highest-
value optional tier** — "what happens when the network dies?" is the
question this answers, and it is the one an IoT judge will ask.

| Component | Specification | Qty | ₹ ea | ₹ |
|---|---|---|---|---|
| SX1278 LoRa (Ra-02) | 433 MHz, SPI, ~5 km LoS | 2 | 450 | 900 |
| 433 MHz spring antenna | SMA / IPEX | 2 | 100 | 200 |
| MicroSD card module | SPI, with 8 GB card | 1 | 250 | 250 |
| INA219 | I²C current/voltage, ±3.2 A | 1 | 220 | 220 |
| 18650 cells + holder | 3.7 V 2600 mAh protected | 2 | 180 | 360 |
| TP4056 + protection | USB-C, 1 A | 1 | 90 | 90 |
| Active buzzer | 5 V piezo | 1 | 60 | 60 |
| 10 W solar panel | 12 V polycrystalline | 1 | 220 | 220 |
| | | | **Total** | **₹2,300** |

**433 MHz is the legal ISM band in India.** The 868 MHz modules widely
recommended online are the European allocation. Use 433 MHz.

INA219 earns its place: motor current is how you detect a jammed gate. A
stepper that misses steps against an obstruction draws a current signature
you can see, and a digital twin that cannot tell whether its actuator
actually moved is not a twin.

---

## V3 — Edge AI and better sensing  ·  +₹5,900  ·  +2 weeks

| Component | Specification | Qty | ₹ ea | ₹ | Why |
|---|---|---|---|---|---|
| ESP32-S3 DevKitC-1 | N16R8, vector ops | 1 | 900 | 900 | TFLite Micro at usable speed |
| ESP32-CAM + OV2640 | 2 MP | 1 | 600 | 600 | Reads a painted gauge; LSPIV surface velocity |
| ESP32-CAM-MB shield | CH340 programmer | 1 | 250 | 250 | Saves genuine pain |
| HLK-LD2410C | 24 GHz FMCW radar | 1 | 450 | 450 | Immune to fog, foam, spray, temperature |
| Hydrostatic level transmitter | 0–1 m, 4–20 mA or 0–5 V | 1 | 1,800 | 1,800 | Independent physics → real sensor fusion |
| INMP441 | I²S MEMS mic, 24-bit | 1 | 250 | 250 | Cavitation FFT |
| HX711 + 5 kg load cell | 24-bit ADC | 1 | 300 | 300 | Trash-rack blockage via differential head |
| MPU6050 | 6-axis IMU | 1 | 250 | 250 | Gate vibration signature |
| Micro hydro generator | F50-12V Pelton | 1 | 450 | 450 | Self-powering during storms |
| 4–20 mA receiver | 250 Ω precision + op-amp | 1 | 150 | 150 | For the transmitter |
| 3S BMS | 12 V Li-ion protection | 1 | 150 | 150 | |
| Misc PCB/connectors | | 1 | 350 | 350 | |
| | | | **Total** | **₹5,900** | |

The hydrostatic transmitter is the single most defensible purchase in this
tier. Two sensors measuring the same quantity through *different physics*
(time-of-flight vs. water column pressure) is what makes fault detection
possible. Two ultrasonic sensors that agree tell you nothing — they fail the
same way at the same time.

---

## V4 — Offline command post and bathymetry  ·  +₹9,900  ·  +3 weeks

Ambitious. Do not start this unless V1–V3 are finished and rehearsed.

| Component | Specification | Qty | ₹ ea | ₹ |
|---|---|---|---|---|
| Raspberry Pi 4B | 2 GB | 1 | 3,800 | 3,800 |
| Pi case + fan + PSU | official | 1 | 900 | 900 |
| MicroSD 32 GB | A1 Class 10 | 1 | 450 | 450 |
| NEO-6M GPS + antenna | UART | 1 | 700 | 700 |
| RC boat hull | 40–50 cm | 1 | 900 | 900 |
| Brushed motor + prop + shaft | 380/540 class | 1 | 500 | 500 |
| L298N | dual H-bridge | 1 | 200 | 200 |
| MG996R | metal-gear servo, rudder | 1 | 400 | 400 |
| LiPo 2S 2200 mAh | 7.4 V | 1 | 900 | 900 |
| LiPo balance charger | 2S–3S + LiPo-safe bag | 1 | 650 | 650 |
| Waterproofing | conformal coat, glands, silicone | 1 | 500 | 500 |
| | | | **Total** | **₹9,900** |

---

## Cumulative budget

**Corrected 28 Aug 2026:** the V1, V3 and V4 tier totals above did not
match the sum of their own line items (V1 was short by ₹100, V3 was over
by ₹1,000, V4 was short by ₹500) — caught while building an HTML version
of this BOM and recomputing every total from the actual rows instead of
trusting the stated ones. V2 and the tools subtotal were already correct.
The figures below are the corrected sums.

| Tier | Adds | Running total | Cumulative weeks |
|---|---|---|---|
| Tools (if needed) | 1,480 | 1,480 | — |
| **V1** | 6,250 | **7,730** | 1 |
| V2 | 2,300 | 10,030 | 2 |
| V3 | 5,900 | 15,930 | 4 |
| V4 | 9,900 | 25,830 | 7 |

Software, data, and hosting: **₹0**. Every dependency is open source and
every data source is free.

Consumables not itemised: filament if 3D printing the gate (≈₹300 of PETG),
poster printing (₹300–500 for A1), and a spare ESP32, which you will need.

---

## Choosing a tier

**The default answer is V1 + V2, and stop.**

The strongest version of this project is a *flawless* V1 rig driving a
digital twin that has been validated against real 2021 dam data, presented
by someone who understands every line of it. The failure mode that actually
loses competitions is a table of half-working V3 and V4 hardware with no
time left to rehearse.

Concretely:

| Situation | Build |
|---|---|
| Solo, or under 4 weeks | **V1 only.** Put every remaining hour into the twin and the demo. |
| Solo with 6+ weeks | **V1 + V2.** Off-grid failover is a complete story on its own. |
| 3–4 people, 8+ weeks, one dedicated to hardware | V1 + V2 + *one* V3 item — the hydrostatic transmitter, for genuine sensor fusion |
| Everything already works and is rehearsed | V4 |

Order V1 first and start building while V2 ships. Indian vendor delivery is
3–5 days; do not sequence the build so that a ₹90 part blocks a demo.

---

## Reference: a real deployed design, not a tier to buy

Found 28 August 2026 while checking ICFOSS's (Kerala's state FOSS body)
GitLab for prior art. This is not another BOM tier — it is a **working,
MIT-licensed, non-contact water-level station** that has actually been
built and documented, worth reading before extending V1 toward a real
field deployment rather than a tabletop demo.

**[`icfoss/OpenIoT/c1_dev_lorawan_automatic_level_monitoring_station`](https://gitlab.com/icfoss/OpenIoT/c1_dev_lorawan_automatic_level_monitoring_station)**

| | This project's V1 | ICFOSS's design |
|---|---|---|
| Level sensor | JSN-SR04T ultrasonic, 25–450 cm | Vega Puls C11 radar, 8 m range, non-contact |
| Telemetry | Wi-Fi (ESP32) | LoRaWAN (C1-Dev board, Murata CMWX1ZZABZ-091) |
| Power | Mains adapter | 100 W solar + 50 Ah Li-ion, MPPT charge controller |
| Payload | Level + temperature | Level, 16-reading history, rate of change, solar/battery voltage and current |
| Range | Tabletop, tethered | Field-deployable, kilometres via LoRaWAN |

The two designs are solving different problems on purpose — V1 above is
built to be cheap, buildable in a week, and demonstrate the *twin*, not the
*sensor network*. But this is exactly the kind of hardware `docs/validation.md`
and `ROADMAP.md` name as the fix for the biggest data-layer gap in the
project: real reservoirs report on a **daily** bulletin, and the routing
calibration attempt (`scripts/routing_calibration.py`) failed specifically
because daily data cannot resolve an 8-hour travel time (see
`docs/validation.md` §"River routing"). A radar level station reporting
every few minutes over LoRaWAN, at either Idukki or a downstream point like
Neeleeswaram, is a plausible real answer to that gap - not a V1 expo
prop, but worth a look if this project ever moves toward an actual
utility pilot rather than a demonstration rig.

ICFOSS's OpenIoT group has several related designs worth the same kind of
look if that direction is pursued: `Water_Quality_Monitoring_Device` and
`Aquasentinals` (same STM32 + LoRaWAN + ChirpStack + Grafana telemetry
stack, different sensors - pH/dissolved oxygen/temperature), and
`flood-monitoring-technopark` (a deployed reference for the alerting and
dashboard side - LoRaWAN sensors on the Thettiyar canal at Technopark,
React/Node/MongoDB, threshold-based SMS/email alerts).
