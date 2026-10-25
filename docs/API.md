# HTTP API

Single device per server. JSON requests use `Content-Type: application/json` and a maximum 4096-byte body. Unknown telemetry fields are rejected. `/health` and dashboard assets are public. Other routes use `Authorization: Bearer TOKEN`.

## Device telemetry

`POST /api/device/telemetry` — use `TANK_DEVICE_TOKEN`. Disabled in demo mode to prevent mixing hardware and simulated readings.

```json
{
  "level_percent": 42.0,
  "distance_cm": 78.0,
  "pump": false,
  "mode": "OFF",
  "fault": null,
  "source_ok": true,
  "high_float_ok": true,
  "uptime_s": 123,
  "rssi": -48
}
```

- `level_percent`: finite number 0–100, or null for an invalid sensor reading.
- `distance_cm`: finite number 0–500, or null.
- `pump`, `source_ok`, `high_float_ok`: JSON booleans.
- `mode`: applied mode, AUTO or OFF.
- `fault`: null or SENSOR_INVALID, HIGH_FLOAT, SOURCE_EMPTY, OVERFLOW_RISK, RUN_TIMEOUT.
- `uptime_s`: integer 0–4294967296. Firmware uptime derives from millis() and wraps about every 49.7 days; controller elapsed timers handle that rollover.
- `rssi`: integer -127–0 dBm.

Null level requires SENSOR_INVALID. A running pump with a fault, OFF mode, unsafe float, missing level, or level at/above 90% is rejected. Validation catches inconsistent reports; hardware protection still belongs to the ESP32 and independent interlocks.

Response:

```json
{"mode": "AUTO"}
```

This is the requested mode. The device applies it locally subject to its protection rules and confirms the applied mode in subsequent telemetry. The server does not send an unconditional pump-on command or remote reset.

## Dashboard

Use the dashboard token printed at server startup, optionally supplied by `TANK_DASHBOARD_TOKEN`.

| Route | Method | Behavior |
|---|---|---|
| `/health` | GET | Public server health only; does not prove device health |
| `/api/state` | GET | Latest telemetry, online/stale status, requested mode, thresholds, latest 180 historical readings, recent events |
| `/api/command` | POST | `{"mode":"AUTO"}` or `{"mode":"OFF"}`; AUTO requires fresh device telemetry |
| `/api/demo` | POST | Demo only: `{"scenario":"low"}`; values normal, low, full, sensor_fault, source_empty, high_float, reset |

`/api/state` uses server receipt time for charts and monotonic elapsed time for online status. A device is offline at 15 seconds since last telemetry. Historical readings persist; device online state and requested modes reset on server restart. Latest telemetry is not restored as if it were live. Events are in-memory only.

Status codes: 200 success, 400 invalid request, 401 missing/wrong bearer token, 404 unknown route, 409 device ingestion attempted while running the simulator. Access tokens are sent in headers and are not recorded in request logs. The browser stores its token in sessionStorage until locked or the tab session ends. There is no public password-reset endpoint; restart the server or supply your own dashboard token.
