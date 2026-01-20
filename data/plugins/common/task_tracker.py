"""
任务进度追踪器

各插件在关键操作后调用，自动更新任务进度。
采用单例模式，全局共享。

使用示例：
    from common.task_tracker import get_task_tracker, TaskTrigger
    
    # 在签到插件中
    tracker = get_task_tracker()
    tracker.track(user_id, TaskTrigger.CHECKIN)
    
    # 在搜索插件中
    tracker.track(user_id, TaskTrigger.SEARCH, plugin_name='music')
    
    # 在订阅插件中
    tracker.track(user_id, TaskTrigger.SUBSCRIBE)
    
    # 批量追踪
    tracker.track(user_id, TaskTrigger.SEARCH, increment=3)
"""

from typing import Optional, List, Callable, Any
from datetime import datetime

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from .task_manager import TaskManager, TaskTrigger, get_task_manager


class TaskTracker:
    """
    任务进度追踪器
    
    提供简洁的API供各插件调用，自动更新任务进度
    """
    
    _instance: Optional['TaskTracker'] = None
    
    def __init__(self, task_manager: TaskManager = None):
        """
        初始化追踪器
        
        Args:
            task_manager: 任务管理器实例
        """
        self._task_manager = task_manager
        self._completion_callbacks: List[Callable] = []
    
    @classmethod
    def get_instance(cls, task_manager: TaskManager = None) -> 'TaskTracker':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls(task_manager)
        elif task_manager is not None and cls._instance._task_manager is None:
            cls._instance._task_manager = task_manager
        return cls._instance
    
    @property
    def task_manager(self) -> Optional[TaskManager]:
        """获取任务管理器"""
        if self._task_manager is None:
            self._task_manager = get_task_manager()
            if self._task_manager is None:
                logger.debug("[TaskTracker] 任务管理器未初始化，跳过任务追踪")
        return self._task_manager
    
    def track(
        self, 
        user_id: str, 
        trigger: TaskTrigger, 
        increment: int = 1,
        plugin_name: str = None,
        **kwargs
    ) -> List[str]:
        """
        追踪用户行为，更新任务进度
        
        Args:
            user_id: 用户ID
            trigger: 触发类型
            increment: 增量（默认1）
            plugin_name: 插件名称（可选）
            **kwargs: 额外参数
            
        Returns:
            完成的任务ID列表
        """
        if not self.task_manager:
            logger.debug("[TaskTracker] 任务管理器未初始化，跳过任务追踪")
            return []
        
        try:
            completed_tasks = self.task_manager.update_progress(
                user_id=user_id,
                trigger=trigger,
                increment=increment,
                plugin_name=plugin_name
            )
            
            # 触发完成回调
            if completed_tasks:
                for task_id in completed_tasks:
                    self._on_task_completed(user_id, task_id)
            
            return completed_tasks
            
        except Exception as e:
            logger.error(f"[TaskTracker] 追踪失败: {e}")
            return []
    
    def on_completion(self, callback: Callable[[str, str], Any]):
        """
        注册任务完成回调
        
        Args:
            callback: 回调函数，参数为 (user_id, task_id)
        """
        self._completion_callbacks.append(callback)
    
    def _on_task_completed(self, user_id: str, task_id: str):
        """任务完成时触发"""
        for callback in self._completion_callbacks:
            try:
                callback(user_id, task_id)
            except Exception as e:
                logger.error(f"[TaskTracker] 完成回调失败: {e}")
    
    # ==================== 便捷方法 ====================
    
    def track_checkin(self, user_id: str) -> List[str]:
        """追踪签到"""
        return self.track(user_id, TaskTrigger.CHECKIN)
    
    def track_search(self, user_id: str, plugin_name: str = None) -> List[str]:
        """追踪搜索"""
        return self.track(user_id, TaskTrigger.SEARCH, plugin_name=plugin_name)
    
    def track_download(self, user_id: str, plugin_name: str = None) -> List[str]:
        """追踪下载"""
        return self.track(user_id, TaskTrigger.DOWNLOAD, plugin_name=plugin_name)
    
    def track_subscribe(self, user_id: str) -> List[str]:
        """追踪订阅"""
        return self.track(user_id, TaskTrigger.SUBSCRIBE)
    
    def track_feedback(self, user_id: str) -> List[str]:
        """追踪反馈"""
        return self.track(user_id, TaskTrigger.FEEDBACK)
    
    def track_view_ranking(self, user_id: str) -> List[str]:
        """追踪查看榜单"""
        return self.track(user_id, TaskTrigger.VIEW_RANKING)
    
    def track_invite(self, user_id: str) -> List[str]:
        """追踪邀请好友"""
        return self.track(user_id, TaskTrigger.INVITE)
    
    def track_bind_invite(self, user_id: str) -> List[str]:
        """追踪绑定邀请码"""
        return self.track(user_id, TaskTrigger.BIND_INVITE)


# ==================== 全局函数 ====================

def get_task_tracker(task_manager: TaskManager = None) -> TaskTracker:
    """获取任务追踪器实例"""
    return TaskTracker.get_instance(task_manager)


# ==================== 装饰器 ====================

def track_task(trigger: TaskTrigger, plugin_name: str = None):
    """
    任务追踪装饰器
    
    自动在函数执行成功后追踪任务进度
    
    使用示例：
        @track_task(TaskTrigger.SEARCH, plugin_name='music')
        async def search(self, event, keyword):
            # 搜索逻辑
            return results
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            
            # 尝试从参数中获取 user_id
            user_id = None
            
            # 检查是否有 event 参数
            for arg in args:
                if hasattr(arg, 'get_sender_id'):
                    # 尝试使用统一用户ID
                    try:
                        from .user_utils import get_unified_user_id
                        user_id = get_unified_user_id(arg)
                    except ImportError:
                        user_id = arg.get_sender_id()
                    break
            
            if not user_id:
                user_id = kwargs.get('user_id')
            
            if user_id:
                tracker = get_task_tracker()
                tracker.track(user_id, trigger, plugin_name=plugin_name)
            
            return result
        
        return wrapper
    return decorator
