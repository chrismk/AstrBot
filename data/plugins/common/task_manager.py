"""
任务管理器

负责：
1. 任务定义管理（注册、查询）
2. 用户任务进度管理
3. 奖励发放
4. 周期重置

使用示例：
    from common.task_manager import get_task_manager
    
    task_manager = get_task_manager(db, points_manager)
    
    # 获取用户任务
    tasks = task_manager.get_user_tasks(user_id, TaskType.DAILY)
    
    # 更新进度
    completed = task_manager.update_progress(user_id, TaskTrigger.SEARCH)
    
    # 领取奖励
    success, msg = task_manager.claim_reward(user_id, task_id)
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from .database_manager import DatabaseManager
from .points_manager import PointsManager


class TaskType(Enum):
    """任务类型"""
    DAILY = "daily"       # 每日任务
    WEEKLY = "weekly"     # 每周任务
    MONTHLY = "monthly"   # 每月任务
    ONETIME = "onetime"   # 一次性任务（永不重置）


class TaskTrigger(Enum):
    """任务触发类型"""
    CHECKIN = "checkin"           # 签到
    SEARCH = "search"             # 搜索
    DOWNLOAD = "download"         # 下载
    SUBSCRIBE = "subscribe"       # 订阅
    FEEDBACK = "feedback"         # 反馈
    CHAT = "chat"                 # 群聊发言
    VIEW_RANKING = "view_ranking" # 查看榜单
    INVITE = "invite"             # 邀请好友
    BIND_INVITE = "bind_invite"   # 绑定邀请码
    FIRST_USE = "first_use"       # 首次使用某功能
    CUSTOM = "custom"             # 自定义（需手动触发）


@dataclass
class TaskDefinition:
    """任务定义"""
    task_id: str                  # 任务ID
    name: str                     # 任务名称
    description: str              # 任务描述
    task_type: TaskType           # 任务类型
    trigger: TaskTrigger          # 触发类型
    target: int                   # 目标值
    reward_points: int            # 奖励积分
    icon: str = "📋"              # 图标
    enabled: bool = True          # 是否启用
    plugin_name: str = None       # 所属插件
    sort_order: int = 0           # 排序
    extra_config: Dict = None     # 额外配置
    
    # 特殊任务标记
    is_bonus: bool = False        # 是否为额外奖励任务（如"全部完成"）
    depends_on: List[str] = None  # 依赖的任务ID列表


@dataclass
class UserTaskProgress:
    """用户任务进度"""
    user_id: str
    task_id: str
    progress: int = 0             # 当前进度
    target: int = 0               # 目标值
    completed: bool = False       # 是否完成
    reward_claimed: bool = False  # 是否已领取奖励
    completed_at: datetime = None # 完成时间
    period_start: datetime = None # 周期开始时间
    period_end: datetime = None   # 周期结束时间
    
    @property
    def progress_percent(self) -> float:
        """进度百分比"""
        return min(self.progress / self.target * 100, 100) if self.target > 0 else 0
    
    @property
    def is_claimable(self) -> bool:
        """是否可领取奖励"""
        return self.completed and not self.reward_claimed


# 默认任务配置
DEFAULT_TASKS = [
    # ========== 每日任务 ==========
    TaskDefinition(
        task_id="daily_checkin",
        name="每日签到",
        description="完成每日签到",
        task_type=TaskType.DAILY,
        trigger=TaskTrigger.CHECKIN,
        target=1,
        reward_points=10,
        icon="✅",
        sort_order=1
    ),
    TaskDefinition(
        task_id="daily_search_3",
        name="搜索3次",
        description="使用搜索功能3次",
        task_type=TaskType.DAILY,
        trigger=TaskTrigger.SEARCH,
        target=3,
        reward_points=20,
        icon="🔍",
        sort_order=2
    ),
    TaskDefinition(
        task_id="daily_view_ranking",
        name="查看热搜榜",
        description="查看热搜榜单1次",
        task_type=TaskType.DAILY,
        trigger=TaskTrigger.VIEW_RANKING,
        target=1,
        reward_points=15,
        icon="📊",
        sort_order=3
    ),
    TaskDefinition(
        task_id="daily_subscribe",
        name="订阅内容",
        description="订阅1个内容源",
        task_type=TaskType.DAILY,
        trigger=TaskTrigger.SUBSCRIBE,
        target=1,
        reward_points=10,
        icon="📰",
        sort_order=4
    ),
    TaskDefinition(
        task_id="daily_all_complete",
        name="全部完成",
        description="完成所有每日任务",
        task_type=TaskType.DAILY,
        trigger=TaskTrigger.CUSTOM,
        target=4,  # 需要完成4个基础任务
        reward_points=50,
        icon="🎁",
        sort_order=99,
        is_bonus=True,
        depends_on=["daily_checkin", "daily_search_3", "daily_view_ranking", "daily_subscribe"]
    ),
    
    # ========== 每周任务 ==========
    TaskDefinition(
        task_id="weekly_streak_7",
        name="连续签到7天",
        description="本周连续签到7天",
        task_type=TaskType.WEEKLY,
        trigger=TaskTrigger.CHECKIN,
        target=7,
        reward_points=100,
        icon="🔥",
        sort_order=1
    ),
    TaskDefinition(
        task_id="weekly_search_20",
        name="累计搜索20次",
        description="本周累计搜索20次",
        task_type=TaskType.WEEKLY,
        trigger=TaskTrigger.SEARCH,
        target=20,
        reward_points=50,
        icon="🔍",
        sort_order=2
    ),
    TaskDefinition(
        task_id="weekly_subscribe_3",
        name="订阅3个内容",
        description="本周订阅3个内容源",
        task_type=TaskType.WEEKLY,
        trigger=TaskTrigger.SUBSCRIBE,
        target=3,
        reward_points=30,
        icon="📰",
        sort_order=3
    ),
    TaskDefinition(
        task_id="weekly_feedback_5",
        name="反馈5次",
        description="本周对推送内容反馈5次",
        task_type=TaskType.WEEKLY,
        trigger=TaskTrigger.FEEDBACK,
        target=5,
        reward_points=40,
        icon="💬",
        sort_order=4
    ),
    
    # ========== 每月任务 ==========
    TaskDefinition(
        task_id="monthly_full_checkin",
        name="本月全勤",
        description="本月每天都签到",
        task_type=TaskType.MONTHLY,
        trigger=TaskTrigger.CHECKIN,
        target=30,  # 动态调整为当月天数
        reward_points=500,
        icon="🏆",
        sort_order=1
    ),
    TaskDefinition(
        task_id="monthly_search_100",
        name="累计搜索100次",
        description="本月累计搜索100次",
        task_type=TaskType.MONTHLY,
        trigger=TaskTrigger.SEARCH,
        target=100,
        reward_points=200,
        icon="🔍",
        sort_order=2
    ),
    TaskDefinition(
        task_id="monthly_subscribe_10",
        name="订阅10个内容",
        description="本月订阅10个内容源",
        task_type=TaskType.MONTHLY,
        trigger=TaskTrigger.SUBSCRIBE,
        target=10,
        reward_points=150,
        icon="📰",
        sort_order=3
    ),
    
    # ========== 一次性任务（新手任务） ==========
    TaskDefinition(
        task_id="onetime_bind_invite",
        name="绑定邀请码",
        description="绑定好友的邀请码",
        task_type=TaskType.ONETIME,
        trigger=TaskTrigger.BIND_INVITE,
        target=1,
        reward_points=30,
        icon="🎫",
        sort_order=1
    ),
    TaskDefinition(
        task_id="onetime_first_search",
        name="首次搜索",
        description="完成第一次搜索",
        task_type=TaskType.ONETIME,
        trigger=TaskTrigger.SEARCH,
        target=1,
        reward_points=20,
        icon="🔍",
        sort_order=2
    ),
    TaskDefinition(
        task_id="onetime_first_subscribe",
        name="首次订阅",
        description="订阅第一个内容源",
        task_type=TaskType.ONETIME,
        trigger=TaskTrigger.SUBSCRIBE,
        target=1,
        reward_points=20,
        icon="📰",
        sort_order=3
    ),
    TaskDefinition(
        task_id="onetime_invite_1",
        name="邀请1位好友",
        description="成功邀请1位新用户",
        task_type=TaskType.ONETIME,
        trigger=TaskTrigger.INVITE,
        target=1,
        reward_points=50,
        icon="👥",
        sort_order=4
    ),
    TaskDefinition(
        task_id="onetime_invite_5",
        name="邀请5位好友",
        description="成功邀请5位新用户",
        task_type=TaskType.ONETIME,
        trigger=TaskTrigger.INVITE,
        target=5,
        reward_points=200,
        icon="🎉",
        sort_order=5
    ),
    TaskDefinition(
        task_id="onetime_invite_10",
        name="邀请大使",
        description="成功邀请10位新用户",
        task_type=TaskType.ONETIME,
        trigger=TaskTrigger.INVITE,
        target=10,
        reward_points=500,
        icon="🏅",
        sort_order=6
    ),
]


class TaskManager:
    """任务管理器"""
    
    def __init__(self, db: DatabaseManager, points_manager: PointsManager = None):
        """
        初始化任务管理器
        
        Args:
            db: 数据库管理器
            points_manager: 积分管理器（用于发放奖励）
        """
        self.db = db
        self.points_manager = points_manager
        self._task_cache: Dict[str, TaskDefinition] = {}
        self._init_tables()
        self._load_default_tasks()
    
    def _init_tables(self):
        """初始化数据库表"""
        try:
            # 任务定义表
            self.db.execute_write("""
                CREATE TABLE IF NOT EXISTS task_definitions (
                    task_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    task_type TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    target INTEGER NOT NULL,
                    reward_points INTEGER NOT NULL,
                    icon TEXT DEFAULT '📋',
                    plugin_name TEXT,
                    sort_order INTEGER DEFAULT 0,
                    is_bonus INTEGER DEFAULT 0,
                    depends_on TEXT,
                    extra_config TEXT,
                    enabled INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 用户任务进度表
            self.db.execute_write("""
                CREATE TABLE IF NOT EXISTS user_task_progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    progress INTEGER DEFAULT 0,
                    target INTEGER NOT NULL,
                    completed INTEGER DEFAULT 0,
                    reward_claimed INTEGER DEFAULT 0,
                    completed_at DATETIME,
                    period_start DATETIME NOT NULL,
                    period_end DATETIME NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, task_id, period_start)
                )
            """)
            
            # 索引
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_user_task_user 
                ON user_task_progress(user_id)
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_user_task_period 
                ON user_task_progress(period_start, period_end)
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_user_task_claimable 
                ON user_task_progress(user_id, completed, reward_claimed)
            """)
            
            # 任务完成日志表
            self.db.execute_write("""
                CREATE TABLE IF NOT EXISTS task_completion_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    reward_points INTEGER NOT NULL,
                    completed_at DATETIME NOT NULL,
                    period_start DATETIME NOT NULL
                )
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_task_log_user 
                ON task_completion_logs(user_id, completed_at)
            """)
            
            logger.info("[TaskManager] 数据库表初始化完成")
            
        except Exception as e:
            logger.error(f"[TaskManager] 数据库初始化失败: {e}")
    
    def _load_default_tasks(self):
        """加载默认任务配置"""
        for task in DEFAULT_TASKS:
            self.register_task(task, update_if_exists=False)
    
    # ==================== 任务定义管理 ====================
    
    def register_task(self, task: TaskDefinition, update_if_exists: bool = True) -> bool:
        """
        注册任务
        
        Args:
            task: 任务定义
            update_if_exists: 如果存在是否更新
            
        Returns:
            是否成功
        """
        try:
            depends_on_json = json.dumps(task.depends_on) if task.depends_on else None
            extra_config_json = json.dumps(task.extra_config) if task.extra_config else None
            
            if update_if_exists:
                self.db.execute_write("""
                    INSERT OR REPLACE INTO task_definitions 
                    (task_id, name, description, task_type, trigger_type, target, 
                     reward_points, icon, plugin_name, sort_order, is_bonus, depends_on, 
                     extra_config, enabled)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task.task_id, task.name, task.description,
                    task.task_type.value, task.trigger.value, task.target,
                    task.reward_points, task.icon, task.plugin_name,
                    task.sort_order, 1 if task.is_bonus else 0,
                    depends_on_json, extra_config_json, 1 if task.enabled else 0
                ))
            else:
                # 只在不存在时插入
                existing = self.db.execute_one(
                    "SELECT task_id FROM task_definitions WHERE task_id = ?",
                    (task.task_id,)
                )
                if not existing:
                    self.db.execute_write("""
                        INSERT INTO task_definitions 
                        (task_id, name, description, task_type, trigger_type, target, 
                         reward_points, icon, plugin_name, sort_order, is_bonus, depends_on, 
                         extra_config, enabled)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        task.task_id, task.name, task.description,
                        task.task_type.value, task.trigger.value, task.target,
                        task.reward_points, task.icon, task.plugin_name,
                        task.sort_order, 1 if task.is_bonus else 0,
                        depends_on_json, extra_config_json, 1 if task.enabled else 0
                    ))
            
            # 更新缓存
            self._task_cache[task.task_id] = task
            return True
            
        except Exception as e:
            logger.error(f"[TaskManager] 注册任务失败: {e}")
            return False
    
    def get_task(self, task_id: str) -> Optional[TaskDefinition]:
        """获取任务定义"""
        if task_id in self._task_cache:
            return self._task_cache[task_id]
        
        try:
            row = self.db.execute_one(
                "SELECT * FROM task_definitions WHERE task_id = ? AND enabled = 1",
                (task_id,)
            )
            if row:
                task = self._row_to_task(row)
                self._task_cache[task_id] = task
                return task
            return None
        except Exception as e:
            logger.error(f"[TaskManager] 获取任务失败: {e}")
            return None
    
    def get_tasks_by_type(self, task_type: TaskType) -> List[TaskDefinition]:
        """按类型获取任务列表"""
        try:
            rows = self.db.execute(
                """SELECT * FROM task_definitions 
                   WHERE task_type = ? AND enabled = 1 
                   ORDER BY sort_order""",
                (task_type.value,)
            )
            return [self._row_to_task(row) for row in rows]
        except Exception as e:
            logger.error(f"[TaskManager] 获取任务列表失败: {e}")
            return []
    
    def _row_to_task(self, row) -> TaskDefinition:
        """数据库行转任务定义"""
        # 转换为字典以支持 .get() 方法
        if hasattr(row, 'keys'):
            row_dict = dict(row)
        else:
            row_dict = row
        
        depends_on = json.loads(row_dict['depends_on']) if row_dict.get('depends_on') else None
        extra_config = json.loads(row_dict['extra_config']) if row_dict.get('extra_config') else None
        
        return TaskDefinition(
            task_id=row_dict['task_id'],
            name=row_dict['name'],
            description=row_dict.get('description', ''),
            task_type=TaskType(row_dict['task_type']),
            trigger=TaskTrigger(row_dict['trigger_type']),
            target=row_dict['target'],
            reward_points=row_dict['reward_points'],
            icon=row_dict.get('icon', '📋'),
            enabled=bool(row_dict.get('enabled', 1)),
            plugin_name=row_dict.get('plugin_name'),
            sort_order=row_dict.get('sort_order', 0),
            is_bonus=bool(row_dict.get('is_bonus', 0)),
            depends_on=depends_on,
            extra_config=extra_config
        )
    
    # ==================== 周期计算 ====================
    
    def _get_period(self, task_type: TaskType, ref_date: date = None) -> Tuple[datetime, datetime]:
        """
        获取任务周期
        
        Returns:
            (period_start, period_end)
        """
        if ref_date is None:
            ref_date = date.today()
        
        if task_type == TaskType.DAILY:
            start = datetime.combine(ref_date, datetime.min.time())
            end = start + timedelta(days=1) - timedelta(seconds=1)
            
        elif task_type == TaskType.WEEKLY:
            # 周一为一周开始
            days_since_monday = ref_date.weekday()
            monday = ref_date - timedelta(days=days_since_monday)
            start = datetime.combine(monday, datetime.min.time())
            end = start + timedelta(days=7) - timedelta(seconds=1)
            
        elif task_type == TaskType.MONTHLY:
            start = datetime.combine(ref_date.replace(day=1), datetime.min.time())
            # 下个月第一天
            if ref_date.month == 12:
                next_month = ref_date.replace(year=ref_date.year + 1, month=1, day=1)
            else:
                next_month = ref_date.replace(month=ref_date.month + 1, day=1)
            end = datetime.combine(next_month, datetime.min.time()) - timedelta(seconds=1)
            
        elif task_type == TaskType.ONETIME:
            # 一次性任务：使用固定的起始时间（永不重置）
            start = datetime(2020, 1, 1)  # 固定起始时间
            end = datetime(2099, 12, 31, 23, 59, 59)  # 永不过期
        else:
            start = datetime.combine(ref_date, datetime.min.time())
            end = start + timedelta(days=1) - timedelta(seconds=1)
        
        return start, end
    
    # ==================== 进度管理 ====================
    
    def get_user_tasks(
        self, 
        user_id: str, 
        task_type: TaskType = None
    ) -> List[Tuple[TaskDefinition, UserTaskProgress]]:
        """
        获取用户任务列表（含进度）
        
        Returns:
            [(TaskDefinition, UserTaskProgress), ...]
        """
        try:
            # 获取任务定义
            if task_type:
                tasks = self.get_tasks_by_type(task_type)
            else:
                tasks = []
                for tt in TaskType:
                    tasks.extend(self.get_tasks_by_type(tt))
            
            result = []
            for task in tasks:
                progress = self._get_or_create_progress(user_id, task)
                result.append((task, progress))
            
            return result
            
        except Exception as e:
            logger.error(f"[TaskManager] 获取用户任务失败: {e}")
            return []
    
    def _get_or_create_progress(
        self, 
        user_id: str, 
        task: TaskDefinition
    ) -> UserTaskProgress:
        """获取或创建用户任务进度"""
        period_start, period_end = self._get_period(task.task_type)
        
        try:
            row = self.db.execute_one("""
                SELECT * FROM user_task_progress 
                WHERE user_id = ? AND task_id = ? AND period_start = ?
            """, (user_id, task.task_id, period_start))
            
            if row:
                # 转换为字典以支持 get 方法
                row_dict = dict(row)
                return UserTaskProgress(
                    user_id=row_dict['user_id'],
                    task_id=row_dict['task_id'],
                    progress=row_dict['progress'],
                    target=row_dict['target'],
                    completed=bool(row_dict['completed']),
                    reward_claimed=bool(row_dict['reward_claimed']),
                    completed_at=row_dict.get('completed_at'),
                    period_start=period_start,
                    period_end=period_end
                )
            
            # 创建新进度
            target = task.target
            # 月任务动态调整目标（当月天数）
            if task.task_id == "monthly_full_checkin":
                import calendar
                _, days_in_month = calendar.monthrange(period_start.year, period_start.month)
                target = days_in_month
            
            self.db.execute_write("""
                INSERT INTO user_task_progress 
                (user_id, task_id, progress, target, period_start, period_end)
                VALUES (?, ?, 0, ?, ?, ?)
            """, (user_id, task.task_id, target, period_start, period_end))
            
            return UserTaskProgress(
                user_id=user_id,
                task_id=task.task_id,
                progress=0,
                target=target,
                completed=False,
                reward_claimed=False,
                period_start=period_start,
                period_end=period_end
            )
            
        except Exception as e:
            logger.error(f"[TaskManager] 获取进度失败: {e}")
            return UserTaskProgress(
                user_id=user_id,
                task_id=task.task_id,
                target=task.target,
                period_start=period_start,
                period_end=period_end
            )
    
    def update_progress(
        self, 
        user_id: str, 
        trigger: TaskTrigger, 
        increment: int = 1,
        plugin_name: str = None
    ) -> List[str]:
        """
        更新任务进度
        
        Args:
            user_id: 用户ID
            trigger: 触发类型
            increment: 增量
            plugin_name: 插件名称（可选，用于过滤特定插件的任务）
            
        Returns:
            完成的任务ID列表
        """
        completed_tasks = []
        
        try:
            # 获取所有匹配触发类型的任务
            rows = self.db.execute("""
                SELECT * FROM task_definitions 
                WHERE trigger_type = ? AND enabled = 1
            """, (trigger.value,))
            
            for row in rows:
                task = self._row_to_task(row)
                
                # 如果指定了插件名，只更新该插件的任务
                if plugin_name and task.plugin_name and task.plugin_name != plugin_name:
                    continue
                
                # 获取进度
                progress = self._get_or_create_progress(user_id, task)
                
                # 已完成的不再更新
                if progress.completed:
                    continue
                
                # 更新进度
                new_progress = min(progress.progress + increment, progress.target)
                completed = new_progress >= progress.target
                completed_at = datetime.now() if completed else None
                
                self.db.execute_write("""
                    UPDATE user_task_progress 
                    SET progress = ?, completed = ?, completed_at = ?, updated_at = ?
                    WHERE user_id = ? AND task_id = ? AND period_start = ?
                """, (
                    new_progress, 1 if completed else 0, completed_at, datetime.now(),
                    user_id, task.task_id, progress.period_start
                ))
                
                if completed:
                    completed_tasks.append(task.task_id)
                    logger.info(f"[TaskManager] 用户 {user_id} 完成任务: {task.name}")
            
            # 检查并更新"全部完成"类型的任务
            if completed_tasks:
                self._check_bonus_tasks(user_id)
            
            return completed_tasks
            
        except Exception as e:
            logger.error(f"[TaskManager] 更新进度失败: {e}")
            return []
    
    def _check_bonus_tasks(self, user_id: str):
        """检查并更新额外奖励任务（如"全部完成"）"""
        try:
            # 获取所有 bonus 任务
            rows = self.db.execute("""
                SELECT * FROM task_definitions 
                WHERE is_bonus = 1 AND enabled = 1
            """)
            
            for row in rows:
                task = self._row_to_task(row)
                if not task.depends_on:
                    continue
                
                progress = self._get_or_create_progress(user_id, task)
                if progress.completed:
                    continue
                
                # 检查依赖任务完成数
                completed_count = 0
                for dep_task_id in task.depends_on:
                    dep_task = self.get_task(dep_task_id)
                    if dep_task:
                        dep_progress = self._get_or_create_progress(user_id, dep_task)
                        if dep_progress.completed:
                            completed_count += 1
                
                # 更新进度
                if completed_count != progress.progress:
                    completed = completed_count >= task.target
                    completed_at = datetime.now() if completed else None
                    
                    self.db.execute_write("""
                        UPDATE user_task_progress 
                        SET progress = ?, completed = ?, completed_at = ?, updated_at = ?
                        WHERE user_id = ? AND task_id = ? AND period_start = ?
                    """, (
                        completed_count, 1 if completed else 0, completed_at, datetime.now(),
                        user_id, task.task_id, progress.period_start
                    ))
                    
                    if completed:
                        logger.info(f"[TaskManager] 用户 {user_id} 完成额外任务: {task.name}")
                        
        except Exception as e:
            logger.error(f"[TaskManager] 检查额外任务失败: {e}")
    
    # ==================== 奖励管理 ====================
    
    def claim_reward(self, user_id: str, task_id: str) -> Tuple[bool, str, int]:
        """
        领取任务奖励
        
        Returns:
            (成功, 消息, 积分数)
        """
        try:
            task = self.get_task(task_id)
            if not task:
                return False, "任务不存在", 0
            
            progress = self._get_or_create_progress(user_id, task)
            
            if not progress.completed:
                return False, "任务未完成", 0
            
            if progress.reward_claimed:
                return False, "奖励已领取", 0
            
            # 检查是否在有效周期内
            now = datetime.now()
            if now > progress.period_end:
                return False, "任务已过期", 0
            
            # 发放奖励
            reward = task.reward_points
            if self.points_manager:
                self.points_manager.add_points(
                    user_id, 
                    reward, 
                    "task_reward", 
                    f"完成任务: {task.name}"
                )
            
            # 标记已领取
            self.db.execute_write("""
                UPDATE user_task_progress 
                SET reward_claimed = 1, updated_at = ?
                WHERE user_id = ? AND task_id = ? AND period_start = ?
            """, (datetime.now(), user_id, task_id, progress.period_start))
            
            # 记录日志
            self.db.execute_write("""
                INSERT INTO task_completion_logs 
                (user_id, task_id, task_type, reward_points, completed_at, period_start)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user_id, task_id, task.task_type.value, 
                reward, datetime.now(), progress.period_start
            ))
            
            return True, f"获得 {reward} 积分", reward
            
        except Exception as e:
            logger.error(f"[TaskManager] 领取奖励失败: {e}")
            return False, "领取失败", 0
    
    def claim_all_rewards(self, user_id: str) -> Tuple[int, int]:
        """
        一键领取所有可领取的奖励
        
        Returns:
            (领取任务数, 总积分)
        """
        claimed_count = 0
        total_points = 0
        
        try:
            # 获取所有可领取的任务
            for task_type in TaskType:
                tasks = self.get_user_tasks(user_id, task_type)
                for task, progress in tasks:
                    if progress.is_claimable:
                        success, _, points = self.claim_reward(user_id, task.task_id)
                        if success:
                            claimed_count += 1
                            total_points += points
            
            return claimed_count, total_points
            
        except Exception as e:
            logger.error(f"[TaskManager] 一键领取失败: {e}")
            return claimed_count, total_points
    
    def get_claimable_count(self, user_id: str) -> int:
        """获取可领取奖励的任务数"""
        try:
            row = self.db.execute_one("""
                SELECT COUNT(*) as count FROM user_task_progress 
                WHERE user_id = ? AND completed = 1 AND reward_claimed = 0
                AND period_end >= ?
            """, (user_id, datetime.now()))
            return row['count'] if row else 0
        except Exception as e:
            logger.error(f"[TaskManager] 获取可领取数失败: {e}")
            return 0
    
    # ==================== 统计查询 ====================
    
    def get_completion_stats(self, user_id: str) -> Dict[str, Any]:
        """获取用户任务完成统计"""
        try:
            stats = {
                'daily': {'completed': 0, 'total': 0, 'points': 0},
                'weekly': {'completed': 0, 'total': 0, 'points': 0},
                'monthly': {'completed': 0, 'total': 0, 'points': 0},
                'total_points_earned': 0
            }
            
            for task_type in TaskType:
                tasks = self.get_user_tasks(user_id, task_type)
                key = task_type.value
                stats[key]['total'] = len(tasks)
                
                for task, progress in tasks:
                    if progress.completed:
                        stats[key]['completed'] += 1
                    if progress.reward_claimed:
                        stats[key]['points'] += task.reward_points
            
            # 历史总积分
            row = self.db.execute_one("""
                SELECT SUM(reward_points) as total FROM task_completion_logs 
                WHERE user_id = ?
            """, (user_id,))
            stats['total_points_earned'] = row['total'] or 0 if row else 0
            
            return stats
            
        except Exception as e:
            logger.error(f"[TaskManager] 获取统计失败: {e}")
            return {}
    
    def get_leaderboard(self, days: int = 7, limit: int = 10) -> List[Dict]:
        """获取任务完成排行榜"""
        try:
            cutoff = datetime.now() - timedelta(days=days)
            rows = self.db.execute("""
                SELECT user_id, 
                       COUNT(*) as task_count,
                       SUM(reward_points) as total_points
                FROM task_completion_logs 
                WHERE completed_at >= ?
                GROUP BY user_id
                ORDER BY total_points DESC
                LIMIT ?
            """, (cutoff, limit))
            
            return [
                {
                    'user_id': row['user_id'],
                    'task_count': row['task_count'],
                    'total_points': row['total_points']
                }
                for row in rows
            ]
            
        except Exception as e:
            logger.error(f"[TaskManager] 获取排行榜失败: {e}")
            return []
    
    # ==================== 任务重置 ====================
    
    def reset_tasks(self, task_type: TaskType) -> int:
        """
        重置指定类型的任务进度
        
        Args:
            task_type: 任务类型
            
        Returns:
            重置的记录数
        """
        if task_type == TaskType.ONETIME:
            logger.debug("[TaskManager] 一次性任务不需要重置")
            return 0
        
        try:
            now = datetime.now()
            
            # 获取新周期
            period_start, period_end = self._get_task_period(task_type)
            
            # 删除已过期的进度记录（未领取奖励的）
            result = self.db.execute_write("""
                DELETE FROM user_task_progress 
                WHERE task_id IN (
                    SELECT task_id FROM task_definitions WHERE task_type = ?
                )
                AND period_end < ?
                AND reward_claimed = 0
            """, (task_type.value, now))
            
            deleted_count = result.rowcount if hasattr(result, 'rowcount') else 0
            
            # 重置已领取奖励但周期已过的记录
            result2 = self.db.execute_write("""
                UPDATE user_task_progress 
                SET progress = 0, 
                    completed = 0, 
                    reward_claimed = 0,
                    period_start = ?,
                    period_end = ?,
                    updated_at = ?
                WHERE task_id IN (
                    SELECT task_id FROM task_definitions WHERE task_type = ?
                )
                AND period_end < ?
            """, (period_start, period_end, now, task_type.value, now))
            
            reset_count = result2.rowcount if hasattr(result2, 'rowcount') else 0
            
            total = deleted_count + reset_count
            logger.info(f"[TaskManager] 重置 {task_type.value} 任务: 删除{deleted_count}条, 重置{reset_count}条")
            
            return total
            
        except Exception as e:
            logger.error(f"[TaskManager] 重置任务失败: {e}")
            return 0
    
    def reset_daily_tasks(self) -> int:
        """重置每日任务"""
        return self.reset_tasks(TaskType.DAILY)
    
    def reset_weekly_tasks(self) -> int:
        """重置每周任务"""
        return self.reset_tasks(TaskType.WEEKLY)
    
    def reset_monthly_tasks(self) -> int:
        """重置每月任务"""
        return self.reset_tasks(TaskType.MONTHLY)
    
    def cleanup_expired_logs(self, days: int = 90) -> int:
        """
        清理过期的任务完成日志
        
        Args:
            days: 保留天数
            
        Returns:
            删除的记录数
        """
        try:
            cutoff = datetime.now() - timedelta(days=days)
            result = self.db.execute_write("""
                DELETE FROM task_completion_logs 
                WHERE completed_at < ?
            """, (cutoff,))
            
            deleted = result.rowcount if hasattr(result, 'rowcount') else 0
            if deleted > 0:
                logger.info(f"[TaskManager] 清理过期日志: {deleted}条")
            return deleted
            
        except Exception as e:
            logger.error(f"[TaskManager] 清理日志失败: {e}")
            return 0


