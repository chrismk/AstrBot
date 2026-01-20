"""
速率限制器 - 防止恶意刷请求

功能：
1. 滑动窗口限流
2. 支持不同操作的不同限制
3. 支持会员等级差异化限制
4. 自动清理过期记录
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from threading import Lock

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class RateLimiter:
    """速率限制器 - 基于滑动窗口算法"""
    
    # 默认限制配置 {action_type: (max_requests, window_seconds)}
    # 推广期配置，适当放宽限制
    DEFAULT_LIMITS = {
        "default": (60, 60),  # 默认：每分钟60次
        "search": (60, 60),  # 搜索类：每分钟60次
        "download": (60, 60),  # 下载类：每分钟60次
        "ai": (60, 60),  # AI解读类：每分钟60次
    }
    
    # 会员等级倍率
    MEMBER_MULTIPLIERS = {
        0: 1.0,  # 免费用户：1倍
        1: 2.0,  # 高级会员：2倍
        2: 5.0,  # VIP会员：5倍
    }
    
    # action_type 到限流类别的映射
    ACTION_CATEGORY_MAP = {
        # 搜索类
        "music_search": "search",
        "book_search": "search",
        "douban_search": "search",
        "pansou_search": "search",
        # 下载类
        "music_download": "download",
        "book_download": "download",
        "yunpan_download": "download",
        # AI类
        "ai_interpret": "ai",
        "book_ai": "ai",
        "douban_ai": "ai",
    }
    
    def __init__(self):
        """初始化速率限制器"""
        # {user_id: {action_type: [timestamp, ...]}}
        self._requests: Dict[str, Dict[str, List[datetime]]] = defaultdict(lambda: defaultdict(list))
        self._lock = Lock()
        self._last_cleanup = datetime.now()
        # 动态注册的限制配置
        self._custom_limits: Dict[str, Tuple[int, int]] = {}
    
    def register_limit(self, action_type: str, max_requests: int, window_seconds: int = 60):
        """
        注册自定义限流配置
        
        Args:
            action_type: 操作类型
            max_requests: 最大请求数
            window_seconds: 时间窗口（秒）
        """
        self._custom_limits[action_type] = (max_requests, window_seconds)
        logger.debug(f"[RateLimiter] 注册限流配置: {action_type} = {max_requests}次/{window_seconds}秒")
    
    def is_allowed(
        self, 
        user_id: str, 
        action_type: str = "default",
        member_level: int = 0
    ) -> Tuple[bool, Optional[str]]:
        """
        检查是否允许请求
        
        Args:
            user_id: 用户ID
            action_type: 操作类型
            member_level: 会员等级 (0=免费, 1=高级, 2=VIP)
            
        Returns:
            (是否允许, 错误消息)
        """
        with self._lock:
            # 定期清理过期记录
            self._cleanup_if_needed()
            
            # 获取限制配置
            max_requests, window_seconds = self._get_limit(action_type, member_level)
            
            # 计算窗口起始时间
            now = datetime.now()
            window_start = now - timedelta(seconds=window_seconds)
            
            # 清理过期记录
            self._requests[user_id][action_type] = [
                ts for ts in self._requests[user_id][action_type]
                if ts > window_start
            ]
            
            # 检查是否超限
            current_count = len(self._requests[user_id][action_type])
            if current_count >= max_requests:
                # 计算需要等待的时间
                oldest_request = self._requests[user_id][action_type][0]
                wait_seconds = int((oldest_request + timedelta(seconds=window_seconds) - now).total_seconds())
                
                logger.warning(
                    f"[RateLimiter] 用户 {user_id} 请求过于频繁: "
                    f"{action_type} ({current_count}/{max_requests})"
                )
                
                return False, f"⚠️ 请求过于频繁，请 {wait_seconds} 秒后再试"
            
            # 记录本次请求
            self._requests[user_id][action_type].append(now)
            
            logger.debug(
                f"[RateLimiter] 用户 {user_id} 请求通过: "
                f"{action_type} ({current_count + 1}/{max_requests})"
            )
            
            return True, None
    
    def _get_limit(self, action_type: str, member_level: int) -> Tuple[int, int]:
        """
        获取限制配置
        
        优先级：自定义配置 > 类别映射 > 默认配置
        
        Args:
            action_type: 操作类型
            member_level: 会员等级
            
        Returns:
            (最大请求数, 窗口秒数)
        """
        # 1. 优先使用自定义配置
        if action_type in self._custom_limits:
            base_limit = self._custom_limits[action_type]
        # 2. 使用类别映射
        elif action_type in self.ACTION_CATEGORY_MAP:
            category = self.ACTION_CATEGORY_MAP[action_type]
            base_limit = self.DEFAULT_LIMITS.get(category, self.DEFAULT_LIMITS["default"])
        # 3. 直接匹配默认配置
        elif action_type in self.DEFAULT_LIMITS:
            base_limit = self.DEFAULT_LIMITS[action_type]
        # 4. 使用默认值
        else:
            base_limit = self.DEFAULT_LIMITS["default"]
        
        max_requests, window_seconds = base_limit
        
        # 应用会员倍率
        multiplier = self.MEMBER_MULTIPLIERS.get(member_level, 1.0)
        max_requests = int(max_requests * multiplier)
        
        return max_requests, window_seconds
    
    def _cleanup_if_needed(self):
        """定期清理过期记录（每5分钟）"""
        now = datetime.now()
        if (now - self._last_cleanup).total_seconds() < 300:
            return
        
        self._last_cleanup = now
        
        # 清理空的用户记录
        empty_users = []
        for user_id, actions in self._requests.items():
            # 清理空的操作记录
            empty_actions = [
                action for action, timestamps in actions.items()
                if not timestamps
            ]
            for action in empty_actions:
                del actions[action]
            
            # 如果用户没有任何记录，标记删除
            if not actions:
                empty_users.append(user_id)
        
        for user_id in empty_users:
            del self._requests[user_id]
        
        if empty_users:
            logger.debug(f"[RateLimiter] 清理了 {len(empty_users)} 个空用户记录")
    
    def get_remaining(
        self, 
        user_id: str, 
        action_type: str = "default",
        member_level: int = 0
    ) -> int:
        """
        获取剩余请求次数
        
        Args:
            user_id: 用户ID
            action_type: 操作类型
            member_level: 会员等级
            
        Returns:
            剩余次数
        """
        with self._lock:
            max_requests, window_seconds = self._get_limit(action_type, member_level)
            
            now = datetime.now()
            window_start = now - timedelta(seconds=window_seconds)
            
            # 统计窗口内的请求数
            current_count = sum(
                1 for ts in self._requests[user_id][action_type]
                if ts > window_start
            )
            
            return max(0, max_requests - current_count)
    
    def reset(self, user_id: str, action_type: Optional[str] = None):
        """
        重置用户的限流记录
        
        Args:
            user_id: 用户ID
            action_type: 操作类型（None表示重置所有）
        """
        with self._lock:
            if action_type:
                if user_id in self._requests:
                    self._requests[user_id][action_type] = []
                    logger.info(f"[RateLimiter] 重置用户 {user_id} 的 {action_type} 限流记录")
            else:
                self._requests[user_id] = defaultdict(list)
                logger.info(f"[RateLimiter] 重置用户 {user_id} 的所有限流记录")
    
    def get_stats(self) -> Dict:
        """
        获取限流统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            total_users = len(self._requests)
            total_requests = sum(
                len(timestamps)
                for actions in self._requests.values()
                for timestamps in actions.values()
            )
            
            return {
                "total_users": total_users,
                "total_requests": total_requests,
                "avg_requests_per_user": total_requests / total_users if total_users > 0 else 0
            }
    
    def get_config(self) -> Dict:
        """
        获取当前限流配置
        
        Returns:
            配置字典
        """
        return {
            "default_limits": {**self.DEFAULT_LIMITS, **self._custom_limits},
            "multipliers": self.MEMBER_MULTIPLIERS
        }
    
    def update_limit(self, category: str, max_requests: int, window_seconds: int = 60):
        """
        更新限流配置
        
        Args:
            category: 类别 (search/download/ai/default)
            max_requests: 最大请求数
            window_seconds: 时间窗口（秒）
        """
        if category in self.DEFAULT_LIMITS:
            self.DEFAULT_LIMITS[category] = (max_requests, window_seconds)
        else:
            self._custom_limits[category] = (max_requests, window_seconds)
        logger.info(f"[RateLimiter] 更新限流配置: {category} = {max_requests}次/{window_seconds}秒")


# 全局单例
_rate_limiter_instance: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """获取全局速率限制器实例"""
    global _rate_limiter_instance
    if _rate_limiter_instance is None:
        _rate_limiter_instance = RateLimiter()
        logger.info("[RateLimiter] 速率限制器初始化完成")
    return _rate_limiter_instance
