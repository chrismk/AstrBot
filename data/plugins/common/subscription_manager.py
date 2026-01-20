"""
统一订阅系统

功能：
1. 榜单订阅 - 订阅热搜榜单变化推送
2. 关键词订阅 - 订阅特定关键词的搜索结果
3. 推送时间设置 - 自定义推送时间
4. 订阅管理 - 查看、修改、取消订阅

设计理念：
1. 遵循现有通用模块的设计模式（单例模式、全局获取函数）
2. 与 DatabaseManager、MessagePusher、PluginScheduler 集成
3. 支持跨平台推送
4. 支持多种订阅类型，可扩展

使用示例：
    from common import get_subscription_manager
    
    sub_manager = get_subscription_manager(db)
    
    # 订阅榜单
    sub_manager.subscribe_ranking(
        user_id="telegram:123456",
        plugin_name="music",
        push_time="19:00"
    )
    
    # 订阅关键词
    sub_manager.subscribe_keyword(
        user_id="telegram:123456",
        plugin_name="music",
        keyword="周杰伦",
        notify_on_new=True
    )
    
    # 获取用户订阅
    subs = sub_manager.get_user_subscriptions("telegram:123456")
    
    # 取消订阅
    sub_manager.unsubscribe(subscription_id)
"""

from datetime import datetime, timedelta
from datetime import time as datetime_time
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import time as time_module

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from .database_manager import DatabaseManager
from .message_formatter import get_separator

# P0优化：延迟导入避免循环依赖
def _mark_prefetcher_dirty():
    """标记预抓取器索引需要重建"""
    try:
        from .content_prefetcher import mark_prefetcher_index_dirty
        mark_prefetcher_index_dirty()
    except ImportError:
        pass


class SubscriptionType(Enum):
    """订阅类型枚举"""
    RANKING = "ranking"           # 榜单订阅
    KEYWORD = "keyword"           # 关键词订阅
    NEW_ENTRY = "new_entry"       # 新上榜订阅
    RISING = "rising"             # 飙升榜订阅
    SOURCE = "source"             # 订阅源订阅
    CUSTOM = "custom"             # 自定义订阅


class PushFrequency(Enum):
    """推送频率枚举"""
    DAILY = "daily"               # 每日推送（固定时间）
    WEEKLY = "weekly"             # 每周推送
    REALTIME = "realtime"         # 实时推送（有更新立即推送）
    MULTI_TIME = "multi_time"     # 多时段推送（如 8:00 和 20:00）
    WEEKLY_DIGEST = "weekly_digest"  # 每周摘要（周末汇总推送）
    CUSTOM = "custom"             # 自定义时间


# 推送频率显示名称
PUSH_FREQUENCY_NAMES = {
    PushFrequency.DAILY: "📅 每日定时",
    PushFrequency.WEEKLY: "📆 每周定时",
    PushFrequency.REALTIME: "⚡ 有更新立即推送",
    PushFrequency.MULTI_TIME: "🕐 多时段推送",
    PushFrequency.WEEKLY_DIGEST: "📰 每周摘要",
    PushFrequency.CUSTOM: "⚙️ 自定义"
}


@dataclass
class Subscription:
    """订阅数据类"""
    id: int
    user_id: str
    subscription_type: SubscriptionType
    plugin_name: str
    target: str                   # 订阅目标（榜单类型/关键词等）
    config: Dict[str, Any]        # 订阅配置
    push_frequency: PushFrequency
    push_time: str                # 推送时间 (HH:MM 格式，多时段用逗号分隔如 "08:00,20:00")
    push_days: List[int]          # 推送日期 (0-6, 0=周一)
    enabled: bool
    created_at: datetime
    last_push_at: Optional[datetime]
    next_push_at: Optional[datetime]
    source_id: Optional[int] = None  # 订阅源ID（仅订阅源类型有值）
    
    def get_push_times(self) -> List[str]:
        """获取所有推送时间点"""
        if not self.push_time:
            return ["19:00"]
        return [t.strip() for t in self.push_time.split(",")]
    
    def is_realtime(self) -> bool:
        """是否实时推送"""
        return self.push_frequency == PushFrequency.REALTIME
    
    def is_weekly_digest(self) -> bool:
        """是否每周摘要"""
        return self.push_frequency == PushFrequency.WEEKLY_DIGEST
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'subscription_type': self.subscription_type.value,
            'plugin_name': self.plugin_name,
            'target': self.target,
            'config': self.config,
            'push_frequency': self.push_frequency.value,
            'push_time': self.push_time,
            'push_days': self.push_days,
            'enabled': self.enabled,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_push_at': self.last_push_at.isoformat() if self.last_push_at else None,
            'next_push_at': self.next_push_at.isoformat() if self.next_push_at else None,
            'source_id': self.source_id
        }
    
    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> 'Subscription':
        """从数据库行创建订阅对象"""
        return cls(
            id=row['id'],
            user_id=row['user_id'],
            subscription_type=SubscriptionType(row['subscription_type']),
            plugin_name=row.get('plugin_name', ''),
            target=row.get('target', ''),
            config=json.loads(row['config']) if row.get('config') else {},
            push_frequency=PushFrequency(row.get('push_frequency', 'daily')),
            push_time=row.get('push_time') or '19:00',
            push_days=json.loads(row['push_days']) if row.get('push_days') else [0, 1, 2, 3, 4, 5, 6],
            enabled=bool(row.get('enabled', row.get('is_active', 1))),
            created_at=datetime.fromisoformat(row['created_at']) if row.get('created_at') else None,
            last_push_at=datetime.fromisoformat(row['last_push_at']) if row.get('last_push_at') else None,
            next_push_at=datetime.fromisoformat(row['next_push_at']) if row.get('next_push_at') else None,
            source_id=row.get('source_id')
        )


