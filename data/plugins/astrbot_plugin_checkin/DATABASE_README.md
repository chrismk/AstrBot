# 签到系统数据库说明

## 数据库文件
- **位置**: `data/plugin_data/checkin/checkin.db`
- **类型**: SQLite3
- **所属插件**: astrbot_plugin_checkin

## 用途
存储签到系统的业务数据，包括签到记录、签到统计等。

## 表结构

### 1. checkin_records - 签到记录表
记录每次签到的详细信息。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 记录ID |
| user_id | TEXT | 用户ID |
| checkin_date | DATE | 签到日期 |
| points_earned | INTEGER | 获得积分 |
| is_lucky | BOOLEAN | 是否幸运签到 |
| is_makeup | BOOLEAN | 是否补签 |
| streak_days | INTEGER | 连续签到天数 |
| created_at | TIMESTAMP | 创建时间 |
| UNIQUE(user_id, checkin_date) | - | 每人每天只能签到一次 |

### 2. checkin_stats - 签到统计表
存储用户的签到统计数据。

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | TEXT PRIMARY KEY | 用户ID |
| total_days | INTEGER | 累计签到天数 |
| current_streak | INTEGER | 当前连续签到天数 |
| max_streak | INTEGER | 最长连续签到天数 |
| last_checkin_date | DATE | 最后签到日期 |
| total_points | INTEGER | 累计获得积分 |
| lucky_count | INTEGER | 幸运签到次数 |
| makeup_count | INTEGER | 补签次数 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

## 数据分类
- **业务历史**: checkin_records - 签到历史记录
- **统计数据**: checkin_stats - 用户签到统计

## 与通用配额系统的关系
- 签到获得的积分会写入通用配额系统的 `points_accounts` 表
- 签到奖励的临时配额会写入通用配额系统的 `quota_boosts` 表
- 本数据库仅存储签到业务相关的记录和统计

## 数据保留策略
- **签到记录**: 建议保留1年
- **签到统计**: 永久保留

## 备份建议
- **频率**: 每周备份
- **方式**: 直接复制 `checkin.db` 文件

## 维护命令
```bash
# 清理1年前的签到记录
sqlite3 data/plugin_data/checkin/checkin.db "DELETE FROM checkin_records WHERE checkin_date < date('now', '-1 year');"

# 优化数据库
sqlite3 data/plugin_data/checkin/checkin.db "VACUUM;"
```

## 注意事项
1. 签到记录应与积分流水保持一致
2. 补签功能需要消耗积分，需要先检查积分余额
3. 定期清理旧的签到记录以节省空间
