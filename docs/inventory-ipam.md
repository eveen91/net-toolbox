# Device, DC Inventory and IPAM integration

## Saving an interface IP

Saving an IP address in Device Visualization automatically attempts IPAM placement after the interface save succeeds. The lookup uses the address itself, stripping any prefix (for example, `10.20.3.7/24` becomes `10.20.3.7`). It searches only the active tenant and chooses the most specific containing subnet.

If no IPAM record exists, placement creates a **used**, **static**, **physical** address with the device name and interface description. If an existing used record is found, its fields are preserved. An unlocked free record is marked used, filling only missing hostname, description and machine-type fields. Reserved or locked free records are reported as conflicts. Existing metadata is preserved. Network/broadcast addresses, DHCP pools and active range reservations are respected, including ranges defined in a parent subnet.

When no network contains the address, a popup explains that **hardware was not placed in IPAM**. IPv6 addresses also receive a popup because IPAM currently supports IPv4 only. The interface save is retained. The popup offers retry, which can be used after creating the required subnet in another tab or resolving a conflict.

Interface saving and IPAM placement are separate operations. Failure or insufficient permissions for IPAM does not undo the saved hardware configuration. Registration is version-checked, idempotent, and transactionally includes IPAM and device audit entries. Concurrent registration of the same address cannot create duplicate records.

The integration does not automatically create subnets. Changing or clearing an interface IP removes its live hardware link from the previous IP, but retains the previous IPAM address record for explicit review or release. Deleting hardware likewise does not implicitly delete IPAM documentation.

## Opening hardware from IPAM

Select an address in the heatmap or address table. Its details include **DC Inventory**, listing matching device interfaces and their current DC, rack and U position. Select a hardware link to open DC Inventory at the device's current rack with the device highlighted and scrolled into view. Unplaced devices open the **Unassigned** view filtered by device name.

Links are derived from current documented interface IPs, with or without a prefix, rather than hostname matching. They are also available for devices whose IPAM entries predate this integration. Multiple matching interfaces/devices are listed separately, with pagination. Location data is read live, so moving a device does not require updating its IPAM record.

## Permissions and tenant scope

- Automatic placement requires `device-visualization` and `ipam.write` (or legacy `ipam`, or `*`). A denied placement is reported in the popup.
- Reading hardware links requires `ipam.read` and `dc-inventory`. The UI hides the section without DC Inventory access; the backend independently enforces both permissions.
- Existing tenant access checks and CSRF protection apply. Records from another tenant are never searched or modified.
- No new role permission or dependency installation is required.

## API

- `POST /api/device-visualization/devices/{deviceId}/ports/{portId}/ipam-placement` with `{ "expectedVersion": 3 }`. The version must match the current device. Possible result statuses: `created`, `existing`, `no_subnet`, `no_address`, `unsupported`, `conflict`. API clients assigning IPs directly should invoke this endpoint after a successful interface save.
- `GET /api/ipam/inventory-links?address=10.20.3.7&limit=25&offset=0` returns `{ items, total, limit, offset }` with current device locations and port names. `limit` is capped at 100.
- `#/dc-inventory?device=123` opens a device location in the current tenant. The device and rack are resolved through authorized DC Inventory endpoints.

## Creating hardware from an IPAM address

Open the details of a recorded IPAM address and select **Hardware inventory → Add device**. The dialog reuses the Device Visualization form and prefills the device name from the hostname and its description from the address notes. Configure its device type and physical ports, then choose **Dedicated MGMT port** or **First data port** for the source IP. On a storage head, the management option uses Controller A. Storage shelves and passive cable panels are unavailable because they have no IP-capable ports.

The same form supports device height, data center, rack and starting U. Rack assignment is optional; equipment without a rack appears under Unassigned. Saving creates the device, its ports, the IP assignment and placement in one transaction, including audit entries. The source IPAM record is marked used, its existing metadata is preserved, and a missing hostname is populated. Any failure rolls back the entire operation. The dialog retains the configuration after a failure and confirms discarding unsaved changes when cancelled.

Creation requires both `ipam.write` and `device-visualization` access. The source address must be unlocked and unchanged since opening the dialog. If a device already documents that IP, the action is disabled; the backend independently rejects duplicate claims, including concurrent creation attempts. The existing device's inventory link can be used instead. Addresses in DHCP pools, active range reservations and special network/broadcast positions cannot be used for this operation.

API: `POST /api/ipam/addresses/{addressId}/hardware` with `{ "expectedUpdatedAt": "<source updatedAt>", "ipPort": "management", "device": { ...DeviceCreate } }`. The endpoint returns the created DeviceDetail with HTTP 201. `ipPort` may also be `data`. All identifiers are resolved in the active tenant.

## Choosing an existing IPAM address for a device port

In Device Visualization, open a network port and select **Choose from IPAM** beside **IP address**. Choose a subnet, search its recorded addresses by IP/hostname/description, or filter by Free, Used or Reserved status. Each result shows its subnet, status, lock flag and hostname. Results are loaded in pages of 25; the picker does not enumerate every possible address in a subnet. When the port already has an IPv4 address, the most specific containing subnet is selected initially.

Selecting a result fills the interface IP field and returns focus to it. It does not save or reserve the address. **Save assignment** performs the existing interface save and IPAM placement flow. Reserved/locked entries retain their existing IPAM protections; any placement conflict is reported by that flow. Manual IPv4/IPv6 input, including an optional prefix, remains available. The picker is hidden without `ipam.read`, legacy `ipam`, or `*` access and uses the existing authorized IPAM endpoints in the active tenant. SAS expansion ports do not expose an IP field.
