# AstrBot 插件开发标准

## 📖 概述

本文档定义了 AstrBot 插件的开发标准，基于**签到插件和豆瓣插件**的跨平台改造经验总结。

### 📅 版本历史

- **v1.3** (2025-11-23) - 新增"常见问题与解决方案"章节，记录事件传播、会话步骤一致性、退出流程等关键问题的解决方案
- **v1.2** (2025-11-20) - 新增 NavigationHandler、SessionManager、LarkMessageHelper 通用模块使用说明
- **v1.1** (2025-11-15) - 新增回调路由器和自动停止事件传播装饰器
- **v1.0** (2025-11-10) - 初始版本，定义跨平台插件开发标准

---

## 🎯 核心原则

### 1. 跨平台一致性
- 所有平台提供一致的用户体验
- 自动适配平台能力
- 优雅的功能降级

### 2. 代码复用优先
- **优先使用通用模块** (`common/`)
- 避免重复实现相同功能
- 继承通用基类扩展功能

### 3. 统一交互设计
- 统一的导航系统（0/1/2）
- 统一的视觉语言
- 统一的命令格式

### 4. 多轮会话支持
- 完整的会话管理
- 自动超时和续期
- 智能导航提示

---

## 📋 标准模板

### 插件结构 (推荐)

```
your_plugin/
├── main.py                          # 主插件类
│   ├── __init__()                   # 初始化（使用 CacheManager）
│   ├── your_cmd()                   # 命令处理器
│   ├── handle_callback()            # 推荐：按钮回调处理
│   └── on_message()                 # 推荐：会话消息处理
│
├── handlers/
│   ├── session_handler.py           # 可选：会话处理器
│   │   ├── _build_menu_response()   # 统一菜单构建
│   │   ├── start_xxx_menu()         # 启动菜单
│   │   └── handle_session_message() # 处理会话消息
│   │
│   └── response_builder.py          # 推荐：响应构建器（继承 BaseResponseBuilder）
│       ├── build_xxx_menu()         # 主菜单
│       ├── build_submenu_response() # 子菜单
│       └── build_detail_response()  # 详情页
│
├── metadata.yaml                    # 必需：插件元数据
└── README.md                        # 必需：插件说明
```

**注意**:
- ❌ 不再需要 `_get_platform_capabilities()` - 使用通用模块
- ❌ 不再需要 `message_editor.py` - 使用通用模块
- ✅ 响应构建器应继承 `BaseResponseBuilder`

---

## 🔧 通用模块使用

### 1. 平台能力检测 ✅ 必需

使用通用模块自动检测平台能力：

```python
from common import get_platform_capabilities

# 获取平台能力
capabilities = get_platform_capabilities(event, "YourPlugin")

# 使用能力
if capabilities['supports_buttons']:
    # 按钮模式
    keyboard = create_inline_keyboard()
else:
    # 会话模式
    message += "\n回复 1 选择功能1"
```

**支持的平台**:
- **按钮模式**: Telegram, Discord
- **会话模式**: 飞书, 微信, QQ, 企业微信, 钉钉

---

### 2. 会话管理器 ✅ 必需

使用通用会话管理器统一处理会话生命周期：

```python
from common import SessionManager

# 初始化
session_manager = SessionManager(timeout_minutes=1)

# 注册会话处理器
async def handle_menu(session_id, message, session, **context):
    # 处理菜单会话
    return result

session_manager.register_handler('menu', handle_menu)

# 创建会话
session = session_manager.create_session(
    session_id="user_123",
    session_type="menu",
    user_id="user_123",
    capabilities={"supports_buttons": False}
)

# 获取会话（自动续期）
session = session_manager.get_session(session_id, renew=True)

# 更新会话
session_manager.update_session(session_id, step=1, data={'action': 'search'})

# 结束会话
session_manager.end_session(session_id)
```

**特性**:
- ✅ 统一的会话管理
- ✅ 自动过期和续期
- ✅ 步骤历史记录
- ✅ 类型处理器注册
- ✅ 降级方案支持

---

### 3. 飞书消息辅助类 ✅ 推荐（飞书平台）

