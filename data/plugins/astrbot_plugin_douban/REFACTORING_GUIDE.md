# AstrBot 插件标准化重构指南

> 基于豆瓣插件重构经验总结的最佳实践文档

## 目录

1. [装饰器使用规范](#1-装饰器使用规范)
2. [配额系统集成](#2-配额系统集成)
3. [会话管理标准化](#3-会话管理标准化)
4. [导航系统实现](#4-导航系统实现)
5. [消息处理最佳实践](#5-消息处理最佳实践)
6. [平台兼容性处理](#6-平台兼容性处理)
7. [代码规范](#7-代码规范)

---

## 1. 装饰器使用规范

### 1.1 命令处理器装饰器顺序

**正确顺序**：`@filter.command` → `@auto_stop_command`

```python
@filter.command(command_name="豆", command_alias=["douban"])
@auto_stop_command
async def handle_search_command(self, event: AstrMessageEvent, keyword: str = ""):
    """处理搜索命令"""
    pass
```

**错误示例**：
```python
# ❌ 错误：装饰器顺序反了
@auto_stop_command
@filter.command(command_name="豆")
async def handle_search_command(self, event: AstrMessageEvent):
    pass
```

### 1.2 回调处理器装饰器顺序

**正确顺序**：`@filter.command("callback")` → `@callback_handler(prefix)` → `@auto_stop_event`

```python
@filter.command("callback")
@callback_handler("douban")
@auto_stop_event
async def handle_callback(self, event: AstrMessageEvent, action: str, **params):
    """处理回调"""
    pass
```

### 1.3 回调数据格式

**标准格式**：`prefix_action_param1_param2`

```python
# 示例
callback_data = "douban_detail_movie_12345"
callback_data = "douban_page_2_book_keyword"
callback_data = "douban_switch_movie_keyword_1"
```

**解析方式**：
```python
@callback_handler("douban")
async def handle_callback(self, event: AstrMessageEvent, action: str, **params):
    # action 已自动去除前缀 "douban_"
    if action == "detail":
        douban_type = params.get('douban_type')
        douban_id = params.get('douban_id')
    elif action == "page":
        page = int(params.get('page', 1))
```

---

## 2. 配额系统集成

### 2.1 配额规则注册

**使用 `QuotaValidator.register_quota_rules()` 方法**：

```python
def _register_quota_rules(self):
    """注册配额规则"""
    if not self.quota_validator:
        return
    
    quota_rules = {
        'douban_search': {
            'free': {'daily_limit': -1, 'points_cost': 0},      # 无限制
            'basic': {'daily_limit': -1, 'points_cost': 0},
            'premium': {'daily_limit': -1, 'points_cost': 0},
            'description': '豆瓣搜索（无限制）'
        },
        'douban_view': {
            'free': {'daily_limit': 30, 'points_cost': 1},      # 每日30次
            'basic': {'daily_limit': 100, 'points_cost': 1},
            'premium': {'daily_limit': -1, 'points_cost': 0},
            'description': '查看豆瓣详情'
        }
    }
    
    self.quota_validator.register_quota_rules(
        plugin_name='douban',
        rules=quota_rules,
        override=True  # 强制更新规则
    )
```

**关键点**：
- `daily_limit: -1` 表示无限制
- `points_cost: 0` 表示不消耗积分
- `override=True` 确保规则更新生效

### 2.2 配额检查和消费

**分离检查和消费**：

```python
# 1. 检查配额
quota_result = await self.quota_validator.check_quota(
    user_id=user_id,
    action_type='douban_view',
    plugin_name='douban'
)

if not quota_result.allowed:
    yield event.plain_result(quota_result.message)
    return

# 2. 执行业务逻辑
# ...

# 3. 消费配额
await self.quota_validator.consume_quota(
    user_id=user_id,
    action_type='douban_view',
    plugin_name='douban',
    points_cost=quota_result.points_cost
)
```

**统计型配额**（不实际限制）：
```python
# 搜索命令：检查但不消费（用于统计）
quota_result = await self.quota_validator.check_quota(
    user_id=user_id,
    action_type='douban_search',
    plugin_name='douban'
)

# 消费0积分（仅统计）
await self.quota_validator.consume_quota(
    user_id=user_id,
    action_type='douban_search',
    plugin_name='douban',
    points_cost=0
)
```

---

## 3. 会话管理标准化

### 3.1 使用 SessionManager

**只使用 `SessionManager`，不要自己维护会话字典**：

```python
# ✅ 正确：使用 SessionManager
from common.session_manager import SessionManager

class MyPlugin:
    def __init__(self, context: Context):
        self.session_manager = SessionManager(timeout_minutes=5)
    
    async def create_session(self, event):
        self.session_manager.create_session(
            session_id=event.get_session_id(),
            session_type="my_plugin_session",
            user_id=event.get_sender_id(),
            step=0,  # 初始步骤
            data={'key': 'value'}
        )
```

**❌ 错误：自己维护会话**：
```python
# ❌ 不要这样做
class SessionHandler:
    def __init__(self):
        self.sessions = {}  # 不要自己维护
```

### 3.2 会话步骤管理

**使用 `step` 和 `step_history` 自动维护层级**：

```python
# 创建会话时设置初始步骤
self.session_manager.create_session(
    session_id=session_id,
    step=0,  # 主菜单
    ...
)

# 进入下级菜单时更新步骤
self.session_manager.update_session(
    session_id=session_id,
    step=1  # SessionManager 自动保存历史 [0]
)

# 返回上级
previous_step = self.session_manager.back_to_previous_step(session_id)
```

**步骤层级定义**：
- `step=0`: 主菜单（入口）
- `step=1`: 一级子菜单
- `step=2`: 二级子菜单
- `step=3+`: 更深层级

---

## 4. 导航系统实现

### 4.1 使用 NavigationHandler

**标准实现**：

```python
from common.navigation_handler import NavigationHandler
from common.navigation_hint import NavigationHint

class SessionHandler:
    def __init__(self, session_manager):
        self.session_manager = session_manager
        
        # 初始化导航处理器
        self.nav_handler = NavigationHandler(self.session_manager)
        
        # 注册导航回调
        self.nav_handler.register_callbacks(
            on_home=self._on_navigate_home,
            on_back=self._on_navigate_back,
            on_exit=self._on_navigate_exit
        )
    
    async def handle_session_message(self, session_id, message, session):
        # 使用 NavigationHandler 处理导航命令
        is_handled, result = await self.nav_handler.handle(
            session_id, message, session
        )
        if is_handled:
            return result
        
        # 处理其他业务逻辑
        # ...
```

### 4.2 导航回调实现

```python
async def _on_navigate_home(self, session_id: str, session: Dict[str, Any]):
    """返回首页回调"""
    # 重置步骤为0（主菜单）
    self.session_manager.update_session(
        session_id, 
        step=0, 
        save_history=False  # 不保存历史
    )
    return await self._show_main_menu(session)

async def _on_navigate_back(self, session_id: str, session: Dict[str, Any]):
    """返回上级回调"""
    # 使用 SessionManager 的步骤历史返回上级
    previous_step = self.session_manager.back_to_previous_step(session_id)
    return await self._show_previous_page(session)

async def _on_navigate_exit(self, session_id: str, session: Dict[str, Any]):
    """退出会话回调"""
    return "✅ 已退出"
```

### 4.3 使用 NavigationHint 生成提示

**自动根据步骤生成提示**：

```python
from common.navigation_hint import NavigationHint

# 根据当前步骤自动生成导航提示
current_step = session.get('step', 0)
hint = NavigationHint.get_hint(level=current_step)

# step=0 → "💡 0-退出"
# step=1 → "💡 b-返回 | 0-退出"
# step=2 → "💡 h-首页 | b-返回 | 0-退出"
```

**快捷方法**：
```python
# 主菜单提示
hint = NavigationHint.get_main_menu_hint()  # "💡 0-退出"

# 一级子菜单提示
hint = NavigationHint.get_sub_menu_hint()  # "💡 b-返回 | 0-退出"

# 二级子菜单提示
hint = NavigationHint.get_detail_hint()  # "💡 h-首页 | b-返回 | 0-退出"
```

**分页导航提示**：
```python
hint = NavigationHint.get_pagination_hint(
    has_prev=page > 1,
    has_next=page < total_pages,
    current_page=page,
    total_pages=total_pages,
    show_home=True,
    show_exit=True
)
```

---

## 5. 消息处理最佳实践

### 5.1 on_message 处理器标准实现

```python
@filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
async def on_message(self, event: AstrMessageEvent):
    """处理所有消息"""
    
    # 1. 检查事件是否已有结果（避免重复处理）
    if event.get_result():
        logger.debug("[Plugin] on_message: 跳过 - 事件已有结果")
        return
    
    message_text = (event.message_str or "").strip()
    if not message_text:
        return
    
    # 2. 跳过命令消息（以 / 开头）
    if message_text.startswith('/'):
        logger.debug(f"[Plugin] on_message: 跳过 - 是命令: {message_text}")
        return
    
    # 3. 跳过回调消息
    if message_text.startswith('callback '):
        logger.debug(f"[Plugin] on_message: 跳过 - 是回调: {message_text}")
        return
    
    session_id = event.get_session_id()
    
    # 4. 检查会话是否存在
    session = self.session_manager.get_session(session_id)
    if not session:
        logger.debug(f"[Plugin] on_message: 没有会话 - session_id={session_id}")
        
        # 【最佳实践】使用通用方法检测会话命令并提示会话已过期
        # 避免用户不知道会话超时而继续输入命令
        try:
            from common.navigation_handler import NavigationHandler
            if NavigationHandler.is_session_command(message_text):
                logger.info(f"[Plugin] 检测到会话命令但会话不存在 - message={message_text}")
                yield event.plain_result("❌ 会话已过期，请重新开始")
                event.stop_event()
                return
        except ImportError:
            # 降级方案：手动检测
            session_commands = ['h', 'H', 'home', '首页', 'b', 'B', 'back', '返回',
                               '0', 'q', 'Q', 'quit', '退出',
                               'p', 'P', 'prev', '上页', 'n', 'N', 'next', '下页']
            if message_text in session_commands or message_text.isdigit():
                logger.info(f"[Plugin] 检测到会话命令但会话不存在 - message={message_text}")
                yield event.plain_result("❌ 会话已过期，请重新开始")
                event.stop_event()
                return
        
        # 处理其他逻辑（如链接识别）
        return
    
    # 5. 特殊处理：跳过命令关键词重复传递
    # 某些平台（如飞书）在命令处理后会将命令消息再次传递
    session_data = session.get('data', {})
    if session_data and message_text.startswith('关键词'):
        logger.debug(f"[Plugin] on_message: 跳过 - 命令关键词重复")
        return
    
    # 6. 处理会话消息
    logger.debug(f"[Plugin] on_message: 检测到会话 - session_id={session_id}")
    result = await self.session_handler.handle_session_message(
        user_id=event.get_sender_id(),
        session_id=session_id,
        message=message_text
    )
    
    if result:
        # 处理返回结果
        if isinstance(result, str):
            yield event.plain_result(result)
        elif isinstance(result, tuple):
            message, keyboard = result
            yield event.chain_result([message, keyboard] if keyboard else [message])
        
        # 阻止事件传播
        event.stop_event()
        return
```

### 5.2 命令处理器最佳实践

```python
@filter.command(command_name="cmd", command_alias=["alias"])
@auto_stop_command
async def handle_command(self, event: AstrMessageEvent, param: str = ""):
    """命令处理器"""
    
    # 1. 获取用户信息
    user_id = event.get_sender_id()
    session_id = event.get_session_id()
    
    # 2. 检查配额
    if self.quota_validator:
        quota_result = await self.quota_validator.check_quota(
            user_id=user_id,
            action_type='action_name',
            plugin_name='plugin_name'
        )
        if not quota_result.allowed:
            yield event.plain_result(quota_result.message)
            return
    
    # 3. 显示加载提示
    loading_msg_id = await LoadingIndicator.show(event, 'process')
    
    try:
        # 4. 执行业务逻辑
        result = await self.do_something(param)
        
        # 5. 获取平台能力
        capabilities = get_platform_capabilities(event, "PluginName")
        
        # 6. 创建会话（如果需要）
        if not capabilities['supports_buttons']:
            self.session_manager.create_session(
                session_id=session_id,
                session_type="plugin_session",
                user_id=user_id,
                step=0,
                capabilities=capabilities,
                data={'result': result}
            )
        
        # 7. 发送响应
        yield event.plain_result(result)
        
        # 8. 消费配额
        if self.quota_validator:
            await self.quota_validator.consume_quota(
                user_id=user_id,
                action_type='action_name',
                plugin_name='plugin_name',
                points_cost=quota_result.points_cost
            )
    
    except Exception as e:
        logger.error(f"命令处理异常: {e}", exc_info=True)
        yield event.plain_result(f"❌ 处理失败: {e}")
    
    finally:
        # 9. 隐藏加载提示
        await LoadingIndicator.hide(event, loading_msg_id)
```

### 5.3 会话超时友好提示

**问题**：用户不知道会话已超时，继续输入会话命令（如 `h`、`b`、`0`、序号等），但没有任何反馈，体验不好。

**❌ 错误方案**：在 `on_message` 中检测会话命令并提示超时

```python
# ❌ 错误！不要这样做
async def on_message(self, event: AstrMessageEvent):
    session = self.session_manager.get_session(session_id)
    if not session:
        # 错误：多个插件并发执行时会冲突
        if NavigationHandler.is_session_command(message_text):
            yield event.plain_result("❌ 会话已过期，请重新开始")
            event.stop_event()
            return
```

**为什么错误**：
1. **插件并发冲突** - 多个插件的 `on_message` 并发执行，豆瓣插件不知道用户是否在使用签到插件的会话
2. **误判其他插件** - 用户输入 `1` 可能是签到插件的补签选择，但豆瓣插件会误判为序号并提示超时
3. **事件传播问题** - 一个插件 `stop_event()` 会影响其他插件的正常处理

**✅ 正确方案**：在 `SessionHandler.handle_session_message()` 中检测并提示

```python
# SessionHandler.handle_session_message()
async def handle_session_message(self, user_id: str, session_id: str, message: str):
    """处理会话消息"""
    # 获取会话
    session = self.session_manager.get_session(session_id)
    
    # ✅ 正确：在这里检测会话超时并提示
    if not session:
        return "❌ 会话已过期，请重新开始"
    
    # 处理会话消息...
    message = message.strip()
    
    # 使用 NavigationHandler 处理导航命令
    if self.nav_handler:
        is_handled, result = await self.nav_handler.handle(session_id, message, session)
        if is_handled:
            return result
    
    # 处理其他会话逻辑...
```

```python
# Plugin.on_message()
async def on_message(self, event: AstrMessageEvent):
    """处理消息"""
    session = self.session_manager.get_session(session_id)
    
    if session:
        # 有会话，处理会话消息
        result = await self.session_handler.handle_session_message(
            user_id, session_id, message
        )
        if result:
            yield event.plain_result(result)
            event.stop_event()
            return
    
    # ✅ 正确：没有会话，直接跳过，不要检测会话命令
    # 因为用户可能在使用其他插件的会话
    logger.debug(f"[Plugin] on_message: 没有会话，跳过处理")
    return
```

**为什么正确**：
1. **避免插件冲突** - 只有拥有会话的插件才会处理消息
2. **精准提示** - 只在用户确实使用过该插件会话时才提示超时
3. **不影响其他插件** - 没有会话的插件直接跳过，不干扰其他插件

**架构流程**：

```
用户输入 "1"
    ↓
多个插件的 on_message 并发执行
    ├─ 豆瓣插件: 没有会话 → 跳过 ✅
    ├─ 签到插件: 有会话 → 调用 SessionHandler ✅
    └─ 其他插件: 没有会话 → 跳过 ✅
    ↓
签到插件的 SessionHandler.handle_session_message()
    ├─ 会话存在 → 处理输入 "1" ✅
    └─ 会话过期 → 返回 "❌ 会话已过期，请重新开始" ✅
```

**效果对比**：

| 场景 | 错误方案（on_message检测） | 正确方案（SessionHandler检测） |
|------|--------------------------|------------------------------|
| 豆瓣会话超时，输入 `5` | 提示超时 ✅ | 提示超时 ✅ |
| 签到会话中，输入 `1` | **误判超时** ❌ | 正常处理 ✅ |
| 没有任何会话，输入 `h` | 提示超时（误报）❌ | 无反应 ✅ |
| 多插件并发 | **冲突** ❌ | 正常工作 ✅ |

**注意事项**：
- ✅ 在 `SessionHandler.handle_session_message()` 开头检测会话是否存在
- ✅ 使用通用提示语 `"❌ 会话已过期，请重新开始"`
- ❌ 不要在 `on_message` 中检测会话命令并提示超时
- ❌ 不要使用 `NavigationHandler.is_session_command()` 在 `on_message` 中判断

---

## 6. 平台兼容性处理

### 6.1 获取平台能力

```python
from common.platform_utils import get_platform_capabilities

capabilities = get_platform_capabilities(event, "PluginName")

# 返回字典包含：
# - platform_name: 平台名称（lark/telegram/qq等）
# - supports_buttons: 是否支持按钮
# - supports_markdown: 是否支持Markdown
# - supports_image_caption: 是否支持图片caption
```

### 6.2 按钮模式 vs 会话模式

**关键原则**：按钮模式不需要在内容中添加导航文本，因为导航已经通过按钮实现。

#### 6.2.1 详情页导航文本

```python
# 获取平台能力
capabilities = get_platform_capabilities(event, "Douban")
is_button_mode = capabilities.get('supports_buttons', False)

# 只在会话模式（非按钮模式）下添加导航文本
if in_session and not is_button_mode:
    from common.navigation_hint import NavigationHint
    comments_text += "\n\n━━━━━━━━━━━━━━━━━━"
    hint = NavigationHint.get_hint(level=current_step)
    comments_text += f"\n{hint}"
```

#### 6.2.2 搜索结果列表导航文本

在格式化搜索结果时，通过 `show_hints` 参数控制是否显示导航文本：

```python
# DoubanFormatter.format_search_results()
@staticmethod
def format_search_results(
    results: list, 
    search_type: str, 
    page: int, 
    page_size: int, 
    total: int,
    show_pagination: bool = True,
    timeout_minutes: int = 1,
    show_hints: bool = True  # 按钮模式下为 False
) -> Tuple[str, list]:
    """格式化搜索结果"""
    # ... 格式化结果 ...
    
    # 只在会话模式下显示导航提示
    if show_hints:
        lines.append("━━━━━━━━━━━━━━━━━━")
        hint = NavigationHint.build_full_hint(
            level=0,
            instruction="请输入序号查看详情",
            timeout_minutes=timeout_minutes,
            show_exit=True,
            show_prev=page > 1,
            show_next=page < total_pages
        )
        lines.append(hint)
    
    return "\n".join(lines), results
```

**在会话处理器中调用**：

```python
# SessionHandler._show_search_results()
capabilities = session.get('capabilities', {})
is_button_mode = capabilities.get('supports_buttons', False)

# 根据当前搜索类型生成切换提示
switch_hint = None
if not is_button_mode:  # 只在会话模式下显示切换提示
    if search_type == 'book':
        switch_hint = "s-搜电影"
    else:
        switch_hint = "s-搜图书"

message, _ = DoubanFormatter.format_search_results(
    results, search_type, page, PAGE_SIZE, total,
    show_pagination=True,
    timeout_minutes=self.SESSION_TIMEOUT_MINUTES,
    show_hints=not is_button_mode,  # 按钮模式不显示导航文本
    switch_hint=switch_hint  # 传入自定义切换提示
)
```

**效果对比**：

| 场景 | 按钮模式（Telegram/飞书） | 会话模式（QQ/微信） |
|------|------------------------|-------------------|
| 搜索结果列表 | 只显示结果 + 按钮 ✅ | 结果 + 导航文本 + 超时提示 ✅ |
| 详情页 | 图片 + 评论 + 按钮 ✅ | 图片 + 评论 + 导航文本 ✅ |
| 用户体验 | 简洁清爽 | 清晰明确 |

**平台对比**：

| 平台 | 支持按钮 | 导航方式 | 内容中是否显示导航文本 |
|------|---------|---------|---------------------|
| 飞书 | ✅ | 按钮 | ❌ 不显示 |
| Telegram | ✅ | 按钮 | ❌ 不显示 |
| QQ | ❌ | 文本命令 | ✅ 显示 |
| 微信 | ❌ | 文本命令 | ✅ 显示 |

#### 6.2.3 会话模式切换功能

**问题**：按钮模式有"搜电影"/"搜图书"按钮，但会话模式没有切换功能。

**解决方案**：添加 `s` 命令支持切换搜索类型。

**实现步骤**：

1. **在 SessionHandler 中处理切换命令**：

```python
# 处理切换类型命令
if message.lower() in ['s', 'switch', '切换']:
    return await self._handle_switch_type(session)

async def _handle_switch_type(self, session: Dict) -> Tuple[str, Any]:
    """处理切换搜索类型"""
    data = session['data']
    current_type = data.get('search_type', 'book')
    keyword = data.get('keyword', '')
    
    # 切换类型
    new_type = 'movie' if current_type == 'book' else 'book'
    
    # 重新搜索
    results, total = await self.douban_api.search_douban(keyword, new_type, 1)
    
    # 更新会话数据
    data['search_type'] = new_type
    data['page'] = 1
    data['results'] = results
    data['total'] = total
    
    return await self._show_search_results(session)
```

2. **在格式化器中添加自定义切换提示**：

```python
# 根据当前类型生成切换提示
switch_hint = None
if not is_button_mode:
    if search_type == 'book':
        switch_hint = "s-搜电影"  # 当前是图书，提示切换到电影
    else:
        switch_hint = "s-搜图书"  # 当前是电影，提示切换到图书

message, _ = DoubanFormatter.format_search_results(
    results, search_type, page, PAGE_SIZE, total,
    show_pagination=True,
    timeout_minutes=self.SESSION_TIMEOUT_MINUTES,
    show_hints=not is_button_mode,
    switch_hint=switch_hint  # 传入自定义切换提示
)
```

**效果展示**：

搜索图书时：
```
📚 图书搜索结果 (第1/200页，共3000条)

1. 宇宙 ⭐⭐⭐⭐ 9.3
...

━━━━━━━━━━━━━━━━━━
💡 请输入序号查看详情
💡 n-下页 | s-搜电影 | 0-退出
⏱️ 请在 1 分钟内输入
```

用户输入 `s` 后：
```
🎬 电影搜索结果 (第1/150页，共2250条)

1. 宇宙 ⭐⭐⭐⭐ 8.5
...

━━━━━━━━━━━━━━━━━━
💡 请输入序号查看详情
💡 n-下页 | s-搜图书 | 0-退出
⏱️ 请在 1 分钟内输入
```

**设计原则**：

1. **自定义切换文字** - 插件根据当前状态生成切换提示，而不是硬编码
2. **按钮模式不显示** - 按钮模式已有按钮，不需要文本提示
3. **会话模式显示** - 会话模式需要文本命令，显示清晰的切换提示
4. **灵活扩展** - 其他插件也可以使用相同的模式

**功能对比**：

| 功能 | 按钮模式 | 会话模式 |
|------|---------|---------|
| 切换类型 | 点击"搜电影"/"搜图书"按钮 | 输入 `s` 或 `切换` |
| 导航提示 | 不显示文本 | 显示 `s-搜电影` 或 `s-搜图书` |
| 用户体验 | 可视化按钮 | 文本命令 |

#### 6.2.4 详情页特殊操作导航

**问题**：详情页在按钮模式下有特殊操作按钮（搜索资源、AI解读、查看详情），但会话模式缺少对应的文本导航。

**解决方案**：为会话模式添加特殊操作的文本导航。

**实现步骤**：

1. **在详情页添加特殊操作导航提示**：

```python
# 如果在会话中且是会话模式（非按钮模式），添加导航提示
if in_session and comments_text and not is_button_mode:
    from common.navigation_hint import NavigationHint
    comments_text += "\n\n━━━━━━━━━━━━━━━━━━"
    
    # 添加特殊操作提示（对应按钮模式的操作按钮）
    comments_text += "\n💡 特殊操作："
    comments_text += "\n  • r-搜索资源"
    comments_text += "\n  • a-AI解读"
    comments_text += "\n  • d-查看详情"
    
    # 根据会话的 step 自动生成标准导航提示
    current_step = session.get('step', 0)
    hint = NavigationHint.get_hint(level=current_step)
    comments_text += f"\n{hint}"
```

2. **在 SessionHandler 中处理特殊操作命令**：

```python
# 处理详情页特殊操作命令
current_step = session.get('step', 0)
if current_step >= 1:  # 在详情页（step >= 1）
    if message.lower() in ['r', 'resource', '资源']:
        return "💡 搜索资源功能需要在按钮模式下使用，或访问豆瓣详情页"
    elif message.lower() in ['a', 'ai', '解读']:
        return "💡 AI解读功能需要在按钮模式下使用，或访问豆瓣详情页"
    elif message.lower() in ['d', 'detail', '详情']:
        # 返回豆瓣详情链接
        current_detail_id = data.get('current_detail_id')
        if current_detail_id:
            detail_url = f"https://book.douban.com/subject/{current_detail_id}/"
            return f"📖 豆瓣详情页：{detail_url}"
```

3. **保存详情ID供后续使用**：

```python
# 在选择详情时保存ID
data['current_detail_id'] = subject_id
self.session_manager.update_session(session_id, step=1)
```

**导航分类**：

| 导航类型 | 按钮模式 | 会话模式 |
|---------|---------|---------|
| **标准导航** | 返回、退出按钮 | b-返回、0-退出 |
| **特殊操作** | 🔍搜索资源、🤖AI解读、📖查看详情按钮 | r-资源、a-解读、d-详情 |

### 6.3 平台特定处理

#### 6.3.1 图片和键盘发送方式

**关键原则**：不同平台对图片+键盘的发送方式有不同要求。

**Telegram 平台**：

```python
# Telegram：图片和键盘一起发送
if comments_text:
    image_component.caption = comments_text
if keyboard:
    yield event.chain_result([image_component, keyboard])  # 一起发送
else:
    yield event.chain_result([image_component])
```

**飞书平台**：

```python
# 飞书：图片、文本、键盘分开发送（飞书适配器会自动调整顺序）
# 注意：飞书不支持 image caption，需要使用 Plain 组件
if comments_text:
    if keyboard:
        yield event.chain_result([image_component, Plain(comments_text), keyboard])
    else:
        yield event.chain_result([image_component, Plain(comments_text)])
else:
    if keyboard:
        yield event.chain_result([image_component, keyboard])
    else:
        yield event.chain_result([image_component])
```

**完整示例**：

```python
platform_name = capabilities.get('platform_name', '').lower()

# 构建操作按钮
builder = DoubanResponseBuilder(capabilities)
keyboard = builder.build_action_keyboard(douban_type, douban_id, None)

# 根据平台发送不同格式
if platform_name == "lark":
    # 飞书：图片在上，文字在下（飞书适配器已处理顺序）
    if comments_text:
        if keyboard:
            yield event.chain_result([image_component, Plain(comments_text), keyboard])
        else:
            yield event.chain_result([image_component, Plain(comments_text)])
    else:
        if keyboard:
            yield event.chain_result([image_component, keyboard])
        else:
            yield event.chain_result([image_component])
else:
    # Telegram等：使用caption，图片和键盘一起发送
    if comments_text:
        image_component.caption = comments_text
    if keyboard:
        yield event.chain_result([image_component, keyboard])
    else:
        yield event.chain_result([image_component])
```

**平台对比**：

| 平台 | 图片文本方式 | 键盘发送方式 | 原因 |
|------|------------|------------|------|
| Telegram | caption | 与图片一起 | 支持图片附带键盘 |
| 飞书 | Plain组件 | 与图片、文本一起 | 不支持caption，需要分开 |

**常见错误**：

❌ **错误**：Telegram 分开发送图片和键盘
```python
yield event.chain_result([image_component])
if keyboard:
    yield event.chain_result([keyboard])  # 键盘会被当作空消息
```

✅ **正确**：Telegram 一起发送图片和键盘
```python
if comments_text:
    image_component.caption = comments_text
if keyboard:
    yield event.chain_result([image_component, keyboard])
else:
    yield event.chain_result([image_component])
```

#### 6.3.2 飞书图片顺序

飞书平台的图片和文本顺序由飞书适配器自动处理：

```python
# 在 lark_event.py 中，飞书适配器会自动调整顺序
# 先添加图片（图片在上）
for img in images:
    content.append([img])

# 再添加文本（文本在下）
for text in text_parts:
    if text.strip():
        stage.append({"tag": "md", "text": text})
if stage:
    content.append(stage)
```

因此插件代码只需按照直观顺序编写：
```python
yield event.chain_result([image_component, Plain(comments_text), keyboard])
# 飞书适配器会自动调整为：图片 → 文本 → 按钮
```

## 7. 会话模式判断

```python
# 根据平台能力决定是否使用会话模式
if not capabilities['supports_buttons']:
    # 不支持按钮，使用会话模式
    self.session_manager.create_session(...)
else:
    # 支持按钮，直接显示内联按钮
    keyboard = builder.build_keyboard(...)
```

---

## 7. 代码规范

### 7.1 常量定义

**使用类常量替代魔法数字**：

```python
class MyPlugin:
    PAGE_SIZE = 15  # 每页显示数量
    CACHE_TTL = 600  # 缓存过期时间（秒）
    SESSION_TIMEOUT = 5  # 会话超时（分钟）
    
    def paginate(self, items, page):
        start = (page - 1) * self.PAGE_SIZE
        end = start + self.PAGE_SIZE
        return items[start:end]
```

### 7.2 日志记录

**使用统一的日志格式**：

```python
from astrbot.api import logger

# DEBUG: 调试信息
logger.debug(f"[Plugin] 操作详情 - param={value}")

# INFO: 重要操作
logger.info(f"[Plugin] 用户操作 - user_id={user_id}, action={action}")

# WARNING: 警告信息
logger.warning(f"[Plugin] 潜在问题 - {issue}")

# ERROR: 错误信息
logger.error(f"[Plugin] 操作失败: {e}", exc_info=True)
```

### 7.3 错误处理

**统一的错误处理模式**：

```python
try:
    # 业务逻辑
    result = await self.do_something()
    yield event.plain_result(result)

except ValueError as e:
    # 用户输入错误
    logger.warning(f"[Plugin] 输入错误: {e}")
    yield event.plain_result(f"❌ 输入错误: {e}")

except Exception as e:
    # 未预期的错误
    logger.error(f"[Plugin] 处理异常: {e}", exc_info=True)
    yield event.plain_result(f"❌ 处理失败，请稍后重试")

finally:
    # 清理资源
    await self.cleanup()
```

### 7.4 类型注解

**使用类型注解提高代码可读性**：

```python
from typing import Dict, List, Optional, Tuple, Any

async def handle_message(
    self,
    user_id: str,
    session_id: str,
    message: str
) -> Optional[Tuple[str, Any]]:
    """
    处理会话消息
    
    Args:
        user_id: 用户ID
        session_id: 会话ID
        message: 用户消息
    
    Returns:
        (消息文本, 键盘对象) 或 None
    """
    pass
```

---

## 8. 完整示例

### 8.1 插件主类结构

```python
from astrbot.api import *
from common.session_manager import SessionManager
from common.quota_validator import QuotaValidator
from common.platform_utils import get_platform_capabilities

class StandardPlugin(BasePlugin):
    """标准插件示例"""
    
    # 常量定义
    PAGE_SIZE = 15
    SESSION_TIMEOUT = 5
    
    def __init__(self, context: Context):
        super().__init__(context)
        
        # 初始化会话管理器
        self.session_manager = SessionManager(timeout_minutes=self.SESSION_TIMEOUT)
        
        # 初始化配额验证器
        self.quota_validator = QuotaValidator(context)
        self._register_quota_rules()
        
        # 初始化会话处理器
        self.session_handler = SessionHandler(
            plugin=self,
            session_manager=self.session_manager
        )
    
    def _register_quota_rules(self):
        """注册配额规则"""
        if not self.quota_validator:
            return
        
        quota_rules = {
            'action_name': {
                'free': {'daily_limit': 10, 'points_cost': 1},
                'basic': {'daily_limit': 50, 'points_cost': 1},
                'premium': {'daily_limit': -1, 'points_cost': 0},
                'description': '操作描述'
            }
        }
        
        self.quota_validator.register_quota_rules(
            plugin_name='plugin_name',
            rules=quota_rules,
            override=True
        )
    
    @filter.command(command_name="cmd")
    @auto_stop_command
    async def handle_command(self, event: AstrMessageEvent, param: str = ""):
        """命令处理器"""
        # 实现命令逻辑
        pass
    
    @filter.command("callback")
    @callback_handler("prefix")
    @auto_stop_event
    async def handle_callback(self, event: AstrMessageEvent, action: str, **params):
        """回调处理器"""
        # 实现回调逻辑
        pass
    
    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """消息监听器"""
        # 实现消息处理逻辑
        pass
    
    async def terminate(self):
        """插件卸载"""
        logger.info("插件正在卸载...")
        if hasattr(self, 'session_manager'):
            self.session_manager.cleanup_all()
```

### 8.2 会话处理器结构

```python
from common.navigation_handler import NavigationHandler
from common.navigation_hint import NavigationHint

class SessionHandler:
    """会话处理器"""
    
    def __init__(self, plugin, session_manager):
        self.plugin = plugin
        self.session_manager = session_manager
        
        # 初始化导航处理器
        self.nav_handler = NavigationHandler(self.session_manager)
        self.nav_handler.register_callbacks(
            on_home=self._on_navigate_home,
            on_back=self._on_navigate_back,
            on_exit=self._on_navigate_exit
        )
    
    async def handle_session_message(
        self,
        user_id: str,
        session_id: str,
        message: str
    ) -> Optional[Tuple[str, Any]]:
        """处理会话消息"""
        
        # 获取会话
        session = self.session_manager.get_session(session_id)
        if not session:
            return "❌ 会话已过期"
        
        message = message.strip()
        
        # 使用 NavigationHandler 处理导航命令
        is_handled, result = await self.nav_handler.handle(
            session_id, message, session
        )
        if is_handled:
            return result
        
        # 处理业务逻辑
        # ...
    
    async def _on_navigate_home(self, session_id: str, session: Dict[str, Any]):
        """返回首页"""
        self.session_manager.update_session(session_id, step=0, save_history=False)
        return await self._show_main_menu(session)
    
    async def _on_navigate_back(self, session_id: str, session: Dict[str, Any]):
        """返回上级"""
        previous_step = self.session_manager.back_to_previous_step(session_id)
        return await self._show_previous_page(session)
    
    async def _on_navigate_exit(self, session_id: str, session: Dict[str, Any]):
        """退出会话"""
        return "✅ 已退出"
```

---

## 9. 常见问题

### Q1: 装饰器顺序错误导致 TypeError

**问题**：`TypeError: 'NoneType' object is not callable`

**原因**：装饰器顺序错误

**解决**：确保装饰器顺序正确
- 命令：`@filter.command` → `@auto_stop_command`
- 回调：`@filter.command("callback")` → `@callback_handler(prefix)` → `@auto_stop_event`

### Q2: 配额规则不更新

**问题**：修改配额规则后不生效

**原因**：`register_quota_rules` 默认不覆盖已存在的规则

**解决**：设置 `override=True`
```python
self.quota_validator.register_quota_rules(
    plugin_name='plugin_name',
    rules=quota_rules,
    override=True  # 强制更新
)
```

### Q3: 飞书平台命令重复处理

**问题**：飞书平台在命令处理后会将命令消息再次传递给 `on_message`

**原因**：飞书平台特性

**解决**：在 `on_message` 中添加特殊处理
```python
# 跳过命令关键词重复传递
session_data = session.get('data', {})
if session_data and message_text.startswith('命令关键词'):
    return
```

### Q4: 导航提示不随层级变化

**问题**：所有页面显示相同的导航提示

**原因**：没有使用 `step` 维护层级

**解决**：使用 `SessionManager` 的 `step` 和 `NavigationHint`
```python
# 创建会话时设置步骤
self.session_manager.create_session(session_id=session_id, step=0, ...)

# 进入下级时更新步骤
self.session_manager.update_session(session_id, step=1)

# 根据步骤生成提示
current_step = session.get('step', 0)
hint = NavigationHint.get_hint(level=current_step)
```

---

## 8. 缓存检查最佳实践

### 8.1 缓存实例检查

**必须使用 `is not None`**：

```python
# ✅ 正确：明确检查 None
if self.cache is not None:
    # ...
```

**❌ 错误：布尔检查**：

```python
# ❌ 错误：如果 cache 实例实现了 __len__ 或 __bool__ 且为空，会被误判为 False
if self.cache:
    # ...
```

### 8.2 缓存写入逻辑

```python
# ✅ 正确：确保 cache 存在且数据不为空
if self.cache is not None and data:
    cache_key = f"key:{id}"
    self.cache.set(cache_key, data)
```

---

## 9. 加载提示标准化

### 9.1 使用 LoadingIndicator

**使用 try-finally 结构确保提示被删除**：

```python
from common.loading_indicator import LoadingIndicator

# 1. 显示加载提示
loading_msg_id = await LoadingIndicator.show(event, 'process')

try:
    # 2. 执行耗时操作
    await asyncio.sleep(1)
    
    # 3. 发送结果
    yield event.plain_result("完成")
    
except Exception as e:
    # 4. 错误处理
    yield event.plain_result(f"错误: {e}")
    
finally:
    # 5. 必须：隐藏加载提示（无论成功与否）
    await LoadingIndicator.hide(event, loading_msg_id)
```

### 9.2 扩展提示类型

如果需要新的提示类型，在 `LoadingIndicator.MESSAGES` 中添加：

```python
# common/loading_indicator.py
MESSAGES = {
    # ... 现有类型 ...
    'ai_interpret': '🤖 正在为您解读，请稍候...',
}
```

---

## 10. AI 解读功能实现

### 10.1 提示词优化

**最佳实践**：
1. **避免复杂格式**：不使用表格、Markdown（部分平台不支持）
2. **字数控制**：明确限制字数（如 500 字）
3. **分段清晰**：使用空行分隔段落
4. **系统提示**：强调简洁、口语化

**示例**：

```python
prompt = f"""请对以下内容进行简洁解读：

{content}

要求：
1. 字数控制在 500 字以内
2. 使用纯文本格式，不要使用表格或特殊符号
3. 分段清晰，每段用空行分隔
4. 从以下角度分析：
   - 核心亮点
   - 适合人群
"""

system_prompt = "你是一位专业的评论家。请用简洁、口语化的方式进行解读，避免使用表格、列表符号等格式。"
```

### 10.2 特殊指令处理

**场景**：在会话模式下触发 AI 解读。

**实现流程**：

1. **SessionHandler 识别指令**：
```python
# session_handler.py
if message.lower() in ['a', 'ai', '解读']:
    if current_step >= 1:
        # 返回特殊标记，传递给主插件处理
        return ("TRIGGER_AI_INTERPRET", search_type, detail_id)
```

2. **主插件处理标记**：
```python
# main.py
elif len(result) == 3 and result[0] == "TRIGGER_AI_INTERPRET":
    # 触发 AI 解读逻辑
    async for r in self._handle_ai_interpret(event, result[1], result[2]):
        yield r
```

**优势**：保持 SessionHandler 职责单一，不包含复杂的 AI 处理逻辑。

---

## 11. 检查清单

重构完成后，使用此清单验证：

- [ ] 装饰器顺序正确
- [ ] 使用 `SessionManager` 管理会话（不自己维护字典）
- [ ] 使用 `step` 和 `step_history` 维护层级
- [ ] 使用 `NavigationHandler` 处理导航命令
- [ ] 使用 `NavigationHint` 生成导航提示
- [ ] 配额规则正确注册（`override=True`）
- [ ] 分离配额检查和消费
- [ ] `on_message` 实现所有必要检查
- [ ] 处理平台特定逻辑（如飞书图片）
- [ ] 使用常量替代魔法数字
- [ ] 添加详细的日志记录
- [ ] 统一的错误处理
- [ ] 类型注解完整
- [ ] 测试所有命令和回调
- [ ] 测试会话导航（h/b/0）
- [ ] 测试配额限制和消费

---

## 12. 参考资源

- **标准插件示例**：`astrbot_plugin_checkin`（签到插件）
- **通用模块位置**：`data/plugins/common/`
  - `session_manager.py` - 会话管理
  - `navigation_handler.py` - 导航处理
  - `navigation_hint.py` - 导航提示
  - `quota_validator.py` - 配额验证
  - `platform_utils.py` - 平台工具
  - `message_editor.py` - 消息编辑
  - `loading_indicator.py` - 加载提示

---

## 13. 版本历史

- **v1.1** (2025-11-26): 添加缓存检查、加载提示标准化、AI解读实现等章节
- **v1.0** (2025-11-24): 初始版本，基于豆瓣插件重构经验

---

**文档维护者**: AstrBot 开发团队  
**最后更新**: 2025-11-26
