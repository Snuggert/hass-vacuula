/**
 * Vacuula Map & Room Card for Home Assistant
 * Auto-registered by the hass-vacuula integration.
 */

const ESC_MAP = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

function escapeHtml(val) {
  return String(val ?? "").replace(/[&<>"']/g, (ch) => ESC_MAP[ch]);
}

function sanitizeColor(val) {
  const str = String(val ?? "").trim();
  if (/^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{1,20})$/.test(str)) {
    return str;
  }
  return "#38bdf8";
}

function sanitizeImgUrl(val) {
  const str = String(val ?? "").trim();
  if (str.startsWith("/") || /^https?:\/\//i.test(str)) {
    return escapeHtml(str);
  }
  return "";
}

function renderAlertIcon(iconType) {
  if (iconType === "bin") {
    return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>';
  }
  if (iconType === "error" || iconType === "sensor") {
    return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>';
  }
  if (iconType === "battery") {
    return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="6" width="18" height="12" rx="2"/><line x1="23" y1="11" x2="23" y2="13"/></svg>';
  }
  if (iconType === "picked_up") {
    return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>';
  }
  return '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
}

const ALERT_INFO_MAP = {
  dustbin_full: {
    icon: "bin",
    title: "Dust Bin Full",
    message: "Empty the robot's dust bin and clean filter.",
    severity: "warning",
    isBin: true,
  },
  ui_alert_dust_bin_full: {
    icon: "bin",
    title: "Dust Bin Full",
    message: "Empty the robot's dust bin and clean filter.",
    severity: "warning",
    isBin: true,
  },
  ui_error_dust_bin_full: {
    icon: "bin",
    title: "Dust Bin Full",
    message: "Empty the robot's dust bin and clean filter.",
    severity: "warning",
    isBin: true,
  },
  dustbin_missing: {
    icon: "bin",
    title: "Dust Bin Missing",
    message: "Insert the dust bin firmly back into the robot.",
    severity: "warning",
    isBin: true,
  },
  ui_alert_dust_bin_missing: {
    icon: "bin",
    title: "Dust Bin Missing",
    message: "Insert the dust bin firmly back into the robot.",
    severity: "warning",
    isBin: true,
  },
  brush_stuck: {
    icon: "warning",
    title: "Brush Stuck",
    message: "Remove hair or debris from the main brush roller.",
    severity: "error",
    isBin: false,
  },
  ui_error_brush_stuck: {
    icon: "warning",
    title: "Brush Stuck",
    message: "Remove hair or debris from the main brush roller.",
    severity: "error",
    isBin: false,
  },
  brush_overload: {
    icon: "warning",
    title: "Brush Overloaded",
    message: "Main brush roller is overloaded; please check for tangled debris.",
    severity: "error",
    isBin: false,
  },
  navigation_stuck: {
    icon: "error",
    title: "Robot Stuck",
    message: "Clear obstacles around the robot and move to open floor.",
    severity: "error",
    isBin: false,
  },
  ui_error_navigation_stuck: {
    icon: "error",
    title: "Robot Stuck",
    message: "Clear obstacles around the robot and move to open floor.",
    severity: "error",
    isBin: false,
  },
  stuck: {
    icon: "error",
    title: "Robot Stuck",
    message: "Clear obstacles around the robot and move to open floor.",
    severity: "error",
    isBin: false,
  },
  clear_path: {
    icon: "warning",
    title: "Clear Path",
    message: "Robot path is blocked; please clear surrounding floor space.",
    severity: "warning",
    isBin: false,
  },
  ui_alert_clear_path: {
    icon: "warning",
    title: "Clear Path",
    message: "Robot path is blocked; please clear surrounding floor space.",
    severity: "warning",
    isBin: false,
  },
  robot_picked_up: {
    icon: "picked_up",
    title: "Robot Picked Up",
    message: "Place the robot back down onto the floor.",
    severity: "warning",
    isBin: false,
  },
  ui_error_picked_up: {
    icon: "picked_up",
    title: "Robot Picked Up",
    message: "Place the robot back down onto the floor.",
    severity: "warning",
    isBin: false,
  },
  cliff_sensor: {
    icon: "sensor",
    title: "Drop Sensor Error",
    message: "Clean the optical drop sensors on the underside of the robot.",
    severity: "error",
    isBin: false,
  },
  ui_error_drop_sensor: {
    icon: "sensor",
    title: "Drop Sensor Error",
    message: "Clean the optical drop sensors on the underside of the robot.",
    severity: "error",
    isBin: false,
  },
  lid_open: {
    icon: "warning",
    title: "Top Cover Open",
    message: "Close the robot's top dust bin cover.",
    severity: "warning",
    isBin: true,
  },
  battery_low: {
    icon: "battery",
    title: "Low Battery",
    message: "Battery level is low; returning to charge base.",
    severity: "info",
    isBin: false,
  },
  ui_alert_battery_low: {
    icon: "battery",
    title: "Low Battery",
    message: "Battery level is low; returning to charge base.",
    severity: "info",
    isBin: false,
  },
};

function formatAlertCode(code) {
  const clean = String(code ?? "")
    .replace(/^ui_(alert|error)_/, "")
    .replace(/_/g, " ")
    .trim();
  if (!clean) return "Unknown Alert";
  return clean.charAt(0).toUpperCase() + clean.slice(1);
}

class VacuulaMapCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._viewMode = "floor"; // "floor" | "run"
    this._selectedZones = new Set();
    this._initialized = false;
    this._lastRenderSignature = "";
  }

  static getStubConfig(hass) {
    const vacuumEntity =
      Object.keys(hass?.states || {}).find(
        (id) => id.startsWith("vacuum.") && hass.states[id]?.attributes?.active_map_id !== undefined
      ) ||
      Object.keys(hass?.states || {}).find((id) => id.startsWith("vacuum.")) ||
      "vacuum.neato_botvac";

    return {
      entity: vacuumEntity,
      default_view: "floor",
      map_height: "auto",
      expand_on_desktop: true,
      show_alerts: true,
      show_bin_alert: true,
      show_header: true,
      show_status_badge: true,
      show_battery: true,
      show_schedule: true,
      show_toolbar: true,
      show_zone_labels: true,
      show_zone_chips: true,
      show_controls: true,
      show_modes: true,
    };
  }

  static getConfigElement() {
    return document.createElement("vacuula-map-card-editor");
  }

  getGridOptions() {
    return {
      columns: 12,
      rows: "auto",
      min_columns: 6,
      min_rows: 4,
    };
  }

  getCardSize() {
    const val = String(this._config.map_height || "auto").toLowerCase();
    if (val === "large" || val === "xlarge") return 9;
    if (val === "compact") return 4;
    return 6;
  }

  setConfig(config) {
    if (!config?.entity) {
      throw new Error("Please specify a Vacuula vacuum entity (e.g. vacuum.neato_botvac)");
    }
    const defaultView = config.default_view ?? config.default_map ?? "floor";
    const showZoneLabels = config.show_zone_labels ?? config.show_zones ?? true;
    const showControls = config.show_controls !== false;
    const showModes = config.show_modes !== false;
    const showHeader = config.show_header !== false;
    const showStatusBadge = config.show_status_badge !== false;
    const showBattery = config.show_battery !== false;
    const showSchedule = config.show_schedule !== false;
    const showToolbar = config.show_toolbar !== false;
    const showZoneChips = config.show_zone_chips !== false;
    const showAlerts = config.show_alerts !== false;
    const showBinAlert = config.show_bin_alert !== false;
    const expandOnDesktop = config.expand_on_desktop !== false;
    const mapHeight = config.map_height || "auto";

    this._config = {
      default_view: defaultView,
      map_height: mapHeight,
      expand_on_desktop: expandOnDesktop,
      show_zone_labels: showZoneLabels,
      show_zone_chips: showZoneChips,
      show_controls: showControls,
      show_modes: showModes,
      show_header: showHeader,
      show_status_badge: showStatusBadge,
      show_battery: showBattery,
      show_schedule: showSchedule,
      show_toolbar: showToolbar,
      show_alerts: showAlerts,
      show_bin_alert: showBinAlert,
      ...config,
    };

    if (!this._initialized) {
      this._viewMode = this._config.default_view === "run" ? "run" : "floor";
      this._initialized = true;
    }
    this._lastRenderSignature = "";
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const sig = this._computeSignature();
    if (sig !== this._lastRenderSignature) {
      this._lastRenderSignature = sig;
      this._updateContent();
    }
  }

  _slug() {
    const entityId = this._config.entity || "";
    return entityId.includes(".") ? entityId.split(".")[1] : entityId;
  }

  _getState(entityId) {
    return this._hass?.states?.[entityId] || null;
  }

  _resolveAlert() {
    const slug = this._slug();
    const vacState = this._getState(this._config.entity);
    const alertSensor = this._getState(`sensor.${slug}_alert`);
    const binSensor =
      this._getState(`binary_sensor.${slug}_dust_bin_full`) ||
      this._getState(`binary_sensor.${slug}_bin_full`);

    let rawCode = "";
    if (binSensor?.state === "on") {
      rawCode = binSensor.attributes?.alert || "dustbin_full";
    } else if (
      alertSensor?.state &&
      !["none", "unknown", "unavailable"].includes(alertSensor.state)
    ) {
      rawCode = alertSensor.state;
    } else if (vacState?.attributes?.alert) {
      rawCode = vacState.attributes.alert;
    } else if (vacState?.attributes?.error) {
      rawCode = vacState.attributes.error;
    } else if (Array.isArray(vacState?.attributes?.errors) && vacState.attributes.errors.length) {
      const first = vacState.attributes.errors[0];
      rawCode = typeof first === "object" ? first?.code || "" : String(first);
    }

    if (!rawCode) return null;

    const lower = String(rawCode).toLowerCase().trim();
    const known = ALERT_INFO_MAP[lower];
    const isBinFull = lower.includes("dustbin") || lower.includes("bin_full");
    const dismissButton = this._getState(`button.${slug}_dismiss_alert`);

    if (known) {
      return {
        code: lower,
        title: known.title,
        message: known.message,
        severity: known.severity,
        icon: known.icon,
        isBin: known.isBin,
        canDismiss: Boolean(dismissButton),
      };
    }

    return {
      code: lower,
      title: formatAlertCode(rawCode),
      message: `Active condition: ${formatAlertCode(rawCode)}.`,
      severity: "warning",
      icon: isBinFull ? "bin" : "warning",
      isBin: isBinFull,
      canDismiss: Boolean(dismissButton),
    };
  }

  _computeSignature() {
    if (!this._hass || !this._config.entity) return "";
    const slug = this._slug();
    const vac = this._getState(this._config.entity);
    const floor = this._getState(this._config.floor_map_entity || `image.${slug}_floor_map`);
    const run = this._getState(this._config.last_run_map_entity || `image.${slug}_last_run_map`);
    const batt = this._getState(`sensor.${slug}_battery`);
    const chg = this._getState(`binary_sensor.${slug}_charging`);
    const binSensor =
      this._getState(`binary_sensor.${slug}_dust_bin_full`) ||
      this._getState(`binary_sensor.${slug}_bin_full`);
    const alertSensor = this._getState(`sensor.${slug}_alert`);
    const area = this._getState(`sensor.${slug}_last_clean_area`);
    const dur = this._getState(`sensor.${slug}_last_clean_duration`);
    const nav = this._getState(`select.${slug}_navigation_mode`);
    const sched = this._getState(`switch.${slug}_schedule`);

    return JSON.stringify([
      this._viewMode,
      Array.from(this._selectedZones),
      vac?.state,
      vac?.attributes?.friendly_name,
      vac?.attributes?.fan_speed,
      vac?.attributes?.navigation_mode,
      vac?.attributes?.action,
      vac?.attributes?.alert,
      vac?.attributes?.error,
      vac?.attributes?.errors,
      vac?.attributes?.active_map_name,
      floor?.state,
      floor?.attributes?.entity_picture,
      floor?.attributes?.map_name,
      floor?.attributes?.zones,
      run?.state,
      run?.attributes?.entity_picture,
      batt?.state,
      chg?.state,
      binSensor?.state,
      binSensor?.attributes?.alert,
      alertSensor?.state,
      area?.state,
      dur?.state,
      nav?.state,
      sched?.state,
      this._config.title,
      this._config.map_height,
      this._config.expand_on_desktop,
      this._config.show_alerts,
      this._config.show_bin_alert,
      this._config.show_header,
      this._config.show_status_badge,
      this._config.show_battery,
      this._config.show_schedule,
      this._config.show_toolbar,
      this._config.show_zone_labels,
      this._config.show_zone_chips,
      this._config.show_controls,
      this._config.show_modes,
    ]);
  }

  _forceUpdate() {
    this._lastRenderSignature = this._computeSignature();
    this._updateContent();
  }

  _toggleZone(zoneName) {
    if (this._selectedZones.has(zoneName)) {
      this._selectedZones.delete(zoneName);
    } else {
      this._selectedZones.add(zoneName);
    }
    this._forceUpdate();
  }

  _clearZones() {
    this._selectedZones.clear();
    this._forceUpdate();
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
        entity_id: this._config.entity,
        zones: Array.from(this._selectedZones),
      };
      if (serial) {
        serviceData.serial = serial;
      }
      this._hass.callService("vacuula", "clean_zones", serviceData);
      this._selectedZones.clear();
      this._forceUpdate();
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

  _toggleSchedule() {
    if (!this._hass) return;
    const schedEntity = `switch.${this._slug()}_schedule`;
    if (this._getState(schedEntity)) {
      this._hass.callService("switch", "toggle", {
        entity_id: schedEntity,
      });
    }
  }

  _dismissAlert() {
    if (!this._hass) return;
    const btnEntity = `button.${this._slug()}_dismiss_alert`;
    if (this._getState(btnEntity)) {
      this._hass.callService("button", "press", { entity_id: btnEntity });
    }
  }

  _refreshMaps() {
    if (!this._hass) return;
    const btnEntity = `button.${this._slug()}_refresh_maps`;
    if (this._getState(btnEntity)) {
      this._hass.callService("button", "press", { entity_id: btnEntity });
    } else {
      this._hass.callService("vacuula", "refresh_maps", {
        entity_id: this._config.entity,
      });
    }
  }

  _getCustomHeightVars() {
    const val = String(this._config.map_height || "auto")
      .trim()
      .toLowerCase();
    switch (val) {
      case "compact":
        return "--vacuula-map-max-height: 320px; --vacuula-map-min-height: 200px;";
      case "medium":
        return "--vacuula-map-max-height: 450px; --vacuula-map-min-height: 300px;";
      case "large":
        return "--vacuula-map-max-height: 620px; --vacuula-map-min-height: 400px;";
      case "xlarge":
        return "--vacuula-map-max-height: 800px; --vacuula-map-min-height: 500px;";
      case "auto":
        return "";
      default:
        if (/^[0-9]+(px|vh|rem|em|%)$/.test(val)) {
          return `--vacuula-map-max-height: ${val}; --vacuula-map-min-height: ${val};`;
        }
        return "";
    }
  }

  _render() {
    if (!this.shadowRoot) return;
    const customVars = this._getCustomHeightVars();
    const expandAttr = this._config.expand_on_desktop !== false ? "true" : "false";

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          ${customVars}
        }
        :host([panel]) ha-card,
        ha-card.panel-mode {
          height: 100%;
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
          flex-wrap: wrap;
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
          gap: 6px;
          font-size: 0.8rem;
          font-weight: 600;
          flex-wrap: wrap;
        }
        .pill {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          padding: 4px 10px;
          border-radius: 999px;
          background: rgba(148, 163, 184, 0.14);
          border: none;
          color: var(--primary-text-color);
          font-size: 0.78rem;
          font-weight: 600;
        }
        .pill.clickable {
          cursor: pointer;
        }
        .pill.active {
          background: rgba(34, 197, 94, 0.2);
          color: #4ade80;
        }

        /* Active Alert & Notification Banner */
        .alert-banner {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          padding: 10px 14px;
          border-top: 1px solid transparent;
          border-bottom: 1px solid transparent;
          transition: background 0.15s ease;
        }
        .alert-banner.warning {
          background: rgba(245, 158, 11, 0.14);
          border-color: rgba(245, 158, 11, 0.35);
          color: #fbbf24;
        }
        .alert-banner.error {
          background: rgba(239, 68, 68, 0.16);
          border-color: rgba(239, 68, 68, 0.35);
          color: #f87171;
        }
        .alert-banner.info {
          background: rgba(56, 189, 248, 0.15);
          border-color: rgba(56, 189, 248, 0.35);
          color: #38bdf8;
        }
        .alert-left {
          display: flex;
          align-items: center;
          gap: 9px;
          min-width: 0;
        }
        .alert-icon {
          font-size: 1.25rem;
          line-height: 1;
          flex-shrink: 0;
        }
        .alert-text-group {
          display: flex;
          flex-direction: column;
          gap: 1px;
          min-width: 0;
        }
        .alert-title {
          font-size: 0.82rem;
          font-weight: 700;
          letter-spacing: -0.01em;
          color: #ffffff;
        }
        .alert-desc {
          font-size: 0.74rem;
          color: var(--secondary-text-color, #cbd5e1);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .alert-dismiss-btn {
          border: 1px solid currentColor;
          background: transparent;
          color: inherit;
          font-size: 0.72rem;
          font-weight: 600;
          padding: 3px 8px;
          border-radius: 6px;
          cursor: pointer;
          white-space: nowrap;
          flex-shrink: 0;
          transition: background 0.12s ease;
        }
        .alert-dismiss-btn:hover {
          background: rgba(255, 255, 255, 0.12);
        }

        /* Map Viewport & Stage */
        .map-wrapper {
          position: relative;
          background: #181c24;
          width: 100%;
          min-height: var(--vacuula-map-min-height, 240px);
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
          max-height: var(--vacuula-map-max-height, 380px);
          object-fit: contain;
          image-rendering: crisp-edges;
          user-select: none;
          -webkit-user-drag: none;
        }

        /* Responsive Large Monitor Scaling */
        @media (min-width: 600px) {
          :host(:not([data-expand="false"])) .map-wrapper {
            min-height: var(--vacuula-map-min-height, 320px);
          }
          :host(:not([data-expand="false"])) .map-img {
            max-height: var(--vacuula-map-max-height, 520px);
          }
        }
        @media (min-width: 1024px) {
          :host(:not([data-expand="false"])) .map-wrapper {
            min-height: var(--vacuula-map-min-height, 400px);
          }
          :host(:not([data-expand="false"])) .map-img {
            max-height: var(--vacuula-map-max-height, 660px);
          }
        }
        @media (min-width: 1440px) {
          :host(:not([data-expand="false"])) .map-wrapper {
            min-height: var(--vacuula-map-min-height, 460px);
          }
          :host(:not([data-expand="false"])) .map-img {
            max-height: var(--vacuula-map-max-height, 800px);
          }
        }
        :host([panel]) .map-wrapper,
        ha-card.panel-mode .map-wrapper {
          min-height: 480px;
        }
        :host([panel]) .map-img,
        ha-card.panel-mode .map-img {
          max-height: calc(100vh - 280px);
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
          background: #0f172a;
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
          background: #0f172a;
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
      <ha-card data-expand="${expandAttr}">
        <div id="root"></div>
      </ha-card>
    `;
    this._forceUpdate();
  }

  _updateContent() {
    const root = this.shadowRoot?.getElementById("root");
    if (!root || !this._hass) return;

    const slug = this._slug();
    const vacState = this._getState(this._config.entity);
    if (!vacState) {
      root.innerHTML = `<div class="empty-map">Entity <b>${escapeHtml(this._config.entity)}</b> not found</div>`;
      return;
    }

    const floorImgId = this._config.floor_map_entity || `image.${slug}_floor_map`;
    const runImgId = this._config.last_run_map_entity || `image.${slug}_last_run_map`;
    const floorState = this._getState(floorImgId);
    const runState = this._getState(runImgId);

    const activeImgState = this._viewMode === "run" && runState ? runState : floorState || runState;
    const imgUrl = sanitizeImgUrl(activeImgState?.attributes?.entity_picture || "");

    const zones = floorState?.attributes?.zones || activeImgState?.attributes?.zones || [];

    const battState = this._getState(`sensor.${slug}_battery`);
    const chargingState = this._getState(`binary_sensor.${slug}_charging`);
    const areaState = this._getState(`sensor.${slug}_last_clean_area`);
    const durState = this._getState(`sensor.${slug}_last_clean_duration`);
    const navSelectState = this._getState(`select.${slug}_navigation_mode`);
    const schedState = this._getState(`switch.${slug}_schedule`);
    const activeAlert = this._resolveAlert();

    const name = this._config.title || vacState.attributes?.friendly_name || slug;
    const stateStr = vacState.state || "unknown";
    const actionStr = vacState.attributes?.action || "";
    const mapName =
      floorState?.attributes?.map_name || vacState.attributes?.active_map_name || "Floor Plan";

    const batteryVal =
      battState?.state && !["unknown", "unavailable"].includes(battState.state)
        ? `${battState.state}%`
        : null;
    const isCharging = chargingState?.state === "on";
    const isScheduleOn = schedState?.state === "on";

    const lastRunParts = [];
    if (areaState?.state && !["unknown", "unavailable"].includes(areaState.state)) {
      lastRunParts.push(`${areaState.state} m²`);
    }
    if (durState?.state && !["unknown", "unavailable"].includes(durState.state)) {
      lastRunParts.push(`${durState.state} min`);
    }
    const subtitleParts = [mapName];
    if (actionStr && actionStr !== "idle") subtitleParts.push(String(actionStr).replace(/_/g, " "));
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
    const currentNav = navSelectState?.state || vacState.attributes?.navigation_mode || "normal";

    const svgPolygons = zones
      .filter((z) => Array.isArray(z.points) && z.points.length >= 3)
      .map((z) => {
        const ptsStr = z.points
          .map((p) => `${Math.round(Number(p[0]) * 1000)},${Math.round(Number(p[1]) * 1000)}`)
          .join(" ");
        const isSel = this._selectedZones.has(z.name);
        const zNameEsc = escapeHtml(z.name);
        return `<polygon class="zone-poly ${isSel ? "selected" : ""}" data-zone="${zNameEsc}" points="${escapeHtml(ptsStr)}" />`;
      })
      .join("");

    const zonePins =
      this._config.show_zone_labels !== false
        ? zones
            .filter((z) => typeof z.x === "number" && typeof z.y === "number")
            .map((z) => {
              const isSel = this._selectedZones.has(z.name);
              const zNameEsc = escapeHtml(z.name);
              const color = sanitizeColor(z.color);
              const leftPct = (Number(z.x) * 100).toFixed(1);
              const topPct = (Number(z.y) * 100).toFixed(1);
              return `
                <button class="zone-pin ${isSel ? "selected" : ""}" data-zone="${zNameEsc}" style="left:${leftPct}%;top:${topPct}%;">
                  <span class="dot" style="background:${color}"></span>
                  <span>${isSel ? "✓ " : ""}${zNameEsc}</span>
                </button>
              `;
            })
            .join("")
        : "";

    const zoneChips =
      zones.length && this._config.show_zone_chips !== false
        ? `
        <div class="zones-bar">
          ${zones
            .map((z) => {
              const isSel = this._selectedZones.has(z.name);
              const zNameEsc = escapeHtml(z.name);
              const color = sanitizeColor(z.color);
              return `
                <button class="zone-chip ${isSel ? "selected" : ""}" data-zone="${zNameEsc}">
                  <span class="dot" style="background:${color}"></span>
                  <span>${isSel ? "✓ " : ""}${zNameEsc}</span>
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

    const stateEsc = escapeHtml(stateStr);

    const alertBannerHtml =
      activeAlert && this._config.show_alerts !== false
        ? `
          <div class="alert-banner ${escapeHtml(activeAlert.severity)}">
            <div class="alert-left">
              <span class="alert-icon">${renderAlertIcon(activeAlert.icon || activeAlert.severity)}</span>
              <div class="alert-text-group">
                <span class="alert-title">${escapeHtml(activeAlert.title)}</span>
                <span class="alert-desc" title="${escapeHtml(activeAlert.message)}">${escapeHtml(activeAlert.message)}</span>
              </div>
            </div>
            ${
              activeAlert.canDismiss
                ? `<button class="alert-dismiss-btn" id="btn-dismiss-alert" title="Dismiss Alert">✕ Dismiss</button>`
                : ""
            }
          </div>
        `
        : "";

    const headerHtml =
      this._config.show_header !== false
        ? `
        <div class="header">
          <div class="title-group">
            <div class="title-row">
              <span class="robot-name">${escapeHtml(name)}</span>
              ${
                this._config.show_status_badge !== false
                  ? `<span class="status-badge" data-state="${stateEsc}">${stateEsc}</span>`
                  : ""
              }
            </div>
            <div class="subtitle">${escapeHtml(subtitleParts.join(" • "))}</div>
          </div>
          <div class="telemetry">
            ${
              activeAlert?.isBin && this._config.show_bin_alert !== false
                ? `<span class="pill active" style="background:rgba(245,158,11,0.22);color:#fbbf24;" title="${escapeHtml(activeAlert.message)}">Bin Full</span>`
                : ""
            }
            ${
              schedState && this._config.show_schedule !== false
                ? `<button class="pill clickable ${isScheduleOn ? "active" : ""}" id="btn-schedule" title="Toggle Robot Schedule">${isScheduleOn ? "Schedule On" : "Schedule Off"}</button>`
                : ""
            }
            ${
              batteryVal && this._config.show_battery !== false
                ? `<span class="pill" title="Battery">${escapeHtml(batteryVal)}${isCharging ? " (Charging)" : ""}</span>`
                : ""
            }
          </div>
        </div>
      `
        : "";

    root.innerHTML = `
      ${headerHtml}
      ${alertBannerHtml}

      <div class="map-wrapper">
        ${
          this._config.show_toolbar !== false
            ? `
            <div class="map-toolbar">
              <button class="tab-btn ${this._viewMode === "floor" ? "active" : ""}" id="tab-floor">Floor Plan</button>
              <button class="tab-btn ${this._viewMode === "run" ? "active" : ""}" id="tab-run">Last Run</button>
              <button class="tab-btn" id="btn-refresh-map" title="Refresh Maps">↻</button>
            </div>
            `
            : ""
        }
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
        this._config.show_controls !== false || this._config.show_modes !== false
          ? `
            <div class="controls-section">
              ${
                this._config.show_controls !== false
                  ? `
                  <div class="action-row">
                    <button class="btn primary" id="btn-start">${escapeHtml(startLabel)}</button>
                    <button class="btn" id="btn-pause" title="Pause">Pause</button>
                    <button class="btn" id="btn-stop" title="Stop">Stop</button>
                    <button class="btn" id="btn-dock" title="Return to Base">Dock</button>
                    <button class="btn" id="btn-locate" title="Locate Robot">Locate</button>
                  </div>
                  `
                  : ""
              }
              ${
                this._config.show_modes !== false
                  ? `
                  <div class="modes-row">
                    <div class="mode-group" title="Fan Speed">
                      ${fanSpeeds
                        .map(
                          (spd) =>
                            `<button class="mode-btn ${spd === currentFan ? "active" : ""}" data-fan="${escapeHtml(spd)}">${escapeHtml(spd)}</button>`
                        )
                        .join("")}
                    </div>
                    <div class="mode-group" title="Navigation Mode">
                      ${navModes
                        .map(
                          (nav) =>
                            `<button class="mode-btn ${nav === currentNav ? "active" : ""}" data-nav="${escapeHtml(nav)}">${escapeHtml(String(nav).replace(/_/g, " "))}</button>`
                        )
                        .join("")}
                    </div>
                  </div>
                  `
                  : ""
              }
            </div>
          `
          : ""
      }
    `;

    // Bind event listeners
    root.querySelector("#btn-dismiss-alert")?.addEventListener("click", () => {
      this._dismissAlert();
    });
    root.querySelector("#tab-floor")?.addEventListener("click", () => {
      this._viewMode = "floor";
      this._forceUpdate();
    });
    root.querySelector("#tab-run")?.addEventListener("click", () => {
      this._viewMode = "run";
      this._forceUpdate();
    });
    root.querySelector("#btn-refresh-map")?.addEventListener("click", () => {
      this._refreshMaps();
    });
    root.querySelector("#btn-schedule")?.addEventListener("click", () => {
      this._toggleSchedule();
    });

    for (const el of root.querySelectorAll("[data-zone]")) {
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const zName = el.getAttribute("data-zone");
        if (zName) this._toggleZone(zName);
      });
    }

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

    for (const el of root.querySelectorAll("[data-fan]")) {
      el.addEventListener("click", () => {
        const fan = el.getAttribute("data-fan");
        if (fan) this._callVacuum("set_fan_speed", { fan_speed: fan });
      });
    }

    for (const el of root.querySelectorAll("[data-nav]")) {
      el.addEventListener("click", () => {
        const nav = el.getAttribute("data-nav");
        if (nav) this._setNavMode(nav);
      });
    }
  }
}

class VacuulaMapCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._rendered = false;
    this._lastVacuumsKey = "";
  }

  setConfig(config) {
    this._config = { ...config };
    if (this._rendered && this.shadowRoot?.activeElement?.id === "title") {
      return;
    }
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const vacuumsKey = Object.keys(hass?.states || {})
      .filter((id) => id.startsWith("vacuum."))
      .sort()
      .join(",");
    if (!this._rendered || vacuumsKey !== this._lastVacuumsKey) {
      this._lastVacuumsKey = vacuumsKey;
      this._render();
    }
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
    this._rendered = true;
    const vacuums = Object.keys(this._hass.states).filter((id) => id.startsWith("vacuum."));

    const cfg = this._config;

    this.shadowRoot.innerHTML = `
      <style>
        .form {
          display: flex;
          flex-direction: column;
          gap: 12px;
          padding: 8px 0;
          font-family: inherit;
        }
        .section-header {
          font-size: 0.78rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--primary-color, #38bdf8);
          margin-top: 10px;
          padding-bottom: 4px;
          border-bottom: 1px solid var(--divider-color, rgba(148, 163, 184, 0.2));
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
          padding: 2px 0;
        }
        .row span {
          color: var(--primary-text-color, #f8fafc);
          font-size: 0.84rem;
        }
      </style>
      <div class="form">
        <div class="section-header">Core Settings</div>
        <label>
          Vacuum Entity
          <select id="entity">
            ${vacuums
              .map(
                (v) =>
                  `<option value="${escapeHtml(v)}" ${v === cfg.entity ? "selected" : ""}>${escapeHtml(v)}</option>`
              )
              .join("")}
          </select>
        </label>
        <label>
          Card Title (optional)
          <input type="text" id="title" value="${escapeHtml(cfg.title || "")}" placeholder="Auto (Robot Name)" />
        </label>
        <label>
          Default Map View
          <select id="default_view">
            <option value="floor" ${(cfg.default_view || "floor") === "floor" ? "selected" : ""}>Floor Plan & Zones</option>
            <option value="run" ${cfg.default_view === "run" ? "selected" : ""}>Last Cleaning Run</option>
          </select>
        </label>

        <div class="section-header">Display & Map Sizing</div>
        <label>
          Map Height / Sizing
          <select id="map_height">
            <option value="auto" ${(cfg.map_height || "auto") === "auto" ? "selected" : ""}>Auto (Responsive 380px–800px)</option>
            <option value="compact" ${cfg.map_height === "compact" ? "selected" : ""}>Compact (320px)</option>
            <option value="medium" ${cfg.map_height === "medium" ? "selected" : ""}>Medium (450px)</option>
            <option value="large" ${cfg.map_height === "large" ? "selected" : ""}>Large (620px)</option>
            <option value="xlarge" ${cfg.map_height === "xlarge" ? "selected" : ""}>Extra Large (800px)</option>
          </select>
        </label>
        <label class="row">
          <span>Expand on Large Screens</span>
          <input type="checkbox" id="expand_on_desktop" ${cfg.expand_on_desktop !== false ? "checked" : ""} />
        </label>
        <label class="row">
          <span>Show Room Pins on Map</span>
          <input type="checkbox" id="show_zone_labels" ${cfg.show_zone_labels !== false ? "checked" : ""} />
        </label>
        <label class="row">
          <span>Show Room Chips Bar</span>
          <input type="checkbox" id="show_zone_chips" ${cfg.show_zone_chips !== false ? "checked" : ""} />
        </label>
        <label class="row">
          <span>Show Map Toolbar Tabs</span>
          <input type="checkbox" id="show_toolbar" ${cfg.show_toolbar !== false ? "checked" : ""} />
        </label>

        <div class="section-header">Alerts & Notifications</div>
        <label class="row">
          <span>Show Alert & Warning Banners</span>
          <input type="checkbox" id="show_alerts" ${cfg.show_alerts !== false ? "checked" : ""} />
        </label>
        <label class="row">
          <span>Show Dust Bin Full Badge</span>
          <input type="checkbox" id="show_bin_alert" ${cfg.show_bin_alert !== false ? "checked" : ""} />
        </label>

        <div class="section-header">Header & Telemetry</div>
        <label class="row">
          <span>Show Card Header</span>
          <input type="checkbox" id="show_header" ${cfg.show_header !== false ? "checked" : ""} />
        </label>
        <label class="row">
          <span>Show Status Badge</span>
          <input type="checkbox" id="show_status_badge" ${cfg.show_status_badge !== false ? "checked" : ""} />
        </label>
        <label class="row">
          <span>Show Battery Status</span>
          <input type="checkbox" id="show_battery" ${cfg.show_battery !== false ? "checked" : ""} />
        </label>
        <label class="row">
          <span>Show Schedule Toggle</span>
          <input type="checkbox" id="show_schedule" ${cfg.show_schedule !== false ? "checked" : ""} />
        </label>

        <div class="section-header">Controls & Modes</div>
        <label class="row">
          <span>Show Vacuum Action Buttons</span>
          <input type="checkbox" id="show_controls" ${cfg.show_controls !== false ? "checked" : ""} />
        </label>
        <label class="row">
          <span>Show Fan Speed & Nav Modes</span>
          <input type="checkbox" id="show_modes" ${cfg.show_modes !== false ? "checked" : ""} />
        </label>
      </div>
    `;

    this.shadowRoot.querySelector("#entity")?.addEventListener("change", (e) => {
      const target = /** @type {HTMLSelectElement} */ (e.target);
      this._emit({ ...this._config, entity: target.value });
    });
    this.shadowRoot.querySelector("#title")?.addEventListener("input", (e) => {
      const target = /** @type {HTMLInputElement} */ (e.target);
      this._emit({ ...this._config, title: target.value });
    });
    this.shadowRoot.querySelector("#default_view")?.addEventListener("change", (e) => {
      const target = /** @type {HTMLSelectElement} */ (e.target);
      this._emit({ ...this._config, default_view: target.value });
    });
    this.shadowRoot.querySelector("#map_height")?.addEventListener("change", (e) => {
      const target = /** @type {HTMLSelectElement} */ (e.target);
      this._emit({ ...this._config, map_height: target.value });
    });
    this.shadowRoot.querySelector("#expand_on_desktop")?.addEventListener("change", (e) => {
      const target = /** @type {HTMLInputElement} */ (e.target);
      this._emit({ ...this._config, expand_on_desktop: target.checked });
    });
    this.shadowRoot.querySelector("#show_zone_labels")?.addEventListener("change", (e) => {
      const target = /** @type {HTMLInputElement} */ (e.target);
      this._emit({ ...this._config, show_zone_labels: target.checked });
    });
    this.shadowRoot.querySelector("#show_zone_chips")?.addEventListener("change", (e) => {
      const target = /** @type {HTMLInputElement} */ (e.target);
      this._emit({ ...this._config, show_zone_chips: target.checked });
    });
    this.shadowRoot.querySelector("#show_toolbar")?.addEventListener("change", (e) => {
      const target = /** @type {HTMLInputElement} */ (e.target);
      this._emit({ ...this._config, show_toolbar: target.checked });
    });
    this.shadowRoot.querySelector("#show_alerts")?.addEventListener("change", (e) => {
      const target = /** @type {HTMLInputElement} */ (e.target);
      this._emit({ ...this._config, show_alerts: target.checked });
    });
    this.shadowRoot.querySelector("#show_bin_alert")?.addEventListener("change", (e) => {
      const target = /** @type {HTMLInputElement} */ (e.target);
      this._emit({ ...this._config, show_bin_alert: target.checked });
    });
    this.shadowRoot.querySelector("#show_header")?.addEventListener("change", (e) => {
      const target = /** @type {HTMLInputElement} */ (e.target);
      this._emit({ ...this._config, show_header: target.checked });
    });
    this.shadowRoot.querySelector("#show_status_badge")?.addEventListener("change", (e) => {
      const target = /** @type {HTMLInputElement} */ (e.target);
      this._emit({ ...this._config, show_status_badge: target.checked });
    });
    this.shadowRoot.querySelector("#show_battery")?.addEventListener("change", (e) => {
      const target = /** @type {HTMLInputElement} */ (e.target);
      this._emit({ ...this._config, show_battery: target.checked });
    });
    this.shadowRoot.querySelector("#show_schedule")?.addEventListener("change", (e) => {
      const target = /** @type {HTMLInputElement} */ (e.target);
      this._emit({ ...this._config, show_schedule: target.checked });
    });
    this.shadowRoot.querySelector("#show_controls")?.addEventListener("change", (e) => {
      const target = /** @type {HTMLInputElement} */ (e.target);
      this._emit({ ...this._config, show_controls: target.checked });
    });
    this.shadowRoot.querySelector("#show_modes")?.addEventListener("change", (e) => {
      const target = /** @type {HTMLInputElement} */ (e.target);
      this._emit({ ...this._config, show_modes: target.checked });
    });
  }
}

if (!customElements.get("vacuula-map-card")) {
  customElements.define("vacuula-map-card", VacuulaMapCard);
}
if (!customElements.get("vacuula-map-card-editor")) {
  customElements.define("vacuula-map-card-editor", VacuulaMapCardEditor);
}

const customWindow = /** @type {any} */ (window);
customWindow.customCards = customWindow.customCards || [];
if (!customWindow.customCards.some((c) => c.type === "vacuula-map-card")) {
  customWindow.customCards.push({
    type: "vacuula-map-card",
    name: "Vacuula Map & Room Card",
    description:
      "Interactive floor map, clickable room zone selector, last run coverage, and controls for Vacuula Neato robots.",
    preview: true,
  });
}

export {
  VacuulaMapCard,
  VacuulaMapCardEditor,
  escapeHtml,
  sanitizeColor,
  sanitizeImgUrl,
  formatAlertCode,
  ALERT_INFO_MAP,
};
