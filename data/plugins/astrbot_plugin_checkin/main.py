"""
签到系统插件
支持每日签到、连续签到奖励、补签、排行榜等功能
"""
from typing import Any
import os
from pathlib import Path
from datetime import datetime, date, timedelta
import random

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.core.message.components import Plain
from astrbot.core import CallbackRouter, callback_handler, auto_stop_event

# 导入通用配额系统
import sys
plugin_root = Path(__file__).parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

try:
    from common.database_manager import DatabaseManager
    from common.points_manager import PointsManager
    from common.platform_capabilities import get_platform_capabilities
    from common.message_editor import MessageEditor
    from common.error_handler import PluginErrorHandler
    from common.loading_indicator import LoadingIndicator
    from common.input_validator import InputValidator
    from common.pagination import Pagination
    from common.help_builder import HelpBuilder
    from common.lark_message_helper import LarkMessageHelper
    from common.command_handler import auto_stop_command
    from common.user_utils import get_unified_user_id
    from common.message_formatter import get_separator
    QUOTA_SYSTEM_AVAILABLE = True
except ImportError as e:
    QUOTA_SYSTEM_AVAILABLE = False
    LarkMessageHelper = None
    logger.error(f"[Checkin] 通用模块不可用: {e}")
    def get_unified_user_id(event):
        return event.get_sender_id()

from .checkin_manager import CheckinManager
from .handlers.admin_handler import AdminHandler
from .handlers.session_handler import SessionHandler
from .handlers.step_manager import CheckinStepManager


