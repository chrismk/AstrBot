# AstrBot 自定义代码检查清单

> **用途：** 在合并 main 分支前，使用此清单检查自定义代码是否被覆盖或删除
> 
> **最后更新：** 2025-11-10
> 
> **维护者：** Chrismk

---

## 📋 快速检查命令

合并前执行以下命令，对比差异：

```bash
# 1. 检查所有自定义文件
git diff origin/main HEAD -- \
  astrbot/core/platform/sources/telegram/ \
  astrbot/core/platform/sources/lark/ \
  astrbot/core/message/components.py \
  rebuild.sh \
  compose.yml

# 2. 检查关键功能是否存在
grep -r "CallbackQueryHandler" astrbot/core/platform/sources/telegram/
grep -r "card_action_trigger" astrbot/core/platform/sources/lark/
grep -r "class InlineKeyboard" astrbot/core/message/components.py
```

---

## 🎯 核心自定义代码清单

### 1. Telegram 平台适配器

#### 📁 `astrbot/core/platform/sources/telegram/tg_adapter.py`

**关键功能：**
- ✅ **CallbackQueryHandler 导入**（第11行）
  ```python
  from telegram.ext import CallbackQueryHandler
  ```

- ✅ **CallbackQueryHandler 注册**（第86行）
  ```python
  self.application.add_handler(CallbackQueryHandler(self.callback_handler))
  ```

- ✅ **callback_handler 方法**（第133-188行）
  - 将按钮回调转换为 `/callback` 命令事件
  - 支持 `llm=0/1` 参数控制是否调用 LLM
  - 标记为命令事件（`is_wake=True`, `is_at_or_wake_command=True`）

**检查方法：**
```bash
grep -n "CallbackQueryHandler" astrbot/core/platform/sources/telegram/tg_adapter.py
grep -n "async def callback_handler" astrbot/core/platform/sources/telegram/tg_adapter.py
```

---

#### 📁 `astrbot/core/platform/sources/telegram/tg_event.py`

**关键功能：**
- ✅ **InlineKeyboard 导入**（第14行）
  ```python
  from astrbot.api.message_components import InlineKeyboard
  ```

- ✅ **InlineKeyboard 预处理**（第105-134行）
  - 收集 InlineKeyboard 组件
  - 转换为 Telegram 的 `InlineKeyboardMarkup`
  - 支持 URL 按钮和 callback_data 按钮

- ✅ **InlineKeyboard 发送**（第139-162行）
  - 将键盘附加到文本消息（`reply_markup=keyboard_markup`）
  - 支持 MarkdownV2 格式

- ✅ **InlineKeyboard 流式响应跳过**（第284-286行，第455-457行）
  ```python
  elif isinstance(i, InlineKeyboard):
      # InlineKeyboard 已在预处理中处理，跳过
      continue
  ```

**检查方法：**
```bash
grep -n "InlineKeyboard" astrbot/core/platform/sources/telegram/tg_event.py
grep -n "reply_markup" astrbot/core/platform/sources/telegram/tg_event.py
```

---

### 2. 飞书/Lark 平台适配器

#### 📁 `astrbot/core/platform/sources/lark/lark_adapter.py`

**关键功能：**
- ✅ **CardService 导入**（第19行）
  ```python
  from .card_service import get_card_service
  ```

- ✅ **卡片交互回调处理器注册**（第96行）
  ```python
  .register_p2_card_action_trigger(do_card_action_trigger)
  ```

- ✅ **do_card_action_trigger 方法**（第56-77行）
  - 处理飞书卡片按钮点击事件
  - 返回 Toast 响应

- ✅ **CardService 初始化**（第113行）
  ```python
  self.card_service = get_card_service(self.appid, self.appsecret)
  ```

- ✅ **CardService 注入到事件**（第264行）
  ```python
  event.card_service = self.card_service
  ```

- ✅ **convert_card_action_msg 方法**（第279-351行）
  - 将卡片回调转换为 `/callback` 命令事件
  - 支持延时更新卡片的 token 传递