使用飞书消息辅助类解决消息ID获取和自动清理问题：

```python
from common import LarkMessageHelper

# 发送并跟踪消息
message_id = await LarkMessageHelper.send_and_track(
    event, 
    "欢迎使用！", 
    session=session,
    auto_cleanup=True  # 自动删除旧消息
)

# 退出时清理
await LarkMessageHelper.cleanup_on_exit(event, session)

# 判断是否应该使用
if LarkMessageHelper.should_use_lark_helper(event):
    # 使用飞书特殊处理
    await LarkMessageHelper.send_and_track(...)
else:
    # 使用通用方式
    yield event.plain_result(...)
```

**特性**:
- ✅ 自动获取消息ID
- ✅ 自动删除旧消息
- ✅ 退出时清理消息
- ✅ 降级方案支持
- ✅ 多种消息类型（post/text）

**收益**:
- 📉 减少 70% 的飞书特殊处理代码
- ✅ 统一的消息清理逻辑
- ✅ 更容易维护

---

### 5. 消息编辑器 ✅ 必需

使用通用消息编辑器统一处理消息发送、编辑和自动清理：

```python
from common import MessageEditor

# 基础用法（不清理旧消息）
async for result in MessageEditor.edit_or_send(event, message, keyboard):
    yield result

# 高级用法（自动清理旧消息 - 推荐用于会话模式）
session = self.session_handler.get_session(session_id)
async for result in MessageEditor.edit_or_send(
    event, message, keyboard,
    session_context=session,  # 传入会话上下文
    auto_cleanup=True         # 启用自动清理
):
    yield result
```

**特性**:
- **按钮平台** (Telegram/Discord): 编辑消息 → 界面整洁
- **会话平台** (飞书/QQ等): 发送新消息 + 删除旧消息 → 界面整洁
- **自动降级**: 不支持删除的平台自动跳过清理
- **静默失败**: 删除失败不影响核心功能

**⚠️ 飞书平台特殊说明**:

由于生成器函数的限制，`MessageEditor` 在飞书平台上**无法可靠获取消息ID**。推荐在飞书平台上使用**插件层面的手动清理**：

```python
# 飞书平台推荐方案：直接调用API
from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

platform_name = (event.get_platform_name() or "").lower()

if platform_name == "lark":
    # 1. 删除旧消息
    if session and session.get('last_message_id'):
        await event.delete_message(session['last_message_id'])
    
    # 2. 直接调用飞书API发送消息
    if isinstance(event, LarkMessageEvent) and hasattr(event, 'bot'):
        req = CreateMessageRequest.builder() \
            .receive_id_type("open_id") \
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(event.get_sender_id())
                .msg_type("post")
                .content('{"zh_cn":{"title":"","content":[[{"tag":"md","text":"' + 
                        message.replace('"', '\\"').replace('\n', '\\n') + '"}]]}}')
                .build()
            ).build()
        
        # 3. 发送并保存消息ID
        resp = await event.bot.im.v1.message.acreate(req)
        if resp and resp.success():
            session['last_message_id'] = resp.data.message_id
            event.stop_event()
            return
else:
    # 其他平台使用 MessageEditor
    async for ret in MessageEditor.edit_or_send(event, message, keyboard):
        yield ret
```

**退出时清理消息**:

```python
# 在 session_handler 中标记退出
if message in ['0', '退出']:
    session['_exiting'] = True
    return "✅ 已退出签到会话"

# 在 main.py 中检测退出并删除消息
if session and session.get('_exiting'):
    if session.get('last_message_id'):
        await event.delete_message(session['last_message_id'])
    event.stop_event()
    return  # 不发送退出消息，保持界面整洁
```

**平台删除能力**:
| 平台 | 支持删除 | 时间限制 | 推荐方案 |
|------|---------|---------|---------|
| Telegram | ✅ | 无限制 | MessageEditor |
| Discord | ✅ | 无限制 | MessageEditor |
| 飞书 | ✅ | 24小时 | **手动清理** ⭐ |
| QQ | ✅ | 2分钟 | MessageEditor |
| 企业微信 | ✅ | 5分钟 | MessageEditor |
| 钉钉 | ✅ | 24小时 | MessageEditor |
| 微信公众号 | ❌ | - | 不支持 |

