#!/bin/bash
# 自定义代码完整性检查脚本
# 用于合并 main 分支后验证自定义代码是否完整

echo "🔍 检查自定义代码完整性..."
echo "================================"
echo ""

ERRORS=0

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查函数
check_exists() {
    local description=$1
    local command=$2
    
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✅${NC} $description"
        return 0
    else
        echo -e "${RED}❌${NC} $description"
        ERRORS=$((ERRORS + 1))
        return 1
    fi
}

echo "📱 Telegram 平台检查"
echo "--------------------------------"

check_exists "Telegram CallbackQueryHandler 导入" \
    "grep -q 'from telegram.ext import.*CallbackQueryHandler' astrbot/core/platform/sources/telegram/tg_adapter.py"

check_exists "Telegram CallbackQueryHandler 注册" \
    "grep -q 'CallbackQueryHandler(self.callback_handler)' astrbot/core/platform/sources/telegram/tg_adapter.py"

check_exists "Telegram callback_handler 方法" \
    "grep -q 'async def callback_handler' astrbot/core/platform/sources/telegram/tg_adapter.py"

check_exists "Telegram InlineKeyboard 导入" \
    "grep -q 'InlineKeyboard' astrbot/core/platform/sources/telegram/tg_event.py"

check_exists "Telegram InlineKeyboard 预处理" \
    "grep -q 'isinstance(i, InlineKeyboard)' astrbot/core/platform/sources/telegram/tg_event.py"

check_exists "Telegram InlineKeyboard 发送逻辑" \
    "grep -q 'reply_markup=keyboard_markup' astrbot/core/platform/sources/telegram/tg_event.py"

echo ""
echo "🦅 飞书平台检查"
echo "--------------------------------"

check_exists "飞书 CardService 文件" \
    "test -f astrbot/core/platform/sources/lark/card_service.py"

check_exists "飞书 TokenManager 文件" \
    "test -f astrbot/core/platform/sources/lark/token_manager.py"

check_exists "飞书 CardService 导入" \
    "grep -q 'from .card_service import get_card_service' astrbot/core/platform/sources/lark/lark_adapter.py"

check_exists "飞书 CardService 初始化" \
    "grep -q 'self.card_service = get_card_service' astrbot/core/platform/sources/lark/lark_adapter.py"

check_exists "飞书卡片回调处理器注册" \
    "grep -q 'register_p2_card_action_trigger' astrbot/core/platform/sources/lark/lark_adapter.py"

check_exists "飞书 convert_card_action_msg 方法" \
    "grep -q 'async def convert_card_action_msg' astrbot/core/platform/sources/lark/lark_adapter.py"

check_exists "飞书 edit_message 方法" \
    "grep -q 'async def edit_message' astrbot/core/platform/sources/lark/lark_event.py"

check_exists "飞书 update_card_delayed 方法" \
    "grep -q 'async def update_card_delayed' astrbot/core/platform/sources/lark/lark_event.py"

echo ""
echo "📦 消息组件检查"
echo "--------------------------------"

check_exists "InlineKeyboard 组件类" \
    "grep -q 'class InlineKeyboard(BaseMessageComponent):' astrbot/core/message/components.py"

check_exists "InlineKeyboard 现代类型注解" \
    "grep -q 'buttons: list\[list\[dict\[str, Any\]\]\]' astrbot/core/message/components.py"

check_exists "CardImage 组件类" \
    "grep -q 'class CardImage(BaseMessageComponent):' astrbot/core/message/components.py"

check_exists "TTS 组件类" \
    "grep -q 'class TTS(BaseMessageComponent):' astrbot/core/message/components.py"

echo ""
echo "🔧 构建和部署检查"
echo "--------------------------------"

check_exists "rebuild.sh git pull 功能" \
    "grep -q 'git pull' rebuild.sh"

check_exists "rebuild.sh compose.yml 检查" \
    "grep -q 'compose.yml 配置' rebuild.sh"

check_exists "compose.yml 本地构建配置" \
    "grep -q 'dockerfile: Dockerfile' compose.yml"

echo ""
echo "================================"
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✅ 所有检查通过！自定义代码完整。${NC}"
    exit 0
else
    echo -e "${RED}❌ 发现 $ERRORS 个问题！请检查上述失败项。${NC}"
    echo ""
    echo "💡 修复建议："
    echo "   1. 查看 CUSTOM_CODE_CHECKLIST.md 了解详细信息"
    echo "   2. 从备份分支恢复丢失的代码："
    echo "      git checkout backup/dev-chrismk-YYYYMMDD -- <丢失的文件>"
    echo "   3. 或者查看最近的提交记录："
    echo "      git log --oneline -10"
    exit 1
fi
