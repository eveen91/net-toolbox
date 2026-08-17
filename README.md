# net::toolbox

A small multi-tool networking app. The main shell (toolbar + home page) is separate
from every tool, and each tool lives in its own folder under `src/tools/`.

## Features

### Core Tools

#### Subnet Splitter
Carve a network into the largest CIDR blocks around excluded ranges. Pure client-side computation — no backend required.

#### Connection Test
SSH/WinRM into source servers and test TCP connectivity to destinations.
- **Linux sources**: SSHes in (`paramiko`, username/password) and runs a remote bash loop that tries `/dev/tcp/$DST/$PORT` for every destination:port
- **Windows sources**: Opens WinRM sessions (`pywinrm`, username/password) and runs PowerShell `TcpClient.BeginConnect`/`EndConnect` tests
- Configurable WinRM transport (NTLM / Kerberos / Basic / CredSSP), scheme (http/https), and port via "Advanced settings"
- Returns results as JSON + CSV export

#### Routing Map
Browse each host's routing table by network and next hop.
- Paste/edit routes in draft textarea (`@hostname`, then `network -> next hop` per line)
- Save to SQLite database with validation (CIDR networks, IP addresses)
- View saved hosts list with route counts
- Load from database for editing
- API endpoints: `GET/PUT/DELETE /api/routing/hosts`, `GET /api/routing/export`

#### IP Calculator
Enter an IP and netmask to get the network, broadcast, and usable host range. Pure client-side computation.

#### IPAM (IP Address Management)
Track subnets with VLAN tags and record used, free, and reserved IP addresses.
- Dashboard view of all subnets with utilization bars
- Add/edit/delete subnets with CIDR, VLAN ID, description
- Track individual IP addresses with status (used/free/reserved), hostname, description, team, machine type (physical/VM), VM cluster, environment (prod/test/dev)
- Bulk edit addresses
- Autodiscovery scan: ping sweep + reverse DNS lookup for live hosts
- Scan exclude lists to skip reserved/locked addresses during autodiscovery
- Settings for default ping timeout/attempts and DNS timeout

### Authentication & Authorization

#### User Management
- Local user authentication with bcrypt-hashed passwords
- Session-based auth with configurable timeout
- Optional login requirement (can run in open mode)
- Password change functionality for logged-in users

#### Role-Based Access Control
- Custom roles with granular permissions per tool
- Admin role with full access (`*` permission) to all tools plus Config Panel
- Default "user" role seeded with all tool permissions
- Assign/revoke roles per user

#### Active Directory Integration
- Direct bind authentication (no stored service account credentials)
- User Principal Name (UPN) based login
- Required group membership for access control
- Admin group membership detection for elevated privileges
- Transitive group membership resolution (nested groups)
- TLS support for LDAPS connections
- Connection testing endpoint for AD configuration validation

### Admin Panel

#### Configuration
- Bootstrap admin user on first setup
- Toggle login requirement on/off
- Configure Active Directory settings (host, port, TLS, domain suffix, required/admin group DNs)
- Test AD connection before saving

#### User & Role Management
- List/create/update/delete users
- Assign roles to users
- Reset user passwords
- Create/update/delete custom roles
- Manage role permissions (tool-level access)

### Docker Support

Full Docker Compose setup for Windows/Docker Desktop:
- Backend container (Python/FastAPI on port 8000)
- Frontend container (React/Vite build served on port 3000)
- Auto-updates from GitHub on every container restart
- Persistent SQLite database volume
- Configurable router DNS for reverse-DNS lookups in IPAM autodiscovery
- See [`docker/README.md`](docker/README.md) for full setup instructions

## Run it

**Frontend**

```bash
npm install
npm run dev
```

Then open the printed local URL.

**Backend** (required for Connection Test, Routing Map, IPAM, and authentication):

```bash
cd server
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

In dev, `vite.config.js` proxies `/api` to `http://localhost:8000` automatically.
In production, put a reverse proxy in front that does the same, or set
`VITE_API_BASE_URL` to the backend's full URL when building the frontend.

The Subnet Splitter and IP Calculator tools need no backend — they're pure client-side computation.

**Docker** (Windows / Docker Desktop, auto-updating from GitHub)

```powershell
cd docker
copy .env.example .env    # then set ROUTER_IP in it
docker compose up -d --build
```

Runs the frontend on `:3000` and backend on `:8000`, pulls the latest commit
from this repo on every container restart, and persists `toolbox.db` in a
named volume. See [`docker/README.md`](docker/README.md) for the full setup,
troubleshooting, and how to track a different branch or fork.

## Project layout

