"use strict";

const IMPORTANT_EVENT_PATTERNS = [
  "full_sync",
  "delta_unavailable",
  "dead",
  "suspected",
  "join",
  "leave",
  "error",
  "timeout",
  "reconcile",
  "partition",
];

const API_ENDPOINTS = {
  introspection: "/api/introspection",
  // Backward-compat marker for UI semantics tests and legacy clients.
  membership: "/api/membership",
};

const METRIC_KEYS = [];
const SCROLL_RESTORE_KEY = "cluster_ui_scroll_y";
const SCROLL_RESTORE_WINDOW_NAME_KEY = "__cluster_ui_scroll__";
const MAX_SCROLL_RESTORE_ATTEMPTS = 40;
let pendingScrollRestore = null;
let scrollRestoreAttempts = 0;

function deriveInitialBaseUrl() {
  try {
    if (typeof window === "undefined" || !window.location) {
      return "http://localhost:10000";
    }
    const { protocol, hostname, port } = window.location;
    if (!protocol || !hostname) {
      return "http://localhost:10000";
    }
    if (port) {
      return `${protocol}//${hostname}:${port}`;
    }
    return `${protocol}//${hostname}`;
  } catch {
    return "http://localhost:10000";
  }
}

const INITIAL_BASE_URL = deriveInitialBaseUrl();

const state = {
  baseUrl: INITIAL_BASE_URL,
  pollMs: 1000,
  timer: null,
  isPolling: false,
  pollSession: 0,
  selectedNodeId: null,
  cluster: null,
  endpointByNodeId: new Map(),
  layoutPositions: new Map(),
  activeLinkKeys: new Set(),
  lastRenderBounds: null,
};

const els = {
  status: document.getElementById("connection-status"),
  baseUrl: document.getElementById("base-url"),
  pollMs: document.getElementById("poll-ms"),
  apply: document.getElementById("apply"),
  snapshotTime: document.getElementById("snapshot-time"),
  metricsStrip: document.getElementById("metrics-strip"),
  topologyHint: document.getElementById("topology-hint"),
  topologyCanvas: document.getElementById("topology-canvas"),
  inspectorSummary: document.getElementById("inspector-summary"),
  inspectorPeers: document.getElementById("inspector-peers"),
  globalStateSummary: document.getElementById("global-state-summary"),
  globalStateCards: document.getElementById("global-state-cards"),
  sensorCount: document.getElementById("sensor-count"),
  sensorTable: document.getElementById("sensor-table"),
  timeline: document.getElementById("timeline"),
};

function saveScrollPositionForNavigation() {
  try {
    if (typeof window === "undefined") {
      return;
    }
    const scrollY = Math.max(0, window.scrollY || 0);
    const doc = document.documentElement;
    const maxY = Math.max(0, doc.scrollHeight - window.innerHeight);
    const ratio = maxY > 0 ? Math.min(1, scrollY / maxY) : 0;
    const payload = JSON.stringify({ y: scrollY, ratio });
    if (window.sessionStorage) {
      window.sessionStorage.setItem(SCROLL_RESTORE_KEY, payload);
    }
    // Cross-port handoff in the same browser tab without touching URL.
    const bag = {};
    if (typeof window.name === "string" && window.name) {
      try {
        const parsed = JSON.parse(window.name);
        if (parsed && typeof parsed === "object") {
          Object.assign(bag, parsed);
        }
      } catch {
        // Ignore non-JSON window.name.
      }
    }
    bag[SCROLL_RESTORE_WINDOW_NAME_KEY] = { y: scrollY, ratio };
    window.name = JSON.stringify(bag);
  } catch {
    // Best-effort only.
  }
}

function restoreScrollPositionAfterNavigation() {
  try {
    if (typeof window === "undefined") {
      return;
    }
    // First choice: cross-port handoff from window.name in same tab.
    if (typeof window.name === "string" && window.name) {
      try {
        const bag = JSON.parse(window.name);
        if (bag && typeof bag === "object" && bag[SCROLL_RESTORE_WINDOW_NAME_KEY]) {
          const saved = bag[SCROLL_RESTORE_WINDOW_NAME_KEY];
          const y = Number(saved && saved.y);
          const ratio = Number(saved && saved.ratio);
          if (Number.isFinite(y) && y >= 0) {
            pendingScrollRestore = {
              y: Math.round(y),
              ratio: Number.isFinite(ratio) ? Math.max(0, Math.min(1, ratio)) : null,
            };
            scrollRestoreAttempts = 0;
          }
          delete bag[SCROLL_RESTORE_WINDOW_NAME_KEY];
          window.name = JSON.stringify(bag);
          return;
        }
      } catch {
        // Ignore non-JSON window.name.
      }
    }

    // Fallback: same-origin navigation.
    if (!window.sessionStorage) {
      return;
    }
    const raw = window.sessionStorage.getItem(SCROLL_RESTORE_KEY);
    if (raw === null) {
      return;
    }
    window.sessionStorage.removeItem(SCROLL_RESTORE_KEY);
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch {
      parsed = { y: Number(raw), ratio: null };
    }
    const y = Number(parsed && parsed.y);
    const ratio = Number(parsed && parsed.ratio);
    if (!Number.isFinite(y) || y < 0) {
      return;
    }
    pendingScrollRestore = {
      y: Math.round(y),
      ratio: Number.isFinite(ratio) ? Math.max(0, Math.min(1, ratio)) : null,
    };
    scrollRestoreAttempts = 0;
  } catch {
    // Best-effort only.
  }
}

