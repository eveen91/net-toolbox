# DC Inventory

DC Inventory documents data centers, racks and device positions in rack units (U).
It uses the same devices as [Device Visualization](device-visualization.md):
it does not create a second inventory or copy ports. Moving a device preserves
its ID, NICs, controllers, MGMT, IP addresses, VLANs and connection destinations.

## Permissions and tenants

The module requires the `dc-inventory` permission. An administrator must explicitly
grant it to existing roles; administrators with `*` have access automatically.
The `device-visualization` permission alone does not allow users to manage data
centers and racks. It does expose a read-only location catalog through the Device
Visualization API so users can select locations for their devices. DC Inventory
can place existing devices; their ports and configuration are edited in Device
Visualization.

Data, locations and audit records belong to the active tenant. The API uses
`X-Tenant-ID`; rack and device IDs from other tenants do not form a shared catalog.

## Data centers, racks and devices

1. Create a data center, then a rack with a capacity of 1–100U.
2. In **Unassigned**, select an existing device and **Assign to rack**.
3. Enter the device height, data center, rack and **Starting U (bottom)**.
   Confirm with **Save placement**.
4. The rack view shows occupied and free units. Selecting a device or
   **Move / unassign** opens the placement editor; selecting no rack unassigns it.

U1 is at the bottom. The starting unit is inclusive: a 2U device starting at U3
occupies U3–U4, and its highest unit is `rackPosition + heightU - 1`.
Device height is an integer from 1–100U. The data center is derived from the
selected rack; selecting a center without a rack does not save a separate DC
assignment. A rack remains in the data center chosen when it was created.

Existing devices initially remain unassigned with an unknown height, displayed
as **Not recorded**. The UI requires a height when saving the device or placement
form; the editor's initial value must not be treated as a previously recorded
height. Port data remains unchanged.

Data center names are unique within a tenant, and rack names within a data
center, without case sensitivity. **Unassigned** supports device search and
shows 25 items per page. **History** provides changes with before and after data.

## Cable management panels

Select a rack and **Add cable management panel (1U)**. Enter a name and starting
unit; the default name includes the rack and position. A Rackmount Cable
Management Panel is a passive item in the shared inventory, always occupies 1U,
and has no network ports or MGMT. It appears in Rack elevation and Device
Visualization. Use the same placement editor to move it; name editing and
deletion are available in Device Visualization. Shared rack occupancy rules and
change history apply.

`POST /api/dc-inventory/cable-panels` requires `dc-inventory` and the fields `name`,
`rackId`, `rackPosition` (optionally `description`). The server sets the type and
height. Device Visualization permission is not required just to add a panel.
Names are unique within the tenant's shared device inventory.

## Rack connections

Open **Connections** after choosing a rack. The diagram shows its equipment at the
recorded U positions, connections within the rack, and directly connected racks
(including other data centers in the active tenant). Equipment without a rack
appears in a separate unassigned column. Cable management panels remain passive
rack items and cannot be cable endpoints.

Use **Add connection** to select a device and free port in the current rack, then
search for the destination device and select its port. The destination can be in
any rack or unassigned. An optional cable label identifies the connection. This
creates an explicit undirected port-to-port relationship; existing **Leads to**
text is retained and is never automatically matched to devices or converted into
cables. The diagram documents saved cabling, not live link status or traffic flow.

Select a cable in the diagram or connection list to highlight both devices and
see full device, port, data center, rack and U details. **Open source rack** or
**Open destination rack** switches to the peer's rack. **Fit racks** shows the
complete layout; **100%** and zoom preserve access to readable labels through
scrolling. The full endpoint list remains readable and keyboard-accessible even
when Fit makes the drawing small. **Show connections for** filters to a device.

Connections are paginated at 20 per page (API maximum 50). The diagram and list
show the same page; the count states the full number of matches. Peer racks are
direct neighbors represented by those connections, rather than a recursive graph
of the entire tenant. Rack diagrams include all equipment installed in each
shown rack. Moving or renaming a device updates the next graph read without
changing its cable endpoints.

A port can belong to only one physical cable. Writes check both device versions
and reserve both ports in one transaction, including audit records. Concurrent
claims or stale selections are rejected; the form retains selections and offers
**Reload ports**. Connecting or disconnecting increments both device versions,
so a previously open device or placement editor may need a reload.

