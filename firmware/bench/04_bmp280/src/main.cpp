/**
 * Bench test 4 of 6: BMP280 barometric pressure sensor.
 *
 * This is squall pre-detection (a falling-pressure trend), NOT the missing
 * hydrostatic water-level transducer discussed in firmware/bench/README.md -
 * BMP280 reads AIR pressure over an I2C bus (0.3-1.1 bar), not water column
 * pressure over a 0-5V analog line. The two are unrelated sensors solving
 * unrelated problems; do not let a "pressure sensor works" result here be
 * read as "the level-fusion sensor works". It is not wired into
 * node_reservoir's level estimate at all.
 *
 * Wiring (I2C): VCC -> 3V3   GND -> GND   SCL -> GPIO22   SDA -> GPIO21
 * (ESP32-WROOM-32 DevKit default I2C pins. main.cpp's comment "NOT 21 -
 * that is I2C SDA" about the gate DIR pin is exactly why this module and
 * the gate driver must never compete for the same pin.)
 *
 * Pass criteria:
 *   - "found at 0x76" or "0x77" prints at boot (module-dependent address).
 *   - Pressure reads roughly 900-1013 hPa at Kerala's typical elevations
 *     (adjust for your actual altitude - this is not a tight tolerance
 *     check, just "is it a plausible atmospheric number").
 *   - Cup your hand over it and blow gently: pressure should tick up
 *     briefly, proving it responds to a real change rather than returning
 *     a cached constant.
 */
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_BMP280.h>

Adafruit_BMP280 bmp;

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("=== AquaSync bench test 4/6: BMP280 ===");

  Wire.begin();  // SDA=21, SCL=22 by default on this board
  if (!bmp.begin(0x76) && !bmp.begin(0x77)) {
    Serial.println(
        "NOT FOUND at 0x76 or 0x77 - check SDA/SCL wiring and that this is "
        "a BMP280, not a BME280 (different default address behaviour) or a "
        "BMP180 (different library entirely).");
    return;
  }
  Serial.println("BMP280 found");
  bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,
                   Adafruit_BMP280::SAMPLING_X2,
                   Adafruit_BMP280::SAMPLING_X16,
                   Adafruit_BMP280::FILTER_X16,
                   Adafruit_BMP280::STANDBY_MS_500);
}

void loop() {
  const float hpa = bmp.readPressure() / 100.0f;
  const float temp_c = bmp.readTemperature();
  Serial.printf("pressure=%7.2f hPa   die_temp=%5.1f C\n", hpa, temp_c);
  delay(1000);
}