function tryRestoreScrollPosition() {
  if (!pendingScrollRestore || typeof window === "undefined" || typeof document === "undefined") {
    return;
  }
  const maxY = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
  const desiredY = Math.max(0, pendingScrollRestore.y);
  const targetY = Math.min(desiredY, maxY);
  window.scrollTo(0, targetY);

  const closeEnough = Math.abs((window.scrollY || 0) - targetY) <= 2;
  const pageIsTallEnough = maxY >= desiredY;
  if ((closeEnough && pageIsTallEnough) || scrollRestoreAttempts >= MAX_SCROLL_RESTORE_ATTEMPTS) {
    pendingScrollRestore = null;
    scrollRestoreAttempts = 0;
    return;
  }
  scrollRestoreAttempts += 1;
  window.setTimeout(tryRestoreScrollPosition, 50);
}

function setConnection(ok, message) {
  els.status.className = `status ${ok ? "connected" : "disconnected"}`;
  els.status.textContent = message;
}

function formatTimestamp(tsMs) {
  if (typeof tsMs !== "number" || !Number.isFinite(tsMs)) {
    return "-";
  }
  return new Date(tsMs).toLocaleString();
}

function formatCompactNumber(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 }).format(value);
}

function formatSensorValue(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? formatCompactNumber(value) : "-";
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed ? trimmed : "-";
  }
  try {
    const serialized = JSON.stringify(value);
    return serialized || "-";
  } catch {
    return String(value);
  }
}

function updateTopologyHintText(baseText) {
  els.topologyHint.textContent = `${baseText} | click a node to switch API target`;
}

function toStatusClass(raw) {
  const text = String(raw || "unknown").toLowerCase();
  return text.replace(/[^a-z0-9]+/g, "-");
}

function renderStatusPill(statusText) {
  const label = statusText || "unknown";
  const cls = toStatusClass(label);
  return `<span class="status-pill ${cls}">${label}</span>`;
}

function nodeSort(a, b) {
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
}

function normalizeCluster(payload) {
  const root = payload && typeof payload === "object" ? payload : {};
  const cluster = root.cluster && typeof root.cluster === "object" ? root.cluster : {};
  const topology = cluster.topology && typeof cluster.topology === "object" ? cluster.topology : {};
  const membership = cluster.membership && typeof cluster.membership === "object" ? cluster.membership : {};
  const sensorState = cluster.sensor_state && typeof cluster.sensor_state === "object" ? cluster.sensor_state : {};
  const events = cluster.events && typeof cluster.events === "object" ? cluster.events : {};
  const metrics = cluster.metrics && typeof cluster.metrics === "object" ? cluster.metrics : {};
  return {
    schemaVersion: root.schema_version || "unknown",
    generatedAtMs: root.generated_at_ms,
    topology,
    membership,
    sensorState,
    events,
    metrics,
  };
}

function createMembershipMap(membership) {
  const map = new Map();
  const peers = Array.isArray(membership.peers) ? membership.peers : [];
  for (const peer of peers) {
    if (!peer || typeof peer !== "object") {
      continue;
    }
    const peerId = typeof peer.peer_id === "string" ? peer.peer_id : "";
    if (!peerId) {
      continue;
    }
    map.set(peerId, peer);
  }
  return map;
}

function getNodeStatus(nodeId, localNodeId, membershipMap) {
  if (nodeId === localNodeId) {
    return "local";
  }
  const peer = membershipMap.get(nodeId);
  if (!peer) {
    return "unknown";
  }
  const display = typeof peer.display_status === "string" ? peer.display_status : "unknown";
  if (display === "alive_direct") {
    return "alive-direct";
  }
  if (display === "alive_indirect") {
    return "alive-indirect";
  }
  if (display === "suspected") {
    return "suspected";
  }
  if (display === "dead") {
    return "dead";
  }
  return "unknown";
}

