# net::toolbox

`net::toolbox` is a multi-tool networking application designed for network engineers and system administrators. It combines client-side utility calculators with backend-powered automation for remote connectivity testing, routing table management, IP address management (IPAM), and multi-vendor switch/gateway troubleshooting.

The application features a clean, modular shell (top toolbar + card grid home page) supporting session-based local authentication, Active Directory (LDAP/LDAPS) integration, role-based access control (RBAC), and containerized Docker deployment.

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Features & Core Tools](#features--core-tools)
   - [Subnet Splitter](#subnet-splitter)
   - [Connection Test](#connection-test)
   - [Routing Map](#routing-map)
   - [IP Calculator](#ip-calculator)
   - [IPAM (IP Address Management)](#ipam-ip-address-management)
   - [Troubleshoot](#troubleshoot)
3. [Authentication & Access Control](#authentication--access-control)
   - [Local & Active Directory Auth](#local--active-directory-auth)
   - [Role-Based Access Control (RBAC)](#role-based-access-control-rbac)
   - [Security & Credential Handling](#security--credential-handling)
4. [Admin Panel](#admin-panel)
5. [Installation & Setup](#installation--setup)
   - [Local Development](#local-development)
   - [Docker & Docker Compose](#docker--docker-compose)
   - [Automated Scanning (Systemd)](#automated-scanning-systemd)
6. [API Reference Catalog](#api-reference-catalog)
7. [Database Schemas](#database-schemas)
8. [Environment Variables](#environment-variables)
9. [Project Layout](#project-layout)
10. [Adding a New Tool](#adding-a-new-tool)
11. [Testing](#testing)

---

## Architecture Overview

`net::toolbox` is structured around a decoupled frontend and backend architecture:

- **Frontend**: Single Page Application (SPA) built with **React 18** and **Vite**. Navigation is handled via top-level state management (`App.jsx`), avoiding router overhead. Each tool lives isolated in its own folder under `src/tools/` and registers with `src/tools/registry.js`.
- **Backend**: Async **FastAPI** application running under **Uvicorn**. Provides REST APIs, background task polling, Server-Sent Events (SSE) streaming for long scans, SSH (`paramiko`/`netmiko`), and WinRM (`pywinrm`) remote execution.
- **Data Persistence**: Uses two isolated **SQLite** databases:
  - `server/toolbox.db`: Application data (Routing tables, IPAM subnets/addresses, Device inventory, Troubleshoot audit logs).
  - `server/auth.db`: Authentication data (User accounts, bcrypt hashes, active sessions, custom roles, AD configurations, app settings). Kept strictly separate so credentials never coexist with application data.

---

## Features & Core Tools

### Subnet Splitter
Carve a network CIDR block into the largest valid subnets around specified excluded IP ranges or addresses.
- **Execution**: Pure client-side computation in JavaScript — no backend required.
- **Capabilities**:
  - Interactive address-space visualizer bar.
  - Automatically calculates non-overlapping CIDR blocks covering remaining usable space.
  - Useful for subnet planning around static allocations or legacy hardware.

### Connection Test
Test TCP port connectivity from remote Linux or Windows source hosts to target destinations.
- **Execution**: Backend-assisted (`POST /api/connection-test/run`).
- **Source Host Support**:
  - **Linux Sources**: Backend connects via SSH (`paramiko`) using session credentials and runs a remote bash loop executing `/dev/tcp/$DST/$PORT`.
  - **Windows Sources**: Backend connects via WinRM (`pywinrm`) using session credentials and runs PowerShell `TcpClient.BeginConnect`/`EndConnect` checks.
- **Configuration & Settings**:
  - Configurable WinRM transport (`NTLM`, `Kerberos`, `Basic`, `CredSSP`), scheme (`http`/`https`), and WinRM port.
  - Results returned directly with JSON rows and CSV export.
- **Security**: Credentials are provided per session and are never logged or persisted.

### Routing Map
Store, view, and organize routing tables across infrastructure hosts.
- **Execution**: Backend-assisted with SQLite persistence (`/api/routing/*`).
- **Capabilities**:
  - **Text Parser**: Paste raw route dumps formatted as `@hostname` followed by `network -> next_hop` or `network directly connected <interface>`.
  - Server-side validation of CIDR networks and IP next hops.
  - Search and filter hosts, view route counts per host, edit routes in draft format, or delete hosts.
  - Export full global routing database via `/api/routing/export`.

### IP Calculator
Quick IP address and subnet calculation tool.
- **Execution**: Pure client-side computation in JavaScript.
- **Outputs**: Network address, Broadcast address, Usable Host IP range, Total host capacity, Wildcard mask, and Netmask in dotted-decimal format.

### IPAM (IP Address Management)
Full-featured IP address and subnet management system.
- **Execution**: Backend-assisted (`/api/ipam/*`) with SQLite storage (`server/db.py`).
- **Capabilities**:
  - **Subnet Management**: Hierarchical parent/child subnet trees, VLAN ID assignment, CIDR tracking, description.
  - **Dashboard**: High-level overview of subnet utilization bars (used, free, reserved counts).
  - **Address Tracking**:
    - Status: `used`, `free`, `reserved`.
    - Metadata: Hostname, description, team, machine type (`physical`/`VM`), VM cluster, environment (`prod`/`test`/`dev`), locked state.
    - Bulk operations: Bulk edit status/metadata, bulk delete, bulk move addresses between subnets.
  - **Autodiscovery Scanner**:
    - Ping sweep + reverse DNS lookup across subnet host IPs (`server/ipam_scan.py`).
    - Exclude lists (`scan-excludes`) to skip gateways, static ranges, or network devices.
    - Configurable scan settings (ping timeout, attempts, DNS timeout, max concurrency limit).
    - Server-Sent Events (SSE) progress streaming (`/autodiscover/stream/{job_id}`).
    - Diff detection against previous scans (newly responsive IPs, hosts going quiet, hostname changes).
    - Single IP re-scan on demand.

### Troubleshoot
Multi-vendor network device diagnostic and lookup suite.
- **Execution**: Backend-assisted (`/api/troubleshoot/*`) using `netmiko` and vendor-specific drivers.
- **Supported Platforms**:
  - Cisco IOS-XE (`cisco_ios`)
  - Aruba AOS-CX (`aruba_aoscx`)
  - Checkpoint Gaia (`checkpoint_gaia`)
- **Sub-Tabs & Capabilities**:
  - **Inventory**: Device inventory management (Management IP, Vendor, Model, OS Version, Device Type). Note: Exactly one gateway device (e.g. Checkpoint Gaia) must be designated for ARP/route lookups.
  - **Full Diagnostic**: Sequential automated workflow: IP lookup -> Gateway ARP table -> Switch MAC table locate -> Port health -> Cable test (optional) -> Optical transceiver health -> Port access status -> Gateway ping -> Route check.
  - **Locate**: Traces IP to MAC address on gateway ARP table, then searches connected switch MAC tables to identify the physical access port.
  - **Port Health**: Inspects link status, operational speed, duplex mode, input/output errors, CRC errors, and packet drops.
  - **Cable Test (TDR)**: Triggers Time-Domain Reflectometry test on switch port (requires explicit UI confirmation due to momentary link interruption).
  - **Optics Health**: Reads SFP/XFP transceiver Digital Optical Monitoring (DOM) values (Tx/Rx optical power, temperature, voltage, bias current) against vendor thresholds.
  - **Port Access Status**: Checks 802.1X, MAB (MAC Authentication Bypass), and port-security authorization state.
  - **Reachability**: Remote ping execution and route table query against network devices.
  - **STP Report**: Inventory-wide Spanning Tree Protocol scan identifying switch ports experiencing recent topology change flaps.
  - **Activity Log**: SQLite audit logging of all CLI commands issued to network hardware.

---

## Authentication & Access Control

### Local & Active Directory Auth
`net::toolbox` supports two authentication modes configured via the Admin Panel:
1. **Open Mode** (`require_login = false`): All tools remain accessible without login.
2. **Login Required** (`require_login = true`): Users must authenticate via local account or Active Directory.

- **Local Accounts**: Passwords hashed with `bcrypt` and stored in `auth.db`.
- **Active Directory (LDAP/LDAPS)**:
  - Direct bind authentication via `ldap3` (no service account stored).
  - Supports User Principal Name (`user@domain`) or plain username + domain suffix.
  - Enforces required Group DN for access control.
  - Supports LDAPS with TLS certificate verification.
  - Group membership resolved transitively (supporting nested AD groups via `memberOf:1.2.840.113556.1.4.1941`).

### Role-Based Access Control (RBAC)
- **Roles**: Custom defined roles with granular per-tool permissions (`subnet-splitter`, `connection-test`, `routing-map`, `ip-calculator`, `ipam`, `troubleshoot`).
- **Admin Role**: Built-in reserved `admin` role with wildcard (`*`) permission granting full access to all tools and the Config Panel.
- **Default User Role**: Seeded `user` role with access to all tools except Troubleshoot (granted by an admin when needed).
- **Active Directory Group Mapping**:
  - Custom roles can be bound to one or more AD group DNs (`role_ad_groups` table).
  - On first AD login, user AD groups are matched against role group bindings to assign the appropriate role automatically.
  - Account roles for AD-sourced users are locked to prevent manual override.

### Security & Credential Handling
- **Per-Session Credentials**: SSH, WinRM, and network device passwords entered in tools are used strictly in memory for the duration of the request/job and are **never** logged, cached, or written to disk.
- **TLS Requirement**: Production deployments should place the backend behind an HTTPS reverse proxy (e.g., Nginx, Caddy, Traefik) to protect credentials in transit.
- **SSH Host-Key Verification**: Outbound SSH connections (Connection Test Linux sources and all Troubleshoot device drivers) verify host keys and **reject unknown hosts**. Trusted keys are read from `~/.ssh/known_hosts` and `server/known_hosts`. To trust a new host, run `ssh-keyscan -H <host> >> server/known_hosts` on a machine you trust.
- **WinRM TLS Verification**: Connection Test Windows sources validate the WinRM server's TLS certificate (no longer ignore it). To trust self-signed/internal WinRM hosts, set `WINRM_CA_TRUST_PATH` to a CA bundle containing your internal issuing CA.

---

## Admin Panel

Accessible to users with the `admin` role (or during initial setup before any admin user exists):
- **Bootstrap Administrator**: Create the primary admin account on first installation.
- **User Management**: View user list (Local vs AD badges), create local accounts, assign roles (local accounts only), reset passwords, and delete users.
- **Role & Permission Management**: Create custom roles, update tool permissions, bind/unbind AD group DNs to roles, and delete unused roles.
- **System Settings**: Toggle global `require_login` enforcement.
- **Active Directory Settings**: Configure AD host, port, TLS, domain suffix, required group DN, admin group DN, and execute real-time connection test checks before saving.

---

## Installation & Setup

### Local Development

#### Prerequisites
- Node.js 18+ and npm
- Python 3.12+

#### 1. Frontend Setup
```bash
npm install
npm run dev
```
The Vite development server runs on `http://localhost:5173`. Proxies `/api` calls to `http://localhost:8000` by default.

#### 2. Backend Setup
```bash
cd server
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```
The backend initializes `server/toolbox.db` and `server/auth.db` automatically on first launch.

---

### Docker & Docker Compose

Full containerized setup suitable for Docker Desktop (Windows/Linux/macOS).

#### Architecture
The setup runs two containers configured via `docker/docker-compose.yml`:
- **`backend`**: Python 3.12 container running FastAPI on port `8000`. Includes `iputils-ping` for IPAM sweeps. Mounts persistent named volume `net-toolbox-data` to `/data` (persisting `toolbox.db` and `auth.db`).
- **`frontend`**: Static file server (`serve`) on port `3000` serving Vite production bundle.

The Docker containers clone the repository dynamically on container start, allowing `docker compose restart` to fetch the latest commits without rebuilding images.

#### Deploying with Docker
```bash
cd docker
copy .env.example .env     # Windows PowerShell / CMD
# or: cp .env.example .env # Linux / macOS

# Edit .env and set ROUTER_IP to your default gateway IP (for LAN DNS resolution)
docker compose up -d --build
```
- Frontend UI: `http://localhost:3000`
- Backend API Health: `http://localhost:8000/api/health`

---

### Automated Scanning (Systemd)

To schedule periodic IPAM autodiscovery scans across all subnets:

1. Locate script at `server/scripts/scan_all_subnets.py`.
2. Deploy systemd templates found in `server/scripts/`:
   ```bash
   sudo cp server/scripts/ipam-scan-all.service /etc/systemd/system/
   sudo cp server/scripts/ipam-scan-all.timer /etc/systemd/system/
   ```
3. Edit `/etc/systemd/system/ipam-scan-all.service` to update `WorkingDirectory`, `ExecStart` path, and `IPAM_BASE_URL` if necessary.
4. Enable and start the timer:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now ipam-scan-all.timer
   ```

---

## API Reference Catalog

All backend endpoints are hosted under `/api`.

### System & Authentication
| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/api/health` | Health check | No |
| `POST` | `/api/auth/login` | Authenticate user (Local / AD) | No |
| `POST` | `/api/auth/logout` | Terminate session | Yes |
| `GET` | `/api/auth/session` | Get current user session & permissions | No |
| `POST` | `/api/auth/change-password` | Change password for logged-in user | Yes |

### Admin Management (`admin` role required)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/admin/bootstrap-status` | Check if initial admin user exists |
| `POST` | `/api/admin/bootstrap` | Bootstrap first admin account |
| `GET` | `/api/admin/users` | List all local and AD users |
| `POST` | `/api/admin/users` | Create local user account |
| `PATCH` | `/api/admin/users/{user_id}/role` | Assign role to local user |
| `DELETE` | `/api/admin/users/{user_id}` | Delete user account |
| `POST` | `/api/admin/users/{user_id}/reset-password` | Reset password for local user |
| `GET` | `/api/admin/roles` | List custom roles and AD group bindings |
| `POST` | `/api/admin/roles` | Create new custom role |
| `PUT` | `/api/admin/roles/{role_id}` | Update role permissions |
| `DELETE` | `/api/admin/roles/{role_id}` | Delete role |
| `GET` | `/api/admin/roles/{role_id}/ad-groups` | List bound AD group DNs |
| `POST` | `/api/admin/roles/{role_id}/ad-groups` | Bind AD group DN to role |
| `DELETE` | `/api/admin/roles/{role_id}/ad-groups` | Unbind AD group DN from role |
| `POST` | `/api/admin/settings/require-login` | Toggle global login requirement |
| `GET` | `/api/admin/settings/ad` | Get AD configuration |
| `POST` | `/api/admin/settings/ad` | Save AD configuration |
| `POST` | `/api/admin/settings/ad/test-connection` | Validate AD LDAP connection |

### Connection Test (`connection-test` feature permission required)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/connection-test/run` | Run TCP connectivity checks from all sources (returns rows + CSV) |

### Routing Map (`routing-map` feature permission required)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/routing/hosts` | List saved hosts with route counts |
| `GET` | `/api/routing/hosts/{host}` | Get routing table for host |
| `PUT` | `/api/routing/hosts/{host}` | Save/upsert routing table for host |
| `DELETE` | `/api/routing/hosts/{host}` | Delete host and routing table |
| `GET` | `/api/routing/export` | Export full routing table database |

### Troubleshoot & Device Inventory

These endpoints are not role-gated on the backend — tool visibility is filtered client-side via `visibleTools()`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/devices` | List inventory network devices |
| `POST` | `/api/devices` | Add switch/gateway to inventory |
| `PUT` | `/api/devices/{device_id}` | Update inventory device |
| `DELETE` | `/api/devices/{device_id}` | Remove device from inventory |
| `POST` | `/api/troubleshoot/test-connection` | Test SSH connectivity to a device |
| `POST` | `/api/troubleshoot/locate` | Trace IP -> MAC -> switch port |
| `POST` | `/api/troubleshoot/port-health` | Query port status, speed, errors |
| `POST` | `/api/troubleshoot/cable-test` | Execute TDR cable diagnostic |
| `POST` | `/api/troubleshoot/transceiver-health` | Query SFP DOM optical diagnostic |
| `POST` | `/api/troubleshoot/access-check` | Query 802.1X/MAB auth status |
| `POST` | `/api/troubleshoot/ping` | Execute remote ping from device |
| `POST` | `/api/troubleshoot/route-check` | Query route table on device |
| `POST` | `/api/troubleshoot/stp-report` | Scan inventory for STP topology changes |
| `POST` | `/api/troubleshoot/run` | Execute full multi-step diagnostic workflow |
| `GET` | `/api/troubleshoot/audit-log` | Retrieve device execution audit logs |

### IPAM (`ipam` feature permission required)
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/ipam/dashboard` | List all subnets with utilization metrics |
| `GET` | `/api/ipam/settings` | Get scanner configuration settings |
| `PUT` | `/api/ipam/settings` | Save scanner settings |
| `GET` | `/api/ipam/subnets` | List subnets with hierarchy tree |
| `POST` | `/api/ipam/subnets` | Create subnet |
| `GET` | `/api/ipam/subnets/{subnet_id}` | Get subnet detail and recorded IP addresses |
| `PUT` | `/api/ipam/subnets/{subnet_id}` | Update subnet properties |
| `DELETE` | `/api/ipam/subnets/{subnet_id}` | Delete subnet and addresses |
| `POST` | `/api/ipam/subnets/{subnet_id}/addresses` | Record single IP address |
| `PUT` | `/api/ipam/subnets/{subnet_id}/addresses/{address_id}` | Update recorded address |
| `DELETE` | `/api/ipam/subnets/{subnet_id}/addresses/{address_id}` | Delete recorded address |
| `PATCH` | `/api/ipam/subnets/{subnet_id}/addresses/bulk` | Bulk edit address status/metadata |
| `POST` | `/api/ipam/subnets/{subnet_id}/addresses/bulk-delete` | Bulk delete addresses |
| `POST` | `/api/ipam/subnets/{subnet_id}/addresses/bulk-move` | Bulk move addresses to target subnet |
| `POST` | `/api/ipam/subnets/{subnet_id}/addresses/{address_id}/move` | Move a single address to another subnet |
| `POST` | `/api/ipam/subnets/{subnet_id}/addresses/{address_id}/rescan` | Rescan specific IP address |
| `GET` | `/api/ipam/subnets/{subnet_id}/scan-excludes` | List scan exclude rules |
| `POST` | `/api/ipam/subnets/{subnet_id}/scan-excludes` | Add scan exclude rule |
| `DELETE` | `/api/ipam/subnets/{subnet_id}/scan-excludes/{exclude_id}` | Remove scan exclude rule |
| `POST` | `/api/ipam/subnets/{subnet_id}/autodiscover/start` | Launch async autodiscovery scan |
| `GET` | `/api/ipam/subnets/{subnet_id}/autodiscover/active` | Query active scan status |
| `GET` | `/api/ipam/subnets/{subnet_id}/autodiscover/stream/{job_id}` | SSE stream of scan progress |
| `GET` | `/api/ipam/subnets/{subnet_id}/scans` | List scan history for subnet |

---

## Database Schemas

### Application Database (`server/toolbox.db`)

#### `hosts`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique host ID |
| `name` | TEXT | NOT NULL UNIQUE | Hostname |
| `updated_at` | TEXT | NOT NULL | ISO 8601 timestamp |

#### `routes`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Route ID |
| `host_id` | INTEGER | FK -> `hosts.id` ON DELETE CASCADE | Parent host |
| `network` | TEXT | NOT NULL | CIDR block |
| `next_hop` | TEXT | NOT NULL | Next hop IP or `directly connected` |
| `interface` | TEXT | NULL | Egress interface name (migrated column) |

#### `interfaces`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Interface ID |
| `host_id` | INTEGER | FK -> `hosts.id` ON DELETE CASCADE | Parent host |
| `name` | TEXT | NOT NULL | Interface name |
| `ip_address` | TEXT | NOT NULL | Interface IP in CIDR notation |
| `description` | TEXT | NULL | Description |

#### `devices`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Device ID |
| `name` | TEXT | NOT NULL UNIQUE | Hostname/Device name |
| `mgmt_ip` | TEXT | NOT NULL | Management IP address |
| `vendor` | TEXT | NOT NULL | Vendor name |
| `model` | TEXT | NOT NULL | Hardware model |
| `os_version` | TEXT | NULL | OS version string |
| `device_type` | TEXT | NOT NULL | `cisco_ios`, `aruba_aoscx`, or `checkpoint_gaia` |
| `updated_at` | TEXT | NOT NULL | Timestamp |

#### `audit_log`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Audit log ID |
| `device_name` | TEXT | NULL | Target device name |
| `command` | TEXT | NOT NULL | Command executed |
| `username` | TEXT | NULL | Execution user |
| `success` | INTEGER | NOT NULL | `1` for success, `0` for failure |
| `error` | TEXT | NULL | Error message if failed |
| `created_at` | TEXT | NOT NULL | Timestamp |

#### `ipam_subnets`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Subnet ID |
| `cidr` | TEXT | NOT NULL UNIQUE | Subnet in CIDR format |
| `vlan` | INTEGER | NULL | VLAN tag (1-4094) |
| `description` | TEXT | NULL | Subnet description |
| `parent_id` | INTEGER | FK -> `ipam_subnets.id` | Parent supernet ID |
| `updated_at` | TEXT | NOT NULL | Timestamp |

#### `ipam_addresses`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Address record ID |
| `subnet_id` | INTEGER | FK -> `ipam_subnets.id` ON DELETE CASCADE | Subnet ID |
| `address` | TEXT | NOT NULL | IP address |
| `status` | TEXT | NOT NULL | `used`, `free`, or `reserved` |
| `hostname` | TEXT | NULL | Resolved/assigned hostname |
| `description` | TEXT | NULL | Description |
| `team` | TEXT | NULL | Owning team |
| `machine_type` | TEXT | NULL | `physical` or `VM` |
| `vm_cluster` | TEXT | NULL | Hypervisor/VM cluster name |
| `environment` | TEXT | NULL | `prod`, `test`, or `dev` |
| `locked` | INTEGER | DEFAULT 0 | Locked state toggle |
| `updated_at` | TEXT | NOT NULL | Timestamp |

#### `ipam_scan_excludes`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Rule ID |
| `subnet_id` | INTEGER | FK -> `ipam_subnets.id` ON DELETE CASCADE | Subnet ID |
| `address` | TEXT | NOT NULL | IP or CIDR range to skip |

#### `ipam_scans`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Scan job ID |
| `subnet_id` | INTEGER | FK -> `ipam_subnets.id` ON DELETE CASCADE | Subnet ID |
| `started_at` | TEXT | NOT NULL | Start timestamp |
| `finished_at` | TEXT | NOT NULL | Completion timestamp |
| `scanned_count` | INTEGER | NOT NULL | Addresses scanned |
| `used_count` | INTEGER | NOT NULL | Responsive IPs found |
| `free_count` | INTEGER | NOT NULL | Non-responsive IPs |
| `skipped_count` | INTEGER | NOT NULL | Excluded/skipped addresses |
| `newly_used_count` | INTEGER | NOT NULL | IPs newly discovered alive |
| `went_quiet_count` | INTEGER | NOT NULL | IPs previously alive now quiet |
| `hostname_changed_count` | INTEGER | NOT NULL | Hostnames updated |
| `diff_json` | TEXT | NOT NULL | JSON diff of changes vs previous scan |

#### `ipam_settings`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `key` | TEXT | PRIMARY KEY | Setting key |
| `value` | TEXT | NOT NULL | Setting value |

---

### Auth Database (`server/auth.db`)

#### `users`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | User ID |
| `username` | TEXT | NOT NULL | Account username |
| `password_hash` | TEXT | NOT NULL | Bcrypt password hash |
| `role` | TEXT | NOT NULL DEFAULT 'user' | Assigned role name |
| `auth_source` | TEXT | NOT NULL DEFAULT 'local' | `local` or `ad` |
| `created_at` | TEXT | NOT NULL | Timestamp |

*Constraint*: `UNIQUE(username, auth_source)`

#### `sessions`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `token_hash` | TEXT | PRIMARY KEY | SHA-256 hashed session token |
| `user_id` | INTEGER | FK -> `users.id` ON DELETE CASCADE | User ID |
| `created_at` | TEXT | NOT NULL | ISO timestamp |
| `expires_at` | TEXT | NOT NULL | Expiry ISO timestamp |

#### `roles`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Role ID |
| `name` | TEXT | NOT NULL UNIQUE | Role name |
| `permissions` | TEXT | NOT NULL DEFAULT '[]' | JSON list of granted tool permissions |
| `is_builtin` | INTEGER | NOT NULL DEFAULT 0 | 1 for built-in roles (`admin`, `user`), 0 for custom |
| `created_at` | TEXT | NOT NULL | Timestamp |

#### `role_ad_groups`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Mapping ID |
| `role_id` | INTEGER | FK -> `roles.id` ON DELETE CASCADE | Role ID |
| `group_dn` | TEXT | NOT NULL UNIQUE | Active Directory group Distinguished Name |
| `created_at` | TEXT | NOT NULL | Timestamp |

#### `ad_settings`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `key` | TEXT | PRIMARY KEY | Setting key (`enabled`, `host`, `port`, `use_tls`, etc.) |
| `value` | TEXT | NOT NULL | Setting value |

#### `app_settings`
| Column | Type | Constraints | Description |
|---|---|---|---|
| `key` | TEXT | PRIMARY KEY | Setting key (`require_login`) |
| `value` | TEXT | NOT NULL | Setting value |

---

## Environment Variables

| Variable | Scope | Default | Description |
|---|---|---|---|
| `VITE_API_BASE_URL` | Frontend Build | `http://localhost:8000` | Backend base URL for browser API calls |
| `IPAM_BASE_URL` | Scripts (`scan_all_subnets.py`) | `http://localhost:8000` | Target backend URL for CLI subnet scan trigger |
| `ROLE` | Docker | `backend` | Sets container mode (`backend` or `frontend`) |
| `REPO_URL` | Docker | `https://github.com/eveen91/net-toolbox.git` | Git repo cloned on container startup |
| `BRANCH` | Docker | `main` | Git branch target for Docker auto-update |
| `ROUTER_IP` | Docker Compose | `192.168.1.1` | LAN Gateway IP configured for container DNS resolver |
| `CORS_ORIGINS` | Backend | *(empty)* | Comma-separated extra browser origins allowed to call the API (e.g. `http://192.168.1.10:3000`) |
| `COOKIE_SECURE` | Backend | `false` | Set to `true` in HTTPS production deployments to enforce the `Secure` flag on session cookies |
| `TRUST_PROXY_HEADERS` | Backend | `false` | Must be set to `true` (or `1`) when running behind a trusted reverse proxy to trust `X-Forwarded-For` headers for rate limiting |
| `WINRM_CA_TRUST_PATH` | Backend | *(unset)* | CA bundle path used to validate self-signed/internal WinRM host certificates |
| `BOOTSTRAP_SECRET` | Backend | *(unset)* | Optional secret required for initial admin bootstrap if configured |

---

## Project Layout

```
net-toolbox/
├── docker/                     # Docker Compose deployment setup
│   ├── Dockerfile              # Unified Python/Node image
│   ├── docker-compose.yml      # Backend and Frontend services
│   ├── entrypoint.sh           # Dynamic Git clone & execution script
│   ├── .env.example            # Environment variables template
│   └── README.md               # Detailed Docker Desktop guide
├── server/                     # FastAPI backend
│   ├── main.py                 # Core API endpoints & auth dependencies
│   ├── db.py                   # Application SQLite database (toolbox.db)
│   ├── auth_db.py              # Auth SQLite database (auth.db)
│   ├── auth.py                 # Bcrypt password hashing & session management
│   ├── ldap_auth.py            # Active Directory LDAP/LDAPS bind engine
│   ├── ipam_scan.py            # Async ping sweep & DNS resolver engine
│   ├── troubleshoot_devices.py # SQLite device inventory management
│   ├── troubleshoot_logic.py   # Parsing & multi-step diagnostic logic
│   ├── troubleshoot_audit.py   # SQLite audit logging for troubleshoot CLI runs
│   ├── device_drivers/         # Vendor SSH drivers (netmiko wrappers)
│   │   ├── base.py             # DeviceSession context manager
│   │   ├── cisco_ios.py        # Cisco IOS-XE CLI drivers
│   │   ├── aruba_cx.py         # Aruba AOS-CX CLI drivers
│   │   └── checkpoint_gaia.py  # Checkpoint Gaia CLI drivers
│   ├── scripts/                # Automated background scripts
│   │   ├── scan_all_subnets.py # Leaf subnet autodiscovery trigger CLI
│   │   ├── ipam-scan-all.service # Systemd unit template
│   │   └── ipam-scan-all.timer   # Systemd timer template
│   ├── tests/                  # Pytest test suite (18 test modules)
│   ├── conftest.py             # Test fixtures and DB isolation setup
│   └── requirements.txt        # Python package requirements
├── src/                        # React frontend
│   ├── App.jsx                 # Top-level shell and page routing
│   ├── index.css               # Global theme & layout CSS
│   ├── components/             # Global components (Toolbar, Nav)
│   ├── pages/                  # Home page grid
│   ├── admin/                  # Config Panel, user/role management, AD settings
│   ├── auth/                   # Login modal, auth context, password forms
│   └── tools/                  # Pluggable tools directory
│       ├── registry.js         # Single registry array defining all tools
│       ├── shared.css          # Shared tool design system styles
│       ├── subnet-splitter/    # Subnet Splitter component & logic
│       ├── connection-test/    # Connection Test component, API & logic
│       ├── routing-map/        # Routing Map component & logic
│       ├── ip-calculator/      # IP Calculator component & logic
│       ├── ipam/               # IPAM components, dashboard & logic
│       └── troubleshoot/       # Troubleshoot tabs & diagnostic components
├── index.html                  # HTML entry point
├── vite.config.js              # Vite bundler configuration & dev proxy
└── package.json                # Frontend dependencies and npm scripts
```

---

## Adding a New Tool

`net::toolbox` uses a pluggable tool architecture. Adding a tool requires only two steps:

1. Create a new directory under `src/tools/<your-tool>/`:
   - Create `YourTool.jsx` for the React component.
   - (Optional) Include tool-specific `logic.js`, `api.js`, or `<your-tool>.css`. Re-use shared styling classes from `src/tools/shared.css` where possible.
2. Register the tool in `src/tools/registry.js`:
   ```javascript
   import YourTool from "./your-tool/YourTool.jsx";

   export const TOOLS = [
     // ... existing tools ...
     {
       id: "your-tool",
       name: "Your Tool Name",
       icon: "🔧",
       tagline: "Short summary of what your tool does.",
       status: "live",
       Component: YourTool,
     },
   ];
   ```
The top navigation toolbar and home page card grid will automatically render the new tool and apply role-based access filtering.

---

## Testing

The backend includes a unit and integration test suite built with `pytest` and FastAPI `TestClient`.

Run tests:
```bash
cd server
pytest
```
Tests automatically execute in an isolated environment using temporary in-memory/file-backed SQLite databases (`conftest.py`) without affecting production `toolbox.db` or `auth.db` files.
