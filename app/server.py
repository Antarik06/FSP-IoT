"""Dependency-free LAN server, SQLite history, and hardware-free simulator."""
import argparse
import hmac
import json
import math
import os
from pathlib import Path
import secrets
import signal
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from app.control import Controller, START_PERCENT, STOP_PERCENT, CRITICAL_PERCENT

ROOT = Path(__file__).resolve().parent.parent
FAULTS = {None, "SENSOR_INVALID", "HIGH_FLOAT", "SOURCE_EMPTY", "OVERFLOW_RISK", "RUN_TIMEOUT"}
STALE_SECONDS = 15


def validate_telemetry(data):
    if not isinstance(data, dict):
        raise ValueError("Telemetry must be an object")
    required = {"level_percent", "distance_cm", "pump", "mode", "fault", "source_ok", "high_float_ok", "uptime_s", "rssi"}
    if set(data) != required:
        raise ValueError("Telemetry fields do not match the documented schema")
    for key, low, high in [("level_percent", 0, 100), ("distance_cm", 0, 500)]:
        value = data[key]
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high):
            raise ValueError(f"Invalid {key}")
    for key in ("pump", "source_ok", "high_float_ok"):
        if type(data[key]) is not bool:
            raise ValueError(f"{key} must be boolean")
    if data["mode"] not in ("AUTO", "OFF") or data["fault"] not in FAULTS:
        raise ValueError("Invalid mode or fault")
    for key, low, high in [("uptime_s", 0, 2**32), ("rssi", -127, 0)]:
        if type(data[key]) is not int or not low <= data[key] <= high:
            raise ValueError(f"Invalid {key}")
    if data["level_percent"] is None and data["fault"] != "SENSOR_INVALID":
        raise ValueError("Missing level must report SENSOR_INVALID")
    if data["pump"] and (data["fault"] or data["mode"] == "OFF" or not data["source_ok"]
                         or not data["high_float_ok"] or data["level_percent"] is None
                         or data["level_percent"] >= STOP_PERCENT):
        raise ValueError("Inconsistent pump safety state")
    return data


class TankState:
    def __init__(self, db_path, demo=False, dashboard_token=None, device_token=None):
        self.lock = threading.RLock()
        self.demo = demo
        self.dashboard_token = dashboard_token or secrets.token_urlsafe(32)
        self.device_token = device_token or secrets.token_urlsafe(32)
        self.desired_mode = "OFF"
        self.latest = None
        self.last_seen = None
        self.last_seen_mono = None
        self.scenario = "normal"
        self.scenario_version = 0
        self.reset_requested = False
        self.events = []
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS readings (id INTEGER PRIMARY KEY, timestamp REAL NOT NULL, payload TEXT NOT NULL)")
        self.db.commit()

    def event(self, message):
        self.events.insert(0, {"timestamp": time.time(), "message": message})
        del self.events[40:]

    def ingest(self, data):
        validate_telemetry(data)
        with self.lock:
            old = self.latest
            if old is None:
                self.event("Simulator connected" if self.demo else "ESP32 connected")
            elif self.last_seen_mono is not None and time.monotonic() - self.last_seen_mono > STALE_SECONDS:
                self.event("Device reconnected")
            if old is None or old["pump"] != data["pump"]:
                self.event("Pump started" if data["pump"] else "Pump stopped")
            if data["fault"] and (old is None or old["fault"] != data["fault"]):
                self.event("Protection triggered: " + data["fault"])
            elif old and old["fault"] and not data["fault"]:
                self.event("Fault reset at device")
            self.latest = dict(data)
            self.last_seen = time.time()
            self.last_seen_mono = time.monotonic()
            self.db.execute("INSERT INTO readings(timestamp,payload) VALUES (?,?)", (self.last_seen, json.dumps(data, allow_nan=False)))
            self.db.execute("DELETE FROM readings WHERE id <= (SELECT COALESCE(MAX(id),0)-10000 FROM readings)")
            self.db.commit()
            return {"mode": self.desired_mode}

    def snapshot(self):
        with self.lock:
            age = None if self.last_seen_mono is None else max(0, time.monotonic() - self.last_seen_mono)
            rows = self.db.execute("SELECT timestamp,payload FROM readings ORDER BY id DESC LIMIT 180").fetchall()
            history = [{"timestamp": stamp, "level_percent": json.loads(payload)["level_percent"]} for stamp, payload in reversed(rows)]
            return {"demo": self.demo, "online": age is not None and age < STALE_SECONDS,
                    "age_seconds": age, "last_seen": self.last_seen, "telemetry": self.latest,
                    "desired_mode": self.desired_mode, "scenario": self.scenario,
                    "thresholds": {"start": START_PERCENT, "stop": STOP_PERCENT, "critical": CRITICAL_PERCENT},
                    "history": history, "events": list(self.events)}

    def command(self, mode):
        if mode not in ("AUTO", "OFF"):
            raise ValueError("Mode must be AUTO or OFF")
        with self.lock:
            if mode == "AUTO" and (self.last_seen_mono is None or time.monotonic() - self.last_seen_mono >= STALE_SECONDS):
                raise ValueError("Device is offline. Automatic mode requires fresh telemetry.")
            self.desired_mode = mode
            self.event("Requested " + mode + " mode; awaiting device telemetry")

    def close(self):
        with self.lock:
            self.db.close()


