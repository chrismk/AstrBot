"""
订阅插件会话处理器
处理按钮模式和会话模式的用户交互
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
import re

try:
    from astrbot.api import logger
    from astrbot.api.event import AstrMessageEvent
    from astrbot.core.message.components import Plain
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

try:
    from common import (
        MessageEditor,
        get_platform_capabilities,
        get_unified_user_id,
        get_push_scheduler
    )
    from common.subscription_manager import (
        SubscriptionManager,
        SubscriptionType,
        PushFrequency
    )
except ImportError:
    logger.warning("[SubscriptionSessionHandler] 通用模块不可用")
    get_push_scheduler = None

from .response_builder import SubscriptionResponseBuilder


class SubscriptionSessionHandler:
    """订阅插件会话处理器"""
    
    # 会话步骤定义
    class Step:
        MAIN_MENU = 0
        SELECT_TYPE = 1
        SELECT_PLUGIN = 2
        SELECT_TIME = 3
        INPUT_KEYWORD = 4
        INPUT_CUSTOM_TIME = 5
        VIEW_LIST = 6
        VIEW_DETAIL = 7
        CONFIRM_DELETE = 8
        EDIT_TIME = 9
        SETTINGS = 10
    
    # 插件映射
    PLUGIN_MAP = {
        '1': 'music',
        '2': 'book',
        '3': 'douban',
        '4': 'pansou'
    }
    
    # 时间映射
    TIME_MAP = {
        '1': '08:00',
        '2': '12:00',
        '3': '18:00',
        '4': '19:00',
        '5': '21:00',
        '6': '22:00'
    }
    
    def __init__(
        self,
        plugin,
        subscription_manager: SubscriptionManager,
        session_manager
    ):
        """
        初始化会话处理器
        
        Args:
            plugin: 主插件实例
            subscription_manager: 订阅管理器
            session_manager: 会话管理器
        """
        self.plugin = plugin
        self.subscription_manager = subscription_manager
        self.session_manager = session_manager
    
    # ==================== 菜单显示 ====================
    
    async def show_main_menu(self, event: AstrMessageEvent, capabilities: Dict[str, Any]):
        """显示主菜单"""
        user_id = get_unified_user_id(event)
        
        # 获取用户订阅
        subscriptions = self.subscription_manager.get_user_subscriptions(user_id)
        
        # 获取可用订阅源
        available_sources = []
        hot_sources = []
        user_categories = []
        
        if hasattr(self.plugin, 'source_manager') and self.plugin.source_manager:
            source_manager = self.plugin.source_manager
            available_sources = source_manager.get_available_sources(0)
            
            # 获取用户已订阅的分类（用于个性化推荐）
            for sub in subscriptions:
                if sub.source_id:
                    source = source_manager.get_source(sub.source_id)
                    if source and source.category and source.category not in user_categories:
                        user_categories.append(source.category)
            
            # 使用优化的推荐算法（考虑健康度、活跃度和用户偏好）
            if hasattr(source_manager, 'get_recommended_sources'):
                hot_sources = source_manager.get_recommended_sources(
                    user_level=0,
                    user_categories=user_categories if user_categories else None,
                    limit=3
                )
            else:
                # 后备：使用旧的热门排序
                hot_sources = source_manager.get_popular_sources(limit=3, user_level=0)
        
        # 构建响应
        builder = SubscriptionResponseBuilder(capabilities)
        message, keyboard = builder.build_main_menu(
            subscriptions, 
            available_sources,
            hot_sources=hot_sources
        )
        
        # 更新会话
        session_id = event.get_session_id()
        self.session_manager.update_session(session_id, step=self.Step.MAIN_MENU)
        
        # 发送响应
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    # ==================== 回调处理 ====================
    
    async def handle_callback(self, event: AstrMessageEvent, data: str):
        """处理回调"""
        session_id = event.get_session_id()
        session = self.session_manager.get_session(session_id)
        capabilities = session.get('capabilities') if session else get_platform_capabilities(event, "Subscription")
        
        # 解析回调数据
        parts = data.split(":")
        action = parts[0] if parts else ""
        params = parts[1:] if len(parts) > 1 else []
        
        logger.debug(f"[SubscriptionSession] 回调: action={action}, params={params}")
        
        # 路由处理
        if action == "home":
            async for result in self.show_main_menu(event, capabilities):
                yield result
        
        elif action == "exit":
            async for result in self._handle_exit(event, session):
                yield result
        
        elif action == "back":
            async for result in self._handle_back(event, session, capabilities):
                yield result
        
        elif action == "add":
            # 添加订阅 - 选择类型后选择插件
            sub_type = params[0] if params else "ranking"
            async for result in self._show_plugin_select(event, sub_type, capabilities):
                yield result
        
        elif action == "plugin":
            # 选择插件后选择时间
            sub_type = params[0] if params else "ranking"
            plugin_name = params[1] if len(params) > 1 else "music"
            
            if sub_type == "keyword":
                # 关键词订阅需要先输入关键词
                async for result in self._show_keyword_input(event, plugin_name, capabilities):
                    yield result
            else:
                async for result in self._show_time_select(event, sub_type, plugin_name, capabilities):
                    yield result
        
        elif action == "time":
            # 选择时间后创建订阅
            sub_type = params[0] if params else "ranking"
            plugin_name = params[1] if len(params) > 1 else "music"
            push_time = ":".join(params[2:]) if len(params) > 2 else "19:00"
            
            async for result in self._create_subscription(event, sub_type, plugin_name, push_time, capabilities):
                yield result
        
        elif action == "time_custom":
            # 自定义时间输入
            sub_type = params[0] if params else "ranking"
            plugin_name = params[1] if len(params) > 1 else "music"
            async for result in self._show_custom_time_input(event, sub_type, plugin_name, capabilities):
                yield result
        
        elif action == "list":
            # 订阅列表
            page = int(params[0]) if params else 1
            async for result in self._show_subscription_list(event, page, capabilities):
                yield result
        
        elif action == "detail":
            # 订阅详情
            sub_id = int(params[0]) if params else 0
            async for result in self._show_subscription_detail(event, sub_id, capabilities):
                yield result
        
        elif action == "enable":
            # 启用订阅
            sub_id = int(params[0]) if params else 0
            async for result in self._enable_subscription(event, sub_id, capabilities):
                yield result
        
        elif action == "disable":
            # 禁用订阅
            sub_id = int(params[0]) if params else 0
            async for result in self._disable_subscription(event, sub_id, capabilities):
                yield result
        
        elif action == "delete":
            # 删除确认
            sub_id = int(params[0]) if params else 0
            async for result in self._show_delete_confirm(event, sub_id, capabilities):
                yield result
        
        elif action == "confirm_delete":
            # 确认删除
            sub_id = int(params[0]) if params else 0
            async for result in self._delete_subscription(event, sub_id, capabilities):
                yield result
        
        elif action == "edit_time":
            # 编辑推送时间
            sub_id = int(params[0]) if params else 0
            async for result in self._show_edit_time(event, sub_id, capabilities):
                yield result
        
        elif action == "set_time":
            # 直接设置推送时间（按钮回调）
            # 格式: subscription:set_time:{sub_id}:{HH}:{MM}
            if len(params) >= 3:
                sub_id = int(params[0])
                push_time = f"{params[1]}:{params[2]}"
                async for result in self._set_push_time(event, sub_id, push_time, capabilities):
                    yield result
        
        elif action == "settings":
            # 推送设置
            async for result in self._show_settings(event, capabilities):
                yield result
        
        elif action == "view_hot":
            # 查看热门订阅源
            page = int(params[0]) if params else 1
            async for result in self._show_hot_sources(event, page, capabilities):
                yield result
        
        elif action == "help":
            # 使用帮助
            async for result in self._show_help(event, capabilities):
                yield result
        
        elif action == "browse_sources":
            # 浏览订阅源
            page = int(params[0]) if params else 1
            category = params[1] if len(params) > 1 else None
            async for result in self._show_source_browse(event, page, category, capabilities):
                yield result
        
        elif action == "source_detail":
            # 订阅源详情
            source_id = int(params[0]) if params else 0
            async for result in self._show_source_detail(event, source_id, capabilities):
                yield result
        
        elif action == "subscribe":
            # 订阅
            source_id = int(params[0]) if params else 0
            async for result in self._subscribe_source(event, source_id, capabilities):
                yield result
        
        elif action == "quick_sub":
            # 快捷订阅（一键订阅）
            source_id = int(params[0]) if params else 0
            async for result in self._quick_subscribe(event, source_id, capabilities):
                yield result
        
        elif action == "unsubscribe":
            # 取消订阅
            source_id = int(params[0]) if params else 0
            async for result in self._unsubscribe_source(event, source_id, capabilities):
                yield result
        
        elif action == "sub_time":
            # P1优化：带时间的一键订阅
            # 格式: subscription:sub_time:{source_id}:{HH}:{MM}
            if len(params) >= 3:
                source_id = int(params[0])
                push_time = f"{params[1]}:{params[2]}"
                async for result in self._subscribe_source_with_time(event, source_id, push_time, capabilities):
                    yield result
        
        elif action == "request":
            # 申请订阅源
            sub_action = params[0] if params else ""
            async for result in self._handle_source_request(event, sub_action, params[1:] if len(params) > 1 else [], capabilities):
                yield result
        
        else:
            yield event.plain_result(f"❌ 未知操作: {action}")
    
    # ==================== 会话输入处理 ====================
    
    async def handle_session_input(self, event: AstrMessageEvent, session: Dict[str, Any]):
        """处理会话模式的用户输入"""
        message_str = event.message_str.strip()
        step = session.get('step', 0)
        capabilities = session.get('capabilities', {})
        session_data = session.get('data', {})
        
        # 导航命令处理
        if message_str.lower() in ['0', 'q', 'quit', 'exit']:
            async for result in self._handle_exit(event, session):
                yield result
            return
        
        if message_str.lower() in ['h', 'home']:
            async for result in self.show_main_menu(event, capabilities):
                yield result
            return
        
        if message_str.lower() in ['b', 'back']:
            async for result in self._handle_back(event, session, capabilities):
                yield result
            return
        
        # 根据步骤处理输入
        if step == self.Step.MAIN_MENU:
            async for result in self._handle_main_menu_input(event, message_str, capabilities):
                yield result
        
        elif step == self.Step.SELECT_PLUGIN:
            sub_type = session_data.get('subscription_type', 'ranking')
            async for result in self._handle_plugin_select_input(event, message_str, sub_type, capabilities):
                yield result
        
        elif step == self.Step.SELECT_TIME:
            sub_type = session_data.get('subscription_type', 'ranking')
            plugin_name = session_data.get('plugin_name', 'music')
            async for result in self._handle_time_select_input(event, message_str, sub_type, plugin_name, capabilities):
                yield result
        
        elif step == self.Step.INPUT_KEYWORD:
            # 检查是否是订阅源申请模式
            if session_data.get('request_mode') == 'source_request':
                async for result in self._handle_source_request_input(event, message_str, capabilities):
                    yield result
            else:
                plugin_name = session_data.get('plugin_name', 'music')
                async for result in self._handle_keyword_input(event, message_str, plugin_name, capabilities):
                    yield result
        
        elif step == self.Step.INPUT_CUSTOM_TIME:
            sub_type = session_data.get('subscription_type', 'ranking')
            plugin_name = session_data.get('plugin_name', 'music')
            keyword = session_data.get('keyword')
            async for result in self._handle_custom_time_input(event, message_str, sub_type, plugin_name, keyword, capabilities):
                yield result
        
        elif step == self.Step.VIEW_LIST:
            async for result in self._handle_list_input(event, message_str, session_data, capabilities):
                yield result
        
        elif step == self.Step.VIEW_DETAIL:
            sub_id = session_data.get('subscription_id')
            async for result in self._handle_detail_input(event, message_str, sub_id, capabilities):
                yield result
        
        elif step == self.Step.CONFIRM_DELETE:
            sub_id = session_data.get('subscription_id')
            async for result in self._handle_delete_confirm_input(event, message_str, sub_id, capabilities):
                yield result
        
        elif step == self.Step.EDIT_TIME:
            sub_id = session_data.get('subscription_id')
            async for result in self._handle_edit_time_input(event, message_str, sub_id, capabilities):
                yield result
    
    # ==================== 具体处理方法 ====================
    
    async def _handle_main_menu_input(self, event: AstrMessageEvent, message_str: str, capabilities: Dict):
        """处理主菜单输入"""
        action_map = {
            '1': 'browse_sources',
            '2': 'list',
            '3': 'settings',
            '4': 'view_hot',
            '5': 'request',
            '6': 'help'
        }
        
        action = action_map.get(message_str)
        if action == 'browse_sources':
            async for result in self._show_source_browse(event, 1, None, capabilities):
                yield result
        elif action == 'list':
            async for result in self._show_subscription_list(event, 1, capabilities):
                yield result
        elif action == 'settings':
            async for result in self._show_settings(event, capabilities):
                yield result
        elif action == 'view_hot':
            async for result in self._show_hot_sources(event, 1, capabilities):
                yield result
        elif action == 'request':
            async for result in self._handle_source_request(event, "", [], capabilities):
                yield result
        elif action == 'help':
            async for result in self._show_help(event, capabilities):
                yield result
        else:
            yield event.plain_result("❌ 无效输入，请输入 1-6 选择操作")
    
    async def _handle_plugin_select_input(self, event: AstrMessageEvent, message_str: str, sub_type: str, capabilities: Dict):
        """处理插件选择输入"""
        plugin_name = self.PLUGIN_MAP.get(message_str)
        if plugin_name:
            if sub_type == 'keyword':
                async for result in self._show_keyword_input(event, plugin_name, capabilities):
                    yield result
            else:
                async for result in self._show_time_select(event, sub_type, plugin_name, capabilities):
                    yield result
        else:
            yield event.plain_result("❌ 无效输入，请输入 1-4 选择平台")
    
    async def _handle_time_select_input(self, event: AstrMessageEvent, message_str: str, sub_type: str, plugin_name: str, capabilities: Dict):
        """处理时间选择输入"""
        # 检查是否是预设时间
        push_time = self.TIME_MAP.get(message_str)
        
        if push_time:
            async for result in self._create_subscription(event, sub_type, plugin_name, push_time, capabilities):
                yield result
        elif message_str == '6':
            # 自定义时间
            async for result in self._show_custom_time_input(event, sub_type, plugin_name, capabilities):
                yield result
        elif self._validate_time_format(message_str):
            # 直接输入的时间
            async for result in self._create_subscription(event, sub_type, plugin_name, message_str, capabilities):
                yield result
        else:
            yield event.plain_result("❌ 无效时间格式，请输入如 19:30 的格式")
    
    async def _handle_keyword_input(self, event: AstrMessageEvent, keyword: str, plugin_name: str, capabilities: Dict):
        """处理关键词输入"""
        if not keyword or len(keyword) < 1:
            yield event.plain_result("❌ 关键词不能为空")
            return
        
        if len(keyword) > 50:
            yield event.plain_result("❌ 关键词过长，请控制在50字以内")
            return
        
        # 保存关键词，进入时间选择
        session_id = event.get_session_id()
        self.session_manager.update_session(session_id, data={'keyword': keyword})
        
        async for result in self._show_time_select(event, 'keyword', plugin_name, capabilities, keyword=keyword):
            yield result
    
    async def _handle_custom_time_input(self, event: AstrMessageEvent, time_str: str, sub_type: str, plugin_name: str, keyword: str, capabilities: Dict):
        """处理自定义时间输入"""
        if not self._validate_time_format(time_str):
            yield event.plain_result("❌ 无效时间格式，请输入如 19:30 的格式")
            return
        
        async for result in self._create_subscription(event, sub_type, plugin_name, time_str, capabilities, keyword=keyword):
            yield result
    
    async def _handle_list_input(self, event: AstrMessageEvent, message_str: str, session_data: Dict, capabilities: Dict):
        """处理列表页输入"""
        current_page = session_data.get('page', 1)
        subscriptions = session_data.get('subscriptions', [])
        
        # 翻页
        if message_str.lower() in ['p', 'prev']:
            if current_page > 1:
                async for result in self._show_subscription_list(event, current_page - 1, capabilities):
                    yield result
            else:
                yield event.plain_result("💡 已是第一页")
            return
        
        if message_str.lower() in ['n', 'next']:
            total_pages = (len(subscriptions) + 4) // 5
            if current_page < total_pages:
                async for result in self._show_subscription_list(event, current_page + 1, capabilities):
                    yield result
            else:
                yield event.plain_result("💡 已是最后一页")
            return
        
        # 选择订阅
        try:
            index = int(message_str) - 1
            if 0 <= index < len(subscriptions):
                sub = subscriptions[index]
                async for result in self._show_subscription_detail(event, sub.id, capabilities):
                    yield result
            else:
                yield event.plain_result("❌ 无效序号")
        except ValueError:
            yield event.plain_result("❌ 请输入有效的数字序号")
    
    async def _handle_detail_input(self, event: AstrMessageEvent, message_str: str, sub_id: int, capabilities: Dict):
        """处理详情页输入"""
        if message_str == '1':
            # 切换启用/禁用
            sub = self.subscription_manager.get_subscription(sub_id)
            if sub:
                if sub.enabled:
                    async for result in self._disable_subscription(event, sub_id, capabilities):
                        yield result
                else:
                    async for result in self._enable_subscription(event, sub_id, capabilities):
                        yield result
        elif message_str == '2':
            # 修改时间
            async for result in self._show_edit_time(event, sub_id, capabilities):
                yield result
        elif message_str == '3':
            # 取消订阅
            async for result in self._show_delete_confirm(event, sub_id, capabilities):
                yield result
        else:
            yield event.plain_result("❌ 无效输入，请输入 1-3 选择操作")
    
    async def _handle_delete_confirm_input(self, event: AstrMessageEvent, message_str: str, sub_id: int, capabilities: Dict):
        """处理删除确认输入"""
        if message_str.lower() in ['y', 'yes', '确认']:
            async for result in self._delete_subscription(event, sub_id, capabilities):
                yield result
        else:
            async for result in self._show_subscription_detail(event, sub_id, capabilities):
                yield result
    
    async def _handle_edit_time_input(self, event: AstrMessageEvent, time_str: str, sub_id: int, capabilities: Dict):
        """处理编辑时间输入"""
        # 检查预设时间
        push_time = self.TIME_MAP.get(time_str)
        if not push_time:
            if self._validate_time_format(time_str):
                push_time = time_str
            else:
                yield event.plain_result("❌ 无效时间格式，请输入如 19:30 的格式")
                return
        
        # 更新时间
        success = self.subscription_manager.update_push_time(sub_id, push_time)
        
        # 通知调度器重新调度该订阅
        if success and get_push_scheduler:
            scheduler = get_push_scheduler()
            if scheduler:
                await scheduler.schedule_subscription(sub_id)
        
        # 获取更新后的订阅信息
        sub = self.subscription_manager.get_subscription(sub_id)
        next_push = sub.next_push_at.strftime('%m-%d %H:%M') if sub and sub.next_push_at else "计算中"
        
        builder = SubscriptionResponseBuilder(capabilities)
        if success:
            message, keyboard = builder.build_success_message(
                'update_time', 
                f"新推送时间: {push_time}\n下次推送: {next_push}"
            )
        else:
            message = "❌ 更新失败，请重试"
            keyboard = None
        
        # 获取保存的消息ID，尝试编辑之前的消息
        session_id = event.get_session_id()
        session = self.session_manager.get_session(session_id)
        input_message_id = session.get('data', {}).get('input_message_id') if session else None
        
        if input_message_id and capabilities.get('supports_buttons'):
            try:
                platform_name = event.get_platform_name()
                if platform_name == "telegram":
                    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                    
                    # 转换键盘格式
                    tg_keyboard = None
                    if keyboard and hasattr(keyboard, 'buttons'):
                        tg_keyboard_buttons = []
                        for row in keyboard.buttons:
                            tg_row = [
                                InlineKeyboardButton(text=btn['text'], callback_data=btn.get('callback_data', ''))
                                if 'callback_data' in btn
                                else InlineKeyboardButton(text=btn['text'], url=btn.get('url', ''))
                                for btn in row
                            ]
                            tg_keyboard_buttons.append(tg_row)
                        tg_keyboard = InlineKeyboardMarkup(tg_keyboard_buttons)
                    
                    chat_id = event.message_obj.group_id or event.get_sender_id()
                    await event.client.edit_message_text(
                        chat_id=chat_id,
                        message_id=int(input_message_id),
                        text=message,
                        reply_markup=tg_keyboard
                    )
                    logger.debug(f"[Subscription] 已编辑消息为成功页面: {input_message_id}")
                    event.stop_event()  # 停止事件传播，防止流转到 LLM
                    return
            except Exception as e:
                logger.warning(f"[Subscription] 编辑消息失败: {e}")
        
        # 编辑失败或不支持，发送新消息
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    async def _set_push_time(self, event: AstrMessageEvent, sub_id: int, push_time: str, capabilities: Dict):
        """直接设置推送时间（按钮回调）"""
        # 更新时间
        success = self.subscription_manager.update_push_time(sub_id, push_time)
        
        # 通知调度器重新调度该订阅
        if success and get_push_scheduler:
            scheduler = get_push_scheduler()
            if scheduler:
                await scheduler.schedule_subscription(sub_id)
        
        builder = SubscriptionResponseBuilder(capabilities)
        if success:
            # 获取更新后的订阅信息
            sub = self.subscription_manager.get_subscription(sub_id)
            next_push = sub.next_push_at.strftime('%m-%d %H:%M') if sub and sub.next_push_at else "计算中"
            message, keyboard = builder.build_success_message(
                'update_time', 
                f"新推送时间: {push_time}\n下次推送: {next_push}"
            )
        else:
            message = "❌ 更新失败，请重试"
            keyboard = None
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    # ==================== 显示方法 ====================
    
    async def _show_plugin_select(self, event: AstrMessageEvent, sub_type: str, capabilities: Dict):
        """显示插件选择"""
        session_id = event.get_session_id()
        self.session_manager.update_session(
            session_id, 
            step=self.Step.SELECT_PLUGIN,
            data={'subscription_type': sub_type}
        )
        
        builder = SubscriptionResponseBuilder(capabilities)
        message, keyboard = builder.build_plugin_select(sub_type)
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    async def _show_time_select(self, event: AstrMessageEvent, sub_type: str, plugin_name: str, capabilities: Dict, keyword: str = None):
        """显示时间选择"""
        session_id = event.get_session_id()
        data = {'subscription_type': sub_type, 'plugin_name': plugin_name}
        if keyword:
            data['keyword'] = keyword
        
        self.session_manager.update_session(session_id, step=self.Step.SELECT_TIME, data=data)
        
        builder = SubscriptionResponseBuilder(capabilities)
        message, keyboard = builder.build_time_select(sub_type, plugin_name)
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    async def _show_keyword_input(self, event: AstrMessageEvent, plugin_name: str, capabilities: Dict):
        """显示关键词输入"""
        session_id = event.get_session_id()
        self.session_manager.update_session(
            session_id,
            step=self.Step.INPUT_KEYWORD,
            data={'subscription_type': 'keyword', 'plugin_name': plugin_name}
        )
        
        builder = SubscriptionResponseBuilder(capabilities)
        message, keyboard = builder.build_keyword_input(plugin_name)
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    async def _show_custom_time_input(self, event: AstrMessageEvent, sub_type: str, plugin_name: str, capabilities: Dict):
        """显示自定义时间输入"""
        session_id = event.get_session_id()
        session = self.session_manager.get_session(session_id)
        keyword = session.get('data', {}).get('keyword') if session else None
        
        self.session_manager.update_session(
            session_id,
            step=self.Step.INPUT_CUSTOM_TIME,
            data={'subscription_type': sub_type, 'plugin_name': plugin_name, 'keyword': keyword}
        )
        
        message = "⌨️ 请输入推送时间\n\n格式: HH:MM (如 19:30)"
        
        async for result in MessageEditor.edit_or_send(event, message, None):
            yield result
    
    async def _show_subscription_list(self, event: AstrMessageEvent, page: int, capabilities: Dict):
        """显示订阅列表"""
        user_id = get_unified_user_id(event)
        subscriptions = self.subscription_manager.get_user_subscriptions(user_id)
        
        session_id = event.get_session_id()
        self.session_manager.update_session(
            session_id,
            step=self.Step.VIEW_LIST,
            data={'page': page, 'subscriptions': subscriptions}
        )
        
        builder = SubscriptionResponseBuilder(capabilities)
        message, keyboard = builder.build_subscription_list(subscriptions, page)
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    async def _show_subscription_detail(self, event: AstrMessageEvent, sub_id: int, capabilities: Dict):
        """显示订阅详情"""
        sub = self.subscription_manager.get_subscription(sub_id)
        if not sub:
            yield event.plain_result("❌ 订阅不存在")
            return
        
        session_id = event.get_session_id()
        self.session_manager.update_session(
            session_id,
            step=self.Step.VIEW_DETAIL,
            data={'subscription_id': sub_id}
        )
        
        builder = SubscriptionResponseBuilder(capabilities)
        message, keyboard = builder.build_subscription_detail(sub)
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    async def _show_delete_confirm(self, event: AstrMessageEvent, sub_id: int, capabilities: Dict):
        """显示删除确认"""
        sub = self.subscription_manager.get_subscription(sub_id)
        if not sub:
            yield event.plain_result("❌ 订阅不存在")
            return
        
        session_id = event.get_session_id()
        self.session_manager.update_session(
            session_id,
            step=self.Step.CONFIRM_DELETE,
            data={'subscription_id': sub_id}
        )
        
        builder = SubscriptionResponseBuilder(capabilities)
        message, keyboard = builder.build_confirm_delete(sub)
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    async def _show_edit_time(self, event: AstrMessageEvent, sub_id: int, capabilities: Dict):
        """显示编辑时间"""
        session_id = event.get_session_id()
        
        # 获取当前消息ID（回调消息，用于后续编辑）
        callback_msg_id = getattr(event.message_obj, 'message_id', None)
        
        self.session_manager.update_session(
            session_id,
            step=self.Step.EDIT_TIME,
            data={
                'subscription_id': sub_id,
                'input_message_id': callback_msg_id  # 保存消息ID用于后续编辑
            }
        )
        
        # 获取当前订阅的推送时间
        sub = self.subscription_manager.get_subscription(sub_id)
        current_time = sub.push_time if sub else "未设置"
        
        message = f"⏰ 修改推送时间\n\n当前时间: {current_time}\n\n请选择新的推送时间:"
        
        if capabilities.get('supports_buttons'):
            from astrbot.core.message.components import InlineKeyboard
            buttons = [
                [
                    {"text": "🌅 08:00", "callback_data": f"subscription:set_time:{sub_id}:08:00"},
                    {"text": "🌞 12:00", "callback_data": f"subscription:set_time:{sub_id}:12:00"},
                    {"text": "🌆 18:00", "callback_data": f"subscription:set_time:{sub_id}:18:00"}
                ],
                [
                    {"text": "🌙 19:00", "callback_data": f"subscription:set_time:{sub_id}:19:00"},
                    {"text": "🌃 21:00", "callback_data": f"subscription:set_time:{sub_id}:21:00"},
                    {"text": "🌛 22:00", "callback_data": f"subscription:set_time:{sub_id}:22:00"}
                ],
                [
                    {"text": "⬅️ 返回", "callback_data": f"subscription:detail:{sub_id}"},
                    {"text": "❌ 退出", "callback_data": "subscription:exit"}
                ]
            ]
            keyboard = InlineKeyboard(buttons=buttons)
            message += "\n\n💡 也可直接输入时间 (如 19:30)"
        else:
            message += """