```
docker/
  Dockerfile                    # backend/frontend image (role picked via ROLE env var)
  entrypoint.sh                 # re-clones this repo from GitHub on every container start
  docker-compose.yml            # backend + frontend services, persistent DB volume
  .env.example                  # ROUTER_IP / REPO_URL / BRANCH overrides
  README.md                     # full Docker setup + troubleshooting guide
src/
  App.jsx                       # shell only: toolbar + routing between home/tools
  index.css                     # theme, toolbar, home page, tool-header styles
  components/
    Toolbar.jsx                 # top nav, reads the tool list from the registry
  pages/
    HomePage.jsx                # tool card grid, reads the tool list from the registry
  admin/
    AdminPanel.jsx              # user/role management, AD settings, app configuration
    AdminGate.jsx               # guards admin routes behind auth + admin role check
    AdminLoginForm.jsx          # initial admin bootstrap login form
    CreateAdminForm.jsx         # first-time admin user creation
    api.js                      # admin API calls (users, roles, settings)
    admin.css                   # admin panel styles
  auth/
    AuthContext.jsx             # React context for session/user state
    LoginPage.jsx               # local login form
    ChangePasswordForm.jsx      # change own password
    SessionExpiredModal.jsx     # notifies on 401/session expiry
    api.js                      # auth API calls (login/logout/session)
    auth.css                    # auth component styles
  tools/
    registry.js                 # the single list of tools shown in the toolbar/home page
    shared.css                  # panel/field/button/table/pill styles common to every tool
    subnet-splitter/
      SubnetSplitter.jsx        # UI for the tool
      logic.js                  # pure subnetting functions (no React), ported from the .ps1
      subnet-splitter.css       # styles unique to this tool (the address-space bar)
    connection-test/
      ConnectionTest.jsx        # UI for the tool
      logic.js                  # input parsing + CSV export (no React)
      api.js                    # talks to the backend's /api/connection-test/run
      connection-test.css       # styles unique to this tool (credential grid, advanced panel)
    routing-map/
      RoutingMap.jsx            # UI for the tool — host list + selected host's route table
      logic.js                  # parses pasted "@host / network -> next hop" blocks (no React)
      routing-map.css           # styles unique to this tool (the host list)
    ip-calculator/
      IpCalculator.jsx          # UI for the tool — network/broadcast/host range calculator
      logic.js                  # IP/netmask parsing and calculation (no React)
      ip-calculator.css         # styles unique to this tool
    ipam/
      Ipam.jsx                  # main IPAM view with address list and editing
      IpamDashboard.jsx         # dashboard showing all subnets with utilization bars
      SubnetSearch.jsx          # search/filter subnets by VLAN or CIDR
      AddSubnetForm.jsx         # create new subnet form
      api.js                    # IPAM API calls (subnets, addresses, scans, settings)
      logic.js                  # formatting helpers, ancestor chain for hierarchy
      ipam.css                  # IPAM-specific styles (utilization bar, address table)
server/
  main.py                       # FastAPI backend: SSHes into Linux sources (paramiko),
                                # WinRMs into Windows sources (pywinrm), runs TCP checks,
                                # serves Routing Map and IPAM endpoints, handles auth
  db.py                         # SQLite persistence for IPAM (subnets, addresses, scans)
  auth_db.py                    # SQLite auth database (users, sessions, roles, settings)
  auth.py                       # password hashing (bcrypt) utilities
  ldap_auth.py                  # Active Directory direct-bind authentication
  ipam_scan.py                  # ping sweep + reverse DNS for IPAM autodiscovery
  toolbox.db                    # created automatically on first run — not committed
  auth.db                       # created automatically on first run — not committed
  requirements.txt
```

## Adding a new tool

1. Create `src/tools/<your-tool>/YourTool.jsx` (plus its own `.css` / `logic.js` if it
   needs them — keep everything the tool needs inside its own folder). Reach for the
   shared classes in `tools/shared.css` (`tool-panel`, `tool-input`, `tool-btn`,
   `tool-table`, `tool-pill-*`, etc.) before inventing new ones — only give the tool
   its own CSS file for what's actually unique to it.
2. Import the component in `src/tools/registry.js` and add one entry to the `TOOLS`
   array (`id`, `name`, `icon`, `tagline`, `status: "live"`, `Component`).

The toolbar and home page both read from `registry.js`, so nothing else needs to change.

## Connection Test — how it reaches each source

- **Linux sources**: the backend SSHes in (`paramiko`, username/password) and runs a
  remote bash loop that tries `/dev/tcp/$DST/$PORT` for every destination:port, same
  approach as the original `connection_test.sh`.
- **Windows sources**: the backend opens a WinRM session (`pywinrm`, username/password)
  and runs the PowerShell `TcpClient.BeginConnect`/`EndConnect` equivalent from the
  original `connection_test.ps1`. WinRM transport (NTLM / Kerberos / Basic / CredSSP),
  scheme (http/https), and port are all configurable in the tool's "Advanced settings".

## Routing Map — storage

Routing tables (a host, and its list of `{network in CIDR, next hop}` routes) are
persisted in a SQLite database at `server/toolbox.db`, created automatically the
first time the backend starts — no setup needed, it's just a file.

