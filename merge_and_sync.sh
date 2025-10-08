#!/usr/bin/env bash
set -euo pipefail

echo "===================================="
echo "  合并 main 分支并同步版本"
echo "===================================="

# 检查当前分支
CURRENT_BRANCH=$(git branch --show-current)
echo "当前分支: $CURRENT_BRANCH"

if [ "$CURRENT_BRANCH" != "dev/chrismk" ]; then
    echo "错误: 当前分支不是 dev/chrismk"
    echo "请先切换到 dev/chrismk 分支"
    exit 1
fi

# 检查工作区是否干净
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "错误: 工作区有未提交的更改"
    echo "请先提交或暂存当前更改"
    git status
    exit 1
fi

# 获取最新代码
echo "获取最新代码..."
git fetch origin

# 合并 main 分支
echo "合并 main 分支..."
git merge origin/main --allow-unrelated-histories || {
    echo "合并失败，请手动解决冲突后继续"
    exit 1
}

# 版本同步功能
echo "执行版本同步..."

# 获取 main 分支的最新版本
MAIN_VERSION=$(git show origin/main:astrbot/core/config/default.py | grep 'VERSION = ' | sed 's/VERSION = "\(.*\)"/\1/' || echo "")

if [ -z "$MAIN_VERSION" ]; then
    echo "警告: 无法获取 main 分支的版本号，跳过版本同步"
else
    # 获取当前分支的版本
    CURRENT_VERSION=$(grep 'VERSION = ' astrbot/core/config/default.py | sed 's/VERSION = "\(.*\)"/\1/')
    echo "main 分支版本: $MAIN_VERSION"
    echo "当前分支版本: $CURRENT_VERSION"
    
    if [ "$MAIN_VERSION" != "$CURRENT_VERSION" ]; then
        echo "更新版本号从 $CURRENT_VERSION 到 $MAIN_VERSION..."
        
        # 更新版本号
        sed -i "s/VERSION = \"$CURRENT_VERSION\"/VERSION = \"$MAIN_VERSION\"/" astrbot/core/config/default.py
        sed -i "s/version = \"$CURRENT_VERSION\"/version = \"$MAIN_VERSION\"/" pyproject.toml
        
        # 提交版本更新
        git add astrbot/core/config/default.py pyproject.toml
        if ! git diff --cached --quiet; then
            git commit -m "chore: bump version to $MAIN_VERSION to sync with main"
            echo "版本同步已提交"
        fi
    else
        echo "版本已经同步，无需更新"
    fi
fi

echo "合并和版本同步完成"
echo "当前版本:"
grep 'VERSION = ' astrbot/core/config/default.py || echo "无法获取版本信息"

echo ""
echo "下一步操作:"
echo "1. 测试代码是否正常运行"
echo "2. 推送更改: git push origin dev/chrismk"
echo "3. 在服务器上执行: ./rebuild.sh"