1. 🌅 08:00
2. 🌞 12:00
3. 🌆 18:00
4. 🌙 19:00
5. 🌃 21:00
6. 🌛 22:00

或直接输入时间 (如 19:30)

💡 b-返回 | 0-退出"""
            keyboard = None
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    async def _show_settings(self, event: AstrMessageEvent, capabilities: Dict):
        """显示推送设置"""
        user_id = get_unified_user_id(event)
        sub_count = self.subscription_manager.count_user_subscriptions(user_id)
        
        message = f"""⚙️ 推送设置

当前订阅数: {sub_count}
最大订阅数: {self.plugin.plugin_config.get('max_subscriptions_per_user', 20)}

💡 更多设置功能开发中..."""
        
        builder = SubscriptionResponseBuilder(capabilities)
        if capabilities.get('supports_buttons'):
            from astrbot.core.message.components import InlineKeyboard
            buttons = [[
                {"text": "🏠 首页", "callback_data": "subscription:home"},
                {"text": "❌ 退出", "callback_data": "subscription:exit"}
            ]]
            keyboard = InlineKeyboard(buttons=buttons)
        else:
            message += "\n\n💡 h-首页 | 0-退出"
            keyboard = None
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    # ==================== 操作方法 ====================
    
    async def _create_subscription(self, event: AstrMessageEvent, sub_type: str, plugin_name: str, push_time: str, capabilities: Dict, keyword: str = None):
        """创建订阅"""
        user_id = get_unified_user_id(event)
        
        # 检查订阅数量限制（使用权益管理器）
        current_count = self.subscription_manager.count_user_subscriptions(user_id)
        
        if hasattr(self.plugin, 'privilege_manager') and self.plugin.privilege_manager:
            can_subscribe, error_msg = self.plugin.privilege_manager.can_subscribe(user_id, current_count)
            if not can_subscribe:
                yield event.plain_result(f"❌ {error_msg}")
                return
        else:
            # 回退到配置限制
            max_count = self.plugin.plugin_config.get('max_subscriptions_per_user', 20)
            if current_count >= max_count:
                yield event.plain_result(f"❌ 订阅数量已达上限 ({current_count}/{max_count})")
                return
        
        # 获取关键词（如果是关键词订阅）
        if sub_type == 'keyword' and not keyword:
            session_id = event.get_session_id()
            session = self.session_manager.get_session(session_id)
            keyword = session.get('data', {}).get('keyword') if session else None
        
        # 创建订阅
        sub_id = None
        target = keyword if sub_type == 'keyword' else sub_type
        
        type_map = {
            'ranking': SubscriptionType.RANKING,
            'keyword': SubscriptionType.KEYWORD,
            'new_entry': SubscriptionType.NEW_ENTRY,
            'rising': SubscriptionType.RISING
        }
        
        subscription_type = type_map.get(sub_type, SubscriptionType.RANKING)
        
        if sub_type == 'ranking':
            sub_id = self.subscription_manager.subscribe_ranking(
                user_id=user_id,
                plugin_name=plugin_name,
                ranking_type='hot',
                push_time=push_time
            )
        elif sub_type == 'keyword':
            sub_id = self.subscription_manager.subscribe_keyword(
                user_id=user_id,
                plugin_name=plugin_name,
                keyword=keyword,
                push_time=push_time
            )
        elif sub_type == 'new_entry':
            sub_id = self.subscription_manager.subscribe_new_entry(
                user_id=user_id,
                plugin_name=plugin_name,
                push_time=push_time
            )
        elif sub_type == 'rising':
            sub_id = self.subscription_manager.subscribe_rising(
                user_id=user_id,
                plugin_name=plugin_name,
                push_time=push_time
            )
        
        builder = SubscriptionResponseBuilder(capabilities)
        
        if sub_id:
            plugin_display = builder.PLUGIN_NAMES.get(plugin_name, plugin_name)
            type_display = builder.SUBSCRIPTION_TYPES.get(sub_type, sub_type)
            details = f"平台: {plugin_display}\n类型: {type_display}\n"
            if keyword:
                details += f"关键词: {keyword}\n"
            details += f"推送时间: {push_time}"
            
            message, keyboard = builder.build_success_message('subscribe', details)
        else:
            message = "❌ 订阅失败，可能已存在相同订阅"
            keyboard = None
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    async def _enable_subscription(self, event: AstrMessageEvent, sub_id: int, capabilities: Dict):
        """启用订阅"""
        success = self.subscription_manager.enable_subscription(sub_id)
        
        builder = SubscriptionResponseBuilder(capabilities)
        if success:
            message, keyboard = builder.build_success_message('enable')
        else:
            message = "❌ 操作失败"
            keyboard = None
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    async def _disable_subscription(self, event: AstrMessageEvent, sub_id: int, capabilities: Dict):
        """禁用订阅"""
        success = self.subscription_manager.disable_subscription(sub_id)
        
        builder = SubscriptionResponseBuilder(capabilities)
        if success:
            message, keyboard = builder.build_success_message('disable')
        else:
            message = "❌ 操作失败"
            keyboard = None
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    async def _delete_subscription(self, event: AstrMessageEvent, sub_id: int, capabilities: Dict):
        """删除订阅"""
        success = self.subscription_manager.unsubscribe(sub_id)
        
        builder = SubscriptionResponseBuilder(capabilities)
        if success:
            message, keyboard = builder.build_success_message('unsubscribe')
        else:
            message = "❌ 删除失败"
            keyboard = None
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    async def _handle_exit(self, event: AstrMessageEvent, session: Dict):
        """处理退出"""
        session_id = event.get_session_id()
        self.session_manager.end_session(session_id)
        
        # 尝试删除消息
        try:
            platform_name = event.get_platform_name()
            msg_id = getattr(event.message_obj, 'message_id', None)
            
            if msg_id and platform_name == "telegram":
                chat_id = event.message_obj.group_id or event.get_sender_id()
                await event.client.delete_message(chat_id=chat_id, message_id=int(msg_id))
                return
        except Exception as e:
            logger.debug(f"[SubscriptionSession] 删除消息失败: {e}")
        
        yield event.plain_result("✅ 已退出订阅管理")
    
    async def _handle_back(self, event: AstrMessageEvent, session: Dict, capabilities: Dict):
        """处理返回"""
        step = session.get('step', 0) if session else 0
        
        if step <= self.Step.MAIN_MENU:
            async for result in self.show_main_menu(event, capabilities):
                yield result
        elif step == self.Step.VIEW_DETAIL:
            async for result in self._show_subscription_list(event, 1, capabilities):
                yield result
        elif step in [self.Step.CONFIRM_DELETE, self.Step.EDIT_TIME]:
            sub_id = session.get('data', {}).get('subscription_id')
            if sub_id:
                async for result in self._show_subscription_detail(event, sub_id, capabilities):
                    yield result
            else:
                async for result in self.show_main_menu(event, capabilities):
                    yield result
        else:
            async for result in self.show_main_menu(event, capabilities):
                yield result
    
    async def _show_help(self, event: AstrMessageEvent, capabilities: Dict):
        """显示使用帮助"""
        message = """📖 订阅系统使用帮助

