# AstrBot 插件开发标准

## 📖 概述

本文档定义了 AstrBot 插件的开发标准，基于**签到插件**的跨平台改造经验总结。

---

## 🎯 核心原则

### 1. 跨平台一致性
- 所有平台提供一致的用户体验
- 自动适配平台能力
- 优雅的功能降级

### 2. 统一交互设计
- 统一的导航系统（0/1/2）
- 统一的视觉语言
- 统一的命令格式

### 3. 多轮会话支持
- 完整的会话管理
- 自动超时和续期
- 智能导航提示

---

## 📋 标准模板

### 插件结构

```
your_plugin/
├── main.py                          # 主插件类
│   ├── _get_platform_capabilities() # 必需：平台能力检测
│   ├── your_cmd()                   # 命令处理器
│   ├── handle_callback()            # 推荐：按钮回调处理
│   └── on_message()                 # 推荐：会话消息处理
│
├── handlers/
│   ├── session_handler.py           # 推荐：会话处理器
│   │   ├── _build_menu_response()   # 统一菜单构建
│   │   ├── start_xxx_menu()         # 启动菜单
│   │   └── handle_session_message() # 处理会话消息
│   │
│   ├── response_builder.py          # 推荐：响应构建器
│   │   ├── build_xxx_menu()         # 主菜单
│   │   ├── build_submenu_response() # 子菜单
│   │   └── build_detail_response()  # 详情页
│   │
│   └── message_editor.py            # 推荐：消息编辑器
│       ├── edit_or_send()           # 统一编辑/发送
│       ├── _edit_telegram_message() # Telegram 编辑
│       └── _edit_lark_message()     # 飞书编辑
│
├── metadata.yaml                    # 必需：插件元数据
└── README.md                        # 必需：插件说明
```

### 必需组件

#### 1. 平台能力检测

```python
def _get_platform_capabilities(self, event: AstrMessageEvent) -> dict:
    """检测平台能力（跨平台交互设计）"""
    # 正确获取平台名称
    platform_name = (event.get_platform_name() or "").lower()
    if not platform_name:
        platform_name = 'unknown'
    
    # 缓存检查
    if platform_name in self._platform_capabilities:
        return self._platform_capabilities[platform_name]
    
    # 平台能力映射
    platform_features = {
        # 完全支持平台（按钮模式）
        'telegram': {
            'supports_buttons': True,
            'supports_inline_keyboard': True,
            'supports_edit_message': True,
            'max_button_per_row': 8,
            'max_caption_length': 1024,
            'platform_name': 'telegram'
        },
        'lark': {
            'supports_buttons': True,
            'supports_inline_keyboard': True,
            'supports_edit_message': True,
            'max_button_per_row': 5,
            'max_caption_length': 2000,
            'platform_name': 'lark'
        },
        'discord': {
            'supports_buttons': True,
            'supports_inline_keyboard': True,
            'supports_edit_message': True,
            'max_button_per_row': 5,
            'max_caption_length': 2000,
            'platform_name': 'discord'
        },
        # 会话模式平台
        'wechat': {
            'supports_buttons': False,
            'supports_inline_keyboard': False,
            'supports_edit_message': False,
            'platform_name': 'wechat'
        },
        'qq': {
            'supports_buttons': False,
            'supports_inline_keyboard': False,
            'supports_edit_message': False,
            'platform_name': 'qq'
        },
        # ... 其他平台
    }
    
    # 默认能力（会话模式）
    default_capabilities = {
        'supports_buttons': False,
        'supports_inline_keyboard': False,
        'supports_edit_message': False,
        'platform_name': platform_name
    }
    
    capabilities = platform_features.get(platform_name, default_capabilities)
    
    # 缓存结果
    self._platform_capabilities[platform_name] = capabilities
    
    return capabilities
```

#### 2. 响应构建器

