# AstrBot 插件数据库架构说明

## 架构概览

AstrBot 采用**混合数据库架构**，将核心通用数据与插件业务数据分离管理。

```
data/
├── quota_system.db          # 通用配额系统（共享）
└── plugin_data/
    ├── checkin/
    │   └── checkin.db       # 签到业务数据
    ├── music/
    │   └── music.db         # 音乐业务数据
    └── yunpan/
        └── yunpan.db        # 云盘业务数据
```

## 设计原则

### 1. 数据分类规则

#### 通用数据库 (`quota_system.db`)
存储所有插件共享的核心数据：
- ✅ **用户身份** - 统一的用户标识和基本信息
- ✅ **积分系统** - 积分账户、流水记录
- ✅ **会员系统** - 会员等级、有效期管理
- ✅ **配额管理** - 配额规则、使用记录、临时加成
- ✅ **权限管理** - 用户权限和角色

#### 插件独立数据库
存储插件特定的业务数据：
- ✅ **业务缓存** - 搜索缓存、详情缓存、文件缓存
- ✅ **业务历史** - 下载历史、操作记录
- ✅ **插件特定配置** - 插件私有的配置数据
- ✅ **临时数据** - 会话数据、临时状态

### 2. 架构优势

#### ✅ 数据一致性
- 用户、积分、会员等核心数据在通用数据库中统一管理
- 避免数据冗余和不一致

#### ✅ 扩展性强
- 新插件可以独立创建自己的数据库
- 不影响现有插件和核心系统

#### ✅ 故障隔离
- 某个插件的数据库问题不会影响其他插件
- 核心系统与业务插件解耦

#### ✅ 性能优化
- 避免单一数据库的锁竞争
- 缓存数据可以独立优化和清理

#### ✅ 维护简单
- 每个数据库职责清晰
- 可以针对不同数据库制定不同的维护策略

## 数据库详细说明

### 通用配额系统数据库
- **文件**: `data/quota_system.db`
- **文档**: [common/DATABASE_README.md](common/DATABASE_README.md)
- **使用插件**: quota_admin, checkin, music, yunpan
- **核心表**: users, points_accounts, memberships, quota_rules

### 签到系统数据库
- **文件**: `data/plugin_data/checkin/checkin.db`
- **文档**: [astrbot_plugin_checkin/DATABASE_README.md](astrbot_plugin_checkin/DATABASE_README.md)
- **核心表**: checkin_records, checkin_stats

### 音乐插件数据库
- **文件**: `data/plugin_data/music/music.db`
- **文档**: [astrbot_plugin_music/DATABASE_README.md](astrbot_plugin_music/DATABASE_README.md)
- **核心表**: search_cache, download_history, telegram_file_cache

### 云盘插件数据库
- **文件**: `data/plugin_data/yunpan/yunpan.db`
- **文档**: [astrbot_plugin_yunpan/DATABASE_README.md](astrbot_plugin_yunpan/DATABASE_README.md)
- **核心表**: book_search_cache, book_download_history, telegram_book_file_cache

## 数据流转示例

### 用户下载音乐流程
```
1. 用户请求下载音乐
   ↓
2. music插件调用通用配额系统验证配额
   ├─ 查询 quota_system.db: users, memberships, quota_rules
   ├─ 检查 quota_system.db: quota_usage (今日使用情况)
   └─ 扣除 quota_system.db: points_accounts (如需消耗积分)
   ↓
3. 配额验证通过，执行下载
   ├─ 检查 music.db: telegram_file_cache (是否有缓存)
   ├─ 记录 music.db: download_history (下载历史)
   └─ 更新 quota_system.db: quota_usage (记录使用)
```

### 用户签到流程
```
1. 用户签到
   ↓
2. checkin插件处理签到逻辑
   ├─ 检查 checkin.db: checkin_records (是否已签到)
   ├─ 记录 checkin.db: checkin_records (签到记录)
   └─ 更新 checkin.db: checkin_stats (统计数据)
   ↓
3. 发放签到奖励到通用配额系统
   ├─ 增加 quota_system.db: points_accounts (积分奖励)
   ├─ 记录 quota_system.db: points_transactions (积分流水)
   └─ 添加 quota_system.db: quota_boosts (临时配额加成)
```

## 备份策略

### 通用配额系统
- **频率**: 每日备份
- **重要性**: ⭐⭐⭐⭐⭐ (最高)
- **原因**: 包含所有用户核心数据

### 插件业务数据库
- **频率**: 每周备份
- **重要性**: ⭐⭐⭐ (中等)
- **原因**: 主要是缓存和历史数据，可以重建

