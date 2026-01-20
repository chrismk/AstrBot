"""
统一的导航命令处理器

提供标准化的导航命令处理，避免每个插件重复实现导航逻辑。

核心功能：
- 统一处理导航命令（h-首页、b-返回、0-退出）
- 自动管理导航状态和步骤历史
- 支持自定义导航回调
- 集成 SessionManager 和 NavigationHint

使用示例：
    from common import NavigationHandler, SessionManager
    
    # 初始化
    session_manager = SessionManager(timeout_minutes=1)
    nav_handler = NavigationHandler(session_manager)
    
    # 注册导航回调
    async def on_home(session_id, session):
        return "返回首页"
    
    async def on_back(session_id, session):
        return "返回上级"
    
    async def on_exit(session_id, session):
        return "退出成功"
    
    nav_handler.register_callbacks(
        on_home=on_home,
        on_back=on_back,
        on_exit=on_exit
    )
    
    # 处理导航命令
    is_handled, result = await nav_handler.handle(session_id, message)
    if is_handled:
        return result
"""

from typing import Dict, Any, Optional, Callable, Tuple
from astrbot.api import logger


class NavigationHandler:
    """统一的导航命令处理器"""
    
    # 导航命令定义
    CMD_HOME = ['h', 'H', '首页', 'home']
    CMD_BACK = ['b', 'B', '返回', 'back']
    CMD_EXIT = ['0', '退出', 'exit', 'q', 'Q', 'quit']
    CMD_PREV = ['p', 'P', '上页', 'prev']
    CMD_NEXT = ['n', 'N', '下页', 'next']
    CMD_SWITCH = ['s', 'S', '切换', 'switch']  # 切换类型/模式
    
    def __init__(self, session_manager=None):
        """
        初始化导航处理器
        
        Args:
            session_manager: SessionManager 实例（可选）
        """
        self.session_manager = session_manager
        self._callbacks: Dict[str, Callable] = {}
        logger.debug("[NavigationHandler] 初始化完成")
    
    def register_callbacks(
        self,
        on_home: Optional[Callable] = None,
        on_back: Optional[Callable] = None,
        on_exit: Optional[Callable] = None
    ):
        """
        注册导航回调函数
        
        Args:
            on_home: 首页回调，签名: async def on_home(session_id, session) -> Any
            on_back: 返回回调，签名: async def on_back(session_id, session) -> Any
            on_exit: 退出回调，签名: async def on_exit(session_id, session) -> Any
        """
        if on_home:
            self._callbacks['home'] = on_home
        if on_back:
            self._callbacks['back'] = on_back
        if on_exit:
            self._callbacks['exit'] = on_exit
        
        logger.debug(f"[NavigationHandler] 注册回调: {list(self._callbacks.keys())}")
    
    @staticmethod
    def is_session_command(message: str) -> bool:
        """
        判断是否是会话命令（包括导航命令、翻页命令和序号）
        
        用于检测用户输入是否为会话相关命令，当会话不存在时可以提示用户。
        
        Args:
            message: 用户输入
        
        Returns:
            是否是会话命令
        
        示例：
            if not session and NavigationHandler.is_session_command(message):
                return "❌ 会话已过期，请重新开始"
        """
        message = message.strip()
        
        # 检查是否为导航命令
        if (message in NavigationHandler.CMD_HOME or
            message in NavigationHandler.CMD_BACK or
            message in NavigationHandler.CMD_EXIT or
            message in NavigationHandler.CMD_PREV or
            message in NavigationHandler.CMD_NEXT):
            return True
        
        # 检查是否为数字（序号）
        if message.isdigit():
            return True
        
        return False
    
    def is_navigation_command(self, message: str) -> bool:
        """
        判断是否是导航命令（不包括翻页命令）
        
        Args:
            message: 用户输入
        
        Returns:
            是否是导航命令
        """
        message = message.strip()
        return (
            message in self.CMD_HOME or
            message in self.CMD_BACK or
            message in self.CMD_EXIT
        )
    
    def get_command_type(self, message: str) -> Optional[str]:
        """
        获取命令类型
        
        Args:
            message: 用户输入
        
        Returns:
            命令类型（'home'/'back'/'exit'），如果不是导航命令则返回 None
        """
        message = message.strip()
        if message in self.CMD_HOME:
            return 'home'
        elif message in self.CMD_BACK:
            return 'back'
        elif message in self.CMD_EXIT:
            return 'exit'
        return None
    
    async def handle(
        self, 
        session_id: str, 
        message: str,
        session: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Any]:
        """
        处理导航命令
        
        Args:
            session_id: 会话ID
            message: 用户输入
            session: 会话对象（可选，如果不提供会自动从 session_manager 获取）
        
        Returns:
            (is_handled, result) - 是否处理、处理结果
            - is_handled: True 表示是导航命令并已处理，False 表示不是导航命令
            - result: 处理结果（字符串或其他返回值）
        
        示例：
            is_handled, result = await nav_handler.handle(session_id, "h")
            if is_handled:
                return result  # 返回首页
        """
        # 判断是否是导航命令
        if not self.is_navigation_command(message):
            return False, None
        
        # 获取命令类型
        cmd_type = self.get_command_type(message)
        if not cmd_type:
            return False, None
        
        # 获取会话
        if session is None and self.session_manager:
            session = self.session_manager.get_session(session_id, renew=True)
        
        if not session:
            logger.warning(f"[NavigationHandler] 会话不存在 - session_id={session_id}")
            return True, "❌ 会话已过期，请重新开始"
        
        logger.debug(f"[NavigationHandler] 处理导航命令 - session_id={session_id}, cmd={cmd_type}")
        
        # 调用对应的回调
        callback = self._callbacks.get(cmd_type)
        if callback:
            try:
                result = await callback(session_id, session)
                return True, result
            except Exception as e:
                logger.error(f"[NavigationHandler] 回调执行失败 - cmd={cmd_type}, error={e}", exc_info=True)
                return True, f"❌ 导航失败: {e}"
        else:
            # 默认处理
            return True, await self._default_handle(session_id, session, cmd_type)
    
    async def _default_handle(
        self, 
        session_id: str, 
        session: Dict[str, Any], 
        cmd_type: str
    ) -> str:
        """
        默认导航处理（当没有注册回调时）
        
        Args:
            session_id: 会话ID
            session: 会话对象
            cmd_type: 命令类型
        
        Returns:
            处理结果
        """
        if cmd_type == 'home':
            # 返回首页：重置步骤为0
            if self.session_manager:
                self.session_manager.update_session(session_id, step=0)
            else:
                session['step'] = 0
            logger.debug(f"[NavigationHandler] 返回首页 - session_id={session_id}")
            return "🏠 已返回首页"
        
        elif cmd_type == 'back':
            # 返回上级：使用步骤历史
            if self.session_manager:
                previous_step = self.session_manager.back_to_previous_step(session_id)
            else:
                history = session.get('step_history', [])
                if history:
                    previous_step = history.pop()
                    session['step'] = previous_step
                else:
                    previous_step = None
            
            if previous_step is not None:
                logger.debug(f"[NavigationHandler] 返回上级 - session_id={session_id}, step={previous_step}")
                return "⬅️ 已返回上级"
            else:
                logger.debug(f"[NavigationHandler] 已在主菜单 - session_id={session_id}")
                return "💡 当前已在主菜单"
        
        elif cmd_type == 'exit':
            # 退出：结束会话
            if self.session_manager:
                self.session_manager.end_session(session_id)
            logger.debug(f"[NavigationHandler] 退出会话 - session_id={session_id}")
            # 标记退出状态（用于消息清理）
            session['_exiting'] = True
            return "✅ 已退出会话"
        
        return "❌ 未知的导航命令"
    
    def validate_navigation(
        self, 
        message: str, 
        session: Dict[str, Any],
        allow_home: bool = True,
        allow_back: bool = True,
        allow_exit: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        验证导航命令是否允许
        
        Args:
            message: 用户输入
            session: 会话对象
            allow_home: 是否允许返回首页
            allow_back: 是否允许返回上级
            allow_exit: 是否允许退出
        
        Returns:
            (is_valid, error_message) - 是否有效、错误消息
        
        使用场景：
            在某些特殊步骤中，可能需要禁止某些导航命令
        """
        cmd_type = self.get_command_type(message)
        if not cmd_type:
            return True, None  # 不是导航命令，通过验证
        
        current_step = session.get('step', 0)
        
        # 检查是否允许
        if cmd_type == 'home' and not allow_home:
            return False, "💡 当前步骤不支持返回首页"
        
        if cmd_type == 'back' and not allow_back:
            return False, "💡 当前步骤不支持返回上级"
        
        if cmd_type == 'exit' and not allow_exit:
            return False, "💡 当前步骤不支持退出"
        
        # 特殊验证：在主菜单时不允许返回
        if cmd_type == 'back' and current_step == 0:
            return False, "💡 当前已在主菜单"
        
        return True, None
    
    @staticmethod
    def should_show_home(step: int) -> bool:
        """
        判断是否应该显示首页导航
        
        Args:
            step: 当前步骤
        
        Returns:
            是否显示首页
        """
        return step >= 2
    
    @staticmethod
    def should_show_back(step: int) -> bool:
        """
        判断是否应该显示返回导航
        
        Args:
            step: 当前步骤
        
        Returns:
            是否显示返回
        """
        return step >= 1
    
    def get_available_commands(self, session: Dict[str, Any]) -> list:
        """
        获取当前可用的导航命令
        
        Args:
            session: 会话对象
        
        Returns:
            可用命令列表
        """
        step = session.get('step', 0)
        commands = []
        
        if self.should_show_home(step):
            commands.append('h-首页')
        if self.should_show_back(step):
            commands.append('b-返回')
        commands.append('0-退出')
        
        return commands


class NavigationResult:
    """导航处理结果封装"""
    
    def __init__(
        self, 
        is_handled: bool, 
        result: Any = None,
        should_exit: bool = False,
        new_step: Optional[int] = None
    ):
        """
        初始化导航结果
        
        Args:
            is_handled: 是否已处理
            result: 处理结果
            should_exit: 是否应该退出会话
            new_step: 新的步骤值
        """
        self.is_handled = is_handled
        self.result = result
        self.should_exit = should_exit
        self.new_step = new_step
    
    def __bool__(self):
        """支持 if nav_result: 语法"""
        return self.is_handled