**检查方法：**
```bash
grep -n "card_service" astrbot/core/platform/sources/lark/lark_adapter.py
grep -n "card_action_trigger" astrbot/core/platform/sources/lark/lark_adapter.py
grep -n "convert_card_action_msg" astrbot/core/platform/sources/lark/lark_adapter.py
```

---

#### 📁 `astrbot/core/platform/sources/lark/lark_event.py`

**关键功能：**
- ✅ **edit_message 方法**（第460-576行）
  - 编辑已发送的消息
  - 支持纯文本和交互式卡片
  - 支持 InlineKeyboard 转换为飞书卡片格式

- ✅ **update_card_delayed 方法**（第580-592行）
  - 使用飞书延时更新卡片 API
  - 调用 CardService 的 update_card 方法

- ✅ **InlineKeyboard 转换逻辑**
  - 支持 URL 按钮和 callback 按钮
  - 支持按钮样式（button_type, button_size, button_width）

**检查方法：**
```bash
grep -n "async def edit_message" astrbot/core/platform/sources/lark/lark_event.py
grep -n "async def update_card_delayed" astrbot/core/platform/sources/lark/lark_event.py
```

---

#### 📁 `astrbot/core/platform/sources/lark/card_service.py` ⭐ 自定义文件

**完整的自定义文件，提供：**
- ✅ **LarkCardService 类**
  - 卡片创建和更新
  - 延时更新 API 支持
  - Token 管理集成

- ✅ **get_card_service 函数**
  - 单例模式管理卡片服务实例

**检查方法：**
```bash
# 确保文件存在
test -f astrbot/core/platform/sources/lark/card_service.py && echo "✅ 文件存在" || echo "❌ 文件丢失"
```

---

#### 📁 `astrbot/core/platform/sources/lark/token_manager.py` ⭐ 自定义文件

**完整的自定义文件，提供：**
- ✅ **TokenManager 类**
  - 飞书访问令牌管理
  - 自动刷新机制
  - 线程安全

- ✅ **get_token_manager 函数**
  - 单例模式管理 token 实例

**检查方法：**
```bash
# 确保文件存在
test -f astrbot/core/platform/sources/lark/token_manager.py && echo "✅ 文件存在" || echo "❌ 文件丢失"
```

---

### 3. 消息组件

#### 📁 `astrbot/core/message/components.py`

**关键功能：**
- ✅ **InlineKeyboard 类**（第876-953行）
  - 使用现代 Python 类型注解：`list[list[dict[str, Any]]]`
  - `add_row()` 方法
  - `new_row()` 方法
  - `add_button()` 方法
  - 飞书特定方法：`to_lark_card()`, `to_lark_interactive_card()`

- ✅ **CardImage 组件**（第697-713行）
  - 卡片图片组件（飞书等平台使用）

- ✅ **TTS 组件**（第716-722行）
  - 文字转语音组件

- ✅ **其他自定义组件类型**
  - Anonymous
  - RedBag
  - Xml

**检查方法：**
```bash
grep -n "class InlineKeyboard" astrbot/core/message/components.py
grep -n "class CardImage" astrbot/core/message/components.py
grep -n "class TTS" astrbot/core/message/components.py
```

---

### 4. 构建和部署

#### 📁 `rebuild.sh`

**关键功能：**
- ✅ **Git pull 在重建前**（第29-32行）
  ```bash
  echo "[rebuild] 拉取最新代码..."
  git pull || {
      echo "警告: git pull 失败，继续使用当前代码"
  }
  ```

- ✅ **compose.yml 配置检查**（第8-27行）
  - 检查是否使用本地构建而非远程镜像
  - 防止使用 `soulter/astrbot:latest`

**检查方法：**
```bash
grep -n "git pull" rebuild.sh
grep -n "compose.yml 配置检查" rebuild.sh
```

---

#### 📁 `compose.yml`

