#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#if __has_include("tank_config.h")
#include "tank_config.h"
#else
#include "tank_config.example.h"
#endif
#include "controller.h"

static_assert(Config::EMPTY_DISTANCE_CM > Config::FULL_DISTANCE_CM, "Empty distance must exceed full distance");
static_assert(Config::FULL_DISTANCE_CM >= 2.0f && Config::EMPTY_DISTANCE_CM <= 390.0f, "Calibration outside sensor range");
static_assert(Config::SAMPLE_MS >= 100 && Config::SAMPLE_MS <= 1000, "Sample interval must be 100–1000 ms");

struct Snapshot {
  float level = NAN;
  float distance = NAN;
  bool pump = false;
  bool sourceOk = false;
  bool highFloatOk = false;
  Tank::Mode mode = Tank::Mode::Off;
  Tank::Fault fault = Tank::Fault::SensorInvalid;
  uint32_t uptime = 0;
};

portMUX_TYPE stateMux = portMUX_INITIALIZER_UNLOCKED;
Snapshot snapshot;
Tank::Mode requestedMode = Tank::Mode::Off;
Tank::Controller controller;
float lastDistance = NAN;
float lastLevel = NAN;
bool resetPending = false;
bool wasResetPressed = false;

void writePump(bool enabled) {
  digitalWrite(Config::RELAY_PIN, (enabled != Config::RELAY_ACTIVE_LOW) ? HIGH : LOW);
}

