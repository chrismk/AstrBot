"""
异常错误追踪器

功能：
1. 记录系统异常和错误
2. 统计错误频率和分布
3. 生成错误报告
4. 支持错误告警

使用示例：
    from common.error_tracker import get_error_tracker, track_error
    
    # 方式1：使用装饰器自动追踪
    @track_error(module="music")
    async def search_music(keyword):
        # 如果发生异常，会自动记录
        pass
    
    # 方式2：手动记录
    tracker = get_error_tracker()
    try:
        # 业务逻辑
    except Exception as e:
        tracker.record_error(
            module="music",
            error_type=type(e).__name__,
            error_message=str(e),
            context={"keyword": keyword}
        )
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Callable
from functools import wraps
import traceback
import json

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from .database_manager import DatabaseManager


class ErrorTracker:
    """异常错误追踪器"""
    
    def __init__(self, db: DatabaseManager):
        """
        初始化错误追踪器
        
        Args:
            db: 数据库管理器实例
        """
        self.db = db
        self._init_tables()
    
    def _init_tables(self):
        """初始化数据库表"""
        try:
            self.db.execute_write("""
                CREATE TABLE IF NOT EXISTS error_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    module TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    error_message TEXT,
                    stack_trace TEXT,
                    context TEXT,
                    user_id TEXT,
                    resolved INTEGER DEFAULT 0,
                    created_at DATETIME NOT NULL
                )
            """)
            
            # 创建索引
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_error_logs_module 
                ON error_logs(module, created_at)
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_error_logs_type 
                ON error_logs(error_type, created_at)
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_error_logs_date 
                ON error_logs(created_at)
            """)
            
        except Exception as e:
            logger.error(f"[ErrorTracker] 初始化数据库表失败: {e}")
    
    def record_error(
        self,
        module: str,
        error_type: str,
        error_message: str,
        stack_trace: str = None,
        context: Dict[str, Any] = None,
        user_id: str = None
    ) -> int:
        """
        记录错误
        
        Args:
            module: 模块名称（如 music, book, subscription）
            error_type: 错误类型（如 ValueError, ConnectionError）
            error_message: 错误信息
            stack_trace: 堆栈跟踪
            context: 上下文信息
            user_id: 相关用户ID
            
        Returns:
            错误记录ID
        """
        try:
            context_json = json.dumps(context, ensure_ascii=False) if context else None
            
            self.db.execute_write("""
                INSERT INTO error_logs 
                (module, error_type, error_message, stack_trace, context, user_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (module, error_type, error_message, stack_trace, context_json, user_id, datetime.now()))
            
            # 获取插入的ID
            result = self.db.execute_one("SELECT last_insert_rowid() as id")
            error_id = result['id'] if result else 0
            
            logger.debug(f"[ErrorTracker] 记录错误: module={module}, type={error_type}")
            return error_id
            
        except Exception as e:
            logger.error(f"[ErrorTracker] 记录错误失败: {e}")
            return 0
    
    def record_exception(
        self,
        module: str,
        exception: Exception,
        context: Dict[str, Any] = None,
        user_id: str = None
    ) -> int:
        """
        记录异常（自动提取类型、消息和堆栈）
        
        Args:
            module: 模块名称
            exception: 异常对象
            context: 上下文信息
            user_id: 相关用户ID
            
        Returns:
            错误记录ID
        """
        return self.record_error(
            module=module,
            error_type=type(exception).__name__,
            error_message=str(exception),
            stack_trace=traceback.format_exc(),
            context=context,
            user_id=user_id
        )
    
    def get_error_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        获取错误统计
        
        Args:
            days: 统计天数
            
        Returns:
            统计数据
        """
        try:
            since = datetime.now() - timedelta(days=days)
            
            # 总错误数
            total_row = self.db.execute_one("""
                SELECT COUNT(*) as count FROM error_logs
                WHERE created_at >= ?
            """, (since,))
            total_errors = total_row['count'] if total_row else 0
            
            # 按模块统计
            by_module = self.db.execute("""
                SELECT module, COUNT(*) as count
                FROM error_logs
                WHERE created_at >= ?
                GROUP BY module
                ORDER BY count DESC
            """, (since,))
            
            # 按错误类型统计
            by_type = self.db.execute("""
                SELECT error_type, COUNT(*) as count
                FROM error_logs
                WHERE created_at >= ?
                GROUP BY error_type
                ORDER BY count DESC
                LIMIT 10
            """, (since,))
            
            # 每日趋势
            daily_trend = self.db.execute("""
                SELECT date(created_at) as date, COUNT(*) as count
                FROM error_logs
                WHERE created_at >= ?
                GROUP BY date(created_at)
                ORDER BY date
            """, (since,))
            
            # 最近错误
            recent_errors = self.db.execute("""
                SELECT module, error_type, error_message, created_at
                FROM error_logs
                WHERE created_at >= ?
                ORDER BY created_at DESC
                LIMIT 10
            """, (since,))
            
            # 计算错误率变化
            yesterday = datetime.now() - timedelta(days=1)
            day_before = datetime.now() - timedelta(days=2)
            
            yesterday_row = self.db.execute_one("""
                SELECT COUNT(*) as count FROM error_logs
                WHERE date(created_at) = date(?)
            """, (yesterday,))
            yesterday_count = yesterday_row['count'] if yesterday_row else 0
            
            day_before_row = self.db.execute_one("""
                SELECT COUNT(*) as count FROM error_logs
                WHERE date(created_at) = date(?)
            """, (day_before,))
            day_before_count = day_before_row['count'] if day_before_row else 0
            
            change_percent = 0
            if day_before_count > 0:
                change_percent = round((yesterday_count - day_before_count) / day_before_count * 100, 1)
            
            return {
                'period': f'最近{days}天',
                'total_errors': total_errors,
                'yesterday_errors': yesterday_count,
                'change_percent': change_percent,
                'by_module': [dict(row) for row in by_module],
                'by_type': [dict(row) for row in by_type],
                'daily_trend': [dict(row) for row in daily_trend],
                'recent_errors': [dict(row) for row in recent_errors]
            }
            
        except Exception as e:
            logger.error(f"[ErrorTracker] 获取错误统计失败: {e}")
            return {}
    
    def get_module_errors(
        self,
        module: str,
        days: int = 7,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取指定模块的错误列表
        
        Args:
            module: 模块名称
            days: 统计天数
            limit: 返回数量限制
            
        Returns:
            错误列表
        """
        try:
            since = datetime.now() - timedelta(days=days)
            
            rows = self.db.execute("""
                SELECT * FROM error_logs
                WHERE module = ? AND created_at >= ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (module, since, limit))
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"[ErrorTracker] 获取模块错误失败: {e}")
            return []
    
    def get_error_detail(self, error_id: int) -> Optional[Dict[str, Any]]:
        """
        获取错误详情
        
        Args:
            error_id: 错误ID
            
        Returns:
            错误详情
        """
        try:
            row = self.db.execute_one("""
                SELECT * FROM error_logs WHERE id = ?
            """, (error_id,))
            
            if row:
                result = dict(row)
                if result.get('context'):
                    result['context'] = json.loads(result['context'])
                return result
            return None
            
        except Exception as e:
            logger.error(f"[ErrorTracker] 获取错误详情失败: {e}")
            return None
    
    def mark_resolved(self, error_id: int) -> bool:
        """
        标记错误已解决
        
        Args:
            error_id: 错误ID
            
        Returns:
            是否成功
        """
        try:
            self.db.execute_write("""
                UPDATE error_logs SET resolved = 1 WHERE id = ?
            """, (error_id,))
            return True
        except Exception as e:
            logger.error(f"[ErrorTracker] 标记错误已解决失败: {e}")
            return False
    
    def get_unresolved_count(self) -> int:
        """获取未解决的错误数量"""
        try:
            row = self.db.execute_one("""
                SELECT COUNT(*) as count FROM error_logs WHERE resolved = 0
            """)
            return row['count'] if row else 0
        except Exception:
            return 0
    
    def cleanup_old_errors(self, days: int = 30) -> int:
        """
        清理旧错误记录
        
        Args:
            days: 保留天数
            
        Returns:
            清理的记录数
        """
        try:
            cutoff = datetime.now() - timedelta(days=days)
            self.db.execute_write("""
                DELETE FROM error_logs WHERE created_at < ? AND resolved = 1
            """, (cutoff,))
            logger.info(f"[ErrorTracker] 清理 {days} 天前的已解决错误")
            return 0
        except Exception as e:
            logger.error(f"[ErrorTracker] 清理旧错误失败: {e}")
            return 0
    
    def format_error_report(self, days: int = 7) -> str:
        """
        格式化错误报告
        
        Args:
            days: 统计天数
            
        Returns:
            格式化的报告文本
        """
        stats = self.get_error_stats(days)
        
        if not stats:
            return "❌ 无法获取错误统计"
        
        lines = [
            f"🔴 系统错误报告 ({stats['period']})",
            "━" * 22,
            f"📊 总错误数: {stats['total_errors']}",
            f"📅 昨日错误: {stats['yesterday_errors']} ({'+' if stats['change_percent'] >= 0 else ''}{stats['change_percent']}%)",
            "",
        ]
        
        # 按模块统计
        if stats.get('by_module'):
            lines.append("📦 模块分布:")
            for item in stats['by_module'][:5]:
                lines.append(f"  • {item['module']}: {item['count']}次")
            lines.append("")
        
        # 按类型统计
        if stats.get('by_type'):
            lines.append("🏷️ 错误类型 TOP5:")
            for i, item in enumerate(stats['by_type'][:5], 1):
                lines.append(f"  {i}. {item['error_type']}: {item['count']}次")
            lines.append("")
        
        # 最近错误
        if stats.get('recent_errors'):
            lines.append("🕐 最近错误:")
            for err in stats['recent_errors'][:3]:
                time_str = err['created_at'][:16] if err['created_at'] else ''
                msg = err['error_message'][:30] + '...' if len(err.get('error_message', '') or '') > 30 else err.get('error_message', '')
                lines.append(f"  [{time_str}] {err['module']}: {msg}")
        
        lines.append("━" * 22)
        return "\n".join(lines)


