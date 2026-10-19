# Device Visualization

This tool manually documents physical ports on switches, routers, Check
Point/FortiGate firewalls, servers and dual-controller storage arrays. It does
not query devices, require passwords or show live link status. A port marker
indicates saved “Leads to” information, rather than an active network connection.

## Permissions and tenants

Data and history are stored in the active tenant's database. Select a tenant in
the application bar, then **Device Visualization**. In an existing installation,
an administrator must grant the role the `device-visualization` permission in
Config Panel. New installations add it to the initial `user` role; existing roles
are not overwritten. Platform administrators and `tenant-admin` have access via `*`.

Device names are unique without case sensitivity under SQLite NOCASE within a
tenant, across all device types. Other tenants can use the same names. Selecting
a tenant clears local edit drafts. Mode without login retains the existing
default tenant access rules.

## Creation and ports

Devices share an inventory with [DC Inventory](dc-inventory.md). The
**New device / Edit device → DC / rack location** form saves device height in U,
rack and starting unit; the data center is derived from the rack. U1 is at the
bottom, and a 2U device starting at U3 occupies U3–U4. The UI requires a height
when saving, including for existing devices whose height is unknown. No rack
means **Unassigned**. Collisions and placements beyond rack capacity are rejected.

The data center and rack catalog can be read with `device-visualization`;
managing locations requires `dc-inventory`. The device API accepts optional
`heightU`, `rackId`, `rackPosition`; omitting them during editing preserves the
location, while `rackId: null` unassigns the device. DC Inventory placement shares
the device version, so concurrent writes require a reload after a conflict.
Placement does not copy the device and preserves all its port data.

1. Select **New device**, a type and name; optionally enter a description and a
   custom model name.
2. Switch/router/firewall: set Ethernet, SFP and QSFP port counts and each
   family's speed. For a firewall, select Check Point, FortiGate or generic.
3. Server: add 1–16 NICs. Each card has its own connector type, 1–8 sockets,
   speed and optional name. **Add network card** uses the first free slot.
4. Use **Save device**. Select a port on the panel, enter a label and **Leads to**,
   then **Save assignment**. **Clear assignment** removes the destination and
   preserves the editor's current label.

Speeds: Ethernet 1/10G, SFP 10/25G, QSFP 40/100G. Up to 128 DATA ports and one
optional MGMT port per device (storage: two, one per controller); switch/router:
up to 96 Ethernet, 48 SFP and 16 QSFP; firewall: up to 96 Ethernet, 32 SFP and
16 QSFP. Firewall appearance is generic; entering a model does not fetch vendor
specifications. A server shows its rear panel and separate NIC slots. On a phone,
the port panel scrolls horizontally.

All device types can have a separate **MGMT · Ethernet 1G** socket (storage: one
per controller). **Dedicated management port (MGMT · Ethernet 1G)** is selected
by default in **New device**. Existing devices remain unchanged; add the port in
**Edit device** by selecting the same checkbox. MGMT does not change DATA port
numbering or NIC slots. Edit its label, **Leads to**, IP address and VLANs in the
regular port editor. Disabling MGMT removes its socket; if it contains saved data,
the existing loss preview and **Confirm removal and save** are required.

Router is a separate device type without a vendor field. A saved device's type
cannot be changed. The API accepts `deviceType: "router"` with `portGroups`, without
`networkCards` or a vendor; the same family speeds apply as for switches.

## Storage arrays: two controllers and separate NICs

In **New device → Storage array**, configure **Controller A** and **Controller B**
separately. Each requires 1–8 NICs in local slots 1–8; each card has 1–8 ports,
its own connector family, speed and optional name. The total limit is 128 DATA
ports. NIC 1 can exist on both controllers at once. The rear panel shows two
separate port banks. Storage arrays have no vendor field, and their saved type
cannot be changed.