@register("checkin", "AstrBot Team", "签到系统插件 - 支持跨平台交互", "2.0.0")
class CheckinPlugin(Star):
    """签到系统插件 - 统一跨平台交互设计"""
    
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context, config)
        self.context = context
        self.plugin_config = config or {}
        
        # 加载插件配置
        self._load_plugin_config()
        
        # 加载管理员配置
        self.admins = self.plugin_config.get("admins", [])
        
        # 用于跟踪正在处理的命令，避免重复处理
        self._processing_commands = set()
        
        # 初始化步骤管理器
        self.step_manager = CheckinStepManager()
        logger.info("[Checkin] 步骤管理器初始化完成")
        
        # 注册回调路由
        CallbackRouter.register("checkin", self.handle_callback, plugin_instance=self)
        logger.info("[Checkin] 已注册回调路由: checkin")
        
        # 初始化通用配额系统
        self.points_manager = None
        self.db = None
        self.system_available = QUOTA_SYSTEM_AVAILABLE
        
        if self.system_available:
            try:
                # 获取数据路径
                astrbot_config = self.context.get_config()
                data_path = astrbot_config.get("data_path", "data")
                
                # 初始化统一数据库
                quota_db_path = os.path.join(data_path, "quota_system.db")
                self.db = DatabaseManager(quota_db_path)
                self.points_manager = PointsManager(self.db)
                
                logger.info("[Checkin] 统一数据库初始化完成")
            except Exception as e:
                logger.error(f"[Checkin] 统一数据库初始化失败: {e}")
                self.system_available = False
        
        # 初始化签到管理器（使用统一数据库）
        if self.system_available:
            self.checkin_manager = CheckinManager(
                db_manager=self.db,  # 使用统一的 quota_system.db
                points_manager=self.points_manager,
                config=self._build_checkin_config()
            )
            
            # 初始化会话处理器（传递 plugin 引用）
            self.session_handler = SessionHandler(
                checkin_manager=self.checkin_manager,
                config=self._build_checkin_config(),
                plugin=self  # 传递自身引用，用于平台能力检测
            )
            
            logger.info("[Checkin] 签到插件初始化完成")
        else:
            self.checkin_manager = None
            self.session_handler = None
            logger.warning("[Checkin] 签到插件初始化失败：统一数据库不可用")
    
    def _load_plugin_config(self):
        """加载插件配置"""
        defaults = {
            # 基础奖励设置
            'base_points': 10,
            'random_points_min': 1,
            'random_points_max': 20,
            # 幸运签到设置
            'lucky_chance': 0.1,
            'lucky_multiplier': 2.0,
            # 连续签到倍数
            'streak_bonus_3': 1.2,
            'streak_bonus_7': 1.5,
            'streak_bonus_15': 1.8,
            'streak_bonus_30': 2.0,
            # 全勤奖励
            'perfect_month_bonus': 200,
            # 补签设置
            'makeup_enabled': True,
            'makeup_max_days': 7,
            'makeup_cost': 50
        }
        for key, default in defaults.items():
            if key not in self.plugin_config:
                self.plugin_config[key] = default
        
        logger.info(f"[Checkin] 插件配置加载完成: base_points={self.plugin_config['base_points']}, random={self.plugin_config['random_points_min']}-{self.plugin_config['random_points_max']}")
    
    def _build_checkin_config(self) -> dict:
        """构建签到管理器所需的配置格式"""
        return {
            'rewards': {
                'base_points': self.plugin_config.get('base_points', 10),
                'random_points_min': self.plugin_config.get('random_points_min', 1),
                'random_points_max': self.plugin_config.get('random_points_max', 20),
                'lucky_chance': self.plugin_config.get('lucky_chance', 0.1),
                'lucky_multiplier': self.plugin_config.get('lucky_multiplier', 2.0),
                'perfect_month_bonus': self.plugin_config.get('perfect_month_bonus', 200),
                'streak_bonus': {
                    '3': self.plugin_config.get('streak_bonus_3', 1.2),
                    '7': self.plugin_config.get('streak_bonus_7', 1.5),
                    '15': self.plugin_config.get('streak_bonus_15', 1.8),
                    '30': self.plugin_config.get('streak_bonus_30', 2.0)
                }
            },
            'makeup': {
                'enabled': self.plugin_config.get('makeup_enabled', True),
                'max_days': self.plugin_config.get('makeup_max_days', 7),
                'cost': self.plugin_config.get('makeup_cost', 50)
            }
        }
    
    def _check_system_available(self, event: AstrMessageEvent):
        """检查系统是否可用"""
        if not self.system_available:
            return False, "❌ 签到系统未初始化，请联系管理员"
        return True, None
    
    def _is_admin(self, user_id: str) -> bool:
        """检查用户是否为管理员"""
        return user_id in self.admins
    
    # ==================== 用户命令 ====================
    
    @filter.command("签")
    @auto_stop_command  # 自动停止事件传播
    async def checkin_cmd(self, event: AstrMessageEvent):
        """签到（多轮对话）"""
        available, msg = self._check_system_available(event)
        if not available:
            yield event.plain_result(msg)
            return
        
        user_id = get_unified_user_id(event)
        session_id = event.get_session_id()
        
        # 检测平台能力
        capabilities = get_platform_capabilities(event, "Checkin")
        
        # 不使用 _processing_commands 标记，因为会导致会话模式下第一条消息被跳过
        # self._processing_commands.add(session_id)
        # logger.debug(f"[Checkin] checkin_cmd: 标记会话正在处理命令 - session_id={session_id}")
        
        # 显示加载提示
        loading_msg_id = await LoadingIndicator.show(event, 'process')
        
        try:
            # 检查今天是否已签到
            from datetime import date
            today = date.today()
            
            if self.checkin_manager._is_checked_in_today(user_id, today):
                # 已签到，显示菜单
                result = await self.session_handler.start_checkin_menu(
                    user_id, session_id, show_already_checked=True, capabilities=capabilities
                )
                
                # 隐藏加载提示
                await LoadingIndicator.hide(event, loading_msg_id)
                
                # 获取会话上下文
                session = self.session_handler._get_session(session_id)
                
                # 准备消息内容
                if isinstance(result, tuple):
                    message_text, keyboard = result
                else:
                    message_text = result
                    keyboard = None
                
                # 飞书平台：使用 LarkMessageHelper
                if LarkMessageHelper and LarkMessageHelper.should_use_lark_helper(event):
                    message_id = await LarkMessageHelper.send_and_track(
                        event, message_text, session, auto_cleanup=False
                    )
                    if message_id:
                        logger.debug(f"[Checkin] 飞书菜单消息发送成功: {message_id}")
                        return  # 不需要 event.stop_event()，装饰器已处理
                    else:
                        logger.debug("[Checkin] 飞书发送失败，降级到普通方式")
                
                # 其他平台或降级方式
                # 不需要手动调用 event.stop_event()，装饰器已处理
                if keyboard:
                    yield event.chain_result([Plain(message_text), keyboard])
                else:
                    yield event.plain_result(message_text)
            else:
                # 未签到，直接签到
                try:
                    result = await self.checkin_manager.daily_checkin(user_id)
                    # 签到成功后，启动会话并显示菜单
                    menu_result = await self.session_handler.start_checkin_menu(
                        user_id, session_id, capabilities=capabilities
                    )
                    
                    # 隐藏加载提示
                    await LoadingIndicator.hide(event, loading_msg_id)
                    
                    # 获取会话上下文
                    session = self.session_handler._get_session(session_id)
                    
                    # 处理菜单结果
                    if isinstance(menu_result, tuple):
                        menu, keyboard = menu_result
                        full_message = result + "\n\n" + menu
                    else:
                        full_message = result + "\n\n" + menu_result
                        keyboard = None
                    
                    # 飞书平台：使用 LarkMessageHelper
                    if LarkMessageHelper and LarkMessageHelper.should_use_lark_helper(event):
                        message_id = await LarkMessageHelper.send_and_track(
                            event, full_message, session, auto_cleanup=False
                        )
                        if message_id:
                            logger.debug(f"[Checkin] 飞书签到消息发送成功: {message_id}")
                            return  # 不需要 event.stop_event()，装饰器已处理
                        else:
                            logger.debug("[Checkin] 飞书发送失败，降级到普通方式")
                    
                    # 其他平台或降级方式
                    # 不需要手动调用 event.stop_event()，装饰器已处理
                    if keyboard:
                        yield event.chain_result([Plain(full_message), keyboard])
                    else:
                        yield event.plain_result(full_message)
                except Exception as e:
                    # 隐藏加载提示
                    await LoadingIndicator.hide(event, loading_msg_id)
                    # 使用统一错误处理
                    error_msg = PluginErrorHandler.handle_exception(e, "签到", "Checkin")
                    yield event.plain_result(error_msg)
        except Exception as e:
            # 隐藏加载提示
            await LoadingIndicator.hide(event, loading_msg_id)
            # 使用统一错误处理
            error_msg = PluginErrorHandler.handle_exception(e, "签到命令", "Checkin")
            yield event.plain_result(error_msg)
        
        # 不需要手动 event.stop_event()，装饰器已处理
    
    @filter.command("帮助")
    @auto_stop_command  # 自动停止事件传播
    async def checkin_help_cmd(self, event: AstrMessageEvent):
        """显示帮助信息"""
        user_id = get_unified_user_id(event)
        is_admin = self._is_admin(user_id)
        capabilities = get_platform_capabilities(event, "Checkin")
        
        # 获取配置
        base_points = self.config.get("rewards", {}).get("base_points", 10)
        random_min = self.config.get("rewards", {}).get("random_points_min", 1)
        random_max = self.config.get("rewards", {}).get("random_points_max", 20)
        makeup_cost = self.config.get("makeup", {}).get("cost", 50)
        
        # 使用 HelpBuilder 构建帮助信息
        help_builder = HelpBuilder(
            plugin_name="签到系统",
            description="每日签到赚积分，连续签到奖励更丰厚！"
        )
        
        # 添加命令
        help_builder.add_command(
            "/签", 
            "签到（多轮对话）",
            "今日未签到：直接签到并显示菜单\n    今日已签到：显示功能菜单"
        ).add_command(
            "/帮助",
            "显示此帮助信息"
        )
        
        # 添加功能特性
        help_builder.add_feature(f"基础奖励：{base_points}积分")
        help_builder.add_feature(f"随机奖励：{random_min}-{random_max}积分")
        help_builder.add_feature("连续签到有额外奖励")
        help_builder.add_feature("每月全勤有特殊奖励")
        help_builder.add_feature("有概率触发幸运签到")
        
        # 添加使用示例
        help_builder.add_example(
            "每日签到",
            "/签",
            "✅ 签到成功！获得 15 积分"
        ).add_example(
            "补签昨天",
            "/签 → 选择补签 → 输入'昨天'",
            "✅ 补签成功！消耗 50 积分"
        )
        
        # 添加提示
        help_builder.add_tip("每天只能签到一次")
        help_builder.add_tip("连续签到奖励更丰厚")
        help_builder.add_tip(f"补签消耗：{makeup_cost}积分/次，可补签最近7天")
        help_builder.add_tip("积分可用于补签或其他功能")
        
        if is_admin:
            help_builder.add_tip("👑 管理员可在 /管理 面板中配置签到系统")
        
        # 构建帮助信息
        help_text, keyboard = help_builder.build(capabilities)
        
        yield event.plain_result(help_text)
    
    # ==================== 按钮回调处理 ====================
    
    @filter.command("callback")
    @callback_handler("checkin")
    @auto_stop_event
    async def handle_callback(self, event: AstrMessageEvent, data: str = ""):
        """
        处理按钮回调（按钮模式）
        
        使用回调路由器，只接收 checkin: 开头的回调
        装饰器已经过滤了前缀，这里只需要提取 action
        """
        # 从消息中提取回调数据并去掉前缀
        raw = event.message_str.strip()
        parts = raw.split(" ", 1)
        if len(parts) < 2:
            return
        callback_data = parts[1].strip()
        action = callback_data.replace("checkin:", "")
        
        logger.debug(f"[Checkin] 收到回调: checkin:{action}")
        
        # 检查系统可用性
        available, msg = self._check_system_available(event)
        if not available:
            yield event.plain_result(msg)
            return  # 不需要 event.stop_event()，装饰器已处理
        
        user_id = get_unified_user_id(event)
        session_id = event.get_session_id()
        
        try:
            if action == "home":
                # 返回首页 - 显示主菜单
                capabilities = get_platform_capabilities(event, "Checkin")
                result = await self.session_handler.start_checkin_menu(
                    user_id, session_id, show_already_checked=True, capabilities=capabilities
                )
                
                # 获取会话上下文（用于消息自动清理）
                session = self.session_handler._get_session(session_id)
                
                # 使用消息编辑器处理（启用自动清理）
                if isinstance(result, tuple):
                    message, keyboard = result
                    async for ret in MessageEditor.edit_or_send(
                        event, message, keyboard,
                        session_context=session,  # 传入会话上下文以启用自动清理
                        auto_cleanup=True
                    ):
                        yield ret
                else:
                    yield event.plain_result(result)
                
            elif action == "exit":
                # 退出会话
                self.session_handler._end_session(session_id)
                # 优雅退出：编辑原消息，移除按钮，显示退出提示
                async for ret in MessageEditor.edit_or_send(event, "✅ 已退出签到会话"):
                    yield ret
            
            elif action.startswith("input:"):
                # 快捷输入回调
                input_value = action.replace("input:", "")
                logger.debug(f"[Checkin] 快捷输入: {input_value}")
                
                # 获取会话并处理输入
                session = self.session_handler._get_session(session_id)
                if session:
                    # 处理会话消息（模拟用户输入）
                    result = await self.session_handler.handle_session_message(
                        user_id, session_id, input_value
                    )
                    
                    if result:
                        # 处理返回值（可能是字符串或元组）
                        if isinstance(result, tuple):
                            message_text, keyboard = result
                            async for ret in MessageEditor.edit_or_send(
                                event, message_text, keyboard,
                                session_context=session, auto_cleanup=True
                            ):
                                yield ret
                        else:
                            async for ret in MessageEditor.edit_or_send(
                                event, result,
                                session_context=session, auto_cleanup=True
                            ):
                                yield ret
                    else:
                        yield event.plain_result("❌ 处理失败")
                else:
                    yield event.plain_result("❌ 会话已过期，请重新开始")
                
            elif action == "makeup":
                # 进入补签流程
                session = self.session_handler._get_session(session_id)
                if not session:
                    self.session_handler._create_session(session_id, 'checkin_menu', user_id)
                    session = self.session_handler._get_session(session_id)  # 重新获取创建的会话
                
                self.session_handler._update_session(
                    session_id, 
                    step=CheckinStepManager.Step.INPUT_REQUIRED, 
                    data={'action': 'makeup'}
                )
                logger.debug(f"[Checkin] 进入步骤: {self.step_manager.get_step_name(CheckinStepManager.Step.INPUT_REQUIRED)}")
                
                # 检测平台能力
                capabilities = get_platform_capabilities(event, "Checkin")
                is_button_mode = capabilities.get('supports_buttons', False)
                
                # 构建消息
                platform = capabilities.get('platform_name', '')
                separator = get_separator(platform)
                result = f"{separator}\n"
                result += "📝 补签功能\n"
                result += f"{separator}\n\n"
                
                if is_button_mode:
                    # 按钮模式：简洁提示
                    result += "💡 点击下方按钮快速补签，或手动输入日期"
                else:
                    # 会话模式：详细说明
                    result += "请输入要补签的日期：\n\n"
                    result += "📅 支持格式：\n"
                    result += "  • 1 - 昨天\n"
                    result += "  • 2 - 前天\n"
                    result += "  • 3 - 大前天\n"
                    result += "  • 2024-01-15"
                    result += f"\n\n{separator}\n"
                    result += self.session_handler._get_navigation_hint(step=CheckinStepManager.Step.INPUT_REQUIRED) + "\n"
                    result += f"⏱️ 请在 {self.session_handler.SESSION_TIMEOUT_MINUTES} 分钟内输入"
                
                # 快捷输入按钮（仅按钮模式）
                quick_inputs = [
                    {"text": "📅 昨天", "callback_data": "checkin:input:昨天"},
                    {"text": "📅 前天", "callback_data": "checkin:input:前天"},
                    {"text": "📅 大前天", "callback_data": "checkin:input:大前天"}
                ]
                
                # 使用响应构建器
                from .handlers.response_builder import CheckinResponseBuilder
                builder = CheckinResponseBuilder(capabilities)
                message, keyboard = builder.build_submenu_response(
                    result, 
                    step=CheckinStepManager.Step.INPUT_REQUIRED, 
                    quick_inputs=quick_inputs
                )
                
                async for ret in MessageEditor.edit_or_send(
                    event, message, keyboard,
                    session_context=session, auto_cleanup=True
                ):
                    yield ret
                
            elif action == "history":
                # 查看签到记录
                capabilities = get_platform_capabilities(event, "Checkin")
                is_button_mode = capabilities.get('supports_buttons', False)
                
                result = await self.checkin_manager.get_checkin_history(user_id)
                
                # 只在会话模式下显示导航提示
                platform = capabilities.get('platform_name', '')
                separator = get_separator(platform)
                if not is_button_mode:
                    result += f"\n\n{separator}\n"
                    result += self.session_handler._get_navigation_hint(step=CheckinStepManager.Step.MAIN_MENU)
                
                # 使用响应构建器
                from .handlers.response_builder import CheckinResponseBuilder
                builder = CheckinResponseBuilder(capabilities)
                message, keyboard = builder.build_detail_response(
                    result, 
                    step=CheckinStepManager.Step.MAIN_MENU
                )
                
                # 获取会话上下文（用于消息自动清理）
                session = self.session_handler._get_session(session_id)
                
                async for ret in MessageEditor.edit_or_send(
                    event, message, keyboard,
                    session_context=session, auto_cleanup=True
                ):
                    yield ret
                
            elif action == "leaderboard":
                # 查看签到排行
                capabilities = get_platform_capabilities(event, "Checkin")
                is_button_mode = capabilities.get('supports_buttons', False)
                platform = capabilities.get('platform_name', '')
                separator = get_separator(platform)
                
                result = await self.checkin_manager.get_leaderboard()
                
                # 只在会话模式下显示导航提示
                if not is_button_mode:
                    result += f"\n\n{separator}\n"
                    result += self.session_handler._get_navigation_hint(step=CheckinStepManager.Step.MAIN_MENU)
                
                # 使用响应构建器
                from .handlers.response_builder import CheckinResponseBuilder
                builder = CheckinResponseBuilder(capabilities)
                message, keyboard = builder.build_detail_response(
                    result, 
                    step=CheckinStepManager.Step.MAIN_MENU
                )
                
                # 获取会话上下文（用于消息自动清理）
                session = self.session_handler._get_session(session_id)
                
                async for ret in MessageEditor.edit_or_send(
                    event, message, keyboard,
                    session_context=session, auto_cleanup=True
                ):
                    yield ret
            
            else:
                logger.warning(f"[Checkin] 未知的回调操作: {action}")
                
        except Exception as e:
            logger.error(f"[Checkin] 处理回调失败: {e}", exc_info=True)
            yield event.plain_result("❌ 操作失败，请稍后重试")
    
    # ==================== 会话处理 ====================
    
    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """处理会话中的消息"""
        # 如果事件已经有结果，不处理
        if event.get_result():
            logger.debug(f"[Checkin] on_message: 跳过 - has_result=True")
            return
        
        # 如果是命令（包括回调命令），不处理
        message_str = event.message_str or ""
        if message_str.startswith("/"):
            logger.debug(f"[Checkin] on_message: 跳过 - 是命令: {message_str}")
            return
        
        # 特别跳过回调消息（某些平台可能不以 / 开头）
        if message_str.startswith("callback "):
            logger.debug(f"[Checkin] on_message: 跳过 - 是回调: {message_str}")
            return
        
        # 检查是否有活跃的签到会话
        user_id = get_unified_user_id(event)
        session_id = event.get_session_id()
        
        # 检查是否有会话
        session = self.session_handler._get_session(session_id)
        if not session:
            logger.debug(f"[Checkin] on_message: 没有会话 - session_id={session_id}")
            return  # 没有会话，不处理
        
        # 特殊处理：如果会话在步骤0（主菜单），且消息是命令关键词，跳过
        # 这是为了处理某些平台（如Telegram）在命令处理后会将命令消息再次传递的情况
        current_step = session.get('step', 0)
        step_history = session.get('step_history', [])
        
        # 如果在主菜单且没有步骤历史，说明会话刚创建
        # 如果消息是命令关键词，则跳过（这是命令消息的重复传递）
        if (self.step_manager.is_main_menu(current_step) and 
            len(step_history) == 0 and 
            message_str in ['签', 'checkin']):
            logger.debug(f"[Checkin] on_message: 跳过 - 会话刚创建且是命令关键词 - message={message_str}")
            return
        
        logger.info(f"[Checkin] on_message: 检测到会话 - session_id={session_id}, message={event.message_str}")
        
        # 有会话，处理消息并阻止事件传播
        # 检查系统是否可用
        available, msg = self._check_system_available(event)
        if not available:
            logger.info(f"[Checkin] on_message: 系统不可用，停止事件")
            yield event.plain_result(msg)
            event.stop_event()
            return
        
        message = event.message_str or ""
        
        # 处理会话消息
        result = await self.session_handler.handle_session_message(
            user_id, session_id, message
        )
        
        if result:
            logger.info(f"[Checkin] on_message: 处理完成，停止事件传播")
            
            # 获取会话对象
            session = self.session_handler._get_session(session_id)
            platform_name = (event.get_platform_name() or "").lower()
            
            # 检查是否是退出命令
            is_exiting = session and session.get('_exiting', False) if session else False
            
            # 如果是退出命令，使用 LarkMessageHelper 清理消息
            if is_exiting:
                if LarkMessageHelper and LarkMessageHelper.should_use_lark_helper(event):
                    await LarkMessageHelper.cleanup_on_exit(event, session)
                    logger.info(f"[Checkin] on_message: 退出会话，已清理消息")
                # 清理消息后，删除会话
                self.session_handler._end_session(session_id)
                logger.debug(f"[Checkin] on_message: 会话已删除 - session_id={session_id}")
                event.stop_event()
                return
            
            # 准备消息内容
            if isinstance(result, tuple):
                message_text, keyboard = result
            else:
                message_text = result
                keyboard = None
            
            # 飞书平台：使用 LarkMessageHelper
            if LarkMessageHelper and LarkMessageHelper.should_use_lark_helper(event):
                message_id = await LarkMessageHelper.send_and_track(
                    event, message_text, session, auto_cleanup=True
                )
                if message_id:
                    logger.info(f"[Checkin] on_message: 飞书消息发送完成: {message_id}")
                    event.stop_event()
                    return
                else:
                    logger.debug("[Checkin] 飞书发送失败，降级到普通方式")
            
            # 其他平台或降级方式
            if keyboard:
                yield event.chain_result([Plain(message_text), keyboard])
            else:
                yield event.plain_result(message_text)
            
            event.stop_event()
            logger.info(f"[Checkin] on_message: stop_event() 已调用，result_type={event.get_result().result_type if event.get_result() else None}")
            return
        else:
            logger.warning(f"[Checkin] on_message: 会话处理返回空结果")
    
    # ==================== 管理员命令（集成到配额管理插件） ====================
    
    @filter.command("签到管理")
    async def checkin_admin_cmd(self, event: AstrMessageEvent):
        """管理员签到管理（临时命令，建议集成到 /管理）"""
        available, msg = self._check_system_available(event)
        if not available:
            yield event.plain_result(msg)
            return
        
        user_id = get_unified_user_id(event)
        if not self._is_admin(user_id):
            yield event.plain_result("❌ 权限不足，仅管理员可用")
            return
        
        result = "👑 签到管理面板\n\n"
        result += "请选择操作：\n\n"
        result += "1. 查看签到统计\n"
        result += "2. 修改基础奖励\n"
        result += "3. 修改随机奖励范围\n"
        result += "4. 修改补签消耗\n"
        result += "5. 重置用户签到\n"
        result += "0. 退出\n\n"
        result += "💡 建议：将此功能集成到 /管理 命令中"
        
        yield event.plain_result(result)
