# 通用配额系统数据库说明

## 数据库文件
- **位置**: `data/quota_system.db`
- **类型**: SQLite3
- **版本**: 3

## 用途
通用配额系统数据库，为所有插件提供统一的用户管理、积分系统、会员系统和配额管理功能。

## 表结构

### 1. users - 用户基础信息表
存储所有使用插件的用户基本信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | TEXT PRIMARY KEY | 用户唯一标识 |
| platform | TEXT | 平台类型（如 qq, telegram 等） |
| platform_user_id | TEXT | 平台用户ID |
| created_at | TIMESTAMP | 创建时间 |

### 2. points_accounts - 积分账户表
管理用户积分余额和流水。

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | TEXT PRIMARY KEY | 用户ID（外键） |
| balance | INTEGER | 当前积分余额 |
| total_earned | INTEGER | 累计获得积分 |
| total_spent | INTEGER | 累计消费积分 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 3. points_transactions - 积分流水表
记录所有积分变动历史。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 流水ID |
| user_id | TEXT | 用户ID |
| amount | INTEGER | 变动金额（正数为收入，负数为支出） |
| balance_after | INTEGER | 变动后余额 |
| type | TEXT | 类型（recharge/consume/refund） |
| source | TEXT | 来源（如 checkin, admin, redeem 等） |
| description | TEXT | 描述 |
| created_at | TIMESTAMP | 创建时间 |

### 4. memberships - 会员信息表
管理用户会员等级和有效期。

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | TEXT PRIMARY KEY | 用户ID |
| level | INTEGER | 会员等级（0=免费, 1=基础, 2=高级, 3=至尊） |
| expire_date | DATE | 到期日期 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 5. quota_rules - 配额规则表
定义不同操作类型和会员等级的配额规则。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 规则ID |
| action_type | TEXT | 操作类型（如 music_download, book_download） |
| member_level | INTEGER | 会员等级 |
| daily_limit | INTEGER | 每日限额 |
| points_cost | INTEGER | 积分消耗 |
| is_active | BOOLEAN | 是否启用 |
| created_at | TIMESTAMP | 创建时间 |

### 6. quota_usage - 配额使用记录表
记录用户每日配额使用情况。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 记录ID |
| user_id | TEXT | 用户ID |
| action_type | TEXT | 操作类型 |
| usage_date | DATE | 使用日期 |
| count | INTEGER | 使用次数 |
| points_used | INTEGER | 消耗积分 |
| created_at | TIMESTAMP | 创建时间 |

### 7. quota_boosts - 临时配额加成表
管理临时配额加成（如签到奖励、活动奖励等）。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 加成ID |
| user_id | TEXT | 用户ID |
| action_type | TEXT | 操作类型 |
| boost_amount | INTEGER | 加成数量 |
| expire_date | DATE | 到期日期 |
| source | TEXT | 来源（如 checkin, event） |
| description | TEXT | 描述 |
| is_used | BOOLEAN | 是否已使用 |
| created_at | TIMESTAMP | 创建时间 |

### 8. search_statistics - 搜索统计表 (v3新增)
记录所有插件的搜索行为，用于生成热门搜索排行榜。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 记录ID |
| user_id | TEXT | 用户ID |
| plugin_name | TEXT | 插件名称（book/music/pansou） |
| search_type | TEXT | 搜索类型（keyword/link/id） |
| keyword | TEXT | 搜索关键词 |
| platform | TEXT | 平台（如 qq/netease） |
| result_count | INTEGER | 搜索结果数量 |
| has_download | INTEGER | 是否有下载 |
| created_at | DATETIME | 创建时间 |

**索引**:
- `idx_search_stats_user_plugin` (user_id, plugin_name)
- `idx_search_stats_keyword` (keyword)
- `idx_search_stats_created` (created_at)
- `idx_search_stats_plugin_created` (plugin_name, created_at)

### 9. download_statistics - 下载统计表 (v3新增)
记录所有插件的下载行为，用于生成热门下载排行榜。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 记录ID |
| user_id | TEXT | 用户ID |
| plugin_name | TEXT | 插件名称 |
| item_id | TEXT | 项目ID（歌曲ID/书籍ID等） |
| item_name | TEXT | 项目名称 |
| item_type | TEXT | 项目类型（song/book/file） |
| platform | TEXT | 平台 |
| quality | TEXT | 品质（128/320/flac/epub/pdf） |
| file_size | INTEGER | 文件大小 |
| source | TEXT | 来源 |
| created_at | DATETIME | 创建时间 |

**索引**:
- `idx_download_stats_user_plugin` (user_id, plugin_name)
- `idx_download_stats_item` (item_id, plugin_name)
- `idx_download_stats_created` (created_at)

## 数据分类
- **核心用户数据**: users, points_accounts, memberships
- **业务数据**: quota_rules, quota_usage, quota_boosts
- **流水数据**: points_transactions
- **统计数据**: search_statistics, download_statistics (v3新增)

## 使用插件
- ✅ astrbot_plugin_quota_admin - 配额管理插件
- ✅ astrbot_plugin_checkin - 签到系统插件
- ✅ astrbot_plugin_music - 音乐搜索插件
- ✅ astrbot_plugin_yunpan - 云盘搜索插件

## 数据保留策略
- **用户数据**: 永久保留
- **积分流水**: 建议保留1年
- **配额使用记录**: 建议保留3个月
- **临时加成**: 自动清理过期记录

## 备份建议
- **频率**: 每日备份
- **方式**: 使用 SQLite 的 `.backup` 命令或直接复制文件
- **位置**: 建议备份到 `data/backups/` 目录

## 维护命令
```bash
# 查看数据库大小
sqlite3 data/quota_system.db "SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size();"

# 优化数据库
sqlite3 data/quota_system.db "VACUUM;"

# 清理过期的临时加成
sqlite3 data/quota_system.db "DELETE FROM quota_boosts WHERE expire_date < date('now') AND is_used = 1;"
```

## 注意事项
1. 此数据库为共享数据库，多个插件同时访问
2. 所有写操作都应使用事务
3. 定期执行 VACUUM 优化数据库
4. 建议定期清理历史流水数据
