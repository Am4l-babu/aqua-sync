/**
 * Bench test 5 of 6: NEMA 17 + A4988 + two limit switches.
 *
 * This is the one component where a bench failure mode (a motor that never
 * reaches a limit switch) is exactly the failure mode the real firmware is
 * designed to refuse to operate through - homeGate() in main.cpp gives up
 * after HOMING_MAX_STEPS and sets `jammed = true` rather than guessing a
 * position. This sketch mirrors that logic exactly, standalone, so the
 * mechanism is proven before it is asked to run unattended in the rig.
 *
 * Wiring (config.h / main.cpp pin map):
 *   A4988 STEP  -> GPIO19        A4988 DIR -> GPIO25 (NOT 21 - that's I2C SDA)
 *   A4988 ENABLE-> GPIO23 (active LOW - driver is ON when this pin is LOW)
 *   Limit CLOSED-> GPIO34 (input only, external pull-up to 3V3)
 *   Limit OPEN  -> GPIO35 (input only, external pull-up to 3V3)
 *   A4988 VMOT/GND -> the 12V rail (through the LM2596's INPUT side, not
 *   its regulated 5V output - the driver wants motor voltage, not logic
 *   voltage). A4988 logic VDD -> 3V3, logic GND -> ESP32 GND (shared
 *   ground with the 12V supply is required even though the two rails are
 *   different voltages).
 *
 * SET THE A4988 CURRENT LIMIT before the first move: with VMOT connected
 * and STEP idle, measure voltage at the driver's reference trim pot against
 * its GND, and multiply by 2 for the current in amps (the standard A4988
 * formula, Vref x 2 = current limit for 0.1 ohm sense resistors - check
 * yours). NEMA 17 4.2 kg-cm motors are typically ~1.0-1.2 A/phase; setting
 * this too high is how a A4988 dies on its first bench run.
 *
 * Pass criteria:
 *   1. HOMING finds the CLOSED switch within a few seconds and prints
 *      "homed". If it prints "JAMMED" instead, the motor is turning the
 *      wrong way (swap A/B or A4988 DIR wiring) or a limit switch is wired
 *      to the wrong pin.
 *   2. A commanded move to 50% travels smoothly, does not overshoot past
 *      either switch, and GATE_MAX_RATE_PCT_PER_S is visibly respected -
 *      it should take about 12.5 s to reach 50% at the real firmware's
 *      4%/s slew limit, not snap there instantly.
 *   3. Manually holding the OPEN switch closed while commanding further
 *      opening stops the motor immediately - the interlock, not a timer,
 *      is what is protecting the mechanism.
 */
#include <Arduino.h>

constexpr uint8_t PIN_GATE_STEP    = 19;
constexpr uint8_t PIN_GATE_DIR     = 25;
constexpr uint8_t PIN_GATE_ENABLE  = 23;
constexpr uint8_t PIN_LIMIT_CLOSED = 34;
constexpr uint8_t PIN_LIMIT_OPEN   = 35;

constexpr float STEPS_PER_PERCENT       = 18.0f;
constexpr uint32_t STEP_PULSE_US        = 3;
constexpr uint32_t STEP_INTERVAL_US     = 700;
constexpr int32_t HOMING_MAX_STEPS      = 4000;
constexpr float GATE_MAX_RATE_PCT_PER_S = 4.0f;

float g_actual_pct = 0.0f;
float g_target_pct = 0.0f;
bool  g_homed = false;
bool  g_jammed = false;
unsigned long g_last_move_ms = 0;

void oneStep() {
  digitalWrite(PIN_GATE_STEP, HIGH);
  delayMicroseconds(STEP_PULSE_US);
  digitalWrite(PIN_GATE_STEP, LOW);
  delayMicroseconds(STEP_INTERVAL_US);
}

