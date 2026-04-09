"use strict";

const statusEl = document.getElementById("status");
const nodesLocalEl = document.getElementById("nodes-local");
const nodesRemoteEl = document.getElementById("nodes-remote");
const membershipBodyEl = document.getElementById("membership-body");
const logEl = document.getElementById("log-entries");
const statNodesEl = document.getElementById("stat-nodes");
const statSensorsEl = document.getElementById("stat-sensors");
const statPeersEl = document.getElementById("stat-peers");
const statSuspectedEl = document.getElementById("stat-suspected");
const statDeadEl = document.getElementById("stat-dead");
const statChangedEl = document.getElementById("stat-changed");

const baseUrlInput = document.getElementById("base-url");
const refreshMsInput = document.getElementById("refresh-ms");
const applyBtn = document.getElementById("apply");

let timer = null;
let currentBaseUrl = null;
let currentLocalNodeId = null;

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

  nodesLocalEl.innerHTML = "";
  nodesRemoteEl.innerHTML = "";
  logEl.innerHTML = "";

  nodeCards.clear();
  sensorRows.clear();
  logSeen.clear();
  logBuffer.length = 0;
  previousSensorState.clear();

  statNodesEl.textContent = "0";
  statSensorsEl.textContent = "0";
  statPeersEl.textContent = "0";
  statSuspectedEl.textContent = "0";
  statDeadEl.textContent = "0";
  statChangedEl.textContent = "0";
  membershipBodyEl.innerHTML = "";
  currentLocalNodeId = null;

  setStatus(false);
}

function placeNodeCard(nodeId, card) {
  const target = currentLocalNodeId && nodeId === currentLocalNodeId ? nodesLocalEl : nodesRemoteEl;
  if (target && card.parentElement !== target) {
    target.appendChild(card);
  }
}

function getNodeCard(nodeId) {
  let card = nodeCards.get(nodeId);
  if (card) {
    placeNodeCard(nodeId, card);
    return card;
  }

  card = document.createElement("div");
  card.className = "node-card";
  card.innerHTML = `
    <div class="node-header">
      <h2>${nodeId}</h2>
    </div>
    <div class="sensors"></div>
  `;

  nodeCards.set(nodeId, card);
  placeNodeCard(nodeId, card);
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

  for (const [nodeId, sensors] of Object.entries(state)) {
    const card = getNodeCard(nodeId);
    placeNodeCard(nodeId, card);
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
      }
    }
  }

  statNodesEl.textContent = String(Object.keys(state).length);
  statSensorsEl.textContent = String(sensorCount);
  statChangedEl.textContent = String(changedThisPoll.size);
}

function formatDeltaMs(lastHeartbeatTsMs) {
  if (typeof lastHeartbeatTsMs !== "number" || !Number.isFinite(lastHeartbeatTsMs)) {
    return "-";
  }
  const delta = Math.max(0, Date.now() - lastHeartbeatTsMs);
  return String(Math.round(delta));
}

function renderMembership(rawMembership) {
  const peers = rawMembership && Array.isArray(rawMembership.peers) ? rawMembership.peers : [];
  const localNodeId = rawMembership && typeof rawMembership.local_node_id === "string"
    ? rawMembership.local_node_id
    : null;
  currentLocalNodeId = localNodeId;
  membershipBodyEl.innerHTML = "";

  let suspected = 0;
  let dead = 0;

  const ordered = peers.slice().sort((a, b) => {
    const left = String(a && a.peer_id ? a.peer_id : "");
    const right = String(b && b.peer_id ? b.peer_id : "");
    return left.localeCompare(right);
  });

  for (const peer of ordered) {
    const status = typeof peer.status === "string" ? peer.status : "unknown";
    if (status === "suspected") {
      suspected += 1;
    } else if (status === "dead") {
      dead += 1;
    }

    const phi = typeof peer.phi === "number" && Number.isFinite(peer.phi) ? peer.phi.toFixed(3) : "-";
    const deltaMs = formatDeltaMs(peer.last_heartbeat_ts_ms);

    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${peer.peer_id || "-"}</td>
      <td><span class="member-status ${status}">${status}</span></td>
      <td>${phi}</td>
      <td><span class="heartbeat-delta ${status}">${deltaMs}</span></td>
    `;
    membershipBodyEl.appendChild(row);
  }

  statPeersEl.textContent = String(ordered.length);
  statSuspectedEl.textContent = String(suspected);
  statDeadEl.textContent = String(dead);

  for (const [nodeId, card] of nodeCards.entries()) {
    placeNodeCard(nodeId, card);
  }
}

async function poll() {
  try {
    const [stateRes, membershipRes] = await Promise.all([
      fetch(api("/api/state"), { cache: "no-store" }),
      fetch(api("/api/membership"), { cache: "no-store" }),
    ]);
    if (!stateRes.ok || !membershipRes.ok) {
      throw new Error("state fetch failed");
    }
    const [rawState, rawMembership] = await Promise.all([
      stateRes.json(),
      membershipRes.json(),
    ]);
    renderState(rawState);
    renderMembership(rawMembership);
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