The shared **Dedicated management ports (one per controller · Ethernet 1G)**
checkbox enables or disables both MGMT ports together: the limit is then 128 DATA
+ 2 MGMT. Edit the IP addresses, labels, destinations and VLANs of the two MGMT
ports independently in the existing port editor. Removing or replacing a
controller A card with a saved IP, VLAN, label or destination requires a review
of lost data and confirmation; retained controller B cards keep their IDs and
assignments.

The API accepts `deviceType: "storage"`, without a vendor, with `networkCards`
instead of `portGroups`. Each card must include `controller: "A"` or `"B"` and a
local `slotNumber` from 1–8. An existing card ID cannot change controller or slot;
a card belonging to another device is rejected. Card and port responses include
optional `controller`, empty for other device types. Servers do not accept a
nonempty `controller`. Omitting `managementPort` retains the existing creation
and editing semantics; `true` creates the MGMT pair.

## Routers, firewalls, storage arrays and servers: panel and connection map

After selecting a router, firewall, storage array or server, the default
**Connections** view combines a compact physical panel with **Fit** and a map of
saved documentation: interface → IP / optional VLAN → **Leads to**. IP and VLAN
remain independent; missing one does not block the others. Selecting an interface
on the map or a socket opens the existing port editor. Both representations
share the selection.

**Show interfaces** offers **With saved details** (label, IP, VLAN or destination),
**All interfaces** and **Management only**. MGMT is first in its group; the map
shows 12 interfaces per page. **Find interface** searches name/label, IP, VLAN
and destination. Empty results explain missing data or matches and offer
**Show all interfaces**, which clears the search filter and shows all ports.

Storage arrays group interfaces by controller. The **Controller** filter selects
**Both controllers**, **Controller A** or **Controller B**; search and interface
scope work with this filter. **Show all interfaces** also resets the controller.

Selecting a router, firewall, storage array or server collapses the device list;
**Browse devices** restores it. Separate **Panel**, **Port table** and **History**
views remain available. Switches retain the default panel on desktop and table
on narrow screens. The map adapts to its container width; on phones it retains
full-size text and buttons, and the physical preview is 140px high. Lines and
arrows describe saved **Leads to** information, not link status or traffic direction.

Servers show a rear panel with NICs side by side and separate MGMT, if enabled.
The map separates **Management** and NIC groups, preserving slot numbers and card
names, including gaps such as NIC 1, 3 and 7. The **Network card** filter selects
a specific card by ID; **Find interface** also searches card names. The card
filter combines with **Show interfaces** scope: a selected card and
**Management only** may produce an empty result described as no interfaces
matching the filters. **Show all interfaces** also resets the NIC filter.
Selecting a port still opens the shared IP, optional VLAN and **Leads to** editor.

Existing servers receive the new view after refreshing the application. This
view change requires no backend, schema or data migration; card IDs, names,
IP addresses and other saved assignments remain unchanged.

## Per-port SFP modules

Select an SFP socket and set **SFP module** in the port editor:

- **Use group default** — retain the SFP group's configured speed;
- **SFP · 1G optical**;
- **SFP+ · 10G optical**;
- **SFP28 · 25G optical**;
- **SFP → RJ45 · 1G copper**.

The choice applies only to that port, including SFP NICs on servers and storage
controllers. Other sockets keep their own settings. The physical cage remains
SFP; the installed module determines the documented connection medium and speed.
The panel, table, connection map and destination picker display the selected
module. An RJ45 1G module matches Ethernet 1G ports and other RJ45 1G modules;
optical SFP 1G matches optical SFP 1G, while SFP28 25G matches SFP ports documented
at 25G. Occupied matching ports retain the usual replacement review.

The selector documents installed hardware; it neither configures the device nor
verifies whether a particular cage/platform supports the module. Group defaults
are separate from per-port module settings. Changing a group speed preserves
explicit module choices. Removing a module-configured port requires the existing
loss preview and confirmation. Saving uses device version checks and audit.

