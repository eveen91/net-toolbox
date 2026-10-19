# Tenants in net::toolbox

A tenant is the organization or customer data boundary for the entire application.
User accounts are global and can belong to multiple tenants, with a different
role in each. DC and VRF remain future structures within a tenant.

## Usage

1. Log in as a platform administrator (`admin`).
2. Open **Administration → Tenants** and create a tenant.
3. Select it in **Manage access for tenant** in the panel.
4. In the same panel, assign an existing account and role. Create new accounts
   under **Users** and permission templates under **Roles**.

`admin` is the platform administrator role: it manages accounts, roles and all
tenants. `tenant-admin` manages existing members of its tenant and has full access
to its tools; it does not receive platform administration access. The platform
administrator grants initial access to other accounts. Custom roles retain their
previous module permissions, but apply within the assigned tenant. Changing a
role template affects all memberships using that template.

## Data and compatibility

- `server/auth.db`: global accounts, sessions, settings, roles, tenants,
  memberships and audit records for tenant creation and access changes.
- `server/toolbox.db`: existing data, assigned without copying to the
  **Domyślny** (Default, `default`) tenant.
- `server/tenants/<UUID>/toolbox.db`: a new tenant's data. Set the parent directory
  with `TENANT_DATA_ROOT`.
- Docker sets `TENANT_DATA_ROOT=/data/tenants` in a persistent volume.

During the initial migration, existing accounts retain their roles in the default
tenant. This migration runs once: restarting does not restore revoked memberships.
New local accounts and the existing AD flow receive initial membership in the
default tenant. New AD accounts recognized solely through a group-to-tenant
assignment do not receive this additional membership. Changing an account's former
role updates that membership only if it still matches the former role; independent
tenant assignments are preserved.

IPAM (including settings, tags, archive and audit), routing, devices,
Device Visualization (switches, firewalls, NICs, ports and history), diagnostics
audit and validation data use the active tenant's database. Subnets, addresses
and device names can be repeated across tenants. Browser-only calculators do not
require a separate database and use the account's global permissions.

Mode without login retains open access only to the default tenant. Other tenants
always require a session and permissions. Logged-in accounts are subject to
membership checks even when the global login requirement is disabled.

## API and new modules

`X-Tenant-ID` selects the tenant; omitting the header retains `default` for
compatibility with existing API clients. SSE streams use the `tenant_id` parameter
because native EventSource does not send custom headers. Both selectors undergo
the same server-side session and current membership checks. File paths are
resolved from the registry and UUID, never from a client-supplied name.

The frontend stores the selection separately in each browser tab. Switching
tenants revalidates the session and unmounts tools, clearing their local state
and SSE connections.

New modules that persist data should use `db.get_connection()` or the shared
`tenancy.context.database_path` resolver, and their initialization must be added
to `tenancy.service.initialize_tenant`. Never switch the global `DB_PATH` during
requests. Threads require `tenancy.context.run_in_executor`, and platform tasks
need an explicit `tenant_scope`. The IPAM scheduler iterates over registered
tenants; jobs inherit the correct context.

## Migrations, backup and recovery

Application startup initializes/migrates modules in every registered database.
Tenant creation publishes the registry entry only after schemas are created
successfully; an ordinary error removes the incomplete directory and rolls back
the entry. An abrupt process interruption can leave an unregistered UUID
directory; it is neither exposed nor automatically attached to the application.

Before upgrading, back up `auth.db`, `toolbox.db` and the entire `TENANT_DATA_ROOT`
directory. The simplest consistent backup is made with the backend stopped.
The SQLite Backup API can copy individual live databases, but a consistent set
of multiple databases requires paused writes or a coordinated snapshot.
See the [server maintenance procedure](maintenance.md) for backup examples and
post-upgrade checks. Recovery must preserve UUIDs and consistency between the
registry and directories. Do not restore a tenant database under another tenant's ID.

There is no automatic tenant deletion or cross-tenant reporting. Separate files
provide an application data boundary; the backend and host administrator still
have access to all files. They are not separate processes or system accounts.

### Moving Routing Map hosts

Select a saved host in Routing Map, use **Move to tenant**, choose the destination,
then **Review move** and **Confirm move**. This moves existing hosts from
“Domyślny” (Default), including routes and interfaces. A logged-in account with
Routing Map access in both tenants is required. Moving preserves the save date
and removes the host from the source; an existing destination host with the same
name blocks the operation. Data changes after preview require another review.
The operation is audited in both tenants. The host block is also removed from
the local import field so a subsequent save does not recreate it in the source.

