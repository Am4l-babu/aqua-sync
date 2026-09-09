/**
 * Bench test 3 of 6: DS18B20 waterproof temperature probe.
 *
 * Wiring (1-Wire, config.h PIN_TEMP_1WIRE = GPIO4):
 *   Red (VCC) -> 3V3     Black (GND) -> GND     Yellow (DATA) -> GPIO4
 *   4.7k pull-up resistor from DATA to 3V3 - BOM item 21 calls this out by
 *   name because the probe reads garbage (or a fixed -127.00 C) without it.
 *
 * Why this one is "not optional" (config.h's own words): the speed of sound
 * used to convert the ultrasonic echo time into a distance drifts about
 * 0.6 m/s per degree C. Skip this probe and every ultrasonic reading in
 * bench test 2 carries an uncorrected, silent temperature bias.
 *
 * Pass criteria:
 *   - Reads a plausible room temperature at power-on (not -127.00, which
 *     means "no probe found" - check the pull-up and the DATA wire first).
 *   - Breathe on it or hold it briefly: the reading rises within a few
 *     seconds and settles back down. A number that never moves at all is
 *     as suspicious as one that reads -127.
 *   - Submerge it: no discontinuity or NaN at the moment it goes underwater.
 */
#include <Arduino.h>
#include <DallasTemperature.h>
#include <OneWire.h>

constexpr uint8_t PIN_TEMP_1WIRE = 4;

OneWire oneWire(PIN_TEMP_1WIRE);
DallasTemperature sensors(&oneWire);

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("=== AquaSync bench test 3/6: DS18B20 ===");
  sensors.begin();

  const uint8_t count = sensors.getDeviceCount();
  Serial.printf("1-Wire devices found: %u\n", count);
  if (count == 0) {
    Serial.println(
        "NONE FOUND - check the 4.7k pull-up (GPIO4 to 3V3) and that DATA "
        "is on GPIO4, not VCC or GND by mistake.");
  }
}

void loop() {
  sensors.requestTemperatures();
  const float c = sensors.getTempCByIndex(0);

  if (c == DEVICE_DISCONNECTED_C || c < -50.0f || c > 80.0f) {
    Serial.printf("FAULT reading: %.2f C - probe missing or pull-up absent\n", c);
  } else {
    Serial.printf("%.2f C  (%.2f F)\n", c, c * 9.0f / 5.0f + 32.0f);
  }
  delay(750);  // DS18B20 conversion time at default 12-bit resolution
}