**关键配置：**
- ✅ **本地构建配置**
  ```yaml
  build:
    context: .
    dockerfile: Dockerfile
  image: astrbot:local
  ```

**检查方法：**
```bash
grep -n "build:" compose.yml
grep -n "dockerfile: Dockerfile" compose.yml
```

---

## 🔍 合并后验证步骤

### 1. 自动化检查脚本

创建并运行以下检查脚本：

```bash
#!/bin/bash
# check_custom_code.sh

echo "🔍 检查自定义代码完整性..."
echo ""

# 检查 Telegram CallbackQueryHandler
if grep -q "CallbackQueryHandler" astrbot/core/platform/sources/telegram/tg_adapter.py; then
    echo "✅ Telegram CallbackQueryHandler 存在"
else
    echo "❌ Telegram CallbackQueryHandler 丢失！"
fi

# 检查 Telegram InlineKeyboard
if grep -q "isinstance(i, InlineKeyboard)" astrbot/core/platform/sources/telegram/tg_event.py; then
    echo "✅ Telegram InlineKeyboard 处理存在"
else
    echo "❌ Telegram InlineKeyboard 处理丢失！"
fi

# 检查飞书 CardService
if [ -f "astrbot/core/platform/sources/lark/card_service.py" ]; then
    echo "✅ 飞书 CardService 文件存在"
else
    echo "❌ 飞书 CardService 文件丢失！"
fi

# 检查飞书 TokenManager
if [ -f "astrbot/core/platform/sources/lark/token_manager.py" ]; then
    echo "✅ 飞书 TokenManager 文件存在"
else
    echo "❌ 飞书 TokenManager 文件丢失！"
fi

# 检查飞书卡片回调
if grep -q "card_action_trigger" astrbot/core/platform/sources/lark/lark_adapter.py; then
    echo "✅ 飞书卡片回调处理存在"
else
    echo "❌ 飞书卡片回调处理丢失！"
fi

# 检查 InlineKeyboard 组件
if grep -q "class InlineKeyboard" astrbot/core/message/components.py; then
    echo "✅ InlineKeyboard 组件存在"
else
    echo "❌ InlineKeyboard 组件丢失！"
fi

# 检查 CardImage 组件
if grep -q "class CardImage" astrbot/core/message/components.py; then
    echo "✅ CardImage 组件存在"
else
    echo "❌ CardImage 组件丢失！"
fi

# 检查 rebuild.sh 的 git pull
if grep -q "git pull" rebuild.sh; then
    echo "✅ rebuild.sh git pull 存在"
else
    echo "❌ rebuild.sh git pull 丢失！"
fi

echo ""
echo "检查完成！"
```

### 2. 手动功能测试

合并后必须测试以下功能：

#### Telegram 平台
- [ ] 发送带 InlineKeyboard 的消息，按钮是否正常显示
- [ ] 点击按钮，是否触发回调事件
- [ ] 插件是否能接收到 `/callback` 事件
- [ ] 图片/文件是否能附带 caption

#### 飞书平台
- [ ] 发送带 InlineKeyboard 的消息，是否转换为交互式卡片
- [ ] 点击卡片按钮，是否触发回调事件
- [ ] `edit_message` 是否能正常编辑消息
- [ ] `update_card_delayed` 是否能延时更新卡片

---

## 📝 合并流程建议

### 合并前

1. **创建备份分支**
   ```bash
   git checkout dev/chrismk
   git branch backup/dev-chrismk-$(date +%Y%m%d)
   git push origin backup/dev-chrismk-$(date +%Y%m%d)
   ```

2. **运行检查脚本**
   ```bash
   bash check_custom_code.sh > pre_merge_check.log
   ```

3. **记录当前状态**
   ```bash
   git diff origin/main HEAD --stat > pre_merge_diff.txt
   ```

### 合并中

1. **使用策略性合并**
   ```bash
   git fetch origin
   git merge origin/main --no-commit --no-ff
   ```