```python
from typing import Optional, Tuple, List, Dict, Any

try:
    from astrbot.core.message.components import InlineKeyboard
except ImportError:
    InlineKeyboard = None

class UniversalResponseBuilder:
    """统一响应构建器 - 支持按钮模式和会话模式"""
    
    def __init__(self, platform_capabilities: dict):
        self.capabilities = platform_capabilities
        self.supports_buttons = platform_capabilities.get('supports_buttons', False)
        self.platform_name = platform_capabilities.get('platform_name', 'unknown')
    
    def build_main_menu(self, message: str) -> Tuple[str, Optional[Any]]:
        """构建主菜单"""
        if self.supports_buttons and InlineKeyboard is not None:
            # 按钮模式：创建 InlineKeyboard
            keyboard = self._create_main_keyboard()
            return message, keyboard
        else:
            # 会话模式：消息已包含文本导航
            return message, None
    
    def _create_main_keyboard(self) -> Any:
        """创建主菜单按钮"""
        if InlineKeyboard is None:
            return None
        
        keyboard = InlineKeyboard()
        
        # 功能按钮（根据实际功能调整）
        keyboard.buttons.append([
            {"text": "📝 功能1", "callback_data": "plugin:action1"},
            {"text": "📊 功能2", "callback_data": "plugin:action2"},
            {"text": "🏆 功能3", "callback_data": "plugin:action3"}
        ])
        
        # 导航按钮（首页只显示退出）
        keyboard.buttons.append([
            {"text": "❌ 退出", "callback_data": "plugin:exit"}
        ])
        
        return keyboard
    
    def build_submenu_response(self, content: str, quick_inputs: List[Dict[str, str]] = None) -> Tuple[str, Optional[Any]]:
        """构建子菜单（支持快捷输入按钮）"""
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            
            # 快捷输入按钮（如有）
            if quick_inputs:
                for i in range(0, len(quick_inputs), 3):
                    row = quick_inputs[i:i+3]
                    keyboard.buttons.append(row)
            
            # 导航按钮
            keyboard.buttons.append([
                {"text": "🏠 返回首页", "callback_data": "plugin:home"},
                {"text": "❌ 退出", "callback_data": "plugin:exit"}
            ])
            return content, keyboard
        else:
            # 会话模式：内容已包含导航提示
            return content, None
```

#### 3. 会话处理器（如需多轮交互）

```python
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from .response_builder import UniversalResponseBuilder

class SessionHandler:
    """会话处理器 - 支持跨平台交互"""
    
    SESSION_TIMEOUT_MINUTES = 1
    
    def __init__(self, business_manager, config: Dict[str, Any], plugin=None):
        self.business_manager = business_manager
        self.config = config
        self.plugin = plugin  # 引用主插件
        self.sessions: Dict[str, Dict[str, Any]] = {}
    
    def _create_session(self, session_id, session_type, user_id, data=None, capabilities=None):
        """创建会话（保存平台能力）"""
        now = datetime.now()
        self.sessions[session_id] = {
            'type': session_type,
            'user_id': user_id,
            'step': 0,
            'data': data or {},
            'created_at': now,
            'expires_at': now + timedelta(minutes=self.SESSION_TIMEOUT_MINUTES),
            'step_history': [],
            'capabilities': capabilities  # 保存平台能力
        }
    
    def _get_session(self, session_id, renew=True):
        """获取会话（自动续期）"""
        session = self.sessions.get(session_id)
        if session:
            if datetime.now() > session['expires_at']:
                self._end_session(session_id)
                return None
            if renew:
                session['expires_at'] = datetime.now() + timedelta(minutes=self.SESSION_TIMEOUT_MINUTES)
        return session
    
    def _build_menu_response(self, prefix: str = "", capabilities: Dict = None) -> Tuple[str, Any]:
        """统一的菜单构建方法"""
        is_button_mode = capabilities and capabilities.get('supports_buttons', False)
        
        result = prefix
        if prefix:
            result += "\n\n"
        
        if is_button_mode:
            # 按钮模式：简洁版
            result += "━━━━━━━━━━━━━━━━━━\n"
            result += "📋 功能菜单\n"
            result += "━━━━━━━━━━━━━━━━━━"
        else:
            # 会话模式：详细版
            result += "━━━━━━━━━━━━━━━━━━\n"
            result += "📋 功能菜单\n"
            result += "━━━━━━━━━━━━━━━━━━\n\n"
            result += "3️⃣ 功能1 - 功能说明\n"
            result += "4️⃣ 功能2 - 功能说明\n"
            result += "5️⃣ 功能3 - 功能说明\n\n"
            result += "━━━━━━━━━━━━━━━━━━\n"
            result += "0️⃣ 退出\n\n"
            result += "💡 请输入数字选择功能\n"
            result += f"⏱️ 请在 {self.SESSION_TIMEOUT_MINUTES} 分钟内输入"
        
        # 使用响应构建器
        if capabilities:
            builder = UniversalResponseBuilder(capabilities)
            return builder.build_main_menu(result)
        else:
            return result, None
```

