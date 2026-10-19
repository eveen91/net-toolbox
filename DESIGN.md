---
name: "net::toolbox"
description: "A precise, full-width network operations workspace"
colors:
  dark-bg: "#11161d"
  dark-panel: "#181f28"
  dark-panel-muted: "#161d25"
  dark-bg-elevated: "#202a35"
  dark-bg-hover: "#202a35"
  dark-border: "#344252"
  dark-border-soft: "#293440"
  dark-text: "#e8edf3"
  dark-muted: "#a5b2c2"
  dark-accent: "#72d6c3"
  dark-accent-dim: "#3c8175"
  dark-accent-2: "#93c5e5"
  dark-warn: "#f1c277"
  dark-warn-dim: "#6b5030"
  dark-danger: "#ffadb4"
  dark-success: "#89dcac"
  dark-input-bg: "#11161d"
  dark-selected: "#203d3a"
  dark-primary-text: "#10231f"
  dark-success-bg: "#173527"
  dark-warning-bg: "#332b1d"
  dark-danger-bg: "#382027"
  dark-focus: "#8de6d5"
  light-bg: "#f3f5f7"
  light-panel: "#ffffff"
  light-panel-muted: "#eaf0f3"
  light-bg-elevated: "#eaf0f3"
  light-bg-hover: "#eaf0f3"
  light-border: "#ccd5df"
  light-border-soft: "#dce3e9"
  light-text: "#17212d"
  light-muted: "#536273"
  light-accent: "#087565"
  light-accent-dim: "#087565"
  light-accent-2: "#215e87"
  light-warn: "#835000"
  light-warn-dim: "#bc9b5d"
  light-danger: "#ad2334"
  light-success: "#17663a"
  light-input-bg: "#ffffff"
  light-selected: "#dcf2ec"
  light-primary-text: "#ffffff"
  light-success-bg: "#e2f3e9"
  light-warning-bg: "#fcf0d9"
  light-danger-bg: "#fce6e9"
  light-focus: "#087565"
typography:
  title:
    fontFamily: '"Inter", system-ui, sans-serif'
    fontSize: "24px"
    fontWeight: 600
    lineHeight: "32px"
  body:
    fontFamily: '"Inter", system-ui, sans-serif'
    fontSize: "14px"
    lineHeight: 1.45
  label:
    fontFamily: '"Inter", system-ui, sans-serif'
    fontSize: "12px"
  data:
    fontFamily: '"IBM Plex Mono", ui-monospace, monospace'
    fontSize: "13px"
  brand:
    fontFamily: '"IBM Plex Mono", ui-monospace, monospace'
    fontSize: "18px"
    fontWeight: 700
rounded:
  control: "6px"
  panel: "8px"
  card: "10px"
  pill: "999px"
spacing:
  compact: "4px"
  control: "8px"
  field: "12px"
  mobile-panel: "16px"
  panel: "20px"
  workspace: "24px"
  section: "32px"
components:
  button-primary:
    backgroundColor: "{colors.dark-accent}"
    textColor: "{colors.dark-primary-text}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
    height: "36px"
  button-primary-light:
    backgroundColor: "{colors.light-accent}"
    textColor: "{colors.light-primary-text}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.dark-muted}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  input:
    backgroundColor: "{colors.dark-input-bg}"
    textColor: "{colors.dark-text}"
    rounded: "{rounded.control}"
    padding: "9px 10px"
  navigation-active:
    backgroundColor: "{colors.dark-selected}"
    textColor: "{colors.dark-accent}"
    padding: "8px 10px"
  panel:
    backgroundColor: "{colors.dark-panel}"
    textColor: "{colors.dark-text}"
    rounded: "{rounded.panel}"
    padding: "20px"
  inspector:
    backgroundColor: "{colors.dark-panel-muted}"
    rounded: "{rounded.panel}"
    padding: "20px"
    width: "334px"
  status-success:
    backgroundColor: "{colors.dark-success-bg}"
    textColor: "{colors.dark-success}"
    rounded: "{rounded.pill}"
---

# Design System: net::toolbox

## Overview

**Creative North Star: "Network Operations Workspace"**

The approved top-navigation direction makes room for network data. The interface is compact, calm, and operational: slate surfaces, a restrained teal accent, readable tables, and object inspectors. The design is extracted from the implemented application, rather than treating static mockups as completed functionality.