🎯 订阅类型说明:
• 📊 热搜榜单 - 每日推送热门内容排行
• 🔍 关键词提醒 - 关注内容上榜时通知
• 🆕 新上榜 - 发现新内容时推送
• 📈 飙升榜 - 热度快速上升内容提醒

⏰ 推送时间:
• 支持自定义推送时间（如 19:30）
• 每日定时推送，不会重复骚扰

📱 使用技巧:
• 使用 /订 快速进入管理界面
• 支持按钮和文字两种交互方式
• 可随时暂停/启用订阅
• 每用户最多 20 个订阅

💡 常见问题:
• 订阅失败：可能已存在相同订阅
• 推送延迟：系统每分钟检查一次
• 修改设置：进入"我的订阅"管理"""

        builder = SubscriptionResponseBuilder(capabilities)
        if capabilities.get('supports_buttons'):
            from astrbot.core.message.components import InlineKeyboard
            buttons = [[
                {"text": "🏠 返回首页", "callback_data": "subscription:home"},
                {"text": "❌ 退出", "callback_data": "subscription:exit"}
            ]]
            keyboard = InlineKeyboard(buttons=buttons)
        else:
            message += "\n\n💡 h-返回首页 | 0-退出"
            keyboard = None
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    # ==================== 订阅源浏览与订阅 ====================
    
    async def _show_source_browse(self, event: AstrMessageEvent, page: int, category: str, capabilities: Dict):
        """显示订阅源浏览页面"""
        # 获取可用订阅源
        if hasattr(self.plugin, 'source_manager') and self.plugin.source_manager:
            sources = self.plugin.source_manager.get_available_sources(0)
        else:
            sources = []
        
        # 按分类筛选
        if category:
            sources = [s for s in sources if (s.category or "其他") == category]
        
        builder = SubscriptionResponseBuilder(capabilities)
        message, keyboard = builder.build_source_browse(sources, page, category)
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    async def _show_source_detail(self, event: AstrMessageEvent, source_id: int, capabilities: Dict):
        """显示订阅源详情"""
        if not hasattr(self.plugin, 'source_manager') or not self.plugin.source_manager:
            yield event.plain_result("❌ 订阅源系统不可用")
            return
        
        source = self.plugin.source_manager.get_source(source_id)
        if not source:
            yield event.plain_result("❌ 订阅源不存在")
            return
        
        # 检查是否已订阅
        user_id = get_unified_user_id(event)
        is_subscribed = self.subscription_manager.is_subscribed_to_source(user_id, source_id)
        
        builder = SubscriptionResponseBuilder(capabilities)
        message, keyboard = builder.build_source_detail(source, is_subscribed)
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    async def _subscribe_source(self, event: AstrMessageEvent, source_id: int, capabilities: Dict):
        """订阅订阅源"""
        user_id = get_unified_user_id(event)
        
        # 获取订阅源
        if not hasattr(self.plugin, 'source_manager') or not self.plugin.source_manager:
            yield event.plain_result("❌ 订阅源系统不可用")
            return
        
        source = self.plugin.source_manager.get_source(source_id)
        if not source:
            yield event.plain_result("❌ 订阅源不存在")
            return
        
        # 检查是否已订阅
        if self.subscription_manager.is_subscribed_to_source(user_id, source_id):
            yield event.plain_result("❌ 您已订阅此内容源")
            return
        
        # 检查订阅源访问权限
        if hasattr(self.plugin, 'privilege_manager') and self.plugin.privilege_manager:
            can_access, error_msg = self.plugin.privilege_manager.can_access_source(
                user_id, source.access_level.value
            )
            if not can_access:
                yield event.plain_result(f"🔒 {error_msg}")
                return
        
        # 检查订阅数量限制（使用权益管理器）
        current_count = self.subscription_manager.count_user_subscriptions(user_id)
        
        if hasattr(self.plugin, 'privilege_manager') and self.plugin.privilege_manager:
            can_subscribe, error_msg = self.plugin.privilege_manager.can_subscribe(user_id, current_count)
            if not can_subscribe:
                yield event.plain_result(f"❌ {error_msg}")
                return
        else:
            # 回退到配置限制
            max_count = self.plugin.plugin_config.get('max_subscriptions_per_user', 20)
            if current_count >= max_count:
                yield event.plain_result(f"❌ 订阅数量已达上限 ({current_count}/{max_count})")
                return
        
        # 创建订阅
        default_time = self.plugin.plugin_config.get('default_push_time', '19:00')
        success = self.subscription_manager.create_source_subscription(
            user_id=user_id,
            source_id=source_id,
            push_time=default_time
        )
        
        if success:
            # 更新订阅源订阅人数
            self.plugin.source_manager.increment_subscriber_count(source_id)
            
            # 获取下次推送时间
            next_push_str = "计算中..."
            try:
                # 查询刚创建的订阅记录
                user_subs = self.subscription_manager.get_user_subscriptions(user_id)
                for sub in user_subs:
                    if sub.source_id == source_id:
                        if sub.next_push_at:
                            next_push_str = sub.next_push_at.strftime('%m-%d %H:%M')
                        break
            except Exception as e:
                logger.debug(f"[订阅] 获取下次推送时间失败: {e}")
            
            display_title = source.get_display_title()
            message = f"""✅ 订阅成功！

