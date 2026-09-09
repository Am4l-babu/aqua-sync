/**
 * Bench test 2 of 6: JSN-SR04T and HC-SR04, one at a time.
 *
 * Same wiring for both (they share the trigger/echo protocol):
 *   TRIG -> PIN_TRIG   ECHO -> PIN_ECHO (through a divider - see below)
 *   VCC  -> 5V         GND  -> GND
 *
 * ECHO is a 5V signal on both sensors. The real node reads it on GPIO18,
 * which is NOT 5V-tolerant, through a resistor divider (main.cpp's comment:
 * "5V -> 3.3V divider REQUIRED"). Wire that divider now, on the bench, and
 * confirm it here - do not defer it to final assembly and discover a fried
 * GPIO after the tanks are glued.
 *
 * Pass criteria:
 *   - Hold a flat surface at a KNOWN distance (a book works) and confirm the
 *     printed distance is within +-1 cm of a tape measure, for both sensors.
 *   - JSN-SR04T only: submerge the transducer face-down in a bucket at a
 *     known depth and confirm the same +-1 cm - it is rated for direct
 *     underwater use, unlike the HC-SR04.
 *   - Move your hand from ~2 cm to ~4 m in front of the sensor and confirm
 *     the reading tracks smoothly, with no long stretches of "no echo".
 *
 * config.h's rig-scale range for the reservoir tank is 2-45 cm
 * (US_MIN_RANGE_M / US_MAX_RANGE_M) - this test intentionally reports the
 * sensor's own full native range instead, so a bench reading outside the
 * eventual tank geometry is not mistaken for a sensor fault.
 */
#include <Arduino.h>

constexpr uint8_t PIN_TRIG = 5;
constexpr uint8_t PIN_ECHO = 18;
constexpr unsigned long TIMEOUT_US = 30000UL;  // ~5 m round trip, generous
constexpr float SPEED_OF_SOUND_M_PER_S = 343.0f;  // 20C dry air, no temp probe yet

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("=== AquaSync bench test 2/6: ultrasonic (JSN-SR04T / HC-SR04) ===");
  Serial.println("Wire ECHO through the 3.3V divider before connecting it.");
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);
  digitalWrite(PIN_TRIG, LOW);
}

void loop() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);

  const unsigned long echo_us = pulseIn(PIN_ECHO, HIGH, TIMEOUT_US);

  if (echo_us == 0) {
    Serial.println("NO ECHO - check wiring, or target is out of range/too soft to reflect");
  } else {
    const float distance_m = (echo_us * 1e-6f * SPEED_OF_SOUND_M_PER_S) / 2.0f;
    Serial.printf("echo=%6lu us   distance=%6.3f m  (%.1f cm)\n",
                  echo_us, distance_m, distance_m * 100.0f);
  }
  delay(200);  // matches the ~5 Hz burst rate main.cpp uses per sample
}