---

### 3. 导航提示模块 ✅ 推荐

使用统一的导航提示模块生成标准化的导航提示：

```python
from common import NavigationHint

# 基础用法
hint = NavigationHint.get_hint(
    step=0,              # 0=主菜单, 1=一级子菜单, 2=二级子菜单
    supports_buttons=False,
    timeout_minutes=1
)
# 输出: "💡 0-退出\n💡 请输入数字选择功能\n⏱️ 请在 1 分钟内输入"

# 分页导航
hint = NavigationHint.get_pagination_hint(
    current_page=1,
    total_pages=5,
    step=1,
    supports_buttons=False
)
# 输出: "💡 p-上页 | n-下页 | b-返回 | 0-退出"

# 详情页分页导航
hint = NavigationHint.get_detail_pagination_hint(
    current_index=3,
    total_count=10,
    supports_buttons=False
)
# 输出: "💡 p-上一个 | n-下一个 | b-返回 | 0-退出"

# 从 Pagination 对象生成
from common import Pagination
pagination = Pagination(items, page=1, page_size=5)
hint = NavigationHint.from_pagination(pagination, step=1, supports_buttons=False)
```

**智能导航规则**:
- **主菜单 (step=0)**: 只显示 `0-退出`
- **一级子菜单 (step=1)**: 显示 `b-返回 | 0-退出`
- **二级子菜单 (step=2)**: 显示 `h-首页 | b-返回 | 0-退出`
- **分页场景**: 自动添加 `p-上页 | n-下页`
- **详情页**: 使用 `p-上一个 | n-下一个`

**优势**:
- ✅ 统一的导航体验
- ✅ 智能的层级感知
- ✅ 避免冗余提示
- ✅ 易于维护

---

### 4. 响应构建器 ✅ 推荐

继承通用基类实现插件特定的响应构建器：

```python
from common import BaseResponseBuilder

class YourPluginResponseBuilder(BaseResponseBuilder):
    """插件响应构建器 - 继承通用基类"""
    
    def build_main_menu(self, message: str):
        """构建主菜单"""
        buttons = [
            [
                {"text": "📝 功能1", "callback_data": "plugin:action1"},
                {"text": "📊 功能2", "callback_data": "plugin:action2"}
            ]
        ]
        
        # 使用基类方法
        return self.build_response(
            message=message,
            buttons=buttons,
            add_navigation=True,
            navigation_callback_prefix="plugin:"
        )
    
    def build_submenu(self, content: str, quick_inputs: List = None):
        """构建子菜单"""
        buttons = []
        
        # 添加快捷输入按钮
        if quick_inputs:
            for i in range(0, len(quick_inputs), 3):
                buttons.append(quick_inputs[i:i+3])
        
        # 使用基类的导航按钮
        nav_buttons = self.build_navigation_buttons(
            show_home=True,
            show_exit=True,
            home_callback="plugin:home",
            exit_callback="plugin:exit"
        )
        buttons.append(nav_buttons)
        
        return self.build_response(content, buttons, add_navigation=False)
```

**基类提供的方法**:
- `build_response()` - 构建通用响应
- `build_navigation_buttons()` - 构建导航按钮
- `build_pagination_buttons()` - 构建分页按钮
- `is_button_mode()` - 判断是否按钮模式
- `is_session_mode()` - 判断是否会话模式
- `create_keyboard()` - 创建键盘

---

### 5. 缓存管理 ✅ 推荐

使用通用缓存管理器处理临时数据：

```python
from common import CacheManager

# 初始化
def __init__(self, context):
    super().__init__(context)
    self.cache = CacheManager(default_ttl=600)  # 10分钟缓存

# 设置缓存
cache_key = f"search:{keyword}:{page}"
self.cache.set(cache_key, results, ttl=600)

# 获取缓存
results = self.cache.get(cache_key)

# 或使用 get_or_set（推荐）
results = self.cache.get_or_set(
    cache_key,
    lambda: self._do_search(keyword, page),
    ttl=600
)
```

