import unittest
from app.control import Controller, MAX_RUN_SECONDS


class ControlTests(unittest.TestCase):
    def ready(self, level=20):
        c = Controller(mode="AUTO")
        for now in (10, 11, 12):
            c.step(now, level)
        return c

    def test_boot_off_and_valid_reading_gate(self):
        c = Controller()
        for now in (10, 11, 12):
            c.step(now, 10)
        self.assertFalse(c.pump)
        c = Controller(mode="AUTO")
        c.step(10, 20)
        c.step(11, 20)
        self.assertFalse(c.pump)
        c.step(12, 20)
        self.assertTrue(c.pump)

    def test_hysteresis_and_exact_thresholds(self):
        c = self.ready(25)
        self.assertTrue(c.pump)
        c.step(13, 70)
        self.assertTrue(c.pump)
        c.step(14, 90)
        self.assertFalse(c.pump)
        self.assertIsNone(c.fault)
        c.step(25, 50)
        self.assertFalse(c.pump)
        c.step(26, 25)
        self.assertTrue(c.pump)

    def test_minimum_off_time(self):
        c = self.ready()
        c.step(13, 90)
        c.step(22.9, 10)
        self.assertFalse(c.pump)
        c.step(23, 10)
        self.assertTrue(c.pump)

    def test_faults_stop_and_latch_until_healthy_reset(self):
        cases = [(None, {}, "SENSOR_INVALID"), (float("nan"), {}, "SENSOR_INVALID"),
                 (float("inf"), {}, "SENSOR_INVALID"), (-1, {}, "SENSOR_INVALID"),
                 (101, {}, "SENSOR_INVALID"), (20, {"source_ok":False}, "SOURCE_EMPTY"),
                 (20, {"high_float_ok":False}, "HIGH_FLOAT"), (95, {}, "OVERFLOW_RISK")]
        for level, flags, fault in cases:
            with self.subTest(fault=fault, level=level):
                c = self.ready()
                c.step(13, level, **flags, reset=True)
                self.assertFalse(c.pump)
                self.assertEqual(c.fault, fault)
                for now in (24, 25, 26):
                    c.step(now, 20)
                self.assertFalse(c.pump)
                c.step(27, 20, reset=True)
                self.assertIsNone(c.fault)
                self.assertTrue(c.pump)

    def test_fault_reset_requires_three_good_samples_and_below_stop(self):
        c = self.ready()
        c.step(13, None)
        c.step(24, 10, reset=True)
        self.assertEqual(c.fault, "SENSOR_INVALID")
        c.step(25, 10)
        c.step(26, 92, reset=True)
        self.assertIsNotNone(c.fault)
        c.step(27, 20, reset=True)
        self.assertIsNone(c.fault)

    def test_runtime_timeout(self):
        c = self.ready()
        c.step(c.run_started + MAX_RUN_SECONDS, 20)
        self.assertEqual(c.fault, "RUN_TIMEOUT")
        self.assertFalse(c.pump)

    def test_off_stops_running_pump(self):
        c = self.ready()
        c.mode = "OFF"
        c.step(13, 20)
        self.assertFalse(c.pump)


if __name__ == "__main__":
    unittest.main()
