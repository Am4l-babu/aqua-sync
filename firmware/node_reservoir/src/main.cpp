/**
 * AquaSync reservoir node - ESP32 firmware for the scale rig and field node.
 *
 * Reads reservoir level, fuses two independent sensors, drives the sluice
 * gate, and publishes telemetry. Four design decisions are worth explaining,
 * because they are what separate this from a sensor demo:
 *
 * 1. TWO SENSORS, DIFFERENT PHYSICS - WHEN BOTH ARE PRESENT.  Ultrasonic
 *    time-of-flight and hydrostatic pressure fail in different ways for
 *    different reasons. Two ultrasonic sensors that agree tell you nothing -
 *    they fail together. A Kalman filter fuses them; their disagreement is
 *    the fault signal. The V1 BOM does not include the pressure transducer
 *    (it is a V3 item - see config.h's HAS_PRESSURE_SENSOR), so as shipped
 *    this node runs on ultrasonic alone, honestly: readPressureDepth()
 *    returns NAN rather than trusting a floating ADC pin, and no code path
 *    downstream of that treats NAN pressure as a valid measurement.
 *
 * 2. TEMPERATURE COMPENSATION IS NOT OPTIONAL.  The speed of sound changes
 *    about 0.6 m/s per degree C. Across a 15 C day that is a ~2.5% range
 *    error - centimetres at rig scale, and far worse at reservoir scale.
 *
 * 3. THE SAFETY INTERLOCK RUNS BELOW THE NETWORK.  A hardcoded check on a
 *    hardware timer overrides any commanded gate position. No cloud message,
 *    no parser bug and no crashed main loop can drive the gate somewhere
 *    physically unsafe.
 *
 * 4. DEGRADATION IS STAGED, NOT ALL BUILT YET.  Wi-Fi/MQTT is what runs
 *    today; a LoRa and then a local-SD fallback are the design (see the
 *    TODO(phase-4) at the one call site that would use them), not yet
 *    implemented. Losing MQTT currently falls back to printing the frame
 *    to serial, which is the honest interim behaviour, not the finished
 *    three-rung ladder this comment used to claim as built.
 *
 * Target: ESP32-WROOM-32 (38-pin). Build with PlatformIO.
 */

#include <Arduino.h>
#include <DallasTemperature.h>
#include <OneWire.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <mbedtls/sha256.h>

#include "config.h"

// ---------------------------------------------------------------------------
// pin map  (see hardware/bom/README.md for the full table)
// ---------------------------------------------------------------------------

constexpr uint8_t PIN_US_TRIG      = 5;
constexpr uint8_t PIN_US_ECHO      = 18;   // 5V -> 3.3V divider REQUIRED
constexpr uint8_t PIN_PRESSURE     = 36;   // ADC1_CH0, input only
constexpr uint8_t PIN_TEMP_1WIRE   = 4;    // 4.7k pull-up to 3V3
constexpr uint8_t PIN_GATE_STEP    = 19;
constexpr uint8_t PIN_GATE_DIR     = 25;   // NOT 21 - that is I2C SDA
constexpr uint8_t PIN_GATE_ENABLE  = 23;
constexpr uint8_t PIN_LIMIT_CLOSED = 34;   // input only, external pull-up
constexpr uint8_t PIN_LIMIT_OPEN   = 35;   // input only, external pull-up
constexpr uint8_t PIN_FLOW         = 27;   // hardware interrupt

// ---------------------------------------------------------------------------
// state
// ---------------------------------------------------------------------------

struct LevelEstimate {
  // level_m is read by the interlock ISR while updateLevelEstimate writes it.
  volatile float level_m = 0.0f;   // fused estimate
  float variance     = 1.0f;   // filter covariance
  float ultrasonic_m = 0.0f;   // raw
  float pressure_m   = 0.0f;   // raw
  float water_temp_c = 25.0f;
  bool  sensors_agree = true;
};

