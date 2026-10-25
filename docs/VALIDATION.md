# Validation record

Checked on 23 October 2026.

| Check | Result |
|---|---|
| Python 3.13.3: `python -m unittest discover -s tests -v` | 17 tests passed |
| Node.js 22.14.0: `node --check web/app.js` | Passed |
| PlatformIO Core 6.1.18: `pio run -d firmware -e esp32dev` | Firmware compiled and linked successfully |
| ESP32 test build: `pio test -d firmware -e controller_tests --without-uploading --without-testing` | Test firmware compiled successfully; no tests executed on a board |
| Browser demo | Login, live telemetry, AUTO request, low-level filling, automatic stop, sensor-fault latch, restore/reset, and OFF confirmation verified |
| Browser console | No warnings/errors observed during the demo check |

The firmware build used Espressif32 6.9.0, Arduino ESP32 2.0.17 and ArduinoJson 6.21.5 with the example configuration. It uses 45,916 bytes of static RAM (14.0%) and 799,533 bytes of program flash (61.0% of the default application partition). Runtime task stacks and heap allocations require additional RAM.

The backend tests include actual HTTP requests on the loopback interface, separate dashboard/device bearer-token checks, malformed telemetry rejection, command request versus applied mode, offline handling, persistent history, simulator-only endpoint isolation and repeated simulator actions. Controller-model tests cover start/stop thresholds, minimum off time, sensor faults, source-empty/high-float faults, critical cutoff, maximum runtime and local reset conditions.

No physical ESP32, sensor, relay, float switch or pump was connected for this validation. Embedded tests are provided for execution on a board. Complete the commissioning checklist in HARDWARE.md before connecting a pump. Compilation and simulator tests do not verify electrical behavior, sensor accuracy, physical shutoff latency or independent interlock wiring.