class SubscriptionManager:
    """
    统一订阅管理器
    
    功能：
    - 订阅管理（创建、查询、更新、删除）
    - 推送时间计算
    - 到期订阅查询
    - 与推送引擎集成
    """
    
    # 插件名称映射（用于显示）
    PLUGIN_NAMES = {
        'music': '🎵 音乐',
        'book': '📚 书籍',
        'douban': '🎬 豆瓣',
        'pansou': '☁️ 云盘'
    }
    
    # 订阅类型映射
    SUBSCRIPTION_TYPE_NAMES = {
        SubscriptionType.RANKING: '📊 榜单订阅',
        SubscriptionType.KEYWORD: '🔍 关键词订阅',
        SubscriptionType.NEW_ENTRY: '🆕 新上榜订阅',
        SubscriptionType.RISING: '📈 飙升榜订阅',
        SubscriptionType.CUSTOM: '⚙️ 自定义订阅'
    }
    
    # 批量日志写入配置
    LOG_BATCH_SIZE = 50                 # 批量写入阈值
    LOG_FLUSH_INTERVAL = 30             # 强制刷新间隔（秒）
    
    def __init__(self, db: DatabaseManager):
        """
        初始化订阅管理器
        
        Args:
            db: 数据库管理器
        """
        self.db = db
        self._init_db_tables()
        
        # 批量日志缓冲
        self._log_buffer: List[tuple] = []
        self._last_flush_time = time_module.time()
    
    def _init_db_tables(self):
        """初始化数据库表"""
        try:
            # 订阅表
            self.db.execute_write("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    subscription_type TEXT NOT NULL,
                    plugin_name TEXT DEFAULT '',
                    target TEXT DEFAULT '',
                    source_id INTEGER DEFAULT 0,
                    config TEXT,
                    push_frequency TEXT DEFAULT 'daily',
                    push_time TEXT DEFAULT '19:00',
                    push_days TEXT DEFAULT '[0,1,2,3,4,5,6]',
                    is_active INTEGER DEFAULT 1,
                    created_at DATETIME NOT NULL,
                    last_push_at DATETIME,
                    next_push_at DATETIME
                )
            """)
            
            # 迁移：添加 source_id 字段
            try:
                self.db.execute_write('ALTER TABLE subscriptions ADD COLUMN source_id INTEGER DEFAULT 0')
            except:
                pass
            try:
                self.db.execute_write('ALTER TABLE subscriptions ADD COLUMN is_active INTEGER DEFAULT 1')
            except:
                pass
            
            # 创建索引
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_subscriptions_user 
                ON subscriptions(user_id)
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_subscriptions_type 
                ON subscriptions(subscription_type)
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_subscriptions_next_push 
                ON subscriptions(next_push_at)
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_subscriptions_enabled 
                ON subscriptions(enabled)
            """)
            
            # 推送历史表
            self.db.execute_write("""
                CREATE TABLE IF NOT EXISTS subscription_push_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subscription_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    push_type TEXT NOT NULL,
                    content_preview TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    pushed_at DATETIME NOT NULL,
                    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
                )
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_sub_push_logs_sub 
                ON subscription_push_logs(subscription_id)
            """)
            
            # P0优化：内容去重表（记录已推送给用户的内容哈希）
            self.db.execute_write("""
                CREATE TABLE IF NOT EXISTS push_content_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    source_id INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    pushed_at DATETIME NOT NULL,
                    UNIQUE(user_id, source_id, content_hash)
                )
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_push_content_user_source 
                ON push_content_history(user_id, source_id)
            """)
            
            # P0优化：推送重试队列
            self.db.execute_write("""
                CREATE TABLE IF NOT EXISTS push_retry_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subscription_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    next_retry_at DATETIME NOT NULL,
                    last_error TEXT,
                    created_at DATETIME NOT NULL,
                    status TEXT DEFAULT 'pending',
                    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
                )
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_push_retry_next 
                ON push_retry_queue(next_retry_at, status)
            """)
            
            # 额外索引优化
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_subscriptions_source 
                ON subscriptions(source_id)
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_subscriptions_active_next 
                ON subscriptions(is_active, next_push_at)
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_push_logs_user 
                ON subscription_push_logs(user_id)
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_push_logs_time 
                ON subscription_push_logs(pushed_at)
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_content_history_time 
                ON push_content_history(pushed_at)
            """)
            
            # 用户反馈表（用于优化推荐）
            self.db.execute_write("""
                CREATE TABLE IF NOT EXISTS push_feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    source_id INTEGER NOT NULL,
                    push_log_id INTEGER,
                    content_hash TEXT,
                    feedback_type TEXT NOT NULL,
                    feedback_value INTEGER DEFAULT 0,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY (push_log_id) REFERENCES subscription_push_logs(id)
                )
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_feedback_user_source 
                ON push_feedback(user_id, source_id)
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_feedback_source 
                ON push_feedback(source_id, feedback_type)
            """)
            
            # 源评分缓存表（聚合用户反馈）
            self.db.execute_write("""
                CREATE TABLE IF NOT EXISTS source_ratings (
                    source_id INTEGER PRIMARY KEY,
                    total_useful INTEGER DEFAULT 0,
                    total_useless INTEGER DEFAULT 0,
                    total_feedback INTEGER DEFAULT 0,
                    avg_score REAL DEFAULT 0.0,
                    last_updated DATETIME
                )
            """)
            
            # P0优化：添加高性能复合索引
            # 用于 get_due_subscriptions 查询优化
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_subscriptions_due_push 
                ON subscriptions(is_active, next_push_at, source_id)
            """)
            # 用于按用户+类型查询优化
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_subscriptions_user_type 
                ON subscriptions(user_id, subscription_type, is_active)
            """)
            # 用于推送历史清理优化
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_push_logs_cleanup 
                ON subscription_push_logs(pushed_at, subscription_id)
            """)
            
            logger.info("[SubscriptionManager] 数据库表初始化完成")
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 数据库表初始化失败: {e}")
    
    # ==================== 批量日志写入 ====================
    
    def _add_log_to_buffer(self, log_entry: tuple):
        """
        添加日志到缓冲区
        
        Args:
            log_entry: (subscription_id, user_id, push_type, status, error_message, pushed_at)
        """
        self._log_buffer.append(log_entry)
        
        # 检查是否需要刷新
        should_flush = (
            len(self._log_buffer) >= self.LOG_BATCH_SIZE or
            time_module.time() - self._last_flush_time >= self.LOG_FLUSH_INTERVAL
        )
        
        if should_flush:
            self._flush_log_buffer()
    
    def _flush_log_buffer(self):
        """刷新日志缓冲区到数据库"""
        if not self._log_buffer:
            return
        
        try:
            # 批量插入
            self.db.execute_many("""
                INSERT INTO subscription_push_logs 
                (subscription_id, user_id, push_type, status, error_message, pushed_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, self._log_buffer)
            
            count = len(self._log_buffer)
            self._log_buffer.clear()
            self._last_flush_time = time_module.time()
            
            logger.debug(f"[SubscriptionManager] 批量写入 {count} 条推送日志")
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 批量写入日志失败: {e}")
            # 失败时尝试逐条写入
            self._fallback_write_logs()
    
    def _fallback_write_logs(self):
        """降级：逐条写入日志"""
        for entry in self._log_buffer:
            try:
                self.db.execute_write("""
                    INSERT INTO subscription_push_logs 
                    (subscription_id, user_id, push_type, status, error_message, pushed_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, entry)
            except Exception as e:
                logger.error(f"[SubscriptionManager] 写入单条日志失败: {e}")
        
        self._log_buffer.clear()
        self._last_flush_time = time_module.time()
    
    def flush_logs(self):
        """强制刷新日志缓冲区（供外部调用）"""
        self._flush_log_buffer()
    
    # ==================== 订阅管理 ====================
    
    def subscribe_ranking(
        self,
        user_id: str,
        plugin_name: str,
        ranking_type: str = "hot",
        push_time: str = "19:00",
        push_frequency: PushFrequency = PushFrequency.DAILY,
        push_days: List[int] = None,
        config: Dict[str, Any] = None
    ) -> Optional[int]:
        """
        订阅榜单
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称 (music/book/douban/pansou)
            ranking_type: 榜单类型 (hot/rising/new)
            push_time: 推送时间 (HH:MM)
            push_frequency: 推送频率
            push_days: 推送日期 (0-6)
            config: 额外配置
            
        Returns:
            订阅ID，失败返回 None
        """
        return self._create_subscription(
            user_id=user_id,
            subscription_type=SubscriptionType.RANKING,
            plugin_name=plugin_name,
            target=ranking_type,
            push_time=push_time,
            push_frequency=push_frequency,
            push_days=push_days,
            config=config
        )
    
    def subscribe_keyword(
        self,
        user_id: str,
        plugin_name: str,
        keyword: str,
        notify_on_new: bool = True,
        notify_on_ranking: bool = False,
        push_time: str = "19:00",
        push_frequency: PushFrequency = PushFrequency.DAILY,
        config: Dict[str, Any] = None
    ) -> Optional[int]:
        """
        订阅关键词
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称
            keyword: 关键词
            notify_on_new: 有新结果时通知
            notify_on_ranking: 进入榜单时通知
            push_time: 推送时间
            push_frequency: 推送频率
            config: 额外配置
            
        Returns:
            订阅ID
        """
        sub_config = config or {}
        sub_config.update({
            'notify_on_new': notify_on_new,
            'notify_on_ranking': notify_on_ranking
        })
        
        return self._create_subscription(
            user_id=user_id,
            subscription_type=SubscriptionType.KEYWORD,
            plugin_name=plugin_name,
            target=keyword,
            push_time=push_time,
            push_frequency=push_frequency,
            config=sub_config
        )
    
    def subscribe_new_entry(
        self,
        user_id: str,
        plugin_name: str,
        push_time: str = "19:00",
        min_searches: int = 3,
        config: Dict[str, Any] = None
    ) -> Optional[int]:
        """
        订阅新上榜
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称
            push_time: 推送时间
            min_searches: 最小搜索次数
            config: 额外配置
            
        Returns:
            订阅ID
        """
        sub_config = config or {}
        sub_config['min_searches'] = min_searches
        
        return self._create_subscription(
            user_id=user_id,
            subscription_type=SubscriptionType.NEW_ENTRY,
            plugin_name=plugin_name,
            target='new_entry',
            push_time=push_time,
            config=sub_config
        )
    
    def subscribe_rising(
        self,
        user_id: str,
        plugin_name: str,
        push_time: str = "19:00",
        min_growth_rate: float = 50.0,
        config: Dict[str, Any] = None
    ) -> Optional[int]:
        """
        订阅飙升榜
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称
            push_time: 推送时间
            min_growth_rate: 最小增长率
            config: 额外配置
            
        Returns:
            订阅ID
        """
        sub_config = config or {}
        sub_config['min_growth_rate'] = min_growth_rate
        
        return self._create_subscription(
            user_id=user_id,
            subscription_type=SubscriptionType.RISING,
            plugin_name=plugin_name,
            target='rising',
            push_time=push_time,
            config=sub_config
        )
    
    def _create_subscription(
        self,
        user_id: str,
        subscription_type: SubscriptionType,
        plugin_name: str,
        target: str,
        push_time: str = "19:00",
        push_frequency: PushFrequency = PushFrequency.DAILY,
        push_days: List[int] = None,
        config: Dict[str, Any] = None
    ) -> Optional[int]:
        """创建订阅（内部方法）"""
        try:
            if push_days is None:
                push_days = [0, 1, 2, 3, 4, 5, 6]  # 默认每天
            
            now = datetime.now()
            next_push = self._calculate_next_push_time(push_time, push_frequency, push_days)
            
            # P0优化：同时设置 enabled 和 is_active 保持一致
            self.db.execute_write("""
                INSERT OR REPLACE INTO subscriptions 
                (user_id, subscription_type, plugin_name, target, config, 
                 push_frequency, push_time, push_days, enabled, is_active, created_at, next_push_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
            """, (
                user_id,
                subscription_type.value,
                plugin_name,
                target,
                json.dumps(config) if config else None,
                push_frequency.value,
                push_time,
                json.dumps(push_days),
                now,
                next_push
            ))
            
            # 获取插入的ID
            row = self.db.execute_one("""
                SELECT id FROM subscriptions 
                WHERE user_id = ? AND subscription_type = ? AND plugin_name = ? AND target = ?
            """, (user_id, subscription_type.value, plugin_name, target))
            
            sub_id = row['id'] if row else None
            logger.info(f"[SubscriptionManager] 创建订阅: user={user_id}, type={subscription_type.value}, plugin={plugin_name}, target={target}, id={sub_id}")
            
            # 追踪任务进度
            if sub_id:
                try:
                    from .task_tracker import get_task_tracker
                    tracker = get_task_tracker()
                    tracker.track_subscribe(user_id)
                except Exception as e:
                    logger.debug(f"[SubscriptionManager] 任务追踪失败: {e}")
                
                # P0优化：标记预抓取器索引需要重建
                _mark_prefetcher_dirty()
            
            return sub_id
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 创建订阅失败: {e}")
            return None
    
    def unsubscribe(self, subscription_id: int) -> bool:
        """
        取消订阅
        
        Args:
            subscription_id: 订阅ID
            
        Returns:
            是否成功
        """
        try:
            self.db.execute_write("""
                DELETE FROM subscriptions WHERE id = ?
            """, (subscription_id,))
            logger.info(f"[SubscriptionManager] 取消订阅: id={subscription_id}")
            
            # P0优化：标记预抓取器索引需要重建
            _mark_prefetcher_dirty()
            
            return True
        except Exception as e:
            logger.error(f"[SubscriptionManager] 取消订阅失败: {e}")
            return False
    
    def unsubscribe_by_target(
        self,
        user_id: str,
        subscription_type: SubscriptionType,
        plugin_name: str,
        target: str
    ) -> bool:
        """
        按目标取消订阅
        
        Args:
            user_id: 用户ID
            subscription_type: 订阅类型
            plugin_name: 插件名称
            target: 订阅目标
            
        Returns:
            是否成功
        """
        try:
            self.db.execute_write("""
                DELETE FROM subscriptions 
                WHERE user_id = ? AND subscription_type = ? AND plugin_name = ? AND target = ?
            """, (user_id, subscription_type.value, plugin_name, target))
            logger.info(f"[SubscriptionManager] 取消订阅: user={user_id}, type={subscription_type.value}, target={target}")
            
            # P0优化：标记预抓取器索引需要重建
            _mark_prefetcher_dirty()
            
            return True
        except Exception as e:
            logger.error(f"[SubscriptionManager] 取消订阅失败: {e}")
            return False
    
    def enable_subscription(self, subscription_id: int) -> bool:
        """启用订阅"""
        try:
            # P0优化：同时更新 enabled 和 is_active 保持一致
            self.db.execute_write("""
                UPDATE subscriptions SET enabled = 1, is_active = 1 WHERE id = ?
            """, (subscription_id,))
            return True
        except Exception as e:
            logger.error(f"[SubscriptionManager] 启用订阅失败: {e}")
            return False
    
    def disable_subscription(self, subscription_id: int) -> bool:
        """禁用订阅"""
        try:
            # P0优化：同时更新 enabled 和 is_active 保持一致
            self.db.execute_write("""
                UPDATE subscriptions SET enabled = 0, is_active = 0 WHERE id = ?
            """, (subscription_id,))
            return True
        except Exception as e:
            logger.error(f"[SubscriptionManager] 禁用订阅失败: {e}")
            return False
    
    def update_push_time(
        self,
        subscription_id: int,
        push_time: str,
        push_days: List[int] = None
    ) -> bool:
        """
        更新推送时间
        
        Args:
            subscription_id: 订阅ID
            push_time: 新的推送时间 (HH:MM)
            push_days: 新的推送日期
            
        Returns:
            是否成功
        """
        try:
            # 获取当前订阅信息
            sub = self.get_subscription(subscription_id)
            if not sub:
                return False
            
            if push_days is None:
                push_days = sub.push_days
            
            next_push = self._calculate_next_push_time(push_time, sub.push_frequency, push_days)
            
            self.db.execute_write("""
                UPDATE subscriptions 
                SET push_time = ?, push_days = ?, next_push_at = ?
                WHERE id = ?
            """, (push_time, json.dumps(push_days), next_push, subscription_id))
            
            # 清除该订阅的推送历史，确保新时间能收到推送
            source_id = sub.source_id if sub.source_id else hash(f"{sub.plugin_name}:{sub.target}") % 1000000
            self.clear_content_history_for_subscription(sub.user_id, source_id)
            
            logger.info(f"[SubscriptionManager] 更新推送时间: id={subscription_id}, time={push_time}")
            return True
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 更新推送时间失败: {e}")
            return False
    
    # ==================== 查询方法 ====================
    
    def get_subscription(self, subscription_id: int) -> Optional[Subscription]:
        """获取单个订阅"""
        try:
            row = self.db.execute_one("""
                SELECT * FROM subscriptions WHERE id = ?
            """, (subscription_id,))
            
            if row:
                return Subscription.from_row(dict(row))
            return None
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取订阅失败: {e}")
            return None
    
    def get_user_subscriptions(
        self,
        user_id: str,
        plugin_name: str = None,
        subscription_type: SubscriptionType = None,
        enabled_only: bool = False
    ) -> List[Subscription]:
        """
        获取用户订阅列表
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称（可选）
            subscription_type: 订阅类型（可选）
            enabled_only: 仅返回启用的订阅
            
        Returns:
            订阅列表
        """
        try:
            conditions = ["user_id = ?"]
            params = [user_id]
            
            if plugin_name:
                conditions.append("plugin_name = ?")
                params.append(plugin_name)
            
            if subscription_type:
                conditions.append("subscription_type = ?")
                params.append(subscription_type.value)
            
            if enabled_only:
                # P0优化：统一使用 is_active 字段
                conditions.append("is_active = 1")
            
            where_clause = " AND ".join(conditions)
            
            rows = self.db.execute(f"""
                SELECT * FROM subscriptions
                WHERE {where_clause}
                ORDER BY created_at DESC
            """, tuple(params))
            
            return [Subscription.from_row(dict(row)) for row in rows]
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取用户订阅失败: {e}")
            return []
    
    def get_due_subscriptions(
        self, 
        buffer_minutes: int = 5,
        within_minutes: int = None,
        limit: int = 200
    ) -> List[Subscription]:
        """
        获取到期需要推送的订阅
        
        P0优化：
        1. 使用复合索引 idx_subscriptions_due_push
        2. 添加 LIMIT 防止大结果集
        3. 支持 within_minutes 参数精确控制时间窗口
        
        Args:
            buffer_minutes: 缓冲时间（分钟），提前获取即将到期的订阅
            within_minutes: 精确时间窗口（分钟），仅获取该时间范围内的订阅
            limit: 最大返回数量，防止大结果集
            
        Returns:
            到期订阅列表
        """
        try:
            now = datetime.now()
            
            # 使用 within_minutes 或 buffer_minutes
            effective_minutes = within_minutes if within_minutes is not None else buffer_minutes
            buffer_time = now + timedelta(minutes=effective_minutes)
            
            # P0优化：使用 is_active 字段（与索引匹配）
            # 查询使用 idx_subscriptions_due_push 索引
            rows = self.db.execute("""
                SELECT * FROM subscriptions
                WHERE is_active = 1 AND next_push_at <= ?
                ORDER BY next_push_at ASC
                LIMIT ?
            """, (buffer_time, limit))
            
            return [Subscription.from_row(dict(row)) for row in rows]
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取到期订阅失败: {e}")
            return []
    
    def get_all_active_subscriptions(
        self, 
        subscription_type: SubscriptionType = None
    ) -> List[Subscription]:
        """
        获取所有活跃订阅（用于预抓取调度）
        
        Args:
            subscription_type: 订阅类型过滤（可选）
            
        Returns:
            活跃订阅列表
        """
        try:
            # P0优化：统一使用 is_active 字段（与索引匹配）
            if subscription_type:
                rows = self.db.execute("""
                    SELECT * FROM subscriptions
                    WHERE is_active = 1 AND subscription_type = ?
                    ORDER BY next_push_at ASC
                """, (subscription_type.value,))
            else:
                rows = self.db.execute("""
                    SELECT * FROM subscriptions
                    WHERE is_active = 1
                    ORDER BY next_push_at ASC
                """)
            
            return [Subscription.from_row(dict(row)) for row in rows]
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取活跃订阅失败: {e}")
            return []
    
    def get_realtime_subscriptions(self, source_id: int = None) -> List[Subscription]:
        """
        获取实时推送的订阅
        
        Args:
            source_id: 订阅源ID（可选，用于筛选特定源的订阅）
            
        Returns:
            实时推送订阅列表
        """
        try:
            # P0优化：统一使用 is_active 字段
            if source_id:
                rows = self.db.execute("""
                    SELECT * FROM subscriptions
                    WHERE is_active = 1 AND push_frequency = ? AND target = ?
                """, (PushFrequency.REALTIME.value, str(source_id)))
            else:
                rows = self.db.execute("""
                    SELECT * FROM subscriptions
                    WHERE is_active = 1 AND push_frequency = ?
                """, (PushFrequency.REALTIME.value,))
            
            return [Subscription.from_row(dict(row)) for row in rows]
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取实时推送订阅失败: {e}")
            return []
    
    def get_weekly_digest_subscriptions(self) -> List[Subscription]:
        """
        获取每周摘要订阅
        
        Returns:
            每周摘要订阅列表
        """
        try:
            # P0优化：统一使用 is_active 字段
            rows = self.db.execute("""
                SELECT * FROM subscriptions
                WHERE is_active = 1 AND push_frequency = ?
            """, (PushFrequency.WEEKLY_DIGEST.value,))
            
            return [Subscription.from_row(dict(row)) for row in rows]
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取每周摘要订阅失败: {e}")
            return []
    
    def get_subscriptions_by_type(
        self,
        subscription_type: SubscriptionType,
        plugin_name: str = None,
        enabled_only: bool = True
    ) -> List[Subscription]:
        """
        按类型获取订阅
        
        Args:
            subscription_type: 订阅类型
            plugin_name: 插件名称（可选）
            enabled_only: 仅返回启用的订阅
            
        Returns:
            订阅列表
        """
        try:
            conditions = ["subscription_type = ?"]
            params = [subscription_type.value]
            
            if plugin_name:
                conditions.append("plugin_name = ?")
                params.append(plugin_name)
            
            if enabled_only:
                # P0优化：统一使用 is_active 字段
                conditions.append("is_active = 1")
            
            where_clause = " AND ".join(conditions)
            
            rows = self.db.execute(f"""
                SELECT * FROM subscriptions
                WHERE {where_clause}
                ORDER BY next_push_at ASC
            """, tuple(params))
            
            return [Subscription.from_row(dict(row)) for row in rows]
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 按类型获取订阅失败: {e}")
            return []
    
    def check_subscription_exists(
        self,
        user_id: str,
        subscription_type: SubscriptionType,
        plugin_name: str,
        target: str
    ) -> bool:
        """检查订阅是否存在"""
        try:
            row = self.db.execute_one("""
                SELECT id FROM subscriptions
                WHERE user_id = ? AND subscription_type = ? AND plugin_name = ? AND target = ?
            """, (user_id, subscription_type.value, plugin_name, target))
            return row is not None
        except Exception as e:
            logger.error(f"[SubscriptionManager] 检查订阅失败: {e}")
            return False
    
    def count_user_subscriptions(self, user_id: str) -> int:
        """统计用户订阅数量"""
        try:
            row = self.db.execute_one("""
                SELECT COUNT(*) as count FROM subscriptions WHERE user_id = ?
            """, (user_id,))
            return row['count'] if row else 0
        except Exception as e:
            logger.error(f"[SubscriptionManager] 统计订阅失败: {e}")
            return 0
    
    # ==================== 订阅源订阅 ====================
    
    def is_subscribed_to_source(self, user_id: str, source_id: int) -> bool:
        """检查用户是否已订阅某订阅源"""
        try:
            row = self.db.execute_one("""
                SELECT id FROM subscriptions 
                WHERE user_id = ? AND source_id = ? AND is_active = 1
            """, (user_id, source_id))
            return row is not None
        except Exception as e:
            logger.error(f"[SubscriptionManager] 检查订阅源订阅失败: {e}")
            return False
    
    def create_source_subscription(
        self,
        user_id: str,
        source_id: int,
        push_time: str = "19:00",
        push_frequency: PushFrequency = PushFrequency.DAILY,
        push_days: List[int] = None,
        plugin_name: str = "subscription"
    ) -> bool:
        """
        创建订阅源订阅
        
        Args:
            user_id: 用户ID
            source_id: 订阅源ID
            push_time: 推送时间
            push_frequency: 推送频率
            push_days: 推送日期
            plugin_name: 插件名称
        """
        try:
            if push_days is None:
                push_days = [0, 1, 2, 3, 4, 5, 6]
            
            now = datetime.now()
            next_push = self._calculate_next_push_time(push_time, push_frequency, push_days)
            
            self.db.execute_write("""
                INSERT INTO subscriptions 
                (user_id, subscription_type, source_id, target, push_time, push_frequency, 
                 push_days, is_active, created_at, next_push_at, plugin_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """, (
                user_id,
                SubscriptionType.SOURCE.value,
                source_id,
                str(source_id),  # target 为源ID的字符串表示
                push_time,
                push_frequency.value,
                json.dumps(push_days),
                now,
                next_push,
                plugin_name
            ))
            
            logger.info(f"[SubscriptionManager] 创建订阅源订阅: user={user_id}, source={source_id}")
            return True
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 创建订阅源订阅失败: {e}")
            return False
    
    def delete_source_subscription(self, user_id: str, source_id: int) -> bool:
        """删除订阅源订阅"""
        try:
            self.db.execute_write("""
                DELETE FROM subscriptions 
                WHERE user_id = ? AND source_id = ?
            """, (user_id, source_id))
            
            logger.info(f"[SubscriptionManager] 删除订阅源订阅: user={user_id}, source={source_id}")
            return True
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 删除订阅源订阅失败: {e}")
            return False
    
    # ==================== 推送相关 ====================
    
    def get_due_subscriptions(self, within_minutes: int = 5) -> List[Subscription]:
        """
        获取即将到期需要推送的订阅
        
        这是调度器的核心查询方法，基于 next_push_at 字段直接查询。
        
        Args:
            within_minutes: 查询未来多少分钟内需要推送的订阅
            
        Returns:
            需要推送的订阅列表
        """
        try:
            now = datetime.now()
            end_time = now + timedelta(minutes=within_minutes)
            
            rows = self.db.execute("""
                SELECT * FROM subscriptions
                WHERE (is_active = 1 OR enabled = 1)
                  AND next_push_at IS NOT NULL
                  AND next_push_at <= ?
                ORDER BY next_push_at ASC
            """, (end_time,))
            
            return [Subscription.from_row(dict(row)) for row in rows]
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取待推送订阅失败: {e}")
            return []
    
    def mark_pushed(self, subscription_id: int, success: bool = True, error_message: str = None):
        """
        标记订阅已推送
        
        Args:
            subscription_id: 订阅ID
            success: 是否成功
            error_message: 错误信息
        """
        try:
            sub = self.get_subscription(subscription_id)
            if not sub:
                return
            
            now = datetime.now()
            next_push = self._calculate_next_push_time(
                sub.push_time, sub.push_frequency, sub.push_days
            )
            
            # 更新订阅
            self.db.execute_write("""
                UPDATE subscriptions 
                SET last_push_at = ?, next_push_at = ?
                WHERE id = ?
            """, (now, next_push, subscription_id))
            
            # 批量记录推送日志（减少IO）
            self._add_log_to_buffer((
                subscription_id,
                sub.user_id,
                sub.subscription_type.value,
                'success' if success else 'failed',
                error_message,
                now
            ))
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 标记推送失败: {e}")
    
    def _calculate_next_push_time(
        self,
        push_time: str,
        push_frequency: PushFrequency,
        push_days: List[int]
    ) -> datetime:
        """
        计算下次推送时间
        
        支持的推送模式：
        - DAILY: 每日定时推送
        - WEEKLY: 每周定时推送
        - REALTIME: 实时推送（检查间隔15分钟）
        - MULTI_TIME: 多时段推送（如 "08:00,20:00"）
        - WEEKLY_DIGEST: 每周摘要（周日推送）
        """
        try:
            now = datetime.now()
            
            # 实时推送：15分钟后检查
            if push_frequency == PushFrequency.REALTIME:
                return now + timedelta(minutes=15)
            
            # 每周摘要：周日指定时间推送
            if push_frequency == PushFrequency.WEEKLY_DIGEST:
                hour, minute = 19, 0  # 默认周日19:00
                if push_time:
                    try:
                        hour, minute = map(int, push_time.split(':')[:1][0].split(':'))
                    except:
                        hour, minute = map(int, push_time.split(',')[0].split(':'))
                
                # 计算到下个周日的天数
                days_until_sunday = (6 - now.weekday()) % 7
                if days_until_sunday == 0:
                    # 今天是周日，检查时间是否已过
                    today_push = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if now >= today_push:
                        days_until_sunday = 7
                
                next_sunday = now + timedelta(days=days_until_sunday)
                return next_sunday.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # 多时段推送：找最近的下一个时间点
            if push_frequency == PushFrequency.MULTI_TIME:
                push_times = [t.strip() for t in push_time.split(',')]
                candidates = []
                
                for pt in push_times:
                    try:
                        hour, minute = map(int, pt.split(':'))
                        # 今天的这个时间点
                        today_push = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        
                        if now < today_push and now.weekday() in push_days:
                            candidates.append(today_push)
                        
                        # 明天及之后的时间点
                        for i in range(1, 8):
                            next_day = now + timedelta(days=i)
                            if next_day.weekday() in push_days:
                                candidates.append(next_day.replace(hour=hour, minute=minute, second=0, microsecond=0))
                                break
                    except:
                        continue
                
                if candidates:
                    return min(candidates)
            
            # 解析单个推送时间
            first_time = push_time.split(',')[0].strip() if push_time else "19:00"
            hour, minute = map(int, first_time.split(':'))
            
            # 今天的推送时间
            today_push = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            if push_frequency == PushFrequency.DAILY:
                # 每日推送
                if now < today_push:
                    # 今天还没到推送时间
                    if now.weekday() in push_days:
                        return today_push
                
                # 找下一个推送日
                for i in range(1, 8):
                    next_day = now + timedelta(days=i)
                    if next_day.weekday() in push_days:
                        return next_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            elif push_frequency == PushFrequency.WEEKLY:
                # 每周推送（取 push_days 中的第一天）
                target_day = push_days[0] if push_days else 0
                days_ahead = target_day - now.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                next_push = now + timedelta(days=days_ahead)
                return next_push.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # 默认返回明天同一时间
            return today_push + timedelta(days=1)
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 计算下次推送时间失败: {e}")
            return datetime.now() + timedelta(days=1)
    
    # ==================== 格式化方法 ====================
    
    def format_subscription_list(self, subscriptions: List[Subscription]) -> str:
        """格式化订阅列表"""
        if not subscriptions:
            return "📭 暂无订阅"
        
        separator = get_separator()
        lines = ["📬 我的订阅", separator]
        
        for i, sub in enumerate(subscriptions, 1):
            plugin_name = self.PLUGIN_NAMES.get(sub.plugin_name, sub.plugin_name)
            type_name = self.SUBSCRIPTION_TYPE_NAMES.get(sub.subscription_type, sub.subscription_type.value)
            status = "✅" if sub.enabled else "⏸️"
            
            # 目标显示
            if sub.subscription_type == SubscriptionType.KEYWORD:
                target_display = f"「{sub.target}」"
            elif sub.subscription_type == SubscriptionType.RANKING:
                target_display = "热搜榜" if sub.target == "hot" else sub.target
            else:
                target_display = ""
            
            lines.append(f"{i}. {status} {plugin_name} {target_display}")
            lines.append(f"   类型: {type_name}")
            lines.append(f"   推送: {sub.push_time}")
            if sub.next_push_at:
                lines.append(f"   下次: {sub.next_push_at.strftime('%m-%d %H:%M')}")
            lines.append("")
        
        return "\n".join(lines)
    
    def format_subscription_detail(self, sub: Subscription) -> str:
        """格式化订阅详情"""
        plugin_name = self.PLUGIN_NAMES.get(sub.plugin_name, sub.plugin_name)
        type_name = self.SUBSCRIPTION_TYPE_NAMES.get(sub.subscription_type, sub.subscription_type.value)
        status = "✅ 已启用" if sub.enabled else "⏸️ 已暂停"
        
        separator = get_separator()
        lines = [
            f"📬 订阅详情 #{sub.id}",
            separator,
            f"📱 平台: {plugin_name}",
            f"📋 类型: {type_name}",
            f"🎯 目标: {sub.target}",
            f"⏰ 推送时间: {sub.push_time}",
            f"📅 推送日期: {self._format_push_days(sub.push_days)}",
            f"📊 状态: {status}",
            f"📆 创建时间: {sub.created_at.strftime('%Y-%m-%d %H:%M') if sub.created_at else '-'}",
        ]
        
        if sub.last_push_at:
            lines.append(f"📤 上次推送: {sub.last_push_at.strftime('%Y-%m-%d %H:%M')}")
        if sub.next_push_at:
            lines.append(f"⏳ 下次推送: {sub.next_push_at.strftime('%Y-%m-%d %H:%M')}")
        
        return "\n".join(lines)
    
    def _format_push_days(self, push_days: List[int]) -> str:
        """格式化推送日期"""
        if push_days == [0, 1, 2, 3, 4, 5, 6]:
            return "每天"
        
        day_names = ['一', '二', '三', '四', '五', '六', '日']
        return "周" + "、".join([day_names[d] for d in push_days])
    
    # ==================== 统计方法 ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """获取订阅统计"""
        try:
            # 总订阅数
            total_row = self.db.execute_one("""
                SELECT COUNT(*) as total FROM subscriptions
            """)
            
            # 启用订阅数
            enabled_row = self.db.execute_one("""
                SELECT COUNT(*) as enabled FROM subscriptions WHERE enabled = 1
            """)
            
            # 按类型统计
            type_rows = self.db.execute("""
                SELECT subscription_type, COUNT(*) as count 
                FROM subscriptions 
                GROUP BY subscription_type
            """)
            
            # 按插件统计
            plugin_rows = self.db.execute("""
                SELECT plugin_name, COUNT(*) as count 
                FROM subscriptions 
                GROUP BY plugin_name
            """)
            
            return {
                'total': total_row['total'] if total_row else 0,
                'enabled': enabled_row['enabled'] if enabled_row else 0,
                'by_type': {row['subscription_type']: row['count'] for row in type_rows},
                'by_plugin': {row['plugin_name']: row['count'] for row in plugin_rows}
            }
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取统计失败: {e}")
            return {'total': 0, 'enabled': 0, 'by_type': {}, 'by_plugin': {}}
    
    def cleanup_old_logs(self, days: int = 30) -> int:
        """清理旧的推送日志"""
        try:
            cutoff = datetime.now() - timedelta(days=days)
            self.db.execute_write("""
                DELETE FROM subscription_push_logs WHERE pushed_at < ?
            """, (cutoff,))
            logger.info(f"[SubscriptionManager] 清理 {days} 天前的推送日志")
            return 0
        except Exception as e:
            logger.error(f"[SubscriptionManager] 清理日志失败: {e}")
            return 0
    
    def count_all_subscriptions(self) -> int:
        """统计所有订阅数"""
        try:
            row = self.db.execute_one(
                "SELECT COUNT(*) as count FROM subscriptions"
            )
            return row['count'] if row else 0
        except Exception as e:
            logger.error(f"[SubscriptionManager] 统计订阅数失败: {e}")
            return 0
    
    def count_active_users(self) -> int:
        """统计活跃用户数（有订阅的用户）"""
        try:
            row = self.db.execute_one(
                "SELECT COUNT(DISTINCT user_id) as count FROM subscriptions WHERE enabled = 1"
            )
            return row['count'] if row else 0
        except Exception as e:
            logger.error(f"[SubscriptionManager] 统计活跃用户失败: {e}")
            return 0
    
    # ==================== 推送日志查询 ====================
    
    def get_push_stats(self) -> Dict[str, int]:
        """获取推送统计（成功/失败数）"""
        try:
            rows = self.db.execute("""
                SELECT status, COUNT(*) as count 
                FROM subscription_push_logs 
                GROUP BY status
            """)
            return {row['status']: row['count'] for row in rows}
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取推送统计失败: {e}")
            return {}
    
    def get_push_stats_detail(self) -> Dict[str, Any]:
        """获取推送统计详情（今日/本周）"""
        try:
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=now.weekday())
            
            # 今日统计
            today_row = self.db.execute_one("""
                SELECT 
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM subscription_push_logs 
                WHERE pushed_at >= ?
            """, (today_start,))
            
            today_success = today_row['success'] or 0 if today_row else 0
            today_failed = today_row['failed'] or 0 if today_row else 0
            today_total = today_success + today_failed
            
            # 本周统计
            week_row = self.db.execute_one("""
                SELECT 
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM subscription_push_logs 
                WHERE pushed_at >= ?
            """, (week_start,))
            
            week_success = week_row['success'] or 0 if week_row else 0
            week_failed = week_row['failed'] or 0 if week_row else 0
            week_total = week_success + week_failed
            
            # 按类型统计
            type_rows = self.db.execute("""
                SELECT push_type, COUNT(*) as count 
                FROM subscription_push_logs 
                WHERE pushed_at >= ?
                GROUP BY push_type
            """, (week_start,))
            
            return {
                'today_success': today_success,
                'today_failed': today_failed,
                'today_rate': (today_success / today_total * 100) if today_total > 0 else 0,
                'week_success': week_success,
                'week_failed': week_failed,
                'week_rate': (week_success / week_total * 100) if week_total > 0 else 0,
                'by_type': {row['push_type']: row['count'] for row in type_rows}
            }
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取推送统计详情失败: {e}")
            return {}
    
    def get_push_logs(
        self, 
        page: int = 1, 
        page_size: int = 10,
        filter_type: str = None,
        filter_value: str = None
    ) -> Dict[str, Any]:
        """
        获取推送日志
        
        Args:
            page: 页码
            page_size: 每页数量
            filter_type: 筛选类型 (user/source/status)
            filter_value: 筛选值
            
        Returns:
            {items: [...], total: int, total_pages: int}
        """
        try:
            # 构建查询条件
            conditions = []
            params = []
            
            if filter_type == 'status' and filter_value:
                conditions.append("status = ?")
                params.append(filter_value)
            elif filter_type == 'user' and filter_value:
                conditions.append("user_id LIKE ?")
                params.append(f"%{filter_value}%")
            
            where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
            
            # 获取总数
            count_row = self.db.execute_one(f"""
                SELECT COUNT(*) as total FROM subscription_push_logs {where_clause}
            """, params)
            total = count_row['total'] if count_row else 0
            total_pages = max(1, (total + page_size - 1) // page_size)
            
            # 获取日志
            offset = (page - 1) * page_size
            rows = self.db.execute(f"""
                SELECT id, subscription_id, user_id, push_type, status, error_message, pushed_at
                FROM subscription_push_logs 
                {where_clause}
                ORDER BY pushed_at DESC
                LIMIT ? OFFSET ?
            """, params + [page_size, offset])
            
            items = []
            for row in rows:
                items.append({
                    'id': row['id'],
                    'subscription_id': row['subscription_id'],
                    'user_id': row['user_id'],
                    'push_type': row['push_type'],
                    'status': row['status'],
                    'error_message': row['error_message'],
                    'pushed_at': row['pushed_at']
                })
            
            return {
                'items': items,
                'total': total,
                'total_pages': total_pages,
                'page': page
            }
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取推送日志失败: {e}")
            return {'items': [], 'total': 0, 'total_pages': 1, 'page': 1}
    
    # ==================== P0: 内容去重 ====================
    
    def is_content_pushed(self, user_id: str, source_id: int, content_hash: str) -> bool:
        """
        检查内容是否已推送给用户
        
        Args:
            user_id: 用户ID
            source_id: 订阅源ID
            content_hash: 内容哈希
            
        Returns:
            是否已推送
        """
        try:
            row = self.db.execute_one("""
                SELECT id FROM push_content_history 
                WHERE user_id = ? AND source_id = ? AND content_hash = ?
            """, (user_id, source_id, content_hash))
            return row is not None
        except Exception as e:
            logger.error(f"[SubscriptionManager] 检查内容去重失败: {e}")
            return False
    
    def mark_content_pushed(self, user_id: str, source_id: int, content_hash: str) -> bool:
        """
        标记内容已推送给用户
        
        Args:
            user_id: 用户ID
            source_id: 订阅源ID
            content_hash: 内容哈希
            
        Returns:
            是否成功
        """
        try:
            self.db.execute_write("""
                INSERT OR IGNORE INTO push_content_history 
                (user_id, source_id, content_hash, pushed_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, source_id, content_hash, datetime.now()))
            return True
        except Exception as e:
            logger.error(f"[SubscriptionManager] 标记内容已推送失败: {e}")
            return False
    
    def cleanup_old_content_history(self, days: int = 7) -> int:
        """
        清理旧的内容推送历史（保留最近N天）
        
        Args:
            days: 保留天数
            
        Returns:
            删除的记录数
        """
        try:
            cutoff = datetime.now() - timedelta(days=days)
            self.db.execute_write("""
                DELETE FROM push_content_history WHERE pushed_at < ?
            """, (cutoff,))
            logger.info(f"[SubscriptionManager] 清理 {days} 天前的内容推送历史")
            return 0
        except Exception as e:
            logger.error(f"[SubscriptionManager] 清理内容历史失败: {e}")
            return 0
    
    def get_user_recent_push(self, user_id: str, max_age_minutes: int = 30) -> Optional[Dict]:
        """
        获取用户最近一次推送的信息（用于文本反馈匹配）
        
        Args:
            user_id: 用户ID
            max_age_minutes: 最大时间范围（分钟），超过此时间的推送不再接受反馈
            
        Returns:
            {'source_id': int, 'content_hash': str, 'pushed_at': datetime} 或 None
        """
        try:
            cutoff = datetime.now() - timedelta(minutes=max_age_minutes)
            row = self.db.execute_one("""
                SELECT source_id, content_hash, pushed_at
                FROM push_content_history 
                WHERE user_id = ? AND pushed_at >= ?
                ORDER BY pushed_at DESC
                LIMIT 1
            """, (user_id, cutoff))
            
            if row:
                return {
                    'source_id': row['source_id'],
                    'content_hash': row['content_hash'],
                    'pushed_at': row['pushed_at']
                }
            return None
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取用户最近推送失败: {e}")
            return None
    
    def clear_content_history_for_subscription(self, user_id: str, source_id: int) -> bool:
        """
        清除特定订阅的推送历史（用于用户修改推送时间后重新推送）
        
        Args:
            user_id: 用户ID
            source_id: 订阅源ID
            
        Returns:
            是否成功
        """
        try:
            self.db.execute_write("""
                DELETE FROM push_content_history 
                WHERE user_id = ? AND source_id = ?
            """, (user_id, source_id))
            logger.debug(f"[SubscriptionManager] 清除推送历史: user={user_id}, source={source_id}")
            return True
        except Exception as e:
            logger.error(f"[SubscriptionManager] 清除推送历史失败: {e}")
            return False
    
    # ==================== P0: 推送重试队列 ====================
    
    def add_to_retry_queue(
        self, 
        subscription_id: int, 
        user_id: str, 
        content: str, 
        error: str = None,
        max_retries: int = 3
    ) -> bool:
        """
        添加到推送重试队列
        
        Args:
            subscription_id: 订阅ID
            user_id: 用户ID
            content: 推送内容
            error: 错误信息
            max_retries: 最大重试次数
            
        Returns:
            是否成功
        """
        try:
            now = datetime.now()
            # 首次重试延迟1分钟
            next_retry = now + timedelta(minutes=1)
            
            self.db.execute_write("""
                INSERT INTO push_retry_queue 
                (subscription_id, user_id, content, retry_count, max_retries, 
                 next_retry_at, last_error, created_at, status)
                VALUES (?, ?, ?, 0, ?, ?, ?, ?, 'pending')
            """, (subscription_id, user_id, content, max_retries, next_retry, error, now))
            
            logger.info(f"[SubscriptionManager] 添加到重试队列: sub={subscription_id}, user={user_id}")
            return True
        except Exception as e:
            logger.error(f"[SubscriptionManager] 添加到重试队列失败: {e}")
            return False
    
    def get_pending_retries(self, limit: int = 50) -> List[Dict]:
        """
        获取待重试的推送
        
        Args:
            limit: 最大数量
            
        Returns:
            待重试列表
        """
        try:
            now = datetime.now()
            rows = self.db.execute("""
                SELECT id, subscription_id, user_id, content, retry_count, max_retries, last_error
                FROM push_retry_queue 
                WHERE status = 'pending' AND next_retry_at <= ?
                ORDER BY next_retry_at ASC
                LIMIT ?
            """, (now, limit))
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取待重试推送失败: {e}")
            return []
    
    def update_retry_status(
        self, 
        retry_id: int, 
        success: bool, 
        error: str = None
    ) -> bool:
        """
        更新重试状态
        
        Args:
            retry_id: 重试记录ID
            success: 是否成功
            error: 错误信息
            
        Returns:
            是否成功
        """
        try:
            if success:
                # 成功，标记完成
                self.db.execute_write("""
                    UPDATE push_retry_queue 
                    SET status = 'success'
                    WHERE id = ?
                """, (retry_id,))
                logger.info(f"[SubscriptionManager] 重试成功: retry_id={retry_id}")
            else:
                # 失败，检查是否还能重试
                row = self.db.execute_one("""
                    SELECT retry_count, max_retries, subscription_id 
                    FROM push_retry_queue WHERE id = ?
                """, (retry_id,))
                
                if row:
                    retry_count = row['retry_count'] + 1
                    if retry_count >= row['max_retries']:
                        # 达到最大重试次数，标记失败
                        self.db.execute_write("""
                            UPDATE push_retry_queue 
                            SET status = 'failed', retry_count = ?, last_error = ?
                            WHERE id = ?
                        """, (retry_count, error, retry_id))
                        
                        # 暂停订阅并记录
                        self._handle_push_failure(row['subscription_id'], error)
                        logger.warning(f"[SubscriptionManager] 重试失败，已暂停订阅: retry_id={retry_id}")
                    else:
                        # 指数退避：1分钟 -> 5分钟 -> 15分钟
                        delays = [1, 5, 15, 30, 60]
                        delay_minutes = delays[min(retry_count, len(delays) - 1)]
                        next_retry = datetime.now() + timedelta(minutes=delay_minutes)
                        
                        self.db.execute_write("""
                            UPDATE push_retry_queue 
                            SET retry_count = ?, next_retry_at = ?, last_error = ?
                            WHERE id = ?
                        """, (retry_count, next_retry, error, retry_id))
                        logger.info(f"[SubscriptionManager] 重试失败，{delay_minutes}分钟后重试: retry_id={retry_id}")
            
            return True
        except Exception as e:
            logger.error(f"[SubscriptionManager] 更新重试状态失败: {e}")
            return False
    
    def _handle_push_failure(self, subscription_id: int, error: str):
        """
        处理推送失败（连续失败后暂停订阅）
        
        Args:
            subscription_id: 订阅ID
            error: 错误信息
        """
        try:
            # 暂停订阅
            self.db.execute_write("""
                UPDATE subscriptions 
                SET is_active = 0
                WHERE id = ?
            """, (subscription_id,))
            
            # 记录日志
            self.db.execute_write("""
                INSERT INTO subscription_push_logs 
                (subscription_id, user_id, push_type, content_preview, status, error_message, pushed_at)
                SELECT id, user_id, 'auto_pause', '连续推送失败，已自动暂停', 'paused', ?, ?
                FROM subscriptions WHERE id = ?
            """, (error, datetime.now(), subscription_id))
            
            logger.warning(f"[SubscriptionManager] 订阅 {subscription_id} 因连续推送失败已暂停")
        except Exception as e:
            logger.error(f"[SubscriptionManager] 处理推送失败时出错: {e}")
    
    def cleanup_old_retries(self, days: int = 7) -> int:
        """
        清理旧的重试记录
        
        Args:
            days: 保留天数
            
        Returns:
            删除的记录数
        """
        try:
            cutoff = datetime.now() - timedelta(days=days)
            self.db.execute_write("""
                DELETE FROM push_retry_queue 
                WHERE created_at < ? AND status IN ('success', 'failed')
            """, (cutoff,))
            logger.info(f"[SubscriptionManager] 清理 {days} 天前的重试记录")
            return 0
        except Exception as e:
            logger.error(f"[SubscriptionManager] 清理重试记录失败: {e}")
            return 0
    
    def get_retry_stats(self) -> Dict:
        """获取重试队列统计"""
        try:
            rows = self.db.execute("""
                SELECT status, COUNT(*) as count 
                FROM push_retry_queue 
                GROUP BY status
            """)
            return {row['status']: row['count'] for row in rows}
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取重试统计失败: {e}")
            return {}
    
    # ==================== 用户反馈系统 ====================
    
    def submit_feedback(
        self, 
        user_id: str, 
        source_id: int, 
        feedback_type: str,
        push_log_id: int = None,
        content_hash: str = None
    ) -> bool:
        """
        提交用户反馈
        
        Args:
            user_id: 用户ID
            source_id: 订阅源ID
            feedback_type: 反馈类型 (useful/useless/mute/report)
            push_log_id: 推送日志ID（可选）
            content_hash: 内容哈希（可选）
            
        Returns:
            是否成功
        """
        try:
            # 反馈值映射
            feedback_values = {
                'useful': 1,      # 有用 +1
                'useless': -1,    # 无用 -1
                'report': -2      # 举报
            }
            
            feedback_value = feedback_values.get(feedback_type, 0)
            
            # 检查是否已反馈过（同一用户对同一源的同一内容）
            if content_hash:
                existing = self.db.execute_one("""
                    SELECT id FROM push_feedback 
                    WHERE user_id = ? AND source_id = ? AND content_hash = ?
                """, (user_id, source_id, content_hash))
                
                if existing:
                    # 更新已有反馈
                    self.db.execute_write("""
                        UPDATE push_feedback 
                        SET feedback_type = ?, feedback_value = ?, created_at = ?
                        WHERE id = ?
                    """, (feedback_type, feedback_value, datetime.now(), existing['id']))
                else:
                    # 插入新反馈
                    self.db.execute_write("""
                        INSERT INTO push_feedback 
                        (user_id, source_id, push_log_id, content_hash, feedback_type, feedback_value, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (user_id, source_id, push_log_id, content_hash, feedback_type, feedback_value, datetime.now()))
            else:
                # 无内容哈希，直接插入
                self.db.execute_write("""
                    INSERT INTO push_feedback 
                    (user_id, source_id, push_log_id, content_hash, feedback_type, feedback_value, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user_id, source_id, push_log_id, content_hash, feedback_type, feedback_value, datetime.now()))
            
            # 更新源评分缓存
            self._update_source_rating(source_id)
            
            # 追踪任务进度
            try:
                from .task_tracker import get_task_tracker
                tracker = get_task_tracker()
                tracker.track_feedback(user_id)
            except Exception as e:
                logger.debug(f"[SubscriptionManager] 任务追踪失败: {e}")
            
            logger.info(f"[SubscriptionManager] 用户反馈: user={user_id}, source={source_id}, type={feedback_type}")
            return True
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 提交反馈失败: {e}")
            return False
    
    def _update_source_rating(self, source_id: int):
        """更新源评分缓存"""
        try:
            # 统计反馈
            stats = self.db.execute_one("""
                SELECT 
                    SUM(CASE WHEN feedback_type = 'useful' THEN 1 ELSE 0 END) as useful,
                    SUM(CASE WHEN feedback_type = 'useless' THEN 1 ELSE 0 END) as useless,
                    COUNT(*) as total,
                    AVG(feedback_value) as avg_score
                FROM push_feedback 
                WHERE source_id = ?
            """, (source_id,))
            
            if stats:
                # 更新或插入评分缓存
                self.db.execute_write("""
                    INSERT OR REPLACE INTO source_ratings 
                    (source_id, total_useful, total_useless, total_feedback, avg_score, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    source_id,
                    stats['useful'] or 0,
                    stats['useless'] or 0,
                    stats['total'] or 0,
                    stats['avg_score'] or 0.0,
                    datetime.now()
                ))
                
        except Exception as e:
            logger.error(f"[SubscriptionManager] 更新源评分失败: {e}")
    
    def get_source_rating(self, source_id: int) -> Dict:
        """
        获取源评分
        
        Returns:
            {useful: int, useless: int, total: int, score: float, rate: float}
        """
        try:
            row = self.db.execute_one("""
                SELECT * FROM source_ratings WHERE source_id = ?
            """, (source_id,))
            
            if row:
                total = row['total_feedback'] or 1
                return {
                    'useful': row['total_useful'] or 0,
                    'useless': row['total_useless'] or 0,
                    'total': row['total_feedback'] or 0,
                    'score': row['avg_score'] or 0.0,
                    'rate': (row['total_useful'] or 0) / total  # 好评率
                }
            
            return {'useful': 0, 'useless': 0, 'total': 0, 'score': 0.0, 'rate': 0.0}
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取源评分失败: {e}")
            return {'useful': 0, 'useless': 0, 'total': 0, 'score': 0.0, 'rate': 0.0}
    
    def get_user_feedback_stats(self, user_id: str) -> Dict:
        """
        获取用户反馈统计
        
        Returns:
            {total: int, useful: int, useless: int, sources: list}
        """
        try:
            # 总体统计
            stats = self.db.execute_one("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN feedback_type = 'useful' THEN 1 ELSE 0 END) as useful,
                    SUM(CASE WHEN feedback_type = 'useless' THEN 1 ELSE 0 END) as useless
                FROM push_feedback 
                WHERE user_id = ?
            """, (user_id,))
            
            # 按源统计（最近反馈的源）
            source_rows = self.db.execute("""
                SELECT source_id, feedback_type, COUNT(*) as count
                FROM push_feedback 
                WHERE user_id = ?
                GROUP BY source_id, feedback_type
                ORDER BY MAX(created_at) DESC
                LIMIT 20
            """, (user_id,))
            
            # 整理源反馈
            sources = {}
            for row in source_rows:
                sid = row['source_id']
                if sid not in sources:
                    sources[sid] = {'useful': 0, 'useless': 0}
                sources[sid][row['feedback_type']] = row['count']
            
            return {
                'total': stats['total'] or 0 if stats else 0,
                'useful': stats['useful'] or 0 if stats else 0,
                'useless': stats['useless'] or 0 if stats else 0,
                'sources': sources
            }
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取用户反馈统计失败: {e}")
            return {'total': 0, 'useful': 0, 'useless': 0, 'sources': {}}
    
    def get_recommended_sources(
        self, 
        user_id: str, 
        limit: int = 10,
        exclude_subscribed: bool = True
    ) -> List[Dict]:
        """
        获取推荐订阅源（基于用户反馈和全局评分）
        
        Args:
            user_id: 用户ID
            limit: 返回数量
            exclude_subscribed: 是否排除已订阅的源
            
        Returns:
            推荐源列表 [{source_id, score, reason}]
        """
        try:
            # 获取用户已订阅的源
            subscribed_ids = set()
            if exclude_subscribed:
                rows = self.db.execute("""
                    SELECT DISTINCT source_id FROM subscriptions 
                    WHERE user_id = ? AND is_active = 1
                """, (user_id,))
                subscribed_ids = {row['source_id'] for row in rows}
            
            # 获取用户喜欢的源类型（基于反馈）
            liked_sources = self.db.execute("""
                SELECT source_id, SUM(feedback_value) as score
                FROM push_feedback 
                WHERE user_id = ? AND feedback_value > 0
                GROUP BY source_id
                ORDER BY score DESC
                LIMIT 5
            """, (user_id,))
            liked_ids = {row['source_id'] for row in liked_sources}
            
            # 获取高评分源
            recommendations = []
            
            high_rated = self.db.execute("""
                SELECT source_id, avg_score, total_feedback,
                       (total_useful * 1.0 / MAX(total_feedback, 1)) as rate
                FROM source_ratings 
                WHERE total_feedback >= 3
                ORDER BY avg_score DESC, total_feedback DESC
                LIMIT ?
            """, (limit * 2,))
            
            for row in high_rated:
                sid = row['source_id']
                if sid in subscribed_ids:
                    continue
                
                reason = "高评分源"
                if sid in liked_ids:
                    reason = "与你喜欢的源相似"
                
                recommendations.append({
                    'source_id': sid,
                    'score': row['avg_score'],
                    'rate': row['rate'],
                    'feedback_count': row['total_feedback'],
                    'reason': reason
                })
                
                if len(recommendations) >= limit:
                    break
            
            return recommendations
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取推荐源失败: {e}")
            return []
    
    def should_reduce_push_frequency(self, user_id: str, source_id: int) -> bool:
        """
        判断是否应该降低推送频率（基于用户反馈）
        
        如果用户对某源连续多次标记"无用"，建议降低推送频率
        """
        try:
            # 获取最近10次反馈
            rows = self.db.execute("""
                SELECT feedback_type FROM push_feedback 
                WHERE user_id = ? AND source_id = ?
                ORDER BY created_at DESC
                LIMIT 10
            """, (user_id, source_id))
            
            if len(rows) < 3:
                return False
            
            # 计算负面反馈比例
            negative_count = sum(1 for r in rows if r['feedback_type'] in ('useless', 'report'))
            negative_rate = negative_count / len(rows)
            
            # 超过60%负面反馈，建议降低频率
            return negative_rate >= 0.6
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 检查推送频率失败: {e}")
            return False
    
    def cleanup_old_feedback(self, days: int = 90) -> int:
        """清理旧反馈记录"""
        try:
            cutoff = datetime.now() - timedelta(days=days)
            result = self.db.execute_write("""
                DELETE FROM push_feedback WHERE created_at < ?
            """, (cutoff,))
            logger.info(f"[SubscriptionManager] 清理 {days} 天前的反馈记录")
            return result
        except Exception as e:
            logger.error(f"[SubscriptionManager] 清理反馈记录失败: {e}")
            return 0
    
    # ==================== 运营数据分析 ====================
    
    def get_subscription_trend(self, days: int = 7) -> Dict[str, Any]:
        """
        获取订阅趋势（新增/流失）
        
        Args:
            days: 统计天数
            
        Returns:
            {
                'daily': [{date, new, lost, net}],
                'total_new': int,
                'total_lost': int,
                'net_growth': int
            }
        """
        try:
            daily_stats = []
            total_new = 0
            total_lost = 0
            
            for i in range(days - 1, -1, -1):
                date = datetime.now() - timedelta(days=i)
                date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
                date_end = date_start + timedelta(days=1)
                
                # 新增订阅
                new_row = self.db.execute_one("""
                    SELECT COUNT(*) as count FROM subscriptions 
                    WHERE created_at >= ? AND created_at < ?
                """, (date_start, date_end))
                new_count = new_row['count'] if new_row else 0
                
                # 流失订阅（当天取消或禁用的）
                # 注：需要有 disabled_at 字段，这里用 is_active=0 且 last_push_at 在当天的近似
                lost_row = self.db.execute_one("""
                    SELECT COUNT(*) as count FROM subscriptions 
                    WHERE is_active = 0 AND last_push_at >= ? AND last_push_at < ?
                """, (date_start, date_end))
                lost_count = lost_row['count'] if lost_row else 0
                
                daily_stats.append({
                    'date': date_start.strftime('%m-%d'),
                    'new': new_count,
                    'lost': lost_count,
                    'net': new_count - lost_count
                })
                
                total_new += new_count
                total_lost += lost_count
            
            return {
                'daily': daily_stats,
                'total_new': total_new,
                'total_lost': total_lost,
                'net_growth': total_new - total_lost
            }
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取订阅趋势失败: {e}")
            return {'daily': [], 'total_new': 0, 'total_lost': 0, 'net_growth': 0}
    
    def get_source_health_ranking(self, limit: int = 10) -> List[Dict]:
        """
        获取源健康度排行
        
        综合指标：
        - 推送成功率（权重40%）
        - 用户满意度/好评率（权重40%）
        - 订阅人数（权重20%）
        
        Returns:
            [{source_id, name, health_score, success_rate, satisfaction, subscribers}]
        """
        try:
            # 获取所有活跃源
            sources = self.db.execute("""
                SELECT DISTINCT source_id FROM subscriptions WHERE source_id > 0
            """)
            
            rankings = []
            
            for row in sources:
                source_id = row['source_id']
                
                # 推送成功率
                push_stats = self.db.execute_one("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success
                    FROM subscription_push_logs 
                    WHERE subscription_id IN (
                        SELECT id FROM subscriptions WHERE source_id = ?
                    )
                    AND pushed_at >= datetime('now', '-7 days')
                """, (source_id,))
                
                total_push = push_stats['total'] or 0 if push_stats else 0
                success_push = push_stats['success'] or 0 if push_stats else 0
                success_rate = (success_push / total_push) if total_push > 0 else 1.0
                
                # 用户满意度
                rating = self.get_source_rating(source_id)
                satisfaction = rating.get('rate', 0.5)  # 好评率，默认0.5
                
                # 订阅人数
                sub_row = self.db.execute_one("""
                    SELECT COUNT(*) as count FROM subscriptions 
                    WHERE source_id = ? AND is_active = 1
                """, (source_id,))
                subscribers = sub_row['count'] if sub_row else 0
                
                # 综合健康度评分 (0-100)
                # 成功率40% + 满意度40% + 订阅热度20%（归一化）
                health_score = (
                    success_rate * 40 +
                    satisfaction * 40 +
                    min(subscribers / 10, 1.0) * 20  # 10人以上满分
                )
                
                rankings.append({
                    'source_id': source_id,
                    'health_score': round(health_score, 1),
                    'success_rate': round(success_rate * 100, 1),
                    'satisfaction': round(satisfaction * 100, 1),
                    'subscribers': subscribers,
                    'feedback_count': rating.get('total', 0)
                })
            
            # 按健康度排序
            rankings.sort(key=lambda x: x['health_score'], reverse=True)
            
            return rankings[:limit]
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取源健康度排行失败: {e}")
            return []
    
    def get_user_activity_stats(self) -> Dict[str, Any]:
        """
        获取用户活跃度分析
        
        Returns:
            {
                'total_users': int,
                'active_users': int,  # 7天内有推送的
                'feedback_rate': float,  # 反馈率
                'avg_subscriptions': float,  # 人均订阅数
                'activity_distribution': {high, medium, low}
            }
        """
        try:
            # 总用户数
            total_row = self.db.execute_one("""
                SELECT COUNT(DISTINCT user_id) as count FROM subscriptions
            """)
            total_users = total_row['count'] if total_row else 0
            
            # 活跃用户（7天内有推送）
            active_row = self.db.execute_one("""
                SELECT COUNT(DISTINCT user_id) as count 
                FROM subscription_push_logs 
                WHERE pushed_at >= datetime('now', '-7 days')
            """)
            active_users = active_row['count'] if active_row else 0
            
            # 反馈率（有反馈的用户 / 有推送的用户）
            feedback_users_row = self.db.execute_one("""
                SELECT COUNT(DISTINCT user_id) as count FROM push_feedback
            """)
            feedback_users = feedback_users_row['count'] if feedback_users_row else 0
            feedback_rate = (feedback_users / active_users * 100) if active_users > 0 else 0
            
            # 人均订阅数
            avg_row = self.db.execute_one("""
                SELECT AVG(sub_count) as avg FROM (
                    SELECT user_id, COUNT(*) as sub_count 
                    FROM subscriptions WHERE is_active = 1
                    GROUP BY user_id
                )
            """)
            avg_subscriptions = round(avg_row['avg'] or 0, 1) if avg_row else 0
            
            # 活跃度分布
            # 高活跃：5+订阅且有反馈
            # 中活跃：2-4订阅
            # 低活跃：1订阅
            distribution = {'high': 0, 'medium': 0, 'low': 0}
            
            user_stats = self.db.execute("""
                SELECT user_id, COUNT(*) as sub_count 
                FROM subscriptions WHERE is_active = 1
                GROUP BY user_id
            """)
            
            for user in user_stats:
                count = user['sub_count']
                if count >= 5:
                    distribution['high'] += 1
                elif count >= 2:
                    distribution['medium'] += 1
                else:
                    distribution['low'] += 1
            
            return {
                'total_users': total_users,
                'active_users': active_users,
                'feedback_rate': round(feedback_rate, 1),
                'avg_subscriptions': avg_subscriptions,
                'activity_distribution': distribution
            }
            
        except Exception as e:
            logger.error(f"[SubscriptionManager] 获取用户活跃度失败: {e}")
            return {
                'total_users': 0, 'active_users': 0, 
                'feedback_rate': 0, 'avg_subscriptions': 0,
                'activity_distribution': {'high': 0, 'medium': 0, 'low': 0}
            }


# ==================== 全局实例 ====================

_subscription_manager: Optional[SubscriptionManager] = None


def get_subscription_manager(db: DatabaseManager = None) -> Optional[SubscriptionManager]:
    """
    获取订阅管理器实例（单例模式）
    
    Args:
        db: 数据库管理器（首次调用时必须提供）
    
    Returns:
        SubscriptionManager 实例
    """
    global _subscription_manager
    
    if _subscription_manager is None and db is not None:
        _subscription_manager = SubscriptionManager(db)
        logger.info("[SubscriptionManager] 创建全局订阅管理器实例")
    
    return _subscription_manager