# ==================== 定时任务注册 ====================

def register_task_scheduler_jobs(scheduler=None):
    """
    注册任务系统的定时任务
    
    Args:
        scheduler: PluginScheduler 实例
    """
    if scheduler is None:
        try:
            from .scheduler import get_scheduler
            scheduler = get_scheduler()
        except ImportError:
            logger.warning("[TaskManager] 调度器不可用，跳过定时任务注册")
            return
    
    task_manager = get_task_manager()
    if not task_manager:
        logger.warning("[TaskManager] 任务管理器不可用，跳过定时任务注册")
        return
    
    # 每日任务重置 - 每天凌晨 0:05
    scheduler.register_task(
        task_id="task_daily_reset",
        func=task_manager.reset_daily_tasks,
        cron="5 0 * * *",
        plugin_name="task_system",
        description="每日任务重置"
    )
    
    # 每周任务重置 - 每周一凌晨 0:10
    scheduler.register_task(
        task_id="task_weekly_reset",
        func=task_manager.reset_weekly_tasks,
        cron="10 0 * * 1",
        plugin_name="task_system",
        description="每周任务重置"
    )
    
    # 每月任务重置 - 每月1号凌晨 0:15
    scheduler.register_task(
        task_id="task_monthly_reset",
        func=task_manager.reset_monthly_tasks,
        cron="15 0 1 * *",
        plugin_name="task_system",
        description="每月任务重置"
    )
    
    # 日志清理 - 每周日凌晨 3:00
    scheduler.register_task(
        task_id="task_log_cleanup",
        func=lambda: task_manager.cleanup_expired_logs(90),
        cron="0 3 * * 0",
        plugin_name="task_system",
        description="任务日志清理（保留90天）"
    )
    
    logger.info("[TaskManager] 定时任务注册完成")


# ==================== 全局实例 ====================

_task_manager: Optional[TaskManager] = None


def get_task_manager(
    db: DatabaseManager = None, 
    points_manager: PointsManager = None
) -> Optional[TaskManager]:
    """
    获取任务管理器实例（单例模式）
    
    Args:
        db: 数据库管理器（首次调用时必须提供）
        points_manager: 积分管理器
    
    Returns:
        TaskManager 实例
    """
    global _task_manager
    
    if _task_manager is None and db is not None:
        _task_manager = TaskManager(db, points_manager)
        logger.info("[TaskManager] 创建全局任务管理器实例")
    
    return _task_manager
