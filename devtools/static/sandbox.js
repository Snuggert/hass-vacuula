const card = document.getElementById("map-card");
const editor = document.getElementById("map-card-editor");
const editorPanel = document.getElementById("editor-panel");
const logEl = document.getElementById("service-log");
const metaEl = document.getElementById("server-meta");
const pillEl = document.getElementById("entity-count-pill");
const tabsEl = document.getElementById("robot-tabs");
const devContainer = document.getElementById("device-info-container");
const entContainer = document.getElementById("entities-container");
const battSlider = document.getElementById("batt-slider");
const battLabel = document.getElementById("batt-label");
const chgToggle = document.getElementById("chg-toggle");
const customCodeInput = document.getElementById("custom-code-input");

const ENTITY_GROUPS = [
  { title: "Vacuum Entity", domains: ["vacuum"] },
  {
    title: "Interactive Controls (Select, Switch, Button)",
    domains: ["select", "switch", "button"],
  },
  { title: "Sensors & Diagnostics", domains: ["sensor", "binary_sensor"] },
  { title: "Map Camera / Image Entities", domains: ["image"] },
];

let activeSerial = null;
let cardConfig = null;
let latestData = { states: {}, entities: [], devices: [], server_info: {} };
const expandedEntities = new Set();

function logMsg(msg) {
  const ts = new Date().toLocaleTimeString();
  logEl.textContent = `[${ts}] ${msg}\n${logEl.textContent.slice(0, 3000)}`;
}

const mockHass = {
  states: {},
  callService: async (domain, service, serviceData) => {
    logMsg(`callService: ${domain}.${service} ${JSON.stringify(serviceData || {})}`);
    const res = await fetch("/api/sandbox/call_service", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ domain, service, service_data: serviceData }),
    });
    const data = await res.json();
    if (data.error) {
      logMsg(`[error] service error: ${data.error}`);
    }
    if (data.states) applyPayload(data);
  },
};

function selectRobot(serial) {
  activeSerial = serial;
  const vacEnt = latestData.entities.find((e) => e.domain === "vacuum" && e.serial === serial);
  if (vacEnt) {
    cardConfig = {
      ...(cardConfig || { map_height: "large", expand_on_desktop: true }),
      entity: vacEnt.entity_id,
    };
    card.setConfig(cardConfig);
    card.hass = { ...mockHass, states: latestData.states };
    editor.hass = { ...mockHass, states: latestData.states };
    editor.setConfig(cardConfig);
  }
  renderInspector();
}

function renderControlHtml(e) {
  if (e.domain === "button") {
    return `<button class="ent-btn" type="button" data-action="press" data-eid="${e.entity_id}">Press</button>`;
  }
  if (e.domain === "switch") {
    const label = e.state === "on" ? "ON (Toggle)" : "OFF (Toggle)";
    return `<button class="ent-btn" type="button" data-action="toggle" data-eid="${e.entity_id}">${label}</button>`;
  }
  if (e.domain === "select") {
    const opts = (e.attributes.options || [])
      .map((o) => `<option value="${o}" ${o === e.state ? "selected" : ""}>${o}</option>`)
      .join("");
    return `<select class="ent-select" data-action="select" data-eid="${e.entity_id}">${opts}</select>`;
  }
  const unit = e.attributes.unit_of_measurement ? ` ${e.attributes.unit_of_measurement}` : "";
  return `<span class="state-badge ${e.state}">${e.state}${unit}</span>`;
}

function renderInspector() {
  const devices = latestData.devices || [];
  const entities = latestData.entities || [];
  if (!activeSerial && devices.length > 0) {
    activeSerial = devices[0].serial;
  }

  tabsEl.innerHTML = devices
    .map(
      (d) =>
        `<button class="robot-tab ${d.serial === activeSerial ? "active" : ""}" type="button" data-robot-serial="${d.serial}">
          ${d.name} <span class="robot-tab-serial">(${d.serial})</span>
        </button>`
    )
    .join("");

  const dev = devices.find((d) => d.serial === activeSerial) || devices[0];
  if (dev) {
    devContainer.innerHTML = `
      <div class="device-box">
        <div><span>Device Name:</span> <strong>${dev.name}</strong></div>
        <div><span>Manufacturer:</span> <strong>${dev.manufacturer}</strong></div>
        <div><span>Model:</span> <strong>${dev.model}</strong></div>
        <div><span>Firmware:</span> <strong>${dev.sw_version}</strong></div>
        <div><span>Serial:</span> <code>${dev.serial}</code></div>
        <div><span>Installer:</span> <code>${dev.installed_with || "N/A"}</code></div>
      </div>
    `;
  }

  const robotEntities = entities.filter((e) => !activeSerial || e.serial === activeSerial);
  entContainer.innerHTML = ENTITY_GROUPS.map((g) => {
    const items = robotEntities.filter((e) => g.domains.includes(e.domain));
    if (!items.length) return "";
    const rows = items
      .map((e) => {
        const isOpen = expandedEntities.has(e.entity_id) ? "open" : "";
        return `
          <div class="entity-row">
            <div class="entity-row-main">
              <div class="entity-meta">
                <span class="entity-name">${e.attributes.friendly_name || e.entity_id}</span>
                <span class="entity-id">${e.entity_id} • <span class="accent">${e.class_name}</span></span>
              </div>
              <div class="entity-ctrl">${renderControlHtml(e)}</div>
            </div>
            <details class="attr-details" data-eid="${e.entity_id}" ${isOpen}>
              <summary>Attributes (${Object.keys(e.attributes || {}).length})</summary>
              <pre>${JSON.stringify(e.attributes, null, 2)}</pre>
            </details>
          </div>
        `;
      })
      .join("");
    return `<div class="entity-group-title">${g.title} (${items.length})</div><div class="entity-list">${rows}</div>`;
  }).join("");
}

