/**
 * Bench test 6 of 6: YF-S201 hall-effect flow sensor.
 *
 * Wiring: Red -> 5V   Black -> GND   Yellow (pulse) -> GPIO27
 * (hardware interrupt pin, INPUT_PULLUP - matches main.cpp exactly)
 *
 * The conversion below is copied verbatim from publishTelemetry() in
 * main.cpp: pulses-per-second times FLOW_LITRES_PER_PULSE times 60,000 ms
 * gives litres per minute. YF-S201's own datasheet constant is 450 pulses
 * per litre, already in config.h - this bench test hardcodes the same
 * number so a mismatch between the two would show up as a wrong reading
 * here, not just in the field.
 *
 * Pass criteria:
 *   - Zero flow at rest reads 0.00 L/min, not a small nonzero drift (a
 *     hall sensor with a stuck or slowly-drifting magnet reads a phantom
 *     trickle - worth catching now, not after the pump is plumbed in).
 *   - Blow through it or run it under a tap: the reading responds within
 *     about a second and settles at a plausible number for the flow you
 *     are actually pushing through - the sensor's own rated range is
 *     1-30 L/min; well outside that, expect a poor reading, not a fault.
 *   - Total pulses only ever increases. A count that resets or jumps
 *     backwards means a floating/noisy interrupt line, not a real pulse
 *     train - check the pull-up and a stable 5V supply to the sensor.
 */
#include <Arduino.h>

constexpr uint8_t PIN_FLOW = 27;
constexpr float FLOW_LITRES_PER_PULSE = 1.0f / 450.0f;  // YF-S201 nominal
constexpr uint32_t SAMPLE_MS = 1000;

volatile uint32_t g_pulses = 0;

void IRAM_ATTR onFlowPulse() { g_pulses++; }

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("=== AquaSync bench test 6/6: YF-S201 flow sensor ===");
  pinMode(PIN_FLOW, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_FLOW), onFlowPulse, RISING);
}

void loop() {
  static uint32_t last_pulses = 0;
  static unsigned long last_sample = 0;

  const unsigned long now = millis();
  if (now - last_sample < SAMPLE_MS) return;
  last_sample = now;

  const uint32_t pulses = g_pulses;  // volatile read, single access
  const uint32_t delta = pulses - last_pulses;
  last_pulses = pulses;

  const float flow_lpm = delta * FLOW_LITRES_PER_PULSE * (60000.0f / SAMPLE_MS);
  Serial.printf("total_pulses=%6u  delta=%3u  flow=%.2f L/min\n",
                pulses, delta, flow_lpm);
}
