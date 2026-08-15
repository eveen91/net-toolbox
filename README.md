# net::toolbox

A small multi-tool networking app. The main shell (toolbar + home page) is separate
from every tool, and each tool lives in its own folder under `src/tools/`.

## Run it

**Frontend**

```bash
npm install
npm run dev
```

Then open the printed local URL.

**Backend** (required for the Connection Test tool — a browser can't open raw
SSH or WinRM sessions itself, so that tool calls a small Python API that does):

```bash
cd server
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

In dev, `vite.config.js` proxies `/api` to `http://localhost:8000` automatically.
In production, put a reverse proxy in front that does the same, or set
`VITE_API_BASE_URL` to the backend's full URL when building the frontend.

The Subnet Splitter tool needs no backend — it's pure client-side computation.

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
  App.jsx                     # shell only: toolbar + routing between home/tools
  index.css                   # theme, toolbar, home page, tool-header styles
  components/
    Toolbar.jsx                # top nav, reads the tool list from the registry
  pages/
    HomePage.jsx                # tool card grid, reads the tool list from the registry
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
      RoutingMap.jsx             # UI for the tool — host list + selected host's route table
      logic.js                   # parses pasted "@host / network -> next hop" blocks (no React)
      routing-map.css            # styles unique to this tool (the host list)
server/
  main.py                      # FastAPI backend: SSHes into Linux sources (paramiko),
                                # WinRMs into Windows sources (pywinrm), runs the TCP
                                # checks remotely, returns results as JSON + CSV.
                                # Also serves the Routing Map endpoints below.
  db.py                        # SQLite persistence for routing tables (hosts + routes)
  toolbox.db                   # created automatically on first run — not committed
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

**Security notes**

- Credentials entered in the UI are sent to the backend for that run only and are not
  stored or logged anywhere.
- Credentials travel from the browser to the backend as plain JSON — put the backend
  behind HTTPS (a reverse proxy is the easiest way) before using this anywhere other
  than localhost.
- The backend's CORS policy (`allow_origins=["*"]`) and SSH host-key policy
  (`AutoAddPolicy`) are permissive defaults meant for getting started — tighten both
  before running this somewhere production-adjacent.