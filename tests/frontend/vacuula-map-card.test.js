import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ALERT_INFO_MAP,
  VacuulaMapCard,
  VacuulaMapCardEditor,
  escapeHtml,
  formatAlertCode,
  formatSensorState,
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
    expect(sanitizeImgUrl("data:image/svg+xml;base64,PHN2Zz4=")).toBe("");
    expect(sanitizeImgUrl("data:image/png;base64,abc<script>")).toBe("");
    expect(sanitizeImgUrl("")).toBe("");
    expect(sanitizeImgUrl(null)).toBe("");

    // Safe PNG base64 data URI allowed
    expect(sanitizeImgUrl("data:image/png;base64,iVBORw0KGgo=")).toBe(
      "data:image/png;base64,iVBORw0KGgo="
    );
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

  it("formatSensorState uses hass.formatEntityState and falls back with unit and precision", () => {
    const mockFormatHass = {
      formatEntityState: vi.fn().mockReturnValue("1,829.46 ft²"),
    };
    const areaObj = {
      entity_id: "sensor.neato_d7_last_clean_area",
      state: "1829.461234",
      attributes: { unit_of_measurement: "ft²" },
    };
    expect(formatSensorState(mockFormatHass, areaObj, "m²", 2)).toBe("1,829.46 ft²");
    expect(mockFormatHass.formatEntityState).toHaveBeenCalledWith(areaObj);

    // Fallback when hass.formatEntityState is unavailable (e.g., dev sandbox / partial mock)
    const fallbackHass = { locale: { language: "en-US" } };
    expect(
      formatSensorState(
        fallbackHass,
        { state: "169.962145479847", attributes: { unit_of_measurement: "ft²" } },
        "m²",
        2
      )
    ).toBe("169.96 ft²");
    expect(
      formatSensorState(
        fallbackHass,
        { state: "1829.461234", attributes: { unit_of_measurement: "ft²" } },
        "m²",
        2
      )
    ).toBe("1,829.46 ft²");
    expect(
      formatSensorState(
        fallbackHass,
        { state: "169.96214", attributes: { unit_of_measurement: "m²" } },
        "m²",
        2
      )
    ).toBe("169.96 m²");
    expect(formatSensorState(fallbackHass, { state: "42.5" }, "m²", 2)).toBe("42.5 m²");
    expect(formatSensorState(fallbackHass, { state: "unknown" }, "m²", 2)).toBe("");
    expect(formatSensorState(fallbackHass, { state: "unavailable" }, "m²", 2)).toBe("");
    expect(formatSensorState(fallbackHass, null, "m²", 2)).toBe("");
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
    expect(card._config.show_run_basemap).toBe(true);
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
      show_run_basemap: false,
    });
    expect(card._config.default_view).toBe("run");
    expect(card._config.map_height).toBe("compact");
    expect(card._config.expand_on_desktop).toBe(false);
    expect(card._config.show_alerts).toBe(false);
    expect(card._config.show_bin_alert).toBe(false);
    expect(card._config.show_header).toBe(false);
    expect(card._config.show_battery).toBe(false);
    expect(card._config.show_controls).toBe(false);
    expect(card._config.show_run_basemap).toBe(false);
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
    expect(stub.show_run_basemap).toBe(true);
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

  it("handles missing or null vacuum entity gracefully", () => {
    card.setConfig({ entity: "vacuum.nonexistent" });
    card.hass = mockHass;
    const root = card.shadowRoot;
    expect(root?.querySelector(".empty-map")?.textContent).toContain(
      "Entity vacuum.nonexistent not found"
    );
  });

  it("handles entity with no floor map picture gracefully", () => {
    mockHass.states["image.neato_d7_floor_map"].attributes.entity_picture = "";
    card.hass = { ...mockHass };
    const root = card.shadowRoot;
    expect(root?.querySelector(".empty-map")?.textContent).toContain("No floor map available yet");
  });

  it("handles unknown alert codes gracefully without crashing", () => {
    mockHass.states["sensor.neato_d7_alert"].state = "ui_error_laser_sensor_dirty";
    mockHass.states["button.neato_d7_dismiss_alert"] = undefined;
    card.hass = { ...mockHass };
    const root = /** @type {ShadowRoot} */ (card.shadowRoot);
    const banner = el(root, ".alert-banner");
    expect(banner.textContent).toContain("Laser sensor dirty");
    expect(banner.textContent).toContain("Active condition: Laser sensor dirty.");
    expect(root.querySelector("#btn-dismiss-alert")).toBeNull();
  });

  it("handles alert from errors list in vacState", () => {
    mockHass.states["sensor.neato_d7_alert"].state = "none";
    mockHass.states["vacuum.neato_d7"].attributes.errors = [{ code: "cliff_sensor" }];
    card.hass = { ...mockHass };
    const root = /** @type {ShadowRoot} */ (card.shadowRoot);
    const banner = el(root, ".alert-banner");
    expect(banner.textContent).toContain("Drop Sensor Error");
    expect(banner.className).toContain("error");
  });

  it("escapes XSS payloads in custom title and room names", () => {
    card.setConfig({
      entity: "vacuum.neato_d7",
      title: "<script>alert('xss')</script>",
    });
    mockHass.states["image.neato_d7_floor_map"].attributes.zones = [
      {
        id: "z-mal",
        name: "<img src=x onerror=alert(1)>",
        color: "#38bdf8",
        x: 0.5,
        y: 0.5,
        points: [
          [0, 0],
          [1, 0],
          [1, 1],
        ],
      },
    ];
    card.hass = { ...mockHass };
    const root = /** @type {ShadowRoot} */ (card.shadowRoot);
    const title = el(root, ".robot-name");
    expect(title.textContent).toBe("<script>alert('xss')</script>");
    expect(title.querySelector("script")).toBeNull();

    const chip = el(root, ".zone-chip");
    expect(chip.querySelector("img")).toBeNull();
  });

  it("handles paused vacuum state with Resume start button", () => {
    mockHass.states["vacuum.neato_d7"].state = "paused";
    card.hass = { ...mockHass };
    const root = /** @type {ShadowRoot} */ (card.shadowRoot);
    const startBtn = el(root, "#btn-start");
    expect(startBtn.textContent).toContain("Resume");
    startBtn.click();
    expect(callServiceMock).toHaveBeenCalledWith("vacuum", "start", {
      entity_id: "vacuum.neato_d7",
    });
  });

  it("handles custom map_height with valid CSS units", () => {
    card.setConfig({ entity: "vacuum.neato_d7", map_height: "450px" });
    const customVars = card._getCustomHeightVars();
    expect(customVars).toContain("--vacuula-map-max-height: 450px;");
    expect(customVars).toContain("--vacuula-map-min-height: 450px;");
  });

  it("dispatches navigation mode, schedule toggle, and map refresh service calls", () => {
    const root = /** @type {ShadowRoot} */ (card.shadowRoot);

    // Schedule toggle button
    const schedBtn = el(root, "#btn-schedule");
    schedBtn.click();
    expect(callServiceMock).toHaveBeenCalledWith("switch", "toggle", {
      entity_id: "switch.neato_d7_schedule",
    });

    // Refresh maps button
    const refreshBtn = el(root, "#btn-refresh-map");
    refreshBtn.click();
    expect(callServiceMock).toHaveBeenCalledWith("vacuula", "refresh_maps", {
      entity_id: "vacuum.neato_d7",
    });
  });

  it("renders map select dropdown and triggers select_option when changed", () => {
    mockHass.states["select.neato_d7_selected_map"] = {
      state: "old",
      attributes: {
        options: ["old", "Ground Floor"],
      },
    };
    mockHass.callService = callServiceMock;
    card.setConfig({ entity: "vacuum.neato_d7" });
    card.hass = mockHass;
    document.body.appendChild(card);

    const root = card.shadowRoot;
    expect(root).not.toBeNull();

    const mapSelect = /** @type {HTMLSelectElement} */ (root.querySelector("#sel-active-map"));
    expect(mapSelect).not.toBeNull();
    expect(mapSelect.value).toBe("old");
    expect(mapSelect.options.length).toBe(2);

    mapSelect.value = "Ground Floor";
    mapSelect.dispatchEvent(new Event("change"));

    expect(callServiceMock).toHaveBeenCalledWith("select", "select_option", {
      entity_id: "select.neato_d7_selected_map",
      option: "Ground Floor",
    });
  });

  it("hides floor zone polygons and pins in run view while preserving zone chips", () => {
    const root = /** @type {ShadowRoot} */ (card.shadowRoot);
    expect(root.querySelector(".zone-svg")).not.toBeNull();
    expect(root.querySelector(".zone-pins")).not.toBeNull();
    expect(root.querySelectorAll(".zone-chip").length).toBe(2);

    el(root, "#tab-run").click();
    expect(root.querySelector(".zone-svg")).toBeNull();
    expect(root.querySelector(".zone-pins")).toBeNull();
    expect(root.querySelectorAll(".zone-chip").length).toBe(2);
  });

  it("uses run entity_picture by default without calling callWS when show_run_basemap is true", () => {
    const callWSMock = vi.fn();
    mockHass.callWS = callWSMock;
    card.hass = { ...mockHass };

    const root = /** @type {ShadowRoot} */ (card.shadowRoot);
    el(root, "#tab-run").click();

    expect(callWSMock).not.toHaveBeenCalled();
    const img = el(root, "img.map-img");
    expect(img.getAttribute("src")).toBe("/api/image_proxy/image.neato_d7_last_run_map");
  });

  it("fetches path-only run image via WebSocket when show_run_basemap is false", async () => {
    const callWSMock = vi.fn().mockResolvedValue({ image_base64: "iVBORw0KGgo=" });
    mockHass.callWS = callWSMock;
    mockHass.states["image.neato_d7_last_run_map"].attributes.serial = "OPS123";
    mockHass.states["image.neato_d7_last_run_map"].attributes.run_id = "run-42";

    card.setConfig({ entity: "vacuum.neato_d7", show_run_basemap: false });
    card.hass = { ...mockHass };

    const root = /** @type {ShadowRoot} */ (card.shadowRoot);
    el(root, "#tab-run").click();

    expect(callWSMock).toHaveBeenCalledTimes(1);
    expect(callWSMock).toHaveBeenCalledWith({
      type: "vacuula/get_run_map_image",
      entity_id: "image.neato_d7_last_run_map",
      include_basemap: false,
      serial: "OPS123",
    });

    await Promise.resolve();
    await Promise.resolve();

    const img = el(root, "img.map-img");
    expect(img.getAttribute("src")).toBe("data:image/png;base64,iVBORw0KGgo=");

    // Toggling floor -> run uses cached data URL for the same run without re-fetching
    el(root, "#tab-floor").click();
    el(root, "#tab-run").click();
    expect(callWSMock).toHaveBeenCalledTimes(1);

    // Rejection on a newer run renders empty-map fallback text
    callWSMock.mockRejectedValueOnce(new Error("not_found"));
    mockHass.states["image.neato_d7_last_run_map"] = {
      state: "2026-10-25T13:00:00Z",
      attributes: {
        entity_picture: "/api/image_proxy/image.neato_d7_last_run_map?v=2",
        serial: "OPS123",
        run_id: "run-43",
      },
    };
    card.hass = { ...mockHass };

    await Promise.resolve();
    await Promise.resolve();

    expect(callWSMock).toHaveBeenCalledTimes(2);
    expect(root.querySelector(".empty-map")?.textContent).toContain(
      "No last run path available yet"
    );
  });

  it("formats last clean area and duration via formatEntityState or fallback unit_of_measurement", () => {
    const root = /** @type {ShadowRoot} */ (card.shadowRoot);
    mockHass.locale = { language: "en-US" };
    mockHass.states["sensor.neato_d7_last_clean_area"] = {
      entity_id: "sensor.neato_d7_last_clean_area",
      state: "169.962145479847",
      attributes: { unit_of_measurement: "ft²" },
    };
    mockHass.states["sensor.neato_d7_last_clean_duration"] = {
      entity_id: "sensor.neato_d7_last_clean_duration",
      state: "67.5",
      attributes: { unit_of_measurement: "min" },
    };
    card.hass = { ...mockHass };

    let subtitle = el(root, ".subtitle").textContent || "";
    expect(subtitle).toContain("Last: 169.96 ft² · 67.5 min");
    expect(subtitle).not.toContain("169.962145479847");
    expect(subtitle).not.toContain("m²");

    // Re-renders when unit_of_measurement changes even if numeric state is unchanged
    mockHass.states["sensor.neato_d7_last_clean_area"] = {
      entity_id: "sensor.neato_d7_last_clean_area",
      state: "169.962145479847",
      attributes: { unit_of_measurement: "m²" },
    };
    card.hass = { ...mockHass };
    subtitle = el(root, ".subtitle").textContent || "";
    expect(subtitle).toContain("Last: 169.96 m² · 67.5 min");

    // Delegates to hass.formatEntityState when provided by Home Assistant
    mockHass.formatEntityState = vi.fn((stateObj) => {
      if (stateObj.entity_id === "sensor.neato_d7_last_clean_area") {
        return "1,829.46 ft²";
      }
      return `${stateObj.state} min`;
    });
    mockHass.states["sensor.neato_d7_last_clean_area"] = {
      entity_id: "sensor.neato_d7_last_clean_area",
      state: "1829.461234",
      attributes: { unit_of_measurement: "ft²" },
    };
    card.hass = { ...mockHass };
    subtitle = el(root, ".subtitle").textContent || "";
    expect(subtitle).toContain("Last: 1,829.46 ft² · 67.5 min");
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

    const basemapCheckbox = /** @type {HTMLInputElement} */ (
      root.querySelector("#show_run_basemap")
    );
    expect(basemapCheckbox.checked).toBe(true);
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

    const basemapCheckbox = /** @type {HTMLInputElement} */ (
      root.querySelector("#show_run_basemap")
    );
    basemapCheckbox.checked = false;
    basemapCheckbox.dispatchEvent(new Event("change"));
    expect(emittedConfig?.show_run_basemap).toBe(false);

    const titleInput = /** @type {HTMLInputElement} */ (root.querySelector("#title"));
    titleInput.value = "New Title";
    titleInput.dispatchEvent(new Event("input"));
    expect(emittedConfig?.title).toBe("New Title");
  });
});