The global shell selects modules and tenant context; local views, filters, and record operations remain in the workspace. Device visuals describe saved documentation and explicitly avoid implying live monitoring.

**Key Characteristics:**
- Full-width data workspace with grouped top navigation.
- Dark and light semantic palettes.
- Unscaled record editing beside a scalable device overview.

## Colors

### Primary

Teal identifies primary actions, active navigation, selected ports, and actionable subnet links. Dark and light themes use separate contrast relationships; use the theme variables rather than copying dark colors into light surfaces.

### Secondary

Cool blue provides secondary technical emphasis. Success, warning, and danger each pair a foreground with a muted background. Preserve visible status text alongside color.

### Neutral

Slate canvas, raised panel, muted panel, input, border, body text, and secondary text form the dark hierarchy. Light mode changes these to cool gray canvas and white panels with darker text. Frontmatter records the exact values from the two theme definitions; hover shares the elevated surface.

## Typography

Body and headings request Inter with system-ui and sans-serif fallbacks. Technical data, brand, CIDRs, and identifiers request IBM Plex Mono with ui-monospace and monospace fallbacks. Neither named font has installed self-hosted assets; actual rendering currently depends on available system fonts.

Module titles use the title token. Body uses the body token; navigation and table data are compact (13px), field labels and table headings are smaller (12px). Object CIDRs use monospace (20px/28px, weight 600). Tables use tabular numerals. Avoid uppercase treatment in ordinary workspace labels; legacy badges retain their compact uppercase convention.

## Layout

The sticky application bar has a minimum height of 60px, desktop padding of 10px 24px, and grouped module disclosures. It shares one row with tenant selection, theme toggle, and account. The workspace fills available width with 24px outer padding and no maximum width. At 1279px and below, desktop groups collapse into a Modules disclosure. At 600px and below, the logo hides, the header uses 8px 12px padding, account names truncate, and workspace padding becomes 16px 12px. These are the implemented thresholds; the earlier mockup's 900px threshold is not the runtime contract.

IPAM separates actions, local view buttons, planning views, search, and object content. Its open inspector occupies 334px with a 24px gap. Below 1024px it becomes a successive screen and hides the underlying subnet content. Device workspaces use a 256px object list and 334px inspector with 16px gaps; below 1600px an open inspector hides the object list, and below 1024px inspection replaces device detail. Routing hosts use a 256px list and flexible detail, stacking at 860px and below.

Interfaces and Routes share fixed table geometry: first two columns are 220px and 240px; at 1279px and below they become 28% and 30%. The final column absorbs remaining width and inline editors stay within their column. At 600px and below the routing, subnet-browser, and port tables become labeled records. Other tables retain their module-specific behavior; this is not a claim that every table has a mobile record layout.

## Elevation & Depth

Workspace panels are flat, using tonal differences and thin borders. Navigation disclosures are fixed portals, placed beneath the toolbar without clipping. Their shadow is `0 12px 32px #0005`; the account panel retains `0 16px 40px rgba(0, 0, 0, 0.5)`; object More disclosures use `0 12px 24px #0004`. The new toolbar is opaque and has no backdrop blur. Do not add decorative elevation to the device chassis.

## Shapes

Controls and canvas viewports have gently rounded corners using the control radius. Panels and inspectors use the panel radius; launcher cards and account panels use the card radius. Status pills use fully rounded ends. One-pixel semantic borders define panels and fields. Local view selection is a flat two-pixel accent underline rather than a filled global-navigation pill.

## Components

### Buttons and inputs

Primary buttons use accent fill and theme-specific primary text. Hover brightens the primary fill with `brightness(1.08)`. Ghost buttons are transparent with semantic borders and muted text; hover switches to the hover surface, ordinary text, and accent-dim border. Press moves buttons down 1px; disabled controls use 0.5 opacity and a default cursor. Shared buttons are at least 36px high, increasing to 44px on small screens. These minima do not imply all legacy controls satisfy a universal target-size audit.

Fields use input surfaces, monospace text, semantic borders, and the control radius. Focus changes the border to accent-dim; visible keyboard focus adds a two-pixel focus outline. General controls use a 3px outline offset; fields use 2px. Mobile inputs increase to 16px to avoid browser zoom.

### Navigation and local views

