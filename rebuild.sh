#!/usr/bin/env bash
set -euo pipefail

echo "===================================="
echo " 重建 AstrBot 服务 (仅后端容器)"
echo "===================================="

# 解析项目根目录与 Compose 文件路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"
COMPOSE_FILE="${PROJECT_ROOT}/compose.yml"

echo "使用配置文件: ${COMPOSE_FILE}"

# 先下线服务（可选）
echo "[rebuild] 停止并移除现有容器..."
docker compose -f "${COMPOSE_FILE}" down || true

# 预清理，确保缓存不会干扰本次构建
echo "[rebuild] 预清理构建缓存与悬空镜像..."
docker builder prune -f || true
docker image prune -f || true

# 仅构建并更新 AstrBot 后端服务
echo "[rebuild] 构建 astrbot 服务镜像..."
docker compose -f "${COMPOSE_FILE}" build astrbot

echo "[rebuild] 启动 astrbot 服务..."
docker compose -f "${COMPOSE_FILE}" up -d astrbot

# 收尾清理
echo "[rebuild] 收尾清理构建缓存..."
docker builder prune -f || true
docker image prune -f || true

echo "[rebuild] 完成。"


