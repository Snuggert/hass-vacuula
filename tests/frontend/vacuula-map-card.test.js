import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ALERT_INFO_MAP,
  VacuulaMapCard,
  VacuulaMapCardEditor,
  escapeHtml,
  formatAlertCode,
  sanitizeColor,
  sanitizeImgUrl,
} from "../../custom_components/vacuula/frontend/vacuula-map-card.js";

/**
 * @param {ParentNode} root
 * @param {string} selector
 * @returns {HTMLElement}
 */
function el(root, selector) {
  const element = root.querySelector(selector);
  if (!element) throw new Error(`Element ${selector} not found`);
  return /** @type {HTMLElement} */ (element);
}

describe("Vacuula Frontend Helper Functions", () => {
  it("escapeHtml escapes HTML entities and handles falsy values", () => {
    expect(escapeHtml('<script>alert("xss")</script>')).toBe(
      "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;"
    );
    expect(escapeHtml("Tom & 'Jerry'")).toBe("Tom &amp; &#39;Jerry&#39;");
    expect(escapeHtml("")).toBe("");
    expect(escapeHtml(null)).toBe("");
    expect(escapeHtml(undefined)).toBe("");
    expect(escapeHtml(123)).toBe("123");
  });

  it("sanitizeColor validates hex and named colors, falling back to default cyan", () => {
    expect(sanitizeColor("#38bdf8")).toBe("#38bdf8");
    expect(sanitizeColor("#fff")).toBe("#fff");
    expect(sanitizeColor("#12345678")).toBe("#12345678");
    expect(sanitizeColor("red")).toBe("red");
    expect(sanitizeColor("royalblue")).toBe("royalblue");

    // Invalid values fallback to #38bdf8
    expect(sanitizeColor("javascript:alert(1)")).toBe("#38bdf8");
    expect(sanitizeColor("#zzzzzz")).toBe("#38bdf8");
    expect(sanitizeColor("")).toBe("#38bdf8");
    expect(sanitizeColor(null)).toBe("#38bdf8");
  });

  it("sanitizeImgUrl allows relative paths and http/https, rejecting malicious schemes", () => {
    expect(sanitizeImgUrl("/api/image/serve/img123")).toBe("/api/image/serve/img123");
    expect(sanitizeImgUrl("https://example.com/map.png")).toBe("https://example.com/map.png");
    expect(sanitizeImgUrl("http://vacuula.local:8085/floor.png")).toBe(
      "http://vacuula.local:8085/floor.png"
    );

    // Malicious protocols rejected
    expect(sanitizeImgUrl("javascript:alert(1)")).toBe("");
    expect(sanitizeImgUrl("data:text/html;base64,...")).toBe("");
    expect(sanitizeImgUrl("")).toBe("");
    expect(sanitizeImgUrl(null)).toBe("");
  });

  it("formatAlertCode transforms snake_case and removes prefix", () => {
    expect(formatAlertCode("ui_alert_dust_bin_full")).toBe("Dust bin full");
    expect(formatAlertCode("ui_error_navigation_stuck")).toBe("Navigation stuck");
    expect(formatAlertCode("brush_stuck")).toBe("Brush stuck");
    expect(formatAlertCode("")).toBe("Unknown Alert");
    expect(formatAlertCode(null)).toBe("Unknown Alert");
  });

  it("ALERT_INFO_MAP has correct definitions for Neato alerts and dust bin flags", () => {
    expect(ALERT_INFO_MAP.dustbin_full.isBin).toBe(true);
    expect(ALERT_INFO_MAP.dustbin_full.severity).toBe("warning");
    expect(ALERT_INFO_MAP.dustbin_missing.isBin).toBe(true);
    expect(ALERT_INFO_MAP.lid_open.isBin).toBe(true);

    expect(ALERT_INFO_MAP.brush_stuck.isBin).toBe(false);
    expect(ALERT_INFO_MAP.brush_stuck.severity).toBe("error");
    expect(ALERT_INFO_MAP.navigation_stuck.severity).toBe("error");
    expect(ALERT_INFO_MAP.battery_low.severity).toBe("info");
  });
});

