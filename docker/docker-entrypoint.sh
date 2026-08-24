#!/bin/bash
set -euo pipefail

if [ "${ROLE:-"backend"}" = "backend" ]; then
    # --- persistent SQLite database -----------------------------------
    # App code is now baked in, toolbox.db/auth.db still reside in persistent volume.
    mkdir -p /data
    
    # We must ensure database files exist before linking
    if [ ! -f /data/toolbox.db ]; then touch /data/toolbox.db; fi
    ln -sf /data/toolbox.db "/app/server/toolbox.db"
    
    if [ ! -f /data/auth.db ]; then touch /data/auth.db; fi
    ln -sf /data/auth.db "/app/server/auth.db"
    
    echo ">>> [backend] Starting API on :8000 ..."
    cd server
    exec uvicorn main:app --host 0.0.0.0 --port 8000

elif [ "${ROLE}" = "frontend" ]; then
    echo ">>> [frontend] Serving dist/ on :3000 ..."
    exec serve -s dist -l 3000
else
    echo "ERROR: ROLE must be 'backend' or 'frontend' (got '${ROLE:-<unset>}')" >&2
    exit 1
fi
