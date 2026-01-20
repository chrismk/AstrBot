# 通用模块使用指南

## 📋 概述

`common` 目录提供了一套完整的通用模块，用于简化插件开发，避免重复代码。所有模块都经过跨平台测试，支持 Telegram、飞书、微信、QQ 等多个平台。

## 🎯 模块列表

### 1. 配额系统模块

#### QuotaValidator（配额验证器）
- **功能**：统一的配额检查和消费管理
- **文件**：`quota_validator.py`
- **使用场景**：限制用户使用频率、积分消费

```python
from common import QuotaValidator, DatabaseManager

db = DatabaseManager("data/quota_system.db")
validator = QuotaValidator(db)

# 检查配额
result = await validator.check_quota(user_id, "music_download", "music")
if result.allowed:
    # 执行操作
    await validator.consume_quota(user_id, "music_download", "music")
```

#### MembershipManager（会员管理器）
- **功能**：会员等级管理、权益管理
- **文件**：`membership_manager.py`

#### PointsManager（积分管理器）
- **功能**：积分增减、查询、历史记录
- **文件**：`points_manager.py`

#### DatabaseManager（数据库管理器）
- **功能**：SQLite 数据库操作封装
- **文件**：`database_manager.py`

---

### 2. 平台相关模块

#### PlatformCapabilities（平台能力检测）✨
- **功能**：自动检测平台能力（按钮/会话模式）
- **文件**：`platform_capabilities.py`
- **使用场景**：所有需要跨平台适配的插件

```python
from common import get_platform_capabilities

capabilities = get_platform_capabilities(event, "MyPlugin")

if capabilities['supports_buttons']:
    # 使用按钮模式
    keyboard = create_inline_keyboard()
else:
    # 使用会话模式
    message += "\n回复 1 选择功能1"
```

**支持的平台：**
- **按钮模式**：Telegram、Discord
- **会话模式**：飞书、微信、QQ、企业微信、钉钉

#### MessageEditor（消息编辑器）✨
- **功能**：跨平台消息编辑和发送
- **文件**：`message_editor.py`
- **使用场景**：需要更新消息内容的场景

```python
from common import MessageEditor

# 自动选择编辑或发送
async for result in MessageEditor.edit_or_send(event, "更新后的消息", keyboard):
    yield result
```

**特性：**
- Telegram：支持消息编辑
- 飞书：支持卡片更新
- 其他平台：自动降级为发送新消息

#### platform_utils（平台工具函数）
- **功能**：便捷的平台判断和信息获取
- **文件**：`platform_utils.py`

```python
from common import platform_utils

# 平台判断
if platform_utils.is_telegram(event):
    # Telegram 特殊处理
    pass

# 获取信息
chat_id = platform_utils.get_chat_id(event)
user_name = platform_utils.get_user_name(event)
is_group = platform_utils.is_group_message(event)
```

---

### 3. 交互相关模块

#### BaseResponseBuilder（响应构建器基类）✨
- **功能**：跨平台响应构建，自动适配按钮/会话模式
- **文件**：`response_builder.py`
- **使用场景**：构建菜单、列表、详情页

```python
from common import BaseResponseBuilder, get_platform_capabilities

capabilities = get_platform_capabilities(event, "MyPlugin")
builder = BaseResponseBuilder(capabilities)

# 构建响应
message, keyboard = builder.build_response(
    message="欢迎使用",
    buttons=[[
        {"text": "功能1", "callback_data": "plugin:func1"},
        {"text": "功能2", "callback_data": "plugin:func2"}
    ]],
    add_navigation=True,
    navigation_callback_prefix="plugin:"
)

# 发送
if keyboard:
    yield event.chain_result([Plain(message), keyboard])
else:
    yield event.plain_result(message)
```

**核心方法：**
- `build_response()` - 构建通用响应
- `create_keyboard()` - 创建键盘
- `build_navigation_buttons()` - 构建导航按钮
- `build_pagination_buttons()` - 构建分页按钮
- `format_session_navigation()` - 格式化会话模式导航

**插件可以继承此类扩展：**
```python
from common import BaseResponseBuilder

class MyResponseBuilder(BaseResponseBuilder):
    def build_custom_menu(self, data):
        # 自定义菜单构建逻辑
        buttons = [[...]]
        return self.build_response(message, buttons)
```

#### message_formatter（消息格式化工具）
- **功能**：统一的消息格式化函数
- **文件**：`message_formatter.py`

```python
from common import message_formatter

# 格式化标题
title = message_formatter.format_title("签到系统", "📝")

# 格式化列表
items = message_formatter.format_list(["项目1", "项目2"], numbered=True)

# 格式化表格
table = message_formatter.format_table(
    headers=["姓名", "积分"],
    rows=[["张三", "100"], ["李四", "200"]]
)

# 截断文本
text = message_formatter.truncate_text("很长的文本...", max_length=50)
```

