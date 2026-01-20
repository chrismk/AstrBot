# 插件级定时任务调度器使用指南

## 📋 概述

`PluginScheduler` 是一个统一的插件级定时任务调度系统，遵循现有通用模块的设计模式（单例模式、全局获取函数），让插件可以轻松注册和管理定时任务。

## 🎯 核心特性

- **简单易用**：装饰器或函数调用两种注册方式
- **Cron 支持**：标准 cron 表达式，灵活配置执行时间
- **间隔执行**：支持固定间隔执行
- **自动重试**：任务失败自动重试，可配置重试次数和间隔
- **持久化**：任务状态和执行日志持久化到数据库
- **任务管理**：支持启用/禁用/手动触发任务

## 🚀 快速开始

### 安装依赖

```bash
pip install apscheduler
```

### 方式1：使用装饰器（推荐）

```python
from common import get_scheduler, scheduled_task, register_decorated_tasks

class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        
        # 初始化调度器
        self.scheduler = get_scheduler(self.db)
        self.scheduler.set_context(context)  # 设置上下文，用于消息推送
        
        # 注册装饰器定义的任务
        register_decorated_tasks(self, self.scheduler)
        
        # 启动调度器（建议在所有插件加载完成后统一启动）
        asyncio.create_task(self.scheduler.start())
    
    @scheduled_task(
        task_id="myplugin:daily_task",
        plugin_name="myplugin",
        cron="0 8 * * *",  # 每天早上8点
        description="每日任务"
    )
    async def daily_task(self, context):
        """每日执行的任务"""
        # 你的任务逻辑
        pass
```

### 方式2：手动注册

```python
from common import get_scheduler

class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        
        # 获取调度器
        self.scheduler = get_scheduler(self.db)
        self.scheduler.set_context(context)
        
        # 注册任务
        self.scheduler.register_task(
            task_id="myplugin:hourly_update",
            plugin_name="myplugin",
            cron="0 * * * *",  # 每小时执行
            handler=self.hourly_update,
            description="每小时更新数据"
        )
        
        # 启动调度器
        asyncio.create_task(self.scheduler.start())
    
    async def hourly_update(self, context):
        """每小时执行的更新任务"""
        # 你的任务逻辑
        pass
```

## 📅 Cron 表达式

标准 5 位 cron 表达式：`分 时 日 月 周`

| 表达式 | 说明 |
|--------|------|
| `0 * * * *` | 每小时整点 |
| `*/30 * * * *` | 每30分钟 |
| `0 8 * * *` | 每天早上8点 |
| `0 19 * * *` | 每天晚上7点 |
| `0 0 * * 1` | 每周一凌晨 |
| `0 0 1 * *` | 每月1号凌晨 |

## 🔧 API 参考

### get_scheduler(db=None)

获取全局调度器实例（单例模式）。

```python
from common import get_scheduler

scheduler = get_scheduler(db)  # 首次调用时传入 db
scheduler = get_scheduler()    # 后续调用可省略
```

### register_task()

注册定时任务。

```python
scheduler.register_task(
    task_id="plugin:task_name",     # 任务唯一标识（建议格式：plugin:name）
    plugin_name="plugin",           # 所属插件名称
    handler=async_function,         # 任务处理函数
    cron="0 * * * *",              # cron 表达式（与 interval_seconds 二选一）
    interval_seconds=3600,          # 间隔秒数（与 cron 二选一）
    description="任务描述",         # 任务描述
    enabled=True,                   # 是否启用
    max_retries=3,                  # 最大重试次数
    retry_delay=60,                 # 重试间隔（秒）
    context=None                    # 上下文对象
)
```

### 任务管理

```python
# 启用任务
scheduler.enable_task("task_id")

# 禁用任务
scheduler.disable_task("task_id")

# 手动触发任务
await scheduler.trigger_task("task_id")

# 获取任务状态
status = scheduler.get_task_status("task_id")

# 获取所有任务
tasks = scheduler.get_all_tasks(plugin_name="myplugin")

# 获取任务日志
logs = scheduler.get_task_logs(task_id="task_id", limit=50)

# 清理旧日志
scheduler.cleanup_old_logs(days=30)
```

### 调度器控制

```python
# 启动调度器
await scheduler.start()

# 停止调度器
scheduler.stop()

# 设置全局上下文（用于消息推送）
scheduler.set_context(context)
```

## 📝 实际应用示例

### 签到提醒任务

