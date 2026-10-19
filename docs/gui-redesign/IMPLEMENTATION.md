# Implemented top navigation variant

Variant B from TOP-NAVIGATION.md is implemented in React. Mockups remain design references; DESIGN.md records the current component and token contract.

## Changes

- Top bar: Infrastructure, Diagnostics and Utilities groups, Workspace, administration according to permissions, tenant, account and theme switch. Below 1280 px, modules are in the Modules menu; phone screens retain tenant and account. Menus render through a portal and support Escape and focus management.
- Full-width content, shared spacing rhythm, buttons, fields, statuses and local view switches. Light and dark themes store only appearance preferences. The mandatory Google font import was removed; font names have local/system fallbacks.
- Modules have hash addresses, working refresh and Back/Forward. Focus moves to content after switching modules. Addresses do not yet encode all object selections and filters.
- IPAM: default subnet list with filtering, separate module views and subnet sections, heatmap as the initial view with 24 × 24 px tiles and 3 px gaps, columns filling available width and up to 20 rows per page, fetching the entire visible range in batches of up to 500 records; the table remains an alternative. Table and map open a shared inspector without switching from table to map. Infrequent subnet actions are under More. Pagination, versioning, permissions and bulk operations are preserved. Record refresh is tied to the selection generation, so late responses do not replace another selected address.
- Device Visualization: Fit measured from device geometry and available space, zoom, fullscreen, searchable port table, adjacent inspector and collapsible device list. Phones initially show the table. Physical port order remains unchanged. Editor saves remain documentation, not hardware configuration. When Fit makes targets too small, selection requires zoom or the table.
- Routing Map: identical colgroup for Interfaces and Routes, stable widths during editing, mobile label/value view. Import is an expandable flow rather than a permanently open form.
- Other modules use the shared appearance and local navigation. The home screen supports keyboard use and describes the actual self-hosted architecture. Demonstration validation stages are explicitly labeled; the GUI does not claim exports or persistent signatures it has not produced.

## Verification

- `npm run build`: production build passes.
- `npm test`: 24 files, 84 tests pass; these include navigation group permissions and Fit calculations.
- Chromium with isolated sample API responses: 63 combinations (Workspace and eight modules × 320/390/768/1024/1366/1440/1920 px), without whole-page horizontal overflow.
- Browser flows: IPAM inspector without switching away from Table, unsaved draft protection, address saving and delayed responses during selection changes; Fit of the entire device and port saving; shared routing table boundaries; both themes; menu visibility for an IPAM reader; focus after Escape, module selection and Back/Forward.
- Independent review of six desktop/mobile screenshots and source: disposition ship after a focus correction. Light theme was checked after color transitions completed.
- `graphify update .`: code graph refreshed through AST extraction.

Screenshots of the actual application with test data are in `.impeccable/review/`. Browser tests check the frontend against fixtures, not connections to real devices or validation of existing backend working changes. A full WCAG conformance audit was not performed. The Impeccable loader and detector are unavailable without the installed engine; source and independent review were used directly.

## Current implementation boundaries

The subnet list is flat; the planned full tree and individual object URLs remain future extensions. Fit provides orientation — names and forms remain readable in the table and inspector. Unsaved-change protection covers device/port, address and subnet header editors; it is not yet a shared Save/Discard/Stay system for every project form. Connections, validation runs and persistent sign-off were not added as new backend features. Implementation does not move or change tenant data.
