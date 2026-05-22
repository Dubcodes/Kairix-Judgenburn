function safeJsonParse(raw, fallback = null) {
  if (!raw) return fallback;
  try {
    return JSON.parse(raw);
  } catch (_) {
    return fallback;
  }
}

const CONNECTION_CONFIG_KEY = "kairix_connection_config";
const CONNECTION = {
  config: safeJsonParse(localStorage.getItem(CONNECTION_CONFIG_KEY), null),
  configLoadedAt: 0,
  mode: "local",
  currentBaseUrl: "",
  lastError: null,
  lastLocalRetryAt: 0,
  liveState: null,
  liveStateFetchedAt: 0,
  stream: null,
  streamConnecting: false,
  listeners: new Set(),
};

function normalizeBaseUrl(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function resolveApiUrl(url, baseUrl = "") {
  if (/^https?:\/\//i.test(url)) return url;
  const path = url.startsWith("/") ? url : `/${url}`;
  return `${normalizeBaseUrl(baseUrl)}${path}`;
}

function sameBase(a, b) {
  return normalizeBaseUrl(a).toLowerCase() === normalizeBaseUrl(b).toLowerCase();
}

function connectionModeFor(baseUrl) {
  const config = CONNECTION.config || {};
  const base = normalizeBaseUrl(baseUrl);
  if (!base) return "local";
  if (config.cloud_base_url && sameBase(base, config.cloud_base_url)) return "cloud";
  if (config.local_base_url && sameBase(base, config.local_base_url)) return "local";
  return "remote";
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 2500) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }
}