function applyPayload(data) {
  latestData = { ...latestData, ...data };
  const states = latestData.states || {};
  mockHass.states = states;

  const count = (latestData.entities || []).length || Object.keys(states).length;
  pillEl.textContent = `${count} Live Integration Entities`;

  if (!activeSerial && latestData.devices?.length > 0) {
    activeSerial = latestData.devices[0].serial;
  }

  const vacId =
    Object.keys(states).find(
      (k) =>
        k.startsWith("vacuum.") && (!activeSerial || states[k].attributes?.serial === activeSerial)
    ) || Object.keys(states).find((k) => k.startsWith("vacuum."));

  if (vacId && (!cardConfig || cardConfig.entity !== vacId)) {
    cardConfig = {
      entity: vacId,
      map_height: "large",
      expand_on_desktop: true,
    };
    card.setConfig(cardConfig);
    editor.setConfig(cardConfig);
  }
  card.hass = { ...mockHass, states };
  editor.hass = { ...mockHass, states };

  if (latestData.server_info?.version) {
    metaEl.textContent = `Vacuula Server v${latestData.server_info.version} • SSE Connected • Python 3.14`;
  }
  renderInspector();
}

async function refreshAll() {
  const res = await fetch("/api/sandbox/states");
  applyPayload(await res.json());
}

async function triggerSim(action, value = null, charging = false, extra = {}) {
  logMsg(
    `event trigger [${activeSerial || "default"}]: ${action}${value !== null ? `=${value}` : ""}`
  );
  const res = await fetch("/api/sandbox/mock_robot", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ serial: activeSerial, action, value, charging, ...extra }),
  });
  applyPayload(await res.json());
}

// Event Listeners & Delegation
document.getElementById("toggle-editor-btn").addEventListener("click", () => {
  editorPanel.classList.toggle("hidden");
});

document.getElementById("refresh-btn").addEventListener("click", refreshAll);

editor.addEventListener("config-changed", (ev) => {
  if (ev.detail?.config) {
    cardConfig = ev.detail.config;
    card.setConfig(cardConfig);
    card.hass = { ...mockHass, states: latestData.states };
    editor.setConfig(cardConfig);
    logMsg(`card config updated: ${JSON.stringify(cardConfig)}`);
  }
});

tabsEl.addEventListener("click", (ev) => {
  const btn = ev.target.closest("[data-robot-serial]");
  if (btn) selectRobot(btn.dataset.robotSerial);
});

entContainer.addEventListener("click", (ev) => {
  const btn = ev.target.closest("[data-action]");
  if (!btn) return;
  const { action, eid } = btn.dataset;
  if (action === "press") mockHass.callService("button", "press", { entity_id: eid });
  if (action === "toggle") mockHass.callService("switch", "toggle", { entity_id: eid });
});

entContainer.addEventListener("change", (ev) => {
  const sel = ev.target.closest("select[data-action='select']");
  if (sel) {
    mockHass.callService("select", "select_option", {
      entity_id: sel.dataset.eid,
      option: sel.value,
    });
  }
});

entContainer.addEventListener(
  "toggle",
  (ev) => {
    const details = ev.target.closest("details[data-eid]");
    if (!details) return;
    if (details.open) expandedEntities.add(details.dataset.eid);
    else expandedEntities.delete(details.dataset.eid);
  },
  true
);

document.getElementById("sim-studio").addEventListener("click", (ev) => {
  const presetBtn = ev.target.closest("[data-batt-pct]");
  if (presetBtn) {
    const pct = Number(presetBtn.dataset.battPct);
    const chg = presetBtn.dataset.battChg === "true";
    battSlider.value = String(pct);
    battLabel.textContent = `${pct}%`;
    chgToggle.checked = chg;
    triggerSim("battery", pct, chg);
    return;
  }

  const simBtn = ev.target.closest("[data-sim]");
  if (!simBtn) return;
  const action = simBtn.dataset.sim;
  const value =
    "valBool" in simBtn.dataset ? simBtn.dataset.valBool === "true" : (simBtn.dataset.val ?? null);
  const extra = simBtn.dataset.category ? { category: Number(simBtn.dataset.category) } : {};
  triggerSim(action, value, false, extra);
});

document.getElementById("custom-alert-btn").addEventListener("click", () => {
  triggerSim("alert", customCodeInput.value);
});

document.getElementById("custom-error-btn").addEventListener("click", () => {
  triggerSim("error", customCodeInput.value);
});

battSlider.addEventListener("input", () => {
  battLabel.textContent = `${battSlider.value}%`;
});

battSlider.addEventListener("change", () => {
  triggerSim("battery", Number(battSlider.value), chgToggle.checked);
});

chgToggle.addEventListener("change", () => {
  triggerSim("charging", chgToggle.checked);
});

// Connect real-time SSE stream from Sandbox -> Browser
const es = new EventSource("/api/sandbox/events");
es.onmessage = (ev) => {
  try {
    applyPayload(JSON.parse(ev.data));
  } catch (err) {
    console.error(err);
  }
};
es.onerror = () => {
  setTimeout(refreshAll, 2000);
};