function buildGraphModel(cluster) {
  const topology = cluster.topology;
  const adjacency = topology && typeof topology.adjacency === "object" ? topology.adjacency : {};
  const localNodeId = typeof cluster.membership.local_node_id === "string" ? cluster.membership.local_node_id : "";
  const membershipMap = createMembershipMap(cluster.membership);
  const nodeSet = new Set();

  for (const nodeId of Object.keys(adjacency)) {
    nodeSet.add(nodeId);
    const neighbors = Array.isArray(adjacency[nodeId]) ? adjacency[nodeId] : [];
    for (const nb of neighbors) {
      if (typeof nb === "string" && nb) {
        nodeSet.add(nb);
      }
    }
  }

  if (localNodeId) {
    nodeSet.add(localNodeId);
  }

  for (const peerId of membershipMap.keys()) {
    nodeSet.add(peerId);
  }

  const nodes = Array.from(nodeSet).sort(nodeSort).map((id) => ({
    id,
    status: getNodeStatus(id, localNodeId, membershipMap),
  }));

  const linkKey = new Set();
  const links = [];

  for (const [from, neighborsRaw] of Object.entries(adjacency)) {
    const neighbors = Array.isArray(neighborsRaw) ? neighborsRaw : [];
    for (const to of neighbors) {
      if (typeof to !== "string" || !to) {
        continue;
      }
      const left = from < to ? from : to;
      const right = from < to ? to : from;
      const key = `${left}::${right}`;
      if (linkKey.has(key)) {
        continue;
      }
      linkKey.add(key);
      links.push({ source: left, target: right });
    }
  }

  links.sort((a, b) => {
    const x = `${a.source}|${a.target}`;
    const y = `${b.source}|${b.target}`;
    return x.localeCompare(y, undefined, { numeric: true, sensitivity: "base" });
  });

  const deadNodeIds = new Set(
    nodes.filter((n) => n.status === "dead").map((n) => n.id),
  );
  const activeLinks = [];
  const inactiveLinks = [];
  for (const link of links) {
    if (deadNodeIds.has(link.source) || deadNodeIds.has(link.target)) {
      inactiveLinks.push(link);
    } else {
      activeLinks.push(link);
    }
  }

  const activeDegree = new Map();
  for (const node of nodes) {
    activeDegree.set(node.id, 0);
  }
  for (const link of activeLinks) {
    activeDegree.set(link.source, (activeDegree.get(link.source) || 0) + 1);
    activeDegree.set(link.target, (activeDegree.get(link.target) || 0) + 1);
  }
  const isolatedNodeIds = new Set(
    nodes
      .filter((n) => n.status !== "dead" && (activeDegree.get(n.id) || 0) === 0)
      .map((n) => n.id),
  );

  return {
    nodes,
    links,
    activeLinks,
    inactiveLinks,
    isolatedNodeIds,
    localNodeId,
    membershipMap,
  };
}

function getCanvasSize(canvas) {
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(640, Math.floor(rect.width));
  const height = Math.max(420, Math.floor(rect.height));
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.floor(width * ratio);
  canvas.height = Math.floor(height * ratio);
  return { width, height, ratio };
}

function layoutNodes(graph, width, height) {
  const margin = 30;
  const nodes = graph.nodes;
  const count = nodes.length;
  if (count === 0) {
    return new Map();
  }

  const positions = new Map();
  const cx = width / 2;
  const cy = height / 2;
  const innerW = Math.max(120, width - margin * 2);
  const innerH = Math.max(120, height - margin * 2);

  if (count <= 20) {
    const radius = Math.min(innerW, innerH) * 0.44;
    for (let i = 0; i < count; i += 1) {
      const angle = (2 * Math.PI * i) / count - Math.PI / 2;
      positions.set(nodes[i].id, {
        x: cx + Math.cos(angle) * radius,
        y: cy + Math.sin(angle) * radius,
      });
    }
    return positions;
  }

  if (count <= 80) {
    const perRing = Math.max(10, Math.ceil(count / 3));
    for (let i = 0; i < count; i += 1) {
      const ring = Math.floor(i / perRing);
      const idxInRing = i % perRing;
      const ringCount = Math.min(perRing, count - ring * perRing);
      const angle = (2 * Math.PI * idxInRing) / Math.max(1, ringCount) - Math.PI / 2;
      const radius = Math.min(innerW, innerH) * (0.22 + ring * 0.18);
      positions.set(nodes[i].id, {
        x: cx + Math.cos(angle) * radius,
        y: cy + Math.sin(angle) * radius,
      });
    }
    return positions;
  }

  const cols = Math.max(8, Math.ceil(Math.sqrt(count * 1.7)));
  const rows = Math.ceil(count / cols);
  const cellW = innerW / cols;
  const cellH = innerH / Math.max(1, rows);

  for (let i = 0; i < count; i += 1) {
    const col = i % cols;
    const row = Math.floor(i / cols);
    positions.set(nodes[i].id, {
      x: margin + col * cellW + cellW / 2,
      y: margin + row * cellH + cellH / 2,
    });
  }

  return positions;
}

function pickLinksToDraw(links, selectedNodeId, localNodeId, nodeCount) {
  const maxLinks = nodeCount > 120 ? 350 : nodeCount > 60 ? 550 : 900;
  if (links.length <= maxLinks) {
    return { visible: links, hiddenCount: 0 };
  }

  const priority = [];
  const secondary = [];
  for (const link of links) {
    const touchesSelected = selectedNodeId && (link.source === selectedNodeId || link.target === selectedNodeId);
    const touchesLocal = localNodeId && (link.source === localNodeId || link.target === localNodeId);
    if (touchesSelected || touchesLocal) {
      priority.push(link);
    } else {
      secondary.push(link);
    }
  }

  const visible = priority.slice(0, maxLinks);
  if (visible.length < maxLinks) {
    const remaining = maxLinks - visible.length;
    const stride = Math.max(1, Math.floor(secondary.length / remaining));
    for (let i = 0; i < secondary.length && visible.length < maxLinks; i += stride) {
      visible.push(secondary[i]);
    }
  }

  return { visible, hiddenCount: links.length - visible.length };
}