describe("VacuulaMapCard Custom Element Lifecycle & Config", () => {
  /** @type {VacuulaMapCard} */
  let card;

  beforeEach(() => {
    card = /** @type {VacuulaMapCard} */ (document.createElement("vacuula-map-card"));
  });

  it("is registered as custom element", () => {
    expect(customElements.get("vacuula-map-card")).toBeDefined();
    expect(card).toBeInstanceOf(VacuulaMapCard);
  });

  it("throws error in setConfig when entity is missing", () => {
    expect(() => card.setConfig({})).toThrow(/specify a Vacuula vacuum entity/);
    expect(() => card.setConfig(null)).toThrow(/specify a Vacuula vacuum entity/);
  });

  it("populates default configuration flags on setConfig", () => {
    card.setConfig({ entity: "vacuum.neato_d7" });
    expect(card._config.entity).toBe("vacuum.neato_d7");
    expect(card._config.default_view).toBe("floor");
    expect(card._config.map_height).toBe("auto");
    expect(card._config.expand_on_desktop).toBe(true);
    expect(card._config.show_alerts).toBe(true);
    expect(card._config.show_bin_alert).toBe(true);
    expect(card._config.show_header).toBe(true);
    expect(card._config.show_status_badge).toBe(true);
    expect(card._config.show_battery).toBe(true);
    expect(card._config.show_schedule).toBe(true);
    expect(card._config.show_toolbar).toBe(true);
    expect(card._config.show_zone_labels).toBe(true);
    expect(card._config.show_zone_chips).toBe(true);
    expect(card._config.show_controls).toBe(true);
    expect(card._config.show_modes).toBe(true);
  });

  it("respects custom config options", () => {
    card.setConfig({
      entity: "vacuum.neato_d7",
      default_view: "run",
      map_height: "compact",
      expand_on_desktop: false,
      show_alerts: false,
      show_bin_alert: false,
      show_header: false,
      show_battery: false,
      show_controls: false,
    });
    expect(card._config.default_view).toBe("run");
    expect(card._config.map_height).toBe("compact");
    expect(card._config.expand_on_desktop).toBe(false);
    expect(card._config.show_alerts).toBe(false);
    expect(card._config.show_bin_alert).toBe(false);
    expect(card._config.show_header).toBe(false);
    expect(card._config.show_battery).toBe(false);
    expect(card._config.show_controls).toBe(false);
  });

  it("getCardSize calculates size based on map_height", () => {
    card.setConfig({ entity: "vacuum.neato_d7", map_height: "compact" });
    expect(card.getCardSize()).toBe(4);

    card.setConfig({ entity: "vacuum.neato_d7", map_height: "large" });
    expect(card.getCardSize()).toBe(9);

    card.setConfig({ entity: "vacuum.neato_d7", map_height: "xlarge" });
    expect(card.getCardSize()).toBe(9);

    card.setConfig({ entity: "vacuum.neato_d7", map_height: "auto" });
    expect(card.getCardSize()).toBe(6);
  });

  it("getGridOptions returns valid sections dashboard grid parameters", () => {
    const opts = card.getGridOptions();
    expect(opts.columns).toBe(12);
    expect(opts.rows).toBe("auto");
    expect(opts.min_columns).toBe(6);
    expect(opts.min_rows).toBe(4);
  });

  it("getStubConfig auto-detects vacuum entity with active map", () => {
    const mockHass = {
      states: {
        "vacuum.living_room": {
          attributes: { active_map_id: "map-123" },
        },
      },
    };
    const stub = VacuulaMapCard.getStubConfig(mockHass);
    expect(stub.entity).toBe("vacuum.living_room");
    expect(stub.expand_on_desktop).toBe(true);
    expect(stub.show_alerts).toBe(true);
    expect(stub.show_bin_alert).toBe(true);
  });

  it("getConfigElement returns vacuula-map-card-editor element", () => {
    const editor = VacuulaMapCard.getConfigElement();
    expect(editor.tagName.toLowerCase()).toBe("vacuula-map-card-editor");
  });
});

