import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from app.server import TankState, TankHTTPServer, validate_telemetry, simulate


def telemetry(**updates):
    return {"level_percent":45.0, "distance_cm":75.0, "pump":False, "mode":"OFF", "fault":None,
            "source_ok":True, "high_float_ok":True, "uptime_s":123, "rssi":-50, **updates}


class ServerTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(__file__).resolve().parent.parent / ".tools" / "test-tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.state = TankState(Path(self.temp.name) / "test.db", dashboard_token="dashboard-key", device_token="device-key")
        self.server = TankHTTPServer(("127.0.0.1", 0), self.state)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval":0.05})
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()
        self.state.close()
        self.temp.cleanup()

    def request(self, path, data=None, token="dashboard-key", raw=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        body = raw if raw is not None else (json.dumps(data) if data is not None else None)
        connection.request("POST" if body is not None else "GET", path, body,
                           {"Authorization":"Bearer " + token, "Content-Type":"application/json"})
        response = connection.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        connection.close()
        return result

    def test_public_dashboard_and_health(self):
        for path in ("/", "/app.js", "/style.css", "/health"):
            status, body, headers = self.request(path, token="")
            self.assertEqual(status, 200)
            self.assertTrue(body)
            self.assertIn("Content-Security-Policy", headers)

    def test_separate_tokens_and_unauthorized_control(self):
        for path, data, token in [("/api/state", None, ""), ("/api/command", {"mode":"AUTO"}, "device-key"),
                                   ("/api/device/telemetry", telemetry(), "dashboard-key")]:
            self.assertEqual(self.request(path, data, token=token)[0], 401)

    def test_live_round_trip_and_confirmation(self):
        self.assertEqual(self.request("/api/command", {"mode":"AUTO"})[0], 400)
        code, raw, _ = self.request("/api/device/telemetry", telemetry(), "device-key")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(raw), {"mode":"OFF"})
        self.assertEqual(self.request("/api/command", {"mode":"AUTO"})[0], 200)
        snapshot = self.state.snapshot()
        self.assertEqual(snapshot["desired_mode"], "AUTO")
        self.assertEqual(snapshot["telemetry"]["mode"], "OFF")
        code, raw, _ = self.request("/api/device/telemetry", telemetry(mode="AUTO"), "device-key")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(raw), {"mode":"AUTO"})
        self.assertTrue(self.state.snapshot()["online"])
        self.assertEqual(len(self.state.snapshot()["history"]), 2)

    def test_stale_reading_and_queued_off(self):
        self.state.ingest(telemetry())
        self.state.last_seen_mono = time.monotonic() - 20
        self.assertFalse(self.state.snapshot()["online"])
        self.assertEqual(self.request("/api/command", {"mode":"AUTO"})[0], 400)
        self.assertEqual(self.request("/api/command", {"mode":"OFF"})[0], 200)

    def test_invalid_payloads(self):
        invalid = [telemetry(level_percent=101), telemetry(level_percent=True), telemetry(pump="true"),
                   telemetry(level_percent=None), telemetry(rssi=-200), telemetry(extra=1),
                   telemetry(mode="ON"), telemetry(pump=True), telemetry(mode="AUTO", pump=True, fault="RUN_TIMEOUT"),
                   telemetry(uptime_s=True), telemetry(distance_cm=float("inf"))]
        for data in invalid:
            with self.subTest(data=data):
                self.assertEqual(self.request("/api/device/telemetry", data, "device-key")[0], 400)
        self.assertEqual(self.request("/api/command", raw="{")[0], 400)
        self.assertEqual(self.request("/api/command", raw='{"mode":NaN}')[0], 400)
        self.assertEqual(self.request("/api/command", raw="[]")[0], 400)
        self.assertEqual(self.request("/api/command", {"mode":"ON"})[0], 400)

    def test_sensor_fault_accepted_with_null_reading(self):
        data = telemetry(level_percent=None, distance_cm=None, fault="SENSOR_INVALID")
        self.assertEqual(self.request("/api/device/telemetry", data, "device-key")[0], 200)

    def test_simulator_endpoints_only_in_demo(self):
        self.assertEqual(self.request("/api/demo", {"scenario":"low"})[0], 404)
        self.state.demo = True
        self.assertEqual(self.request("/api/demo", {"scenario":"low"})[0], 200)
        self.assertEqual(self.state.scenario, "low")
        version = self.state.scenario_version
        self.assertEqual(self.request("/api/demo", {"scenario":"low"})[0], 200)
        self.assertEqual(self.state.scenario_version, version + 1)
        self.assertEqual(self.request("/api/demo", {"scenario":"reset"})[0], 200)
        self.assertTrue(self.state.reset_requested)
        self.assertEqual(self.request("/api/device/telemetry", telemetry(), "device-key")[0], 409)

    def test_static_path_traversal(self):
        self.assertEqual(self.request("/../app/server.py")[0], 404)
        self.assertEqual(self.request("/firmware/include/tank_config.h")[0], 404)

    def test_history_persists_and_boot_defaults_off(self):
        self.state.ingest(telemetry())
        reopened = TankState(Path(self.temp.name) / "test.db")
        try:
            self.assertEqual(len(reopened.snapshot()["history"]), 1)
            self.assertFalse(reopened.snapshot()["online"])
            self.assertEqual(reopened.desired_mode, "OFF")
        finally:
            reopened.close()

    def test_simulator_produces_valid_telemetry(self):
        self.state.demo = True
        stop = threading.Event()
        thread = threading.Thread(target=simulate, args=(self.state, stop))
        thread.start()
        deadline = time.monotonic() + 2
        try:
            while self.state.latest is None and time.monotonic() < deadline:
                stop.wait(0.01)
            validate_telemetry(self.state.latest)
            self.assertTrue(self.state.snapshot()["online"])
            self.assertFalse(self.state.latest["pump"])
        finally:
            stop.set()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
