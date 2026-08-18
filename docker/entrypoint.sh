#!/bin/bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/eveen91/net-toolbox.git}"
BRANCH="${BRANCH:-main}"
APP_DIR="/app"

echo ">>> [$ROLE] Cloning ${REPO_URL} (branch: ${BRANCH}) ..."
# cd out of APP_DIR before deleting it - deleting your own cwd leaves the
# shell (and anything it execs, like git) unable to resolve getcwd(),
# which makes git fail with "Unable to read current working directory".
cd /
rm -rf "${APP_DIR}"
git clone --depth 1 --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
cd "${APP_DIR}"
echo ">>> [$ROLE] Now on commit: $(git rev-parse --short HEAD)"

if [ "${ROLE}" = "backend" ]; then
    # --- persistent SQLite database -----------------------------------
    # The repo is deleted and re-cloned on every start, so anything that
    # needs to survive a restart must live outside /app. /data is backed
    # by a named Docker volume (see docker-compose.yml). We symlink the
    # app's expected db path to the persistent location instead of
    # patching the source.
    mkdir -p /data
    touch /data/toolbox.db
    ln -sf /data/toolbox.db "${APP_DIR}/server/toolbox.db"
    echo ">>> [backend] toolbox.db -> /data/toolbox.db (persistent volume)"

    touch /data/auth.db
    ln -sf /data/auth.db "${APP_DIR}/server/auth.db"
    echo ">>> [backend] auth.db -> /data/auth.db (persistent volume)"

    echo ">>> [backend] Installing Python dependencies ..."
    pip install --no-cache-dir -r server/requirements.txt

    echo ">>> [backend] Starting API on :8000 ..."
    cd server
    exec uvicorn main:app --host 0.0.0.0 --port 8000

elif [ "${ROLE}" = "frontend" ]; then
    echo ">>> [frontend] Installing dependencies ..."
    npm ci

    echo ">>> [frontend] Building with VITE_API_BASE_URL=${VITE_API_BASE_URL:-<same-origin>} ..."
    npm run build

    echo ">>> [frontend] Serving dist/ on :3000 ..."
    exec serve -s dist -l 3000

else
    echo "ERROR: ROLE must be 'backend' or 'frontend' (got '${ROLE:-<unset>}')" >&2
    exit 1
fi