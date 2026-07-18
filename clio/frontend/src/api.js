const BASE = "/api";

async function handle(response) {
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // ignore non-JSON error bodies
    }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

export function createScenario(rawText) {
  return fetch(`${BASE}/scenarios`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raw_text: rawText }),
  }).then(handle);
}

export function updateScenario(id, payload) {
  return fetch(`${BASE}/scenarios/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(handle);
}

export function getScenario(id) {
  return fetch(`${BASE}/scenarios/${id}`).then(handle);
}

export function getReport(id) {
  return fetch(`${BASE}/scenarios/${id}/report`).then(handle);
}

export function listHistory() {
  return fetch(`${BASE}/history`).then(handle);
}

export function listCachedCases() {
  return fetch(`${BASE}/cache/cases`).then(handle);
}

export function getCachedCase(id) {
  return fetch(`${BASE}/cache/cases/${id}`).then(handle);
}

export function deleteCachedCase(id) {
  return fetch(`${BASE}/cache/cases/${id}`, { method: "DELETE" }).then(handle);
}

export function getHealth() {
  return fetch(`${BASE}/health`).then(handle);
}

// --- Historical-event-analysis mode ---

export function createEventQuery(rawText) {
  return fetch(`${BASE}/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raw_text: rawText }),
  }).then(handle);
}

export function getEventQuery(id) {
  return fetch(`${BASE}/events/${id}`).then(handle);
}

export function getEventReport(id) {
  return fetch(`${BASE}/events/${id}/report`).then(handle);
}

export function listEventHistory() {
  return fetch(`${BASE}/event-history`).then(handle);
}

export function streamEventAnalysis(eventQueryId, opts) {
  return streamSse(`${BASE}/events/${eventQueryId}/analyze`, opts);
}

/**
 * Streams POST /api/scenarios/{id}/analyze as parsed SSE events. Native
 * EventSource can't send a POST body/method, so this parses the
 * text/event-stream response manually from a fetch() ReadableStream.
 */
export function streamAnalysis(scenarioId, opts) {
  return streamSse(`${BASE}/scenarios/${scenarioId}/analyze`, opts);
}

async function* streamSse(url, { signal } = {}) {
  const response = await fetch(url, { method: "POST", signal });
  if (!response.ok || !response.body) {
    throw new Error(`Analysis stream failed to start (HTTP ${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sepIndex;
    while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
      const rawEvent = buffer.slice(0, sepIndex);
      buffer = buffer.slice(sepIndex + 2);
      const parsed = parseSseBlock(rawEvent);
      if (parsed) yield parsed;
    }
  }
}

function parseSseBlock(block) {
  let event = "message";
  const dataLines = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  const raw = dataLines.join("\n");
  try {
    return { event, data: JSON.parse(raw) };
  } catch {
    return { event, data: raw };
  }
}