describe("VacuulaMapCard DOM Rendering and Interaction", () => {
  /** @type {VacuulaMapCard} */
  let card;
  let mockHass;
  let callServiceMock;

  beforeEach(() => {
    callServiceMock = vi.fn().mockResolvedValue({ result: "ok" });
    mockHass = {
      states: {
        "vacuum.neato_d7": {
          state: "docked",
          attributes: {
            friendly_name: "Neato D7 Connected",
            status: "Charging (85%)",
            battery_level: 85,
            navigation_mode: "normal",
            available_zones: ["Kitchen", "Living Room"],
            active_map_id: "map-1",
            active_map_name: "Ground Floor",
          },
        },
        "image.neato_d7_floor_map": {
          state: "2026-10-25T12:00:00Z",
          attributes: {
            entity_picture: "/api/image_proxy/image.neato_d7_floor_map",
            zones: [
              {
                id: "z-kitchen",
                name: "Kitchen",
                color: "#38bdf8",
                x: 0.25,
                y: 0.3,
                points: [
                  [0.1, 0.1],
                  [0.4, 0.1],
                  [0.4, 0.5],
                  [0.1, 0.5],
                ],
              },
              {
                id: "z-living",
                name: "Living Room",
                color: "#10b981",
                x: 0.6,
                y: 0.7,
                points: [
                  [0.5, 0.5],
                  [0.9, 0.5],
                  [0.9, 0.9],
                  [0.5, 0.9],
                ],
              },
            ],
          },
        },
        "image.neato_d7_last_run_map": {
          state: "2026-10-25T12:00:00Z",
          attributes: {
            entity_picture: "/api/image_proxy/image.neato_d7_last_run_map",
          },
        },
        "sensor.neato_d7_alert": {
          state: "none",
        },
        "sensor.neato_d7_battery": {
          state: "85",
        },
        "button.neato_d7_dismiss_alert": {
          state: "2026-10-25T10:00:00Z",
        },
        "switch.neato_d7_schedule": {
          state: "on",
        },
      },
      callService: callServiceMock,
    };

    card = /** @type {VacuulaMapCard} */ (document.createElement("vacuula-map-card"));
    document.body.appendChild(card);
    card.setConfig({ entity: "vacuum.neato_d7" });
    card.hass = mockHass;
  });

  it("renders card title and status badge in shadowRoot", () => {
    const root = card.shadowRoot;
    expect(root).not.toBeNull();
    const title = root.querySelector(".robot-name");
    expect(title.textContent).toBe("Neato D7 Connected");

    const badge = root.querySelector(".status-badge");
    expect(badge.textContent).toContain("docked");
  });

  it("renders floor map image and zone chips", () => {
    const root = card.shadowRoot;
    const img = root.querySelector("img.map-img");
    expect(img).not.toBeNull();
    expect(img.getAttribute("src")).toBe("/api/image_proxy/image.neato_d7_floor_map");

    const chips = root.querySelectorAll(".zone-chip");
    expect(chips.length).toBe(2);
    expect(chips[0].textContent).toContain("Kitchen");
    expect(chips[1].textContent).toContain("Living Room");
  });

  it("clicking a zone chip toggles zone selection and shows clear button", () => {
    const root = /** @type {ShadowRoot} */ (card.shadowRoot);
    const kitchenChip = el(root, '.zone-chip[data-zone="Kitchen"]');
    kitchenChip.click();

    expect(card._selectedZones.has("Kitchen")).toBe(true);

    // Clicking again deselects
    kitchenChip.click();
    expect(card._selectedZones.has("Kitchen")).toBe(false);
  });

  it("toggling between floor and run view updates view mode", () => {
    const root = /** @type {ShadowRoot} */ (card.shadowRoot);
    const runBtn = el(root, "#tab-run");
    runBtn.click();
    expect(card._viewMode).toBe("run");

    const floorBtn = el(root, "#tab-floor");
    floorBtn.click();
    expect(card._viewMode).toBe("floor");
  });

  it("clicking start button with selected zone dispatches clean_zones action", async () => {
    card._selectedZones.add("Kitchen");
    const root = /** @type {ShadowRoot} */ (card.shadowRoot);
    const startBtn = el(root, "#btn-start");
    startBtn.click();

    expect(callServiceMock).toHaveBeenCalledWith("vacuula", "clean_zones", {
      entity_id: "vacuum.neato_d7",
      zones: ["Kitchen"],
    });
  });

  it("clicking control buttons dispatches appropriate vacuum services", () => {
    const root = /** @type {ShadowRoot} */ (card.shadowRoot);

    el(root, "#btn-pause").click();
    expect(callServiceMock).toHaveBeenCalledWith("vacuum", "pause", {
      entity_id: "vacuum.neato_d7",
    });

    el(root, "#btn-stop").click();
    expect(callServiceMock).toHaveBeenCalledWith("vacuum", "stop", {
      entity_id: "vacuum.neato_d7",
    });

    el(root, "#btn-dock").click();
    expect(callServiceMock).toHaveBeenCalledWith("vacuum", "return_to_base", {
      entity_id: "vacuum.neato_d7",
    });

    el(root, "#btn-locate").click();
    expect(callServiceMock).toHaveBeenCalledWith("vacuum", "locate", {
      entity_id: "vacuum.neato_d7",
    });
  });

  it("renders alert banner and bin full badge when alert is active", () => {
    mockHass.states["sensor.neato_d7_alert"].state = "dustbin_full";
    card.hass = { ...mockHass };

    const root = /** @type {ShadowRoot} */ (card.shadowRoot);
    const banner = el(root, ".alert-banner");
    expect(banner).not.toBeNull();
    expect(banner.textContent).toContain("Dust Bin Full");

    // Dismiss alert button
    const dismissBtn = el(root, "#btn-dismiss-alert");
    expect(dismissBtn).not.toBeNull();
    dismissBtn.click();
    expect(callServiceMock).toHaveBeenCalledWith("button", "press", {
      entity_id: "button.neato_d7_dismiss_alert",
    });
  });

  it("suppresses alert banner when show_alerts is false", () => {
    card.setConfig({ entity: "vacuum.neato_d7", show_alerts: false });
    mockHass.states["sensor.neato_d7_alert"].state = "dustbin_full";
    card.hass = { ...mockHass };

    const root = card.shadowRoot;
    expect(root.querySelector(".alert-banner")).toBeNull();
  });
});

