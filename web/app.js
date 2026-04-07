"use strict";

const statusEl = document.getElementById("status");
const nodesEl = document.getElementById("nodes");
const logEl = document.getElementById("log-entries");
const statNodesEl = document.getElementById("stat-nodes");
const statSensorsEl = document.getElementById("stat-sensors");
const statChangedEl = document.getElementById("stat-changed");

const baseUrlInput = document.getElementById("base-url");
const refreshMsInput = document.getElementById("refresh-ms");
const applyBtn = document.getElementById("apply");

let timer = null;
let currentBaseUrl = null;

const nodeCards = new Map();
const sensorRows = new Map();
const previousSensorState = new Map();

const LOG_MAX = 300;
const logSeen = new Set();
const logBuffer = [];

function api(path) {
  return currentBaseUrl + path;
}

function setStatus(ok) {
  statusEl.textContent = ok ? "Connected" : "Disconnected";
  statusEl.style.color = ok ? "var(--accent)" : "var(--danger)";
}

function fmtTs(ts) {
  return new Date(ts).toLocaleTimeString();
}

function formatNumber(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return value;
  }
  return Number(value.toFixed(2));
}

function prettifySensorName(sensorId) {
  if (typeof sensorId !== "string" || sensorId.length === 0) {
    return String(sensorId);
  }

  const withoutIndex = sensorId.replace(/@\d+$/g, "");
  const normalized = withoutIndex
    .replace(/_/g, " ")
    .replace(/@/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  if (normalized.length === 0) {
    return sensorId;
  }

  return normalized
    .split(" ")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatValue(data) {
  const unit = data && data.meta && data.meta.unit ? String(data.meta.unit) : "";
  const rawValue = data ? data.value : null;
  const main = String(formatNumber(rawValue));
  if (!unit) {
    return `<span class="val-main">${main}</span>`;
  }
  return `<span class="val-main">${main}</span> <span class="val-unit">${unit}</span>`;
}

function plainValue(data) {
  const unit = data && data.meta && data.meta.unit ? " " + String(data.meta.unit) : "";
  const rawValue = data ? data.value : null;
  return String(formatNumber(rawValue)) + unit;
}

function sensorSignature(data) {
  const meta = data && data.meta && typeof data.meta === "object" ? data.meta : {};
  return JSON.stringify({
    value: data ? formatNumber(data.value) : null,
    unit: meta.unit ?? null,
    period_ms: meta.period_ms ?? null,
  });
}

function resetUI() {
  if (timer) {
    clearInterval(timer);
    timer = null;
  }

  nodesEl.innerHTML = "";
  logEl.innerHTML = "";

  nodeCards.clear();
  sensorRows.clear();
  logSeen.clear();
  logBuffer.length = 0;
  previousSensorState.clear();

  statNodesEl.textContent = "0";
  statSensorsEl.textContent = "0";
  statChangedEl.textContent = "0";

  setStatus(false);
}

function getNodeCard(nodeId) {
  let card = nodeCards.get(nodeId);
  if (card) {
    return card;
  }

  card = document.createElement("div");
  card.className = "node-card";
  card.innerHTML = `
    <div class="node-header">
      <h2>${nodeId}</h2>
      <span class="node-mark">idle</span>
    </div>
    <div class="sensors"></div>
  `;

  nodeCards.set(nodeId, card);
  nodesEl.appendChild(card);
  return card;
}

function getSensorRow(nodeId, sensorId) {
  const key = nodeId + "|" + sensorId;
  let row = sensorRows.get(key);
  if (row) {
    return row;
  }

  const card = getNodeCard(nodeId);
  const container = card.querySelector(".sensors");

  row = document.createElement("div");
  row.className = "sensor";
  row.innerHTML = `
    <span class="id"></span>
    <span class="val"></span>
    <span class="ts"></span>
  `;

  sensorRows.set(key, row);
  container.appendChild(row);
  return row;
}

function splitGlobalSensorId(globalId) {
  if (typeof globalId !== "string") {
    return null;
  }
  const idx = globalId.indexOf(":");
  if (idx <= 0) {
    return null;
  }
  return {
    origin: globalId.slice(0, idx),
    sensorId: globalId.slice(idx + 1),
  };
}

function normalizeGroupedByOrigin(payload) {
  if (!payload || typeof payload !== "object") {
    return {};
  }

  const topValues = Object.values(payload);
  let flatMap = null;

  if (topValues.length === 1 && topValues[0] && typeof topValues[0] === "object") {
    flatMap = topValues[0];
  } else {
    flatMap = {};
    for (const v of topValues) {
      if (v && typeof v === "object") {
        Object.assign(flatMap, v);
      }
    }
  }

  const grouped = {};
  for (const [globalId, rec] of Object.entries(flatMap)) {
    const parts = splitGlobalSensorId(globalId);
    if (!parts) {
      continue;
    }
    if (!grouped[parts.origin]) {
      grouped[parts.origin] = {};
    }
    grouped[parts.origin][parts.sensorId] = rec;
  }

  return grouped;
}

function pushLog(nodeId, sensorId, data) {
  const key = `${nodeId}|${sensorId}|${data.ts_ms}`;
  if (logSeen.has(key)) {
    return;
  }

  logSeen.add(key);
  logBuffer.unshift({
    ts: data.ts_ms,
    nodeId,
    sensorId: prettifySensorName(sensorId),
    value: plainValue(data),
  });

  while (logBuffer.length > LOG_MAX) {
    const e = logBuffer.pop();
    logSeen.delete(`${e.nodeId}|${e.sensorId}|${e.ts}`);
  }
}

function flushLog() {
  logEl.innerHTML = "";
  for (const e of logBuffer) {
    const line = document.createElement("div");
    line.className = "log-entry";
    line.textContent = `[${fmtTs(e.ts)}] ${e.nodeId} ${e.sensorId} -> ${e.value}`;
    logEl.appendChild(line);
  }
}

function renderState(rawState) {
  const state = normalizeGroupedByOrigin(rawState);
  const changedThisPoll = new Set();
  let sensorCount = 0;

  for (const card of nodeCards.values()) {
    card.classList.remove("active");
    const mark = card.querySelector(".node-mark");
    if (mark) {
      mark.textContent = "idle";
    }
  }

  for (const [nodeId, sensors] of Object.entries(state)) {
    for (const [sensorId, data] of Object.entries(sensors)) {
      const row = getSensorRow(nodeId, sensorId);
      const key = nodeId + "|" + sensorId;
      const signature = sensorSignature(data);
      const prev = previousSensorState.get(key);
      const isUpdated = !prev || prev !== signature;
      sensorCount += 1;

      previousSensorState.set(key, signature);

      row.querySelector(".id").textContent = prettifySensorName(sensorId);
      row.querySelector(".val").innerHTML = formatValue(data);
      row.querySelector(".ts").textContent = fmtTs(data.ts_ms);
      row.classList.toggle("updated", isUpdated);

      if (isUpdated) {
        changedThisPoll.add(key);
        pushLog(nodeId, sensorId, data);
        const card = nodeCards.get(nodeId);
        if (card) {
          card.classList.add("active");
          const mark = card.querySelector(".node-mark");
          if (mark) {
            mark.textContent = "active";
          }
        }
      }
    }
  }

  statNodesEl.textContent = String(Object.keys(state).length);
  statSensorsEl.textContent = String(sensorCount);
  statChangedEl.textContent = String(changedThisPoll.size);
}

async function poll() {
  try {
    const stateRes = await fetch(api("/api/state"), { cache: "no-store" });
    if (!stateRes.ok) {
      throw new Error("state fetch failed");
    }
    const rawState = await stateRes.json();
    renderState(rawState);
    flushLog();
    setStatus(true);
  } catch {
    setStatus(false);
  }
}

function start() {
  const newBase = baseUrlInput.value.replace(/\/+$/, "");
  if (newBase !== currentBaseUrl) {
    currentBaseUrl = newBase;
    resetUI();
  }

  const ms = Math.max(200, Number(refreshMsInput.value) || 1000);
  timer = setInterval(poll, ms);
  poll();
}

applyBtn.onclick = start;
start();
