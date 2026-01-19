# 自定义代码完整性检查脚本 (PowerShell 版本)
# 用于合并 main 分支后验证自定义代码是否完整

Write-Host "🔍 检查自定义代码完整性..." -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

$ERRORS = 0

# 检查函数
function Check-Exists {
    param(
        [string]$Description,
        [string]$FilePath,
        [string]$Pattern
    )
    
    if (Test-Path $FilePath) {
        if (Select-String -Path $FilePath -Pattern $Pattern -Quiet) {
            Write-Host "✅ $Description" -ForegroundColor Green
            return $true
        }
    }
    
    Write-Host "❌ $Description" -ForegroundColor Red
    $script:ERRORS++
    return $false
}

function Check-FileExists {
    param(
        [string]$Description,
        [string]$FilePath
    )
    
    if (Test-Path $FilePath) {
        Write-Host "✅ $Description" -ForegroundColor Green
        return $true
    } else {
        Write-Host "❌ $Description" -ForegroundColor Red
        $script:ERRORS++
        return $false
    }
}

Write-Host "📱 Telegram 平台检查" -ForegroundColor Yellow
Write-Host "--------------------------------" -ForegroundColor Yellow

Check-Exists "Telegram CallbackQueryHandler 导入" `
    "astrbot/core/platform/sources/telegram/tg_adapter.py" `
    "from telegram.ext import.*CallbackQueryHandler"

Check-Exists "Telegram CallbackQueryHandler 注册" `
    "astrbot/core/platform/sources/telegram/tg_adapter.py" `
    "CallbackQueryHandler\(self\.callback_handler\)"

Check-Exists "Telegram callback_handler 方法" `
    "astrbot/core/platform/sources/telegram/tg_adapter.py" `
    "async def callback_handler"

Check-Exists "Telegram InlineKeyboard 导入" `
    "astrbot/core/platform/sources/telegram/tg_event.py" `
    "InlineKeyboard"

Check-Exists "Telegram InlineKeyboard 预处理" `
    "astrbot/core/platform/sources/telegram/tg_event.py" `
    "isinstance\(i, InlineKeyboard\)"

Check-Exists "Telegram InlineKeyboard 发送逻辑" `
    "astrbot/core/platform/sources/telegram/tg_event.py" `
    "reply_markup=keyboard_markup"

Write-Host ""
Write-Host "🦅 飞书平台检查" -ForegroundColor Yellow
Write-Host "--------------------------------" -ForegroundColor Yellow

Check-FileExists "飞书 CardService 文件" `
    "astrbot/core/platform/sources/lark/card_service.py"

Check-FileExists "飞书 TokenManager 文件" `
    "astrbot/core/platform/sources/lark/token_manager.py"

Check-Exists "飞书 CardService 导入" `
    "astrbot/core/platform/sources/lark/lark_adapter.py" `
    "from \.card_service import get_card_service"

Check-Exists "飞书 CardService 初始化" `
    "astrbot/core/platform/sources/lark/lark_adapter.py" `
    "self\.card_service = get_card_service"

Check-Exists "飞书卡片回调处理器注册" `
    "astrbot/core/platform/sources/lark/lark_adapter.py" `
    "register_p2_card_action_trigger"

Check-Exists "飞书 convert_card_action_msg 方法" `
    "astrbot/core/platform/sources/lark/lark_adapter.py" `
    "async def convert_card_action_msg"

Check-Exists "飞书 edit_message 方法" `
    "astrbot/core/platform/sources/lark/lark_event.py" `
    "async def edit_message"

Check-Exists "飞书 update_card_delayed 方法" `
    "astrbot/core/platform/sources/lark/lark_event.py" `
    "async def update_card_delayed"

Write-Host ""
Write-Host "📦 消息组件检查" -ForegroundColor Yellow
Write-Host "--------------------------------" -ForegroundColor Yellow

Check-Exists "InlineKeyboard 组件类" `
    "astrbot/core/message/components.py" `
    "class InlineKeyboard\(BaseMessageComponent\):"

Check-Exists "InlineKeyboard 现代类型注解" `
    "astrbot/core/message/components.py" `
    "buttons: list\[list\[dict\[str, Any\]\]\]"

Check-Exists "CardImage 组件类" `
    "astrbot/core/message/components.py" `
    "class CardImage\(BaseMessageComponent\):"

Check-Exists "TTS 组件类" `
    "astrbot/core/message/components.py" `
    "class TTS\(BaseMessageComponent\):"

Write-Host ""
Write-Host "🔧 构建和部署检查" -ForegroundColor Yellow
Write-Host "--------------------------------" -ForegroundColor Yellow

Check-Exists "rebuild.sh git pull 功能" `
    "rebuild.sh" `
    "git pull"

Check-Exists "rebuild.sh compose.yml 检查" `
    "rebuild.sh" `
    "compose\.yml 配置"

Check-Exists "compose.yml 本地构建配置" `
    "compose.yml" `
    "dockerfile: Dockerfile"

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
if ($ERRORS -eq 0) {
    Write-Host "✅ 所有检查通过！自定义代码完整。" -ForegroundColor Green
    exit 0
} else {
    Write-Host "❌ 发现 $ERRORS 个问题！请检查上述失败项。" -ForegroundColor Red
    Write-Host ""
    Write-Host "💡 修复建议：" -ForegroundColor Yellow
    Write-Host "   1. 查看 CUSTOM_CODE_CHECKLIST.md 了解详细信息"
    Write-Host "   2. 从备份分支恢复丢失的代码："
    Write-Host "      git checkout backup/pre-merge-20251128 -- 丢失的文件"
    Write-Host "   3. 或者查看最近的提交记录："
    Write-Host "      git log --oneline -10"
    exit 1
}