struct GateState {
  // commanded_pct is written by the safety interlock (timer ISR), by the MQTT
  // command handler and by homing, and read by driveGate. volatile stops the
  // compiler caching it across those contexts; the portMUX below makes the
  // read-modify-write in driveGate atomic against the ISR.
  volatile float commanded_pct = 0.0f;
  float   actual_pct    = 0.0f;
  int32_t position_steps = 0;
  bool    homed         = false;
  bool    jammed        = false;
};

static LevelEstimate g_level;
static GateState     g_gate;

// Guards the gate setpoint against the 10 Hz interlock ISR.
static portMUX_TYPE  g_gate_mux = portMUX_INITIALIZER_UNLOCKED;
static volatile uint32_t g_flow_pulses = 0;
static uint8_t g_prev_hash[32] = {0};

OneWire oneWire(PIN_TEMP_1WIRE);
DallasTemperature tempSensor(&oneWire);
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

// ---------------------------------------------------------------------------
// sensing
// ---------------------------------------------------------------------------

void IRAM_ATTR onFlowPulse() { g_flow_pulses++; }

/**
 * Speed of sound in air, corrected for temperature.
 *
 * The only thermometer on this node is the DS18B20, and it is in the water.
 * The ultrasonic pulse travels through the air above it, so what gets passed
 * here is a proxy, not the air temperature. The error is bounded and small:
 * the coefficient is 0.606 m/s per degree against roughly 346 m/s, so even a
 * 5 degree air-water difference is about 0.9% of the speed - under 4 mm over
 * this tank's 400 mm range. Worth knowing, not worth a second sensor, and
 * worth saying out loud rather than letting the parameter name imply a
 * measurement nobody takes.
 */
static inline float speedOfSound(float temp_c) {
  return 331.3f + 0.606f * temp_c;
}

/**
 * Single ultrasonic range reading, in metres of water depth.
 * Returns NAN on timeout so a missed echo never reads as zero depth -
 * which the filter would otherwise interpret as an empty reservoir.
 */
float readUltrasonic(float air_temp_c) {
  digitalWrite(PIN_US_TRIG, LOW);
  delayMicroseconds(4);
  digitalWrite(PIN_US_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_US_TRIG, LOW);

  const unsigned long echo_us = pulseIn(PIN_US_ECHO, HIGH, ULTRASONIC_TIMEOUT_US);
  if (echo_us == 0) return NAN;

  const float distance_m = (echo_us * 1e-6f * speedOfSound(air_temp_c)) / 2.0f;
  if (distance_m < US_MIN_RANGE_M || distance_m > US_MAX_RANGE_M) return NAN;

  return SENSOR_MOUNT_HEIGHT_M - distance_m;   // distance to surface -> depth
}

/** Median of N samples: rejects the single-ping dropouts these sensors give. */
float readUltrasonicMedian(float air_temp_c, uint8_t n = 5) {
  float s[9];
  uint8_t valid = 0;
  for (uint8_t i = 0; i < n && i < 9; i++) {
    const float v = readUltrasonic(air_temp_c);
    if (!isnan(v)) s[valid++] = v;
    delay(35);   // below ~30 Hz the previous burst still echoes
  }
  if (valid == 0) return NAN;

  for (uint8_t i = 1; i < valid; i++) {          // insertion sort, tiny n
    const float k = s[i];
    int8_t j = i - 1;
    while (j >= 0 && s[j] > k) { s[j + 1] = s[j]; j--; }
    s[j + 1] = k;
  }
  return s[valid / 2];
}

/**
 * Hydrostatic depth from a 0-5V pressure transducer: h = P / (rho * g).
 *
 * Returns NAN when HAS_PRESSURE_SENSOR is not defined (config.h) - i.e. on
 * every V1 rig as currently ordered. This is deliberate, not a placeholder:
 * PIN_PRESSURE floats without the transducer, and a floating ESP32 ADC pin
 * does not reliably read as broken - RF and PWM noise can land it inside a
 * plausible depth range, which would make updateLevelEstimate() below trust
 * noise over the one real sensor. NAN propagates cleanly through pr_ok
 * (any comparison against NAN is false) and through jsonF() in
 * publishTelemetry(), which already renders a non-finite float as JSON
 * `null` rather than losing the frame.
 */
