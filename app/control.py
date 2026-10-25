"""Executable simulator model of the firmware's local pump controller."""
from dataclasses import dataclass
import math

START_PERCENT = 25.0
STOP_PERCENT = 90.0
CRITICAL_PERCENT = 95.0
MIN_OFF_SECONDS = 10.0
MAX_RUN_SECONDS = 900.0


@dataclass
class Controller:
    mode: str = "OFF"
    pump: bool = False
    fault: str | None = None
    last_off: float = 0.0
    run_started: float = 0.0
    valid_samples: int = 0

    def step(self, now, level, *, source_ok=True, high_float_ok=True, reset=False):
        valid = (isinstance(level, (float, int)) and not isinstance(level, bool)
                 and math.isfinite(level) and 0 <= level <= 100)
        self.valid_samples = min(3, self.valid_samples + 1) if valid else 0
        cause = ("SENSOR_INVALID" if not valid else
                 "HIGH_FLOAT" if not high_float_ok else
                 "SOURCE_EMPTY" if not source_ok else
                 "OVERFLOW_RISK" if level >= CRITICAL_PERCENT else
                 "RUN_TIMEOUT" if self.pump and now - self.run_started >= MAX_RUN_SECONDS
                 else None)
        if cause:
            self.fault = cause
        elif reset and valid and level < STOP_PERCENT and self.valid_samples >= 3:
            self.fault = None
        if self.fault or self.mode == "OFF" or (valid and level >= STOP_PERCENT):
            self._stop(now)
        elif (not self.pump and self.valid_samples >= 3 and level <= START_PERCENT
              and now - self.last_off >= MIN_OFF_SECONDS):
            self.pump = True
            self.run_started = now
        return self.pump

    def _stop(self, now):
        if self.pump:
            self.last_off = now
        self.pump = False