bool homeGate() {
  Serial.println("homing to CLOSED limit ...");
  digitalWrite(PIN_GATE_DIR, LOW);
  digitalWrite(PIN_GATE_ENABLE, LOW);

  for (int32_t i = 0; i < HOMING_MAX_STEPS; i++) {
    if (digitalRead(PIN_LIMIT_CLOSED) == LOW) {
      g_actual_pct = 0.0f;
      g_homed = true;
      digitalWrite(PIN_GATE_ENABLE, HIGH);
      Serial.println("homed - CLOSED switch reached");
      return true;
    }
    oneStep();
  }
  g_jammed = true;
  digitalWrite(PIN_GATE_ENABLE, HIGH);
  Serial.println(
      "JAMMED - never reached CLOSED within HOMING_MAX_STEPS. Check motor "
      "direction (swap A4988 DIR sense or motor coil pair) and that the "
      "CLOSED limit switch is on GPIO34, not GPIO35.");
  return false;
}

void serviceGate(float dt_s) {
  if (!g_homed || g_jammed) return;

  const float max_delta = GATE_MAX_RATE_PCT_PER_S * dt_s;
  float delta = g_target_pct - g_actual_pct;
  delta = constrain(delta, -max_delta, max_delta);
  if (fabsf(delta) < 0.01f) return;

  if (delta > 0 && digitalRead(PIN_LIMIT_OPEN) == LOW) {
    Serial.println("OPEN limit reached - refusing to move further open");
    return;
  }
  if (delta < 0 && digitalRead(PIN_LIMIT_CLOSED) == LOW) {
    Serial.println("CLOSED limit reached - refusing to move further closed");
    return;
  }

  digitalWrite(PIN_GATE_DIR, delta > 0 ? HIGH : LOW);
  digitalWrite(PIN_GATE_ENABLE, LOW);

  const int32_t steps = fabsf(delta) * STEPS_PER_PERCENT;
  for (int32_t i = 0; i < steps; i++) oneStep();

  g_actual_pct += delta;
  digitalWrite(PIN_GATE_ENABLE, HIGH);
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("=== AquaSync bench test 5/6: stepper gate ===");
  Serial.println("Set the A4988 current limit BEFORE this line finishes -");
  Serial.println("see the comment block at the top of this file. 5 s to abort...");
  delay(5000);

  pinMode(PIN_GATE_STEP, OUTPUT);
  pinMode(PIN_GATE_DIR, OUTPUT);
  pinMode(PIN_GATE_ENABLE, OUTPUT);
  pinMode(PIN_LIMIT_CLOSED, INPUT);  // external pull-up per BOM/wiring note
  pinMode(PIN_LIMIT_OPEN, INPUT);
  digitalWrite(PIN_GATE_ENABLE, HIGH);  // driver off until homing starts

  if (!homeGate()) {
    Serial.println("Stopping here. Fix the jam before re-flashing.");
    while (true) delay(1000);
  }

  Serial.println("commanding a move to 50% open, at the real 4%/s slew limit ...");
  g_target_pct = 50.0f;
  g_last_move_ms = millis();
}

void loop() {
  const unsigned long now = millis();
  const float dt_s = (now - g_last_move_ms) / 1000.0f;
  if (dt_s < 0.05f) return;  // ~20 Hz service loop, same order as the real node
  g_last_move_ms = now;

  serviceGate(dt_s);

  static unsigned long last_print = 0;
  if (now - last_print >= 500) {
    last_print = now;
    Serial.printf("actual=%.1f%%  target=%.1f%%  CLOSED=%d OPEN=%d\n",
                  g_actual_pct, g_target_pct,
                  digitalRead(PIN_LIMIT_CLOSED), digitalRead(PIN_LIMIT_OPEN));
  }

  // Once it settles at 50%, walk back to fully closed, so the test ends in
  // a known, safe position rather than leaving the gate open on the bench.
  if (fabsf(g_actual_pct - g_target_pct) < 0.05f && g_target_pct > 0.0f) {
    Serial.println("reached 50% - returning to fully closed");
    g_target_pct = 0.0f;
  }
}