---

## 🎨 视觉规范

### 分隔线
```
━━━━━━━━━━━━━━━━━━
```

### Emoji 标准

| 功能 | Emoji | 说明 | 使用场景 |
|------|-------|------|----------|
| 菜单 | 📋 | 菜单标题 | 所有菜单页面 |
| 成功 | ✅ | 操作成功 | 成功提示 |
| 失败 | ❌ | 操作失败 | 错误提示 |
| 提示 | 💡 | 操作提示 | 帮助信息 |
| 时间 | ⏱️ | 超时提示 | 会话超时 |
| 导航 | 1️⃣2️⃣0️⃣ | 导航选项 | 会话模式导航 |
| 功能 | 📝📊🏆 | 功能图标 | 按钮和菜单项 |
| 返回 | 🏠 | 返回首页 | 导航按钮 |
| 退出 | ❌ | 退出会话 | 导航按钮 |
| 日期 | 📅 | 日期相关 | 日期输入 |

### 导航格式

**按钮模式（Telegram/飞书/Discord）**

主菜单：
```
[📝 功能1] [📊 功能2] [🏆 功能3]
[❌ 退出]
```

子菜单/详情页：
```
[🏠 返回首页] [❌ 退出]
```

**会话模式（微信/QQ等）**

主菜单（step=0）：
```
━━━━━━━━━━━━━━━━━━
0️⃣ 退出

💡 请输入数字选择功能
⏱️ 请在 1 分钟内输入
```

子菜单（step>0）：
```
━━━━━━━━━━━━━━━━━━
1️⃣ 返回首页 | 2️⃣ 返回上级 | 0️⃣ 退出
⏱️ 请在 1 分钟内输入
```

---

## 🔧 实现规范

### 1. 命令处理器

```python
from astrbot.core.message.components import Plain

@filter.command("your_cmd")
async def your_cmd(self, event: AstrMessageEvent):
    """命令处理"""
    # 1. 检测平台能力
    capabilities = self._get_platform_capabilities(event)
    
    # 2. 构建响应
    builder = UniversalResponseBuilder(capabilities)
    message, keyboard = builder.build_main_menu(content)
    
    # 3. 发送响应（正确的方式）
    if keyboard:
        yield event.chain_result([Plain(message), keyboard])
    else:
        yield event.plain_result(message)
    
    # 4. 停止事件传播
    event.stop_event()
    return
```

### 2. 按钮回调处理（使用回调路由器）⭐

```python
from .handlers.message_editor import MessageEditor
from astrbot.core import CallbackRouter, callback_handler, auto_stop_event

# 在 __init__ 中注册回调路由
def __init__(self, context: Context, config: dict = None):
    super().__init__(context, config)
    # ... 其他初始化代码
    
    # 注册回调路由（推荐）
    CallbackRouter.register("your_plugin", self.handle_callback, plugin_instance=self)
    logger.info("[YourPlugin] 已注册回调路由: your_plugin")

# 使用装饰器处理回调
@filter.command("callback")
@callback_handler("your_plugin")
@auto_stop_event  # 自动停止事件传播
async def handle_callback(self, event: AstrMessageEvent, data: str = ""):
    """
    按钮回调处理
    
    使用 @callback_handler 装饰器：
    - 只接收 your_plugin: 开头的回调
    - 装饰器自动过滤前缀，无需手动检查
    - 需要手动提取 action（保持灵活性）
    """
    # 提取回调数据并去掉前缀
    raw = event.message_str.strip()
    parts = raw.split(" ", 1)
    if len(parts) < 2:
        return
    callback_data = parts[1].strip()
    action = callback_data.replace("your_plugin:", "")
    
    try:
        # 处理操作
        if action == "home":
            # 返回首页
            capabilities = self._get_platform_capabilities(event)
            result = await self.session_handler.start_menu(
                user_id, session_id, capabilities=capabilities
            )
            
            if isinstance(result, tuple):
                message, keyboard = result
                async for ret in MessageEditor.edit_or_send(event, message, keyboard):
                    yield ret
            else:
                yield event.plain_result(result)
                
        elif action == "exit":
            # 退出会话
            self.session_handler._end_session(session_id)
            yield event.plain_result("✅ 已退出")
            # @auto_stop_event 装饰器会自动停止事件传播
        
        elif action.startswith("input:"):
            # 快捷输入回调
            input_value = action.replace("input:", "")
            result = await self.session_handler.handle_session_message(
                user_id, session_id, input_value
            )
            
            if result:
                if isinstance(result, tuple):
                    message, keyboard = result
                    async for ret in MessageEditor.edit_or_send(event, message, keyboard):
                        yield ret
                else:
                    async for ret in MessageEditor.edit_or_send(event, result):
                        yield ret
        # 不需要手动 stop_event，装饰器会自动处理
        
    except Exception as e:
        logger.error(f"处理回调失败: {e}", exc_info=True)
        yield event.plain_result(f"❌ 操作失败: {e}")
        # 不需要手动 stop_event，装饰器会自动处理
```

