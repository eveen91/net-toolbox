# Server updates and maintenance

This procedure covers system package upgrades (`apt upgrade`) and restarting
net::toolbox. Changing the application version may also trigger migrations at
backend startup, so back up the data before starting the new version for the
first time.

## Impact of system packages

| Packages | Relevance to the project | Post-upgrade checks |
|---|---|---|
| `python3.13`, `libpython3.13-*`, `python3.13-venv` | Backend interpreter and standard library; the local `venv` may use the system interpreter through a symlink | Interpreter version, imports and API startup |
| `libsqlite3-0` | Application, account and tenant databases through `sqlite3` | Database integrity and data reads |
| `libssl3t64`, `openssl`, `openssl-provider-legacy` | TLS and cryptographic components; dependencies may also use libraries bundled in their packages | AD/LDAPS login, HTTPS and SSH connections in use |
| `libc6`, `libc-bin` | System libraries used by the interpreter and native extensions | Restart application processes and check logs |
| `linux-image-amd64` | Host kernel | Reboot the host, check network access and restart the application |
| `bind9-*`, `dhcpcd-base`, `curl`, `libcurl*` | DNS/HTTP tools and host network configuration | DNS, host address and device access |
| `tzdata` | System time zones | Correct displayed dates; application timestamps are stored in UTC |

Upgrading within the same Python release series usually allows the existing
`venv` to be retained. Packages installed through `pip` are not upgraded by `apt`.
After changing series, e.g. 3.13 → 3.14, prepare a new environment and verify
dependencies. Do not combine a routine system upgrade with an unplanned upgrade
of all `pip` packages. See the [Python venv documentation](https://docs.python.org/3.13/library/venv.html)
for environment behavior.

A check on 2026-10-12 for the local host identified Debian 13 upgrades:
Python `3.13.5-2+deb13u4 → deb13u5`, SQLite `3.46.1-7+deb13u1 → deb13u2`,
OpenSSL `3.5.6 → 3.5.7`. Dependency imports worked before the upgrade.
This records an assessment of a specific package set; it does not confirm system
health after upgrading or define permanent project requirements.

## Before upgrading

1. Review proposed changes with `apt list --upgradable` and `apt-cache policy`.
2. Check how the backend and frontend server are started. A manually launched
   `uvicorn` command does not provide automatic startup after reboot.
   `ipam-scan-all.timer` starts the scan client, not the API server.
3. Wait for scans and cross-tenant data moves to finish. Pause external jobs that
   write to the databases and the scan timer, if used. Stop all backend processes
   through their normal management mechanism.
4. Create a consistent backup of the data below and retain the startup
   configuration, including `TENANT_DATA_ROOT` and the code version in use.

### Local installation backup

Include `server/auth.db`, `server/toolbox.db` and the entire tenant directory
with UUIDs. The default is `server/tenants`; determine custom paths from backend
configuration. Do not assume service environment variables exist in the current
shell.

Bash example, from the repository root, **after stopping all processes that write
to the databases**. Adjust the backup and tenant directories. Do not use this
variant on paths that are symlinks to a Docker volume.

```bash
set -euo pipefail
umask 077
backup_dir="/var/backups/net-toolbox/$(date -u +%Y%m%dT%H%M%SZ)"
tenant_data_dir="${TENANT_DATA_ROOT:-$PWD/server/tenants}"
mkdir -p "$backup_dir"
cp -a server/auth.db server/toolbox.db "$backup_dir/"
# Also preserve existing journal files, e.g. after an unexpected shutdown.
for database_file in server/auth.db server/toolbox.db; do
  for suffix in -wal -shm -journal; do
    if [ -f "${database_file}${suffix}" ]; then
      cp -a "${database_file}${suffix}" "$backup_dir/"
    fi
  done
done
if [ -d "$tenant_data_dir" ]; then
  cp -a "$tenant_data_dir" "$backup_dir/tenants"
fi
```

A missing tenant directory is normal if only the default tenant exists. If the
registry contains other tenants, missing files must be investigated before the
backup can be considered complete. The backup contains accounts, sessions and
authentication configuration; restrict access to it.

Copying live files with `cp` is not an online backup procedure. The
[SQLite Backup API](https://www.sqlite.org/backup.html) provides a valid copy of
one database, but successive copies of multiple databases do not guarantee a
shared point in time. To keep the tenant registry and data moves consistent,
pause writes while taking the entire backup set or use a coordinated storage
snapshot.

### Docker installation

Data resides in the `net-toolbox-data` volume: `/data/auth.db`, `/data/toolbox.db`
and `/data/tenants/<UUID>/toolbox.db`. Stop the backend
(`docker compose -f docker/docker-compose.yml stop backend`) and archive the
**entire volume**, preserving directory structure and permissions. A custom
`TENANT_DATA_ROOT` outside this volume requires a separate backup.

Upgrading host packages does not upgrade libraries inside an existing image.
To update those libraries, rebuild the image from an updated base, then recreate
containers while preserving the data volume.

## Upgrade and startup

Run the planned `apt update` and `apt upgrade`, and review configuration and
service restart messages. Restart the backend after changes to Python, OpenSSL
or libc. After a kernel upgrade, reboot the host to load the new kernel. Ensure
both backend and frontend start after reboot.

For a manually launched backend, from the repository root:

```bash
cd server
./venv/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

For a service-managed deployment, use its actual service name and preserve its
environment variables. The repository does not define a universal systemd
service to start the backend. Resume paused timers only after checking the API.

## Post-upgrade checks

Run the following commands from the repository root. They do not modify data:

```bash
server/venv/bin/python3 -c 'import sys, sqlite3, ssl; print(sys.version); print("SQLite", sqlite3.sqlite_version); print(ssl.OPENSSL_VERSION)'
server/venv/bin/python3 -c 'import fastapi, uvicorn, paramiko, netmiko, bcrypt, cryptography, ldap3, winrm; print("Backend imports: OK")'
curl --fail --show-error http://127.0.0.1:8000/api/health
```

The expected health response is `{"status":"ok"}`. It confirms API process
availability; it does not check databases, tenant permissions or device
connections. For containers, check imports inside the backend container.

Also check:

- startup logs: no import, database initialization or migration errors;
- integrity of **every** database: `PRAGMA integrity_check` should return `ok`,
  and `PRAGMA foreign_key_check` should return no rows;
- local and AD/LDAPS login, if configured;
- tenant switching and access to expected IPAM and Routing Map data;
- data isolation and ordinary user permissions;
- SSH/WinRM/HTTPS connections and DNS in use, including device access;
- IPAM schedules: no unexpected scans or startup errors.

Run integrity checks in SQLite read-only mode against the actual files resolved
from the registry and configuration. Opening an incorrect path normally can
create an empty database and conceal the mistake. Do not use real network or
host moves as a technical test; use test data.

Cross-tenant data moves require SQLite DELETE/TRUNCATE/PERSIST journal mode in
all participating databases. Do not switch them to WAL as part of a routine
upgrade. Details: [tenants and data moves](tenants.md).

## Troubleshooting

First check the interpreter version, `venv` path, configuration and logs. When
changing Python release series, build a separate environment from
`server/requirements.txt` and verify it before switching the backend. A
deprecation warning alone does not indicate an import failure or API outage.

If data recovery is necessary, stop all writers and also preserve a copy of the
failed state. Restore the entire consistent set of `auth.db`, `toolbox.db` and
tenant directories with their original UUIDs, preserving permissions for the
backend's system account. Do not mix databases from different points in time or
leave WAL/journal files from another state. Use an application version compatible
with the restored schema; backend startup may run migrations again. Perform the
checks above before resuming writes.
