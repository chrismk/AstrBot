"""
数据库管理器

负责：
1. 数据库连接管理
2. 表结构初始化
3. 数据库迁移
4. WAL 模式优化
"""

import sqlite3
from pathlib import Path
from typing import Optional, List, Tuple, Any
from datetime import datetime
from contextlib import contextmanager

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class DatabaseManager:
    """数据库管理器 - 使用 SQLite + WAL 模式"""
    
    # 数据库版本
    DB_VERSION = 4
    
    def __init__(self, db_path: str):
        """
        初始化数据库管理器
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._ensure_db_directory()
        self._init_database()
    
    def _ensure_db_directory(self):
        """确保数据库目录存在"""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
    
    def _init_database(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 启用外键约束
            cursor.execute("PRAGMA foreign_keys = ON")
            
            # 启用 WAL 模式（提高并发性能）
            cursor.execute("PRAGMA journal_mode = WAL")
            
            # 设置同步模式为 NORMAL（平衡性能和安全性）
            cursor.execute("PRAGMA synchronous = NORMAL")
            
            # 设置缓存大小（10MB）
            cursor.execute("PRAGMA cache_size = -10000")
            
            # 创建版本表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS db_version (
                    version INTEGER PRIMARY KEY,
                    applied_at DATETIME NOT NULL
                )
            """)
            
            # 检查当前版本
            cursor.execute("SELECT version FROM db_version ORDER BY version DESC LIMIT 1")
            row = cursor.fetchone()
            current_version = row[0] if row else 0
            
            # 执行迁移
            if current_version < self.DB_VERSION:
                self._migrate(cursor, current_version)
                cursor.execute(
                    "INSERT INTO db_version (version, applied_at) VALUES (?, ?)",
                    (self.DB_VERSION, datetime.now())
                )
            
            conn.commit()
            logger.info(f"[QuotaDB] 数据库初始化完成: {self.db_path} (版本: {self.DB_VERSION})")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"[QuotaDB] 数据库初始化失败: {e}")
            raise
        finally:
            conn.close()
    
    def _migrate(self, cursor: sqlite3.Cursor, from_version: int):
        """执行数据库迁移"""
        logger.info(f"[QuotaDB] 开始数据库迁移: v{from_version} -> v{self.DB_VERSION}")
        
        if from_version < 1:
            self._create_initial_schema(cursor)
        
        if from_version < 2:
            self._migrate_to_v2(cursor)
        
        if from_version < 3:
            self._migrate_to_v3(cursor)
        
        if from_version < 4:
            self._migrate_to_v4(cursor)
    
    def _create_initial_schema(self, cursor: sqlite3.Cursor):
        """创建初始数据库结构"""
        
        logger.info("[QuotaDB] 创建初始数据库结构...")
        
        # 1. 用户表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                platform TEXT NOT NULL,
                platform_user_id TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                last_active_at DATETIME,
                is_banned INTEGER DEFAULT 0,
                ban_reason TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_platform 
            ON users(platform, platform_user_id)
        """)
        
        # 2. 会员表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memberships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 0,
                expire_date DATE,
                auto_renew INTEGER DEFAULT 0,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memberships_user 
            ON memberships(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_memberships_expire 
            ON memberships(expire_date)
        """)
        
        # 3. 积分账户表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS points_accounts (
                user_id TEXT PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                total_spent INTEGER DEFAULT 0,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # 4. 积分流水表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS points_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                amount INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                type TEXT NOT NULL,
                source TEXT,
                description TEXT,
                related_order_id TEXT,
                created_at DATETIME NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_points_trans_user 
            ON points_transactions(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_points_trans_type 
            ON points_transactions(type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_points_trans_created 
            ON points_transactions(created_at)
        """)
        
        # 5. 配额规则表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quota_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                plugin_name TEXT NOT NULL,
                member_level INTEGER NOT NULL,
                daily_limit INTEGER NOT NULL,
                points_cost INTEGER DEFAULT 0,
                description TEXT,
                is_active INTEGER DEFAULT 1,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                UNIQUE(plugin_name, action_type, member_level)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_quota_rules_plugin 
            ON quota_rules(plugin_name)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_quota_rules_action 
            ON quota_rules(action_type)
        """)
        
        # 6. 配额使用记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quota_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                plugin_name TEXT NOT NULL,
                usage_date DATE NOT NULL,
                count INTEGER DEFAULT 1,
                points_spent INTEGER DEFAULT 0,
                created_at DATETIME NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_quota_usage_user_date 
            ON quota_usage(user_id, usage_date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_quota_usage_action_date 
            ON quota_usage(action_type, usage_date)
        """)
        
        # 7. 临时配额加成表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quota_boosts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                action_type TEXT,
                boost_amount INTEGER NOT NULL,
                expire_date DATE NOT NULL,
                source TEXT,
                description TEXT,
                is_used INTEGER DEFAULT 0,
                created_at DATETIME NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_quota_boosts_user_expire 
            ON quota_boosts(user_id, expire_date)
        """)
        
        # 8. 公告表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_announcements_created 
            ON announcements(created_at DESC)
        """)
        
        # 9. 公告已读记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS announcement_reads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                announcement_id INTEGER NOT NULL,
                read_at DATETIME NOT NULL,
                UNIQUE(user_id, announcement_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (announcement_id) REFERENCES announcements(id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_announcement_reads_user 
            ON announcement_reads(user_id)
        """)
        
        # 插入默认配额规则
        self._insert_default_rules(cursor)
        
        logger.info("[QuotaDB] 初始数据库结构创建完成")
    
    def _insert_default_rules(self, cursor: sqlite3.Cursor):
        """插入默认配额规则"""
        
        logger.info("[QuotaDB] 插入默认配额规则...")
        
        now = datetime.now()
        
        # 免费用户规则 (level=0) - 推广期全部无限
        free_rules = [
            ('music_search', 'music', 0, -1, 0, '音乐搜索'),
            ('music_download_128', 'music', 0, -1, 0, '下载128k音质'),
            ('music_download_320', 'music', 0, -1, 0, '下载320k音质'),
            ('music_download_flac', 'music', 0, -1, 0, '下载无损音质'),
            ('music_lyric', 'music', 0, -1, 0, '查看歌词'),
            ('douban_view', 'douban', 0, -1, 0, '查看豆瓣评分'),
            ('douban_search', 'douban', 0, -1, 0, '搜索豆瓣'),
            ('pansou_search', 'pansou', 0, -1, 0, '搜索云盘资源'),
            ('pansou_download', 'pansou', 0, -1, 0, '下载云盘资源'),
            ('file_process', 'file_processor', 0, -1, 0, '处理文件'),
        ]
        
        # 高级会员规则 (level=1) - 推广期全部无限
        premium_rules = [
            ('music_search', 'music', 1, -1, 0, '音乐搜索'),
            ('music_download_128', 'music', 1, -1, 0, '下载128k音质'),
            ('music_download_320', 'music', 1, -1, 0, '下载320k音质'),
            ('music_download_flac', 'music', 1, -1, 0, '下载无损音质'),
            ('music_lyric', 'music', 1, -1, 0, '查看歌词'),
            ('douban_view', 'douban', 1, -1, 0, '查看豆瓣评分'),
            ('douban_search', 'douban', 1, -1, 0, '搜索豆瓣'),
            ('pansou_search', 'pansou', 1, -1, 0, '搜索云盘资源'),
            ('pansou_download', 'pansou', 1, -1, 0, '下载云盘资源'),
            ('file_process', 'file_processor', 1, -1, 0, '处理文件'),
        ]
        
        # VIP会员规则 (level=2) - 全部无限
        vip_rules = [
            ('music_search', 'music', 2, -1, 0, '音乐搜索'),
            ('music_download_128', 'music', 2, -1, 0, '下载128k音质'),
            ('music_download_320', 'music', 2, -1, 0, '下载320k音质'),
            ('music_download_flac', 'music', 2, -1, 0, '下载无损音质'),
            ('music_lyric', 'music', 2, -1, 0, '查看歌词'),
            ('douban_view', 'douban', 2, -1, 0, '查看豆瓣评分'),
            ('douban_search', 'douban', 2, -1, 0, '搜索豆瓣'),
            ('pansou_search', 'pansou', 2, -1, 0, '搜索云盘资源'),
            ('pansou_download', 'pansou', 2, -1, 0, '下载云盘资源'),
            ('file_process', 'file_processor', 2, -1, 0, '处理文件'),
        ]
        
        all_rules = free_rules + premium_rules + vip_rules
        
        for rule in all_rules:
            action_type, plugin_name, level, daily_limit, points_cost, description = rule
            cursor.execute("""
                INSERT OR IGNORE INTO quota_rules 
                (action_type, plugin_name, member_level, daily_limit, points_cost, description, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (action_type, plugin_name, level, daily_limit, points_cost, description, now, now))
        
        logger.info(f"[QuotaDB] 已插入 {len(all_rules)} 条默认配额规则")
    
    def _migrate_to_v2(self, cursor: sqlite3.Cursor):
        """迁移到版本2：添加配额预留和统计分析表"""
        
        logger.info("[QuotaDB] 迁移到版本2...")
        
        # 1. 配额预留表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quota_reservations (
                reservation_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                plugin_name TEXT NOT NULL,
                points_cost INTEGER DEFAULT 0,
                expire_at DATETIME NOT NULL,
                status TEXT NOT NULL DEFAULT 'reserved',
                created_at DATETIME NOT NULL,
                confirmed_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_quota_reservations_user 
            ON quota_reservations(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_quota_reservations_status 
            ON quota_reservations(status, expire_at)
        """)
        
        # 2. 配额超限日志表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quota_exceeded_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                member_level INTEGER NOT NULL,
                plugin_name TEXT NOT NULL,
                log_date DATE NOT NULL,
                created_at DATETIME NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_quota_exceeded_user_date 
            ON quota_exceeded_logs(user_id, log_date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_quota_exceeded_action_date 
            ON quota_exceeded_logs(action_type, log_date)
        """)
        
        logger.info("[QuotaDB] 版本2迁移完成")
    
    def _migrate_to_v3(self, cursor: sqlite3.Cursor):
        """迁移到版本3：添加搜索统计表"""
        
        logger.info("[QuotaDB] 迁移到版本3...")
        
        # 搜索统计表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS search_statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                plugin_name TEXT NOT NULL,
                search_type TEXT DEFAULT 'keyword',
                keyword TEXT,
                platform TEXT,
                result_count INTEGER DEFAULT 0,
                has_download INTEGER DEFAULT 0,
                created_at DATETIME NOT NULL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_stats_user_plugin 
            ON search_statistics(user_id, plugin_name)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_stats_keyword 
            ON search_statistics(keyword)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_stats_created 
            ON search_statistics(created_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_stats_plugin_created 
            ON search_statistics(plugin_name, created_at)
        """)
        
        # 下载统计表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS download_statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                plugin_name TEXT NOT NULL,
                item_id TEXT NOT NULL,
                item_name TEXT,
                item_type TEXT,
                platform TEXT,
                quality TEXT,
                file_size INTEGER DEFAULT 0,
                source TEXT,
                created_at DATETIME NOT NULL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_download_stats_user_plugin 
            ON download_statistics(user_id, plugin_name)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_download_stats_item 
            ON download_statistics(item_id, plugin_name)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_download_stats_created 
            ON download_statistics(created_at)
        """)
        
        logger.info("[QuotaDB] 版本3迁移完成")
    
    def _migrate_to_v4(self, cursor: sqlite3.Cursor):
        """迁移到版本4：添加用户反馈表"""
        
        logger.info("[QuotaDB] 迁移到版本4...")
        
        # 用户反馈表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                plugin_name TEXT,
                feedback_type TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                admin_id TEXT,
                admin_reply TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME,
                replied_at DATETIME
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_feedback_user 
            ON user_feedback(user_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_feedback_status 
            ON user_feedback(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_feedback_created 
            ON user_feedback(created_at DESC)
        """)
        
        logger.info("[QuotaDB] 版本4迁移完成")
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接（上下文管理器）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 使用 Row 对象，可以通过列名访问
        try:
            yield conn
        finally:
            conn.close()
    
    def execute(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """执行查询并返回结果"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()
    
    def execute_one(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        """执行查询并返回单行结果"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()
    
    def execute_write(self, query: str, params: tuple = ()) -> int:
        """执行写操作并返回影响的行数"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount
    
    def execute_many(self, query: str, params_list: list) -> int:
        """
        批量执行写操作（减少IO）
        
        Args:
            query: SQL语句
            params_list: 参数列表，每个元素是一个参数元组
            
        Returns:
            影响的总行数
        """
        if not params_list:
            return 0
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            conn.commit()
            return cursor.rowcount
