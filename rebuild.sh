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

# 检查 compose.yml 是否配置为本地构建
echo "[rebuild] 检查 compose.yml 配置..."
if grep -q "image: soulter/astrbot" "${COMPOSE_FILE}"; then
    echo "错误: compose.yml 配置为使用远程镜像 'soulter/astrbot'"
    echo "这将导致使用官方镜像而不是本地代码构建"
    echo ""
    echo "请修改 compose.yml，将:"
    echo "  image: soulter/astrbot:latest"
    echo "改为:"
    echo "  build:"
    echo "    context: ."
    echo "    dockerfile: Dockerfile"
    echo "  image: astrbot:local"
    echo ""
    exit 1
fi

if ! grep -q "build:" "${COMPOSE_FILE}"; then
    echo "警告: compose.yml 中未找到 'build:' 配置"
    echo "请确认是否正确配置了本地构建"
    read -p "是否继续? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "✓ compose.yml 配置检查通过"

# 拉取最新代码
echo "[rebuild] 拉取最新代码..."
git pull || {
    echo "警告: git pull 失败，继续使用当前代码"
}

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