# ==================== 全局实例和便捷函数 ====================

_global_tracker: Optional[ErrorTracker] = None


def get_error_tracker(db: DatabaseManager = None) -> Optional[ErrorTracker]:
    """
    获取全局错误追踪器实例（单例模式）
    
    Args:
        db: 数据库管理器（首次调用时必须提供）
    
    Returns:
        ErrorTracker 实例
    """
    global _global_tracker
    
    if _global_tracker is None and db:
        _global_tracker = ErrorTracker(db)
        logger.info("[ErrorTracker] 创建全局错误追踪器实例")
    
    return _global_tracker


def track_error(module: str, reraise: bool = True):
    """
    错误追踪装饰器
    
    自动捕获并记录函数中的异常。
    
    Args:
        module: 模块名称
        reraise: 是否重新抛出异常（默认 True）
    
    Example:
        @track_error(module="music")
        async def search_music(keyword):
            # 如果发生异常，会自动记录
            pass
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                tracker = get_error_tracker()
                if tracker:
                    # 尝试从参数中提取 user_id
                    user_id = kwargs.get('user_id')
                    if not user_id and args:
                        # 尝试从第一个参数（可能是 event）中获取
                        first_arg = args[0]
                        if hasattr(first_arg, 'get_sender_id'):
                            user_id = first_arg.get_sender_id()
                    
                    tracker.record_exception(
                        module=module,
                        exception=e,
                        context={'function': func.__name__, 'args_count': len(args)},
                        user_id=user_id
                    )
                
                if reraise:
                    raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                tracker = get_error_tracker()
                if tracker:
                    tracker.record_exception(
                        module=module,
                        exception=e,
                        context={'function': func.__name__}
                    )
                
                if reraise:
                    raise
        
        # 根据函数类型返回对应的包装器
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator
