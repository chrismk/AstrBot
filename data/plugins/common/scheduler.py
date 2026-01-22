"""
插件级定时任务调度器

设计理念：
1. 遵循现有通用模块的设计模式（单例模式、全局获取函数）
2. 插件通过简单的装饰器或注册函数添加定时任务
3. 支持 cron 表达式和间隔执行两种模式
4. 任务执行日志和错误处理
5. 支持任务的启用/禁用/手动触发
6. 与现有的 DatabaseManager 集成，持久化任务状态

使用示例：
    from common import get_scheduler, scheduled_task
    
    # 方式1：使用装饰器（推荐）
    @scheduled_task(
        task_id="checkin_reminder",
        cron="0 19 * * *",  # 每天19:00执行
        description="签到提醒"
    )
    async def checkin_reminder_task(context):
        # 执行签到提醒逻辑
        pass
    
    # 方式2：手动注册
    scheduler = get_scheduler()
    scheduler.register_task(
        task_id="ranking_update",
        plugin_name="search_stats",
        cron="0 * * * *",  # 每小时执行
        handler=update_ranking_handler,
        description="更新热搜榜单"
    )
    
    # 手动触发任务
    await scheduler.trigger_task("ranking_update")
    
    # 启用/禁用任务
    scheduler.enable_task("ranking_update")
    scheduler.disable_task("ranking_update")
    
    # 获取任务状态
    status = scheduler.get_task_status("ranking_update")

依赖：
    - APScheduler (需要安装: pip install apscheduler)
    - 现有的 DatabaseManager（用于持久化任务状态和日志）
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable, List, Union
from functools import wraps
from enum import Enum
import traceback

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.jobstores.memory import MemoryJobStore
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    AsyncIOScheduler = None
    CronTrigger = None
    IntervalTrigger = None

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from .database_manager import DatabaseManager


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"      # 等待执行
    RUNNING = "running"      # 正在执行
    SUCCESS = "success"      # 执行成功
    FAILED = "failed"        # 执行失败
    DISABLED = "disabled"    # 已禁用


class ScheduledTask:
    """定时任务数据类"""
    
    def __init__(
        self,
        task_id: str,
        plugin_name: str,
        handler: Callable,
        cron: str = None,
        interval_seconds: int = None,
        description: str = "",
        enabled: bool = True,
        max_retries: int = 3,
        retry_delay: int = 60,
        context: Any = None
    ):
        """
        初始化定时任务
        
        Args:
            task_id: 任务唯一标识
            plugin_name: 所属插件名称
            handler: 任务处理函数（async function）
            cron: cron 表达式（与 interval_seconds 二选一）
            interval_seconds: 间隔秒数（与 cron 二选一）
            description: 任务描述
            enabled: 是否启用
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）
            context: 上下文对象（传递给 handler）
        """
        self.task_id = task_id
        self.plugin_name = plugin_name
        self.handler = handler
        self.cron = cron
        self.interval_seconds = interval_seconds
        self.description = description
        self.enabled = enabled
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.context = context
        
        # 运行时状态
        self.status = TaskStatus.PENDING
        self.last_run: Optional[datetime] = None
        self.next_run: Optional[datetime] = None
        self.run_count: int = 0
        self.success_count: int = 0
        self.fail_count: int = 0
        self.last_error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'task_id': self.task_id,
            'plugin_name': self.plugin_name,
            'cron': self.cron,
            'interval_seconds': self.interval_seconds,
            'description': self.description,
            'enabled': self.enabled,
            'status': self.status.value,
            'last_run': self.last_run.isoformat() if self.last_run else None,
            'next_run': self.next_run.isoformat() if self.next_run else None,
            'run_count': self.run_count,
            'success_count': self.success_count,
            'fail_count': self.fail_count,
            'last_error': self.last_error
        }


class PluginScheduler:
    """
    插件级定时任务调度器
    
    遵循现有通用模块的设计模式：
    - 单例模式
    - 全局获取函数
    - 与 DatabaseManager 集成
    """
    
    def __init__(self, db: DatabaseManager = None):
        """
        初始化调度器
        
        Args:
            db: 数据库管理器（可选，用于持久化任务日志）
        """
        self.db = db
        self.tasks: Dict[str, ScheduledTask] = {}
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._started = False
        self._context = None  # 全局上下文（用于消息推送等）
        
        if not APSCHEDULER_AVAILABLE:
            logger.warning("[Scheduler] APScheduler 未安装，定时任务功能不可用")
            logger.warning("[Scheduler] 请运行: pip install apscheduler")
        
        # 初始化数据库表
        if self.db:
            self._init_db_tables()
    
    def _init_db_tables(self):
        """初始化数据库表"""
        try:
            # 任务配置表
            self.db.execute_write("""
                CREATE TABLE IF NOT EXISTS scheduled_tasks (
                    task_id TEXT PRIMARY KEY,
                    plugin_name TEXT NOT NULL,
                    cron TEXT,
                    interval_seconds INTEGER,
                    description TEXT,
                    enabled INTEGER DEFAULT 1,
                    last_run DATETIME,
                    next_run DATETIME,
                    run_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    fail_count INTEGER DEFAULT 0,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
            """)
            
            # 任务执行日志表
            self.db.execute_write("""
                CREATE TABLE IF NOT EXISTS task_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at DATETIME NOT NULL,
                    finished_at DATETIME,
                    duration_ms INTEGER,
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    FOREIGN KEY (task_id) REFERENCES scheduled_tasks(task_id)
                )
            """)
            
            # 创建索引
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_task_logs_task_id 
                ON task_logs(task_id)
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_task_logs_started 
                ON task_logs(started_at)
            """)
            
            logger.info("[Scheduler] 数据库表初始化完成")
            
        except Exception as e:
            logger.error(f"[Scheduler] 数据库表初始化失败: {e}")
    
    def set_context(self, context: Any):
        """
        设置全局上下文
        
        Args:
            context: AstrBot 的 Context 对象，用于消息推送等功能
        """
        self._context = context
        logger.debug("[Scheduler] 全局上下文已设置")
    
    def register_task(
        self,
        task_id: str,
        plugin_name: str,
        handler: Callable,
        cron: str = None,
        interval_seconds: int = None,
        description: str = "",
        enabled: bool = True,
        max_retries: int = 3,
        retry_delay: int = 60,
        context: Any = None
    ) -> bool:
        """
        注册定时任务
        
        Args:
            task_id: 任务唯一标识（建议格式：plugin_name:task_name）
            plugin_name: 所属插件名称
            handler: 任务处理函数（async function）
            cron: cron 表达式（与 interval_seconds 二选一）
            interval_seconds: 间隔秒数（与 cron 二选一）
            description: 任务描述
            enabled: 是否启用
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）
            context: 上下文对象（传递给 handler）
        
        Returns:
            是否注册成功
        """
        if not APSCHEDULER_AVAILABLE:
            logger.error(f"[Scheduler] 无法注册任务 {task_id}: APScheduler 未安装")
            return False
        
        if not cron and not interval_seconds:
            logger.error(f"[Scheduler] 任务 {task_id} 必须指定 cron 或 interval_seconds")
            return False
        
        # 创建任务对象
        task = ScheduledTask(
            task_id=task_id,
            plugin_name=plugin_name,
            handler=handler,
            cron=cron,
            interval_seconds=interval_seconds,
            description=description,
            enabled=enabled,
            max_retries=max_retries,
            retry_delay=retry_delay,
            context=context or self._context
        )
        
        self.tasks[task_id] = task
        
        # 持久化到数据库
        if self.db:
            self._save_task_to_db(task)
        
        # 如果调度器已启动，立即添加任务
        if self._started and enabled:
            self._add_job(task)
        
        logger.info(f"[Scheduler] 注册任务: {task_id} ({description})")
        return True
    
    def _save_task_to_db(self, task: ScheduledTask):
        """保存任务到数据库"""
        try:
            now = datetime.now()
            self.db.execute_write("""
                INSERT OR REPLACE INTO scheduled_tasks 
                (task_id, plugin_name, cron, interval_seconds, description, enabled, 
                 last_run, next_run, run_count, success_count, fail_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                        COALESCE((SELECT created_at FROM scheduled_tasks WHERE task_id = ?), ?), ?)
            """, (
                task.task_id, task.plugin_name, task.cron, task.interval_seconds,
                task.description, 1 if task.enabled else 0,
                task.last_run, task.next_run, task.run_count, task.success_count, task.fail_count,
                task.task_id, now, now
            ))
        except Exception as e:
            logger.error(f"[Scheduler] 保存任务到数据库失败: {e}")
    
    def _add_job(self, task: ScheduledTask):
        """添加任务到调度器"""
        if not self._scheduler:
            return
        
        try:
            # 移除已存在的任务
            try:
                existing_job = self._scheduler.get_job(task.task_id)
                if existing_job:
                    self._scheduler.remove_job(task.task_id)
            except Exception:
                pass
            
            # 创建触发器
            if task.cron:
                trigger = CronTrigger.from_crontab(task.cron)
            else:
                trigger = IntervalTrigger(seconds=task.interval_seconds)
            
            # 添加任务
            self._scheduler.add_job(
                self._execute_task,
                trigger=trigger,
                id=task.task_id,
                args=[task.task_id],
                name=task.description or task.task_id,
                replace_existing=True
            )
            
            # 尝试获取下次执行时间（兼容不同版本 APScheduler）
            try:
                job = self._scheduler.get_job(task.task_id)
                if job:
                    # APScheduler 3.x
                    if hasattr(job, 'next_run_time'):
                        task.next_run = job.next_run_time
                    # APScheduler 4.x
                    elif hasattr(job, 'next_fire_time'):
                        task.next_run = job.next_fire_time
            except Exception:
                pass
            
            logger.debug(f"[Scheduler] 添加任务到调度器: {task.task_id}, 下次执行: {task.next_run}")
            
        except Exception as e:
            logger.error(f"[Scheduler] 添加任务到调度器失败: {e}")
    
    async def _execute_task(self, task_id: str):
        """执行任务（内部方法）"""
        task = self.tasks.get(task_id)
        if not task:
            logger.warning(f"[Scheduler] 任务不存在: {task_id}")
            return
        
        if not task.enabled:
            logger.debug(f"[Scheduler] 任务已禁用，跳过: {task_id}")
            return
        
        started_at = datetime.now()
        task.status = TaskStatus.RUNNING
        task.run_count += 1
        retry_count = 0
        error_message = None
        
        logger.info(f"[Scheduler] 开始执行任务: {task_id}")
        
        while retry_count <= task.max_retries:
            try:
                # 执行任务处理函数
                if asyncio.iscoroutinefunction(task.handler):
                    await task.handler(task.context)
                else:
                    task.handler(task.context)
                
                # 执行成功
                task.status = TaskStatus.SUCCESS
                task.success_count += 1
                task.last_run = datetime.now()
                task.last_error = None
                
                duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)
                logger.info(f"[Scheduler] 任务执行成功: {task_id}, 耗时: {duration_ms}ms")
                
                # 记录日志
                if self.db:
                    self._log_execution(task_id, "success", started_at, duration_ms, retry_count)
                
                break
                
            except Exception as e:
                retry_count += 1
                error_message = f"{type(e).__name__}: {str(e)}"
                
                logger.error(f"[Scheduler] 任务执行失败: {task_id}, 错误: {error_message}")
                logger.debug(traceback.format_exc())
                
                if retry_count <= task.max_retries:
                    logger.info(f"[Scheduler] 任务 {task_id} 将在 {task.retry_delay}秒后重试 ({retry_count}/{task.max_retries})")
                    await asyncio.sleep(task.retry_delay)
                else:
                    # 重试次数用尽
                    task.status = TaskStatus.FAILED
                    task.fail_count += 1
                    task.last_run = datetime.now()
                    task.last_error = error_message
                    
                    duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)
                    
                    # 记录日志
                    if self.db:
                        self._log_execution(task_id, "failed", started_at, duration_ms, retry_count, error_message)
        
        # 更新数据库
        if self.db:
            self._save_task_to_db(task)
        
        # 更新下次执行时间（兼容不同版本 APScheduler）
        if self._scheduler:
            try:
                job = self._scheduler.get_job(task_id)
                if job:
                    if hasattr(job, 'next_run_time'):
                        task.next_run = job.next_run_time
                    elif hasattr(job, 'next_fire_time'):
                        task.next_run = job.next_fire_time
            except Exception:
                pass
    
    def _log_execution(
        self,
        task_id: str,
        status: str,
        started_at: datetime,
        duration_ms: int,
        retry_count: int,
        error_message: str = None
    ):
        """记录任务执行日志"""
        try:
            self.db.execute_write("""
                INSERT INTO task_logs 
                (task_id, status, started_at, finished_at, duration_ms, error_message, retry_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (task_id, status, started_at, datetime.now(), duration_ms, error_message, retry_count))
        except Exception as e:
            logger.error(f"[Scheduler] 记录执行日志失败: {e}")
    
    async def start(self):
        """启动调度器"""
        if not APSCHEDULER_AVAILABLE:
            logger.error("[Scheduler] 无法启动调度器: APScheduler 未安装")
            return
        
        if self._started:
            logger.warning("[Scheduler] 调度器已在运行")
            return
        
        try:
            # 创建调度器
            self._scheduler = AsyncIOScheduler(
                jobstores={'default': MemoryJobStore()},
                job_defaults={
                    'coalesce': True,  # 合并错过的执行
                    'max_instances': 1,  # 同一任务最多同时运行1个实例
                    'misfire_grace_time': 60  # 错过执行的容忍时间（秒）
                }
            )
            
            # 添加所有已启用的任务
            for task in self.tasks.values():
                if task.enabled:
                    self._add_job(task)
            
            # 启动调度器
            self._scheduler.start()
            self._started = True
            
            logger.info(f"[Scheduler] 调度器已启动，共 {len(self.tasks)} 个任务")
            
        except Exception as e:
            logger.error(f"[Scheduler] 启动调度器失败: {e}")
    
    def stop(self):
        """停止调度器"""
        if self._scheduler and self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False
            logger.info("[Scheduler] 调度器已停止")
    
    def enable_task(self, task_id: str) -> bool:
        """启用任务"""
        task = self.tasks.get(task_id)
        if not task:
            logger.warning(f"[Scheduler] 任务不存在: {task_id}")
            return False
        
        task.enabled = True
        task.status = TaskStatus.PENDING
        
        if self._started:
            self._add_job(task)
        
        if self.db:
            self._save_task_to_db(task)
        
        logger.info(f"[Scheduler] 任务已启用: {task_id}")
        return True
    
    def disable_task(self, task_id: str) -> bool:
        """禁用任务"""
        task = self.tasks.get(task_id)
        if not task:
            logger.warning(f"[Scheduler] 任务不存在: {task_id}")
            return False
        
        task.enabled = False
        task.status = TaskStatus.DISABLED
        
        if self._scheduler and self._scheduler.get_job(task_id):
            self._scheduler.remove_job(task_id)
        
        if self.db:
            self._save_task_to_db(task)
        
        logger.info(f"[Scheduler] 任务已禁用: {task_id}")
        return True
    
    async def trigger_task(self, task_id: str) -> bool:
        """手动触发任务"""
        task = self.tasks.get(task_id)
        if not task:
            logger.warning(f"[Scheduler] 任务不存在: {task_id}")
            return False
        
        logger.info(f"[Scheduler] 手动触发任务: {task_id}")
        await self._execute_task(task_id)
        return True
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务状态"""
        task = self.tasks.get(task_id)
        if not task:
            return None
        return task.to_dict()
    
    def get_all_tasks(self, plugin_name: str = None) -> List[Dict[str, Any]]:
        """
        获取所有任务
        
        Args:
            plugin_name: 过滤指定插件的任务（可选）
        
        Returns:
            任务列表
        """
        tasks = self.tasks.values()
        if plugin_name:
            tasks = [t for t in tasks if t.plugin_name == plugin_name]
        return [t.to_dict() for t in tasks]
    
    def get_task_logs(
        self,
        task_id: str = None,
        limit: int = 50,
        status: str = None
    ) -> List[Dict[str, Any]]:
        """
        获取任务执行日志
        
        Args:
            task_id: 任务ID（可选，不指定则返回所有）
            limit: 返回数量限制
            status: 状态过滤（success/failed）
        
        Returns:
            日志列表
        """
        if not self.db:
            return []
        
        try:
            conditions = []
            params = []
            
            if task_id:
                conditions.append("task_id = ?")
                params.append(task_id)
            
            if status:
                conditions.append("status = ?")
                params.append(status)
            
            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            
            rows = self.db.execute(f"""
                SELECT * FROM task_logs
                {where_clause}
                ORDER BY started_at DESC
                LIMIT ?
            """, (*params, limit))
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"[Scheduler] 获取任务日志失败: {e}")
            return []
    
    def cleanup_old_logs(self, days: int = 30) -> int:
        """
        清理旧日志
        
        Args:
            days: 保留天数
        
        Returns:
            清理的记录数
        """
        if not self.db:
            return 0
        
        try:
            cutoff = datetime.now() - timedelta(days=days)
            self.db.execute_write("""
                DELETE FROM task_logs WHERE started_at < ?
            """, (cutoff,))
            logger.info(f"[Scheduler] 清理 {days} 天前的任务日志")
            return 0
        except Exception as e:
            logger.error(f"[Scheduler] 清理日志失败: {e}")
            return 0


