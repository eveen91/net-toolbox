# New net::toolbox GUI — proposal for review

Status: design, not implementation. Date: 2026-10-13. Mockups use sample data only and do not represent infrastructure status. The application and existing working changes were not modified.

Update: variant B was subsequently implemented. See [implementation scope and verification](IMPLEMENTATION.md); current tokens and components are documented in [DESIGN.md](../../DESIGN.md). This document preserves the original proposal and audit.

## Goal and scope

Turn a collection of separate tools into a consistent workspace for network administrators. The main outcome: users always know where to find an object, where its data lives, where to edit it and what an operation affects. User-confirmed priorities: arbitrary placement of IPAM buttons and data, device visualization that does not fit the screen, inconsistent Interfaces/Routes column widths and inconsistency across the application.

The audit covers the application shell, all eight registered modules, the home screen, account, login, administration and tenants. Findings come from the current JSX/CSS, product and tenant documentation, and a graphify query. The running application was not audited in a browser; geometry observations were calculated from CSS. Accessibility, zoom behavior and real data require verification during implementation. SVG mockups propose composition, rather than an interactive prototype.

## Mockups

A top navigation alternative that recovers 216 px of width: [variant B — design and comparison](TOP-NAVIGATION.md).

- [IPAM: subnet list, address table and inspector](ipam.svg).
- [Device Visualization: complete device panel and port inspector](devices.svg).
- [Routing Map: shared Interfaces and Routes column boundaries](routing.svg).

Each mockup is 1440 × 900 px and shows the same system: navigation, tenant, heading, local views and data area. English remains the interface language, consistent with the current application. The original design documentation was written in Polish; it has since been translated into English. Implementation should keep each screen linguistically consistent.

## Audit: problem → consequence → solution

| Priority | Repository evidence | Problem and consequence | Design decision |
|---|---|---|---|
| P0 | `src/tools/post-change-validation/ExecutionTab.jsx`, `DiffViewTab.jsx`, `PirReportTab.jsx` | Execution uses SAMPLE_TESTS and a timer; Diff shows a fixed positive result; PIR changes local state and claims an export. The GUI may appear to prove tests were executed. | Visible Demonstration mode. Real statuses require backend evidence; missing data does not mean PASS. |
| P1 | `src/components/Toolbar.jsx`, `src/index.css`, `src/tenants/tenants.css` | All modules, configuration, account and tenant compete for a horizontal bar. `.nt-toolbar` scrolls on the X axis. | Persistent grouped navigation panel; the top bar provides context and account controls. |
| P1 | `src/App.jsx` | Navigation is local `useState("home")`; object and view selections are not page addresses. | Addressable views, Back/Forward and restoring the view after refresh. |
| P1 | `src/index.css`, `.nt-main` | A 1280 px limit and 28 px padding leave unused width on large screens. | Data modules use all available width. Width limits remain for prose and simple forms. |
| P1 | `src/tools/ipam/Ipam.jsx`, `IpamToolbar.jsx` | The initial view is search without a subnet list; view switches, planning tools, import and settings sit next to search. | Default subnet list; separate local navigation, filters and actions. |
| P1 | `src/tools/ipam/SubnetDetail.jsx` | Inventory combines statistics, subnets, heatmap/table, DHCP, reservations and tags. Opening a table record sets `inventoryView("heatmap")`. | Subnet tabs organized by topic; table and map open the same inspector without switching views. |
| P1 | `src/tools/device-visualization/device-visualization.css`, `DeviceFaceplate.jsx` | Fixed port widths and `max-content` layout force horizontal scrolling. For 48 Ethernet ports with numeric naming: 24 × 82 + 23 × 8 = 2152 px, before SFP/QSFP. | Fit view, zoom mode and alternative table. Readable data does not shrink with the drawing. |
| P1 | `src/tools/device-visualization/DeviceVisualization.jsx` | The list takes 270 px and the editor sits below the device panel; selecting a port requires finding the form further down. | Ports open an inspector beside the panel. The device list leaves the workspace on smaller screens. |
| P1 | `src/tools/routing-map/RoutingTable.jsx`, `src/tools/shared.css` | Two three-column tables without a width contract or `colgroup`; automatic layout depends on content and editing elements. | Shared column and padding preset. Editing does not change column widths. |
| P1 | `src/pages/HomePage.jsx` | Cards are clickable `div` elements; the description claims everything runs locally in the browser, although modules use the server. | Keyboard-accessible links; descriptions matching the self-hosted architecture and each tool's scope. |
| P2 | `src/index.css`, `src/tools/shared.css` | Many labels are 10–11 px, monospace covers names and nontechnical content, and inputs remove outlines. | Sans for the interface, mono for addresses and port names. Shared visible focus. |
| P2 | `src/tools/shared.css`, module CSS | Tables default to max-height 360 px, some modules override it; separate button and tab systems. | One component set and scrolling policy; local exceptions only for actual data needs. |
| P2 | `src/tools/post-change-validation/PostChangeValidation.jsx`, `src/tools/routing-map/RoutingMap.jsx`, `src/tools/troubleshoot/Troubleshoot.jsx` | Different tab implementations; validation uses clickable `div` elements. | Route navigation as links; tabs within objects with full keyboard support. |

