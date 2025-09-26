#!/usr/bin/env bash
set -euo pipefail

# Quick rebuild and prune build caches

echo "[rebuild] Bringing down existing containers..."
docker compose down

echo "[rebuild] Pruning build cache and dangling images..."
# Remove build cache first (before building)
docker builder prune -f
# Remove dangling images
docker image prune -f

echo "[rebuild] Building and starting containers..."
docker compose up -d --build

echo "[rebuild] Final cleanup..."
# Final cleanup after build
docker builder prune -f
docker image prune -f

echo "[rebuild] Done."


