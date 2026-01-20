# 插件配额注册指南

## 📋 概述

从现在开始，插件应该在初始化时**自己注册配额规则**，而不是依赖中心化的硬编码配置。

## 🎯 优势

- ✅ **解耦合** - 配额规则与插件代码在一起
- ✅ **灵活性** - 插件可以动态调整配额
- ✅ **可维护性** - 插件开发者最清楚自己的配额需求
- ✅ **热加载** - 支持插件动态加载/卸载

## 📝 使用方法

### 1. 在插件初始化时注册配额

```python
from astrbot.api.star import Star, register
from common import QuotaValidator, DatabaseManager
import os

@register("douban", "豆瓣插件", "1.0.0")
class DoubanPlugin(Star):
    
    def __init__(self, context, config):
        super().__init__(context, config)
        
        # 初始化配额验证器
        data_path = context.get_data_path()
        quota_db_path = os.path.join(data_path, "quota_system.db")
        db = DatabaseManager(quota_db_path)
        self.quota_validator = QuotaValidator(db)
        
        # 注册配额规则
        self._register_quota_rules()
    
    def _register_quota_rules(self):
        """注册插件的配额规则"""
        rules = [
            {
                'action_type': 'douban_view',
                'free': {'daily_limit': 10, 'points_cost': 0},
                'premium': {'daily_limit': -1, 'points_cost': 0},
                'vip': {'daily_limit': -1, 'points_cost': 0},
                'description': '查看豆瓣评分'
            },
            {
                'action_type': 'douban_search',
                'free': {'daily_limit': 5, 'points_cost': 0},
                'premium': {'daily_limit': -1, 'points_cost': 0},
                'vip': {'daily_limit': -1, 'points_cost': 0},
                'description': '搜索豆瓣'
            }
        ]
        
        success = self.quota_validator.register_quota_rules(
            plugin_name='douban',
            rules=rules,
            override=False  # 不覆盖已存在的规则
        )
        
        if success:
            logger.info("[Douban] 配额规则注册成功")
        else:
            logger.warning("[Douban] 配额规则注册失败")
```

### 2. 在命令中检查和消费配额

```python
@filter.command("豆瓣")
async def douban_cmd(self, event: AstrMessageEvent):
    """查看豆瓣评分"""
    user_id = event.get_sender_id()
    
    # 1. 检查并消费配额
    result = await self.quota_validator.check_and_consume(
        user_id=user_id,
        action_type='douban_view',
        plugin_name='douban'
    )
    
    if not result.allowed:
        yield event.plain_result(result.message)
        return
    
    # 2. 执行实际操作
    try:
        douban_data = await self._fetch_douban_data()
        yield event.plain_result(f"✅ {douban_data}")
    except Exception as e:
        # 3. 失败时退还配额
        await self.quota_validator.refund_quota(
            user_id=user_id,
            action_type='douban_view',
            plugin_name='douban'
        )
        yield event.plain_result(f"❌ 查询失败: {e}")
```

### 3. 配额规则格式说明

```python
{
    'action_type': 'action_name',  # 操作类型（必填）
    'free': {                       # 免费用户配额（可选）
        'daily_limit': 10,          # 每日限制次数（-1 表示无限制）
        'points_cost': 0            # 积分消耗（0 表示免费）
    },
    'premium': {                    # 高级会员配额（可选）
        'daily_limit': 50,
        'points_cost': 0
    },
    'vip': {                        # VIP会员配额（可选）
        'daily_limit': -1,          # 无限制
        'points_cost': 0
    },
    'description': '操作描述'      # 操作描述（可选）
}
```

## 🔧 API 参考

### `register_quota_rules(plugin_name, rules, override=False)`

注册插件的配额规则。

**参数：**
- `plugin_name` (str): 插件名称
- `rules` (list): 配额规则列表
- `override` (bool): 是否覆盖已存在的规则，默认 False

**返回：**
- `bool`: 是否注册成功

### `unregister_quota_rules(plugin_name)`

卸载插件的配额规则（禁用而非删除）。

**参数：**
- `plugin_name` (str): 插件名称

**返回：**
- `bool`: 是否卸载成功

### `get_plugin_rules(plugin_name)`

获取插件的所有配额规则。

**参数：**
- `plugin_name` (str): 插件名称

**返回：**
- `list`: 规则列表

### `refund_quota(user_id, action_type, plugin_name)`

退还配额（操作失败时）。

**参数：**
- `user_id` (str): 用户ID
- `action_type` (str): 操作类型
- `plugin_name` (str): 插件名称

**返回：**
- `bool`: 是否退还成功

## 💡 最佳实践

### 1. 配额设计原则

- **免费用户**: 提供基本功能，限制次数
- **高级会员**: 大幅提升配额，部分功能免费
- **VIP会员**: 所有功能无限制

### 2. 操作失败处理

```python
try:
    result = await do_something()
    yield event.plain_result(result)
except Exception as e:
    # 失败时退还配额
    await self.quota_validator.refund_quota(
        user_id, action_type, plugin_name
    )
    yield event.plain_result(f"❌ 操作失败: {e}")
```

### 3. 配额检查时机

- **检查**: 在执行操作之前
- **消费**: 操作成功后
- **退还**: 操作失败后

### 4. 命名规范

- 操作类型命名: `{plugin}_{action}` (如 `music_download_flac`)
- 插件名称: 使用小写字母和下划线 (如 `music`, `douban`)

## 📊 示例：完整的插件实现

参考 `astrbot_plugin_yunpan` 插件，它已经完整实现了配额自注册系统。

## 🔄 迁移指南

如果你的插件还在使用旧的配额系统，请按以下步骤迁移：

1. 在 `__init__` 中添加 `_register_quota_rules()` 方法
2. 将配额规则从中心配置移到插件代码中
3. 使用 `check_and_consume()` 替代旧的配额检查方法
4. 在操作失败时调用 `refund_quota()`

## ❓ 常见问题

### Q: 规则已存在怎么办？

A: 默认情况下，如果规则已存在会跳过。如果需要更新，设置 `override=True`。

### Q: 如何查看已注册的规则？

A: 使用 `get_plugin_rules(plugin_name)` 查看。

### Q: 插件卸载时需要清理规则吗？

A: 不需要，规则会被标记为禁用而不是删除，方便后续重新启用。

### Q: 可以动态修改配额吗？

A: 可以，调用 `register_quota_rules()` 并设置 `override=True`。