Preserve what already works well: server-side address pagination, debounced search, record version checks, move previews, existing unsaved-change protection, audit and separate IPAM permissions. The redesign should not replace these with a simplified mockup.

## Information architecture

```text
net::toolbox
├─ Workspace
├─ Infrastructure
│  ├─ IPAM
│  ├─ Device Visualization
│  └─ Routing Map
├─ Diagnostics
│  ├─ Troubleshoot
│  ├─ Connection Test
│  └─ Post-Change Validation
├─ Utilities
│  ├─ IP Calculator
│  └─ Subnet Splitter
└─ Administration [according to permissions]
   ├─ Tenant access
   ├─ Users [platform administration]
   ├─ Roles [platform administration]
   ├─ Active Directory [platform administration]
   └─ Audit [appropriate scope]
```

The tenant is a data boundary, not a filter. It remains visible in the top bar, including on phones. Global calculators are labeled `Browser utility · Global`; database modules show the active tenant's name. Switching tenants first resolves unsaved forms, then verifies access, unmounts the module and clears selection, cache and streams. It does not restore an object ID from the previous tenant. On failure, it does not show data under the new tenant's name. Preserve the current rules for separate selections in browser tabs.

Do not equate `tenant-admin` with a platform administrator. Screen and action visibility follows existing permissions, and the server remains the authorization authority. No module access hides its link; read-only mode retains data and shows `Read only`, without write actions. Do not replace separate `ipam.read/write/scan/admin` permissions with one generic switch.

## Shared screen anatomy

1. Sidebar: logo, Workspace, grouped modules, administration at the bottom. The active module has a muted background rather than a bright filled button.
2. Context bar: tenant and account. Initially, search covers navigation and the current module; cross-module search requires separate backend work and is not promised.
3. Page header: title, short description and one primary action on the right. Infrequent operations under `More`; destructive actions at the end of the menu.
4. Local navigation: module subpages always below the header. Do not mix navigation with filters.
5. Workspace: list/selector on the left, data in the center, inspector on the right after selection. Simple calculators use form → result without additional panels.
6. Data toolbar: search, filters, result count and view switch. Bulk actions appear only after selection.
7. Table footer: result range and pagination. Form save actions sit in a fixed inspector footer.

Give each region one purpose. Adding a subnet does not belong in filters; settings do not appear among results; deletion does not visually compete with editing. Do not create one enormous component requiring dozens of flags — the shared anatomy accommodates lists, tables, canvases and forms.

## IPAM

### Structure

