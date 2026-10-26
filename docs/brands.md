# Brand Assets & Theme Integration

This document outlines how brand assets for the Neato Botvac custom integration are structured, loaded, and resolved across Home Assistant Core, HACS (Home Assistant Community Store), and the Home Assistant Brands CDN.

> [!NOTE]
> All brand icons and logos in this repository are **original artwork designed in the Home Assistant Material Design (MDI) style**. They depict a classic Neato D-shape robot vacuum with Home Assistant blue/cyan status lighting and do not use any artwork, trademarks, or assets from the upstream Vacuula server project.

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

## 2. Brand Asset Specification

The repository bundles all 8 standard brand image files conforming to Home Assistant specifications:

| Filename | Dimensions | Theme Target | Description |
|:---|:---:|:---:|:---|
| `icon.png` | 256 × 256 | Light theme | Clean MDI-style D-shape robot vacuum avatar on transparent background (dark charcoal body with HA blue accent). |
| `icon@2x.png` | 512 × 512 | Light theme | HiDPI / retina version of `icon.png`. |
| `dark_icon.png` | 256 × 256 | Dark theme | High-contrast silver/white avatar on transparent background with cyan status light. |
| `dark_icon@2x.png` | 512 × 512 | Dark theme | HiDPI / retina version of `dark_icon.png`. |
| `logo.png` | 512 × 512 | Light theme | Brand logo for integration card and device headers. |
| `logo@2x.png` | 512 × 512 | Light theme | HiDPI version of `logo.png`. |
| `dark_logo.png` | 512 × 512 | Dark theme | Dark-theme optimized brand logo. |
| `dark_logo@2x.png` | 512 × 512 | Dark theme | HiDPI version of `dark_logo.png`. |

These assets are mirrored in:
- `custom_components/vacuula/brand/` (canonical Home Assistant path)
- `brand/` (repository root for compatibility with repository validators)

---

## 3. Maintenance & Regeneration Tooling

If the master artwork is updated, run the automated brand generation script to regenerate all 8 compliant PNGs:

```bash
python3 -m devtools.generate_brands
```

Automated test verification:
```bash
pytest tests/test_brand.py
```