2. **检查冲突文件**
   ```bash
   git status
   # 特别关注以下文件：
   # - astrbot/core/platform/sources/telegram/tg_adapter.py
   # - astrbot/core/platform/sources/telegram/tg_event.py
   # - astrbot/core/platform/sources/lark/lark_adapter.py
   # - astrbot/core/platform/sources/lark/lark_event.py
   # - astrbot/core/message/components.py
   ```

3. **对于自定义文件，使用 --ours 策略**
   ```bash
   git checkout --ours astrbot/core/platform/sources/lark/card_service.py
   git checkout --ours astrbot/core/platform/sources/lark/token_manager.py
   ```

### 合并后

1. **运行检查脚本**
   ```bash
   bash check_custom_code.sh > post_merge_check.log
   diff pre_merge_check.log post_merge_check.log
   ```

2. **对比关键文件**
   ```bash
   git diff backup/dev-chrismk-$(date +%Y%m%d) HEAD -- \
     astrbot/core/platform/sources/telegram/ \
     astrbot/core/platform/sources/lark/ \
     astrbot/core/message/components.py
   ```

3. **如果发现代码丢失，从备份恢复**
   ```bash
   git checkout backup/dev-chrismk-$(date +%Y%m%d) -- <丢失的文件>
   ```

---

## 🚨 常见问题

### Q1: 合并后 InlineKeyboard 不显示？
**原因：** `tg_event.py` 中的 InlineKeyboard 处理逻辑被删除

**解决：**
```bash
git checkout backup/dev-chrismk-$(date +%Y%m%d) -- astrbot/core/platform/sources/telegram/tg_event.py
```

### Q2: 按钮点击无响应？
**原因：** `tg_adapter.py` 中的 CallbackQueryHandler 被删除

**解决：**
```bash
git checkout backup/dev-chrismk-$(date +%Y%m%d) -- astrbot/core/platform/sources/telegram/tg_adapter.py
```

### Q3: 飞书卡片无法更新？
**原因：** `card_service.py` 或 `lark_event.py` 中的方法被删除

**解决：**
```bash
git checkout backup/dev-chrismk-$(date +%Y%m%d) -- astrbot/core/platform/sources/lark/
```

### Q4: Docker 容器使用旧代码？
**原因：** `compose.yml` 配置被改为使用远程镜像

**解决：**
```bash
git checkout backup/dev-chrismk-$(date +%Y%m%d) -- compose.yml
```

---

## 📊 自定义代码统计

| 类别 | 文件数 | 代码行数（估算） | 关键功能数 |
|------|--------|------------------|-----------|
| Telegram 适配器 | 2 | ~200 | 4 |
| 飞书适配器 | 4 | ~600 | 8 |
| 消息组件 | 1 | ~100 | 4 |
| 构建脚本 | 2 | ~50 | 2 |
| **总计** | **9** | **~950** | **18** |

---

## 🔗 相关提交记录

- `9a693ff2` - feat: lark adapter improvements (2025-10-20)
  - 新增 `card_service.py`
  - 新增 `token_manager.py`
  - 增强 `lark_adapter.py` 和 `lark_event.py`

- `a5626cd0` - [rebuild] 先拉取最新代码再重建 (2025-10-20)
  - 修改 `rebuild.sh`

- `b128e3cc` - fix: restore InlineKeyboard support in Telegram adapter (2025-11-10)
  - 恢复 `tg_event.py` 的 InlineKeyboard 支持

- `28404c93` - fix: restore custom features lost during merge (2025-11-10)
  - 恢复 `lark_adapter.py`, `lark_event.py`, `components.py`

- `223fac41` - fix: restore Telegram CallbackQueryHandler (2025-11-10)
  - 恢复 `tg_adapter.py` 的回调处理器

---

## ✅ 最后更新

- **日期：** 2025-11-10
- **版本：** v4.5.6 合并后
- **状态：** 所有自定义代码已验证完整

**维护建议：** 每次合并 main 分支后，更新此文档并运行检查脚本。