function statusColor(status) {
  switch (status) {
    case "local":
      return "#f7f7f2";
    case "alive-direct":
      return "#5fb98a";
    case "alive-indirect":
      return "#8fd3bc";
    case "suspected":
      return "#f6b04d";
    case "dead":
      return "#d96f66";
    default:
      return "#8f9aa8";
  }
}

function drawTopology(graph) {
  const canvas = els.topologyCanvas;
  const ctx = canvas.getContext("2d");
  const { width, height, ratio } = getCanvasSize(canvas);
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const layout = layoutNodes(graph, width, height);
  state.layoutPositions = layout;

  const pickedActive = pickLinksToDraw(graph.activeLinks, state.selectedNodeId, graph.localNodeId, graph.nodes.length);
  const pickedInactive = pickLinksToDraw(graph.inactiveLinks, state.selectedNodeId, graph.localNodeId, graph.nodes.length);

  ctx.setLineDash([4, 4]);
  ctx.strokeStyle = "rgba(150, 150, 150, 0.45)";
  ctx.lineWidth = 1;
  for (const link of pickedInactive.visible) {
    const a = layout.get(link.source);
    const b = layout.get(link.target);
    if (!a || !b) {
      continue;
    }
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  }
  ctx.setLineDash([]);

  ctx.strokeStyle = "rgba(177, 214, 244, 0.55)";
  ctx.lineWidth = graph.nodes.length <= 20 ? 2 : 1;
  for (const link of pickedActive.visible) {
    const a = layout.get(link.source);
    const b = layout.get(link.target);
    if (!a || !b) {
      continue;
    }
    const touchesSelected = state.selectedNodeId && (link.source === state.selectedNodeId || link.target === state.selectedNodeId);
    if (touchesSelected) {
      ctx.strokeStyle = "rgba(255, 245, 191, 0.92)";
      ctx.lineWidth = graph.nodes.length <= 20 ? 3 : 2;
    } else {
      ctx.strokeStyle = "rgba(177, 214, 244, 0.52)";
      ctx.lineWidth = graph.nodes.length <= 20 ? 2 : 1;
    }
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  }

  const showLabels = graph.nodes.length <= 60;
  for (const node of graph.nodes) {
    const pos = layout.get(node.id);
    if (!pos) {
      continue;
    }

    const isSelected = node.id === state.selectedNodeId;
    const radius = graph.nodes.length <= 20
      ? (isSelected ? 11 : 9)
      : (isSelected ? 8 : 6);

    ctx.fillStyle = statusColor(node.status);
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, radius, 0, Math.PI * 2);
    ctx.fill();

    if (isSelected) {
      ctx.strokeStyle = "#fff5bf";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, radius + 5, 0, Math.PI * 2);
      ctx.stroke();
    }
    if (graph.isolatedNodeIds.has(node.id)) {
      ctx.strokeStyle = "#ffd89c";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(pos.x, pos.y, radius + 9, 0, Math.PI * 2);
      ctx.stroke();
    }

    if (showLabels || isSelected || node.id === graph.localNodeId) {
      ctx.fillStyle = "#d7e2f0";
      ctx.font = graph.nodes.length <= 20 ? "14px 'IBM Plex Mono'" : "12px 'IBM Plex Mono'";
      ctx.fillText(node.id, pos.x + 12, pos.y - 12);
    }
  }

  const renderedLinks = pickedActive.visible.length + pickedInactive.visible.length;
  const totalLinks = graph.links.length;
  const hintBase = totalLinks > renderedLinks
    ? `${graph.nodes.length} nodes, ${totalLinks} links (${renderedLinks} rendered)`
    : `${graph.nodes.length} nodes, ${totalLinks} links`;
  updateTopologyHintText(hintBase);

  state.lastRenderBounds = { width, height };
}

function linkKey(link) {
  const a = link.source < link.target ? link.source : link.target;
  const b = link.source < link.target ? link.target : link.source;
  return `${a}::${b}`;
}

function findClosestNode(canvasX, canvasY) {
  let best = null;
  for (const [nodeId, pos] of state.layoutPositions.entries()) {
    const dx = pos.x - canvasX;
    const dy = pos.y - canvasY;
    const distSq = dx * dx + dy * dy;
    if (best === null || distSq < best.distSq) {
      best = { nodeId, distSq };
    }
  }
  if (!best || best.distSq > 18 * 18) {
    return null;
  }
  return best.nodeId;
}

function extractSeqVersion(record) {
  const meta = record && typeof record.meta === "object" ? record.meta : {};
  const candidates = [
    meta.seq,
    meta.version,
    meta.cursor,
    meta.last_seq,
    meta.seq_no,
    record.seq,
    record.version,
  ];
  for (const candidate of candidates) {
    if (candidate === null || candidate === undefined) {
      continue;
    }
    if (typeof candidate === "number" || typeof candidate === "string") {
      return String(candidate);
    }
  }
  return "-";
}

