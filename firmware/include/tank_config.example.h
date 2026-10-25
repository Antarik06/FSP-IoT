#pragma once

// Copy to tank_config.h. Never commit Wi-Fi credentials or the device token.
namespace Config {
constexpr char WIFI_SSID[] = "YOUR_2_4_GHZ_WIFI";
constexpr char WIFI_PASSWORD[] = "YOUR_WIFI_PASSWORD";
// Your computer's LAN IPv4 address, not localhost. LAN prototype uses HTTP.
constexpr char SERVER_URL[] = "http://192.168.1.10:8080/api/device/telemetry";
constexpr char DEVICE_TOKEN[] = "REPLACE_WITH_TANK_DEVICE_TOKEN";
constexpr int TRIG_PIN = 5;
constexpr int ECHO_PIN = 18;  // 5 V echo MUST pass through a voltage divider.
constexpr int RELAY_PIN = 23;
constexpr int HIGH_FLOAT_PIN = 19;  // LOW=healthy, HIGH=trip/disconnected.
constexpr int SOURCE_FLOAT_PIN = 21; // LOW=source has water, HIGH=empty/disconnected.
constexpr int RESET_PIN = 32; // Momentary normally-open button to ground.
constexpr int BUZZER_PIN = 22; // Active 3.3 V buzzer through suitable driver.
constexpr bool RELAY_ACTIVE_LOW = true;
constexpr float EMPTY_DISTANCE_CM = 120.0f;
constexpr float FULL_DISTANCE_CM = 20.0f;
constexpr uint32_t SAMPLE_MS = 500;
constexpr uint32_t TELEMETRY_MS = 2000;
}
