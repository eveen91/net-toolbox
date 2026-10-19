# Alternative B — top navigation

Status: a proposal alongside variant A with a sidebar. Mockups are static, contain sample data and do not change the running GUI. They retain the visual system and rules for actions, filters, tables and inspectors from the [main design](README.md).

## 1440 × 900 mockups

- [IPAM with a wider address table](ipam-topnav.svg).
- [Device Visualization with a wider device panel](devices-topnav.svg).
- [Routing Map with shared column boundaries](routing-topnav.svg).

## Composition

One application bar, 60 px high:

```text
net::toolbox | Workspace | Infrastructure ▾ | Diagnostics ▾ | Utilities ▾ | Administration | Tenant | Account
```

`Infrastructure` contains IPAM, Device Visualization and Routing Map. `Diagnostics` contains Troubleshoot, Connection Test and Post-Change Validation. `Utilities` contains IP Calculator and Subnet Splitter. Administration is available according to role; its subpages have their own local navigation. The active module remains clear in the page title, and its group is highlighted in the bar.

Menus open by click, Enter or Space, rather than hover alone. They show full module names and identify the active one. Escape closes the menu and restores focus; keyboard entry and moving through links must work without a mouse. The menu panel extends beyond the bar through a portal/popover and is not clipped. Links remain actual view addresses. Do not apply ARIA menu roles without implementing the complete keyboard model; a simple disclosure with a list of links is sufficient.

Below the bar: title and primary action → module local navigation → data tools → object and inspector. Filters, tabs and operations do not move into the global bar. No additional rows of global navigation are introduced.

## Space recovered

At 1440 px, with 24 px margins and a 334 px inspector:

| Region | A: sidebar | B: top bar |
|---|---:|---:|
| Navigation consuming width | 216 px | 0 px |
| Workspace inside margins | 1176 px | 1392 px |
| Main area with inspector open and a 16 px gap | 826 px | 1042 px |
| Top bar height | 60 px | 60 px |

The gain is **216 px of width**, about **26% for the main area with an inspector**. Fonts are not enlarged and controls are not stretched: the extra space goes to data and the canvas. In Routing Map mockups, the first two columns remain 220 and 240 px; the third grows, and boundaries remain shared between Interfaces and Routes.

Subnet/device/host lists do not have to occupy the recovered space. On laptops, they remain selectors opening an object browser; during editing, data and the inspector receive the space. Wide monitors can show the list beside details while maintaining a reasonable minimum data width. Closing the inspector returns its width to the table or device panel.

## Behavior at different widths

- **From 1280 px:** Workspace/Infrastructure/Diagnostics/Utilities groups, administration, tenant and account in one row. Long user/tenant names are visually truncated with the full value accessible; they do not widen navigation. The tenant name in the menu confirms its identity before switching.
- **900–1279 px:** logo, `Modules` selector with the current module, tenant and account; the complete tool list appears in a grouped dropdown panel. Do not reduce text size to squeeze in all buttons.
- **Below 900 px:** compact header with `Modules` navigation, tenant and account; the logo can move into the navigation panel. Object selection and inspector become subsequent screens. Menu content has its own vertical scroll without whole-application horizontal scrolling.
- **1366 × 768:** retain a compact header and fixed Save in the inspector. Fit adapts the device panel to available space after subtracting toolbar heights as well as accounting for width.

Breakpoints are a starting point for verifying actual labels, fonts and zoom. Tenant switching, RBAC, draft protection and versioning retain the main design's rules.

## Decision comparison

| Criterion | A: sidebar | B: top bar |
|---|---|---|
| Large tables and port panels | Less width | More width without enlarging the bar |
| Module discovery | All names always visible | Modules visible after opening a group |
| Switching modules | One click | Open a group and select a link |
| Growing tool count | Extends the sidebar list | Extends lists within groups |
| Small laptop | Requires sidebar collapsing | Leaves width for data; navigation switches to Modules |
| Predictable work within a module | Shared anatomy | Same anatomy, wider workspace |

**Recommendation for the reported issues:** variant B better suits wide tables and device visualizations. Grouping menus keeps the top bar manageable, while module actions remain below it. The cost is an additional step when switching tools. Implementation should use one selected shell; there is no need to maintain two complete navigation systems in parallel.

## Pre-implementation checks

Verify no overflow with long tenant and account names, keyboard menu accessibility, correct focus after view changes and space allocation with the inspector open. Confirm Fit for 48 Ethernet + uplinks and 48 SFP + 8 QSFP. Mockups have validated SVG syntax and geometry, but do not constitute browser testing of the running interface.