function renderSensorTable(cluster) {
  const records = Array.isArray(cluster.sensorState.records) ? cluster.sensorState.records : [];
  const selected = state.selectedNodeId;
  const filtered = selected
    ? records.filter((r) => r && typeof r.origin === "string" && r.origin === selected)
    : records;

  filtered.sort((a, b) => {
    const left = `${a.origin || ""}|${a.sensor_id || ""}`;
    const right = `${b.origin || ""}|${b.sensor_id || ""}`;
    return left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" });
  });

  els.sensorCount.textContent = `${filtered.length} records${selected ? ` (origin: ${selected})` : ""}`;
  els.sensorTable.innerHTML = "";

  const maxRows = 600;
  const rows = filtered.slice(0, maxRows);
  for (const record of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${record.global_sensor_id || "-"}</td>
      <td>${record.origin || "-"}</td>
      <td>${record.sensor_id || "-"}</td>
      <td>${formatSensorValue(record.value)}</td>
      <td>${formatTimestamp(record.ts_ms)}</td>
      <td>${extractSeqVersion(record)}</td>
    `;
    els.sensorTable.appendChild(tr);
  }

  if (filtered.length > maxRows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="6">Showing ${maxRows} of ${filtered.length} rows for readability.</td>`;
    els.sensorTable.appendChild(tr);
  }
}

function eventPriority(eventType) {
  const type = String(eventType || "").toLowerCase();
  for (let i = 0; i < IMPORTANT_EVENT_PATTERNS.length; i += 1) {
    if (type.includes(IMPORTANT_EVENT_PATTERNS[i])) {
      return IMPORTANT_EVENT_PATTERNS.length - i;
    }
  }
  return 0;
}

function isSensorDataTimelineEvent(item) {
  const eventType = String(item && item.event_type ? item.event_type : "").toLowerCase();
  const details = item && item.details && typeof item.details === "object" ? item.details : {};

  if (eventType.startsWith("inbound_")) {
    return false;
  }

  if (eventType.includes("sensor")) {
    return true;
  }

  if (typeof details.sensor_id === "string" && details.sensor_id !== "") {
    return true;
  }
  if (typeof details.global_sensor_id === "string" && details.global_sensor_id !== "") {
    return true;
  }

  return false;
}

function renderTimeline(cluster) {
  const items = Array.isArray(cluster.events.items) ? cluster.events.items.slice() : [];
  const filtered = items.filter((item) => isSensorDataTimelineEvent(item));
  filtered.sort((a, b) => {
    const pa = eventPriority(a.event_type);
    const pb = eventPriority(b.event_type);
    if (pa !== pb) {
      return pb - pa;
    }
    const ta = typeof a.ts_ms === "number" ? a.ts_ms : 0;
    const tb = typeof b.ts_ms === "number" ? b.ts_ms : 0;
    return tb - ta;
  });

  els.timeline.innerHTML = "";
  const maxRows = 140;
  for (const item of filtered.slice(0, maxRows)) {
    const row = document.createElement("article");
    row.className = "event-row";
    const sender = item.sender_id || "-";
    const target = item.target_id || "-";
    const detail = item.details && typeof item.details === "object"
      ? JSON.stringify(item.details)
      : "{}";
    row.innerHTML = `
      <div class="event-head">
        <strong>${item.event_type || "unknown_event"}</strong>
        <span>${formatTimestamp(item.ts_ms)}</span>
      </div>
      <div class="event-meta">${item.category || "-"} | ${sender} -> ${target}</div>
      <div class="event-detail">${detail}</div>
    `;
    els.timeline.appendChild(row);
  }
}

function renderMetricsStrip(cluster, graph) {
  const membershipPeers = Array.isArray(cluster.membership.peers) ? cluster.membership.peers : [];
  const sensorRecords = Array.isArray(cluster.sensorState.records) ? cluster.sensorState.records : [];
  const suspected = membershipPeers.filter((p) => p && p.display_status === "suspected").length;
  const dead = membershipPeers.filter((p) => p && p.display_status === "dead").length;
  const alivePeers = membershipPeers.filter((p) => {
    const status = p && typeof p.display_status === "string" ? p.display_status : "";
    return status === "alive_direct" || status === "alive_indirect";
  }).length;
  const metrics = cluster.metrics && typeof cluster.metrics === "object" ? cluster.metrics : {};
  const counters = metrics.counters && typeof metrics.counters === "object" ? metrics.counters : {};

  const summary = [
    { label: "Nodes", value: graph.nodes.length },
    { label: "Sensors", value: sensorRecords.length },
    { label: "Alive", value: alivePeers },
    { label: "Suspected", value: suspected },
    { label: "Dead", value: dead },
  ];

  for (const key of METRIC_KEYS) {
    if (Object.prototype.hasOwnProperty.call(counters, key)) {
      summary.push({ label: key.replace(/_total$/, "").replace(/_/g, " "), value: counters[key] });
    }
  }

  els.metricsStrip.innerHTML = "";
  for (const item of summary) {
    const card = document.createElement("div");
    card.className = "metric-card";
    card.innerHTML = `<div class="metric-label">${item.label}</div><div class="metric-value">${formatCompactNumber(item.value)}</div>`;
    els.metricsStrip.appendChild(card);
  }
}

