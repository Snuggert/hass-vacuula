/**
 * Vacuula Map & Room Card for Home Assistant
 * Auto-registered by the hass-vacuula integration.
 */

class VacuulaMapCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._viewMode = "floor"; // "floor" | "run"
    this._selectedZones = new Set();
    this._initialized = false;
  }

  static getStubConfig(hass) {
    const vacuumEntity =
      Object.keys(hass?.states || {}).find(
        (id) =>
          id.startsWith("vacuum.") &&
          hass.states[id]?.attributes?.active_map_id !== undefined
      ) ||
      Object.keys(hass?.states || {}).find((id) => id.startsWith("vacuum.")) ||
      "vacuum.mappa";

    return {
      entity: vacuumEntity,
      default_view: "floor",
      show_zone_labels: true,
      show_controls: true,
    };
  }

  static getConfigElement() {
    return document.createElement("vacuula-map-card-editor");
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Please specify a Vacuula vacuum entity (e.g. vacuum.mappa)");
    }
    this._config = {
      default_view: "floor",
      show_zone_labels: true,
      show_controls: true,
      ...config,
    };
    if (!this._initialized) {
      this._viewMode = this._config.default_view === "run" ? "run" : "floor";
      this._initialized = true;
    }
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._updateContent();
  }

  getCardSize() {
    return 6;
  }

  _slug() {
    const entityId = this._config.entity || "";
    return entityId.includes(".") ? entityId.split(".")[1] : entityId;
  }

  _getState(entityId) {
    return this._hass?.states?.[entityId] || null;
  }

  _toggleZone(zoneName) {
    if (this._selectedZones.has(zoneName)) {
      this._selectedZones.delete(zoneName);
    } else {
      this._selectedZones.add(zoneName);
    }
    this._updateContent();
  }

  _clearZones() {
    this._selectedZones.clear();
    this._updateContent();
  }

  _handleStart() {
    if (!this._hass) return;
    const vacState = this._getState(this._config.entity);
    if (!vacState) return;

    if (this._selectedZones.size > 0 && vacState.state !== "paused") {
      const floorImg = this._getState(
        this._config.floor_map_entity || `image.${this._slug()}_floor_map`
      );
      const serial = floorImg?.attributes?.serial;
      const serviceData = {
        zones: Array.from(this._selectedZones),
      };
      if (serial) {
        serviceData.serial = serial;
      }
      this._hass.callService("vacuula", "clean_zones", serviceData);
      this._selectedZones.clear();
      this._updateContent();
      return;
    }

    this._hass.callService("vacuum", "start", {
      entity_id: this._config.entity,
    });
  }

  _callVacuum(service, extra = {}) {
    if (!this._hass) return;
    this._hass.callService("vacuum", service, {
      entity_id: this._config.entity,
      ...extra,
    });
  }

  _setNavMode(option) {
    if (!this._hass) return;
    const navEntity = `select.${this._slug()}_navigation_mode`;
    if (this._getState(navEntity)) {
      this._hass.callService("select", "select_option", {
        entity_id: navEntity,
        option,
      });
    }
  }

  _refreshMaps() {
    if (!this._hass) return;
    const btnEntity = `button.${this._slug()}_refresh_maps`;
    if (this._getState(btnEntity)) {
      this._hass.callService("button", "press", { entity_id: btnEntity });
    } else {
      this._hass.callService("vacuula", "refresh_maps", {});
    }
  }

  _render() {
    if (!this.shadowRoot) return;
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }
        ha-card {
          overflow: hidden;
          background: var(--ha-card-background, var(--card-background-color, #1e222b));
          color: var(--primary-text-color);
          border-radius: var(--ha-card-border-radius, 16px);
        }
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 14px 16px 10px;
          gap: 10px;
        }
        .title-group {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .title-row {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .robot-name {
          font-size: 1.1rem;
          font-weight: 600;
          letter-spacing: -0.01em;
        }
        .status-badge {
          font-size: 0.72rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          padding: 2px 8px;
          border-radius: 999px;
          background: rgba(148, 163, 184, 0.18);
          color: var(--primary-text-color);
        }
        .status-badge[data-state="cleaning"] {
          background: rgba(56, 189, 248, 0.22);
          color: #38bdf8;
        }
        .status-badge[data-state="docked"] {
          background: rgba(34, 197, 94, 0.2);
          color: #4ade80;
        }
        .status-badge[data-state="returning"] {
          background: rgba(250, 204, 21, 0.22);
          color: #facc15;
        }
        .status-badge[data-state="error"] {
          background: rgba(239, 68, 68, 0.25);
          color: #f87171;
        }
        .subtitle {
          font-size: 0.78rem;
          color: var(--secondary-text-color);
        }
        .telemetry {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 0.82rem;
          font-weight: 600;
        }
        .pill {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          padding: 4px 10px;
          border-radius: 999px;
          background: rgba(148, 163, 184, 0.14);
        }
        .map-wrapper {
          position: relative;
          background: #181c24;
          width: 100%;
          min-height: 240px;
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: hidden;
          border-top: 1px solid rgba(255, 255, 255, 0.06);
          border-bottom: 1px solid rgba(255, 255, 255, 0.06);
        }
        .map-stage {
          position: relative;
          display: inline-block;
          max-width: 100%;
          line-height: 0;
        }
        .map-img {
          display: block;
          width: 100%;
          max-height: 380px;
          object-fit: contain;
          user-select: none;
          -webkit-user-drag: none;
        }
        .zone-svg {
          position: absolute;
          inset: 0;
          width: 100%;
          height: 100%;
          pointer-events: none;
        }
        .zone-poly {
          pointer-events: auto;
          cursor: pointer;
          fill: transparent;
          stroke: transparent;
          stroke-width: 4;
          transition: fill 0.15s ease, stroke 0.15s ease;
        }
        .zone-poly:hover {
          fill: rgba(255, 255, 255, 0.12);
          stroke: rgba(255, 255, 255, 0.65);
        }
        .zone-poly.selected {
          fill: rgba(56, 189, 248, 0.28);
          stroke: #ffffff;
          stroke-width: 6;
          stroke-dasharray: 14 6;
        }
        .zone-pins {
          position: absolute;
          inset: 0;
          pointer-events: none;
        }
        .zone-pin {
          position: absolute;
          transform: translate(-50%, -50%);
          pointer-events: auto;
          cursor: pointer;
          border: 1px solid rgba(255, 255, 255, 0.35);
          background: rgba(15, 23, 42, 0.82);
          backdrop-filter: blur(4px);
          color: #f8fafc;
          font-size: 0.72rem;
          font-weight: 600;
          padding: 3px 8px;
          border-radius: 999px;
          display: inline-flex;
          align-items: center;
          gap: 5px;
          box-shadow: 0 2px 6px rgba(0, 0, 0, 0.45);
          transition: transform 0.12s ease, background 0.12s ease, border-color 0.12s ease;
          white-space: nowrap;
        }
        .zone-pin:hover {
          transform: translate(-50%, -50%) scale(1.06);
        }
        .zone-pin.selected {
          background: #0284c7;
          border-color: #ffffff;
          color: #ffffff;
          transform: translate(-50%, -50%) scale(1.08);
        }
        .dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          display: inline-block;
          flex-shrink: 0;
        }
        .map-toolbar {
          position: absolute;
          top: 10px;
          right: 10px;
          display: flex;
          gap: 4px;
          background: rgba(15, 23, 42, 0.82);
          backdrop-filter: blur(6px);
          padding: 3px;
          border-radius: 10px;
          border: 1px solid rgba(255, 255, 255, 0.12);
          z-index: 2;
        }
        .tab-btn {
          border: none;
          background: transparent;
          color: #cbd5e1;
          font-size: 0.74rem;
          font-weight: 600;
          padding: 4px 9px;
          border-radius: 7px;
          cursor: pointer;
        }
        .tab-btn.active {
          background: #38bdf8;
          color: #0f172a;
        }
        .zones-bar {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          padding: 10px 14px 4px;
          align-items: center;
        }
        .zone-chip {
          border: 1px solid rgba(148, 163, 184, 0.25);
          background: rgba(148, 163, 184, 0.08);
          color: var(--primary-text-color);
          border-radius: 999px;
          padding: 4px 10px;
          font-size: 0.76rem;
          font-weight: 500;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          cursor: pointer;
          transition: all 0.12s ease;
        }
        .zone-chip.selected {
          background: rgba(56, 189, 248, 0.22);
          border-color: #38bdf8;
          color: #38bdf8;
          font-weight: 600;
        }
        .controls-section {
          padding: 10px 14px 14px;
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .action-row {
          display: grid;
          grid-template-columns: 2fr repeat(4, 1fr);
          gap: 8px;
        }
        .btn {
          border: 1px solid rgba(148, 163, 184, 0.2);
          background: rgba(148, 163, 184, 0.1);
          color: var(--primary-text-color);
          border-radius: 10px;
          padding: 9px 10px;
          font-size: 0.8rem;
          font-weight: 600;
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
          transition: background 0.12s ease, transform 0.1s ease;
        }
        .btn:hover {
          background: rgba(148, 163, 184, 0.2);
        }
        .btn:active {
          transform: scale(0.98);
        }
        .btn.primary {
          background: #0284c7;
          border-color: #38bdf8;
          color: #ffffff;
        }
        .btn.primary:hover {
          background: #0369a1;
        }
        .modes-row {
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 8px;
          flex-wrap: wrap;
        }
        .mode-group {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          background: rgba(148, 163, 184, 0.1);
          padding: 3px;
          border-radius: 9px;
        }
        .mode-btn {
          border: none;
          background: transparent;
          color: var(--secondary-text-color);
          font-size: 0.72rem;
          font-weight: 600;
          padding: 4px 8px;
          border-radius: 6px;
          cursor: pointer;
          text-transform: capitalize;
        }
        .mode-btn.active {
          background: rgba(56, 189, 248, 0.24);
          color: #38bdf8;
        }
        .empty-map {
          padding: 48px 20px;
          text-align: center;
          color: #94a3b8;
          font-size: 0.85rem;
        }
      </style>
      <ha-card>
        <div id="root"></div>
      </ha-card>
    `;
    this._updateContent();
  }

  _updateContent() {
    const root = this.shadowRoot?.getElementById("root");
    if (!root || !this._hass) return;

    const slug = this._slug();
    const vacState = this._getState(this._config.entity);
    if (!vacState) {
      root.innerHTML = `<div class="empty-map">Entity <b>${this._config.entity}</b> not found</div>`;
      return;
    }

    const floorImgId =
      this._config.floor_map_entity || `image.${slug}_floor_map`;
    const runImgId =
      this._config.last_run_map_entity || `image.${slug}_last_run_map`;
    const floorState = this._getState(floorImgId);
    const runState = this._getState(runImgId);

    const activeImgState =
      this._viewMode === "run" && runState ? runState : floorState || runState;
    const imgUrl = activeImgState?.attributes?.entity_picture || "";

    const zones =
      floorState?.attributes?.zones ||
      activeImgState?.attributes?.zones ||
      [];

    const battState = this._getState(`sensor.${slug}_battery`);
    const chargingState = this._getState(`binary_sensor.${slug}_charging`);
    const areaState = this._getState(`sensor.${slug}_last_clean_area`);
    const durState = this._getState(`sensor.${slug}_last_clean_duration`);
    const navSelectState = this._getState(`select.${slug}_navigation_mode`);

    const name =
      this._config.title ||
      vacState.attributes?.friendly_name ||
      slug;
    const stateStr = vacState.state || "unknown";
    const actionStr = vacState.attributes?.action || "";
    const mapName =
      floorState?.attributes?.map_name ||
      vacState.attributes?.active_map_name ||
      "Floor Plan";

    const batteryVal = battState?.state && battState.state !== "unavailable"
      ? `${battState.state}%`
      : null;
    const isCharging = chargingState?.state === "on";

    const lastRunParts = [];
    if (areaState?.state && !["unknown", "unavailable"].includes(areaState.state)) {
      lastRunParts.push(`${areaState.state} m²`);
    }
    if (durState?.state && !["unknown", "unavailable"].includes(durState.state)) {
      lastRunParts.push(`${durState.state} min`);
    }
    const subtitleParts = [mapName];
    if (actionStr && actionStr !== "idle") subtitleParts.push(actionStr.replace(/_/g, " "));
    if (lastRunParts.length) subtitleParts.push(`Last: ${lastRunParts.join(" · ")}`);

    const selectedCount = this._selectedZones.size;
    let startLabel = "Clean All";
    if (stateStr === "paused") {
      startLabel = "Resume";
    } else if (selectedCount === 1) {
      startLabel = `Clean ${Array.from(this._selectedZones)[0]}`;
    } else if (selectedCount > 1) {
      startLabel = `Clean ${selectedCount} Rooms`;
    }

    const fanSpeeds = vacState.attributes?.fan_speed_list || ["eco", "turbo"];
    const currentFan = vacState.attributes?.fan_speed || "turbo";
    const navModes = navSelectState?.attributes?.options || ["normal", "extra_care", "deep"];
    const currentNav =
      navSelectState?.state ||
      vacState.attributes?.navigation_mode ||
      "normal";

    const svgPolygons = zones
      .filter((z) => Array.isArray(z.points) && z.points.length >= 3)
      .map((z) => {
        const ptsStr = z.points
          .map((p) => `${Math.round(p[0] * 1000)},${Math.round(p[1] * 1000)}`)
          .join(" ");
        const isSel = this._selectedZones.has(z.name);
        return `<polygon class="zone-poly ${isSel ? "selected" : ""}" data-zone="${z.name}" points="${ptsStr}" />`;
      })
      .join("");

    const zonePins =
      this._config.show_zone_labels !== false
        ? zones
            .filter((z) => typeof z.x === "number" && typeof z.y === "number")
            .map((z) => {
              const isSel = this._selectedZones.has(z.name);
              const color = z.color || "#38bdf8";
              return `
                <button class="zone-pin ${isSel ? "selected" : ""}" data-zone="${z.name}" style="left:${(z.x * 100).toFixed(1)}%;top:${(z.y * 100).toFixed(1)}%;">
                  <span class="dot" style="background:${color}"></span>
                  <span>${isSel ? "✓ " : ""}${z.name}</span>
                </button>
              `;
            })
            .join("")
        : "";

    const zoneChips = zones.length
      ? `
        <div class="zones-bar">
          ${zones
            .map((z) => {
              const isSel = this._selectedZones.has(z.name);
              const color = z.color || "#38bdf8";
              return `
                <button class="zone-chip ${isSel ? "selected" : ""}" data-zone="${z.name}">
                  <span class="dot" style="background:${color}"></span>
                  <span>${isSel ? "✓ " : ""}${z.name}</span>
                </button>
              `;
            })
            .join("")}
          ${
            selectedCount > 0
              ? `<button class="zone-chip" id="clear-zones-btn" title="Clear selection">✕ Clear</button>`
              : ""
          }
        </div>
      `
      : "";

    root.innerHTML = `
      <div class="header">
        <div class="title-group">
          <div class="title-row">
            <span class="robot-name">${name}</span>
            <span class="status-badge" data-state="${stateStr}">${stateStr}</span>
          </div>
          <div class="subtitle">${subtitleParts.join(" • ")}</div>
        </div>
        <div class="telemetry">
          ${
            batteryVal
              ? `<span class="pill" title="Battery">${isCharging ? "⚡" : "🔋"} ${batteryVal}</span>`
              : ""
          }
        </div>
      </div>

      <div class="map-wrapper">
        <div class="map-toolbar">
          <button class="tab-btn ${this._viewMode === "floor" ? "active" : ""}" id="tab-floor">Floor Plan</button>
          <button class="tab-btn ${this._viewMode === "run" ? "active" : ""}" id="tab-run">Last Run</button>
          <button class="tab-btn" id="btn-refresh-map" title="Refresh Maps">↻</button>
        </div>
        ${
          imgUrl
            ? `
              <div class="map-stage">
                <img class="map-img" src="${imgUrl}" alt="Vacuum Map" />
                <svg class="zone-svg" viewBox="0 0 1000 1000" preserveAspectRatio="none">
                  ${svgPolygons}
                </svg>
                <div class="zone-pins">
                  ${zonePins}
                </div>
              </div>
            `
            : `<div class="empty-map">No floor map available yet</div>`
        }
      </div>

      ${zoneChips}

      ${
        this._config.show_controls !== false
          ? `
            <div class="controls-section">
              <div class="action-row">
                <button class="btn primary" id="btn-start">▶ ${startLabel}</button>
                <button class="btn" id="btn-pause" title="Pause">⏸</button>
                <button class="btn" id="btn-stop" title="Stop">⏹</button>
                <button class="btn" id="btn-dock" title="Return to Base">⌂ Dock</button>
                <button class="btn" id="btn-locate" title="Locate Robot">🔊</button>
              </div>
              <div class="modes-row">
                <div class="mode-group" title="Fan Speed">
                  ${fanSpeeds
                    .map(
                      (spd) =>
                        `<button class="mode-btn ${spd === currentFan ? "active" : ""}" data-fan="${spd}">${spd}</button>`
                    )
                    .join("")}
                </div>
                <div class="mode-group" title="Navigation Mode">
                  ${navModes
                    .map(
                      (nav) =>
                        `<button class="mode-btn ${nav === currentNav ? "active" : ""}" data-nav="${nav}">${nav.replace(/_/g, " ")}</button>`
                    )
                    .join("")}
                </div>
              </div>
            </div>
          `
          : ""
      }
    `;

    // Bind event listeners
    root.querySelector("#tab-floor")?.addEventListener("click", () => {
      this._viewMode = "floor";
      this._updateContent();
    });
    root.querySelector("#tab-run")?.addEventListener("click", () => {
      this._viewMode = "run";
      this._updateContent();
    });
    root.querySelector("#btn-refresh-map")?.addEventListener("click", () => {
      this._refreshMaps();
    });

    root.querySelectorAll("[data-zone]").forEach((el) => {
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const zName = el.getAttribute("data-zone");
        if (zName) this._toggleZone(zName);
      });
    });

    root.querySelector("#clear-zones-btn")?.addEventListener("click", () => {
      this._clearZones();
    });

    root.querySelector("#btn-start")?.addEventListener("click", () => {
      this._handleStart();
    });
    root.querySelector("#btn-pause")?.addEventListener("click", () => {
      this._callVacuum("pause");
    });
    root.querySelector("#btn-stop")?.addEventListener("click", () => {
      this._callVacuum("stop");
    });
    root.querySelector("#btn-dock")?.addEventListener("click", () => {
      this._callVacuum("return_to_base");
    });
    root.querySelector("#btn-locate")?.addEventListener("click", () => {
      this._callVacuum("locate");
    });

    root.querySelectorAll("[data-fan]").forEach((el) => {
      el.addEventListener("click", () => {
        const fan = el.getAttribute("data-fan");
        if (fan) this._callVacuum("set_fan_speed", { fan_speed: fan });
      });
    });

    root.querySelectorAll("[data-nav]").forEach((el) => {
      el.addEventListener("click", () => {
        const nav = el.getAttribute("data-nav");
        if (nav) this._setNavMode(nav);
      });
    });
  }
}

class VacuulaMapCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
  }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _emit(newConfig) {
    this._config = newConfig;
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: this._config },
        bubbles: true,
        composed: true,
      })
    );
  }

  _render() {
    if (!this.shadowRoot || !this._hass) return;
    const vacuums = Object.keys(this._hass.states).filter((id) =>
      id.startsWith("vacuum.")
    );

    this.shadowRoot.innerHTML = `
      <style>
        .form {
          display: flex;
          flex-direction: column;
          gap: 12px;
          padding: 8px 0;
        }
        label {
          display: flex;
          flex-direction: column;
          gap: 4px;
          font-size: 0.85rem;
          font-weight: 500;
        }
        select, input[type="text"] {
          padding: 8px;
          border-radius: 6px;
          border: 1px solid var(--divider-color, #475569);
          background: var(--card-background-color, #1e293b);
          color: var(--primary-text-color, #f8fafc);
        }
        .row {
          flex-direction: row;
          align-items: center;
          justify-content: space-between;
        }
      </style>
      <div class="form">
        <label>
          Vacuum Entity
          <select id="entity">
            ${vacuums
              .map(
                (v) =>
                  `<option value="${v}" ${v === this._config.entity ? "selected" : ""}>${v}</option>`
              )
              .join("")}
          </select>
        </label>
        <label>
          Card Title (optional)
          <input type="text" id="title" value="${this._config.title || ""}" placeholder="Auto (Robot Name)" />
        </label>
        <label>
          Default Map View
          <select id="default_view">
            <option value="floor" ${(this._config.default_view || "floor") === "floor" ? "selected" : ""}>Floor Plan & Zones</option>
            <option value="run" ${this._config.default_view === "run" ? "selected" : ""}>Last Cleaning Run</option>
          </select>
        </label>
        <label class="row">
          <span>Show Room Pins on Map</span>
          <input type="checkbox" id="show_zone_labels" ${this._config.show_zone_labels !== false ? "checked" : ""} />
        </label>
        <label class="row">
          <span>Show Vacuum Controls</span>
          <input type="checkbox" id="show_controls" ${this._config.show_controls !== false ? "checked" : ""} />
        </label>
      </div>
    `;

    this.shadowRoot.querySelector("#entity")?.addEventListener("change", (e) => {
      this._emit({ ...this._config, entity: e.target.value });
    });
    this.shadowRoot.querySelector("#title")?.addEventListener("input", (e) => {
      this._emit({ ...this._config, title: e.target.value });
    });
    this.shadowRoot
      .querySelector("#default_view")
      ?.addEventListener("change", (e) => {
        this._emit({ ...this._config, default_view: e.target.value });
      });
    this.shadowRoot
      .querySelector("#show_zone_labels")
      ?.addEventListener("change", (e) => {
        this._emit({ ...this._config, show_zone_labels: e.target.checked });
      });
    this.shadowRoot
      .querySelector("#show_controls")
      ?.addEventListener("change", (e) => {
        this._emit({ ...this._config, show_controls: e.target.checked });
      });
  }
}

if (!customElements.get("vacuula-map-card")) {
  customElements.define("vacuula-map-card", VacuulaMapCard);
}
if (!customElements.get("vacuula-map-card-editor")) {
  customElements.define("vacuula-map-card-editor", VacuulaMapCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "vacuula-map-card")) {
  window.customCards.push({
    type: "vacuula-map-card",
    name: "Vacuula Map & Room Card",
    description:
      "Interactive floor map, clickable room zone selector, last run coverage, and controls for Vacuula Neato robots.",
    preview: true,
  });
}