**优势**:
- ✅ 自动过期处理
- ✅ 线程安全
- ✅ 统一的缓存管理

---

### 6. 工具函数 ✅ 可选

#### platform_utils
```python
from common import platform_utils

# 平台判断
if platform_utils.is_telegram(event):
    # Telegram 特殊处理
    pass

# 获取信息
user_id = platform_utils.get_user_id(event)
user_name = platform_utils.get_user_name(event)
is_group = platform_utils.is_group_message(event)
```

#### message_formatter
```python
from common import message_formatter

# 格式化标题
title = message_formatter.format_title("标题", "📝")

# 格式化列表
items = message_formatter.format_list(["项1", "项2"], numbered=True)

# 截断文本
text = message_formatter.truncate_text(text, max_length=100)
```

---

## 📝 完整示例

### 最小插件示例

```python
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Plain, Image
from astrbot.core.utils.callback_router import CallbackRouter, callback_handler, auto_stop_event
from common import (
    get_platform_capabilities,
    MessageEditor,
    BaseResponseBuilder,
    CacheManager
)

class MyResponseBuilder(BaseResponseBuilder):
    """插件响应构建器"""
    def build_main_menu(self, message):
        buttons = [[
            {"text": "功能1", "callback_data": "myplugin:func1"},
            {"text": "功能2", "callback_data": "myplugin:func2"}
        ]]
        return self.build_response(message, buttons, add_navigation=True, navigation_callback_prefix="myplugin:")

@register("myplugin", "Author", "Description", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context):
        super().__init__(context)
        self.cache = CacheManager(ttl=600)
        CallbackRouter.register("myplugin", self.handle_callback, plugin_instance=self)
    
    @filter.command("cmd")
    async def my_command(self, event: AstrMessageEvent):
        # 1. 获取平台能力
        capabilities = get_platform_capabilities(event, "MyPlugin")
        
        # 2. 构建响应
        builder = MyResponseBuilder(capabilities)
        message, keyboard = builder.build_main_menu("欢迎使用！")
        
        # 3. 发送响应
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    @callback_handler("myplugin")
    @auto_stop_event
    async def handle_callback(self, event: AstrMessageEvent, data: str = ""):
        # 处理回调
        capabilities = get_platform_capabilities(event, "MyPlugin")
        builder = MyResponseBuilder(capabilities)
        # ... 处理逻辑
```

---

## 📚 参考资源

### 文档
- [通用模块使用指南](../data/plugins/common/README_COMMON_MODULES.md)
- [迁移指南](./COMMON_MODULES_MIGRATION_GUIDE.md)
- [平台配置更新说明](./PLATFORM_CONFIGURATION_UPDATE.md)

### 示例插件
- **签到插件**: `data/plugins/astrbot_plugin_checkin/` - 完美示例 ⭐⭐⭐⭐⭐
- **豆瓣插件**: `data/plugins/astrbot_plugin_douban/` - 完美示例 ⭐⭐⭐⭐⭐

---

## ✅ 开发检查清单

### 必需项
- [ ] 使用 `get_platform_capabilities()` 检测平台能力
- [ ] 使用 `SessionManager` 管理会话 ⭐ v2.2
- [ ] 使用 `NavigationHandler` 处理导航命令 ⭐ v2.3
- [ ] 使用 `MessageEditor.edit_or_send()` 发送/编辑消息
- [ ] 使用 `@callback_handler` 装饰器处理回调
- [ ] 使用 `@auto_stop_event` 装饰器停止事件传播

### 推荐项
- [ ] 响应构建器继承 `BaseResponseBuilder`
- [ ] 使用 `LarkMessageHelper` 处理飞书平台消息 ⭐ v2.2
- [ ] 使用 `NavigationHint` 生成统一导航提示
- [ ] 使用 `CacheManager` 管理缓存
- [ ] 使用 `platform_utils` 工具函数
- [ ] 使用 `message_formatter` 格式化消息