Data and audit records are saved in one SQLite transaction spanning three files.
Moving requires DELETE/TRUNCATE/PERSIST journal mode in all participating
databases; WAL mode is rejected because SQLite does not guarantee atomicity
across multiple files in that mode ([SQLite ATTACH](https://www.sqlite.org/lang_attach.html)).

### Moving IPAM networks

In subnet details, use **Move to tenant → Review move → Confirm move**.
A logged-in account with `ipam.write` (or `ipam`/`*`) in both tenants is required.
The selected subnet moves with its entire child subnet tree, metadata, addresses,
tags and assignments, DHCP, range reservations, scan exclusions, scan history and
completed jobs. Record IDs are allocated in the destination database and
relationships are remapped accordingly. A parent network outside the moved tree
remains in the source.

A range conflict with any destination network, a tag with the same name and
different metadata, an active scan of an overlapping range, or a data change after
preview blocks the move. Scan schedules move as **disabled**; they can be enabled
again in the new tenant. Archived deleted records and muted data quality checks
remain in the source. Audit history is copied to the destination; its original
and a move record remain in the source. The operation also appears in both
tenants' audit logs. All data and audit changes form a single transaction with
the same SQLite journal mode requirements as Routing Map moves.

## Device Visualization

[Device Visualization](device-visualization.md) stores data in the active tenant's
database. The `device-visualization` permission is granted through membership
roles; it is not automatically added to existing roles. The module covers
switches, Check Point/FortiGate firewalls and generic servers. Backups of all
tenant databases include its data and audit records.

## User and group access

The platform administrator selects a tenant in **Administration → Tenants →
Manage access for tenant**. This selection controls permission management and
does not change the tools' active tenant in the top bar. Assign a role to a
specific user in the accounts section; assign a role to a group under **Group
access**. Role templates and module permissions are still defined under **Roles**.

**Administration → Groups** supports local and AD groups:

- **Local**: the platform administrator adds and removes members. Existing local
  or AD accounts can be assigned. Membership alone does not grant access; the
  group must have a role in the relevant tenant.
- **Active Directory**: enter a name and full group DN. The application does not
  manage directory membership. Groups assigned to tenants are checked during AD
  authentication, including nested membership. The members view shows accounts
  recognized at their last authentication, rather than a complete directory
  listing. Users should log in through AD again after a new group is assigned.

Without an individual assignment, permissions from all matching groups within a
tenant are combined. **An individual role takes precedence and replaces the
entire set of group permissions**. Removing the individual role restores group
permissions; it does not necessarily revoke all access. To revoke access, remove
all its sources. To restrict an individual user who belongs to a group, assign a
role with a narrower permission set in that tenant.

Existing assignments, including automatic account membership in the **Domyślny**
(Default) tenant, are preserved and take precedence over groups. Remove the
individual assignment to use group inheritance in that tenant. A global
administrator still has access to all tenants. A `tenant-admin` role granted
through a group does not grant platform administration or the right to create
groups or grant tenant access to groups.

Changes to local groups, group assignments, individual roles and permission
templates are read on every request. The application learns of AD membership
changes only at the next AD authentication; until then, the last verified state
applies. An incorrect password or LDAP outage is not evidence of leaving a group.
New AD groups without tenant assignments do not expand the AD login gate.

Groups, local memberships, tenant assignments and the latest AD observations are
stored in `auth.db`. Migration adds tables without changing existing data. Group
and assignment changes are audited in the same transaction; global group history
is under **Groups**, and changes affecting a specific tenant also appear under
**Tenants**. Deleting a group removes its memberships and all tenant assignments
while preserving audit records.

New endpoints:

- `/api/admin/access-groups` — search and create groups; delete via `/{id}`.
- `/api/admin/access-groups/{id}/members` — members; PUT/DELETE `/{userId}` for local groups only.
- `/api/admin/access-groups/accounts` and `/audit` — paginated account selection and group history.
- `/api/tenants/{tenantId}/group-access` — group assignments; PUT/DELETE `/{groupId}` for platform administrators only.

Global group, member, account selection and group history lists default to 25
items per page (maximum 100). AD observations are not accepted from the browser;
only the backend writes them after verifying credentials.