function renderInspector(cluster, graph) {
  const selectedId = state.selectedNodeId;
  const membershipPeers = Array.isArray(cluster.membership.peers) ? cluster.membership.peers : [];
  const membershipMap = graph.membershipMap;

  if (!selectedId) {
    els.inspectorSummary.textContent = "Select a node in the graph to inspect local health/topology context.";
    els.inspectorPeers.innerHTML = "";
    return;
  }

  const selectedPeer = membershipMap.get(selectedId);
  const selectedStatus = graph.nodes.find((n) => n.id === selectedId)?.status || "unknown";

  const directObserved = selectedPeer ? selectedPeer.direct_observed === true : selectedId === graph.localNodeId;
  const phiText = selectedPeer && selectedPeer.direct_observed === true && typeof selectedPeer.phi === "number"
    ? selectedPeer.phi.toFixed(3)
    : "n/a";

  els.inspectorSummary.innerHTML = `
    <strong>${selectedId}</strong> | status: <code>${selectedStatus}</code> |
    direct observed by local node: <code>${directObserved ? "yes" : "no"}</code> |
    phi(local): <code>${phiText}</code>
  `;

  const peerRows = [];
  if (selectedId === graph.localNodeId) {
    for (const peer of membershipPeers.slice().sort((a, b) => nodeSort(a.peer_id, b.peer_id))) {
      const relation = peer.direct_observed === true ? "direct" : "indirect";
      const phi = peer.direct_observed === true && typeof peer.phi === "number" ? peer.phi.toFixed(3) : "-";
      peerRows.push({
        peer: peer.peer_id || "-",
        relation,
        status: peer.display_status || peer.status || "unknown",
        phi,
        evidence: peer.last_evidence_source || "-",
      });
    }
  } else {
    const relation = selectedPeer
      ? selectedPeer.direct_observed === true ? "direct" : "indirect"
      : "unknown";
    const status = selectedPeer
      ? selectedPeer.display_status || selectedPeer.status || "unknown"
      : "unknown";
    const phi = selectedPeer && selectedPeer.direct_observed === true && typeof selectedPeer.phi === "number"
      ? selectedPeer.phi.toFixed(3)
      : "-";
    peerRows.push({
      peer: selectedId,
      relation,
      status,
      phi,
      evidence: selectedPeer ? selectedPeer.last_evidence_source || "-" : "not present in local membership view",
    });
  }

  els.inspectorPeers.innerHTML = "";
  for (const row of peerRows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.peer}</td>
      <td>${row.relation}</td>
      <td>${renderStatusPill(row.status)}</td>
      <td>${row.phi}</td>
      <td>${row.evidence}</td>
    `;
    els.inspectorPeers.appendChild(tr);
  }
}

function renderGlobalState(cluster, graph) {
  const nodes = graph.nodes.slice().sort((a, b) => nodeSort(a.id, b.id));
  const records = Array.isArray(cluster.sensorState.records) ? cluster.sensorState.records : [];
  const recordsByOrigin = new Map();

  for (const record of records) {
    const origin = record && typeof record.origin === "string" ? record.origin : "";
    if (!origin) {
      continue;
    }
    if (!recordsByOrigin.has(origin)) {
      recordsByOrigin.set(origin, []);
    }
    recordsByOrigin.get(origin).push(record);
  }

  const totalSensors = records.length;
  els.globalStateSummary.textContent = `nodes=${nodes.length} | sensors=${totalSensors}`;

  els.globalStateCards.innerHTML = "";
  if (nodes.length === 0) {
    const empty = document.createElement("div");
    empty.className = "global-empty";
    empty.textContent = "No nodes in topology/membership snapshot.";
    els.globalStateCards.appendChild(empty);
    return;
  }

  for (const node of nodes) {
    const nodeRecords = recordsByOrigin.get(node.id) || [];
    nodeRecords.sort((a, b) => {
      const left = `${a.sensor_id || ""}|${a.global_sensor_id || ""}`;
      const right = `${b.sensor_id || ""}|${b.global_sensor_id || ""}`;
      return left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" });
    });

    const card = document.createElement("article");
    card.className = "global-node-card";
    card.innerHTML = `
      <header class="global-node-head">
        <div class="global-node-title">${node.id}</div>
        <div class="global-node-meta">
          ${renderStatusPill(node.status)}
          <span class="global-sensor-count">${nodeRecords.length} sensors</span>
        </div>
      </header>
      <div class="global-sensor-list"></div>
    `;

    const list = card.querySelector(".global-sensor-list");
    if (nodeRecords.length === 0) {
      const emptyRow = document.createElement("div");
      emptyRow.className = "global-sensor-empty";
      emptyRow.textContent = "No sensor records for this node.";
      list.appendChild(emptyRow);
    } else {
      for (const record of nodeRecords) {
        const row = document.createElement("div");
        row.className = "global-sensor-row";
        row.innerHTML = `
          <div class="sensor-name">${record.sensor_id || "-"}</div>
          <div class="sensor-value">${formatSensorValue(record.value)}</div>
          <div class="sensor-ts">${formatTimestamp(record.ts_ms)}</div>
          <div class="sensor-seq">${extractSeqVersion(record)}</div>
        `;
        list.appendChild(row);
      }
    }

    els.globalStateCards.appendChild(card);
  }
}

function renderDashboard(cluster) {
  const graph = buildGraphModel(cluster);
  if (!state.selectedNodeId && graph.localNodeId) {
    state.selectedNodeId = graph.localNodeId;
  }
  if (state.selectedNodeId && !graph.nodes.some((n) => n.id === state.selectedNodeId)) {
    state.selectedNodeId = graph.localNodeId || (graph.nodes[0] ? graph.nodes[0].id : null);
  }

  state.activeLinkKeys = new Set(graph.activeLinks.map(linkKey));
  drawTopology(graph);
  renderMetricsStrip(cluster, graph);
  renderInspector(cluster, graph);
  renderGlobalState(cluster, graph);
  renderSensorTable(cluster);
  renderTimeline(cluster);
  tryRestoreScrollPosition();
}

async function fetchClusterSnapshot() {
  const url = `${state.baseUrl}${API_ENDPOINTS.introspection}`;
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return normalizeCluster(await response.json());
}

function makeUrl(protocol, host, port) {
  return `${protocol}//${host}:${port}`;
}