### 避免项
- [ ] ❌ 不要实现 `_get_platform_capabilities()` 方法
- [ ] ❌ 不要创建 `message_editor.py` 文件
- [ ] ❌ 不要创建 `session_handler.py` 中的会话管理代码 ⭐ v2.2
- [ ] ❌ 不要手动实现导航命令处理逻辑 ⭐ v2.3
- [ ] ❌ 不要手动实现飞书消息ID获取和删除 ⭐ v2.2
- [ ] ❌ 不要手动管理缓存字典
- [ ] ❌ 不要重复实现已有的通用功能
- [ ] ❌ 不要硬编码导航提示文本

---

**更新日期**: 2025-11-23  
**版本**: v2.3  
**基于**: 签到插件 v2.3 + 豆瓣插件 v1.0

**v2.3 更新内容** ⭐ 重大更新:
- ✅ **新增 NavigationHandler** - 统一导航命令处理器，减少 60% 导航代码
- ✅ 完善导航回调机制，支持自定义导航逻辑
- ✅ 优化会话导航体验

**v2.2 更新内容** ⭐ 重大更新:
- ✅ **新增 SessionManager** - 统一会话管理器，减少 80% 重复代码
- ✅ **新增 LarkMessageHelper** - 飞书消息辅助类，减少 70% 飞书特殊处理代码
- ✅ 新增 NavigationHint 统一导航提示模块
- ✅ 新增飞书平台消息自动清理最佳实践
- ✅ 新增退出时清理消息的标准实现
- ✅ 完善消息ID保存和删除的完整流程
- ✅ 优化会话模式下的用户体验

**v2.1 更新内容**:
- ✅ 新增 NavigationHint 统一导航提示模块
- ✅ 新增飞书平台消息自动清理最佳实践
- ✅ 新增退出时清理消息的标准实现

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

**按钮模式（Telegram/Discord）**

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
💡 0-退出

💡 请输入数字选择功能
⏱️ 请在 1 分钟内输入
```

子菜单（step>0）：
```
━━━━━━━━━━━━━━━━━━
💡 h-首页 | b-返回 | 0-退出
⏱️ 请在 1 分钟内输入
```

分页菜单：
```
━━━━━━━━━━━━━━━━━━
💡 p-上页 | n-下页 | h-首页 | 0-退出
```

**统一导航键定义**：
| 键 | 功能 | 说明 |
|---|------|------|
| `0` | 退出 | 退出当前会话 |
| `h` | 首页 | 返回主菜单（Home） |
| `b` | 返回 | 返回上级菜单（Back） |
| `n` | 下页 | 下一页（Next） |
| `p` | 上页 | 上一页（Previous） |

**注意**：使用字母键避免与序号（1-15）冲突

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
            
            # ✅ 优雅退出：编辑原消息，移除按钮，而不是发送新消息
            async for ret in MessageEditor.edit_or_send(event, "✅ 已退出"):
                yield ret
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
        # ✅ 优雅退出：编辑原消息，移除按钮
        async for ret in MessageEditor.edit_or_send(event, "✅ 已退出"):
            yield ret
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

## 🐛 常见问题与解决方案

### 问题 1: 命令消息被 `on_message` 重复处理

**现象：**
- 在 Telegram 等平台上，用户输入 `/签` 后，会话处理器提示"请输入有效的数字"
- 命令执行成功，但消息内容（去掉 `/` 后）被当作会话输入处理

**原因：**
不同平台的命令处理机制不同：
- **Telegram**: 命令处理后，会将命令消息（去掉 `/`）再次传递给 `on_message`
- **飞书**: 命令处理后，不会再次传递

**错误方案 ❌：**
```python
# 使用时间判断（不可靠）
if time_since_creation < 3 and message == "签":
    return  # 用户快速点击按钮时会失败
```

**正确方案 ✅：**
```python
# 基于会话状态判断
current_step = session.get('step', 0)
step_history = session.get('step_history', [])

# 如果在主菜单（step=0）且没有步骤历史，说明会话刚创建
# 如果消息是命令关键词，则跳过（这是命令消息的重复传递）
if current_step == 0 and len(step_history) == 0 and message_str in ['签', 'checkin']:
    logger.debug(f"跳过 - 会话刚创建且是命令关键词")
    return
