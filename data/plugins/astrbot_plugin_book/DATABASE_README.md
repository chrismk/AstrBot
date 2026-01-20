# 云盘插件数据库说明

## 数据库文件
- **位置**: `data/plugin_data/yunpan/yunpan.db`
- **类型**: SQLite3
- **所属插件**: astrbot_plugin_yunpan

## 用途
存储云盘插件的业务数据，包括搜索缓存、下载历史、文件缓存等。

## 表结构

### 1. book_search_cache - 书籍搜索缓存表
缓存书籍搜索结果，提高响应速度。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 缓存ID |
| cache_key | TEXT UNIQUE | 缓存键（由关键词生成） |
| user_id | TEXT | 用户ID |
| keyword | TEXT | 搜索关键词 |
| results | TEXT | 搜索结果（JSON格式） |
| total_count | INTEGER | 总结果数 |
| current_page | INTEGER | 当前页码 |
| created_time | TIMESTAMP | 创建时间 |

### 2. book_download_history - 书籍下载历史表
记录用户的书籍下载历史。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 记录ID |
| user_id | TEXT | 用户ID |
| book_ssid | TEXT | 书籍SSID |
| book_title | TEXT | 书籍标题 |
| author | TEXT | 作者 |
| file_format | TEXT | 文件格式（pdf/epub/mobi等） |
| file_size | INTEGER | 文件大小（字节） |
| download_time | TIMESTAMP | 下载时间 |

### 3. telegram_book_file_cache - Telegram书籍文件缓存表
缓存已上传到Telegram的书籍文件ID，避免重复上传。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 缓存ID |
| book_ssid | TEXT | 书籍SSID |
| file_format | TEXT | 文件格式 |
| file_tag | TEXT | 文件标签（用于区分同一书籍的不同版本） |
| file_id | TEXT | Telegram文件ID |
| file_size | INTEGER | 文件大小 |
| file_name | TEXT | 文件名 |
| book_info | TEXT | 书籍详细信息（JSON格式） |
| mime_type | TEXT | MIME类型 |
| uploaded_by | TEXT | 上传者 |
| upload_time | TIMESTAMP | 上传时间 |
| use_count | INTEGER | 使用次数 |
| is_valid | INTEGER | 是否有效 |
| UNIQUE(book_ssid, file_tag) | - | 唯一约束 |

### 4. book_detail_cache - 书籍详情缓存表
缓存书籍详细信息，减少API调用。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 缓存ID |
| book_ssid | TEXT UNIQUE | 书籍SSID |
| book_data | TEXT | 书籍数据（JSON格式） |
| created_time | TIMESTAMP | 创建时间 |
| expires_time | TIMESTAMP | 过期时间 |

## 数据分类
- **业务缓存**: book_search_cache, book_detail_cache, telegram_book_file_cache
- **业务历史**: book_download_history
- **临时数据**: 所有缓存表都是临时数据

## 与通用配额系统的关系
- 下载书籍时会调用通用配额系统验证配额
- 配额消耗记录存储在通用配额系统的 `quota_usage` 表
- 本数据库不存储配额相关数据（已废弃的 `user_book_quota` 表已删除）

## 数据保留策略
- **搜索缓存**: 24小时后自动清理
- **书籍详情缓存**: 根据 `expires_time` 自动清理
- **下载历史**: 建议保留3个月
- **文件缓存**: 永久保留（除非标记为无效）

## 备份建议
- **频率**: 每周备份
- **方式**: 直接复制 `yunpan.db` 文件
- **注意**: 缓存数据可以不备份，历史数据建议备份

## 维护命令
```bash
# 清理24小时前的搜索缓存
sqlite3 data/plugin_data/yunpan/yunpan.db "DELETE FROM book_search_cache WHERE created_time < datetime('now', '-24 hours');"

# 清理过期的书籍详情缓存
sqlite3 data/plugin_data/yunpan/yunpan.db "DELETE FROM book_detail_cache WHERE expires_time <= datetime('now');"

# 清理3个月前的下载历史
sqlite3 data/plugin_data/yunpan/yunpan.db "DELETE FROM book_download_history WHERE download_time < datetime('now', '-3 months');"

# 清理无效的文件缓存
sqlite3 data/plugin_data/yunpan/yunpan.db "DELETE FROM telegram_book_file_cache WHERE is_valid = 0 AND upload_time < datetime('now', '-7 days');"

# 优化数据库
sqlite3 data/plugin_data/yunpan/yunpan.db "VACUUM;"
```

## 注意事项
1. 搜索缓存应定期清理，避免占用过多空间
2. Telegram文件缓存可以显著提高响应速度，建议保留
3. 下载历史可用于统计分析，建议保留一定时间
4. 定期执行 VACUUM 优化数据库性能
5. 书籍文件通常较大，建议监控缓存表大小