Module navigation: `Subnets`, `Overview`, `Planning`, `Data quality`, `Archive`. `Import` is a list action starting the complete flow: file → preview → result. `Planning` contains Allocator and Resubnet, retaining current previews. Settings and tag management are available from the module menu according to permissions.

The default Subnets screen lists available networks: CIDR, description, VLAN, tags and summarized utilization. The tree uses existing `parentId`; it does not imply all overlapping CIDRs form a confirmed hierarchy. Search and filters sit above the list. No selected object means browsing the list, rather than an instruction to “search for something”.

After subnet selection: parent breadcrumbs, CIDR, description and VLAN, a status summary, then `Addresses`, `DHCP & ranges`, `Child subnets`, `History`, `Settings` tabs. Address allocation is an Addresses action; scanning is a subnet action with separate scope confirmation; export is in the data menu. Tenant moves and archiving include an impact review.

### Addresses

The table is the default working view; the map is an alternative occupancy analysis. The table shows saved records with an explicit label. The heatmap covers address space, paginated for large networks; unrecorded addresses are not automatically free. Keep Used, Reserved, Free (recorded), Not recorded separate. Do not sum parent and child networks as independent ranges or present occupancy as host reachability.

An address row and map cell open the same inspector. The table does not switch to the map. Inspector: address and status, hostname/description, team/environment/type, tags, lock and available exclusions, history. The form saves manually; changing status does not unexpectedly save all other fields. Fields and actions must respect existing permissions.

Bulk selection retains current semantics: only the current filtered page. Label it `12 selected on this page`; do not imply selection of the entire database. Changing filters/pagination explicitly clears selection. Operation results report successes, skips and reasons, without a false claim of complete success.

### Flow

Subnet list → selection → address table → open address → edit in inspector → save → update row without losing filters or scroll position. A version conflict preserves the draft, shows the current version and offers another review; it does not overwrite another user's changes.

## Device Visualization

Device list: name, type, model and assigned port count. Filters remain consistent with the API: vendor applies to firewalls; do not add fictional locations, racks or switch vendors. Object header: name, description, model, port summary. Views: `Panel`, `Port table`, `History`; device editing is an action rather than another unrelated screen.

### Fitting the complete panel on screen

The canvas is bounded by available screen space. Initially use `Fit`: all port group geometry fits within the canvas width. Calculate scale from the actual bounding box and ResizeObserver, with a margin; the canvas does not widen the page. Opening the inspector recalculates Fit unless the user chose manual zoom. Controls: `Fit`, minus, current scale, plus, `Fullscreen`. Zoomed views scroll only the canvas. Fullscreen has a visible exit and Escape support.

Do not shrink all JSX, including text and buttons, to an unreadable size. Fit shows a port schematic: family, number and assignment; full names, labels, destination and VLAN are in the inspector and table. Preserve physical pairs 1/2, 3/4, etc., and separate Ethernet/SFP/QSFP and NIC groups. Do not wrap ports into arbitrary rows merely to fit the width.

If Fit reduces interaction targets below the accepted minimum, use the schematic for orientation and provide selection through a readable list/table and port search. Do not overlap enlarged hitboxes. Default to the table on small screens; Panel and Fullscreen remain explicit choices. Keyboard support: one Tab enters the schematic, arrows move between ports, Enter selects, and focus has a readable name. Selection is shared between panel and table.

### Editing

The selected port opens an inspector beside the canvas: full name, family/speed, label, Leads to, Access/Trunk mode and relevant VLANs. Save actions sit in a fixed footer; unsaved changes are visible. Switching ports, devices, modules or tenants uses a shared `Save / Discard / Stay` decision. An asynchronous operation cannot save to a newly selected object.

A documented assignment is not link status. Show `Saved documentation · No live link status`. Leads to remains text; do not draw confirmed connections to other devices without relationships in the data. Changing VLAN does not configure hardware. Reducing the port count shows the existing preview of lost assignments/configuration and requires confirmation. Deleted device history remains available by ID search.