Disclosures open on click or native button keyboard activation, focus their first link, close on Escape with trigger focus restored, and close when focus leaves the toolbar/popup. Real hash links retain modified-click browser behavior. Current pages expose aria-current; local view buttons use aria-pressed in a labeled group. After changing modules, App focuses the main region without scrolling. The Modules label is currently static and does not include the current module name; the module title and active popup link communicate context. There is a skip-to-content link. These observed behaviors are not a certification of complete accessibility.

### Panels, cards, and status

Shared panels use panel surfaces, borders, 20px padding, and 16px mobile padding. Launcher cards use 18px padding, a minimum height of 130px, and a small border change and upward movement on hover. Pills pair semantic foreground/background with concise status text. Inspectors use muted panel surfaces and sticky headings/actions where implemented.

### IPAM inspector

The Subnets browser shows saved parent-child relationships through indentation, expand/collapse buttons, and explicit parent CIDR notes. Search and tag filters keep nonmatching ancestors visible as “Parent context” and automatically expand matching paths; collapse controls are disabled while filtering. Mobile labeled records retain the hierarchy cues and use 44px expand/collapse targets. Hash addresses bookmark modules, not every object or local view. The selected address is edited in a dedicated inspector with full-size fields, details, and save actions. Write, scan, and administration actions remain permission-controlled. The subnet object exposes local actions and More separately from its address filters. Do not migrate operations into global navigation.

### IPAM address views

Heatmap is the default address view on initial selection and when switching subnets. Tiles are fixed at 24 × 24px with a 3px gap. The column count fills the available workspace width, including after opening an inspector. Column measurement and overlays share the same geometry; each page shows up to 20 rows, and all recorded addresses in its range are fetched in batches of at most 500 records. Table remains available as an alternative.

### Device overview and Port table

Fit scales only the physical canvas, preserves physical port order, and considers both viewport width and height without enlarging beyond 100%. The viewport height is `clamp(200px, 38dvh, 380px)` outside fullscreen. Zoom and fullscreen controls complement the full-label Port table and unscaled editor. When a transformed socket's minimum dimension falls below 24px, canvas selection is disabled and an overview message directs users to zoom or the table. Saved documentation explicitly carries “No live link status”.

The optional dedicated management socket appears as a separate **MGMT · Ethernet 1G** group on every device type (storage arrays have one per controller, enabled together), using the existing chassis, socket, selection, and theme treatments. Keep DATA numbering and server NIC slots intact. Its labeled checkbox belongs in New device and Edit device; labels, destinations, interface IP addresses, and optional VLANs use the existing unscaled port editor. Place IP before the optional VLAN controls and keep its independence from VLAN explicit. Show saved IP in the searchable Port table and socket tooltip/accessibility text. Removing saved MGMT or IP data uses the established removal review. Usage and API behavior live in [docs/device-visualization.md](docs/device-visualization.md).

Routers, firewalls, storage arrays, and servers default to Connections: a compact Fit physical panel above a readable map of saved interface → IP / optional VLAN → destination details. Reuse the incumbent semantic surfaces, borders, mono technical values, and unscaled inspector. The panel and map share port selection; selecting an appliance collapses the device list, restored by Browse devices. Keep the map at full text/control size as container queries rearrange its rows; on phones the physical overview is 140px high. Show management first, offer documented/all/management scopes and search, paginate at 12 interfaces, and provide a useful empty state. Preserve separate Panel, Port table, and History views and existing switch defaults. Storage rear panels keep controllers A and B in separate banks with local NIC slots; the map repeats that grouping and adds a Both controllers / A / B filter. Each controller’s ports retain separate selection and documentation through the shared inspector. Server rear panels arrange NIC banks side by side with separate optional management. Their maps group Management and NIC slots/names, preserve slot gaps, and add a Network card filter; search includes card names, while Show all interfaces resets the card filter too. Keep empty filter intersections explicit. Diagram arrows must not imply live state or traffic direction.

### DC Inventory workspace

DC Inventory extends the shared operational panels, theme variables, fields, buttons, and local views. Keep the rack elevation beside its installed-device table, with U1 at the bottom and each U represented by a 44px row; selection opens an unscaled placement form. The rack scrolls within its viewport rather than shrinking labels. At 900px and below the elevation and table stack; at 600px and below device tables become labeled records and location fields use one column. Keep recorded device height, inclusive U ranges, free capacity, and validation errors explicit. Reuse the same DC / rack location fields in Device Visualization; location is shared documentation, not a second device catalog. See [docs/dc-inventory.md](docs/dc-inventory.md).