### 3. 会话消息处理

```python
from .handlers.message_editor import MessageEditor

@filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
async def on_message(self, event: AstrMessageEvent):
    """会话消息处理"""
    # 1. 跳过已处理的消息
    if event.get_result():
        return
    
    # 2. 跳过命令和回调
    message_str = event.message_str or ""
    if message_str.startswith("/"):
        return
    if message_str.startswith("callback "):
        return
    
    # 3. 检查会话
    user_id = event.get_sender_id()
    session_id = event.get_session_id()
    session = self.session_handler._get_session(session_id, renew=True)
    
    if not session:
        return
    
    # 4. 处理会话消息
    result = await self.session_handler.handle_session_message(
        user_id, session_id, message_str
    )
    
    if result:
        # 处理返回值（可能是字符串或元组）
        if isinstance(result, tuple):
            message_text, keyboard = result
            async for ret in MessageEditor.edit_or_send(event, message_text, keyboard):
                yield ret
        else:
            yield event.plain_result(result)
        
        event.stop_event()
        return
```

### 4. 消息编辑器（推荐）

```python
from typing import Optional, Any
from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger
from astrbot.core.message.components import Plain

try:
    from astrbot.core.message.components import InlineKeyboard
except ImportError:
    InlineKeyboard = None

class MessageEditor:
    """消息编辑辅助类 - 统一处理不同平台的消息编辑"""
    
    @staticmethod
    async def edit_or_send(event: AstrMessageEvent, message: str, keyboard: Any = None):
        """尝试编辑消息，如果不支持则发送新消息"""
        platform_name = (event.get_platform_name() or "").lower()
        
        try:
            # Telegram 平台：支持消息编辑
            if platform_name == "telegram":
                success = await MessageEditor._edit_telegram_message(event, message, keyboard)
                if success:
                    return
            
            # 其他平台或编辑失败：发送新消息
            if keyboard:
                yield event.chain_result([Plain(message), keyboard])
            else:
                yield event.plain_result(message)
                
        except Exception as e:
            logger.error(f"[消息编辑器] 失败: {e}", exc_info=True)
            yield event.plain_result(message)
    
    @staticmethod
    async def _edit_telegram_message(event, message: str, keyboard: Any = None) -> bool:
        """编辑 Telegram 消息"""
        try:
            from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            
            if not isinstance(event, TelegramPlatformEvent):
                return False
            
            # 转换键盘格式
            tg_keyboard = None
            if keyboard and hasattr(keyboard, 'buttons') and keyboard.buttons:
                tg_keyboard_buttons = []
                for row in keyboard.buttons:
                    tg_row = [
                        InlineKeyboardButton(text=btn['text'], callback_data=btn['callback_data'])
                        for btn in row
                    ]
                    tg_keyboard_buttons.append(tg_row)
                tg_keyboard = InlineKeyboardMarkup(tg_keyboard_buttons)
            
            # 编辑消息
            msg_id = int(event.message_obj.message_id)
            chat_id = event.message_obj.group_id or event.get_sender_id()
            
            await event.client.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=message,
                reply_markup=tg_keyboard
            )
            
            return True
            
        except Exception as e:
            logger.warning(f"Telegram 消息编辑失败: {e}")
            return False
```