float readPressureDepth() {
#ifdef HAS_PRESSURE_SENSOR
  const uint16_t raw = analogRead(PIN_PRESSURE);
  const float volts = (raw / 4095.0f) * ADC_REF_VOLTS * ADC_DIVIDER_RATIO;
  const float pascals = (volts - TRANSDUCER_OFFSET_V) * TRANSDUCER_PA_PER_VOLT;
  return pascals / (1000.0f * 9.80665f);
#else
  return NAN;
#endif
}

/**
 * One-dimensional Kalman update fusing the two depth estimates.
 *
 * The reservoir level is a slowly-varying state with fast measurement noise,
 * which is exactly what this filter is for. Beyond smoothing, it gives the
 * thing a single sensor never can: when the two measurements disagree by
 * more than their combined noise, one of them is broken, and the node can
 * say so instead of confidently reporting a wrong number.
 */
void updateLevelEstimate(float dt_s) {
  tempSensor.requestTemperatures();
  const float temp_c = tempSensor.getTempCByIndex(0);
  if (temp_c > -50.0f && temp_c < 80.0f) g_level.water_temp_c = temp_c;

  const float us = readUltrasonicMedian(g_level.water_temp_c);
  const float pr = readPressureDepth();

  g_level.ultrasonic_m = us;
  g_level.pressure_m   = pr;

  // Predict: level drifts slowly, so growth in uncertainty is small.
  g_level.variance += PROCESS_NOISE * dt_s;

  const bool us_ok = !isnan(us);
  // NAN comparisons are always false in IEEE 754, so on a build without
  // HAS_PRESSURE_SENSOR (readPressureDepth() returns NAN), pr_ok is false
  // on every call, unconditionally - not measured, structural.
  const bool pr_ok = pr > 0.0f && pr < US_MAX_RANGE_M;

#ifdef HAS_PRESSURE_SENSOR
  g_level.sensors_agree =
      (us_ok && pr_ok) ? (fabsf(us - pr) < SENSOR_DISAGREE_THRESHOLD_M) : false;
#else
  // No second physics channel exists on this build - there is nothing to
  // disagree with, so unconditionally reporting false here would raise a
  // fault the fault-injection demo never caused, on every single frame.
  // The one channel this build actually has still has to be valid.
  g_level.sensors_agree = us_ok;
#endif

  auto fuse = [](float measurement, float noise) {
    const float k = g_level.variance / (g_level.variance + noise);
    g_level.level_m += k * (measurement - g_level.level_m);
    g_level.variance *= (1.0f - k);
  };

  if (us_ok && pr_ok && g_level.sensors_agree) {
    fuse(us, US_NOISE);
    fuse(pr, PRESSURE_NOISE);
  } else if (pr_ok) {
    // Pressure is the more trustworthy fallback when it exists: it does not
    // care about surface waves, foam, spray or air temperature. This branch
    // is structurally unreachable without HAS_PRESSURE_SENSOR - pr_ok is
    // always false above - and is left in place rather than #ifdef'd out,
    // so defining that flag is the only change needed to re-enable it.
    fuse(pr, PRESSURE_NOISE * 2.0f);
  } else if (us_ok) {
    fuse(us, US_NOISE * 2.0f);
  }
  // If neither is usable the estimate coasts on the prediction and the
  // variance grows, which the twin sees and can act on.
}

// ---------------------------------------------------------------------------
// gate control
// ---------------------------------------------------------------------------

/**
 * Hard physical bounds, enforced below anything the network can reach.
 *
 * Runs on a timer ISR and overrides the commanded position unconditionally.
 * A crashed main loop, a malformed MQTT payload or a hostile command cannot
 * put the gate somewhere unsafe, because none of them execute here.
 */