The Connections view adds a separate physical cabling diagram with rack units aligned at the bottom, including peer racks and a distinct unassigned-equipment column. Use existing semantic tokens; selected cables and their two devices use the accent, while unrelated cables dim. Provide Fit, 100%, zoom, a bounded scrolling canvas and a readable equivalent list. Never imply live state or infer port relationships from free-text Leads to notes. Filter and paginate graph/list together at 20 connections per page; show direct neighbors only. Full endpoint and location names remain readable below the diagram. Place source/destination selection in an inline form, retain drafts after conflicts, and confirm disconnection with both ends visible. On phones, stack form fields and details while the diagram scrolls independently.

### DHCP Generator workspace

Infrastructure → DHCP Generator extends the shared panels, buttons, fields, local view controls, and semantic theme tokens. A configuration list (256px) sits beside a flexible editor; at 900px and below they stack. At 600px and below fields become a single column and published-version tables become labeled records. Configuration, Validate & publish, Versions, and Audit remain local views below global navigation. Reservations show 25 entries per page; configuration lists, versions, and audit show 20. Keep draft saving, validation, publication, and immutable version actions distinct and retain readable generated-text previews in both themes.

### Tenant and group access workspace

Administration → Groups and Tenants extend the shared theme, fields, buttons, tables, and local administration tabs. Group creation, membership, and access history stay in Groups; per-tenant individual and group roles stay in Tenants. The panel's “Manage access for tenant” selector chooses the access-management target independently of the active tool tenant in the global toolbar.

Desktop access and membership views use tables. At 600px and below they become labeled records, with full-width fields and wrapping actions; long group DNs and account names wrap within the record. Group lists, member lists, searchable group/account choices, and global group history use 25-entry pages. This pagination rule does not describe the separate tenant membership and recent-change tables.

Local membership exposes add/remove actions. AD membership is read-only and identified as the latest successful-login observation, with “Managed in AD” text on member records. Place the explanation of combined group permissions and individual-role precedence beside role controls. New group grants begin with an empty role choice, and saving requires an explicit selection. Keep removal consequences visible in confirmation text, including the possibility of remaining inherited access. The API and permission model is documented in [docs/tenants.md](docs/tenants.md).

### Routing Map → IPAM import

Routing Map → Hosts extends the existing operational workspace in Operate mode. Keep **Import all networks to IPAM** beside the Interfaces heading and each **Import to IPAM** action inside its Description cell. Interfaces and Routes retain their shared three-column geometry; on small screens, the action stays with the labeled Description record.

Explain network calculation and duplicate skipping beside the actions. Results remain inline above Interfaces: a status announcement gives created/skipped counts, **Open IPAM** links to the module, and native **Import details** discloses created networks and individual skip reasons. Reuse shared ghost buttons and semantic text/surfaces in both themes; no extra card or modal is needed.

Pending import disables conflicting host operations and interface editing, and guards host/view navigation. Permission restrictions have visible explanatory text. Failures announce an error and offer **Reload interfaces**, including when saved source data changed. Preserve the active tenant throughout the handoff. Behavior and API details live in [docs/routing-ipam-import.md](docs/routing-ipam-import.md).

### Motion

Navigation color/background changes use 0.15s ease. Buttons use 0.08s ease for their press transform and 0.15s ease for brightness. Launcher cards use 0.15s ease for their border and 0.08s ease for their hover transform. Reduced-motion preference sets transition and animation durations to zero and disables smooth scrolling.

## Do's and Don'ts

### Do:

- Do keep module actions, local views, and data filters below global navigation.
- Do use semantic variables so surfaces and state colors follow both themes.
- Do preserve tenant boundaries, feature permissions, draft protection, and existing save/version behavior.
- Do keep complete port labels and editing controls available outside the scaled canvas.

### Don't:

- Don't invent live monitoring, link state, tenant data, or RBAC capabilities.
- Don't treat Fit as a readable editor or enable scaled port targets smaller than 24px.
- Don't claim the static mockups or complete accessibility specification are fully implemented.
- Don't assume Inter or IBM Plex Mono is downloaded or self-hosted.
