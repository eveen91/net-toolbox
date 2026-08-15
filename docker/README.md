# Running net::toolbox in Docker Desktop (Windows)

This setup is intentionally **not** built from your local copy of the repo.
Every time a container starts (including a plain `docker restart` or
`docker compose restart`), it clones `https://github.com/eveen91/net-toolbox`
fresh via `git clone` and builds/runs from that. So you always get whatever
is currently on the `main` branch on GitHub — no rebuilding the Docker image
needed to pick up new commits.

Two containers, matching the project's own frontend/backend split:

- **backend** — clones the repo, `pip install`s `server/requirements.txt`,
  runs `uvicorn main:app` on port **8000**. Also includes `iputils-ping`
  (needed for the IPAM autodiscovery ping sweep — `python:3.12-slim` doesn't
  ship a `ping` binary by default) and a `dns:` setting pointed at your LAN
  router (needed so reverse-DNS lookups for hostnames like `pc.home` resolve
  the same way they did on your VM — see "Hostname resolution" below).
- **frontend** — clones the repo, `npm ci`, `npm run build` (pointed at the
  backend via `VITE_API_BASE_URL`), serves the static build on port
  **3000**.

The SQLite database (`server/toolbox.db`) is the one thing that must survive
the repo being wiped and re-cloned on every start. The backend container
symlinks `server/toolbox.db` to `/data/toolbox.db`, and `/data` is a named
Docker volume (`net-toolbox-data`) — so your routing tables / IPAM data
persist across restarts, rebuilds, and even `docker compose down` (as long
as you don't also pass `-v`).

## Prerequisites

- Docker Desktop for Windows, with the WSL2 backend (default in current
  versions) — nothing extra to configure.
- Internet access from containers (default Docker Desktop networking already
  allows this).

## Setup

1. Put these four files in a folder on your machine, e.g.
   `C:\docker\net-toolbox\`:
   - `Dockerfile`
   - `entrypoint.sh`
   - `docker-compose.yml`
   - `.env.example` (copy to `.env` — you'll want to set `ROUTER_IP`, see below)

2. Copy `.env.example` to `.env` and set `ROUTER_IP` to your router's LAN IP
   (e.g. `192.168.1.1` — find it on Windows via `ipconfig` → "Default
   Gateway"). This is what makes hostname resolution work; see "Hostname
   resolution" below for why.

3. Open a terminal (PowerShell) in that folder and run:

   ```powershell
   docker compose up -d --build
   ```

4. Open the app:
   - Frontend: http://localhost:3000
   - Backend health check: http://localhost:8000/api/health

## Day-to-day use

- **Pick up the latest commit from GitHub:**

  ```powershell
  docker compose restart
  ```

  (or just restart the containers from Docker Desktop's UI). This re-runs
  the entrypoint script, which re-clones the repo from scratch — no rebuild
  needed, since the `git clone` happens at container start, not at image
  build time.

- **Stop it:**

  ```powershell
  docker compose down
  ```

  Your database is untouched (it lives in the `net-toolbox-data` volume,
  not in the container).

- **Wipe the database and start clean:**

  ```powershell
  docker compose down -v
  ```

- **View logs** (handy since the clone/build steps print progress):

  ```powershell
  docker compose logs -f
  ```

- **Track a branch other than `main`, or a fork:** create a `.env` file
  (copy `.env.example`) next to `docker-compose.yml`:
  ```
  REPO_URL=https://github.com/eveen91/net-toolbox.git
  BRANCH=main
  ```
  then `docker compose up -d --build` again.

## Hostname resolution (autodiscovery / reverse DNS)

The IPAM autodiscovery scan pings a subnet, then does a reverse-DNS lookup
on whatever answers, to show names like `pc.home` next to each IP. That
lookup just asks whatever DNS server is in the container's `/etc/resolv.conf`.

By default, Docker Desktop containers go through Docker's own internal DNS
proxy, which may not end up asking your router — and your router is usually
the thing that knows about `pc.home`-style local hostnames (from DHCP
leases). This is different from running the app directly on a VM on your
LAN, where the OS's resolver was probably pointed straight at the router.

Fix: `docker-compose.yml`'s `backend` service sets `dns:` to `${ROUTER_IP}`,
read from your `.env` file. Set it once and rebuild:

```
ROUTER_IP=192.168.1.1
```

```powershell
docker compose up -d --build
```

You can confirm it landed with:

```powershell
docker compose exec backend cat /etc/resolv.conf
```

it should show your router's IP as the `nameserver`. If reverse-DNS still
comes back empty for devices you know have local names, the router itself
may not be answering PTR queries for them (some routers only do forward
lookups) — that's a router-side limitation, not something to fix in Docker.

## Notes / things worth knowing

- Each restart re-installs npm/pip dependencies too (since the whole repo
  folder is wiped and re-cloned), so a restart takes maybe 15–40 seconds
  depending on your connection rather than being instant. If you'd rather
  have instant restarts and only fetch new code when you ask for it, say so
  and I can change the entrypoint to `git pull` an already-cloned copy
  instead of a full re-clone each time — trade-off is that "download newest
  version on every restart" becomes "download newest version only when you
  trigger it."
- The backend's CORS policy is wide open (`allow_origins=["*"]`) and its SSH
  host-key policy auto-accepts unknown hosts — the project's own README
  flags both as fine for local/internal use but worth tightening before
  exposing this beyond your machine.
- The Connection Test tool needs to reach whatever SSH/WinRM hosts you point
  it at _from inside the backend container_. On Docker Desktop for Windows
  that's usually fine for anything reachable from your machine's network,
  but if you're testing hosts on an isolated VLAN, make sure the container's
  network can actually reach them.
- If you'd rather run this as a single container instead of two, or put
  Nginx in front instead of the built-in `serve`, that's a quick change to
  this same entrypoint script — just let me know.
