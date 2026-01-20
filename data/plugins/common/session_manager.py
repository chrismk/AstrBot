"""
统一的会话管理器

提供标准化的会话创建、获取、更新、过期管理功能，支持多种会话类型和自定义处理器。

核心功能：
- 会话生命周期管理（创建、获取、更新、结束）
- 自动过期检测和清理
- 自动续期机制
- 步骤历史记录
- 会话类型处理器注册
- 统一的消息处理接口

使用示例：
    from common import get_session_manager
    
    # 推荐：使用全局会话管理器（所有插件共享）
    session_manager = get_session_manager(timeout_minutes=1)
    
    # 注册会话处理器
    async def handle_menu(session_id, message, session, **context):
        # 处理菜单会话
        return result
    
    session_manager.register_handler('menu', handle_menu)
    
    # 创建会话
    session = session_manager.create_session(
        session_id="user_123",
        session_type="menu",
        user_id="user_123",
        capabilities={"supports_buttons": False}
    )
    
    # 处理消息
    result = await session_manager.handle_message(
        session_id="user_123",
        message="1",
        event=event
    )
    
注意：
    - 每个插件应使用唯一的命名空间（如 "douban", "pansou"）
    - 命名空间会自动添加到会话ID前缀，实现完全隔离
    - 插件代码无需修改，SessionManager 自动处理命名空间转换

互斥会话模式（推荐）：
    - 同一用户同一时间只保持一个活动会话
    - 新会话创建时，旧会话自动结束
    - 避免命令歧义（如 p/n 等导航命令）
    - 提供会话切换提示，让用户明确当前会话状态
    
    示例：
        # 插件A触发插件B时，结束自己的会话
        self.session_manager.end_session(session_id)
        # 调用插件B，让插件B创建新会话
        await plugin_b._handle_command(event, keyword, create_session=True, from_plugin="plugin_a")
"""

from typing import Dict, Any, Optional, Callable, List
from datetime import datetime, timedelta
from astrbot.api import logger


# 全局会话管理器实例
_global_session_manager: Optional['SessionManager'] = None


def get_session_manager(timeout_minutes: int = 1) -> 'SessionManager':
    """
    获取全局会话管理器（单例模式）
    
    Args:
        timeout_minutes: 会话超时时间（分钟），仅在首次创建时生效
    
    Returns:
        全局 SessionManager 实例
    
    注意：
        - 所有插件共享同一个 SessionManager 实例
        - 确保同一用户同一时间只有一个活动会话
        - 通过 session['type'] 区分不同插件的会话
    """
    global _global_session_manager
    if _global_session_manager is None:
        _global_session_manager = SessionManager(timeout_minutes=timeout_minutes)
        logger.info(f"[SessionManager] 创建全局会话管理器，超时时间: {timeout_minutes}分钟")
    return _global_session_manager