float readDistance() {
  digitalWrite(Config::TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(Config::TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(Config::TRIG_PIN, LOW);
  const unsigned long duration = pulseIn(Config::ECHO_PIN, HIGH, 30000);
  const float distance = duration * 0.0343f / 2.0f;
  if (duration == 0 || distance < 2.0f || distance > Config::EMPTY_DISTANCE_CM + 10.0f) return NAN;
  return distance;
}

// Network waits run on core 0; local sensing and relay control run on core 1.
void networkTask(void*) {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(Config::WIFI_SSID, Config::WIFI_PASSWORD);
  uint32_t lastReconnect = millis();
  for (;;) {
    if (WiFi.status() == WL_CONNECTED) {
      Snapshot current;
      portENTER_CRITICAL(&stateMux);
      current = snapshot;
      portEXIT_CRITICAL(&stateMux);
      StaticJsonDocument<512> doc;
      if (isfinite(current.level)) doc["level_percent"] = current.level;
      else doc["level_percent"] = nullptr;
      if (isfinite(current.distance)) doc["distance_cm"] = current.distance;
      else doc["distance_cm"] = nullptr;
      doc["pump"] = current.pump;
      doc["mode"] = current.mode == Tank::Mode::Auto ? "AUTO" : "OFF";
      if (current.fault == Tank::Fault::None) doc["fault"] = nullptr;
      else doc["fault"] = Tank::faultName(current.fault);
      doc["source_ok"] = current.sourceOk;
      doc["high_float_ok"] = current.highFloatOk;
      doc["uptime_s"] = current.uptime;
      doc["rssi"] = WiFi.RSSI();
      String body;
      serializeJson(doc, body);
      WiFiClient client;
      HTTPClient http;
      http.setConnectTimeout(1000);
      http.setTimeout(1000);
      if (http.begin(client, Config::SERVER_URL)) {
        http.addHeader("Content-Type", "application/json");
        http.addHeader("Authorization", String("Bearer ") + Config::DEVICE_TOKEN);
        const int status = http.POST(body);
        if (status == HTTP_CODE_OK) {
          // Only two modes are accepted. No remote override or remote fault reset.
          StaticJsonDocument<128> response;
          if (http.getSize() >= 0 && http.getSize() <= 128 && !deserializeJson(response, http.getString())) {
            const char* mode = response["mode"] | "";
            if (strcmp(mode, "AUTO") == 0 || strcmp(mode, "OFF") == 0) {
              portENTER_CRITICAL(&stateMux);
              requestedMode = strcmp(mode, "AUTO") == 0 ? Tank::Mode::Auto : Tank::Mode::Off;
              portEXIT_CRITICAL(&stateMux);
            }
          }
        } else Serial.printf("Telemetry failed (%d); local control continues\n", status);
        http.end();
      }
    } else if (uint32_t(millis() - lastReconnect) >= 15000) {
      WiFi.reconnect();
      lastReconnect = millis();
    }
    vTaskDelay(pdMS_TO_TICKS(Config::TELEMETRY_MS));
  }
}

void setup() {
  // Hardware pull-up/down must also keep the relay OFF before firmware starts.
  writePump(false);
  pinMode(Config::RELAY_PIN, OUTPUT);
  writePump(false);
  pinMode(Config::TRIG_PIN, OUTPUT);
  pinMode(Config::ECHO_PIN, INPUT);
  pinMode(Config::HIGH_FLOAT_PIN, INPUT_PULLUP);
  pinMode(Config::SOURCE_FLOAT_PIN, INPUT_PULLUP);
  pinMode(Config::RESET_PIN, INPUT_PULLUP);
  pinMode(Config::BUZZER_PIN, OUTPUT);
  digitalWrite(Config::BUZZER_PIN, LOW);
  Serial.begin(115200);
  controller.lastOff = millis();
  const BaseType_t created = xTaskCreatePinnedToCore(networkTask, "telemetry", 8192, nullptr, 1, nullptr, 0);
  if (created != pdPASS) Serial.println("Networking task unavailable; pump remains OFF until a valid mode request.");
  Serial.println("Water tank controller booted in OFF mode");
}

void loop() {
  static uint32_t lastSample = millis() - Config::SAMPLE_MS;
  const uint32_t now = millis();
  const bool highOk = digitalRead(Config::HIGH_FLOAT_PIN) == LOW;
  const bool sourceOk = digitalRead(Config::SOURCE_FLOAT_PIN) == LOW;
  const bool resetPressed = digitalRead(Config::RESET_PIN) == LOW;
  if (resetPressed && !wasResetPressed) resetPending = true;
  wasResetPressed = resetPressed;
  portENTER_CRITICAL(&stateMux);
  controller.mode = requestedMode;
  portEXIT_CRITICAL(&stateMux);
  // Check digital interlocks between ultrasonic samples, too.
  if (!highOk) controller.trip(Tank::Fault::HighFloat, now);
  else if (!sourceOk) controller.trip(Tank::Fault::SourceEmpty, now);
  if (controller.mode == Tank::Mode::Off) controller.stop(now);
  if (controller.pump && uint32_t(now - controller.runStarted) >= Tank::MAX_RUN_MS) controller.trip(Tank::Fault::RunTimeout, now);
  // Apply an interlock stop before waiting for an ultrasonic echo.
  writePump(controller.pump);
  if (uint32_t(now - lastSample) >= Config::SAMPLE_MS) {
    lastSample = now;
    lastDistance = readDistance();
    lastLevel = isfinite(lastDistance) ? constrain(100.0f * (Config::EMPTY_DISTANCE_CM - lastDistance) /
                (Config::EMPTY_DISTANCE_CM - Config::FULL_DISTANCE_CM), 0.0f, 100.0f) : NAN;
    controller.sample(millis(), lastLevel, sourceOk, highOk, resetPending);
    resetPending = false;
  }
  writePump(controller.pump);
  digitalWrite(Config::BUZZER_PIN, controller.fault != Tank::Fault::None && (now / 250) % 2 ? HIGH : LOW);
  Snapshot current;
  current.level = lastLevel;
  current.distance = lastDistance;
  current.pump = controller.pump;
  current.sourceOk = sourceOk;
  current.highFloatOk = highOk;
  current.mode = controller.mode;
  current.fault = controller.fault;
  current.uptime = now / 1000;
  portENTER_CRITICAL(&stateMux);
  snapshot = current;
  portEXIT_CRITICAL(&stateMux);
  delay(10);
}