describe("VacuulaMapCardEditor Custom Element", () => {
  /** @type {VacuulaMapCardEditor} */
  let editor;
  let mockHass;

  beforeEach(() => {
    mockHass = {
      states: {
        "vacuum.neato_d7": {
          attributes: { friendly_name: "Neato D7" },
        },
        "vacuum.neato_d10": {
          attributes: { friendly_name: "Neato D10" },
        },
      },
    };
    editor = /** @type {VacuulaMapCardEditor} */ (
      document.createElement("vacuula-map-card-editor")
    );
    document.body.appendChild(editor);
    editor.hass = mockHass;
    editor.setConfig({
      entity: "vacuum.neato_d7",
      title: "Custom Title",
      default_view: "floor",
      map_height: "auto",
      expand_on_desktop: true,
      show_alerts: true,
      show_bin_alert: true,
    });
  });

  it("is registered as custom element", () => {
    expect(customElements.get("vacuula-map-card-editor")).toBeDefined();
    expect(editor).toBeInstanceOf(VacuulaMapCardEditor);
  });

  it("renders editor form fields populated with current config", () => {
    const root = editor.shadowRoot;
    expect(root).not.toBeNull();

    const entitySelect = /** @type {HTMLSelectElement} */ (root.querySelector("#entity"));
    expect(entitySelect.value).toBe("vacuum.neato_d7");
    expect(entitySelect.children.length).toBe(2);

    const titleInput = /** @type {HTMLInputElement} */ (root.querySelector("#title"));
    expect(titleInput.value).toBe("Custom Title");

    const expandCheckbox = /** @type {HTMLInputElement} */ (
      root.querySelector("#expand_on_desktop")
    );
    expect(expandCheckbox.checked).toBe(true);
  });

  it("dispatches config-changed event when inputs are modified", () => {
    const root = editor.shadowRoot;
    /** @type {any} */
    let emittedConfig = null;

    editor.addEventListener("config-changed", (ev) => {
      const customEv = /** @type {CustomEvent} */ (ev);
      emittedConfig = customEv.detail.config;
    });

    const expandCheckbox = /** @type {HTMLInputElement} */ (
      root.querySelector("#expand_on_desktop")
    );
    expandCheckbox.checked = false;
    expandCheckbox.dispatchEvent(new Event("change"));

    expect(emittedConfig).not.toBeNull();
    expect(emittedConfig?.expand_on_desktop).toBe(false);

    const titleInput = /** @type {HTMLInputElement} */ (root.querySelector("#title"));
    titleInput.value = "New Title";
    titleInput.dispatchEvent(new Event("input"));
    expect(emittedConfig?.title).toBe("New Title");
  });
});
