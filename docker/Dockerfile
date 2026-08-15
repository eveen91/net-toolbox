# One image, two roles (backend / frontend), selected at runtime by entrypoint.sh
# via the ROLE environment variable set in docker-compose.yml.
#
# The app's source code is NOT copied in at build time. entrypoint.sh clones it
# fresh from GitHub every time the container starts, so `docker compose restart`
# (or recreating the container) always picks up the latest commit.

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        nodejs \
        npm \
        iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# Static file server for the built frontend (this is a generic tool, not
# app code, so baking it into the image is fine even though app code itself
# is always re-cloned).
RUN npm install -g serve

WORKDIR /app

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]