function isUnroutableHost(host) {
  if (typeof host !== "string") {
    return true;
  }
  const normalized = host.trim().toLowerCase();
  return !normalized || normalized === "0.0.0.0" || normalized === "::" || normalized === "[::]";
}

function parseNodeIndex(nodeId) {
  const match = String(nodeId || "").match(/(\d+)$/);
  if (!match) {
    return null;
  }
  const value = Number(match[1]);
  return Number.isFinite(value) ? value : null;
}

function parseBaseUrlParts() {
  try {
    const parsed = new URL(state.baseUrl);
    const protocol = parsed.protocol || "http:";
    const host = parsed.hostname || "localhost";
    const port = parsed.port ? Number(parsed.port) : null;
    if (port !== null && (!Number.isFinite(port) || port <= 0)) {
      return null;
    }
    return { protocol, host, port };
  } catch {
    return null;
  }
}

function buildCandidateBaseUrlsForNode(nodeId) {
  const candidates = [];
  const seen = new Set();
  const addCandidate = (url) => {
    if (typeof url !== "string" || !url || seen.has(url)) {
      return;
    }
    seen.add(url);
    candidates.push(url);
  };

  const cached = state.endpointByNodeId.get(nodeId);
  if (cached) {
    addCandidate(cached);
  }

  if (!state.cluster || !state.cluster.membership) {
    return candidates;
  }
  const baseParts = parseBaseUrlParts();
  const protocol = baseParts ? baseParts.protocol : "http:";
  const currentHost = baseParts ? baseParts.host : "localhost";
  const currentPort = baseParts && typeof baseParts.port === "number" ? baseParts.port : 10000;
  const localNodeId = typeof state.cluster.membership.local_node_id === "string"
    ? state.cluster.membership.local_node_id
    : "";

  const peers = Array.isArray(state.cluster.membership.peers) ? state.cluster.membership.peers : [];
  const peer = peers.find((p) => p && p.peer_id === nodeId);
  const peerHost = peer && typeof peer.host === "string" ? peer.host : null;
  const peerPort = typeof peer.port === "number" && Number.isFinite(peer.port) ? peer.port : null;

  const ports = [];
  const addPort = (port) => {
    if (!Number.isFinite(port) || port <= 0) {
      return;
    }
    const normalized = Math.round(port);
    if (normalized <= 0 || normalized > 65535 || ports.includes(normalized)) {
      return;
    }
    ports.push(normalized);
  };

  const localIdx = parseNodeIndex(localNodeId);
  const targetIdx = parseNodeIndex(nodeId);
  if (localIdx !== null && targetIdx !== null) {
    // Highest priority: keep same host, move to target node offset port
    // (e.g. node-1@12000 -> node-2@12001).
    addPort(currentPort + (targetIdx - localIdx));
  }

  // Keep current port only as fallback.
  addPort(currentPort);

  if (peerPort !== null) {
    addPort(peerPort + 1000);
    addPort(peerPort);
  }

  if (localIdx !== null && targetIdx !== null) {
    const inferredBase = currentPort - (localIdx - 1);
    addPort(inferredBase + (targetIdx - 1));
  }

  const hosts = [];
  const addHost = (host) => {
    if (typeof host !== "string" || !host || isUnroutableHost(host) || hosts.includes(host)) {
      return;
    }
    hosts.push(host);
  };

  // Prefer the current browser host (usually externally reachable), then peer host.
  addHost(currentHost);
  addHost(peerHost);
  addHost("localhost");
  addHost("127.0.0.1");

  for (const host of hosts) {
    for (const port of ports) {
      addCandidate(makeUrl(protocol, host, port));
    }
  }

  return candidates;
}

