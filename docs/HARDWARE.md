# Hardware and commissioning

## Components

| Component | Purpose |
|---|---|
| Original dual-core ESP32 DevKit / ESP32-WROOM development board | Wi-Fi and local control |
| HC-SR04 ultrasonic module | Dry indoor bench demonstration; not waterproof |
| Two float switches with healthy-closed contacts | High-level trip and source-water availability |
| 3.3 V logic-compatible relay driver/module, correctly rated for the load | Pump switching |
| Small low-voltage DC pump and separate rated DC supply | Safe bench prototype |
| Momentary button, active buzzer with driver | Local fault reset and audible alarm |
| 10 kΩ and 20 kΩ resistors | 5 V echo to ~3.33 V divider |
| Suitable pull resistor, flyback protection, fuse, enclosure and wiring | Relay startup and load protection |

A real tank needs an appropriate waterproof sensor. Substitute a pulse/echo sensor only after checking its minimum measurement distance, supply, logic levels, protocol, and calibration. Do not assume a waterproof sensor can use the HC-SR04 calibration or wiring unchanged.

The [HC-SR04 datasheet](https://cdn.sparkfun.com/datasheets/Sensors/Proximity/HCSR04.pdf) describes the 5 V supply, 2–400 cm nominal range and trigger timing. The [ESP32-DevKitC guide](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html) documents board pins and power options. Use only one board power-input method at a time.

## GPIO mapping

| ESP32 GPIO | Connect to | Notes |
|---|---|---|
| 5 | Ultrasonic TRIG | Bench sensor trigger input; verify logic compatibility |
| 18 | Divided ultrasonic ECHO | Never connect 5 V ECHO directly to the ESP32 |
| 23 | Relay driver input | Default active LOW; check module input requirements |
| 19 | High-water healthy contact | Other terminal to GND; closed below trip level, opens on trip |
| 21 | Source-water healthy contact | Other terminal to GND; closed while source has water |
| 32 | Reset button | Normally open momentary button to GND |
| 22 | Active-buzzer driver input | Drive through a suitable transistor, not a high-current buzzer directly |
| GND | Low-voltage signal ground | Common signal ground for sensor/driver as required |

Both float inputs use INPUT_PULLUP: **LOW means healthy; HIGH means unsafe or disconnected**. Orient/configure the actual float contacts accordingly and verify with a multimeter. A short to ground can hide a fault; this is not a safety-rated circuit. Use proper input conditioning and cable protection for long outdoor wiring.

Echo divider:

```text
HC-SR04 ECHO (5 V) --- 10 kΩ ---+--- ESP32 GPIO18
                               |
                             20 kΩ
                               |
                              GND
```

Power the bench HC-SR04 from a suitable 5 V source. Never power a pump from the ESP32. Use relay NO contacts so loss of relay coil power opens the pump circuit. For an active-low relay, provide an appropriate external pull-up to a **3.3 V-safe** level so it remains OFF while the ESP32 is booting/resetting; choose the bias/interface for the actual module. For active-high hardware, change `RELAY_ACTIVE_LOW` and use a suitable pull-down. Scope or test the output over power cycles with the pump disconnected.

## Independent stop circuit

For an installation, use a properly engineered series contact chain that removes power from the pump contactor coil regardless of ESP32 output:

```text
Control supply → fuse → physical stop → high-level interlock
               → source-low interlock → relay NO → contactor coil → return
```

Use separate contacts/switches for GPIO sensing and power control, or isolated interfaces. **Do not connect coil voltage to a GPIO.** Select switch/relay/contactor voltage and current ratings for the actual load and its starting current. Suppress inductive transients appropriately. For a mains pump, have a qualified electrician design and install the fused, earthed, enclosed circuit; breadboard wiring is only for the low-voltage prototype. A welded relay, MCU crash, or sensor stuck at a plausible value needs independent hardware protection. The source float and runtime cap reduce dry-running risk but do not measure flow or prove that water is entering the tank.

## Calibration

Mount the sensor facing vertically down with a clear acoustic path. Keep it away from the inlet stream and tank walls. Measure from the **sensor face** to water:

- `EMPTY_DISTANCE_CM`: distance at the desired 0% water level; example 120 cm.
- `FULL_DISTANCE_CM`: distance at the desired 100% level, leaving sufficient headspace; example 20 cm.

```text
level_percent = 100 × (empty_distance − measured_distance)
                      / (empty_distance − full_distance)
```

Readings are bounded to 0–100 only after range checking. No echo, distance below 2 cm, or distance more than 10 cm beyond the calibrated empty distance is invalid and latches a fault. Measurements closer than the calibrated full surface map to 100% and trip the critical cutoff. The example assumes an HC-SR04 range; use a full headspace of at least 20 cm for this bench setup. Level percent equals volume percent only for tanks with a constant horizontal cross-section, such as a rectangular or upright cylindrical tank.

This implementation uses individual readings with a three-sample **start** gate. It does not smooth away a high or invalid reading. That prioritizes shutdown but can cause nuisance trips from splashes or condensation. Validate sensor behavior under actual filling conditions. Set the physical high float above the 90% normal stop, below the spill level, with enough headroom for flow, sampling delay, pump coast-down, and any siphoning. A pump shutoff cannot prevent gravity-fed or stuck-valve inflow; use the right valve/interlock if your plumbing needs it.

## Commissioning sequence

1. Disconnect the pump; use a test lamp or relay indicator.
2. Verify actual supply, 3.3 V echo, common grounding, and relay OFF polarity.
3. Power-cycle repeatedly. The relay must remain OFF during boot, flashing, Wi-Fi failure, and default OFF mode.
4. Verify displayed distance against physical measurements at low, middle, and high levels.
5. Enter AUTO. Below 25%, confirm three valid samples and 10 seconds off before starting. Confirm OFF at 90%.
6. Open each float contact and unplug the sensor separately. Each must disable the relay and latch a fault.
7. Restore each input. Verify no automatic fault clearing; press the local reset only after three healthy readings below 90%.
8. Test an independent hardwired high-level stop even with the GPIO relay command forced active on a bench test jig.
9. Disconnect Wi-Fi while filling. Verify local shutoff still works. Dashboard must show stale/offline data after 15 seconds. A remote OFF request remains queued until connectivity returns.
10. Test with the actual low-voltage pump under supervision, including stop latency, headroom, blocked inflow and source-empty conditions. Test the 15-minute continuous-run trip with a safe test load, never deliberately dry-run a pump.