---

## ⚠️ 重要说明

### 回调路由器（推荐使用）⭐⭐⭐⭐⭐

**新特性：回调路由注册机制**

从 AstrBot v3.4.11+ 开始，推荐使用回调路由器来优化回调处理性能。

**优点：**
- ✅ **高性能** - O(1) 时间复杂度，直接路由到对应插件
- ✅ **零噪音** - 其他插件不会收到不相关的回调
- ✅ **代码简洁** - 自动提取 action，无需手动解析
- ✅ **易于调试** - 清晰的路由日志

**使用方法：**

1. **导入回调路由器**
```python
from astrbot.core import CallbackRouter, callback_handler
```

2. **在初始化时注册**
```python
def __init__(self, context: Context, config: dict = None):
    super().__init__(context, config)
    # 注册回调路由
    CallbackRouter.register("your_plugin", self.handle_callback, plugin_instance=self)
```

3. **使用装饰器处理回调**
```python
@filter.command("callback")
@callback_handler("your_plugin")
async def handle_callback(self, event: AstrMessageEvent, data: str = ""):
    # 装饰器已过滤前缀，手动提取 action
    raw = event.message_str.strip()
    callback_data = raw.split(" ", 1)[1] if " " in raw else ""
    action = callback_data.replace("your_plugin:", "")
    
    if action == "home":
        # 处理返回首页
        pass
```

**性能对比：**

| 方案 | 插件数量 | 每次回调调用次数 | 性能 |
|------|---------|----------------|------|
| 传统方式 | 10个 | 10次 | ⭐⭐ |
| 回调路由器 | 10个 | 1次 | ⭐⭐⭐⭐⭐ |
| 传统方式 | 50个 | 50次 | ⭐ |
| 回调路由器 | 50个 | 1次 | ⭐⭐⭐⭐⭐ |

---

### ⚠️ 为什么使用了回调路由器，其他插件还能收到回调？

**原因：插件执行顺序**

如果插件 A（使用路由器）排在插件 B（未使用路由器）**之后**执行，那么插件 B 仍然会先收到回调，产生日志噪音。

**解决方案：**
1. **所有插件**都应该使用回调路由器，或手动检查回调前缀。
2. `@auto_stop_event` 只能阻止**后续**插件收到回调，无法影响**之前**执行的插件。

### 🎯 自动停止事件传播（推荐）⭐⭐⭐⭐⭐

**使用 `@auto_stop_event` 装饰器，自动处理事件停止：**

```python
from astrbot.core import auto_stop_event

@filter.command("callback")
@callback_handler("your_plugin")
@auto_stop_event  # 自动停止事件传播
async def handle_callback(self, event, data=""):
    if action == "exit":
        yield event.plain_result("✅ 已退出")
        # 不需要手动调用 event.stop_event()
    
    elif action == "home":
        async for ret in MessageEditor.edit_or_send(event, message, keyboard):
            yield ret
        # 不需要手动调用 event.stop_event()
```

**优点：**
- ✅ 代码简洁，无需重复写 `event.stop_event()`
- ✅ 自动处理所有分支，不会遗漏
- ✅ 自动在函数结束时停止事件传播
- ✅ 支持异常情况，确保事件总是被停止

---

### ⚠️ 手动停止事件传播（不推荐）

**问题：** 在 async generator 函数中，`yield` 之后的代码可能不会执行！

```python
# ❌ 错误示例
async def handle_callback(...):
    if action == "exit":
        yield event.plain_result("✅ 已退出")
        event.stop_event()  # 这行代码可能永远不会执行！
```

**原因：**
- `yield` 会暂停函数执行，将控制权返回给调用者
- `yield` 之后的代码只有在调用者**再次迭代**时才会执行
- 框架在获取到结果后不会再次迭代，导致 `stop_event()` 不执行

**✅ 正确做法 1：在结果上调用 `.stop_event()`**

```python
async def handle_callback(...):
    if action == "exit":
        # 在结果对象上调用 .stop_event()，然后 yield
        result = event.plain_result("✅ 已退出").stop_event()
        yield result
        return
```

**✅ 正确做法 2：使用 MessageEditor（自动处理）**

