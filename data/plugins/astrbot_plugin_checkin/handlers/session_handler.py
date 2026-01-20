"""
签到插件会话处理器
处理会话模式下的用户交互
"""
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any
from astrbot.api import logger

import sys
from pathlib import Path
plugin_root = Path(__file__).parent.parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

from common.message_formatter import get_separator

# 导入优化模块
try:
    from common.input_validator import InputValidator
    from common.error_handler import PluginErrorHandler
    from common.navigation_hint import NavigationHint
    from common.session_manager import SessionManager
    from common.navigation_handler import NavigationHandler
except ImportError:
    InputValidator = None
    PluginErrorHandler = None
    NavigationHint = None
    SessionManager = None
    NavigationHandler = None
    logger.warning("[SessionHandler] 优化模块不可用")

# 导入响应构建器
from .response_builder import CheckinResponseBuilder
from .step_manager import CheckinStepManager


class SessionHandler:
    """会话处理器 - 支持跨平台交互（基于 SessionManager）"""
    
    # 会话超时时间（分钟）
    SESSION_TIMEOUT_MINUTES = 1
    
    def __init__(self, checkin_manager, config: Dict[str, Any], plugin=None):
        self.checkin_manager = checkin_manager
        self.config = config
        self.plugin = plugin  # 引用主插件，用于获取平台能力
        
        # 初始化步骤管理器
        self.step_manager = CheckinStepManager()
        logger.debug("[SessionHandler] 步骤管理器初始化完成")
        
        # 使用通用会话管理器
        if SessionManager:
            self.session_manager = SessionManager(timeout_minutes=self.SESSION_TIMEOUT_MINUTES)
            # 注册会话处理器
            self.session_manager.register_handler('checkin_menu', self._handle_checkin_menu_step)
            logger.debug("[SessionHandler] 使用通用 SessionManager")
        else:
            # 降级方案：使用本地会话存储
            self.session_manager = None
            self.sessions: Dict[str, Dict[str, Any]] = {}
            logger.warning("[SessionHandler] SessionManager 不可用，使用本地会话管理")
        
        # 使用通用导航处理器
        if NavigationHandler:
            self.nav_handler = NavigationHandler(self.session_manager)
            # 注册导航回调
            self.nav_handler.register_callbacks(
                on_home=self._on_navigate_home,
                on_back=self._on_navigate_back,
                on_exit=self._on_navigate_exit
            )
            logger.debug("[SessionHandler] 使用通用 NavigationHandler")
        else:
            self.nav_handler = None
            logger.warning("[SessionHandler] NavigationHandler 不可用，使用本地导航处理")
    
    def _create_session(self, session_id: str, session_type: str, user_id: str, data: Dict[str, Any] = None, capabilities: Dict = None):
        """创建会话"""
        if self.session_manager:
            # 使用通用 SessionManager
            return self.session_manager.create_session(
                session_id=session_id,
                session_type=session_type,
                user_id=user_id,
                data=data,
                capabilities=capabilities
            )
        else:
            # 降级方案
            now = datetime.now()
            self.sessions[session_id] = {
                'type': session_type,
                'user_id': user_id,
                'step': 0,
                'data': data or {},
                'created_at': now,
                'expires_at': now + timedelta(minutes=self.SESSION_TIMEOUT_MINUTES),
                'step_history': [],
                'capabilities': capabilities
            }
            logger.debug(f"[SessionHandler] 创建会话 - session_id={session_id}")
    
    def _get_session(self, session_id: str, renew: bool = True) -> Optional[Dict[str, Any]]:
        """获取会话（自动清理过期会话）
        
        Args:
            session_id: 会话ID
            renew: 是否续期（延长过期时间）
        """
        if self.session_manager:
            # 使用通用 SessionManager
            return self.session_manager.get_session(session_id, renew=renew)
        else:
            # 降级方案
            session = self.sessions.get(session_id)
            if session:
                if datetime.now() > session['expires_at']:
                    logger.info(f"[SessionHandler] 会话已过期 - session_id={session_id}")
                    self._end_session(session_id)
                    return None
                if renew:
                    session['expires_at'] = datetime.now() + timedelta(minutes=self.SESSION_TIMEOUT_MINUTES)
            return session
    
    def _update_session(self, session_id: str, step: int = None, data: Dict[str, Any] = None):
        """更新会话"""
        if self.session_manager:
            # 使用通用 SessionManager
            self.session_manager.update_session(session_id, step=step, data=data)
        else:
            # 降级方案
            if session_id in self.sessions:
                if step is not None:
                    self.sessions[session_id]['step'] = step
                if data is not None:
                    self.sessions[session_id]['data'].update(data)
    
    def _end_session(self, session_id: str):
        """结束会话"""
        if self.session_manager:
            # 使用通用 SessionManager
            self.session_manager.end_session(session_id)
        else:
            # 降级方案
            if session_id in self.sessions:
                del self.sessions[session_id]
    
    def _get_navigation_hint(self, step: int) -> str:
        """获取导航提示（使用通用模块）
        
        Args:
            step: 当前步骤
                0 = 主菜单（只显示退出）
                1 = 一级子菜单（查看记录/排行榜，显示返回+退出）
                2+ = 二级子菜单（补签输入等，显示首页+返回+退出）
        
        Returns:
            导航提示文本
        """
        if NavigationHint:
            return NavigationHint.get_hint(level=step)
        else:
            # 降级方案：手动生成
            if step == self.step_manager.Step.MAIN_MENU:
                return "💡 0-退出"
            elif step == self.step_manager.Step.VIEW_ONLY:
                return "❌ 无效的输入，请使用导航命令：b-返回 | 0-退出"
            else:
                return "💡 h-首页 | b-返回 | 0-退出"
    
    # ==================== 导航回调 ====================
    
    async def _on_navigate_home(self, session_id: str, session: Dict[str, Any]):
        """返回首页回调"""
        # 重置步骤为主菜单
        self._update_session(session_id, step=CheckinStepManager.Step.MAIN_MENU, data={})
        # 返回主菜单
        capabilities = session.get('capabilities')
        return self._build_menu_response("🏠 已返回首页\n\n", capabilities)
    
    async def _on_navigate_back(self, session_id: str, session: Dict[str, Any]):
        """返回上级回调"""
        step = session.get('step', 0)
        if step > 0:
            # 返回主菜单
            self._update_session(session_id, step=CheckinStepManager.Step.MAIN_MENU, data={})
            capabilities = session.get('capabilities')
            return self._build_menu_response("⬅️ 已返回上级\n\n", capabilities)
        else:
            # 已在主菜单
            return "💡 当前已在主菜单"
    
    async def _on_navigate_exit(self, session_id: str, session: Dict[str, Any]):
        """退出会话回调"""
        # 标记为退出，以便在main.py中删除最后一条消息
        session['_exiting'] = True
        # 注意：不在这里删除会话，让 main.py 在清理消息后删除
        # self._end_session(session_id)  # 延迟到 main.py 清理消息后
        return "✅ 已退出签到会话"
    
    # ==================== 签到菜单会话 ====================
    
    async def _show_main_menu(self, for_buttons: bool = False) -> str:
        """显示主菜单
        
        Args:
            for_buttons: 是否为按钮模式（True=简洁版，False=详细版）
        """
        if for_buttons:
            # 按钮模式：不显示菜单标题，功能完全由按钮提供
            return ""
        else:
            # 会话模式：显示完整的文本菜单
            separator = get_separator()
            result = f"{separator}\n"
            result += "📋 签到功能菜单\n"
            result += f"{separator}\n\n"
            result += "1️⃣ 补签 - 补签漏签日期\n"
            result += "2️⃣ 签到记录 - 查看签到历史\n"
            result += "3️⃣ 签到排行 - 查看排行榜\n\n"
            result += f"{separator}\n"
            result += "0️⃣ 退出\n\n"
            result += f"💡 请输入数字选择功能\n"
            result += f"⏱️ 请在 {self.SESSION_TIMEOUT_MINUTES} 分钟内输入选择"
            return result
    
    def _build_menu_response(self, prefix: str = "", capabilities: Dict = None) -> Tuple[str, Any]:
        """
        构建菜单响应（统一方法）
        
        Args:
            prefix: 菜单前的提示文本（如"✅ 今日已签到"）
            capabilities: 平台能力字典
            
        Returns:
            (消息文本, 键盘或None)
        """
        # 检查是否为按钮模式
        is_button_mode = capabilities and capabilities.get('supports_buttons', False)
        
        # 构建消息
        result = prefix
        if prefix:
            result += "\n\n"
        
        # 根据模式显示不同的菜单（同步调用）
        if is_button_mode:
            # 按钮模式：不显示菜单标题，功能完全由按钮提供
            pass  # 不添加任何菜单文本
        else:
            # 会话模式：详细版
            platform = capabilities.get('platform_name', '') if capabilities else ''
            separator = get_separator(platform)
            result += f"{separator}\n"
            result += "📋 签到功能菜单\n"
            result += f"{separator}\n\n"
            result += "1️⃣ 补签 - 补签漏签日期\n"
            result += "2️⃣ 签到记录 - 查看签到历史\n"
            result += "3️⃣ 签到排行 - 查看排行榜\n\n"
            result += f"{separator}\n"
            result += "0️⃣ 退出\n\n"
            result += f"💡 请输入数字选择功能\n"
            result += f"⏱️ 请在 {self.SESSION_TIMEOUT_MINUTES} 分钟内输入选择"
        
        # 如果提供了平台能力，使用响应构建器
        if capabilities:
            builder = CheckinResponseBuilder(capabilities)
            return builder.build_checkin_menu(result, self.SESSION_TIMEOUT_MINUTES)
        else:
            # 兼容旧版本，返回纯文本
            return result, None
    
    async def start_checkin_menu(self, user_id: str, session_id: str, show_already_checked: bool = False, capabilities: Dict = None) -> Tuple[str, Any]:
        """启动签到菜单会话
        
        Args:
            user_id: 用户ID
            session_id: 会话ID
            show_already_checked: 是否显示"今日已签到"提示
            capabilities: 平台能力字典（可选）
            
        Returns:
            (消息文本, 键盘或None)
        """
        try:
            # 创建会话（保存平台能力）
            self._create_session(session_id, 'checkin_menu', user_id, capabilities=capabilities)
            
            # 使用统一的菜单构建方法
            prefix = "✅ 今日已签到" if show_already_checked else ""
            return self._build_menu_response(prefix, capabilities)
            
        except Exception as e:
            logger.error(f"[SessionHandler] 启动签到菜单失败: {e}", exc_info=True)
            return f"❌ 启动菜单失败: {e}", None
    
    async def _handle_checkin_menu_step(self, user_id: str, session_id: str, message: str):
        """处理签到菜单会话的步骤"""
        try:
            session = self._get_session(session_id)
            if not session or session['type'] != 'checkin_menu':
                return "❌ 会话已过期，请重新开始"
            
            step = session['step']
            message = message.strip()
            
            # ==================== 通用导航 ====================
            # 使用 NavigationHandler 处理导航命令
            if self.nav_handler:
                is_handled, result = await self.nav_handler.handle(session_id, message, session)
                if is_handled:
                    return result
            else:
                # 降级方案：手动处理
                if message in ['0', '退出', 'q', 'Q']:
                    session['_exiting'] = True
                    self._end_session(session_id)
                    return "✅ 已退出签到会话"
                
                if message.lower() in ['h', 'home', '首页']:
                    self._update_session(session_id, step=CheckinStepManager.Step.MAIN_MENU, data={})
                    capabilities = session.get('capabilities')
                    return self._build_menu_response("", capabilities)
                
                if message.lower() in ['b', 'back', '返回']:
                    if step > 0:
                        self._update_session(session_id, step=0, data={})
                        capabilities = session.get('capabilities')
                        return self._build_menu_response("", capabilities)
                    else:
                        return "💡 当前已在主菜单"
            
            # ==================== 功能菜单 ====================
            if step == 0:
                # 选择功能
                try:
                    choice = int(message)
                except ValueError:
                    return "❌ 请输入有效的数字"
                
                if choice == 1:
                    # 补签（进入输入页面）
                    self._update_session(
                        session_id, 
                        step=CheckinStepManager.Step.INPUT_REQUIRED, 
                        data={'action': 'makeup'}
                    )
                    separator = get_separator()
                    result = f"{separator}\n"
                    result += "📝 补签功能\n"
                    result += f"{separator}\n\n"
                    result += "请输入要补签的日期：\n\n"
                    result += "📅 支持格式：\n"
                    result += "  • 1 - 昨天\n"
                    result += "  • 2 - 前天\n"
                    result += "  • 3 - 大前天\n"
                    result += "  • 2024-01-15\n\n"
                    result += f"{separator}\n"
                    result += self._get_navigation_hint(step=CheckinStepManager.Step.INPUT_REQUIRED) + "\n"
                    result += f"⏱️ 请在 {self.SESSION_TIMEOUT_MINUTES} 分钟内输入"
                    return result
                
                elif choice == 2:
                    # 签到记录（进入查看页面）
                    self._update_session(
                        session_id, 
                        step=CheckinStepManager.Step.VIEW_ONLY, 
                        data={'action': 'history'}
                    )
                    result = await self.checkin_manager.get_checkin_history(user_id)
                    # 不结束会话，添加导航提示（1层菜单：显示返回上级）
                    separator = get_separator()
                    result += f"\n\n{separator}\n"
                    result += self._get_navigation_hint(step=CheckinStepManager.Step.VIEW_ONLY)
                    return result
                
                elif choice == 3:
                    # 签到排行（进入查看页面）
                    self._update_session(
                        session_id, 
                        step=CheckinStepManager.Step.VIEW_ONLY, 
                        data={'action': 'leaderboard'}
                    )
                    result = await self.checkin_manager.get_leaderboard()
                    # 不结束会话，添加导航提示（1层菜单：显示返回上级）
                    separator = get_separator()
                    result += f"\n\n{separator}\n"
                    result += self._get_navigation_hint(step=CheckinStepManager.Step.VIEW_ONLY)
                    return result
                
                else:
                    return "❌ 无效的选择，请输入 0-3"
            
            elif self.step_manager.is_readonly_step(step):
                # 处理只读页面（查看记录/排行榜）
                # 这里不需要处理具体输入，因为记录/排行榜是只读的
                # 用户只能使用导航命令（b/h/0），这些由通用导航处理
                # 如果到了这里，说明输入了无效内容
                return "❌ 无效的输入，请使用导航命令：b-返回 | 0-退出"
            
            elif self.step_manager.is_input_step(step):
                # 处理补签日期输入（二级菜单）
                action = session['data'].get('action')
                
                if action == 'makeup':
                    # 支持取消
                    if message in ['0', '取消']:
                        # 返回主菜单
                        self._update_session(session_id, step=CheckinStepManager.Step.MAIN_MENU, data={})
                        capabilities = session.get('capabilities')
                        return self._build_menu_response("", capabilities)
                    
                    # 使用输入验证器验证日期
                    if InputValidator:
                        is_valid, error_msg, date_obj = InputValidator.validate_date(message)
                        if not is_valid:
                            # 返回错误消息，保持在当前步骤
                            return error_msg
                    
                    # 执行补签
                    try:
                        result = await self.checkin_manager.makeup_checkin(user_id, message)
                        # 补签完成后返回主菜单
                        self._update_session(session_id, step=0, data={})
                        
                        # 使用统一的菜单构建方法
                        capabilities = session.get('capabilities')
                        menu_msg, menu_keyboard = self._build_menu_response("", capabilities)
                        
                        # 返回结果 + 菜单
                        return (result + "\n\n" + menu_msg, menu_keyboard)
                    except Exception as e:
                        # 使用统一错误处理
                        if PluginErrorHandler:
                            error_msg = PluginErrorHandler.handle_exception(e, "补签", "Checkin")
                        else:
                            error_msg = f"❌ 补签失败: {e}"
                        
                        # 返回主菜单
                        self._update_session(session_id, step=0, data={})
                        capabilities = session.get('capabilities')
                        menu_msg, menu_keyboard = self._build_menu_response("", capabilities)
                        return (error_msg + "\n\n" + menu_msg, menu_keyboard)
            
        except Exception as e:
            logger.error(f"[SessionHandler] 处理签到菜单步骤失败: {e}", exc_info=True)
            self._end_session(session_id)
            return f"❌ 操作失败: {e}"
    
    # ==================== 会话消息处理 ====================
    
    async def handle_session_message(self, user_id: str, session_id: str, message: str) -> Optional[str]:
        """处理会话中的消息"""
        try:
            session = self._get_session(session_id)
            if not session:
                return None
            
            session_type = session['type']
            
            if session_type == 'checkin_menu':
                return await self._handle_checkin_menu_step(user_id, session_id, message)
            else:
                return None
                
        except Exception as e:
            logger.error(f"[SessionHandler] 处理会话消息失败: {e}", exc_info=True)
            return f"❌ 处理消息失败: {e}"
