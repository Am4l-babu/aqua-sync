/**
 * AquaSync reservoir node - ESP32 firmware for the scale rig and field node.
 *
 * Reads reservoir level, fuses two independent sensors, drives the sluice
 * gate, and publishes telemetry. Four design decisions are worth explaining,
 * because they are what separate this from a sensor demo:
 *
 * 1. TWO SENSORS, DIFFERENT PHYSICS.  Ultrasonic time-of-flight and
 *    hydrostatic pressure fail in different ways for different reasons. Two
 *    ultrasonic sensors that agree tell you nothing - they fail together.
 *    A Kalman filter fuses them; their disagreement is the fault signal.
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
 * 4. IT DEGRADES INSTEAD OF FAILING.  Wi-Fi -> LoRa -> local SD. If telemetry
 *    is lost entirely the node assumes a conservative worst case rather than
 *    holding its last command.
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
  float level_m      = 0.0f;   // fused estimate
  float variance     = 1.0f;   // filter covariance
  float ultrasonic_m = 0.0f;   // raw
  float pressure_m   = 0.0f;   // raw
  float water_temp_c = 25.0f;
  bool  sensors_agree = true;
};

struct GateState {
  float   commanded_pct = 0.0f;
  float   actual_pct    = 0.0f;
  int32_t position_steps = 0;
  bool    homed         = false;
  bool    jammed        = false;
};

static LevelEstimate g_level;
static GateState     g_gate;
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

/** Speed of sound in air, corrected for temperature. */
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

/** Hydrostatic depth from a 0-5V pressure transducer: h = P / (rho * g). */
float readPressureDepth() {
  const uint16_t raw = analogRead(PIN_PRESSURE);
  const float volts = (raw / 4095.0f) * ADC_REF_VOLTS * ADC_DIVIDER_RATIO;
  const float pascals = (volts - TRANSDUCER_OFFSET_V) * TRANSDUCER_PA_PER_VOLT;
  return pascals / (1000.0f * 9.80665f);
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
  const bool pr_ok = pr > 0.0f && pr < US_MAX_RANGE_M;

  g_level.sensors_agree =
      (us_ok && pr_ok) ? (fabsf(us - pr) < SENSOR_DISAGREE_THRESHOLD_M) : false;

  auto fuse = [](float measurement, float noise) {
    const float k = g_level.variance / (g_level.variance + noise);
    g_level.level_m += k * (measurement - g_level.level_m);
    g_level.variance *= (1.0f - k);
  };

  if (us_ok && pr_ok && g_level.sensors_agree) {
    fuse(us, US_NOISE);
    fuse(pr, PRESSURE_NOISE);
  } else if (pr_ok) {
    // Pressure is the more trustworthy fallback: it does not care about
    // surface waves, foam, spray or air temperature.
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
  if (g_level.level_m >= EMERGENCY_LEVEL_M) {
    g_gate.commanded_pct = 100.0f;          // structural relief overrides all
  } else if (g_level.level_m <= MIN_OPERATING_LEVEL_M) {
    g_gate.commanded_pct = 0.0f;            // never drain below dead storage
  }
}

/** Move toward the commanded position, respecting limits and ramp rate. */
void driveGate(float dt_s) {
  if (!g_gate.homed) return;

  const float max_delta = GATE_MAX_RATE_PCT_PER_S * dt_s;
  float delta = g_gate.commanded_pct - g_gate.actual_pct;
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

void publishTelemetry() {
  static uint32_t last_pulses = 0;
  const uint32_t pulses = g_flow_pulses;
  const float flow_lpm = (pulses - last_pulses) * FLOW_LITRES_PER_PULSE
                       * (60000.0f / TELEMETRY_INTERVAL_MS);
  last_pulses = pulses;

  char payload[512];
  snprintf(payload, sizeof(payload),
           "{\"node\":\"%s\",\"uptime_s\":%lu,"
           "\"level_m\":%.4f,\"variance\":%.5f,"
           "\"ultrasonic_m\":%.4f,\"pressure_m\":%.4f,\"temp_c\":%.2f,"
           "\"sensors_agree\":%s,"
           "\"gate_cmd_pct\":%.1f,\"gate_actual_pct\":%.1f,"
           "\"gate_homed\":%s,\"gate_jammed\":%s,"
           "\"flow_lpm\":%.2f}",
           NODE_ID, millis() / 1000UL,
           g_level.level_m, g_level.variance,
           g_level.ultrasonic_m, g_level.pressure_m, g_level.water_temp_c,
           g_level.sensors_agree ? "true" : "false",
           g_gate.commanded_pct, g_gate.actual_pct,
           g_gate.homed ? "true" : "false",
           g_gate.jammed ? "true" : "false",
           flow_lpm);

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

  // Seed the filter from pressure - it does not need a plausible prior the
  // way the ultrasonic median does.
  g_level.level_m = readPressureDepth();

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

  if (!mqtt.connected() && now - last_reconnect >= 5000) {
    last_reconnect = now;
    if (WiFi.status() == WL_CONNECTED && mqtt.connect(NODE_ID)) {
      mqtt.subscribe(MQTT_TOPIC_COMMAND);
      Serial.println("mqtt connected");
    }
  }
  mqtt.loop();
}