```python
async def handle_callback(...):
    if action == "home":
        async for ret in MessageEditor.edit_or_send(event, message, keyboard):
            yield ret
        # MessageEditor 在编辑成功时会 return（不 yield）
        # 所以这里的 stop_event() 能被执行
        event.stop_event()
        return
```

**规则总结：**
1. 如果直接 `yield event.plain_result()`，必须在结果上调用 `.stop_event()`
2. 如果使用 `MessageEditor.edit_or_send()`，可以在循环后调用 `event.stop_event()`
3. 异常处理中的 `yield` 也要遵循规则 1

---

### 传统回调处理方式（兼容）

如果不使用回调路由器，需要手动检查前缀：

```python
@filter.command("callback")
async def handle_callback(self, event: AstrMessageEvent, data: str = ""):
    # 手动提取和检查
    raw = event.message_str.strip()
    parts = raw.split(" ", 1)
    if len(parts) < 2:
        return
    callback_data = parts[1].strip()
    
    # 静默返回（不打印日志）
    if not callback_data or not callback_data.startswith("your_plugin:"):
        return
    
    # 手动提取 action
    action = callback_data.replace("your_plugin:", "")
    # ... 处理逻辑
```

**注意：** 传统方式会导致所有插件都接收所有回调消息，影响性能。

---

## 📊 支持的平台

### 完全支持（按钮模式）
- ✅ Telegram
- ✅ 飞书（Lark）
- ✅ Discord

### 会话模式
- ✅ 微信（WeChat）
- ✅ QQ
- ✅ 企业微信（WeChat Work）
- ✅ 钉钉（DingTalk）

---

## 📚 参考文档

### 设计指南
1. **跨平台交互设计指南** - 通用设计方案
2. **多轮对话插件设计指南** - 会话管理详解

### 实现参考
3. **签到插件改造说明** - 完整改造过程
4. **签到插件功能清单** - 详细功能列表

### 源码参考
5. **签到插件源码** - `data/plugins/astrbot_plugin_checkin/`

---

## ✅ 开发检查清单

### 基础功能
- [ ] 实现平台能力检测
- [ ] 创建响应构建器
- [ ] 统一视觉风格
- [ ] 添加错误处理
- [ ] 完善日志记录

### 交互功能
- [ ] 支持按钮模式（如平台支持）
- [ ] 支持会话模式（如平台不支持按钮）
- [ ] 实现消息编辑（如平台支持）
- [ ] 统一导航系统（0/1/2）

### 多轮会话（可选）
- [ ] 实现会话管理
- [ ] 添加超时机制
- [ ] 实现自动续期
- [ ] 智能导航提示

### 测试验证
- [ ] 测试所有支持平台
- [ ] 验证按钮功能
- [ ] 验证会话功能
- [ ] 边界情况测试

### 文档完善
- [ ] 编写 README.md
- [ ] 添加使用示例
- [ ] 说明配置项
- [ ] 列出依赖项

---

## 🚀 快速开始

### 1. 复制模板

```bash
cp -r data/plugins/astrbot_plugin_checkin data/plugins/your_plugin
```

### 2. 修改基础信息

```python
@register("your_plugin", "Your Name", "插件描述", "1.0.0")
class YourPlugin(Star):
    pass
```

### 3. 实现核心功能

- 保留平台能力检测
- 保留响应构建器
- 修改业务逻辑
- 调整菜单选项

### 4. 测试和发布

- 测试各平台功能
- 完善文档
- 提交代码

---

## 💡 最佳实践

### 1. 代码组织
- 业务逻辑与交互分离
- 使用处理器模式
- 保持代码简洁

### 2. 错误处理
- 捕获所有异常
- 提供友好提示
- 记录详细日志

### 3. 性能优化
- 缓存平台能力
- 及时清理会话
- 避免重复计算

### 4. 用户体验
- 提示信息清晰
- 操作流程简单
- 响应速度快

---

## 🎉 总结

遵循本标准开发的插件将具有：

- ✅ 跨平台一致性
- ✅ 统一的交互体验
- ✅ 完善的功能支持
- ✅ 良好的代码质量
- ✅ 易于维护和扩展

**让我们一起建设更好的 AstrBot 插件生态！** 🚀
