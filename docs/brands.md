# Brand Assets & Theme Integration

This document outlines how Vacuula brand assets are structured, loaded, and resolved across Home Assistant Core, HACS (Home Assistant Community Store), and the Home Assistant Brands CDN.

---

## 1. Overview & Architecture

Home Assistant supports custom integration branding through two primary channels:

1. **Local Bundled Assets (Home Assistant 2026.3+):**
   Custom integrations ship their own brand images inside `custom_components/vacuula/brand/`. When the integration is installed, Home Assistant serves these directly via its local authenticated Brands Proxy API:
   ```text
   /api/brands/integration/vacuula/icon.png
   /api/brands/integration/vacuula/dark_icon.png
   ```

2. **Marketplace & Community Store Sync (HACS / Home Assistant Marketplace):**
   Before an integration is installed, the UI displays repository icons from the Home Assistant Brands service:
   - Modern Marketplace endpoint: `https://brands.home-assistant.io/marketplace/vacuula/[icon.png|dark_icon.png]`
   - Legacy HACS proxy endpoint: `https://brands.home-assistant.io/_/vacuula/[icon.png|dark_icon.png]`

---

## 2. Why `brands.home-assistant.io/_/vacuula/dark_icon.png` Returned a Missing Image

The URL path `/_/` is Home Assistant Brands CDN's **placeholder fallback route**. When an integration:
- Does not have brand assets submitted to the central [home-assistant/brands](https://github.com/home-assistant/brands) repository, or
- Missing a dedicated `dark_icon.png` in its GitHub releases,

the CDN serves a generic fallback placeholder ("Image not found").

Furthermore:
- In releases prior to v0.6.0, `dark_icon.png`, `dark_icon@2x.png`, `dark_logo.png`, and `dark_logo@2x.png` were not present in the repository.
- `icon.png` was sized at 192×192 px instead of standard 256×256 px.
- Artwork was dark charcoal `#222222` with no light-colored variant for dark mode.

---

## 3. Brand Asset Specification

The repository bundles all 8 standard brand image files conforming to Home Assistant specifications:

| Filename | Dimensions | Theme Target | Description |
|:---|:---:|:---:|:---|
| `icon.png` | 256 × 256 | Light theme | Square robot vacuum avatar on transparent background (dark charcoal body). |
| `icon@2x.png` | 512 × 512 | Light theme | HiDPI / retina version of `icon.png`. |
| `dark_icon.png` | 256 × 256 | Dark theme | High-contrast silver/white avatar on transparent background with vivid status light. |
| `dark_icon@2x.png` | 512 × 512 | Dark theme | HiDPI / retina version of `dark_icon.png`. |
| `logo.png` | 512 × 512 | Light theme | Brand logo for integration card and device headers. |
| `logo@2x.png` | 512 × 512 | Light theme | HiDPI version of `logo.png`. |
| `dark_logo.png` | 512 × 512 | Dark theme | Dark-theme optimized brand logo. |
| `dark_logo@2x.png` | 512 × 512 | Dark theme | HiDPI version of `dark_logo.png`. |

These assets are mirrored in:
- `custom_components/vacuula/brand/` (canonical Home Assistant path)
- `brand/` (repository root for compatibility with repository validators)

---

## 4. Maintenance & Regeneration Tooling

If the master artwork is updated, run the automated brand generation script to regenerate all 8 compliant PNGs:

```bash
python3 scripts/generate_brands.py
```

Automated test verification:
```bash
pytest tests/test_brand.py
```

---

## 5. (Optional) Upstream CDN Submission to `home-assistant/brands`

While modern Home Assistant and HACS Marketplace dynamically fetch local assets from GitHub releases, you can also register the brand in the centralized Home Assistant Brands repository so that legacy CDN queries (`https://brands.home-assistant.io/_/vacuula/...`) resolve permanently:

1. Fork [home-assistant/brands](https://github.com/home-assistant/brands) on GitHub.
2. Create a folder `custom_integrations/vacuula/`.
3. Copy the 8 PNG files from `custom_components/vacuula/brand/` into `custom_integrations/vacuula/`.
4. Submit a Pull Request titled `Add brand assets for Vacuula custom integration`.
