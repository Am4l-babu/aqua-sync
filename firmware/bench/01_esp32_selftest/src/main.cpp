/**
 * Bench test 1 of 6: the ESP32 board alone.
 *
 * Nothing is wired to it yet. This exists to separate three failure modes
 * that otherwise get diagnosed together, at the worst time - inside a rig
 * that is already glued and full of water:
 *
 *   1. Bad board / bad USB cable / bad driver   -> nothing below prints
 *   2. Bad Wi-Fi credentials or router out of range -> prints, never "WIFI OK"
 *   3. A pin is dead (rare, but cheap to rule out)   -> ADC/GPIO loop fails
 *
 * Pass: the serial monitor shows "WIFI OK" with an IP address, the onboard
 * LED blinks once a second, and the floating-pin ADC line prints a number
 * that jumps around (proving the ADC itself works - a *steady* number on a
 * floating pin is more likely a dead ADC than a quiet one).
 */
#include <Arduino.h>
#include <WiFi.h>

#ifndef WIFI_SSID
#define WIFI_SSID "CHANGE_ME"
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "CHANGE_ME"
#endif

// Most ESP32-WROOM-32 DevKits (BOM item 1) put the onboard LED on GPIO2.
// If it does not blink, check the silkscreen on your specific board - a few
// clones wire it differently or omit it.
constexpr uint8_t PIN_LED = 2;

// Any pin not yet claimed by a sensor is fine here. GPIO34 is one of the
// four input-only ADC1 pins this project uses for real sensors later
// (config.h: PIN_LIMIT_CLOSED), so testing on it now also confirms that
// specific pin is alive before it is asked to do real work.
constexpr uint8_t PIN_ADC_SCRATCH = 34;

unsigned long last_blink = 0;
bool led_state = false;

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println();
  Serial.println("=== AquaSync bench test 1/6: ESP32 self-test ===");

  pinMode(PIN_LED, OUTPUT);
  analogReadResolution(12);

  Serial.printf("connecting to '%s' ", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  for (int i = 0; i < 20 && WiFi.status() != WL_CONNECTED; i++) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WIFI OK, IP = ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println(
        "WIFI FAILED - check WIFI_SSID/WIFI_PASSWORD above and that the "
        "router is in range. The board itself may still be fine.");
  }
}

void loop() {
  const unsigned long now = millis();
  if (now - last_blink >= 1000) {
    last_blink = now;
    led_state = !led_state;
    digitalWrite(PIN_LED, led_state);
    const uint16_t floating = analogRead(PIN_ADC_SCRATCH);
    Serial.printf("[%lus] led=%d  floating ADC(pin %d)=%u  wifi=%s\n",
                  now / 1000, led_state, PIN_ADC_SCRATCH, floating,
                  WiFi.status() == WL_CONNECTED ? "connected" : "down");
  }
}
