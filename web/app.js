"use strict";
const $ = (id) => document.getElementById(id);
let token = sessionStorage.getItem("tank-token") || "";
let lastState = null;
let busy = false;
let toastTimer;
const faultLabels = {SENSOR_INVALID:"Sensor unavailable", HIGH_FLOAT:"High-water float tripped", SOURCE_EMPTY:"Source tank empty", OVERFLOW_RISK:"Critical water level", RUN_TIMEOUT:"Maximum run time exceeded"};
function notify(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, 4500);
}
async function api(path, body) {
  const response = await fetch(path, {method: body ? "POST" : "GET", headers: {Authorization:`Bearer ${token}`, ...(body ? {"Content-Type":"application/json"} : {})}, ...(body ? {body:JSON.stringify(body)} : {}), signal:AbortSignal.timeout(5000)});
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401) {
      $("login-overlay").hidden = false;
      sessionStorage.removeItem("tank-token");
      token = "";
    }
    throw new Error(data.error || "Request failed");
  }
  return data;
}
function formatTime(timestamp) { return new Date(timestamp * 1000).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit",second:"2-digit"}); }
function text(id, value) { $(id).textContent = value; }
function field(id, ok, positive, negative) {
  text(id, ok === undefined ? "—" : ok ? positive : negative);
  $(id).classList.toggle("bad", ok === false);
}
function drawChart(history) {
  const rows = history.slice(-180);
  if (!rows.length) return;
  const start = rows[0].timestamp;
  const span = Math.max(1, rows[rows.length - 1].timestamp - start);
  const segments = [];
  let segment = [];
  let previousTime = null;
  for (const row of rows) {
    if (row.level_percent === null || (previousTime !== null && row.timestamp - previousTime > 15)) {
      if (segment.length) segments.push(segment);
      segment = [];
    }
    if (row.level_percent !== null) segment.push([45 + (row.timestamp - start) / span * 655, 180 - row.level_percent / 100 * 160]);
    previousTime = row.timestamp;
  }
  if (segment.length) segments.push(segment);
  const path = (points) => points.map(([x,y],i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  $("chart-line").setAttribute("d", segments.map(path).join(" "));
  $("chart-area").setAttribute("d", segments.map(s => `${path(s)} L${s[s.length-1][0].toFixed(1)} 180 L${s[0][0].toFixed(1)} 180 Z`).join(" "));
  text("chart-start", formatTime(start));
  text("chart-end", formatTime(rows[rows.length - 1].timestamp));
  $("chart").setAttribute("aria-label", `Water level history, ${rows.length} readings from ${formatTime(start)} to ${formatTime(rows[rows.length-1].timestamp)}`);
}
function render(state) {
  lastState = state;
  const t = state.telemetry;
  const valid = t && t.level_percent !== null;
  const level = valid ? t.level_percent : null;
  const online = state.online;
  text("environment", state.demo ? "SIMULATOR" : "ESP32 · LIVE");
  $("connection-dot").className = `status-dot${online ? " online" : ""}`;
  $("connection-text").replaceChildren(document.createTextNode(online ? (state.demo ? "Simulator connected" : "Device connected") : "Device offline"));
  const subtitle = document.createElement("small");
  subtitle.textContent = online ? "Updates every 2 seconds" : state.age_seconds === null ? "Waiting for first upload" : `Last seen ${Math.floor(state.age_seconds)}s ago`;
  $("connection-text").append(subtitle);
  text("level", valid ? Math.round(level) : "—");
  text("level-caption", !online ? "Last known reading" : !valid ? "Sensor unavailable" : level >= 90 ? "Tank is full" : level <= 25 ? "Low water level" : "Water level healthy");
  text("tank-status", !online ? "Offline" : t?.fault ? "Protection active" : "Monitoring");
  $("tank-status").classList.toggle("danger", !online || Boolean(t?.fault));
  const waterY = 229 - (level ?? 0) / 100 * 204;
  $("water").setAttribute("y", waterY);
  $("water").setAttribute("height", 229 - waterY);
  $("water-surface").setAttribute("d", valid ? `M29 ${waterY} Q69 ${waterY-5} 109 ${waterY} T189 ${waterY} V${waterY+5} Q149 ${waterY+10} 109 ${waterY+5} T29 ${waterY+5}Z` : "");
  $("tank-svg").setAttribute("aria-label", valid ? `Tank ${Math.round(level)} percent full${online ? "" : ", last known reading"}` : "Tank level unavailable");
  text("distance", t?.distance_cm != null ? `${t.distance_cm.toFixed(1)} cm` : "— cm");
  text("last-received", state.last_seen ? formatTime(state.last_seen) : "—");
  text("pump", !online ? "Pump state unknown" : t?.pump ? "Pump is running" : "Pump is off");
  text("mode", `Reported mode: ${t?.mode ?? "—"}${!online && t ? " (stale)" : ""}`);
  $("pump-dot").className = `status-dot${online && t?.pump ? " running" : ""}`;
  field("high-float", online ? t?.high_float_ok : undefined, "Healthy", "Tripped / disconnected");
  field("source", online ? t?.source_ok : undefined, "Available", "Empty / disconnected");
  text("fault", t ? (t.fault ? faultLabels[t.fault] || t.fault : "Clear") + (!online ? " (stale)" : "") : "—");
  $("fault").classList.toggle("bad", Boolean(t?.fault));
  text("rssi", t ? `${t.rssi} dBm${online ? "" : " · stale"}` : "— dBm");
  const uptime = t?.uptime_s ?? 0;
  text("uptime", t ? `${Math.floor(uptime/3600)}h ${Math.floor(uptime%3600/60)}m${online ? "" : " · stale"}` : "—");
  $("auto").disabled = busy || !online || Boolean(t?.fault);
  $("off").disabled = busy;
  const pending = t?.mode !== state.desired_mode || !online;
  text("command-status", pending ? `Requested: ${state.desired_mode}. Awaiting device confirmation.` : `Applied: ${state.desired_mode}. ${state.desired_mode === "AUTO" ? "Fills at 25%, stops at 90%." : "Automatic filling is paused."}`);
  const alert = !online ? "Device is offline. Readings are stale and remote commands cannot confirm a stop. Local protection continues on a powered ESP32; use the physical disconnect when needed." : t?.fault ? `${faultLabels[t.fault] || t.fault}. Pump disabled. Fix the cause, collect three valid readings below 90%, then press the local reset button.` : "";
  text("alert", alert);
  $("alert").hidden = !alert;
  drawChart(state.history);
  $("events").replaceChildren(...state.events.slice(0, 15).map(event => {
    const li = document.createElement("li");
    li.append(document.createTextNode(event.message));
    const time = document.createElement("time");
    time.dateTime = new Date(event.timestamp * 1000).toISOString();
    time.textContent = formatTime(event.timestamp);
    li.append(time);
    return li;
  }));
  $("demo-panel").hidden = !state.demo;
  document.querySelectorAll("[data-scenario]").forEach(button => {
    button.classList.toggle("active", button.dataset.scenario === state.scenario);
    button.disabled = busy;
  });
}
async function refresh() {
  if (!token) return;
  const state = await api("/api/state");
  $("login-overlay").hidden = true;
  render(state);
}
function connectionFailure() {
  if (lastState) render({...lastState, online:false});
  text("alert", "Dashboard server is unreachable. Displayed readings are stale. Device operation cannot be confirmed; local protection remains on the ESP32 while it is powered.");
  $("alert").hidden = false;
  $("auto").disabled = true;
}
async function command(path, body) {
  busy = true;
  if (lastState) render(lastState);
  try {
    await api(path, body);
    notify(path === "/api/command" ? "Request queued. Waiting for device confirmation." : "Simulator action queued.");
  } catch (error) { notify(error.message); }
  finally {
    busy = false;
    try { await refresh(); } catch { connectionFailure(); }
  }
}
$("login-form").addEventListener("submit", async event => {
  event.preventDefault();
  token = $("token").value.trim();
  text("login-error", "");
  try {
    await refresh();
    sessionStorage.setItem("tank-token", token);
    $("token").value = "";
  } catch (error) { text("login-error", error.message); }
});
$("sign-out").addEventListener("click", () => {
  token = "";
  sessionStorage.removeItem("tank-token");
  $("login-overlay").hidden = false;
  $("token").focus();
});
$("auto").addEventListener("click", () => command("/api/command", {mode:"AUTO"}));
$("off").addEventListener("click", () => command("/api/command", {mode:"OFF"}));
document.querySelectorAll("[data-scenario]").forEach(button => button.addEventListener("click", () => command("/api/demo", {scenario:button.dataset.scenario})));
async function poll() {
  try { await refresh(); } catch { if (token) connectionFailure(); }
  setTimeout(poll, 2000);
}
poll();