```

**优势：**
- ✅ 不依赖时间，无论用户操作多快都准确
- ✅ 基于会话的实际状态判断
- ✅ 适用于所有平台

---

### 问题 2: 命令处理器未停止事件传播

**现象：**
- 命令执行成功并发送了消息，但消息继续传播到 `on_message` 或 LLM
- 导致重复处理或错误提示

**原因：**
在使用 `yield` 发送消息后，没有正确调用 `event.stop_event()`

**错误示例 ❌：**
```python
@filter.command("签")
async def checkin_cmd(self, event):
    # 发送消息
    if keyboard:
        yield event.chain_result([Plain(message_text), keyboard])
    else:
        yield event.plain_result(message_text)
    # ❌ 没有停止事件传播，消息会继续传播
```

**正确方案 ✅：**
```python
@filter.command("签")
async def checkin_cmd(self, event):
    # 先停止事件传播
    event.stop_event()
    
    # 然后发送消息
    if keyboard:
        yield event.chain_result([Plain(message_text), keyboard])
    else:
        yield event.plain_result(message_text)
```

**关键点：**
- ✅ 在 `yield` **之前**调用 `event.stop_event()`
- ✅ 确保所有分支都调用了 `event.stop_event()`
- ✅ 飞书平台使用 `LarkMessageHelper` 时，在发送成功后调用 `event.stop_event()` 并 `return`

---

### 问题 3: 会话步骤（step）不一致

**现象：**
- 用户点击快捷按钮（如"昨天"）后，提示"无效的输入，请使用导航命令"
- 明明是有效的输入，却被拒绝

**原因：**
不同入口设置的会话步骤不一致：
- 按钮回调设置 `step=1`
- 菜单选项设置 `step=2`
- 会话处理器中 `step=1` 被定义为只读页面

**错误示例 ❌：**
```python
# 在 handle_callback 中
elif action == "makeup":
    self.session_handler._update_session(session_id, step=1, data={'action': 'makeup'})
    # ...

# 在 handle_session_message 中
if choice == 1:  # 补签
    self._update_session(session_id, step=2, data={'action': 'makeup'})
    # ...

# 在会话处理逻辑中
elif step == 1:
    # 处理1级子菜单的导航（查看记录/排行榜页面）
    # 这里不需要处理具体输入，因为记录/排行榜是只读的
    return "❌ 无效的输入，请使用导航命令：b-返回 | 0-退出"
```

**正确方案 ✅：**
```python
# 统一所有入口的 step 值
# step=0 - 主菜单
# step=1 - 一级子菜单（记录/排行榜，只读）
# step=2 - 二级子菜单（补签输入）

# 在 handle_callback 中
elif action == "makeup":
    self.session_handler._update_session(session_id, step=2, data={'action': 'makeup'})
    # ...

# 在 handle_session_message 中
if choice == 1:  # 补签
    self._update_session(session_id, step=2, data={'action': 'makeup'})
    # ...
```

**最佳实践：**
- ✅ 在代码注释中明确定义每个 step 的含义
- ✅ 确保所有入口（命令、按钮、菜单）设置相同的 step
- ✅ 使用常量定义 step 值，避免硬编码
- ✅ 在响应构建器中也使用相同的 step 值

**推荐做法：**
```python
# 定义 step 常量
class SessionStep:
    MAIN_MENU = 0      # 主菜单
    VIEW_ONLY = 1      # 只读页面（记录/排行榜）
    INPUT_REQUIRED = 2 # 需要输入（补签）

# 使用常量
self._update_session(session_id, step=SessionStep.INPUT_REQUIRED, data={'action': 'makeup'})
```

---

### 问题 4: 退出时未删除最后一条消息

**现象：**
- 用户输入 `0` 退出时，发送了"已退出"消息，但没有删除之前的菜单消息
- 导致消息堆积

**原因：**
退出逻辑中，会话在消息清理之前就被删除了

**错误示例 ❌：**
```python
async def _on_navigate_exit(self, session_id: str, session: Dict[str, Any]):
    """退出会话回调"""
    session['_exiting'] = True
    self._end_session(session_id)  # ❌ 立即删除会话
    return "✅ 已退出签到会话"

