"""数据库管理器"""

import sqlite3
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path

from .models import BookSearchCache, BookDownloadHistory, TelegramBookFileCache, BookDetailCache

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class BookDatabaseManager:
    """书籍数据库管理器"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """初始化数据库"""
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 书籍搜索结果缓存表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS book_search_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        cache_key TEXT UNIQUE NOT NULL,
                        user_id TEXT NOT NULL,
                        keyword TEXT NOT NULL,
                        results TEXT NOT NULL,
                        total_count INTEGER NOT NULL,
                        current_page INTEGER NOT NULL,
                        created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 书籍下载历史表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS book_download_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        book_ssid TEXT NOT NULL,
                        book_title TEXT NOT NULL,
                        author TEXT,
                        file_format TEXT NOT NULL,
                        file_size INTEGER DEFAULT 0,
                        download_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Telegram书籍文件缓存表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS telegram_book_file_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        book_ssid TEXT NOT NULL,
                        file_format TEXT,
                        file_tag TEXT NOT NULL,
                        file_id TEXT NOT NULL,
                        file_size INTEGER,
                        file_name TEXT,
                        book_info TEXT, -- 存储书籍详细信息的JSON字符串
                        mime_type TEXT,
                        uploaded_by TEXT,
                        upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        use_count INTEGER DEFAULT 0,
                        is_valid INTEGER DEFAULT 1,
                        UNIQUE(book_ssid, file_tag)
                    )
                """)
                
                # 书籍详情缓存表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS book_detail_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        book_ssid TEXT UNIQUE NOT NULL,
                        book_data TEXT NOT NULL,
                        created_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_time TIMESTAMP NOT NULL
                    )
                """)
                
                conn.commit()
                logger.info("书籍数据库初始化完成")
                
                # 检查并添加 book_info 列（用于从旧版本平滑升级）
                try:
                    cursor.execute("PRAGMA table_info(telegram_book_file_cache)")
                    columns = [column[1] for column in cursor.fetchall()]
                    if 'book_info' not in columns:
                        cursor.execute("ALTER TABLE telegram_book_file_cache ADD COLUMN book_info TEXT")
                        conn.commit()
                        logger.info("成功为 telegram_book_file_cache 表添加 'book_info' 字段")
                except Exception as e:
                    logger.warning(f"检查或添加 'book_info' 字段失败: {e}")
                
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise
    
    def save_search_cache(self, cache: BookSearchCache) -> bool:
        """保存搜索缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO book_search_cache 
                    (cache_key, user_id, keyword, results, total_count, current_page, created_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    cache.cache_key, cache.user_id, cache.keyword,
                    cache.results, cache.total_count, cache.current_page,
                    cache.created_time
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"保存搜索缓存失败: {e}")
            return False
    
    def get_search_cache(self, cache_key: str) -> Optional[BookSearchCache]:
        """获取搜索缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT cache_key, user_id, keyword, results, total_count, current_page, created_time, id
                    FROM book_search_cache WHERE cache_key = ?
                """, (cache_key,))
                
                row = cursor.fetchone()
                if row:
                    return BookSearchCache(
                        cache_key=row[0], user_id=row[1], keyword=row[2],
                        results=row[3], total_count=row[4], current_page=row[5],
                        created_time=datetime.fromisoformat(row[6]), id=row[7]
                    )
        except Exception as e:
            logger.error(f"获取搜索缓存失败: {e}")
        return None
    
    def get_daily_download_count(self, user_id: str) -> int:
        """获取用户今日下载次数"""
        try:
            today = datetime.now().date()
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM book_download_history 
                    WHERE user_id = ? AND DATE(download_time) = ?
                """, (user_id, today))
                
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"获取今日下载次数失败: {e}")
            return 0
    
    def add_download_history(self, history: BookDownloadHistory) -> bool:
        """添加下载历史"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO book_download_history 
                    (user_id, book_ssid, book_title, author, file_format, file_size, download_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    history.user_id, history.book_ssid, history.book_title,
                    history.author, history.file_format, history.file_size,
                    history.download_time
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"添加下载历史失败: {e}")
            return False
    
    def get_file_cache(self, book_ssid: str, file_tag: str) -> Optional[TelegramBookFileCache]:
        """根据SSID和文件tag获取有效的文件缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, book_ssid, file_format, file_tag, file_id, file_size, 
                           file_name, book_info, mime_type, uploaded_by, upload_time, 
                           use_count, is_valid
                    FROM telegram_book_file_cache 
                    WHERE book_ssid = ? AND file_tag = ? AND is_valid = 1
                """, (book_ssid, file_tag))
                row = cursor.fetchone()
                if row:
                    return TelegramBookFileCache(
                        id=row[0],
                        book_ssid=row[1],
                        file_format=row[2],
                        file_tag=row[3],
                        file_id=row[4],
                        file_size=row[5],
                        file_name=row[6],
                        book_info=row[7],
                        mime_type=row[8],
                        uploaded_by=row[9],
                        upload_time=row[10],
                        use_count=row[11],
                        is_valid=row[12]
                    )
                else:
                    pass
            return None
        except Exception as e:
            logger.error(f"获取文件缓存失败: {e}")
            return None
    
    def save_file_cache(self, cache: TelegramBookFileCache) -> bool:
        """保存或更新文件缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT id FROM telegram_book_file_cache WHERE book_ssid = ? AND file_tag = ?",
                    (cache.book_ssid, cache.file_tag)
                )
                existing = cursor.fetchone()
                if existing:
                    cursor.execute(
                        """
                        UPDATE telegram_book_file_cache
                        SET file_id = ?, file_size = ?, file_name = ?, book_info = ?, upload_time = ?, uploaded_by = ?, is_valid = 1, use_count = use_count + 1
                        WHERE id = ?
                        """,
                        (cache.file_id, cache.file_size, cache.file_name, cache.book_info, datetime.now(), cache.uploaded_by, existing[0])
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO telegram_book_file_cache
                        (book_ssid, file_format, file_tag, file_id, file_size, file_name, book_info, mime_type, uploaded_by, upload_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (cache.book_ssid, cache.file_format, cache.file_tag, cache.file_id, cache.file_size,
                         cache.file_name, cache.book_info, cache.mime_type, cache.uploaded_by, datetime.now())
                    )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"保存文件缓存失败: {e}")
            import traceback
            logger.error(f"异常堆栈: {traceback.format_exc()}")
            return False
    
    def update_file_cache_use_count(self, book_ssid: str, file_tag: str) -> bool:
        """更新文件缓存使用次数"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE telegram_book_file_cache 
                    SET use_count = use_count + 1 
                    WHERE book_ssid = ? AND file_tag = ?
                """, (book_ssid, file_tag))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"更新文件缓存使用次数失败: {e}")
            return False
    
    def cleanup_old_caches(self, days: int = 7):
        """清理旧缓存"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 清理搜索缓存
                cursor.execute("""
                    DELETE FROM book_search_cache WHERE created_time < ?
                """, (cutoff_date,))
                
                # 清理过期的详情缓存
                cursor.execute("""
                    DELETE FROM book_detail_cache WHERE expires_time < ?
                """, (datetime.now(),))
                
                conn.commit()
                logger.info(f"清理了 {days} 天前的缓存")
        except Exception as e:
            logger.error(f"清理缓存失败: {e}")
    
    def get_book_detail_cache(self, book_ssid: str) -> Optional[BookDetailCache]:
        """获取书籍详情缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT book_ssid, book_data, created_time, expires_time, id
                    FROM book_detail_cache WHERE book_ssid = ?
                """, (book_ssid,))
                
                row = cursor.fetchone()
                if row:
                    return BookDetailCache(
                        book_ssid=row[0], book_data=row[1],
                        created_time=datetime.fromisoformat(row[2]),
                        expires_time=datetime.fromisoformat(row[3]), id=row[4]
                    )
        except Exception as e:
            logger.error(f"获取书籍详情缓存失败: {e}")
        return None
    
    def save_book_detail_cache(self, cache: BookDetailCache) -> bool:
        """保存书籍详情缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO book_detail_cache 
                    (book_ssid, book_data, created_time, expires_time)
                    VALUES (?, ?, ?, ?)
                """, (
                    cache.book_ssid, cache.book_data,
                    cache.created_time, cache.expires_time
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"保存书籍详情缓存失败: {e}")
            return False