{source.icon} {display_title}
⏰ 推送时间: {default_time}
⏳ 下次推送: {next_push_str}

💡 您可以在"我的订阅"中管理此订阅"""
        else:
            message = "❌ 订阅失败，请稍后重试"
        
        if capabilities.get('supports_buttons'):
            from astrbot.core.message.components import InlineKeyboard
            buttons = [[
                {"text": "📋 我的订阅", "callback_data": "subscription:list"},
                {"text": "🏠 返回首页", "callback_data": "subscription:home"}
            ]]
            keyboard = InlineKeyboard(buttons=buttons)
        else:
            keyboard = None
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    async def _subscribe_source_with_time(self, event: AstrMessageEvent, source_id: int, push_time: str, capabilities: Dict):
        """
        P1优化：带时间的一键订阅
        合并订阅和时间设置为一步，减少操作流程
        """
        user_id = get_unified_user_id(event)
        
        # 获取订阅源
        if not hasattr(self.plugin, 'source_manager') or not self.plugin.source_manager:
            yield event.plain_result("❌ 订阅源系统不可用")
            return
        
        source = self.plugin.source_manager.get_source(source_id)
        if not source:
            yield event.plain_result("❌ 订阅源不存在")
            return
        
        # 检查是否已订阅
        if self.subscription_manager.is_subscribed_to_source(user_id, source_id):
            yield event.plain_result(f"❌ 您已订阅此内容源")
            return
        
        # 检查订阅源访问权限
        if hasattr(self.plugin, 'privilege_manager') and self.plugin.privilege_manager:
            can_access, error_msg = self.plugin.privilege_manager.can_access_source(
                user_id, source.access_level.value
            )
            if not can_access:
                yield event.plain_result(f"🔒 {error_msg}")
                return
        
        # 检查订阅数量限制
        current_count = self.subscription_manager.count_user_subscriptions(user_id)
        
        if hasattr(self.plugin, 'privilege_manager') and self.plugin.privilege_manager:
            can_subscribe, error_msg = self.plugin.privilege_manager.can_subscribe(user_id, current_count)
            if not can_subscribe:
                yield event.plain_result(f"❌ {error_msg}")
                return
        else:
            max_count = self.plugin.plugin_config.get('max_subscriptions_per_user', 20)
            if current_count >= max_count:
                yield event.plain_result(f"❌ 订阅数量已达上限 ({current_count}/{max_count})")
                return
        
        # 创建订阅（使用指定的时间）
        success = self.subscription_manager.create_source_subscription(
            user_id=user_id,
            source_id=source_id,
            push_time=push_time
        )
        
        if success:
            # 更新订阅源订阅人数
            self.plugin.source_manager.increment_subscriber_count(source_id)
            
            # 获取下次推送时间
            next_push_str = "计算中..."
            try:
                user_subs = self.subscription_manager.get_user_subscriptions(user_id)
                for sub in user_subs:
                    if sub.source_id == source_id:
                        if sub.next_push_at:
                            next_push_str = sub.next_push_at.strftime('%m-%d %H:%M')
                        break
            except Exception as e:
                logger.debug(f"[订阅] 获取下次推送时间失败: {e}")
            
            display_title = source.get_display_title()
            message = f"""✅ 订阅成功！