def simulate(state, stop):
    controller = Controller(last_off=time.monotonic())
    level = 42.0
    previous_version = -1
    started = previous = time.monotonic()
    while not stop.is_set():
        now = time.monotonic()
        elapsed = min(now - previous, 2)
        previous = now
        with state.lock:
            controller.mode = state.desired_mode
            scenario = state.scenario
            scenario_version = state.scenario_version
            reset = state.reset_requested
            state.reset_requested = False
        if scenario_version != previous_version:
            if scenario == "low":
                level = 18.0
            elif scenario == "full":
                level = 92.0
            elif scenario == "normal":
                level = min(level, 85.0)
            previous_version = scenario_version
        level = max(0.0, min(100.0, level + (2.8 if controller.pump else -0.22) * elapsed))
        sensed = None if scenario == "sensor_fault" else round(level, 2)
        source_ok = scenario != "source_empty"
        high_ok = scenario != "high_float"
        controller.step(now, sensed, source_ok=source_ok, high_float_ok=high_ok, reset=reset)
        state.ingest({"level_percent": sensed, "distance_cm": None if sensed is None else round(120 - sensed, 2),
                      "pump": controller.pump, "mode": controller.mode, "fault": controller.fault,
                      "source_ok": source_ok, "high_float_ok": high_ok,
                      "uptime_s": int(now - started), "rssi": -48})
        stop.wait(1)


class TankHTTPServer(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True

    def __init__(self, address, state):
        self.state = state
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "TankMonitor/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format, *args):
        # Never log headers or authentication tokens.
        pass

    def reply(self, code, body, content_type="application/json"):
        raw = json.dumps(body, allow_nan=False).encode() if content_type == "application/json" else body
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def authenticated(self, device=False):
        token = self.server.state.device_token if device else self.server.state.dashboard_token
        supplied = self.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied.encode(), ("Bearer " + token).encode()):
            self.reply(401, {"error": "Enter the dashboard access token printed in the server terminal." if not device else "Invalid device token"})
            return False
        return True

    def read_json(self):
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            raise ValueError("Content-Type must be application/json")
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 4096:
            raise ValueError("JSON body must be 1–4096 bytes")
        data = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite JSON value")))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            self.reply(200, {"status": "ok"})
        elif path == "/api/state":
            if self.authenticated():
                self.reply(200, self.server.state.snapshot())
        else:
            files = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8"), "/favicon.ico": None}
            asset = files.get(path)
            if asset:
                self.reply(200, (ROOT / "web" / asset[0]).read_bytes(), asset[1])
            elif path == "/favicon.ico":
                self.reply(204, b"", "image/x-icon")
            else:
                self.reply(404, {"error": "Not found"})

    def do_POST(self):
        path = urlsplit(self.path).path
        device = path == "/api/device/telemetry"
        if not self.authenticated(device=device):
            return
        try:
            data = self.read_json()
            state = self.server.state
            if device:
                if state.demo:
                    self.reply(409, {"error": "Device ingestion is disabled during simulation. Restart without --demo."})
                    return
                result = state.ingest(data)
            elif path == "/api/command":
                if set(data) != {"mode"}:
                    raise ValueError("Expected only mode")
                state.command(data["mode"])
                result = {"accepted": True, "desired_mode": data["mode"]}
            elif path == "/api/demo" and state.demo:
                if set(data) != {"scenario"} or data["scenario"] not in ("normal", "low", "full", "sensor_fault", "source_empty", "high_float", "reset"):
                    raise ValueError("Invalid simulator scenario")
                with state.lock:
                    if data["scenario"] == "reset":
                        state.reset_requested = True
                    else:
                        state.scenario = data["scenario"]
                        state.scenario_version += 1
                    state.event("Demo action: " + data["scenario"])
                result = {"accepted": True}
            else:
                self.reply(404, {"error": "Not found"})
                return
            self.reply(200, result)
        except (ValueError, TypeError, KeyError) as error:
            self.reply(400, {"error": str(error)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Run simulated tank; no ESP32 required")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", type=Path, help="SQLite path; demo/live default to separate files")
    args = parser.parse_args()
    dashboard_token = os.environ.get("TANK_DASHBOARD_TOKEN")
    device_token = os.environ.get("TANK_DEVICE_TOKEN")
    if not args.demo and (not device_token or len(device_token) < 24):
        parser.error("Live mode requires TANK_DEVICE_TOKEN with at least 24 characters; see README.md")
    if dashboard_token and len(dashboard_token) < 24:
        parser.error("TANK_DASHBOARD_TOKEN must contain at least 24 characters")
    db_path = args.db or ROOT / "data" / ("demo.sqlite3" if args.demo else "tank.sqlite3")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    state = TankState(db_path, args.demo, dashboard_token, device_token)
    server = TankHTTPServer((args.host, args.port), state)
    stop = threading.Event()
    simulation = threading.Thread(target=simulate, args=(state, stop), daemon=True) if args.demo else None
    if simulation:
        simulation.start()
    print(f"\nSmart Water Tank · {'SIMULATOR' if args.demo else 'LIVE ESP32'}", flush=True)
    print(f"Dashboard: http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{server.server_port}", flush=True)
    print(f"Dashboard access token: {state.dashboard_token}\n", flush=True)
    print("Pump starts in OFF mode. Use Resume automatic after checking the installation.", flush=True)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if simulation:
            simulation.join(timeout=5)
        server.server_close()
        state.close()


if __name__ == "__main__":
    main()