# ==================== 全局实例和便捷函数 ====================

_global_scheduler: Optional[PluginScheduler] = None


def get_scheduler(db: DatabaseManager = None) -> PluginScheduler:
    """
    获取全局调度器实例（单例模式）
    
    Args:
        db: 数据库管理器（首次调用时可选）
    
    Returns:
        PluginScheduler 实例
    """
    global _global_scheduler
    
    if _global_scheduler is None:
        _global_scheduler = PluginScheduler(db)
        logger.info("[Scheduler] 创建全局调度器实例")
    elif db and _global_scheduler.db is None:
        _global_scheduler.db = db
        _global_scheduler._init_db_tables()
    
    return _global_scheduler


def scheduled_task(
    task_id: str,
    plugin_name: str = "unknown",
    cron: str = None,
    interval_seconds: int = None,
    description: str = "",
    enabled: bool = True,
    max_retries: int = 3,
    retry_delay: int = 60
):
    """
    定时任务装饰器
    
    用于将函数注册为定时任务，简化任务注册流程。
    
    Args:
        task_id: 任务唯一标识
        plugin_name: 所属插件名称
        cron: cron 表达式
        interval_seconds: 间隔秒数
        description: 任务描述
        enabled: 是否启用
        max_retries: 最大重试次数
        retry_delay: 重试间隔（秒）
    
    Example:
        @scheduled_task(
            task_id="checkin:reminder",
            plugin_name="checkin",
            cron="0 19 * * *",
            description="每日签到提醒"
        )
        async def send_checkin_reminder(context):
            # 发送签到提醒
            pass
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        
        # 注册任务（延迟注册，等待调度器初始化）
        wrapper._scheduled_task_config = {
            'task_id': task_id,
            'plugin_name': plugin_name,
            'handler': func,
            'cron': cron,
            'interval_seconds': interval_seconds,
            'description': description,
            'enabled': enabled,
            'max_retries': max_retries,
            'retry_delay': retry_delay
        }
        
        return wrapper
    
    return decorator


def register_decorated_tasks(module, scheduler: PluginScheduler = None):
    """
    注册模块中所有使用 @scheduled_task 装饰的函数
    
    Args:
        module: 包含装饰函数的模块或类实例
        scheduler: 调度器实例（可选，默认使用全局实例）
    
    Example:
        # 在插件 __init__ 中调用
        from common import register_decorated_tasks, get_scheduler
        
        scheduler = get_scheduler(self.db)
        register_decorated_tasks(self, scheduler)
    """
    if scheduler is None:
        scheduler = get_scheduler()
    
    # 遍历模块/类的所有属性
    for name in dir(module):
        obj = getattr(module, name, None)
        if obj and hasattr(obj, '_scheduled_task_config'):
            config = obj._scheduled_task_config
            scheduler.register_task(**config)
            logger.debug(f"[Scheduler] 自动注册装饰器任务: {config['task_id']}")