{source.icon} {display_title}
⏰ 推送时间: {push_time}
⏳ 下次推送: {next_push_str}

💡 您可以在"我的订阅"中管理此订阅"""
        else:
            message = "❌ 订阅失败，请稍后重试"
        
        if capabilities.get('supports_buttons'):
            from astrbot.core.message.components import InlineKeyboard
            buttons = [[
                {"text": "📋 我的订阅", "callback_data": "subscription:list"},
                {"text": "🏠 返回首页", "callback_data": "subscription:home"}
            ]]
            keyboard = InlineKeyboard(buttons=buttons)
        else:
            keyboard = None
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    async def _quick_subscribe(self, event: AstrMessageEvent, source_id: int, capabilities: Dict):
        """快捷订阅（一键订阅，简化流程）"""
        user_id = get_unified_user_id(event)
        
        # 获取订阅源
        if not hasattr(self.plugin, 'source_manager') or not self.plugin.source_manager:
            yield event.plain_result("❌ 订阅源系统不可用")
            return
        
        source = self.plugin.source_manager.get_source(source_id)
        if not source:
            yield event.plain_result("❌ 订阅源不存在")
            return
        
        # 检查是否已订阅 - P1优化：已订阅时提供修改时间选项
        if self.subscription_manager.is_subscribed_to_source(user_id, source_id):
            display_title = source.get_display_title()
            
            # 获取当前订阅信息
            current_time = "未设置"
            sub_id = None
            try:
                user_subs = self.subscription_manager.get_user_subscriptions(user_id)
                for sub in user_subs:
                    if sub.source_id == source_id:
                        current_time = sub.push_time
                        sub_id = sub.id
                        break
            except Exception:
                pass
            
            message = f"""ℹ️ 您已订阅 {source.icon} {display_title}

