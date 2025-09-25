#!/usr/bin/env bash
set -euo pipefail

# Quick rebuild and prune build caches

echo "[rebuild] Bringing down existing containers..."
docker compose down

echo "[rebuild] Building and starting containers..."
docker compose up -d --build

echo "[rebuild] Pruning build cache and dangling images..."
# Remove build cache
docker builder prune -f
# Remove dangling images created during rebuild
docker image prune -f

echo "[rebuild] Done."