# 在 main.py 中
if is_exiting:
    await LarkMessageHelper.cleanup_on_exit(event, session)  # ❌ session 已经是 None
```

**正确方案 ✅：**
```python
async def _on_navigate_exit(self, session_id: str, session: Dict[str, Any]):
    """退出会话回调"""
    session['_exiting'] = True
    # ✅ 不在这里删除会话，让 main.py 在清理消息后删除
    return "✅ 已退出签到会话"

# 在 main.py 中
if is_exiting:
    # 先清理消息
    if LarkMessageHelper and LarkMessageHelper.should_use_lark_helper(event):
        await LarkMessageHelper.cleanup_on_exit(event, session)
    # 再删除会话
    self.session_handler._end_session(session_id)
    event.stop_event()
    return
```

**关键点：**
- ✅ 退出回调只设置标记，不删除会话
- ✅ 在 `main.py` 中检测退出标记后，先清理消息，再删除会话
- ✅ 清理完成后停止事件传播，不发送新消息

---

## 📊 支持的平台

### 按钮模式平台
- ✅ Telegram
- ✅ Discord

### 会话模式平台（使用文字菜单）
- ✅ 飞书（Lark）
- ✅ 微信（WeChat）
- ✅ QQ
- ✅ 企业微信（WeChat Work）
- ✅ 钉钉（DingTalk）

> **注意**：飞书平台的按钮功能尚不完善，目前使用会话模式（文字菜单），与微信公众号类似。

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

### 事件传播控制 ⭐ 重要
- [ ] 命令处理器在 `yield` 之前调用 `event.stop_event()`
- [ ] 回调处理器使用 `@auto_stop_event` 装饰器
- [ ] `on_message` 正确过滤命令消息（基于会话状态）
- [ ] 验证消息不会被重复处理或传播到 LLM

### 会话步骤一致性 ⭐ 重要
- [ ] 定义清晰的 step 含义（建议使用常量）
- [ ] 所有入口（命令/按钮/菜单）设置相同的 step
- [ ] 响应构建器使用相同的 step 值
- [ ] 会话处理逻辑与 step 定义一致

### 退出流程 ⭐ 重要
- [ ] 退出回调只设置标记，不删除会话
- [ ] 在 main.py 中先清理消息，再删除会话
- [ ] 清理完成后停止事件传播，不发送新消息
- [ ] 验证退出时旧消息被正确删除

### 测试验证
- [ ] 测试所有支持平台
- [ ] 验证按钮功能
- [ ] 验证会话功能
- [ ] 边界情况测试
- [ ] **Telegram 平台：验证命令不会被 on_message 重复处理**
- [ ] **飞书平台：验证退出时消息正确删除**
- [ ] **快捷按钮：验证输入被正确处理**

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
- **使用常量定义会话步骤（step）**

### 2. 错误处理
- 捕获所有异常
- 提供友好提示
- 记录详细日志
- **添加调试日志帮助排查问题**

### 3. 性能优化
- 缓存平台能力
- 及时清理会话
- 避免重复计算
- **使用回调路由器减少无效调用**

### 4. 用户体验
- 提示信息清晰
- 操作流程简单
- 响应速度快
- **退出时自动清理消息，避免堆积**

### 5. 事件传播控制 ⭐ 新增
- **命令处理器：在 `yield` 之前调用 `event.stop_event()`**
- **回调处理器：使用 `@auto_stop_event` 装饰器**
- **会话处理器：基于会话状态过滤命令消息**
- **验证消息不会被重复处理或传播到 LLM**

### 6. 会话管理 ⭐ 新增
- **定义清晰的 step 含义，使用常量避免硬编码**
- **确保所有入口设置相同的 step 值**
- **退出时先清理消息，再删除会话**
- **使用 `step_history` 判断会话是否刚创建**

---

## 🎉 总结

遵循本标准开发的插件将具有：

- ✅ 跨平台一致性
- ✅ 统一的交互体验
- ✅ 完善的功能支持
- ✅ 良好的代码质量
- ✅ 易于维护和扩展

**让我们一起建设更好的 AstrBot 插件生态！** 🚀