async function probeIntrospection(baseUrl, expectedNodeId, timeoutMs = 1600) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${baseUrl}${API_ENDPOINTS.introspection}`, {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) {
      return { ok: false, matched: false, localNodeId: null };
    }
    const payload = await response.json();
    const cluster = payload && typeof payload.cluster === "object" ? payload.cluster : {};
    const membership = cluster && typeof cluster.membership === "object" ? cluster.membership : {};
    const localNodeId = typeof membership.local_node_id === "string" ? membership.local_node_id : null;
    return {
      ok: true,
      matched: localNodeId === expectedNodeId,
      localNodeId,
    };
  } catch {
    return { ok: false, matched: false, localNodeId: null };
  } finally {
    clearTimeout(timer);
  }
}

async function switchConnectionToNode(nodeId) {
  if (!state.cluster) {
    return false;
  }
  const localNodeId = typeof state.cluster.membership.local_node_id === "string"
    ? state.cluster.membership.local_node_id
    : "";
  if (!nodeId || nodeId === localNodeId) {
    return false;
  }

  const candidates = buildCandidateBaseUrlsForNode(nodeId);
  if (candidates.length === 0) {
    setConnection(false, `No endpoint candidates for ${nodeId}`);
    return false;
  }

  setConnection(false, `Switching to ${nodeId}...`);
  const candidate = candidates[0];
  state.endpointByNodeId.set(nodeId, candidate);

  // Primary behavior: navigate to the target node UI by changing browser URL.
  if (typeof window !== "undefined" && window.location && typeof window.location.assign === "function") {
    const relativePath = `${window.location.pathname || "/ui"}${window.location.search || ""}${window.location.hash || ""}`;
    const targetUrl = new URL(relativePath, `${candidate}/`).toString();
    setConnection(true, `Navigating to ${nodeId}...`);
    saveScrollPositionForNavigation();
    window.location.assign(targetUrl);
    return true;
  }

  // Non-browser fallback.
  state.baseUrl = candidate;
  els.baseUrl.value = candidate;
  state.activeLinkKeys = new Set();
  restartPolling();
  return true;
}

async function pollOnce() {
  if (state.isPolling) {
    return;
  }
  const session = state.pollSession;
  state.isPolling = true;
  try {
    const cluster = await fetchClusterSnapshot();
    if (session !== state.pollSession) {
      return;
    }
    state.cluster = cluster;
    const localNodeId = cluster.membership && typeof cluster.membership.local_node_id === "string"
      ? cluster.membership.local_node_id
      : null;
    if (localNodeId) {
      state.endpointByNodeId.set(localNodeId, state.baseUrl);
      // Keep default selection on local node only when no explicit user selection exists.
      if (!state.selectedNodeId) {
        state.selectedNodeId = localNodeId;
      }
    }
    renderDashboard(cluster);
    els.snapshotTime.textContent = formatTimestamp(cluster.generatedAtMs);
    setConnection(true, "Connected");
  } catch (error) {
    if (session !== state.pollSession) {
      return;
    }
    const message = error instanceof Error ? error.message : "fetch failed";
    setConnection(false, `Disconnected (${message})`);
  } finally {
    state.isPolling = false;
  }
}

function restartPolling() {
  state.pollSession += 1;
  if (state.timer) {
    clearInterval(state.timer);
    state.timer = null;
  }
  state.timer = setInterval(pollOnce, state.pollMs);
  pollOnce();
}

function applySettings() {
  const nextBase = String(els.baseUrl.value || "").replace(/\/+$/, "");
  const baseChanged = nextBase !== state.baseUrl;
  state.baseUrl = String(els.baseUrl.value || "").replace(/\/+$/, "");
  state.pollMs = Math.max(250, Number(els.pollMs.value) || 1000);
  if (baseChanged) {
    state.activeLinkKeys = new Set();
  }
  restartPolling();
}

async function onCanvasClick(event) {
  const rect = els.topologyCanvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  const nodeId = findClosestNode(x, y);
  if (!nodeId) {
    return;
  }
  if (!state.cluster) {
    return;
  }
  const graph = buildGraphModel(state.cluster);
  const clickedNode = graph.nodes.find((n) => n.id === nodeId);
  const clickedStatus = clickedNode ? clickedNode.status : "unknown";

  // Always allow inspection selection on click.
  state.selectedNodeId = nodeId;
  renderDashboard(state.cluster);

  // Never switch connection toward dead nodes: keep current endpoint and just inspect.
  if (clickedStatus === "dead") {
    return;
  }

  const currentLocalNodeId = typeof state.cluster.membership.local_node_id === "string"
    ? state.cluster.membership.local_node_id
    : "";
  if (nodeId === currentLocalNodeId) {
    return;
  }
  const switched = await switchConnectionToNode(nodeId);
  if (switched) {
    // After a successful endpoint switch, immediately keep the view anchored
    // to the clicked target node (avoid reading stale pre-switch cluster state).
    state.selectedNodeId = nodeId;
  }
}

function onResize() {
  if (state.cluster) {
    renderDashboard(state.cluster);
  }
}

els.apply.addEventListener("click", applySettings);
els.topologyCanvas.addEventListener("click", onCanvasClick);
window.addEventListener("resize", onResize);

restoreScrollPositionAfterNavigation();
tryRestoreScrollPosition();
els.baseUrl.value = state.baseUrl;
applySettings();
