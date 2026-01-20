# 知识猎人通用配额系统

## 📖 简介

完整的**会员+积分+配额**三位一体管理系统，为所有插件提供统一的配额验证功能。

### ✨ 核心特性

- ✅ **统一配额验证**：所有插件使用同一套配额规则
- ✅ **会员等级管理**：免费/高级/VIP三级体系
- ✅ **积分系统**：充值、消费、流水记录
- ✅ **临时配额包**：积分兑换流量包
- ✅ **灵活扩展**：新插件只需配置规则
- ✅ **生产级代码**：完整的错误处理和日志

---

## 🚀 快速开始

### 1. 初始化系统

```python
from data.plugins.common import DatabaseManager, QuotaValidator

# 创建数据库管理器
db = DatabaseManager("data/quota_system.db")

# 创建配额验证器
validator = QuotaValidator(db)
```

### 2. 在插件中使用

```python
# 在插件的 __init__ 方法中初始化
class MyPlugin:
    def __init__(self, context):
        super().__init__(context)
        
        # 获取数据库路径
        config = self.context.get_config()
        data_path = config.get("data_path", "data")
        db_path = os.path.join(data_path, "quota_system.db")
        
        # 初始化配额系统
        self.db = DatabaseManager(db_path)
        self.quota_validator = QuotaValidator(self.db)
```

### 3. 检查和消费配额

```python
async def handle_download(self, user_id: str, quality: str):
    # 1. 检查配额
    result = await self.quota_validator.check_quota(
        user_id=user_id,
        action_type=f"music_download_{quality}",
        plugin_name="music",
        use_points=True  # 允许积分抵扣
    )
    
    if not result.allowed:
        # 配额不足，返回提示
        return result.message
    
    # 2. 执行下载操作
    success = await self.do_download(...)
    
    if success:
        # 3. 消费配额
        await self.quota_validator.consume_quota(
            user_id=user_id,
            action_type=f"music_download_{quality}",
            plugin_name="music",
            points_cost=result.points_cost
        )
        
        return "✅ 下载成功"
```

---

## 📊 配额规则配置

配额规则存储在 `quota_rules` 表中，可以通过数据库直接修改：

```sql
-- 查看所有规则
SELECT * FROM quota_rules;

-- 修改免费用户的无损下载配额
UPDATE quota_rules 
SET daily_limit = 3 
WHERE action_type = 'music_download_flac' AND member_level = 0;

-- 添加新插件的规则
INSERT INTO quota_rules 
(action_type, plugin_name, member_level, daily_limit, points_cost, description, is_active, created_at, updated_at)
VALUES 
('new_action', 'new_plugin', 0, 10, 0, '新功能', 1, datetime('now'), datetime('now'));
```

---

## 💎 会员等级

| 等级 | 名称 | 价格 | 权益 |
|------|------|------|------|
| 0 | 免费用户 | - | 基础配额 |
| 1 | 高级会员 | ¥19.9/月 | 大幅提升配额 |
| 2 | VIP会员 | ¥399/年 | 无限配额 |

### 升级会员

```python
from data.plugins.common import MembershipManager, MemberLevel

membership_mgr = MembershipManager(db)

# 升级到高级会员（1个月）
await membership_mgr.upgrade(user_id, MemberLevel.PREMIUM, months=1)

# 升级到VIP会员（12个月）
await membership_mgr.upgrade(user_id, MemberLevel.VIP, months=12)

# 查询会员信息
info = await membership_mgr.get_membership_info(user_id)
print(f"会员等级: {info['level_name']}")
print(f"到期日期: {info['expire_date']}")
print(f"剩余天数: {info['days_remaining']}")
```

---

## 💰 积分系统

### 充值积分

```python
from data.plugins.common import PointsManager

points_mgr = PointsManager(db)

# 充值积分
await points_mgr.recharge(
    user_id="user123",
    amount=100,
    source="payment",
    order_id="ORDER_123",
    description="用户充值"
)

# 查询余额
balance = await points_mgr.get_balance(user_id)
```

### 兑换配额包

```python
# 查看可用配额包
packages = points_mgr.get_boost_packages()

# 兑换配额包
success, message = await points_mgr.exchange_boost_package(
    user_id="user123",
    package_id="music_flac_5"  # 5次无损下载
)
print(message)
```

### 内置配额包

| ID | 描述 | 积分 | 有效期 |
|----|------|------|--------|
| `music_flac_5` | 5次无损音乐下载 | 50 | 24小时 |
| `music_320_10` | 10次320k音乐下载 | 30 | 24小时 |
| `yunpan_10` | 10次云盘资源下载 | 40 | 24小时 |
| `all_day_pass` | 全功能日卡（所有操作+50次） | 100 | 24小时 |

---

## 🗄️ 数据库表结构

系统使用7张核心表：

1. **users** - 用户基础信息
2. **memberships** - 会员信息
3. **points_accounts** - 积分账户
4. **points_transactions** - 积分流水
5. **quota_rules** - 配额规则
6. **quota_usage** - 配额使用记录
7. **quota_boosts** - 临时配额加成

---

## 🧪 测试

运行测试脚本验证系统：

```bash
python data/plugins/common/test_quota_system.py
```

测试覆盖：
- ✅ 数据库初始化
- ✅ 免费用户配额限制
- ✅ 积分充值和抵扣
- ✅ 会员升级
- ✅ 配额包兑换
- ✅ 积分流水记录

---

## 📝 最佳实践

### 1. 错误处理

```python
try:
    result = await validator.check_quota(...)
    if result.allowed:
        # 执行操作
        pass
except Exception as e:
    logger.error(f"配额检查失败: {e}")
    # 降级处理，允许操作
```

### 2. 日志记录

系统自动记录所有关键操作：
- 配额检查和消费
- 积分充值和扣除
- 会员升级和过期
- 配额包兑换

### 3. 性能优化

- 使用 WAL 模式提高并发性能
- 合理设置缓存大小
- 定期清理过期数据

### 4. 安全建议

- 积分充值需要验证支付回调
- 会员升级需要验证订单状态
- 敏感操作记录完整日志

---

## 🔧 维护

### 定期任务

```python
# 每天执行一次，处理过期会员
from data.plugins.common import MembershipManager

membership_mgr = MembershipManager(db)
expired_count = await membership_mgr.check_and_expire_memberships()
logger.info(f"处理了 {expired_count} 个过期会员")
```

### 数据备份

```bash
# 备份数据库
cp data/quota_system.db data/quota_system_backup_$(date +%Y%m%d).db
```

---

## 📞 支持

如有问题，请查看：
- 测试脚本: `test_quota_system.py`
- 实施清单: `docs/插件改进实施清单.md`
- 设计方案: `docs/通用配额系统设计方案.md`