void IRAM_ATTR safetyInterlock() {
  const float level = g_level.level_m;
  portENTER_CRITICAL_ISR(&g_gate_mux);
  if (level >= EMERGENCY_LEVEL_M) {
    g_gate.commanded_pct = 100.0f;          // structural relief overrides all
  } else if (level <= MIN_OPERATING_LEVEL_M) {
    g_gate.commanded_pct = 0.0f;            // never drain below dead storage
  }
  portEXIT_CRITICAL_ISR(&g_gate_mux);
}

/** Move toward the commanded position, respecting limits and ramp rate. */
void driveGate(float dt_s) {
  if (!g_gate.homed) return;

  // Take one consistent copy: the interlock can change the setpoint between
  // the comparison and the step loop otherwise.
  portENTER_CRITICAL(&g_gate_mux);
  const float commanded = g_gate.commanded_pct;
  portEXIT_CRITICAL(&g_gate_mux);

  const float max_delta = GATE_MAX_RATE_PCT_PER_S * dt_s;
  float delta = commanded - g_gate.actual_pct;
  delta = constrain(delta, -max_delta, max_delta);
  if (fabsf(delta) < 0.01f) return;

  if (delta > 0 && digitalRead(PIN_LIMIT_OPEN) == LOW) return;
  if (delta < 0 && digitalRead(PIN_LIMIT_CLOSED) == LOW) return;

  digitalWrite(PIN_GATE_DIR, delta > 0 ? HIGH : LOW);
  digitalWrite(PIN_GATE_ENABLE, LOW);       // A4988 enable is active low

  const int32_t steps = fabsf(delta) * STEPS_PER_PERCENT;
  for (int32_t i = 0; i < steps; i++) {
    digitalWrite(PIN_GATE_STEP, HIGH);
    delayMicroseconds(STEP_PULSE_US);
    digitalWrite(PIN_GATE_STEP, LOW);
    delayMicroseconds(STEP_INTERVAL_US);
  }

  g_gate.position_steps += (delta > 0 ? steps : -steps);
  g_gate.actual_pct += delta;

  // Release the driver between moves. Left enabled, the A4988 holds torque
  // continuously: the motor and driver run hot for no benefit on a sluice
  // that is not fighting a load once it has stopped.
  digitalWrite(PIN_GATE_ENABLE, HIGH);
}

/** Drive to the closed limit switch to establish a datum. */
bool homeGate() {
  digitalWrite(PIN_GATE_DIR, LOW);
  digitalWrite(PIN_GATE_ENABLE, LOW);

  for (int32_t i = 0; i < HOMING_MAX_STEPS; i++) {
    if (digitalRead(PIN_LIMIT_CLOSED) == LOW) {
      g_gate.position_steps = 0;
      g_gate.actual_pct = 0.0f;
      g_gate.homed = true;
      return true;
    }
    digitalWrite(PIN_GATE_STEP, HIGH);
    delayMicroseconds(STEP_PULSE_US);
    digitalWrite(PIN_GATE_STEP, LOW);
    delayMicroseconds(STEP_INTERVAL_US * 2);
  }

  // Never reached the switch: the mechanism is jammed or the switch failed.
  // Refuse to operate rather than moving a gate with no known position.
  g_gate.jammed = true;
  digitalWrite(PIN_GATE_ENABLE, HIGH);
  return false;
}

// ---------------------------------------------------------------------------
// tamper-evident logging
// ---------------------------------------------------------------------------

/**
 * Chain each record to its predecessor with SHA-256.
 *
 * After the 2018 floods there were public disputes about whether reservoir
 * levels had been reported accurately and promptly. A hash chain does not
 * prevent misreporting - but it makes silent *retrospective* editing
 * detectable, which is the part that matters in an inquiry.
 */
void appendAuditRecord(const char* payload, char* out_hex, size_t out_len) {
  mbedtls_sha256_context ctx;
  mbedtls_sha256_init(&ctx);
  mbedtls_sha256_starts(&ctx, 0);
  mbedtls_sha256_update(&ctx, g_prev_hash, sizeof(g_prev_hash));
  mbedtls_sha256_update(&ctx, (const unsigned char*)payload, strlen(payload));
  mbedtls_sha256_finish(&ctx, g_prev_hash);
  mbedtls_sha256_free(&ctx);

  for (size_t i = 0; i < 32 && (i * 2 + 2) < out_len; i++) {
    snprintf(out_hex + i * 2, 3, "%02x", g_prev_hash[i]);
  }
}