## Routing Map — column alignment

Show the saved host list first, then host details. Move the import editor to a separate `Import routes` flow; it should not permanently occupy the left side of the operational screen. Local navigation: `Hosts`, `Routing test`, `Topology`.

In host details, Interfaces and Routes occupy the same width and start on the same axis. For wide views, use a shared three-column preset: first 220 px, second 240 px, third the remainder. For a 960 px data area, boundaries are 0 / 220 / 460 / 960 px. Both tables have an explicit `colgroup`, `table-layout: fixed`, identical 12 px padding and rows at least 40 px high. During editing, inputs fit their own cells without recalculating columns. The mockup shows tables for the same host, rather than comparing different objects.

| Slot | Interfaces | Routes | Rule |
|---|---|---|---|
| A: 220 px | Name | Network | Full technical value available for copying |
| B: 240 px | Address | Next hop | Monospace; long addresses supported without geometry changes |
| C: remaining space | Description | Interface | Descriptions can wrap; interface names provide a full-value preview |

In narrower areas, use a shared 28% / 30% / 42% variant with a minimum readable table width. Below that width, both sections switch to label/value records rather than widening the entire page. Do not force identical widths on every table in the project — the shared contract applies to adjacent sections with comparable structure.

Topology has Fit, zoom and a host inspector accessible by click and keyboard, rather than hover-only data. An edge still represents a shared network from saved data; it does not represent a physical cable or a verified routing path.

## Other screens

| Screen | New layout and primary flow |
|---|---|
| Workspace | Compact tool group catalog and locally remembered recent modules. Short, accurate descriptions. No aggregate “network health” indicators that the application does not collect. |
| Connection Test | Configuration on the left, results on the right. Sources → destinations → ports → OS-appropriate credentials → advanced options. Scope summary before starting. Results distinguish connection failure, execution error and missing result; status filters and full details. Preserve validation, limits and SSH/WinRM parameters. Do not promise job cancellation without an API. |
| Troubleshoot | Preserve Diagnostics, Locate & Port, Reachability & Route, STP, Inventory, Activity scope. Unify navigation and target → parameters → result layout. Locate has persistent target context, followed by readable port health, cable, optics and access sections. Result cards do not resize arbitrarily and show time and source. Preserve shared `locateForm` and Route check's dependency on Locate credentials; do not pretend a global context exists today. |
| Post-Change Validation | Baseline → Execution → Diff → PIR sequence with plan and evidence. Stages without data show Not available, not success. Clearly label current simulations Demonstration. Real runs, persistent sign-off and export require separate integration; GUI changes alone cannot supply them. |
| IP Calculator | Short form with adjacent result, copying IP/CIDR/mask, binary breakdown in an expandable section. Labels associated with inputs; clear information about the prefix from the IP field. |
| Subnet Splitter | Network and exclusions as input, scope preview and CIDR blocks as output. Errors identify a specific line. Checking individual IPs is a secondary section; preserve existing calculation rules. |
| Login / account | One field and error system with password manager support. Account and password changes in a separate panel with correct focus. Session expiry blocks actions; do not store diagnostic credentials in localStorage or URLs. |
| Administration / tenants | Separate platform and active tenant scope. Users/Roles: table and inspector, permissions grouped by module. AD: sectioned form matching existing options. Audit: filters, table, event details; do not imply unified auditing across all modules without API aggregation. |

## Visual system — proposed tokens

This is a candidate system, not an approved global DESIGN.md. Style: flat, calm surfaces, subtle separators, readable typography and one teal accent. No background gradients, decorative glass, excessive pills or cards within cards. Identity remains in `net::toolbox`, the accent and precise data.

| Token | Dark variant | Light variant |
|---|---|---|
| canvas | #11161D | #F3F5F7 |
| surface | #181F28 | #FFFFFF |
| surface-subtle | #202A35 | #EAF0F3 |
| border | #344252 | #CCD5DF |
| text | #E8EDF3 | #17212D |
| text-muted | #A5B2C2 | #536273 |
| primary background | #72D6C3 | #087565 |
| primary text | #10231F | #FFFFFF |
| selection background | #203D3A | #DCF2EC |
| focus ring | #8DE6D5 | #087565 |
| success text | #89DCAC | #17663A |
| warning text | #F1C277 | #835000 |
| danger text | #FFADB4 | #AD2334 |

Text and buttons: self-hosted Inter or system sans fallback. Mono: self-hosted IBM Plex Mono, only for IP/CIDR/MAC/port names/CLI. No mandatory Google font downloads in a self-hosted installation. Typography: page title 24/32 px semibold, object title 20/28, body 14/20, data 13/20, labels at least 12/16. Tabular numerals. The 14 px body size does not apply to mobile inputs: use at least 16 px there.

Spacing scale: 4, 8, 12, 16, 24, 32 px. Workspace padding: 24 px desktop, 16 px tablet, 12 px phone. Controls: 36 px desktop, at least 44 px for touch. Table rows: 40 px standard, optional 32 px compact on desktop only. Radius: 6 px controls, 8 px surfaces. One 18–20 px SVG icon system with consistent stroke weight; no mix of Unicode and emoji.

States: hover, focus, selected, disabled, pending, error, success. Accent indicates action or selection; a green status should not resemble a selected row. Status always uses text + symbol, not color alone. Motion only as feedback, 150–200 ms; reduced-motion disables transitions. No animated whole-page entrances.

## Responsive behavior and geometry

| Viewport width | Composition |
|---|---|
| ≥1600 px | Sidebar 216 px, list 256–280 px, flexible data area, inspector 320–360 px. Not every region must always be open. |
| 1280–1599 px | Sidebar 200–216 px. The object list collapses when the inspector is open; canvas and table retain usable width. The 1440 px mockups deliberately show this variant. |
| 900–1279 px | Navigation in a drawer with names; list and detail as two views. The inspector replaces detail or opens a full panel with focus management. |
| <900 px | One primary view: list → object → inspector, with explicit Back. Tenant remains visible. Device defaults to table. |
| Phone / 320 CSS px | Label/value records and vertical scrolling. A canvas or genuinely two-dimensional table may scroll independently, but the whole page must not. Full-screen forms and touch controls. |

Do not assess layout by viewport alone: opening the inspector reduces content width. Also use container queries. Do not squeeze four columns onto a 1366 × 768 laptop. On that screen, the header is compact, the list collapses during editing, and the selected port and Save button remain visible without scrolling the entire page. Tables use sticky headers; apply nested scrolling deliberately, not through a global 360 px limit.

## States and accessibility

| Situation | Behavior |
|---|---|
| First use | Explain what the module stores and offer the appropriate Add/Import action; explain required access for read-only users. |
| No filter results | Preserve filters, show count 0 and Clear filters. Do not confuse this with an empty database. |
| Loading | Stable skeleton geometry; while refreshing, mark old data as refreshing and prevent operations on stale selections. |
| Data error | Message beside the affected region and Retry; do not discard the draft. Do not show 0 for unknown data. |
| Scan / job | Scope, backend status, progress only when known, results and errors. Switching views does not cancel server work. |
| Version conflict | Preserve the draft, explain, read the current version and preview again before saving. |
| Archiving / deletion | Exact object, scope of effects, reason if required by the API; confirmation in a dedicated dialog or review step. |
| Partial success | List skipped items and reasons; warning status rather than overall success. |
| Unsaved changes | Save / Discard / Stay, including tenant changes; no automatic overwrite. |
| Session expired | Block actions and require login again; secrets are not persisted. Restore a draft only for the same account and tenant after verifying access. |

Implementation target: WCAG 2.2 AA. Text contrast at least 4.5:1, large text 3:1, essential boundaries and focus indicators 3:1. The AA interaction target minimum is 24 × 24 CSS px with standard exceptions; adopt 44 px as the project's touch standard. All actions support keyboard input, sticky bars do not obscure focus, and closing a panel restores focus to its trigger. Dialogs have a name, focus management and Escape support; tabs use roving tabindex and arrows. Page links do not pretend to be ARIA tabs. Tables retain semantics and `aria-sort`; maps have an equivalent table view. Async messages use `aria-live`, and errors are associated with fields. Check 200% zoom, reflow at 320 CSS px and password manager support. Source: [W3C WCAG 2.2 Quick Reference](https://www.w3.org/WAI/WCAG22/quickref/).

## Phased implementation

1. **Shared shell and components.** AppShell, Sidebar, TenantSwitcher, PageHeader, local navigation, Button, Field, StatusBadge, DataTable, Inspector, dialog, Empty/Error/Loading. Add addressable views; consider hash routing for self-hosted installations without requiring new server rewrites. Preserve auth gates and tenant remounting. Do not change APIs for cosmetic work.
2. **Routing Map as the first table test.** Explicit Interfaces/Routes columns, consistent alignment and stable editing. The small scope validates shared components before rebuilding IPAM.
3. **Device Visualization.** Fit and zoom, port table, inspector, responsive list collapsing, focus and draft protection. Preserve versioning and device structure change previews.
4. **IPAM.** Subnet list, local view hierarchy, subnet tabs and shared address inspector. Only then unify import, planning, quality and archive. Do not rewrite scan hooks and the entire backend at once.
5. **Diagnostics, calculators and administration.** Move existing behavior into shared components. Label demonstration validation screens before further development. Connecting real runs/sign-off/export is a separate functional task.
6. **Cross-cutting validation.** Both themes, keyboard, laptop/tablet/phone, different roles, large datasets and version conflicts. Remove old global `.tabs`, `.tab` classes, hardcoded colors and duplicate components only after migrating every consumer.

View addresses should encode module, object ID, local section and explicit filters. Cache scope is always tenant + module + object. An ID in a URL is not proof of permission. Do not store passwords, secrets or raw diagnostic results in URLs or persistent storage. Appearance settings may be local, as may view preferences after appropriate scoping.

## Acceptance criteria

- IPAM opens with a visible subnet list; opening an address from the table does not switch to the map. Filters and table position remain after saving.
- All modules share header, navigation, filter and primary action structure rather than blindly imposed identical containers.
- At 1366 × 768, Device Fit shows the entire 48 Ethernet panel + uplink groups. Also check 48 SFP + 8 QSFP, a firewall and a multi-NIC server. If Fit is unreadable, port selection remains available from the table; saving and full port names remain readable.
- Interfaces and Routes have exactly shared column boundaries at the same widths, including while editing and with long data. Test an empty section, a long interface name and a multiline description.
- Switching tenants with an open form does not lose changes without a decision, display the old tenant's data under a new name or persist credentials.
- IPAM read/write/scan/admin and tenant-admin/platform-admin modes preserve current backend boundaries; direct URLs do not bypass denied access.
- Sample validation results are labeled as demonstrations, without claims of completed exports or persistent signatures.
- No whole-page horizontal scrolling at 320, 390, 768, 1024, 1366, 1440 or 1920 px. Independent scrolling of two-dimensional data is clearly described.
- All primary flows support keyboard use, zoom and both themes. Assess conformance in the implementation, not from mockups.

## Decisions to confirm before implementation

Recommendation: implement the system in phases, starting with the shared shell and Routing Map tables. Dark remains the initial theme for existing users and light is equally supported; user preference overrides system preference. The English interface requires no language changes. Do not introduce new DC/VRF/rack structures or false monitoring. Composition and list collapsing during editing remain for review; mockups allow these decisions to be assessed before changing the running application.