**Disconnect cable → Confirm disconnect** removes only the relationship and
retains devices, port settings and **Leads to** notes. Removing a connected port
or NIC in Device Visualization requires the existing loss preview and explicit
confirmation. Confirmed port/device deletion also removes its cables, frees the
other endpoints and records `endpoint_removed` in inventory history. Explicit
connect/disconnect operations also appear in both devices' histories. Data and
audit writes roll back together on failure.

Device Visualization also supports selecting a destination device and port from
**Leads to**. That workflow creates the same physical cables and reciprocal notes,
with a state-bound confirmation before replacing occupied endpoints. See
[device/port selection](device-visualization.md#choosing-a-leads-to-destination).
The inventory's direct Add connection/Disconnect actions retain their existing
behavior of preserving free-text notes.

The existing `dc-inventory` permission covers graph access, minimal port choices
and cable management; it does not grant the full Device Visualization API.
Everything is scoped to the active tenant. Restarting the backend adds the
`dc_connections` table, indexes and cleanup triggers idempotently; no new
application dependencies or separate database are required.

## Data protection

Saving rejects overlapping U ranges and devices extending beyond rack capacity.
A rack cannot be reduced below its highest occupied unit. All devices must be
moved or unassigned before a rack can be deleted; all racks must be removed before
a data center can be deleted. Deleting an empty location requires confirmation.

Updates and deletions compare `expectedVersion` with the current version. After
a conflict, reload the data and review the placement. Placement shares the device
version with Device Visualization, so a concurrent port edit can invalidate an
already open placement form. Saving, version updates and audit writes are atomic;
a placement change in DC Inventory appears in both device and inventory history.
Saving without changes does not increment the version. Range protection is also
enforced in the database.

## API

Prefix: `/api/dc-inventory`.

| Method and path | Purpose |
| --- | --- |
| `GET /datacenters`, `POST /datacenters` | List and create data centers |
| `PUT /datacenters/{id}`, `DELETE /datacenters/{id}` | Edit or delete a data center |
| `GET /racks`, `POST /racks` | List and create racks |
| `GET /racks/{id}`, `PUT /racks/{id}`, `DELETE /racks/{id}` | Rack contents, editing or deletion |
| `GET /devices` | Shared devices; filters: `unassigned`, `rackId`, `query` |
| `PUT /devices/{id}/placement` | Place an existing device |
| `GET /racks/{id}/connections` | Rack graph; `deviceId`, `limit` (1–50, default 20), `offset` |
| `GET /devices/{id}/ports` | Minimal port choices, occupancy and device version |
| `POST /connections` | Create a physical port pair |
| `DELETE /connections/{id}` | Confirm and remove a cable relationship |
| `GET /audit` | Inventory history |

Lists use `limit` (1–100) and `offset`; `/racks` also accepts `dataCenterId`.
A data center accepts `name` and optional `description`; a new rack additionally
requires `dataCenterId` and `heightU`. Editing requires `expectedVersion`; DELETE
also requires `confirmDelete: true` in the JSON body. Placement accepts
`expectedVersion`, `rackId`, `rackPosition`, `heightU`. Omitted placement fields
retain their values; `rackId: null` unassigns the device and clears its starting
unit. Rack assignment requires a height and starting unit. The API remains
compatible with older clients that omit location fields in Device Visualization.

Connection creation accepts `sourcePortId`, `targetPortId`, `sourceVersion`,
`targetVersion` and optional `label` (up to 100 characters). The endpoints must
belong to two different devices. Deletion accepts `expectedVersion` and
`confirmDelete: true`. A busy port returns HTTP 409 with `detail.code` set to
`port_connected`; stale device selections return `stale_version`. Minimal port
choices return a device summary and at most 130 ports, including `connectionId`;
they do not expose IP/VLAN or free-text destination configuration.

HTTP 409 includes `stale_version`, `placement_conflict`, `rack_too_small`,
`location_not_empty` and `confirmation_required` in `detail.code`. Invalid
operations return 400, invalid payloads 422, missing resources 404, and an
unavailable or busy database 503. The read-only Device Visualization catalog is at
`GET /api/device-visualization/inventory/datacenters` and
`GET /api/device-visualization/inventory/racks`.

## Updates and maintenance

Restarting the backend automatically and idempotently upgrades existing tenant
databases: it creates `dc_datacenters`, `dc_racks`, `dc_audit`, location fields in
`dv_devices` and U range protection. New tenants receive the same schema.
No new dependencies, separate database or volume are required. Tenant database
backups include the inventory and shared devices; see [server maintenance](maintenance.md).