---

### 4. 工具模块

#### CacheManager（缓存管理器）
- **功能**：内存缓存，支持 TTL
- **文件**：`cache_manager.py`
- **使用场景**：临时数据缓存、搜索结果缓存

```python
from common import CacheManager

cache = CacheManager(default_ttl=3600)  # 默认1小时过期

# 设置缓存
cache.set("search_results", results, ttl=600)  # 10分钟过期

# 获取缓存
results = cache.get("search_results")

# 获取或创建
def expensive_operation():
    return "result"

result = cache.get_or_set("key", expensive_operation, ttl=300)

# 清理过期缓存
cache.clear_expired()
```

---

## 🚀 快速开始

### 最小示例插件

```python
from astrbot.api import Star, register, filter, AstrMessageEvent, logger
from astrbot.core.message.components import Plain
from common import (
    get_platform_capabilities,
    BaseResponseBuilder,
    MessageEditor
)

@register("example", "Author", "示例插件", "1.0.0")
class ExamplePlugin(Star):
    
    @filter.command("示例")
    async def example_cmd(self, event: AstrMessageEvent):
        """示例命令"""
        # 1. 获取平台能力
        capabilities = get_platform_capabilities(event, "Example")
        
        # 2. 构建响应
        builder = BaseResponseBuilder(capabilities)
        message, keyboard = builder.build_response(
            message="欢迎使用示例插件！",
            buttons=[[
                {"text": "功能1", "callback_data": "example:func1"},
                {"text": "功能2", "callback_data": "example:func2"}
            ]],
            add_navigation=True,
            navigation_callback_prefix="example:"
        )
        
        # 3. 发送响应
        if keyboard:
            yield event.chain_result([Plain(message), keyboard])
        else:
            yield event.plain_result(message)
```

---

## 📚 完整示例

查看以下插件的实现作为参考：
- **签到插件**：`astrbot_plugin_checkin/`
- **豆瓣插件**：`astrbot_plugin_douban/`

---

## 🔧 开发建议

### 1. 平台能力检测
**始终使用** `get_platform_capabilities()` 而不是手动判断平台：

```python
# ❌ 不推荐
if event.get_platform_name() == "telegram":
    # ...

# ✅ 推荐
capabilities = get_platform_capabilities(event, "MyPlugin")
if capabilities['supports_buttons']:
    # ...
```

### 2. 消息编辑
**始终使用** `MessageEditor.edit_or_send()` 而不是平台特定代码：

```python
# ❌ 不推荐
if platform == "telegram":
    await event.client.edit_message(...)
else:
    yield event.plain_result(...)

# ✅ 推荐
async for result in MessageEditor.edit_or_send(event, message, keyboard):
    yield result
```

### 3. 响应构建
**继承** `BaseResponseBuilder` 而不是从零实现：

```python
# ✅ 推荐
from common import BaseResponseBuilder

class MyResponseBuilder(BaseResponseBuilder):
    def build_my_menu(self, data):
        # 使用基类方法
        buttons = self.build_navigation_buttons()
        return self.build_response(message, [buttons])
```

### 4. 缓存使用
对于频繁访问的数据，使用缓存：

```python
from common import CacheManager

cache = CacheManager(ttl=600)  # 10分钟缓存

# 搜索结果缓存
cache_key = f"search:{keyword}:{page}"
results = cache.get(cache_key)
if not results:
    results = await search_api(keyword, page)
    cache.set(cache_key, results)
```

---

## 📊 模块依赖关系

```
platform_capabilities (基础)
    ↓
message_editor (依赖平台能力)
    ↓
response_builder (依赖平台能力)
    ↓
插件实现
```

---

## 🆕 版本历史

### v1.0.0 (2025-11-22)
- ✅ 提取 `PlatformCapabilities` - 平台能力检测
- ✅ 提取 `MessageEditor` - 消息编辑器
- ✅ 提取 `BaseResponseBuilder` - 响应构建器基类
- ✅ 新增 `platform_utils` - 平台工具函数
- ✅ 新增 `message_formatter` - 消息格式化工具
- ✅ 新增 `CacheManager` - 缓存管理器

---

## 💡 贡献指南

如果你发现可以提取的通用功能，欢迎贡献！

1. 确保功能在多个插件中重复出现
2. 提取为通用模块，添加文档和示例
3. 更新 `__init__.py` 导出
4. 更新此 README

---

## 📞 支持

如有问题，请查看：
- [插件开发标准](../../../docs/README_插件开发标准.md)
- [平台配置更新说明](../../../docs/PLATFORM_CONFIGURATION_UPDATE.md)
- 参考示例插件实现