⏰ 当前推送时间: {current_time}

💡 您可以修改推送时间或查看详情"""
            
            if capabilities.get('supports_buttons'):
                from astrbot.core.message.components import InlineKeyboard
                buttons = []
                if sub_id:
                    buttons.append([
                        {"text": "⏰ 修改时间", "callback_data": f"subscription:edit_time:{sub_id}"},
                        {"text": "📋 详情", "callback_data": f"subscription:detail:{sub_id}"}
                    ])
                buttons.append([
                    {"text": "📋 我的订阅", "callback_data": "subscription:list"},
                    {"text": "🏠 返回首页", "callback_data": "subscription:home"}
                ])
                keyboard = InlineKeyboard(buttons=buttons)
            else:
                keyboard = None
            
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
            return
        
        # 未订阅：直接使用默认时间创建订阅
        default_time = self.plugin.plugin_config.get('default_push_time', '19:00')
        async for result in self._subscribe_source_with_time(event, source_id, default_time, capabilities):
            yield result
    
    async def _unsubscribe_source(self, event: AstrMessageEvent, source_id: int, capabilities: Dict):
        """取消订阅"""
        user_id = get_unified_user_id(event)
        
        # 获取订阅源
        if not hasattr(self.plugin, 'source_manager') or not self.plugin.source_manager:
            yield event.plain_result("❌ 订阅源系统不可用")
            return
        
        source = self.plugin.source_manager.get_source(source_id)
        if not source:
            yield event.plain_result("❌ 订阅源不存在")
            return
        
        # 取消订阅
        success = self.subscription_manager.delete_source_subscription(user_id, source_id)
        
        if success:
            # 更新订阅源订阅人数
            self.plugin.source_manager.decrement_subscriber_count(source_id)
            
            display_title = source.get_display_title()
            message = f"✅ 已取消订阅: {source.icon} {display_title}"
        else:
            message = "❌ 取消订阅失败"
        
        if capabilities.get('supports_buttons'):
            from astrbot.core.message.components import InlineKeyboard
            buttons = [[
                {"text": "📰 浏览订阅源", "callback_data": "subscription:browse_sources:1"},
                {"text": "🏠 返回首页", "callback_data": "subscription:home"}
            ]]
            keyboard = InlineKeyboard(buttons=buttons)
        else:
            keyboard = None
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    # ==================== 热门订阅源 ====================
    
    async def _show_hot_sources(self, event: AstrMessageEvent, page: int, capabilities: Dict):
        """显示热门订阅源"""
        user_id = get_unified_user_id(event)
        
        # 获取热门订阅源
        hot_sources = []
        if hasattr(self.plugin, 'source_manager') and self.plugin.source_manager:
            hot_sources = self.plugin.source_manager.get_popular_sources(limit=20, user_level=0)
        
        # 获取用户已订阅的源ID
        user_subscribed_ids = set()
        user_subs = self.subscription_manager.get_user_subscriptions(user_id)
        for sub in user_subs:
            if sub.source_id:
                user_subscribed_ids.add(sub.source_id)
        
        # 构建响应
        builder = SubscriptionResponseBuilder(capabilities)
        message, keyboard = builder.build_hot_sources_page(hot_sources, user_subscribed_ids, page)
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    # ==================== 订阅源申请 ====================
    
    async def _handle_source_request(self, event: AstrMessageEvent, sub_action: str, params: List, capabilities: Dict):
        """处理订阅源申请"""
        user_id = get_unified_user_id(event)
        builder = SubscriptionResponseBuilder(capabilities)
        
        if not sub_action:
            # 显示申请主页
            message, keyboard = builder.build_source_request_page()
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif sub_action == "start":
            # 显示申请表单
            message, keyboard = builder.build_source_request_form()
            
            # 更新会话状态
            session_id = event.get_session_id()
            self.session_manager.update_session(
                session_id, 
                step=self.Step.INPUT_KEYWORD,  # 复用输入步骤
                data={'request_mode': 'source_request'}
            )
            
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif sub_action == "my":
            # 查看我的申请
            requests = self._get_user_source_requests(user_id)
            message, keyboard = builder.build_my_source_requests(requests)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif sub_action == "submit":
            # 提交申请
            import urllib.parse
            url = urllib.parse.unquote(params[0]) if params else ""
            
            if not url:
                yield event.plain_result("❌ 请提供订阅源链接")
                return
            
            # 保存申请
            request_id = self._save_source_request(user_id, url)
            
            if request_id:
                message, keyboard = builder.build_source_request_success(request_id)
            else:
                message = "❌ 提交申请失败，请稍后重试"
                keyboard = None
            
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        else:
            yield event.plain_result(f"❌ 未知操作: {sub_action}")
    
    def _get_user_source_requests(self, user_id: str) -> List[Dict]:
        """获取用户的订阅源申请"""
        try:
            if hasattr(self.plugin, 'db') and self.plugin.db:
                rows = self.plugin.db.execute("""
                    SELECT * FROM source_requests 
                    WHERE user_id = ? 
                    ORDER BY created_at DESC 
                    LIMIT 20
                """, (user_id,))
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"[SubscriptionSessionHandler] 获取用户申请失败: {e}")
        return []
    
    def _save_source_request(self, user_id: str, content: str, name: str = None, description: str = None) -> Optional[int]:
        """保存订阅源申请"""
        try:
            if hasattr(self.plugin, 'db') and self.plugin.db:
                # 确保表存在
                self.plugin.db.execute_write("""
                    CREATE TABLE IF NOT EXISTS source_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        content TEXT NOT NULL,
                        name TEXT,
                        description TEXT,
                        status TEXT DEFAULT 'pending',
                        admin_reply TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                self.plugin.db.execute_write("""
                    INSERT INTO source_requests (user_id, content, name, description)
                    VALUES (?, ?, ?, ?)
                """, (user_id, content, name, description))
                
                row = self.plugin.db.execute_one("SELECT last_insert_rowid() as id")
                return row['id'] if row else None
        except Exception as e:
            logger.error(f"[SubscriptionSessionHandler] 保存申请失败: {e}")
        return None
    
    async def _handle_source_request_input(self, event: AstrMessageEvent, message_str: str, capabilities: Dict):
        """处理订阅源申请输入"""
        user_id = get_unified_user_id(event)
        builder = SubscriptionResponseBuilder(capabilities)
        
        # 解析用户输入
        content = message_str.strip()
        
        # 检查是否是URL
        import re
        url_pattern = r'https?://[^\s]+'
        url_match = re.search(url_pattern, content)
        
        if url_match:
            url = url_match.group(0)
            # 提取可能的名称和说明
            remaining = content.replace(url, '').strip()
            parts = remaining.split(maxsplit=1)
            name = parts[0] if parts else None
            description = parts[1] if len(parts) > 1 else None
            
            # 显示确认页面
            message, keyboard = builder.build_source_request_confirm(url, name, description)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        else:
            # 没有找到URL，提示用户
            message = """❌ 未检测到有效的链接

请提供订阅源的RSS链接或网站地址，例如：
• https://example.com/feed.xml
• https://rsshub.app/xxx

💡 提示: 发送 b 返回，发送 0 退出"""
            
            if capabilities.get('supports_buttons'):
                from astrbot.core.message.components import InlineKeyboard
                buttons = [[
                    {"text": "🔙 返回", "callback_data": "subscription:request"},
                    {"text": "❌ 退出", "callback_data": "subscription:exit"}
                ]]
                keyboard = InlineKeyboard(buttons=buttons)
            else:
                keyboard = None
            
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
    
    # ==================== 工具方法 ====================
    
    def _validate_time_format(self, time_str: str) -> bool:
        """验证时间格式"""
        pattern = r'^([01]?[0-9]|2[0-3]):([0-5][0-9])$'
        return bool(re.match(pattern, time_str))
