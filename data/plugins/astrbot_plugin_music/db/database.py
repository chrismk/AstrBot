"""数据库管理器"""

import sqlite3
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path

from .models import SearchCache, DownloadHistory, TelegramFileCache, SongDetailCache
from ..utils.exceptions import DatabaseError

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, db_path: str, logger_param=None):
        self.db_path = db_path
        # logger_param已废弃，使用全局logger
        self._init_database()
    
    def _init_database(self):
        """初始化数据库"""
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 搜索结果缓存表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS search_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        cache_key TEXT UNIQUE NOT NULL,
                        user_id TEXT NOT NULL,
                        keyword TEXT NOT NULL,
                        platform TEXT NOT NULL,
                        results TEXT NOT NULL,
                        total_count INTEGER NOT NULL,
                        current_page INTEGER NOT NULL,
                        created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 下载历史表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS download_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        song_id TEXT NOT NULL,
                        song_name TEXT NOT NULL,
                        artist TEXT NOT NULL,
                        music_platform TEXT NOT NULL,
                        quality_level TEXT NOT NULL,
                        file_size INTEGER,
                        download_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Telegram文件缓存表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS telegram_file_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        song_id TEXT NOT NULL,
                        music_platform TEXT NOT NULL,
                        quality_level TEXT NOT NULL,
                        file_id TEXT NOT NULL,
                        file_unique_id TEXT,
                        file_size INTEGER,
                        file_name TEXT,
                        duration INTEGER,
                        title TEXT,
                        performer TEXT,
                        caption TEXT,
                        mime_type TEXT,
                        uploaded_by TEXT,
                        upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        use_count INTEGER DEFAULT 1,
                        is_valid INTEGER DEFAULT 1,
                        UNIQUE(song_id, music_platform, quality_level)
                    )
                """)
                
                # 歌曲详情缓存表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS song_detail_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        song_id TEXT NOT NULL,
                        music_platform TEXT NOT NULL,
                        song_data TEXT NOT NULL,
                        created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_time TIMESTAMP NOT NULL,
                        UNIQUE(song_id, music_platform)
                    )
                """)
                
                # 创建索引
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_search_cache_user ON search_cache(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_download_history_user ON download_history(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_download_history_time ON download_history(download_time)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_cache_lookup ON telegram_file_cache(song_id, music_platform, quality_level)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_song_detail_cache_lookup ON song_detail_cache(song_id, music_platform)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_song_detail_cache_expires ON song_detail_cache(expires_time)")
                
                conn.commit()
                logger.info("数据库初始化成功")
                
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}", exc_info=True)
            raise DatabaseError(f"数据库初始化失败: {e}")
    
    # ==================== 搜索缓存 ====================
    
    def save_search_cache(self, cache: SearchCache) -> bool:
        """保存搜索缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO search_cache 
                    (cache_key, user_id, keyword, platform, results, total_count, current_page, created_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    cache.cache_key, cache.user_id, cache.keyword, cache.platform,
                    cache.results, cache.total_count, cache.current_page,
                    cache.created_time or datetime.now()
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"保存搜索缓存失败: {e}", exc_info=True)
            return False
    
    def get_search_cache(self, cache_key: str) -> Optional[SearchCache]:
        """获取搜索缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, cache_key, user_id, keyword, platform, results, 
                           total_count, current_page, created_time
                    FROM search_cache 
                    WHERE cache_key = ?
                """, (cache_key,))
                
                row = cursor.fetchone()
                if row:
                    return SearchCache(
                        id=row[0],
                        cache_key=row[1],
                        user_id=row[2],
                        keyword=row[3],
                        platform=row[4],
                        results=row[5],
                        total_count=row[6],
                        current_page=row[7],
                        created_time=datetime.fromisoformat(row[8]) if row[8] else datetime.now()
                    )
                return None
        except Exception as e:
            logger.error(f"获取搜索缓存失败: {e}", exc_info=True)
            return None
    
    def get_recent_search_caches(self, limit: int = 10) -> List[SearchCache]:
        """获取最近的搜索缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, cache_key, user_id, keyword, platform, results, total_count, current_page, created_time
                    FROM search_cache 
                    ORDER BY created_time DESC 
                    LIMIT ?
                """, (limit,))
                
                caches = []
                for row in cursor.fetchall():
                    cache = SearchCache(
                        id=row[0],
                        cache_key=row[1],
                        user_id=row[2],
                        keyword=row[3],
                        platform=row[4],
                        results=row[5],
                        total_count=row[6],
                        current_page=row[7],
                        created_time=datetime.fromisoformat(row[8]) if row[8] else datetime.now()
                    )
                    caches.append(cache)
                return caches
        except Exception as e:
            logger.error(f"获取最近搜索缓存失败: {e}", exc_info=True)
            return []
    
    def cleanup_old_search_cache(self, hours: int = 24):
        """清理旧的搜索缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cutoff_time = datetime.now() - timedelta(hours=hours)
                cursor.execute("DELETE FROM search_cache WHERE created_time < ?", (cutoff_time,))
                deleted = cursor.rowcount
                conn.commit()
                logger.info(f"清理了 {deleted} 条旧搜索缓存")
                return deleted
        except Exception as e:
            logger.error(f"清理搜索缓存失败: {e}", exc_info=True)
            return 0
    
    # ==================== 下载历史 ====================
    
    def add_download_history(self, history: DownloadHistory) -> bool:
        """添加下载历史"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO download_history 
                    (user_id, song_id, song_name, artist, music_platform, quality_level, file_size, download_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    history.user_id, history.song_id, history.song_name, history.artist,
                    history.music_platform, history.quality_level, history.file_size,
                    history.download_time or datetime.now()
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"添加下载历史失败: {e}", exc_info=True)
            return False
    
    def get_user_daily_downloads(self, user_id: str, quality_level: Optional[str] = None) -> int:
        """获取用户今日下载次数"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                
                if quality_level:
                    cursor.execute("""
                        SELECT COUNT(*) FROM download_history 
                        WHERE user_id = ? AND quality_level = ? AND download_time >= ?
                    """, (user_id, quality_level, today_start))
                else:
                    cursor.execute("""
                        SELECT COUNT(*) FROM download_history 
                        WHERE user_id = ? AND download_time >= ?
                    """, (user_id, today_start))
                
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"获取用户下载次数失败: {e}", exc_info=True)
            return 0
    
    # ==================== Telegram文件缓存 ====================
    
    def get_file_cache(self, song_id: str, platform: str, quality: str) -> Optional[TelegramFileCache]:
        """获取文件缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, song_id, music_platform, quality_level, file_id, file_unique_id,
                           file_size, file_name, duration, title, performer, caption, mime_type,
                           uploaded_by, upload_time, use_count, is_valid
                    FROM telegram_file_cache 
                    WHERE song_id = ? AND music_platform = ? AND quality_level = ? AND is_valid = 1
                """, (song_id, platform, quality))
                
                row = cursor.fetchone()
                if row:
                    return TelegramFileCache(
                        id=row[0],
                        song_id=row[1],
                        music_platform=row[2],
                        quality_level=row[3],
                        file_id=row[4],
                        file_unique_id=row[5],
                        file_size=row[6],
                        file_name=row[7],
                        duration=row[8],
                        title=row[9],
                        performer=row[10],
                        caption=row[11],
                        mime_type=row[12],
                        uploaded_by=row[13],
                        upload_time=datetime.fromisoformat(row[14]) if row[14] else datetime.now(),
                        use_count=row[15],
                        is_valid=row[16]
                    )
                return None
        except Exception as e:
            logger.error(f"获取文件缓存失败: {e}", exc_info=True)
            return None
    
    def save_file_cache(self, cache: TelegramFileCache) -> bool:
        """保存文件缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO telegram_file_cache 
                    (song_id, music_platform, quality_level, file_id, file_unique_id, file_size,
                    file_name, duration, title, performer, caption, mime_type, uploaded_by, upload_time,
                    use_count, is_valid)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    cache.song_id, cache.music_platform, cache.quality_level, cache.file_id,
                    cache.file_unique_id, cache.file_size, cache.file_name, cache.duration,
                    cache.title, cache.performer, cache.caption, cache.mime_type, cache.uploaded_by,
                    cache.upload_time or datetime.now(), cache.use_count, cache.is_valid
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"保存文件缓存失败: {e}", exc_info=True)
            return False
    
    def increment_cache_use_count(self, song_id: str, platform: str, quality: str) -> bool:
        """增加缓存使用次数"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE telegram_file_cache 
                    SET use_count = use_count + 1 
                    WHERE song_id = ? AND music_platform = ? AND quality_level = ?
                """, (song_id, platform, quality))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"更新缓存使用次数失败: {e}", exc_info=True)
            return False
    
    def mark_cache_invalid(self, song_id: str, platform: str, quality: str) -> bool:
        """标记缓存失效"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE telegram_file_cache 
                    SET is_valid = 0 
                    WHERE song_id = ? AND music_platform = ? AND quality_level = ?
                """, (song_id, platform, quality))
                conn.commit()
                logger.info(f"标记file_id失效: {song_id}/{platform}/{quality}")
                return True
        except Exception as e:
            logger.error(f"标记缓存失效失败: {e}", exc_info=True)
            return False
    
    # ==================== 歌曲详情缓存 ====================
    
    def get_song_detail_cache(self, song_id: str, platform: str) -> Optional[SongDetailCache]:
        """获取歌曲详情缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                now = datetime.now()
                
                cursor.execute("""
                    SELECT id, song_id, music_platform, song_data, created_time, expires_time
                    FROM song_detail_cache 
                    WHERE song_id = ? AND music_platform = ? AND expires_time > ?
                """, (song_id, platform, now))
                
                row = cursor.fetchone()
                if row:
                    return SongDetailCache(
                        id=row[0],
                        song_id=row[1],
                        music_platform=row[2],
                        song_data=row[3],
                        created_time=datetime.fromisoformat(row[4]) if row[4] else datetime.now(),
                        expires_time=datetime.fromisoformat(row[5]) if row[5] else datetime.now()
                    )
                return None
        except Exception as e:
            logger.error(f"获取歌曲详情缓存失败: {e}", exc_info=True)
            return None
    
    def save_song_detail_cache(self, cache: SongDetailCache) -> bool:
        """保存歌曲详情缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO song_detail_cache 
                    (song_id, music_platform, song_data, created_time, expires_time)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    cache.song_id,
                    cache.music_platform, 
                    cache.song_data,
                    cache.created_time or datetime.now(),
                    cache.expires_time
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"保存歌曲详情缓存失败: {e}", exc_info=True)
            return False
    
    def cleanup_expired_song_detail_cache(self) -> int:
        """清理过期的歌曲详情缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                now = datetime.now()
                cursor.execute("DELETE FROM song_detail_cache WHERE expires_time <= ?", (now,))
                deleted = cursor.rowcount
                conn.commit()
                if deleted > 0:
                    logger.info(f"清理了 {deleted} 条过期歌曲详情缓存")
                return deleted
        except Exception as e:
            logger.error(f"清理歌曲详情缓存失败: {e}", exc_info=True)
            return 0

