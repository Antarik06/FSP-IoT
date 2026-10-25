# Project overview

**Title:** Smart Water Tank Level Monitoring and Overflow Prevention System

## Problem and objective

Manual pump operation can waste water through overflow and damage a pump when its source is empty. This project measures tank water level, displays it over Wi-Fi, and automatically controls a fill pump using local threshold logic and independent water-presence inputs.

## Modules

1. **Sensing:** downward-facing ultrasonic distance measurement converts water surface distance into calibrated level percent. High-level and source-water floats provide separate digital inputs.
2. **Local control:** ESP32 decides whether to operate the pump. Hysteresis, minimum off time, continuous-run timeout, and latched faults reduce unwanted cycling and unsafe operation.
3. **Connectivity:** the ESP32 exchanges authenticated HTTP telemetry and requested mode with a LAN server. Losing Wi-Fi does not suspend sensing or local shutoff.
4. **Monitoring:** a responsive dashboard shows level, pump state, mode confirmation, interlocks, recent activity and historical trends.
5. **Storage and demonstration:** SQLite retains readings. A hardware-free simulator demonstrates behavior using the same API/dashboard and an equivalent Python controller model.

## Algorithm

```text
Boot with pump OFF
Read floats continuously and ultrasonic sensor every 500 ms
If sensor invalid OR high float trips OR source empty OR level >= 95%:
    latch fault and switch pump OFF
If continuous pump run >= 15 minutes:
    latch runtime fault and switch pump OFF
Clear fault only on local reset with healthy inputs,
    three valid samples and level < 90%
If fault latched OR requested mode OFF:
    switch pump OFF
Else if level >= 90%:
    switch pump OFF
Else if level <= 25% AND three valid samples AND pump off >= 10 seconds:
    switch pump ON
Else:
    keep current pump state
Upload latest measurements every 2 seconds and accept AUTO/OFF request
```

## Demonstration checklist

| Demonstration | Expected behavior |
|---|---|
| Start demo | Dashboard connects; pump starts OFF |
| Resume automatic + low level | Pump starts after valid readings and off delay |
| Near full while filling | Pump switches OFF above normal stop level |
| Sensor failure | Level unavailable, pump OFF, SENSOR_INVALID latched |
| Source empty | Pump OFF, SOURCE_EMPTY latched |
| Float trip | Pump OFF, HIGH_FLOAT latched |
| Restore normal without reset | Fault remains latched |
| Local reset after valid readings | Fault clears; AUTO can resume |
| Stop server / unplug network on real device | Dashboard becomes stale; ESP32 still protects locally |

Use the Python tests for boundary cases such as exactly 25%, 90%, 95%, runtime expiry, and malformed/unauthorized requests. ESP32 tests include hysteresis, a latched fault, and timer rollover. Electrical behavior must be validated on the assembled hardware.

## Scope and limitations

This is a single-tank LAN prototype. It does not include cloud hosting, SMS/email delivery, multi-user roles, mobile push alerts, flow verification, or a hardware certification. Percent represents calibrated water height, not automatically liters. Sensor mounting, condensation, turbulent water, relay failure, gravity inflow and power loss need appropriate physical design. The firmware and simulator models must be kept consistent when thresholds are changed; the dashboard thresholds are currently fixed with the server constants.

Potential extensions include a flow sensor for no-flow detection, a tank geometry/volume model, certificate-validated HTTPS or MQTT over TLS, multi-device identity, and notification integrations.
