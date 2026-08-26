/**
 * AquaSync reservoir node configuration.
 *
 * Copy to config_local.h and edit for your rig, or override via
 * build_flags in platformio.ini. Do not commit credentials.
 */
#pragma once

// -- identity ---------------------------------------------------------------
#define NODE_ID "aquasync-reservoir-01"

// -- network ----------------------------------------------------------------
#define WIFI_SSID     "CHANGE_ME"
#define WIFI_PASSWORD "CHANGE_ME"
#define MQTT_HOST     "192.168.1.100"
#define MQTT_PORT     1883
#define MQTT_TOPIC_TELEMETRY "aquasync/reservoir/01/telemetry"
#define MQTT_TOPIC_COMMAND   "aquasync/reservoir/01/command"

// -- timing -----------------------------------------------------------------
#define SENSE_INTERVAL_MS      500
#define TELEMETRY_INTERVAL_MS 1000

// -- ultrasonic -------------------------------------------------------------
// Height of the transducer face above the tank floor. Measure it; do not
// estimate it. Every depth reading is differenced against this number.
#define SENSOR_MOUNT_HEIGHT_M    0.450f
#define US_MIN_RANGE_M           0.020f
#define US_MAX_RANGE_M           0.450f
#define ULTRASONIC_TIMEOUT_US    30000UL

// -- pressure transducer ----------------------------------------------------
#define ADC_REF_VOLTS            3.30f
#define ADC_DIVIDER_RATIO        2.00f   // 0-5V sensor into a 3.3V ADC
#define TRANSDUCER_OFFSET_V      0.50f   // output at zero pressure
#define TRANSDUCER_PA_PER_VOLT   2500.0f // (span Pa) / (span volts)

// -- Kalman filter ----------------------------------------------------------
// Tuning note: PROCESS_NOISE is how fast we believe the true level can
// change. Too high and the filter chases surface waves; too low and it lags
// a real drawdown. Start here and tune against a step test on the rig.
#define PROCESS_NOISE            0.00005f
#define US_NOISE                 0.00040f   // ultrasonic variance, m^2
#define PRESSURE_NOISE           0.00015f   // pressure variance, m^2
#define SENSOR_DISAGREE_THRESHOLD_M 0.030f  // above this, one of them is wrong

// -- gate -------------------------------------------------------------------
#define STEPS_PER_PERCENT        18.0f
#define STEP_PULSE_US            3
#define STEP_INTERVAL_US         700
#define HOMING_MAX_STEPS         4000
// Slew limit. A gate that slams is a hazard in itself, at any scale, and
// Kerala protocol requires staged opening with siren warning.
#define GATE_MAX_RATE_PCT_PER_S  4.0f

// -- safety interlock (rig-scale metres) ------------------------------------
#define EMERGENCY_LEVEL_M        0.400f
#define MIN_OPERATING_LEVEL_M    0.040f

// -- flow sensor ------------------------------------------------------------
// YF-S201 nominal: 450 pulses per litre.
#define FLOW_LITRES_PER_PULSE    (1.0f / 450.0f)
