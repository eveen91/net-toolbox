# Bake app source into image for deployment security (avoids runtime cloning).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g serve

WORKDIR /app

# Copy dependency files first to leverage Docker build cache
COPY server/requirements.txt ./server/
RUN pip install --no-cache-dir -r server/requirements.txt
COPY package.json package-lock.json ./
RUN npm ci

# Copy the actual source code
COPY . .

# Build the frontend
RUN npm run build

# Set up database symlinks at entrypoint
ENV ROLE=backend
ENTRYPOINT ["/app/docker/docker-entrypoint.sh"]