Workflow in the UI:
- Paste/edit routes in the "draft" textarea (`@hostname`, then `network -> next hop`
  per line), then **Save to database** — this validates each network as CIDR and each
  next hop as an IP address server-side, and upserts every host found in the draft.
- The **saved hosts** list below it is the actual database contents — click a host to
  view its routes (fetched fresh from the database), or **Delete host** to remove it.
- **Load from database** pulls everything currently saved back into the draft textarea
  for editing.

API (all under `/api/routing/`):

| Method | Path | Does |
|---|---|---|
| GET | `/hosts` | List saved hosts with route counts |
| GET | `/hosts/{host}` | One host's full routing table |
| PUT | `/hosts/{host}` | Replace a host's routes (upserts the host) |
| DELETE | `/hosts/{host}` | Remove a host and its routes |
| GET | `/export` | All hosts with full routes, in one call |

**Why SQLite**: this is a single-server internal tool with modest data volume and
mostly read traffic (browsing routes) — SQLite needs no separate database process to
run or manage, the whole database is one file to back up or move, and it comfortably
handles this workload. If this ever needs multiple backend processes writing
concurrently, or grows well beyond routing tables, Postgres is the natural upgrade —
the data model in `db.py` wouldn't need to change, just the storage layer.

The table isn't wired up to live hosts yet. The natural next step is reusing the
SSH/WinRM machinery Connection Test already has to populate it by running
`ip route`/`route -n` (Linux) or `Get-NetRoute` (Windows) instead of typing routes in
by hand.

## IPAM — storage & scanning

Subnets and their IP addresses are persisted in a separate SQLite database at
`server/db.py` (distinct from auth data). Each subnet tracks VLAN ID, description,
and a list of addresses with status (used/free/reserved), hostname, team, machine
type, VM cluster, environment, and lock state.

**Autodiscovery scan**: when triggered on a subnet, the backend:
1. Enumerates all usable host addresses in the CIDR, minus scan excludes
2. Pings each address (configurable timeout/attempts via settings)
3. For live hosts, performs reverse DNS lookup for hostname
4. Updates the database with alive status and resolved hostnames

Scan jobs stream progress via Server-Sent Events (`/api/ipam/subnets/{id}/autodiscover/stream/{job_id}`).

API highlights (all under `/api/ipam/`):
- `GET/POST /subnets` — list/create subnets
- `GET/PUT/DELETE /subnets/{id}` — fetch/update/delete a subnet
- `POST /subnets/{id}/addresses` — add an address
- `PUT/DELETE /subnets/{id}/addresses/{addrId}` — edit/remove an address
- `PATCH /subnets/{id}/addresses/bulk` — bulk update addresses
- `POST /subnets/{id}/autodiscover` — start a ping+DNS scan
- `GET /subnets/{id}/scan-excludes` — list excluded addresses
- `POST/DELETE /subnets/{id}/scan-excludes` — manage exclude list
- `GET /dashboard` — summary view of all subnets with utilization

## Authentication & Authorization

**Auth database**: user credentials, sessions, roles, and app settings live in
`server/auth.db`, deliberately separate from application data (`toolbox.db`).

**Local authentication**:
- Passwords hashed with bcrypt before storage
- Session tokens issued on login, stored with expiry
- Configurable session timeout via admin settings
- Optional login requirement (app can run in open mode)

**Active Directory authentication**:
- Direct bind using typed credentials (no service account stored)
- Supports UPN format (`user@domain`) or plain username + domain suffix
- Required group DN restricts access to AD group members
- Admin group DN grants elevated privileges
- Transitive group membership resolution (nested groups via `memberOf:1.2.840.113556.1.4.1941`)
- LDAPS support with certificate validation
- Connection test endpoint validates AD configuration before saving

**Role-based access control**:
- Custom roles with per-tool permissions (`subnet-splitter`, `connection-test`, etc.)
- Admin role (`*` permission) bypasses all tool restrictions
- Default "user" role seeded with all tool permissions
- Users assigned exactly one role
- Tool visibility filtered by `visibleTools()` based on user's role permissions

Admin API endpoints (all under `/api/admin/`):
- `POST /bootstrap` — create first admin user
- `GET/POST /users`, `PATCH /users/{id}/role`, `DELETE /users/{id}` — user management
- `GET/POST /roles`, `PUT/DELETE /roles/{id}` — role management
- `PUT /settings/require-login` — toggle login requirement
- `GET/PUT /settings/ad`, `POST /settings/ad/test-connection` — AD configuration

**Security notes**

- Credentials entered in the UI are sent to the backend for that run only and are not
  stored or logged anywhere.
- Credentials travel from the browser to the backend as plain JSON — put the backend
  behind HTTPS (a reverse proxy is the easiest way) before using this anywhere other
  than localhost.
- The backend's CORS policy (`allow_origins=["*"]`) and SSH host-key policy
  (`AutoAddPolicy`) are permissive defaults meant for getting started — tighten both
  before running this somewhere production-adjacent.