class SessionManager:
    """统一的会话管理器 - 支持多种会话类型"""
    
    def __init__(self, timeout_minutes: int = 1):
        """
        初始化会话管理器
        
        Args:
            timeout_minutes: 会话超时时间（分钟）
        """
        self.timeout_minutes = timeout_minutes
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self._handlers: Dict[str, Callable] = {}  # 会话类型处理器
        logger.debug(f"[SessionManager] 初始化完成，超时时间: {timeout_minutes}分钟")
    
    def register_handler(self, session_type: str, handler: Callable):
        """
        注册会话类型处理器
        
        Args:
            session_type: 会话类型标识
            handler: 异步处理函数，签名: async def handler(session_id, message, session, **context) -> Any
        """
        self._handlers[session_type] = handler
        logger.debug(f"[SessionManager] 注册处理器: {session_type}")
    
    def create_session(
        self, 
        session_id: str, 
        session_type: str, 
        user_id: str,
        data: Dict[str, Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        创建新会话
        
        Args:
            session_id: 会话ID（通常是用户ID或群组ID）
            session_type: 会话类型（用于路由到对应处理器）
            user_id: 用户ID
            data: 会话数据字典
            **kwargs: 其他扩展字段（如 capabilities, config 等）
        
        Returns:
            创建的会话对象
        """
        now = datetime.now()
        session = {
            'type': session_type,
            'user_id': user_id,
            'step': 0,
            'data': data or {},
            'created_at': now,
            'expires_at': now + timedelta(minutes=self.timeout_minutes),
            'step_history': [],  # 步骤历史，用于返回上级
            **kwargs  # 支持扩展字段（如 capabilities, config 等）
        }
        self.sessions[session_id] = session
        logger.debug(f"[SessionManager] 创建会话 - session_id={session_id}, type={session_type}, timeout={self.timeout_minutes}分钟")
        return session
    
    def get_session(
        self, 
        session_id: str, 
        renew: bool = True,
        auto_cleanup: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        获取会话（自动续期和清理）
        
        Args:
            session_id: 会话ID
            renew: 是否续期（延长过期时间）
            auto_cleanup: 是否自动清理过期会话
        
        Returns:
            会话对象，如果不存在或已过期则返回 None
        """
        session = self.sessions.get(session_id)
        if not session:
            return None
        
        # 检查过期
        if datetime.now() > session['expires_at']:
            logger.info(f"[SessionManager] 会话已过期 - session_id={session_id}")
            if auto_cleanup:
                self.end_session(session_id)
            return None
        
        # 续期：每次访问时延长过期时间
        if renew:
            session['expires_at'] = datetime.now() + timedelta(minutes=self.timeout_minutes)
            logger.debug(f"[SessionManager] 会话续期 - session_id={session_id}, 新过期时间={session['expires_at']}")
        
        return session
    
    def update_session(
        self, 
        session_id: str, 
        step: int = None, 
        data: Dict[str, Any] = None,
        save_history: bool = True,
        **kwargs
    ):
        """
        更新会话
        
        Args:
            session_id: 会话ID
            step: 新的步骤值
            data: 要更新的数据字典（会合并到现有数据）
            save_history: 是否保存步骤历史
            **kwargs: 其他要更新的字段
        """
        if session_id not in self.sessions:
            logger.warning(f"[SessionManager] 会话不存在，无法更新 - session_id={session_id}")
            return
        
        session = self.sessions[session_id]
        
        # 更新步骤
        if step is not None:
            current_step = session['step']
            if save_history and current_step != step:
                # 保存步骤历史（用于返回上级）
                session['step_history'].append(current_step)
            session['step'] = step
            logger.debug(f"[SessionManager] 更新步骤 - session_id={session_id}, step={step}")
        
        # 更新数据
        if data is not None:
            session['data'].update(data)
        
        # 更新其他字段
        for key, value in kwargs.items():
            session[key] = value
    
    def end_session(self, session_id: str):
        """
        结束会话
        
        Args:
            session_id: 会话ID
        """
        if session_id in self.sessions:
            session_type = self.sessions[session_id].get('type', 'unknown')
            del self.sessions[session_id]
            logger.debug(f"[SessionManager] 结束会话 - session_id={session_id}, type={session_type}")
    
    async def handle_message(
        self, 
        session_id: str, 
        message: str,
        **context
    ) -> Any:
        """
        处理会话消息（调用注册的处理器）
        
        Args:
            session_id: 会话ID
            message: 用户消息
            **context: 额外的上下文参数（如 event, user_id 等）
        
        Returns:
            处理结果（由具体处理器返回）
        """
        session = self.get_session(session_id)
        if not session:
            return None
            
        session_type = session['type']
        handler = self._handlers.get(session_type)
        
        if not handler:
            logger.warning(f"[SessionManager] 未找到会话处理器: {session_type}")
            return None
            
        return await handler(session_id, message, session, **context)

    def match_session(self, session_id: str, target_type: str) -> bool:
        """
        检查会话是否匹配指定类型（最佳实践辅助方法）
        
        逻辑：
        1. 获取会话（不续期）
        2. 检查是否存在且类型匹配
        3. 如果匹配，执行续期
        
        Args:
            session_id: 会话ID
            target_type: 期望的会话类型
            
        Returns:
            bool: 是否匹配（如果匹配，会话已自动续期）
        """
        # 1. 获取但不续期，避免干扰其他插件会话
        session = self.get_session(session_id, renew=False)
        
        # 2. 检查匹配
        if not session or session.get('type') != target_type:
            return False
            
        # 3. 匹配成功，执行续期
        self.get_session(session_id, renew=True)
        return True
    
    def cleanup_expired(self) -> int:
        """
        清理所有过期会话
        
        Returns:
            清理的会话数量
        """
        now = datetime.now()
        expired = [
            sid for sid, sess in self.sessions.items()
            if now > sess['expires_at']
        ]
        for sid in expired:
            self.end_session(sid)
        
        if expired:
            logger.info(f"[SessionManager] 清理过期会话 - 数量={len(expired)}")
        
        return len(expired)
    
    def get_all_sessions(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有活跃会话
        
        Returns:
            会话字典
        """
        return self.sessions.copy()
    
    def get_session_count(self) -> int:
        """
        获取活跃会话数量
        
        Returns:
            会话数量
        """
        return len(self.sessions)
    
    def has_session(self, session_id: str) -> bool:
        """
        检查会话是否存在且未过期
        
        Args:
            session_id: 会话ID
        
        Returns:
            是否存在
        """
        session = self.get_session(session_id, renew=False, auto_cleanup=False)
        return session is not None
    
    def get_step_history(self, session_id: str) -> List[int]:
        """
        获取会话的步骤历史
        
        Args:
            session_id: 会话ID
        
        Returns:
            步骤历史列表
        """
        session = self.get_session(session_id, renew=False)
        if session:
            return session.get('step_history', [])
        return []
    
    def back_to_previous_step(self, session_id: str) -> Optional[int]:
        """
        返回到上一个步骤
        
        Args:
            session_id: 会话ID
        
        Returns:
            上一个步骤值，如果没有历史则返回 None
        """
        session = self.get_session(session_id)
        if not session:
            return None
        
        history = session.get('step_history', [])
        if history:
            previous_step = history.pop()
            session['step'] = previous_step
            logger.debug(f"[SessionManager] 返回上一步 - session_id={session_id}, step={previous_step}")
            return previous_step
        
        return None