API: port assignments accept nullable `transceiver` with values `sfp-1g`,
`sfp-10g`, `sfp28-25g`, `rj45-1g`. Non-null values are accepted only for SFP ports.
Omitting the field preserves the saved module for older clients; `null` restores
the group default. Port responses retain physical `family` and group `speedGbps`,
and expose `transceiver`, `effectiveFamily`, `effectiveSpeedGbps`. Backend startup
idempotently adds `dv_ports.transceiver`, leaving existing records at the group
default and preserving IDs, network data, connections and audit history.

## Choosing a Leads to destination

**Leads to** remains freely editable. **Choose existing device** searches devices
by name, model or description in the active tenant (20 devices per page, excluding
the current device). Select a device to see only ports with the same effective connector medium (Ethernet, SFP
or QSFP) and speed as the source port, taking installed SFP modules into account
and including matching MGMT ports.
Occupied matching ports remain selectable with replacement confirmation. If none
match, choose another device or use a manual note. The list shows their saved destinations,
physical cable IDs, labels, IP addresses and VLAN settings. Choose a port to stage
a connection, or **Use device name only** to fill a text note without a cable.
Typing manually also switches back to a text note.

**Save assignment** with a selected port atomically creates an actual port-to-port
cable and sets reciprocal notes: `Destination device / port` on the source and
`Source device / port` on the destination. The cable immediately appears on the
next DC Inventory graph read. Target labels, IP addresses and VLAN settings are
preserved; source fields are saved from the current editor. Nothing is configured
on the actual hardware. Closing the picker alone does not save anything.

A port is considered assigned when it has a physical cable or a nonempty
**Leads to** note. When either end would lose an existing assignment, saving shows
**Replace existing connection?** with current destinations, cable endpoints,
labels, IP/VLAN settings and the proposed pair. Only **Confirm change and save**
commits it. **Cancel replacement** leaves saved data unchanged. Replacing cables
frees displaced peer ports and clears only reciprocal notes that still match the
removed pair; custom notes on displaced peers are retained. Labels, IP addresses
and VLAN settings on those peers are preserved.

The server checks both device versions and binds confirmation to the exact source
draft, affected port configurations and cable relationships. Concurrent changes
require a fresh review; a stale confirmation cannot overwrite a new state. Data,
versions and audit records for all affected devices and cables change in one
transaction and roll back together on failure. Re-saving an unchanged pair is a
no-op. The Device Visualization permission covers this workflow; `dc-inventory`
is only needed to open its separate inventory workspace and API.

Manual text and device-name-only choices remain notes: they do not create, replace
or remove physical cables, and renaming/deleting a device does not rewrite those
notes. **Clear assignment** clears the note only. Use a selected device/port to
replace a physical connection, or DC Inventory to explicitly disconnect it.

API: the existing `PUT /api/device-visualization/devices/{id}/ports/{portId}`
accepts optional `targetPortId` and `targetVersion` alongside the normal source
assignment fields and `expectedVersion`. Both target fields must be supplied
together. If replacement is needed, HTTP 409 has
`detail.code: connection_change_required`, `token`, affected `ports`, current
`connections` and proposed reciprocal destinations. Resubmit the unchanged
request with `replacementToken: token` to confirm. Changes to the state or draft
invalidate that token and return a new review. Omitting the target fields retains
legacy manual-note behavior. No additional schema migration or dependency is
needed beyond the existing physical cabling schema.

## Physical cabling between devices

