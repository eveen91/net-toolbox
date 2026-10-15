# Routing Map → IPAM

In **Routing Map → Hosts**, select a saved host. Use **Import to IPAM** beside an interface to import its subnet, or **Import all networks to IPAM** for the entire interface list. **Import details** reports the created networks and the reason for every skipped interface. **Open IPAM** opens the target module in the same active tenant.

The server calculates the network from the saved interface address and mask:

- `192.0.2.129/25` → `192.0.2.128/25`;
- `198.51.100.1/24` → `198.51.100.0/24`;
- `/31` and `/32` remain valid networks; dotted-decimal masks are accepted.

IPv6 and addresses without an explicit mask are skipped, with an explanation. Repeated networks are deduplicated; existing IPAM subnets are skipped without changing their metadata. Interface addresses are retained as source information, not inserted as IPAM address records. The import creates subnet records with the host/interface origin and original description, bounded to 500 characters. VLAN IDs are not inferred from interface names.

The saved source is authoritative, including interface entries derived from directly connected routes. The request carries the displayed host's `updatedAt`; a changed source returns HTTP 409 without importing. Use **Reload interfaces** to review the current data before another click.

All eligible subnet insertions, IPAM hierarchy updates and `subnet_create` audit entries share one SQLite transaction. An unexpected storage/audit failure rolls back the entire import. Existing IPAM hierarchy and DHCP-pool reconciliation rules apply when new subnets are added. Concurrent and repeated imports cannot create duplicate subnets. Normal duplicate/unsupported-entry skips are reported individually, rather than treated as storage errors.

Access requires **both** `routing-map` and IPAM write permission (`ipam.write`, legacy `ipam` or `*`) in the active tenant. Default-tenant open mode and the existing CSRF rules remain in force. Source routing data is not moved or modified; newly created subnet records use the same tenant database.

API: `POST /api/routing/hosts/{host}/ipam-import`

```json
{"expectedUpdatedAt":"2026-10-14T12:00:00+00:00","interfaces":["eth0"]}
```

Use `interfaces: null` or omit it to import all saved interfaces (maximum 1,000). The response contains `created`, `skipped`, and a count `summary`. Client-supplied network addresses and alternate target tenant IDs are not accepted.

Find imported networks in **IPAM → Subnets**, nested beneath their containing subnet when one exists. Expand the parent or filter by the imported CIDR or description; matching paths expand automatically and retain ancestors as **Parent context**. The parent's **Child subnets** section also lists its immediate children.