// ---------------------------------------------------------------------------
// telemetry
// ---------------------------------------------------------------------------

/**
 * Format a float for JSON, or `null` if it is not finite.
 *
 * printf renders a failed sensor as a bare `nan`, which is not valid JSON -
 * so one dead channel took the whole frame down at the parser, hiding the
 * gate position and the flow along with it. That is exactly backwards: a
 * sensor failure is when the rest of the frame matters most.
 */
static const char* jsonF(char* buf, size_t n, float v, int dp) {
  if (!isfinite(v)) {
    snprintf(buf, n, "null");
  } else {
    snprintf(buf, n, "%.*f", dp, v);
  }
  return buf;
}

void publishTelemetry() {
  static uint32_t last_pulses = 0;
  const uint32_t pulses = g_flow_pulses;
  const float flow_lpm = (pulses - last_pulses) * FLOW_LITRES_PER_PULSE
                       * (60000.0f / TELEMETRY_INTERVAL_MS);
  last_pulses = pulses;

  char b_lvl[16], b_var[16], b_us[16], b_pr[16], b_tmp[16], b_flow[16];
  char payload[512];
  snprintf(payload, sizeof(payload),
           "{\"node\":\"%s\",\"uptime_s\":%lu,"
           "\"level_m\":%s,\"variance\":%s,"
           "\"ultrasonic_m\":%s,\"pressure_m\":%s,\"temp_c\":%s,"
           "\"sensors_agree\":%s,"
           "\"gate_cmd_pct\":%.1f,\"gate_actual_pct\":%.1f,"
           "\"gate_homed\":%s,\"gate_jammed\":%s,"
           "\"flow_lpm\":%s}",
           NODE_ID, millis() / 1000UL,
           jsonF(b_lvl, sizeof(b_lvl), g_level.level_m, 4),
           jsonF(b_var, sizeof(b_var), g_level.variance, 5),
           jsonF(b_us, sizeof(b_us), g_level.ultrasonic_m, 4),
           jsonF(b_pr, sizeof(b_pr), g_level.pressure_m, 4),
           jsonF(b_tmp, sizeof(b_tmp), g_level.water_temp_c, 2),
           g_level.sensors_agree ? "true" : "false",
           g_gate.commanded_pct, g_gate.actual_pct,
           g_gate.homed ? "true" : "false",
           g_gate.jammed ? "true" : "false",
           jsonF(b_flow, sizeof(b_flow), flow_lpm, 2));

  char hash_hex[65] = {0};
  appendAuditRecord(payload, hash_hex, sizeof(hash_hex));

  char framed[640];
  snprintf(framed, sizeof(framed), "{\"data\":%s,\"hash\":\"%s\"}", payload, hash_hex);

  if (mqtt.connected()) {
    mqtt.publish(MQTT_TOPIC_TELEMETRY, framed);
  } else {
    // TODO(phase-4): fall back to LoRa, then to the SD card.
    Serial.println(framed);
  }
}

void onMqttMessage(char* topic, byte* payload, unsigned int length) {
  if (strcmp(topic, MQTT_TOPIC_COMMAND) != 0) return;

  char buf[128];
  const unsigned int n = min(length, (unsigned int)(sizeof(buf) - 1));
  memcpy(buf, payload, n);
  buf[n] = '\0';

  // Minimal parse - a full JSON parser is more attack surface than this
  // needs. The interlock is the real defence regardless of what arrives.
  const char* key = strstr(buf, "\"gate_pct\"");
  if (!key) return;
  const char* colon = strchr(key, ':');
  if (!colon) return;

  const float pct = constrain(atof(colon + 1), 0.0f, 100.0f);
  g_gate.commanded_pct = pct;
  Serial.printf("[cmd] gate -> %.1f%%\n", pct);
}