[DC Inventory → Connections](dc-inventory.md#rack-connections) adds explicit
port-to-port cabling within and between racks. It uses these same device and port
IDs, including controller-specific and MGMT ports. The inventory workspace requires `dc-inventory`; the device/port selection
workflow above can manage the same cables using `device-visualization`.

Port responses include nullable `connectionId`; the port editor shows the cable
ID and supports reviewing a replacement through device/port selection. This is separate from the **Leads to** note: editing
or clearing that note does not disconnect a cable. Connecting/disconnecting
increments the version of both devices and is audited. Moving devices preserves
cables. Removing a connected port or card requires preview and confirmation;
`removedConfiguredPortCount` includes ports with IP, VLAN, an explicit SFP module or a physical cable,
counting each once. Confirmed removal clears the relationship and records it in
inventory history; deleting a device similarly releases its peer ports.

## Editing and data protection

Changing speed and adding ports preserve existing assignments. Reducing the
port count removes the highest numbers. Removing a middle card does not change
other cards' slot numbers. Adding a card in the same slot creates a new card;
it does not inherit former assignments. Changing a card's connector family
replaces its ports.

If an edit removes labels, destinations, IP addresses or VLANs, **Save device**
first shows an exact loss preview. Only **Confirm removal and save** commits the
change. Modifying the form invalidates the preview. The API independently checks
the version and confirmation. A concurrent edit conflict preserves the draft
and requires an explicit device reload and change review. Saving without changes
does not increment the version.

**Delete device → Confirm delete** removes the device and ports while retaining
history. The deletion message includes the historical device ID.

## Search and history

The list supports name/model/description search, type and vendor filters, and
pages of 20 devices. **Device history** shows saved changes with before and after
data. Enter a deleted device's ID to view its history. The actor is identified
by a global account ID; no actor means open mode. History is also paginated.

## API and maintenance

Prefix: `/api/device-visualization/devices`. Available operations include listing,
CRUD, preview via `POST /{id}/update-preview`, editing via
`PUT /{id}/ports/{portId}` and history via `GET /{id}/audit`. Listing accepts
`query`, `deviceType`, `vendor`, `limit` (1–100) and `offset`; history accepts
`limit`/`offset`. Tenant selection uses `X-Tenant-ID`.

Editing requires `expectedVersion`; removing port data additionally requires
`confirmPortDataRemoval: true`, and DELETE requires `confirmDelete: true` in the
JSON body. HTTP 409 with `detail.code` indicates `stale_version` or
`confirmation_required`. Invalid payloads return 422, name conflicts 400, and
missing resources 404.

Device creation and editing accept the optional boolean `managementPort`.
`true` adds MGMT (a pair for storage arrays), while `false` disables it. Omitting
the field during creation does not add MGMT; the **New device** UI sends `true`
by default. Omitting it during editing preserves the saved setting, including
for older API clients. The port uses existing groups, ports, versioning and
audit; no schema migration is required.

The `dv_devices`, `dv_port_groups`, `dv_ports`, `dv_audit` tables are created at
startup in every registered database and when a tenant is created. Data, version
and audit records change in one transaction. There is no separate database or
additional volume. Backups of all tenant databases also cover this module; see
[server maintenance](maintenance.md).

Raising the switch SFP limit from 32 to 48 migrates the constraint in existing
databases at backend startup, preserving IDs, assignments and audit records.
Configurations including 48 SFP + 6 or 8 QSFP (54 or 56 ports total) are supported.

At backend startup, an idempotent migration extends the previous device type
`CHECK` constraint with `router` and `storage`. It preserves device IDs, groups,
ports, assignments, audit records and the ID sequence; manual database editing
is not required.

Controllers use existing NIC groups without an additional database field
migration. Internal group slots 1–8 represent A and 9–16 represent B; the API
always shows local slots 1–8 with `controller`. This representation is a backend
implementation detail.

## Interface IP addresses and optional VLANs

The port editor's **IP address** field accepts IPv4 or IPv6, optionally with a
prefix, e.g. `192.0.2.10`, `192.0.2.10/24` or `2001:db8::10/64`. The address belongs
to the interface: saving a prefix preserves the host address rather than replacing
it with the network address. VLAN is optional and independent of the IP address;
save IP alone, VLAN alone or both. This applies to all ports, including MGMT.
An empty field clears the address when saved. The port table shows an
**IP address** column and also searches addresses; the socket tooltip and
accessible name on the panel include the saved IP.

The assignment API and port response include nullable `ipAddress` (up to 64
characters). Addresses are normalized: IPv6 uses compressed notation and prefixes
use numeric notation. Addresses with a `%` zone, e.g. `fe80::1%eth0`, are rejected.
Invalid addresses return 422. `ipAddress: null` or an empty string clears the IP;
omitting the field during editing preserves the current address for older
clients. VLAN operations do not require an IP address.

At backend startup, an idempotent migration adds the `ip_address` column to
`dv_ports`, preserving existing ports, assignments and audit records. Existing
ports initially have no IP. Address writes use shared versioning and audit.
Removing a port containing only an IP also requires a loss preview and
confirmation; `removedConfiguredPortCount` includes ports with IP, VLAN, an explicit SFP module or a physical cable,
counting each once.

In the port editor, select **Port mode**: **Access** (one Access VLAN) or
**Trunk** (Allowed VLANs: a list such as `10,20,100-110` or `all`). Trunk can have
an optional Native VLAN. VLAN IDs range from 1–4094. **Not configured** clears
the VLAN configuration when saved. Changing mode resets incompatible form fields.
Saving is manual documentation and does not send configuration to the device.

Configuration is available for ports on all device types, saved with versioning
and audit, and preserved during speed changes and ordinary assignment edits.
Removing a configured port requires preview and confirmation even without a label
or destination. Migration adds fields to existing ports without changing their IDs.

The port API also accepts `portMode`, `accessVlan`, `trunkVlans`, `nativeVlan`.
Omitting all four preserves the current configuration for older clients; explicit
`portMode: null` without VLANs clears it. Trunk lists are normalized, sorted and
deduplicated. Native VLAN is documented independently of Allowed VLANs.

## Switch port naming conventions

In **New device / Edit device → Port naming**, select:

- `Eth 1 / SFP 1 / QSFP 1` — separate numbering for each family (default);
- `1/1/1` — unit / slot / port, with editable unit and slot numbers;
- `1/0/1` — unit / 0 / port, with editable unit;
- `1/1` — unit / port;
- `1, 2, 3` — continuous numbering.

Numeric formats number ports in order: Ethernet, SFP, QSFP. Names therefore do
not repeat across families. Adding ports in an earlier family shifts later
families' numbers. Only display names change: IDs, labels, destinations and VLANs
are preserved. Unit number: 1–16; slot: 0–16. Routers, firewalls and server cards
retain family- or card-based names. Existing switches continue using family-based
names after migration. API fields: `portNaming`, `portUnit`, `portSlot`; editing
with an older client that omits these fields preserves the saved convention.

The switch panel arranges each port family in two rows, paired vertically:
1 above 2, 3 above 4, etc. The column count grows with the port count; only the
panel scrolls on narrow screens. Layout does not change numbering or configuration.

## Storage heads, shelves and drive bays

Use **Storage head / array** for the existing dual-controller device and **Storage expansion shelf** for an enclosure attached to it. A shelf is a separate inventory device with its own height and optional rack placement. It has exactly two dedicated SAS expansion ports. Connect these through **Choose existing device** and select a matching expansion port on a head or another shelf; reciprocal assignments and the DC Inventory cabling view use the existing physical connection mechanism. Free-text destinations remain supported. Ports already in use require the existing replacement review.

A head can record 0–16 expansion ports in **Edit device → Disks and expansion**. Expansion ports are separate from controller NICs and cannot be connected to network ports. They currently use the documented SAS 12G connector profile; this is documentation, not hardware discovery or validation of a vendor topology. Existing heads retain their NICs and receive no additional ports until configured.

Both heads and shelves can record 0–120 drive bays. Bay numbers start at 1. Select a bay in the device form to toggle **Occupied / Empty**, then save the device. The overview shows each bay and totals for occupied, empty and overall capacity. Before reducing the count, mark any occupied bays beyond the new count as empty. Occupancy is manual documentation and is included in device version checks and audit history; it does not query disks or represent health, RAID state or capacity.

The startup migration preserves existing devices, port IDs, assignments and rack placements. Existing devices begin with no recorded drive bays. API updates that omit the new storage fields preserve their current values.

## IPAM placement

Saving an interface IP now attempts registration in the most specific matching IPAM subnet in the active tenant. A popup reports missing networks, conflicts or failed placement while retaining the device save. See [Device, DC Inventory and IPAM integration](inventory-ipam.md) for matching rules, permissions and API details.