### 备份脚本示例
```bash
#!/bin/bash
# backup_databases.sh

BACKUP_DIR="data/backups/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# 备份通用配额系统（每日）
cp data/quota_system.db "$BACKUP_DIR/quota_system.db"

# 备份插件数据库（每周）
if [ $(date +%u) -eq 7 ]; then
    cp data/plugin_data/checkin/checkin.db "$BACKUP_DIR/checkin.db"
    cp data/plugin_data/music/music.db "$BACKUP_DIR/music.db"
    cp data/plugin_data/yunpan/yunpan.db "$BACKUP_DIR/yunpan.db"
fi

# 清理30天前的备份
find data/backups/ -type d -mtime +30 -exec rm -rf {} +
```

## 维护建议

### 定期维护任务

#### 每日
- ✅ 备份通用配额系统数据库
- ✅ 清理过期的搜索缓存（24小时）

#### 每周
- ✅ 备份插件业务数据库
- ✅ 清理过期的详情缓存
- ✅ 执行 VACUUM 优化数据库

#### 每月
- ✅ 清理3个月前的历史记录
- ✅ 清理无效的文件缓存
- ✅ 检查数据库大小和性能

### 维护脚本示例
```bash
#!/bin/bash
# maintain_databases.sh

# 清理搜索缓存
sqlite3 data/plugin_data/music/music.db "DELETE FROM search_cache WHERE created_time < datetime('now', '-24 hours');"
sqlite3 data/plugin_data/yunpan/yunpan.db "DELETE FROM book_search_cache WHERE created_time < datetime('now', '-24 hours');"

# 清理过期缓存
sqlite3 data/plugin_data/music/music.db "DELETE FROM song_detail_cache WHERE expires_time <= datetime('now');"
sqlite3 data/plugin_data/yunpan/yunpan.db "DELETE FROM book_detail_cache WHERE expires_time <= datetime('now');"

# 优化数据库
for db in data/quota_system.db data/plugin_data/*/*.db; do
    echo "Optimizing $db..."
    sqlite3 "$db" "VACUUM;"
done
```

## 迁移指南

### 从旧版本迁移

如果你的插件使用了旧的数据库文件名：
- `music_plugin.db` → `music.db`
- `yunpan_plugin.db` → `yunpan.db`

迁移步骤：
```bash
# 1. 停止 AstrBot
# 2. 重命名数据库文件
mv data/plugin_data/astrbot_plugin_music/music_plugin.db data/plugin_data/music/music.db
mv data/plugin_data/astrbot_plugin_yunpan/yunpan_plugin.db data/plugin_data/yunpan/yunpan.db

# 3. 重启 AstrBot
```

### 清理废弃的配额表

如果你的数据库中还有旧的 `user_quota` 或 `user_book_quota` 表：
```bash
# 音乐插件
sqlite3 data/plugin_data/music/music.db "DROP TABLE IF EXISTS user_quota;"

# 云盘插件
sqlite3 data/plugin_data/yunpan/yunpan.db "DROP TABLE IF EXISTS user_book_quota;"
```

## 开发新插件指南

### 1. 确定数据分类
- 用户、积分、会员相关 → 使用通用配额系统
- 插件特定的缓存、历史 → 创建独立数据库

### 2. 创建数据库
```python
import os
from pathlib import Path

# 获取数据路径
config = self.context.get_config()
data_path = config.get("data_path", "data")

# 创建插件数据目录
plugin_data_dir = os.path.join(data_path, "plugin_data", "your_plugin_name")
os.makedirs(plugin_data_dir, exist_ok=True)

# 数据库文件路径
db_path = os.path.join(plugin_data_dir, "your_plugin_name.db")
```

### 3. 使用通用配额系统
```python
from common.database_manager import DatabaseManager
from common.quota_validator import QuotaValidator

# 初始化通用配额系统
quota_db_path = os.path.join(data_path, "quota_system.db")
common_db = DatabaseManager(quota_db_path)
quota_validator = QuotaValidator(common_db)

# 验证配额
success, message = await quota_validator.check_quota(
    user_id=user_id,
    action_type="your_action_type",
    count=1
)
```

### 4. 编写数据库文档
参考现有插件的 `DATABASE_README.md` 格式。

## 常见问题

### Q: 为什么不使用单一数据库？
A: 单一数据库会导致耦合度高、性能瓶颈、维护困难。混合架构在保证核心数据一致性的同时，给插件足够的灵活性。

### Q: 如何处理跨数据库查询？
A: 通过应用层逻辑处理。先从通用数据库获取用户信息，再从插件数据库获取业务数据。

### Q: 数据库文件会不会太多？
A: 不会。每个插件一个数据库文件，职责清晰，便于管理。相比单一大数据库，这种方式更易维护。

### Q: 如何保证数据一致性？
A: 通过事务和应用层逻辑保证。关键操作使用数据库事务，跨数据库操作在应用层保证一致性。

## 总结

AstrBot 的混合数据库架构是经过深思熟虑的设计，它：
- ✅ 保证了核心数据的一致性
- ✅ 给插件足够的灵活性
- ✅ 提供了良好的扩展性
- ✅ 实现了故障隔离
- ✅ 优化了性能

这是目前最佳的架构选择，建议所有新插件都遵循这个设计原则。