```python
from common import get_scheduler, scheduled_task, MessagePusher

class CheckinPlugin(Star):
    @scheduled_task(
        task_id="checkin:daily_reminder",
        plugin_name="checkin",
        cron="0 19 * * *",  # 每天19:00
        description="每日签到提醒"
    )
    async def send_checkin_reminder(self, context):
        """发送签到提醒给未签到用户"""
        # 获取今日未签到用户
        unchecked_users = await self.checkin_manager.get_unchecked_users_today()
        
        for user_id in unchecked_users:
            message = "📢 签到提醒\n\n今天还没签到哦！回复 /签 立即签到~"
            await MessagePusher.send_private_message(user_id, message, context)
```

### 热搜榜单更新任务

```python
from common import get_scheduler

class SearchStatsPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        
        scheduler = get_scheduler(self.db)
        
        # 每小时更新热搜榜单
        scheduler.register_task(
            task_id="search_stats:update_ranking",
            plugin_name="search_stats",
            cron="0 * * * *",
            handler=self.update_ranking,
            description="更新热搜榜单"
        )
        
        # 每天凌晨清理旧数据
        scheduler.register_task(
            task_id="search_stats:cleanup",
            plugin_name="search_stats",
            cron="0 3 * * *",
            handler=self.cleanup_old_data,
            description="清理旧数据"
        )
    
    async def update_ranking(self, context):
        """更新热搜榜单"""
        # 计算热搜排名
        # 对比上一周期，计算排名变化
        # 缓存榜单数据
        pass
    
    async def cleanup_old_data(self, context):
        """清理旧数据"""
        self.search_stats.cleanup_old_data(days=90)
```

### 订阅推送任务

```python
from common import get_scheduler, MessagePusher

class SubscriptionPlugin(Star):
    @scheduled_task(
        task_id="subscription:push",
        plugin_name="subscription",
        cron="0 8,12,19 * * *",  # 每天8点、12点、19点
        description="订阅内容推送"
    )
    async def push_subscriptions(self, context):
        """推送订阅内容"""
        # 获取当前时段的订阅
        subscriptions = await self.get_due_subscriptions()
        
        for sub in subscriptions:
            content = await self.generate_push_content(sub)
            await MessagePusher.send_private_message(
                sub['user_id'], 
                content, 
                context
            )
```

## 🗄️ 数据库表结构

### scheduled_tasks 表

| 字段 | 类型 | 说明 |
|------|------|------|
| task_id | TEXT | 任务唯一标识（主键） |
| plugin_name | TEXT | 所属插件名称 |
| cron | TEXT | cron 表达式 |
| interval_seconds | INTEGER | 间隔秒数 |
| description | TEXT | 任务描述 |
| enabled | INTEGER | 是否启用 |
| last_run | DATETIME | 上次执行时间 |
| next_run | DATETIME | 下次执行时间 |
| run_count | INTEGER | 执行次数 |
| success_count | INTEGER | 成功次数 |
| fail_count | INTEGER | 失败次数 |

### task_logs 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 自增主键 |
| task_id | TEXT | 任务ID |
| status | TEXT | 执行状态 (success/failed) |
| started_at | DATETIME | 开始时间 |
| finished_at | DATETIME | 结束时间 |
| duration_ms | INTEGER | 执行耗时（毫秒） |
| error_message | TEXT | 错误信息 |
| retry_count | INTEGER | 重试次数 |

## ⚠️ 注意事项

1. **APScheduler 依赖**：需要安装 `apscheduler` 包
2. **任务ID唯一性**：建议使用 `plugin_name:task_name` 格式
3. **异步函数**：任务处理函数必须是 `async` 函数
4. **错误处理**：任务内部应做好异常处理，避免影响其他任务
5. **调度器启动**：建议在所有插件加载完成后统一启动调度器
6. **资源清理**：插件卸载时应停止相关任务

## 🔄 与现有模块的集成

### 与 MessagePusher 集成

```python
from common import MessagePusher

async def my_task(context):
    await MessagePusher.send_private_message(
        user_id="telegram:123456",
        message="定时消息",
        context=context
    )
```

### 与 SearchStatistics 集成

```python
from common import get_search_statistics

async def update_ranking(context):
    stats = get_search_statistics()
    popular = stats.get_popular_searches(days=1, limit=20)
    # 处理榜单数据...
```

### 与 DatabaseManager 集成

调度器自动使用传入的 `DatabaseManager` 实例，无需额外配置。