// ---------------------------------------------------------------------------
// lifecycle
// ---------------------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  delay(400);
  Serial.println("\nAquaSync reservoir node starting");

  pinMode(PIN_US_TRIG, OUTPUT);
  pinMode(PIN_US_ECHO, INPUT);
  pinMode(PIN_GATE_STEP, OUTPUT);
  pinMode(PIN_GATE_DIR, OUTPUT);
  pinMode(PIN_GATE_ENABLE, OUTPUT);
  pinMode(PIN_LIMIT_CLOSED, INPUT);   // GPIO 34/35 have no internal pull-ups;
  pinMode(PIN_LIMIT_OPEN, INPUT);     // externals are on the board
  pinMode(PIN_FLOW, INPUT_PULLUP);

  digitalWrite(PIN_GATE_ENABLE, HIGH);   // start with the driver disabled
  attachInterrupt(digitalPinToInterrupt(PIN_FLOW), onFlowPulse, RISING);

  tempSensor.begin();
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_PRESSURE, ADC_11db);

#ifdef HAS_PRESSURE_SENSOR
  // Seed the filter from pressure - it does not need a plausible prior the
  // way the ultrasonic median does.
  g_level.level_m = readPressureDepth();
#else
  // No pressure sensor on this build (see config.h's HAS_PRESSURE_SENSOR) -
  // seeding from it would seed the entire filter from NAN. Take one
  // ultrasonic reading instead, at the struct's default temperature prior
  // (water_temp_c is not read from the DS18B20 until the first
  // updateLevelEstimate() call). If even that fails, leave the struct's
  // zero default in place: the filter's variance starts high (1.0f) and
  // corrects within a few real samples rather than trusting a guess.
  const float boot_us = readUltrasonicMedian(g_level.water_temp_c);
  if (!isnan(boot_us)) g_level.level_m = boot_us;
#endif

  Serial.println("homing gate ...");
  Serial.println(homeGate() ? "gate homed" : "GATE HOMING FAILED - refusing to operate");

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  for (int i = 0; i < 20 && WiFi.status() != WL_CONNECTED; i++) delay(500);
  Serial.println(WiFi.status() == WL_CONNECTED
                     ? "wifi connected"
                     : "wifi unavailable - degrading to local operation");

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMqttMessage);

  // The interlock runs on its own timer, independent of loop().
  hw_timer_t* timer = timerBegin(0, 80, true);      // 1 MHz tick
  timerAttachInterrupt(timer, &safetyInterlock, true);
  timerAlarmWrite(timer, 100000, true);             // 10 Hz
  timerAlarmEnable(timer);
}

void loop() {
  static uint32_t last_sense = 0, last_publish = 0, last_reconnect = 0;
  static uint32_t last_wifi_retry = 0;
  const uint32_t now = millis();

  if (now - last_sense >= SENSE_INTERVAL_MS) {
    updateLevelEstimate((now - last_sense) / 1000.0f);
    driveGate((now - last_sense) / 1000.0f);
    last_sense = now;
  }

  if (now - last_publish >= TELEMETRY_INTERVAL_MS) {
    publishTelemetry();
    last_publish = now;
  }

  // Wi-Fi first: the MQTT reconnect below is gated on the link being up, so
  // without this a single dropped association left the node offline forever
  // while still happily reconnecting to a broker it could never reach. An
  // expo hall is precisely where that happens.
  if (WiFi.status() != WL_CONNECTED && now - last_wifi_retry >= 10000) {
    last_wifi_retry = now;
    Serial.println("wifi down - reconnecting");
    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }

  if (!mqtt.connected() && now - last_reconnect >= 5000) {
    last_reconnect = now;
    if (WiFi.status() == WL_CONNECTED && mqtt.connect(NODE_ID)) {
      mqtt.subscribe(MQTT_TOPIC_COMMAND);
      Serial.println("mqtt connected");
    }
  }
  mqtt.loop();
}
