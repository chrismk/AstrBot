# 音乐插件数据库说明

## 数据库文件
- **位置**: `data/plugin_data/music/music.db`
- **类型**: SQLite3
- **所属插件**: astrbot_plugin_music

## 用途
存储音乐插件的业务数据，包括搜索缓存、下载历史、文件缓存等。

## 表结构

### 1. search_cache - 搜索结果缓存表
缓存音乐搜索结果，提高响应速度。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 缓存ID |
| cache_key | TEXT UNIQUE | 缓存键（由关键词和平台生成） |
| user_id | TEXT | 用户ID |
| keyword | TEXT | 搜索关键词 |
| platform | TEXT | 音乐平台（qq/netease/kugou等） |
| results | TEXT | 搜索结果（JSON格式） |
| total_count | INTEGER | 总结果数 |
| current_page | INTEGER | 当前页码 |
| created_time | TIMESTAMP | 创建时间 |

**索引**: `idx_search_cache_user` (user_id)

### 2. download_history - 下载历史表
记录用户的音乐下载历史。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 记录ID |
| user_id | TEXT | 用户ID |
| song_id | TEXT | 歌曲ID |
| song_name | TEXT | 歌曲名称 |
| artist | TEXT | 艺术家 |
| music_platform | TEXT | 音乐平台 |
| quality_level | TEXT | 音质等级（standard/high/lossless） |
| file_size | INTEGER | 文件大小（字节） |
| download_time | TIMESTAMP | 下载时间 |

**索引**: 
- `idx_download_history_user` (user_id)
- `idx_download_history_time` (download_time)

### 3. telegram_file_cache - Telegram文件缓存表
缓存已上传到Telegram的音乐文件ID，避免重复上传。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 缓存ID |
| song_id | TEXT | 歌曲ID |
| music_platform | TEXT | 音乐平台 |
| quality_level | TEXT | 音质等级 |
| file_id | TEXT | Telegram文件ID |
| file_unique_id | TEXT | Telegram唯一文件ID |
| file_size | INTEGER | 文件大小 |
| file_name | TEXT | 文件名 |
| duration | INTEGER | 时长（秒） |
| title | TEXT | 标题 |
| performer | TEXT | 表演者 |
| mime_type | TEXT | MIME类型 |
| uploaded_by | TEXT | 上传者 |
| upload_time | TIMESTAMP | 上传时间 |
| use_count | INTEGER | 使用次数 |
| is_valid | INTEGER | 是否有效 |
| UNIQUE(song_id, music_platform, quality_level) | - | 唯一约束 |

**索引**: `idx_file_cache_lookup` (song_id, music_platform, quality_level)

### 4. song_detail_cache - 歌曲详情缓存表
缓存歌曲详细信息，减少API调用。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 缓存ID |
| song_id | TEXT | 歌曲ID |
| music_platform | TEXT | 音乐平台 |
| song_data | TEXT | 歌曲数据（JSON格式） |
| created_time | TIMESTAMP | 创建时间 |
| expires_time | TIMESTAMP | 过期时间 |
| UNIQUE(song_id, music_platform) | - | 唯一约束 |

**索引**: 
- `idx_song_detail_cache_lookup` (song_id, music_platform)
- `idx_song_detail_cache_expires` (expires_time)

## 数据分类
- **业务缓存**: search_cache, song_detail_cache, telegram_file_cache
- **业务历史**: download_history
- **临时数据**: 所有缓存表都是临时数据

## 与通用配额系统的关系
- 下载音乐时会调用通用配额系统验证配额
- 配额消耗记录存储在通用配额系统的 `quota_usage` 表
- 本数据库不存储配额相关数据（已废弃的 `user_quota` 表已删除）

## 数据保留策略
- **搜索缓存**: 24小时后自动清理
- **歌曲详情缓存**: 根据 `expires_time` 自动清理
- **下载历史**: 建议保留3个月
- **文件缓存**: 永久保留（除非标记为无效）

## 备份建议
- **频率**: 每周备份
- **方式**: 直接复制 `music.db` 文件
- **注意**: 缓存数据可以不备份，历史数据建议备份

## 维护命令
```bash
# 清理24小时前的搜索缓存
sqlite3 data/plugin_data/music/music.db "DELETE FROM search_cache WHERE created_time < datetime('now', '-24 hours');"

# 清理过期的歌曲详情缓存
sqlite3 data/plugin_data/music/music.db "DELETE FROM song_detail_cache WHERE expires_time <= datetime('now');"

# 清理3个月前的下载历史
sqlite3 data/plugin_data/music/music.db "DELETE FROM download_history WHERE download_time < datetime('now', '-3 months');"

# 清理无效的文件缓存
sqlite3 data/plugin_data/music/music.db "DELETE FROM telegram_file_cache WHERE is_valid = 0 AND upload_time < datetime('now', '-7 days');"

# 优化数据库
sqlite3 data/plugin_data/music/music.db "VACUUM;"
```

## 注意事项
1. 搜索缓存应定期清理，避免占用过多空间
2. Telegram文件缓存可以显著提高响应速度，建议保留
3. 下载历史可用于统计分析，建议保留一定时间
4. 定期执行 VACUUM 优化数据库性能