async function readJsonResponse(response) {
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function loadClientConfig(force = false) {
  if (!force && CONNECTION.config && Date.now() - CONNECTION.configLoadedAt < 30000) return CONNECTION.config;
  const stored = safeJsonParse(localStorage.getItem(CONNECTION_CONFIG_KEY), null);
  const timeoutMs = Number(stored?.request_timeout_ms || 2500);
  const attempts = [""];
  if (stored?.cloud_base_url) attempts.push(stored.cloud_base_url);
  let lastError = null;
  for (const base of attempts) {
    try {
      const response = await fetchWithTimeout(resolveApiUrl("/api/client-config", base), { cache: "no-store" }, timeoutMs);
      const data = await readJsonResponse(response);
      CONNECTION.config = data.connectivity || {};
      CONNECTION.configLoadedAt = Date.now();
      localStorage.setItem(CONNECTION_CONFIG_KEY, JSON.stringify(CONNECTION.config));
      if (force && CONNECTION.stream) {
        CONNECTION.stream.close();
        CONNECTION.stream = null;
        connectLiveStateStream().catch(error => {
          CONNECTION.lastError = error.message || String(error);
        });
      }
      return CONNECTION.config;
    } catch (error) {
      lastError = error;
    }
  }
  CONNECTION.lastError = lastError?.message || "Unable to load client connection settings";
  return CONNECTION.config || {};
}

function apiCandidateBases(method = "GET") {
  const config = CONNECTION.config || {};
  const bases = [];
  const add = base => {
    const normalized = normalizeBaseUrl(base);
    if (!bases.some(item => sameBase(item, normalized))) bases.push(normalized);
  };
  if (config.prefer_local && config.local_base_url) add(config.local_base_url);
  add("");
  if (config.fallback_enabled && config.cloud_base_url) add(config.cloud_base_url);
  return bases;
}

async function apiRequest(method, url, body = undefined) {
  await loadClientConfig(false);
  const config = CONNECTION.config || {};
  const timeoutMs = Number(config.request_timeout_ms || 2500);
  const options = {
    method,
    cache: "no-store",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
  let lastError = null;
  for (const base of apiCandidateBases(method)) {
    try {
      const response = await fetchWithTimeout(resolveApiUrl(url, base), options, timeoutMs);
      const data = await readJsonResponse(response);
      CONNECTION.currentBaseUrl = base;
      CONNECTION.mode = connectionModeFor(base);
      CONNECTION.lastError = null;
      return data;
    } catch (error) {
      lastError = error;
      if (!["TypeError", "AbortError"].includes(error.name)) break;
    }
  }
  CONNECTION.lastError = lastError?.message || "Request failed";
  throw lastError;
}

const API = {
  get(url) {
    return apiRequest("GET", url);
  },
  post(url, body) {
    return apiRequest("POST", url, body);
  },
  put(url, body) {
    return apiRequest("PUT", url, body);
  },
};

function deviceId() {
  let id = localStorage.getItem("kairix_device_id");
  if (!id) {
    const randomPart = Math.random().toString(36).slice(2);
    const timePart = Date.now().toString(36);
    id = `device-${timePart}-${randomPart}`;
    localStorage.setItem("kairix_device_id", id);
  }
  return id;
}

function session() {
  const cookieSessionId = cookieValue("kairix_client_session_id");
  const cookieRole = cookieValue("kairix_client_role");
  if (cookieSessionId && cookieRole) {
    const cookieSession = {
      session_id: Number(cookieSessionId),
      role: cookieRole,
      display_name: cookieRole.replace("_", " "),
    };
    const raw = localStorage.getItem("kairix_session");
    if (raw) {
      const stored = safeJsonParse(raw);
      if (stored && String(stored.session_id) === String(cookieSession.session_id) && stored.role === cookieSession.role) {
        return stored;
      }
    }
    return cookieSession;
  }
  return safeJsonParse(localStorage.getItem("kairix_session"), null);
}

function setSession(value) {
  localStorage.setItem("kairix_session", JSON.stringify(value));
}

function clearSession() {
  localStorage.removeItem("kairix_session");
  document.cookie = "kairix_client_session_id=; Max-Age=0; path=/";
  document.cookie = "kairix_client_role=; Max-Age=0; path=/";
}

function cookieValue(name) {
  const prefix = `${name}=`;
  return document.cookie
    .split(";")
    .map(part => part.trim())
    .find(part => part.startsWith(prefix))
    ?.slice(prefix.length) || null;
}

function requireRole(allowedRoles, options = {}) {
  const current = session();
  const roles = Array.isArray(allowedRoles) ? allowedRoles : [allowedRoles];
  if (!current || !roles.includes(current.role)) {
    clearSession();
    window.location.replace(options.redirect || "/");
    throw new Error("Kairix login required");
  }
  return current;
}

async function validateSession(current, allowedRoles = []) {
  const roles = Array.isArray(allowedRoles) ? allowedRoles : [allowedRoles];
  try {
    const url = current?.session_id
      ? `/api/auth/session?session_id=${encodeURIComponent(current.session_id)}`
      : "/api/auth/session";
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) {
      throw new Error(await res.text());
    }
    const server = await res.json();
    if (roles.length && !roles.includes(server.role)) {
      throw new Error("Role not allowed");
    }
    if (server.role !== current.role) {
      throw new Error("Session role mismatch");
    }
    setSession({ ...current, ...server });
    return server;
  } catch (error) {
    clearSession();
    window.location.replace("/");
    throw error;
  }
}

function formatRun(run) {
  if (!run) return "No current competitor";
  const car = run.vehicle ? run.vehicle.name : "Vehicle TBC";
  return `#${run.competitor.entry_number} ${run.competitor.driver_name} - ${car}`;
}

function formatSeconds(value) {
  const raw = Number(value || 0);
  const sign = raw < 0 ? "-" : "";
  const seconds = Math.abs(Math.trunc(raw));
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${sign}${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function stampTimer(timer) {
  if (!timer) return null;
  return { ...timer, fetched_at_ms: Date.now() };
}

function timerDisplaySeconds(timer) {
  if (!timer) return 0;
  let displayMs = Number(timer.display_ms ?? Number(timer.display_seconds || 0) * 1000);
  if (timer.status === "running") {
    const fetchedAt = Number(timer.fetched_at_ms || Date.now());
    const deltaMs = Math.max(0, Date.now() - fetchedAt);
    displayMs = timer.mode === "count_down" ? displayMs - deltaMs : displayMs + deltaMs;
  }
  return displayMs < 0 ? Math.ceil(displayMs / 1000) : Math.floor(displayMs / 1000);
}

function rememberLiveState(state, source = "poll") {
  if (!state) return null;
  if (state.timer) state.timer = stampTimer(state.timer);
  state.client_connection = {
    mode: CONNECTION.mode,
    base_url: CONNECTION.currentBaseUrl,
    source,
    last_error: CONNECTION.lastError,
    fetched_at: Date.now(),
  };
  CONNECTION.liveState = state;
  CONNECTION.liveStateFetchedAt = Date.now();
  if (!document.body.classList.contains("overlay-body")) {
    applyTheme(state.graphics?.layout_config?.theme);
  }
  return state;
}

function cachedLiveState(maxAgeMs = 2500) {
  if (!CONNECTION.liveState) return null;
  if (Date.now() - CONNECTION.liveStateFetchedAt > maxAgeMs) return null;
  return CONNECTION.liveState;
}

async function getEventState(options = {}) {
  const cached = options.preferCache === false ? null : cachedLiveState(options.maxAgeMs || 2500);
  if (cached) return cached;
  const state = await API.get("/api/event-state");
  return rememberLiveState(state, "poll");
}

async function getQueue(options = {}) {
  const cached = options.preferCache === false ? null : cachedLiveState(options.maxAgeMs || 2500);
  if (cached?.queue) return { runs: cached.queue };
  return API.get("/api/queue");
}

function liveStreamCandidateBases() {
  const config = CONNECTION.config || {};
  const bases = [];
  const add = base => {
    const normalized = normalizeBaseUrl(base);
    if (!bases.some(item => sameBase(item, normalized))) bases.push(normalized);
  };
  if (config.prefer_local && config.local_base_url) add(config.local_base_url);
  add("");
  if (config.fallback_enabled && config.cloud_base_url) add(config.cloud_base_url);
  return bases;
}

async function connectLiveStateStream() {
  if (CONNECTION.stream || CONNECTION.streamConnecting) return;
  CONNECTION.streamConnecting = true;
  await loadClientConfig(false);
  const bases = liveStreamCandidateBases();
  let index = 0;

  const openNext = () => {
    if (!CONNECTION.listeners.size) {
      CONNECTION.streamConnecting = false;
      return;
    }
    const base = bases[index % bases.length] || "";
    index += 1;
    const source = new EventSource(resolveApiUrl("/api/live/events", base));
    CONNECTION.stream = source;
    CONNECTION.currentBaseUrl = base;
    CONNECTION.mode = connectionModeFor(base);

    source.addEventListener("state", event => {
      const state = rememberLiveState(JSON.parse(event.data), "sse");
      CONNECTION.listeners.forEach(listener => listener(state));
      const config = CONNECTION.config || {};
      const retryMs = Number(config.retry_local_after_seconds || 20) * 1000;
      if (
        CONNECTION.mode === "cloud"
        && config.auto_return_to_local !== false
        && config.local_base_url
        && Date.now() - CONNECTION.lastLocalRetryAt > retryMs
      ) {
        CONNECTION.lastLocalRetryAt = Date.now();
        index = 0;
        source._kairixSwitching = true;
        source.close();
        if (CONNECTION.stream === source) CONNECTION.stream = null;
        setTimeout(openNext, 25);
      }
    });

    source.addEventListener("error", event => {
      if (source._kairixSwitching) return;
      CONNECTION.lastError = "Live stream disconnected";
      source.close();
      if (CONNECTION.stream === source) CONNECTION.stream = null;
      setTimeout(openNext, 1200);
    });
  };

  openNext();
  CONNECTION.streamConnecting = false;
}

function subscribeLiveState(listener) {
  CONNECTION.listeners.add(listener);
  if (CONNECTION.liveState) listener(CONNECTION.liveState);
  connectLiveStateStream().catch(error => {
    CONNECTION.lastError = error.message || String(error);
  });
  return () => {
    CONNECTION.listeners.delete(listener);
    if (!CONNECTION.listeners.size && CONNECTION.stream) {
      CONNECTION.stream.close();
      CONNECTION.stream = null;
    }
  };
}

function applyTheme(theme = null) {
  if (document.body.classList.contains("overlay-body")) return;
  const root = document.documentElement;
  const values = {
    bg: theme?.bg || "#f7f7f4",
    panel: theme?.panel || "#ffffff",
    ink: theme?.ink || "#181818",
    muted: theme?.muted || "#646464",
    line: theme?.line || "#d9d9d2",
    accent: theme?.accent || "#b91c1c",
    good: theme?.good || "#147a43",
    warn: theme?.warn || "#a15c00",
    dark: theme?.dark || "#121212",
    blue: theme?.blue || "#175b89",
  };
  Object.entries(values).forEach(([key, value]) => root.style.setProperty(`--${key}`, value));
  root.dataset.themeLoaded = "true";
}

function attachButtonHelpers(root = document) {
  root.querySelectorAll("button, a.btn, [data-help]").forEach(element => {
    if (element.dataset.help) {
      element.title = element.dataset.help;
      if (!element.getAttribute("aria-label") && ["BUTTON", "A"].includes(element.tagName)) {
        element.setAttribute("aria-label", element.dataset.help);
      }
      return;
    }
    if (element.title) return;
    const label = element.textContent.trim().replace(/\s+/g, " ");
    if (label) element.title = label;
  });
}

async function withButtonFeedback(button, action) {
  if (!button) return action();
  button.classList.add("pressed", "busy");
  const original = button.innerHTML;
  try {
    const result = await action();
    button.classList.remove("busy");
    button.classList.add("success");
    setTimeout(() => {
      button.classList.remove("pressed", "success");
      button.innerHTML = original;
    }, 650);
    return result;
  } catch (error) {
    button.classList.remove("pressed", "busy");
    throw error;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  attachButtonHelpers();
  const autoLive = document.body.dataset.kairixAutoLive !== "false" && !document.body.classList.contains("overlay-body");
  if (autoLive) {
    loadClientConfig().catch(() => {});
    subscribeLiveState(() => {});
    getEventState().catch(() => applyTheme());
  }
  const observer = new MutationObserver(mutations => {
    for (const mutation of mutations) {
      mutation.addedNodes.forEach(node => {
        if (node.nodeType === Node.ELEMENT_NODE) attachButtonHelpers(node);
      });
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
});

window.Kairix = { API, CONNECTION, deviceId, session, setSession, clearSession, requireRole, validateSession, formatRun, formatSeconds, stampTimer, timerDisplaySeconds, getEventState, getQueue, subscribeLiveState, loadClientConfig, applyTheme, withButtonFeedback, attachButtonHelpers, safeJsonParse };
