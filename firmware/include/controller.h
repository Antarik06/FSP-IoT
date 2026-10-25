#pragma once
#include <stdint.h>
#include <math.h>

namespace Tank {
constexpr float START_PERCENT = 25.0f;
constexpr float STOP_PERCENT = 90.0f;
constexpr float CRITICAL_PERCENT = 95.0f;
constexpr uint32_t MIN_OFF_MS = 10000;
constexpr uint32_t MAX_RUN_MS = 900000;
enum class Mode { Off, Auto };
enum class Fault { None, SensorInvalid, HighFloat, SourceEmpty, OverflowRisk, RunTimeout };

inline const char* faultName(Fault fault) {
  switch (fault) {
    case Fault::SensorInvalid: return "SENSOR_INVALID";
    case Fault::HighFloat: return "HIGH_FLOAT";
    case Fault::SourceEmpty: return "SOURCE_EMPTY";
    case Fault::OverflowRisk: return "OVERFLOW_RISK";
    case Fault::RunTimeout: return "RUN_TIMEOUT";
    default: return "";
  }
}

struct Controller {
  Mode mode = Mode::Off;
  Fault fault = Fault::None;
  bool pump = false;
  uint8_t validSamples = 0;
  uint32_t lastOff = 0;
  uint32_t runStarted = 0;

  void stop(uint32_t now) {
    if (pump) lastOff = now;
    pump = false;
  }

  void trip(Fault reason, uint32_t now) {
    fault = reason;
    stop(now);
  }

  // Unsigned elapsed arithmetic works across the millis() rollover.
  void sample(uint32_t now, float level, bool sourceOk, bool highFloatOk, bool reset) {
    const bool valid = isfinite(level) && level >= 0 && level <= 100;
    validSamples = valid ? (validSamples < 3 ? validSamples + 1 : 3) : 0;
    Fault cause = Fault::None;
    if (!valid) cause = Fault::SensorInvalid;
    else if (!highFloatOk) cause = Fault::HighFloat;
    else if (!sourceOk) cause = Fault::SourceEmpty;
    else if (level >= CRITICAL_PERCENT) cause = Fault::OverflowRisk;
    else if (pump && uint32_t(now - runStarted) >= MAX_RUN_MS) cause = Fault::RunTimeout;
    if (cause != Fault::None) fault = cause;
    else if (reset && level < STOP_PERCENT && validSamples >= 3) fault = Fault::None;
    if (fault != Fault::None || mode == Mode::Off || (valid && level >= STOP_PERCENT)) stop(now);
    else if (!pump && validSamples >= 3 && level <= START_PERCENT && uint32_t(now - lastOff) >= MIN_OFF_MS) {
      pump = true;
      runStarted = now;
    }
  }
};
}
