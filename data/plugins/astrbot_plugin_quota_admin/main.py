"""
通用配额系统管理插件 v2.0
标准化跨平台交互插件，支持按钮模式和会话模式
"""
from typing import Any
import os
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core import CallbackRouter, callback_handler, auto_stop_event

# 导入通用配额系统
import sys
plugin_root = Path(__file__).parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

try:
    from common import (
        DatabaseManager,
        QuotaValidator,
        MembershipManager,
        PointsManager,
        QuotaReservation,
        QuotaAnalytics,
        SessionManager,
        MessageEditor,
        get_platform_capabilities,
        get_unified_user_id,
        FeedbackManager,
        get_feedback_manager,
        SearchStatistics,
        get_search_statistics,
        MessagePusher,
        get_message_pusher,
        get_rate_limiter,
        LoadingIndicator,
        LarkMessageHelper,
        extract_user_info,
        auto_stop_command,
        get_separator
    )
    QUOTA_SYSTEM_AVAILABLE = True
except ImportError as e:
    QUOTA_SYSTEM_AVAILABLE = False
    logger.error(f"[QuotaAdmin] 通用模块不可用: {e}")
    def get_unified_user_id(event):
        return event.get_sender_id()
    
    # 定义备用装饰器
    def auto_stop_command(func):
        """自动停止事件传播的装饰器"""
        async def wrapper(self, event):
            async for result in func(self, event):
                yield result
            event.stop_event()
        return wrapper

# 导入插件处理器
from .handlers.response_builder import QuotaAdminResponseBuilder
from .handlers.session_handlers import SessionHandler


@register("quota_admin", "AstrBot Team", "通用配额系统管理插件", "2.0.0")
class QuotaAdminPlugin(Star):
    """通用配额系统管理插件 - 标准化跨平台交互"""
    
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context, config)
        self.context = context
        self.config = config or {}
        
        # 从框架配置中读取管理员列表
        admins_str = self.config.get("admins", "")
        self.admins = [admin.strip() for admin in admins_str.split(",") if admin.strip()]
        
        # 读取其他配置项
        self.feedback_enabled = self.config.get("feedback_enabled", True)
        self.notification_enabled = self.config.get("notification_enabled", True)
        self.auto_delete_input_message = self.config.get("auto_delete_input_message", True)
        self.feedback_min_length = self.config.get("feedback_content_min_length", 5)
        self.feedback_max_length = self.config.get("feedback_content_max_length", 1000)
        self.statistics_enabled = self.config.get("statistics_enabled", True)
        self.statistics_days = self.config.get("statistics_days", 7)
        self.session_timeout = self.config.get("session_timeout", 5)
        
        # 初始化通用配额系统
        self.db = None
        self.quota_validator = None
        self.membership_manager = None
        self.points_manager = None
        self.rate_limiter = None
        self.quota_reservation = None
        self.quota_analytics = None
        self.session_manager = None
        self.session_handler = None
        self.feedback_manager = None
        self.search_statistics = None
        self.message_pusher = None
        self.daily_report_generator = None
        self.system_available = QUOTA_SYSTEM_AVAILABLE
        
        # 读取每日报告配置（默认早上8点推送昨日报告）
        self.daily_report_enabled = self.config.get("daily_report_enabled", True)
        self.daily_report_time = self.config.get("daily_report_time", "08:00")
        self.daily_report_level = self.config.get("daily_report_level", "full")
        
        if self.system_available:
            try:
                # 获取数据路径
                data_path = self.context.get_config().get("data_path", "data")
                quota_db_path = os.path.join(data_path, "quota_system.db")
                
                # 初始化核心管理器
                self.db = DatabaseManager(quota_db_path)
                self.quota_validator = QuotaValidator(self.db)
                self.membership_manager = MembershipManager(self.db)
                self.points_manager = PointsManager(self.db)
                
                # 初始化优化模块
                self.rate_limiter = get_rate_limiter()
                self.quota_reservation = QuotaReservation(self.db, self.quota_validator)
                self.quota_analytics = QuotaAnalytics(self.db)
                
                # 初始化反馈管理器和搜索统计
                self.feedback_manager = FeedbackManager(self.db)
                self.search_statistics = SearchStatistics(self.db)
                
                # 初始化消息推送器
                self.message_pusher = get_message_pusher()
                
                # 初始化会话管理器（使用配置中的超时时间）
                self.session_manager = SessionManager(timeout_minutes=self.session_timeout)
                
                # 注册回调路由
                CallbackRouter.register("quota_admin", self.handle_callback, plugin_instance=self)
                logger.info("[QuotaAdmin] 已注册回调路由: quota_admin")
                
                # 初始化会话处理器
                self.session_handler = SessionHandler(
                    self.quota_validator,
                    self.membership_manager,
                    self.points_manager,
                    self.quota_analytics,
                    self.session_manager,
                    self.admins,
                    self.context  # 传入 context
                )
                
                # 初始化任务管理器（如果任务插件未启用）
                try:
                    from common.task_manager import get_task_manager
                    from common.task_tracker import get_task_tracker
                    
                    task_manager = get_task_manager(self.db, self.points_manager)
                    if task_manager:
                        # 初始化任务追踪器
                        get_task_tracker(task_manager)
                        logger.info("[QuotaAdmin] 任务管理器初始化成功")
                    else:
                        logger.debug("[QuotaAdmin] 任务管理器初始化跳过（可能由其他插件管理）")
                except Exception as e:
                    logger.debug(f"[QuotaAdmin] 任务管理器初始化失败: {e}")
                
                # 初始化错误追踪器
                try:
                    from common.error_tracker import get_error_tracker
                    get_error_tracker(self.db)
                    logger.info("[QuotaAdmin] 错误追踪器初始化成功")
                except Exception as e:
                    logger.debug(f"[QuotaAdmin] 错误追踪器初始化失败: {e}")
                
                # 初始化每日报告生成器
                try:
                    from common.daily_report import init_daily_report
                    
                    self.daily_report_generator = init_daily_report(
                        db=self.db,
                        search_statistics=self.search_statistics,
                        quota_analytics=self.quota_analytics,
                        session_handler=self.session_handler,
                        context=self.context,
                        config={
                            'enabled': self.daily_report_enabled,
                            'send_time': self.daily_report_time,
                            'report_level': self.daily_report_level,
                            'admin_ids': self.admins
                        }
                    )
                    logger.info(f"[QuotaAdmin] 每日报告初始化成功: enabled={self.daily_report_enabled}, time={self.daily_report_time}")
                    
                    # 注册定时任务
                    self._register_daily_report_task()
                except Exception as e:
                    logger.error(f"[QuotaAdmin] 每日报告初始化失败: {e}")
                
                logger.info(f"[QuotaAdmin] 通用配额系统初始化完成（标准化版本 v2.0）")
                logger.info(f"[QuotaAdmin] 配置的管理员列表: {self.admins}")
                logger.info(f"[QuotaAdmin] 会话超时时间: {self.session_timeout} 分钟")
                logger.info(f"[QuotaAdmin] 反馈功能: {'启用' if self.feedback_enabled else '禁用'}")
                logger.info(f"[QuotaAdmin] 通知推送: {'启用' if self.notification_enabled else '禁用'}")
            except Exception as e:
                logger.error(f"[QuotaAdmin] 通用配额系统初始化失败: {e}", exc_info=True)
                self.system_available = False
        else:
            logger.warning("[QuotaAdmin] 配额系统不可用，插件功能受限")
    
    def _check_system_available(self, event: AstrMessageEvent):
        """检查系统是否可用"""
        if not self.system_available:
            return False, "❌ 配额系统未初始化，请联系管理员"
        return True, None
    
    def _ensure_user_info(self, event: AstrMessageEvent):
        """确保用户信息被保存/更新"""
        if not self.system_available:
            return
        
        user_info = extract_user_info(event)
        # 调试日志
        logger.info(f"[QuotaAdmin] 提取用户信息: {user_info}")
        
        self.quota_validator._ensure_user_exists(
            user_id=user_info['user_id'],
            username=user_info['username'],
            platform=user_info['platform'],
            platform_user_id=user_info['platform_user_id']
        )
    
    def _is_admin(self, user_id: str, event: AstrMessageEvent = None) -> bool:
        """检查用户是否为管理员"""
        # 1. 检查插件配置
        if user_id in self.admins:
            return True
            
        # 2. 检查全局配置
        global_admins = self.context.get_config().get("admins_id", [])
        if user_id in global_admins:
            return True
            
        # 3. 检查事件对象
        if event and event.is_admin():
            return True
            
        return False
    
    def _get_plugin_admins(self) -> list:
        """获取插件配置中的管理员列表"""
        return self.admins
    
    # 管理员输入模式存储
    _admin_input_modes = {}
    _admin_input_data = {}
    
    def _set_admin_input_mode(self, user_id: str, mode: str, data: dict = None):
        """设置管理员输入模式"""
        self._admin_input_modes[user_id] = mode
        if data:
            self._admin_input_data[user_id] = data
    
    def _get_admin_input_mode(self, user_id: str) -> str:
        """获取管理员输入模式"""
        return self._admin_input_modes.get(user_id, "")
    
    def _get_admin_input_data(self, user_id: str) -> dict:
        """获取管理员输入模式的额外数据"""
        return self._admin_input_data.get(user_id, {})
    
    def _clear_admin_input_mode(self, user_id: str):
        """清除管理员输入模式"""
        if user_id in self._admin_input_modes:
            del self._admin_input_modes[user_id]
        if user_id in self._admin_input_data:
            del self._admin_input_data[user_id]
    
    # ==================== 每日报告定时任务 ====================
    
    def _register_daily_report_task(self):
        """注册每日报告定时任务"""
        if not self.daily_report_generator:
            return
        
        try:
            from common.scheduler import get_scheduler
            
            scheduler = get_scheduler(self.db)
            if not scheduler:
                logger.warning("[QuotaAdmin] 调度器不可用，无法注册每日报告任务")
                return
            
            # 解析时间
            hour, minute = 21, 0
            if self.daily_report_time:
                try:
                    parts = self.daily_report_time.split(":")
                    hour = int(parts[0])
                    minute = int(parts[1]) if len(parts) > 1 else 0
                except Exception:
                    pass
            
            # 注册定时任务
            scheduler.register_task(
                task_id="quota_admin:daily_report",
                plugin_name="quota_admin",
                cron=f"{minute} {hour} * * *",  # 每天指定时间
                handler=self._daily_report_task_handler,
                description="每日统计报告",
                enabled=self.daily_report_enabled
            )
            
            # 启动调度器（如果尚未启动）
            import asyncio
            if not scheduler._started:
                asyncio.get_event_loop().create_task(scheduler.start())
            
            logger.info(f"[QuotaAdmin] 每日报告任务已注册: {hour:02d}:{minute:02d}")
            
        except ImportError:
            logger.warning("[QuotaAdmin] 调度器模块未安装")
        except Exception as e:
            logger.error(f"[QuotaAdmin] 注册每日报告任务失败: {e}")
    
    async def _daily_report_task_handler(self, context=None):
        """每日报告定时任务处理函数"""
        if not self.daily_report_generator:
            logger.warning("[QuotaAdmin] 每日报告生成器未初始化")
            return
        
        await self.daily_report_generator.scheduled_send(context=self.context)
    
    def _update_daily_report_config(self, **kwargs):
        """更新每日报告配置"""
        if not self.daily_report_generator:
            return
        
        # 更新生成器配置
        self.daily_report_generator.update_config(kwargs)
        
        # 如果时间改变，重新注册任务
        if 'send_time' in kwargs:
            self.daily_report_time = kwargs['send_time']
            self._register_daily_report_task()
        
        # 更新实例属性
        if 'enabled' in kwargs:
            self.daily_report_enabled = kwargs['enabled']
            # 更新任务状态
            try:
                from common.scheduler import get_scheduler
                scheduler = get_scheduler(self.db)
                if scheduler:
                    if kwargs['enabled']:
                        scheduler.enable_task("quota_admin:daily_report")
                    else:
                        scheduler.disable_task("quota_admin:daily_report")
            except Exception:
                pass
        
        if 'report_level' in kwargs:
            self.daily_report_level = kwargs['report_level']
    
    # ==================== 深度链接处理 ====================
    
    @filter.command("start")
    async def handle_start_command(self, event: AstrMessageEvent):
        """处理 /start 深度链接（邀请系统）"""
        text = event.message_str or ""
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return  # 无参数，不处理
        
        param = parts[1].strip()
        
        # 邀请深度链接: inv_{invite_code}
        if param.startswith("inv_"):
            invite_code = param[4:]  # 去掉 "inv_" 前缀
            user_id = get_unified_user_id(event)
            
            try:
                from common.invite_manager import get_invite_manager
                from common.task_tracker import get_task_tracker, TaskTrigger
                
                invite_manager = get_invite_manager(self.db, self.points_manager)
                if not invite_manager:
                    yield event.plain_result("❌ 邀请系统暂不可用")
                    event.stop_event()
                    return
                
                success, msg = invite_manager.process_invite(user_id, invite_code)
                
                if success:
                    # 追踪任务进度
                    try:
                        tracker = get_task_tracker()
                        tracker.track(user_id, TaskTrigger.BIND_INVITE)
                    except Exception:
                        pass
                    
                    # 显示欢迎消息
                    welcome_msg = f"🎉 欢迎加入！\n\n{msg}\n\n"
                    welcome_msg += "💡 使用 /我 查看个人中心\n"
                    welcome_msg += "💡 使用 /帮助 查看功能列表"
                    yield event.plain_result(welcome_msg)
                else:
                    yield event.plain_result(f"❌ {msg}")
                
                event.stop_event()
                return
                
            except Exception as e:
                logger.error(f"[QuotaAdmin] 处理邀请深度链接失败: {e}")
                yield event.plain_result("❌ 处理失败，请稍后重试")
                event.stop_event()
                return
    
    # ==================== 用户命令 ====================
    
    @filter.command("我")
    @auto_stop_command
    async def my_info_cmd(self, event: AstrMessageEvent):
        """我的信息（跨平台统一交互）"""
        available, msg = self._check_system_available(event)
        if not available:
            yield event.plain_result(msg)
            return
        
        # 保存/更新用户信息
        self._ensure_user_info(event)
        
        user_id = get_unified_user_id(event)
        session_id = event.get_session_id()
        
        # 显示加载提示
        loading_msg_id = await LoadingIndicator.show(event, 'process')
        
        try:
            # 获取平台能力
            capabilities = get_platform_capabilities(event, "QuotaAdmin")
            
            # 创建响应构建器
            builder = QuotaAdminResponseBuilder(capabilities)
            
            # 获取用户信息
            user_info = await self._get_user_info(user_id)
            
            # 检查未读公告
            unread_announcements = await self.session_handler.get_unread_announcements(user_id)
            if unread_announcements:
                # 显示第一条未读公告
                ann = unread_announcements[0]
                ann_msg = f"📢 新公告\n\n{ann.get('content', '')}\n\n发布时间: {ann.get('created_at', '')[:10]}"
                yield event.plain_result(ann_msg)
                # 标记已读
                await self.session_handler.mark_announcement_read(user_id, ann['id'])
            
            # 构建响应
            message, keyboard = builder.build_my_info_menu(user_info, step=0)
            
            # 创建会话（按钮模式不需要会话，会话模式需要）
            if not capabilities['supports_buttons']:
                session = self.session_manager.create_session(
                    session_id=session_id,
                    session_type="my_info",
                    user_id=user_id,
                    capabilities=capabilities
                )
                logger.debug(f"[QuotaAdmin] 创建会话: {session_id}, type=my_info")
            
            # 飞书平台特殊处理
            if LarkMessageHelper.should_use_lark_helper(event):
                session = self.session_manager.get_session(session_id)
                message_id = await LarkMessageHelper.send_and_track(
                    event, message, session, auto_cleanup=True
                )
                if message_id:
                    logger.debug(f"[QuotaAdmin] 飞书消息发送成功: {message_id}")
                    return
            
            # 其他平台使用 MessageEditor
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
                
        finally:
            # 清理加载提示
            await LoadingIndicator.hide(event, loading_msg_id)
    
    
    # ==================== 管理员命令 ====================
    
    @filter.command("管理")
    @auto_stop_command
    async def admin_cmd(self, event: AstrMessageEvent):
        """管理员面板（跨平台统一交互）"""
        available, msg = self._check_system_available(event)
        if not available:
            yield event.plain_result(msg)
            return
        
        # 保存/更新用户信息
        self._ensure_user_info(event)
        
        user_id = get_unified_user_id(event)
        if not self._is_admin(user_id, event):
            yield event.plain_result("❌ 权限不足，仅管理员可用")
            return
        
        session_id = event.get_session_id()
        
        # 显示加载提示
        loading_msg_id = await LoadingIndicator.show(event, 'process')
        
        try:
            # 获取平台能力
            capabilities = get_platform_capabilities(event, "QuotaAdmin")
            
            # 创建响应构建器
            builder = QuotaAdminResponseBuilder(capabilities)
            
            # 获取统计数据
            stats = await self._get_admin_stats()
            
            # 构建响应
            message, keyboard = builder.build_admin_menu(stats, step=0)
            
            # 创建会话
            if not capabilities['supports_buttons']:
                session = self.session_manager.create_session(
                    session_id=session_id,
                    session_type="admin",
                    user_id=user_id,
                    capabilities=capabilities
                )
                logger.debug(f"[QuotaAdmin] 创建管理会话: {session_id}")
            
            # 飞书平台特殊处理
            if LarkMessageHelper.should_use_lark_helper(event):
                session = self.session_manager.get_session(session_id)
                message_id = await LarkMessageHelper.send_and_track(
                    event, message, session, auto_cleanup=True
                )
                if message_id:
                    return
            
            # 其他平台
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
                
        finally:
            await LoadingIndicator.hide(event, loading_msg_id)
    
    
    @filter.command("会员")
    @auto_stop_command
    async def membership_cmd(self, event: AstrMessageEvent):
        """会员介绍"""
        available, msg = self._check_system_available(event)
        if not available:
            yield event.plain_result(msg)
            return
        
        # 保存/更新用户信息
        self._ensure_user_info(event)
        
        user_id = get_unified_user_id(event)
        
        # 获取平台能力
        capabilities = get_platform_capabilities(event, "QuotaAdmin")
        builder = QuotaAdminResponseBuilder(capabilities)
        
        # 获取用户信息
        user_info = await self._get_user_info(user_id)
        
        # 构建响应
        message, keyboard = builder.build_membership_intro(user_info)
        
        async for result in MessageEditor.edit_or_send(event, message, keyboard):
            yield result
    
    @filter.command("帮助")
    @auto_stop_command
    async def help_cmd(self, event: AstrMessageEvent):
        """显示帮助信息"""
        user_id = get_unified_user_id(event)
        is_admin = self._is_admin(user_id, event)
        
        help_text = "📚 配额系统帮助\n\n"
        help_text += "👤 用户命令：\n"
        help_text += "/我 - 查询我的信息（配额/积分/会员/兑换）\n"
        help_text += "/会员 - 查看会员权益介绍\n"
        help_text += "/帮助 - 显示此帮助信息\n"
        
        if is_admin:
            help_text += "\n👑 管理员命令：\n"
            help_text += "/管理 - 管理面板（配额/积分/会员/统计/限流）\n"
        
        help_text += "\n💡 提示：\n"
        help_text += "- 支持按钮模式（Telegram/Discord）和会话模式（飞书/QQ等）\n"
        help_text += "- 积分可用于抵扣配额或兑换配额包\n"
        help_text += "- 会员享有更高的配额限制和限流倍率\n"
        help_text += "- 配额每日0点重置\n"
        help_text += "- 请求过于频繁会被限流，请合理使用\n"
        help_text += "- 回复 0 或 取消 可随时退出对话"
        
        yield event.plain_result(help_text)
    
    # ==================== 回调处理 ====================
    
    @filter.command("callback")
    @callback_handler("quota_admin")
    @auto_stop_event
    async def handle_callback(self, event: AstrMessageEvent, data: str = ""):
        """处理按钮回调"""
        available, msg = self._check_system_available(event)
        if not available:
            yield event.plain_result(msg)
            return
        
        # 保存/更新用户信息
        self._ensure_user_info(event)
        
        user_id = get_unified_user_id(event)
        session_id = event.get_session_id()
        
        # 从 event.message_str 中提取回调数据
        # 格式: "/callback quota_admin:action:sub_action" 或 JSON 格式（飞书）
        raw = event.message_str.strip()
        parts = raw.split(" ", 1)
        if len(parts) < 2:
            return
        
        callback_data = parts[1].strip()
        
        # 获取平台能力
        capabilities = get_platform_capabilities(event, "QuotaAdmin")
        builder = QuotaAdminResponseBuilder(capabilities)
        
        # 解析回调数据（支持 JSON 格式和传统格式）
        action = ""
        sub_action = ""
        params = {}
        
        if callback_data.startswith("{"):
            # JSON 格式（飞书）
            try:
                import json
                data = json.loads(callback_data)
                full_action = data.get("action", "")
                # 移除 quota_admin_ 前缀
                if full_action.startswith("quota_admin_"):
                    action = full_action[len("quota_admin_"):]
                else:
                    action = full_action
                params = {k: v for k, v in data.items() if k != "action"}
                logger.debug(f"[QuotaAdmin] JSON回调: action={action}, params={params}")
            except Exception as e:
                logger.error(f"[QuotaAdmin] 解析JSON回调失败: {e}")
                return
        else:
            # 传统格式: quota_admin:action:sub_action
            if callback_data.startswith("quota_admin:"):
                callback_data = callback_data[len("quota_admin:"):]
            
            parts = callback_data.split(":")
            action = parts[0] if parts else ""
            sub_action = parts[1] if len(parts) > 1 else ""
            # 将剩余部分作为参数
            if len(parts) > 2:
                params = {"extra": parts[2:]}
            logger.debug(f"[QuotaAdmin] 传统回调: action={action}, sub_action={sub_action}")
        
        try:
            if action == "back" or action == "home":
                # 返回主菜单
                user_info = await self._get_user_info(user_id)
                message, keyboard = builder.build_my_info_menu(user_info, step=0)
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "close":
                # 关闭菜单（尝试删除消息或显示已关闭）
                try:
                    platform_name = event.get_platform_name()
                    if platform_name == "telegram":
                        # Telegram 可以删除消息
                        chat_id = event.message_obj.group_id or event.get_sender_id()
                        callback_msg_id = getattr(event.message_obj, 'message_id', None)
                        if callback_msg_id:
                            await event.client.delete_message(chat_id=chat_id, message_id=int(callback_msg_id))
                            return
                except Exception as e:
                    logger.debug(f"[QuotaAdmin] 删除消息失败: {e}")
                yield event.plain_result("👋 已关闭")
            
            # ==================== 普通用户回调 ====================
            elif action == "quota_detail" or action == "1":
                # 查看配额详情
                quota_data = await self._get_quota_usage(user_id)
                message, keyboard = builder.build_quota_usage_response(quota_data, step=1)
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "points_history" or action == "2":
                # 查看积分流水
                transactions = await self.points_manager.get_transactions(user_id, limit=10)
                transactions_data = [dict(t) for t in transactions]
                message, keyboard = builder.build_points_transactions_response(transactions_data, step=1)
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "quota_boost" or action == "3":
                # 查看配额加成
                boosts = await self.points_manager.get_active_boosts(user_id)
                message, keyboard = builder.build_quota_boosts_response(boosts, step=1)
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "redeem_menu":
                # 兑换菜单
                packages = self.points_manager.get_boost_packages()
                balance = await self.points_manager.get_balance(user_id)
                message, keyboard = builder.build_redeem_menu(packages, balance, step=2)
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result

            elif action == "redeem":
                # 兑换配额包
                package_id = parts[1] if len(parts) > 1 else ""
                if package_id:
                    success, message = await self.points_manager.exchange_boost_package(user_id, package_id)
                    yield event.plain_result(message)
                else:
                    yield event.plain_result("❌ 无效的配额包")
            
            elif action == "checkin":
                # 直接执行签到，显示二级菜单
                try:
                    from astrbot_plugin_checkin.checkin_manager import CheckinManager
                    # CheckinManager 需要 db_manager, points_manager, config
                    checkin_config = {
                        'base_points': 10,
                        'streak_bonus': 5,
                        'lucky_rate': 0.1,
                        'lucky_bonus': 50
                    }
                    checkin_manager = CheckinManager(self.db, self.points_manager, checkin_config)
                    result = await checkin_manager.daily_checkin(user_id)
                    
                    # 显示签到结果页面（二级菜单）
                    message, keyboard = builder.build_checkin_result(result)
                    async for r in MessageEditor.edit_or_send(event, message, keyboard):
                        yield r
                except ImportError:
                    yield event.plain_result("📅 请使用 /签到 命令进行签到")
                except Exception as e:
                    logger.warning(f"[QuotaAdmin] 签到失败: {e}", exc_info=True)
                    # 显示错误页面（二级菜单）
                    message, keyboard = builder.build_checkin_result("❌ 签到失败，请稍后重试")
                    async for r in MessageEditor.edit_or_send(event, message, keyboard):
                        yield r
            
            elif action == "my_announcements":
                # 查看公告
                announcements = await self.session_handler.get_announcements(limit=5)
                message, keyboard = builder.build_announcements_list(announcements, is_admin=False)
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "help":
                # 帮助信息
                message, keyboard = builder.build_help_page()
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            # ==================== 任务系统回调 ====================
            elif action == "tasks":
                async for result in self._handle_tasks_callback(event, user_id, sub_action, builder):
                    yield result
            
            # ==================== 邀请系统回调 ====================
            elif action == "invite":
                async for result in self._handle_invite_callback(event, user_id, sub_action, builder):
                    yield result
            
            # ==================== 管理员回调 ====================
            elif action == "admin":
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return

                if sub_action == "user":
                    # 用户管理 - 显示用户列表
                    user_data = await self.session_handler._get_user_list(platform="all", page=1)
                    message, keyboard = builder.build_user_list(
                        users=user_data['users'],
                        page=user_data['page'],
                        total_pages=user_data['total_pages'],
                        total_count=user_data['total'],
                        current_platform="all",
                        platforms=user_data['platforms']
                    )
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result

                elif sub_action == "points":
                    # 积分管理 - 启动会话
                    msg = "💰 积分管理\n\n请输入充值信息\n格式: 用户ID 积分数 原因\n示例: user_qq_123456 100 活动奖励\n\n回复 0 退出"
                    self.session_manager.create_session(
                        session_id=session_id,
                        session_type="admin",
                        user_id=user_id,
                        step=1,
                        data={'action': 'points_mgmt'}
                    )
                    yield event.plain_result(msg)

                elif sub_action == "member":
                    # 会员管理 - 启动会话
                    msg = "👑 会员管理\n\n请输入升级信息\n格式: 用户ID 等级 天数\n等级: 1=高级 2=VIP\n示例: user_qq_123456 1 30\n\n回复 0 退出"
                    self.session_manager.create_session(
                        session_id=session_id,
                        session_type="admin",
                        user_id=user_id,
                        step=1,
                        data={'action': 'member_mgmt'}
                    )
                    yield event.plain_result(msg)

                elif sub_action == "stats":
                    # 详细统计
                    stats = await self.quota_analytics.get_usage_stats(days=7)
                    message, keyboard = builder.build_stats_detail(stats)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result

                elif sub_action == "rate":
                    # 限流状态
                    from common import get_rate_limiter
                    rate_limiter = get_rate_limiter()
                    r_stats = rate_limiter.get_stats()
                    message, keyboard = builder.build_rate_limit_status(r_stats)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "quota_manage":
                    # 配额管理菜单（默认显示统计）
                    quota_stats = await self.session_handler.get_quota_statistics()
                    message, keyboard = builder.build_quota_manage_menu(quota_stats)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "quota_rules":
                    # 配额规则
                    rules, plugins = await self.session_handler.get_quota_rules()
                    message, keyboard = builder.build_quota_rules_list(rules, plugins)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "points_stats":
                    # 积分统计
                    stats = await self.session_handler.get_points_stats()
                    message, keyboard = builder.build_points_stats(stats)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "search_stats":
                    # 搜索统计
                    stats = await self.session_handler.get_search_stats()
                    message, keyboard = builder.build_search_stats(stats)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "download_stats":
                    # 下载统计
                    stats = await self.session_handler.get_download_stats()
                    message, keyboard = builder.build_download_stats(stats)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "edit_quota":
                    # 编辑配额 - 显示插件列表
                    plugins = await self.session_handler.get_quota_plugins()
                    message, keyboard = builder.build_edit_quota_menu(plugins)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "blacklist":
                    # 黑名单管理
                    blacklist = await self.session_handler.get_blacklist()
                    message, keyboard = builder.build_blacklist_menu(blacklist)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "points_manage":
                    # 积分管理菜单（含统计数据）
                    points_stats = await self.session_handler.get_points_stats()
                    message, keyboard = builder.build_points_op_menu(points_stats)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "points_op":
                    # 积分操作菜单（兼容旧回调）
                    points_stats = await self.session_handler.get_points_stats()
                    message, keyboard = builder.build_points_op_menu(points_stats)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "data_stats":
                    # 数据统计子菜单（含使用统计）
                    usage_stats = await self.quota_analytics.get_usage_stats(days=7)
                    message, keyboard = builder.build_data_stats_menu(usage_stats)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "announce":
                    # 公告管理
                    announcements = await self.session_handler.get_announcements()
                    message, keyboard = builder.build_announce_menu(announcements)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "rate_config":
                    # 限流配置
                    from common.rate_limiter import get_rate_limiter
                    rate_limiter = get_rate_limiter()
                    config = rate_limiter.get_config()
                    message, keyboard = builder.build_rate_limit_config(config)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "system":
                    # 系统状态
                    status = await self.session_handler.get_system_status()
                    message, keyboard = builder.build_system_status(status)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "feedback":
                    # 反馈管理
                    logger.debug(f"[QuotaAdmin] 处理管理员反馈管理: user_id={user_id}")
                    result = self.feedback_manager.get_feedback_list(limit=10)
                    logger.debug(f"[QuotaAdmin] 反馈列表结果: {len(result['feedbacks'])} 条反馈, {result['pending_count']} 条待处理")
                    
                    message, keyboard = builder.build_admin_feedback_list(
                        feedbacks=result['feedbacks'],
                        pending_count=result['pending_count'],
                        total=result['total']
                    )
                    logger.debug(f"[QuotaAdmin] 构建的消息长度: {len(message)}")
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "active_stats":
                    # 活跃用户统计
                    stats = self.search_statistics.get_dashboard_stats(days=7)
                    message, keyboard = builder.build_active_users_stats(stats)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "scheduler":
                    # 定时任务管理
                    try:
                        from common.scheduler import get_scheduler
                        scheduler = get_scheduler(self.db)
                        tasks = scheduler.get_all_tasks()
                        # 获取最近的执行日志
                        recent_logs = scheduler.get_task_logs(limit=10)
                        message, keyboard = builder.build_scheduler_menu(tasks, recent_logs)
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    except ImportError:
                        yield event.plain_result("❌ 定时任务模块未安装")
                    except Exception as e:
                        logger.error(f"[QuotaAdmin] 获取定时任务失败: {e}")
                        yield event.plain_result(f"❌ 获取定时任务失败: {e}")
                
                elif sub_action == "plugin_ranking":
                    # 插件排行（复用活跃用户统计页面）
                    stats = self.search_statistics.get_dashboard_stats(days=7)
                    message, keyboard = builder.build_active_users_stats(stats)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "sub_config":
                    # 订阅配置管理
                    try:
                        from common.subscription_privileges import get_subscription_privilege_manager
                        privilege_manager = get_subscription_privilege_manager(db_manager=self.db)
                        configs = privilege_manager.get_all_level_configs()
                        message, keyboard = builder.build_subscription_config_menu(configs)
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    except Exception as e:
                        logger.error(f"[QuotaAdmin] 获取订阅配置失败: {e}")
                        yield event.plain_result(f"❌ 获取订阅配置失败: {e}")
                
                elif sub_action == "member_config":
                    # 会员权益配置
                    try:
                        from common.subscription_privileges import get_subscription_privilege_manager
                        privilege_manager = get_subscription_privilege_manager(db_manager=self.db)
                        configs = privilege_manager.get_all_level_configs()
                        message, keyboard = builder.build_member_config_menu(configs)
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    except Exception as e:
                        logger.error(f"[QuotaAdmin] 获取会员配置失败: {e}")
                        yield event.plain_result(f"❌ 获取会员配置失败: {e}")
                
                elif sub_action == "ad_manage":
                    # 广告管理
                    try:
                        from common.ad_manager import get_ad_manager
                        ad_manager = get_ad_manager(self.db)
                        ads = ad_manager.get_all_ads()
                        stats = ad_manager.get_stats()
                        message, keyboard = builder.build_ad_manage_menu(ads, stats)
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    except Exception as e:
                        logger.error(f"[QuotaAdmin] 获取广告列表失败: {e}")
                        yield event.plain_result(f"❌ 获取广告列表失败: {e}")
            
            # ==================== 每日报告回调 ====================
            elif action == "scheduler":
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                
                # 处理每日报告相关回调
                if sub_action == "daily_report":
                    # 获取额外参数
                    extra = params.get('extra', []) if params else []
                    
                    if not extra:
                        # 显示每日报告配置页面
                        if self.daily_report_generator:
                            config = self.daily_report_generator.get_config()
                            message, keyboard = builder.build_daily_report_config(config)
                            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                                yield result
                        else:
                            yield event.plain_result("❌ 每日报告模块未初始化")
                    
                    elif extra[0] == "toggle":
                        # 开启/关闭报告
                        enabled = bool(int(extra[1])) if len(extra) > 1 else True
                        self._update_daily_report_config(enabled=enabled)
                        
                        # 刷新页面
                        config = self.daily_report_generator.get_config()
                        message, keyboard = builder.build_daily_report_config(config)
                        status = "已启用" if enabled else "已禁用"
                        message = f"✅ 每日报告{status}\n\n" + message
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    
                    elif extra[0] == "time":
                        # 显示时间选择页面
                        current_time = self.daily_report_time
                        message, keyboard = builder.build_daily_report_time_select(current_time)
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    
                    elif extra[0] == "set_time":
                        # 设置发送时间
                        new_time = extra[1] if len(extra) > 1 else "21:00"
                        self._update_daily_report_config(send_time=new_time)
                        
                        # 刷新页面
                        config = self.daily_report_generator.get_config()
                        message, keyboard = builder.build_daily_report_config(config)
                        message = f"✅ 发送时间已设置为 {new_time}\n\n" + message
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    
                    elif extra[0] == "level":
                        # 显示级别选择页面
                        current_level = self.daily_report_level
                        message, keyboard = builder.build_daily_report_level_select(current_level)
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    
                    elif extra[0] == "set_level":
                        # 设置报告级别
                        new_level = extra[1] if len(extra) > 1 else "full"
                        self._update_daily_report_config(report_level=new_level)
                        
                        # 刷新页面
                        level_name = "简报" if new_level == "brief" else "完整报告"
                        config = self.daily_report_generator.get_config()
                        message, keyboard = builder.build_daily_report_config(config)
                        message = f"✅ 报告级别已设置为{level_name}\n\n" + message
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    
                    elif extra[0] == "preview":
                        # 预览报告
                        if self.daily_report_generator:
                            try:
                                report = await self.daily_report_generator.generate_report()
                                message, keyboard = builder.build_daily_report_preview(report)
                                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                                    yield result
                            except Exception as e:
                                logger.error(f"[QuotaAdmin] 生成报告预览失败: {e}")
                                yield event.plain_result(f"❌ 生成报告失败: {e}")
                        else:
                            yield event.plain_result("❌ 每日报告模块未初始化")
                    
                    elif extra[0] == "send":
                        # 立即发送
                        if self.daily_report_generator:
                            # 显示加载提示
                            loading_msg_id = await LoadingIndicator.show(event, 'process', "正在生成并发送报告...")
                            try:
                                results = await self.daily_report_generator.send_to_admins()
                                message, keyboard = builder.build_daily_report_send_result(results)
                                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                                    yield result
                            except Exception as e:
                                logger.error(f"[QuotaAdmin] 发送报告失败: {e}")
                                yield event.plain_result(f"❌ 发送失败: {e}")
                            finally:
                                # 清理加载提示
                                await LoadingIndicator.hide(event, loading_msg_id)
                        else:
                            yield event.plain_result("❌ 每日报告模块未初始化")
            
            # ==================== 订阅配置回调 ====================
            elif action == "sub_config":
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                
                from common.subscription_privileges import get_subscription_privilege_manager, MemberLevel
                privilege_manager = get_subscription_privilege_manager(db_manager=self.db)
                
                if sub_action == "edit":
                    # 编辑指定等级的订阅配置
                    extra = params.get('extra', []) if params else []
                    level = int(extra[0]) if extra else 0
                    config = privilege_manager.get_all_level_configs().get(level, {})
                    message, keyboard = builder.build_subscription_config_edit(level, config)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "set_limit":
                    # 设置订阅数量限制
                    # 格式: sub_config:set_limit:level:value
                    extra = params.get('extra', []) if params else []
                    level = int(extra[0]) if len(extra) > 0 else 0
                    value = int(extra[1]) if len(extra) > 1 else 3
                    
                    member_level = MemberLevel(level)
                    success = privilege_manager.update_subscription_limit(member_level, value)
                    
                    if success:
                        # 刷新显示
                        config = privilege_manager.get_all_level_configs().get(level, {})
                        message, keyboard = builder.build_subscription_config_edit(level, config)
                        message = f"✅ 已设置订阅数量: {'无限' if value == -1 else f'{value}个'}\n\n" + message
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    else:
                        yield event.plain_result("❌ 设置失败")
                
                elif sub_action == "set_access":
                    # 设置访问权限
                    # 格式: sub_config:set_access:level:0,1,2
                    extra = params.get('extra', []) if params else []
                    level = int(extra[0]) if len(extra) > 0 else 0
                    access_str = extra[1] if len(extra) > 1 else "0"
                    access_levels = [int(x) for x in access_str.split(',')]
                    
                    member_level = MemberLevel(level)
                    success = privilege_manager.update_source_access(member_level, access_levels)
                    
                    if success:
                        # 刷新显示
                        config = privilege_manager.get_all_level_configs().get(level, {})
                        message, keyboard = builder.build_subscription_config_edit(level, config)
                        message = "✅ 已更新访问权限\n\n" + message
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    else:
                        yield event.plain_result("❌ 设置失败")
            
            # ==================== 会员配置回调 ====================
            elif action == "member_config":
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                
                from common.subscription_privileges import get_subscription_privilege_manager, MemberLevel
                privilege_manager = get_subscription_privilege_manager(db_manager=self.db)
                
                if sub_action == "edit":
                    # 编辑指定等级的会员权益
                    extra = params.get('extra', []) if params else []
                    level = int(extra[0]) if extra else 0
                    config = privilege_manager.get_all_level_configs().get(level, {})
                    message, keyboard = builder.build_member_config_edit(level, config)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "set_ad":
                    # 设置广告开关
                    extra = params.get('extra', []) if params else []
                    level = int(extra[0]) if len(extra) > 0 else 0
                    value = bool(int(extra[1])) if len(extra) > 1 else True
                    
                    member_level = MemberLevel(level)
                    config = privilege_manager._get_level_config(member_level)
                    config['ad_enabled'] = value
                    success = privilege_manager.update_level_config(member_level, config)
                    
                    if success:
                        config = privilege_manager.get_all_level_configs().get(level, {})
                        message, keyboard = builder.build_member_config_edit(level, config)
                        message = f"✅ 已{'开启' if value else '关闭'}广告\n\n" + message
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    else:
                        yield event.plain_result("❌ 设置失败")
                
                elif sub_action == "set_custom_time":
                    # 设置自定义推送时间
                    extra = params.get('extra', []) if params else []
                    level = int(extra[0]) if len(extra) > 0 else 0
                    value = bool(int(extra[1])) if len(extra) > 1 else False
                    
                    member_level = MemberLevel(level)
                    config = privilege_manager._get_level_config(member_level)
                    config['custom_push_time'] = value
                    success = privilege_manager.update_level_config(member_level, config)
                    
                    if success:
                        config = privilege_manager.get_all_level_configs().get(level, {})
                        message, keyboard = builder.build_member_config_edit(level, config)
                        message = f"✅ 已{'启用' if value else '禁用'}自定义推送时间\n\n" + message
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    else:
                        yield event.plain_result("❌ 设置失败")
                
                elif sub_action == "set_priority":
                    # 设置优先推送
                    extra = params.get('extra', []) if params else []
                    level = int(extra[0]) if len(extra) > 0 else 0
                    value = bool(int(extra[1])) if len(extra) > 1 else False
                    
                    member_level = MemberLevel(level)
                    config = privilege_manager._get_level_config(member_level)
                    config['priority_push'] = value
                    success = privilege_manager.update_level_config(member_level, config)
                    
                    if success:
                        config = privilege_manager.get_all_level_configs().get(level, {})
                        message, keyboard = builder.build_member_config_edit(level, config)
                        message = f"✅ 已{'开启' if value else '关闭'}优先推送\n\n" + message
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    else:
                        yield event.plain_result("❌ 设置失败")
                
                elif sub_action == "set_history":
                    # 设置历史保留天数
                    extra = params.get('extra', []) if params else []
                    level = int(extra[0]) if len(extra) > 0 else 0
                    value = int(extra[1]) if len(extra) > 1 else 7
                    
                    member_level = MemberLevel(level)
                    config = privilege_manager._get_level_config(member_level)
                    config['history_days'] = value
                    success = privilege_manager.update_level_config(member_level, config)
                    
                    if success:
                        config = privilege_manager.get_all_level_configs().get(level, {})
                        message, keyboard = builder.build_member_config_edit(level, config)
                        history_str = '永久' if value == -1 else f'{value}天'
                        message = f"✅ 已设置历史保留: {history_str}\n\n" + message
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    else:
                        yield event.plain_result("❌ 设置失败")
            
            # ==================== 广告管理回调 ====================
            elif action == "ad":
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                
                from common.ad_manager import get_ad_manager
                ad_manager = get_ad_manager(self.db)
                
                if sub_action == "detail":
                    # 查看广告详情
                    extra = params.get('extra', []) if params else []
                    ad_id = int(extra[0]) if extra else 0
                    ad = ad_manager.get_ad(ad_id)
                    if ad:
                        message, keyboard = builder.build_ad_detail(ad)
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    else:
                        yield event.plain_result("❌ 广告不存在")
                
                elif sub_action == "toggle":
                    # 切换广告状态
                    extra = params.get('extra', []) if params else []
                    ad_id = int(extra[0]) if extra else 0
                    new_state = ad_manager.toggle_ad(ad_id)
                    if new_state is not None:
                        status_text = '启用' if new_state else '暂停'
                        ad = ad_manager.get_ad(ad_id)
                        message, keyboard = builder.build_ad_detail(ad)
                        message = f"✅ 已{status_text}广告 #{ad_id}\n\n" + message
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    else:
                        yield event.plain_result("❌ 操作失败")
                
                elif sub_action == "weight":
                    # 设置权重
                    extra = params.get('extra', []) if params else []
                    ad_id = int(extra[0]) if len(extra) > 0 else 0
                    weight = int(extra[1]) if len(extra) > 1 else 1
                    success = ad_manager.update_ad(ad_id, weight=weight)
                    if success:
                        ad = ad_manager.get_ad(ad_id)
                        message, keyboard = builder.build_ad_detail(ad)
                        message = f"✅ 已设置权重为 {weight}\n\n" + message
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    else:
                        yield event.plain_result("❌ 设置失败")
                
                elif sub_action == "delete":
                    # 删除广告
                    extra = params.get('extra', []) if params else []
                    ad_id = int(extra[0]) if extra else 0
                    success = ad_manager.delete_ad(ad_id)
                    if success:
                        # 返回列表
                        ads = ad_manager.get_all_ads()
                        stats = ad_manager.get_stats()
                        message, keyboard = builder.build_ad_manage_menu(ads, stats)
                        message = f"✅ 已删除广告 #{ad_id}\n\n" + message
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    else:
                        yield event.plain_result("❌ 删除失败")
                
                elif sub_action == "add":
                    # 进入添加模式
                    self._set_admin_input_mode(user_id, "ad_add", {})
                    message, keyboard = builder.build_ad_add_prompt()
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "edit":
                    # 进入编辑模式
                    extra = params.get('extra', []) if params else []
                    ad_id = int(extra[0]) if extra else 0
                    ad = ad_manager.get_ad(ad_id)
                    if ad:
                        self._set_admin_input_mode(user_id, "ad_edit", {"ad_id": ad_id})
                        message, keyboard = builder.build_ad_edit_prompt(ad)
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    else:
                        yield event.plain_result("❌ 广告不存在")
            
            # ==================== 用户详情回调 ====================
            elif action == "user_detail":
                # 查看用户详情
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                target_user_id = sub_action
                detail = await self.session_handler.get_user_detail(target_user_id)
                message, keyboard = builder.build_user_detail(
                    detail['user_info'], detail['membership'], 
                    detail['points'], detail['quota_usage']
                )
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "member_edit":
                # 编辑会员等级
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                target_user_id = sub_action
                membership = await self.membership_manager.get_membership_info(target_user_id)
                current_level = membership.get('level', 0) if membership else 0
                if hasattr(current_level, 'value'):
                    current_level = current_level.value
                expire_date = membership.get('expire_date') if membership else None
                message, keyboard = builder.build_member_edit_menu(target_user_id, current_level, expire_date)
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "set_member":
                # 设置会员等级
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                # 格式: set_member:user_id:level
                target_user_id = sub_action
                extra = params.get('extra', []) if params else []
                level = int(extra[0]) if extra else 0
                # 使用默认1个月
                success = await self.session_handler.set_user_membership(target_user_id, level, 1)
                if success:
                    level_names = {0: "免费用户", 1: "高级会员", 2: "VIP会员"}
                    yield event.plain_result(f"✅ 已将用户 {target_user_id} 设为 {level_names.get(level, '未知')}")
                else:
                    yield event.plain_result("❌ 设置失败")
            
            elif action == "member_duration":
                # 设置会员时长
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                # 格式: member_duration:user_id:months
                target_user_id = sub_action
                extra = params.get('extra', []) if params else []
                months = int(extra[0]) if extra else 1
                # 获取当前等级，续期
                membership = await self.membership_manager.get_membership_info(target_user_id)
                current_level = membership.get('level', 1) if membership else 1
                if hasattr(current_level, 'value'):
                    current_level = current_level.value
                if current_level == 0:
                    current_level = 1  # 免费用户升级为高级
                success = await self.session_handler.set_user_membership(target_user_id, current_level, months)
                if success:
                    yield event.plain_result(f"✅ 已为用户 {target_user_id} 续期 {months} 个月")
                else:
                    yield event.plain_result("❌ 续期失败")
            
            elif action == "points_add":
                # 快捷充值积分（从用户详情页）
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                target_user_id = sub_action
                # 设置输入模式
                self._set_admin_input_mode(user_id, "points_add_user", {"target_user": target_user_id})
                message, keyboard = builder.build_points_input_prompt("add_single", target_user_id)
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            # ==================== 限流配置回调 ====================
            elif action == "rate_edit":
                # 编辑限流配置
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                category = sub_action
                from common.rate_limiter import get_rate_limiter
                rate_limiter = get_rate_limiter()
                config = rate_limiter.get_config()
                limits = config.get('default_limits', {})
                current = limits.get(category, (60, 60))
                message, keyboard = builder.build_rate_edit_form(category, current[0], current[1])
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "rate_set":
                # 设置限流
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                # 格式: rate_set:category:max_req:window
                category = sub_action
                extra = params.get('extra', []) if params else []
                max_req = int(extra[0]) if len(extra) > 0 else 60
                window = int(extra[1]) if len(extra) > 1 else 60
                from common.rate_limiter import get_rate_limiter
                rate_limiter = get_rate_limiter()
                rate_limiter.update_limit(category, max_req, window)
                yield event.plain_result(f"✅ 已更新 {category} 限流: {max_req}次/{window}秒")
            
            # ==================== 配额规则编辑回调 ====================
            elif action == "edit_plugin":
                # 编辑指定插件的配额规则
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                plugin = sub_action
                rules = await self.session_handler.get_plugin_quota_rules(plugin)
                message, keyboard = builder.build_edit_quota_rules(plugin, rules)
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "edit_rule":
                # 编辑单条规则
                # 回调格式: edit_rule:plugin:action_type
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                # sub_action 是 plugin，extra[0] 是 action_type
                plugin = sub_action
                action_type = params.get('extra', [''])[0] if params else ''
                if plugin and action_type:
                    rule = await self.session_handler.get_quota_rule(plugin, action_type)
                    if rule:
                        message, keyboard = builder.build_edit_rule_form(plugin, action_type, rule)
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    else:
                        yield event.plain_result(f"❌ 未找到规则: {plugin}.{action_type}")
            
            elif action == "set_rule":
                # 快捷设置规则
                # 回调格式: set_rule:plugin:action_type:setting
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                # sub_action 是 plugin，extra[0] 是 action_type，extra[1] 是 setting
                plugin = sub_action
                extra = params.get('extra', []) if params else []
                action_type = extra[0] if len(extra) > 0 else ''
                setting = extra[1] if len(extra) > 1 else ''
                
                if plugin and action_type and setting:
                    if setting == "unlimited":
                        success = await self.session_handler.set_rule_unlimited(plugin, action_type)
                        msg = "✅ 已设置为无限制" if success else "❌ 设置失败"
                    else:
                        success = await self.session_handler.set_rule_limited(plugin, action_type)
                        msg = "✅ 已恢复默认限制" if success else "❌ 设置失败"
                    
                    # 刷新显示
                    rule = await self.session_handler.get_quota_rule(plugin, action_type)
                    if rule:
                        message, keyboard = builder.build_edit_rule_form(plugin, action_type, rule)
                        message = msg + "\n\n" + message
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
            
            # ==================== 黑名单回调 ====================
            elif action == "blacklist":
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                
                if sub_action == "add":
                    # 进入添加黑名单模式
                    self._set_admin_input_mode(user_id, "blacklist_add")
                    yield event.plain_result("🚫 添加黑名单\n\n请输入: 用户ID 原因\n示例: user123 恶意刷量")
                
                elif sub_action.startswith("remove:"):
                    # 解封用户
                    target_user = sub_action[7:]
                    success = await self.session_handler.remove_from_blacklist(target_user)
                    msg = f"✅ 已解封用户 {target_user}" if success else "❌ 解封失败"
                    blacklist = await self.session_handler.get_blacklist()
                    message, keyboard = builder.build_blacklist_menu(blacklist)
                    message = msg + "\n\n" + message
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action.startswith("page:"):
                    # 翻页
                    page = int(sub_action[5:])
                    blacklist = await self.session_handler.get_blacklist()
                    message, keyboard = builder.build_blacklist_menu(blacklist, page)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
            
            # ==================== 积分操作回调 ====================
            elif action == "points":
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                
                if sub_action in ["add_single", "add_batch", "deduct"]:
                    # 进入输入模式
                    self._set_admin_input_mode(user_id, f"points_{sub_action}")
                    message, keyboard = builder.build_points_input_prompt(sub_action)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
            
            # ==================== 公告回调 ====================
            elif action == "announce":
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                
                if sub_action == "new":
                    # 进入公告输入模式
                    self._set_admin_input_mode(user_id, "announce_new")
                    message, keyboard = builder.build_announce_input_prompt()
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
            
            # ==================== 用户管理回调 ====================
            elif action == "user_page":
                # 用户列表翻页
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                
                # 支持 JSON 格式和传统格式
                page = params.get('page', 1) if params else (int(sub_action) if sub_action.isdigit() else 1)
                platform = params.get('platform', 'all') if params else (params.get('extra', ['all'])[0] if params.get('extra') else 'all')
                
                user_data = await self.session_handler._get_user_list(platform=platform, page=page)
                message, keyboard = builder.build_user_list(
                    users=user_data['users'],
                    page=user_data['page'],
                    total_pages=user_data['total_pages'],
                    total_count=user_data['total'],
                    current_platform=platform,
                    platforms=user_data['platforms']
                )
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "user_platform":
                # 显示平台选择器
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                
                user_data = await self.session_handler._get_user_list(platform="all", page=1)
                message, keyboard = builder.build_platform_selector(
                    platforms=user_data['platforms'],
                    current="all"
                )
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "user_filter":
                # 按平台筛选
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                
                # 支持 JSON 格式和传统格式
                platform = params.get('platform', 'all') if params else (sub_action or "all")
                user_data = await self.session_handler._get_user_list(platform=platform, page=1)
                message, keyboard = builder.build_user_list(
                    users=user_data['users'],
                    page=user_data['page'],
                    total_pages=user_data['total_pages'],
                    total_count=user_data['total'],
                    current_platform=platform,
                    platforms=user_data['platforms']
                )
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "user_detail":
                # 用户详情
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                
                # 支持 JSON 格式和传统格式
                target_user_id = params.get('user_id', '') if params else sub_action
                if not target_user_id and len(parts) > 1:
                    # 用户ID可能包含冒号，需要重新拼接
                    target_user_id = ":".join(parts[1:])
                
                user_info = await self.session_handler._get_user_detail(target_user_id)
                if not user_info:
                    yield event.plain_result(f"❌ 用户不存在: {target_user_id}")
                    return
                
                message, keyboard = builder.build_user_detail(user_info)
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "points_add":
                # 积分充值入口
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                
                # 支持 JSON 格式和传统格式
                target_user_id = params.get('user_id', '') if params else sub_action
                if not target_user_id and len(parts) > 1:
                    target_user_id = ":".join(parts[1:])
                
                separator = get_separator()
                msg = f"💰 为用户充值积分\n\n"
                msg += f"目标用户: {target_user_id}\n\n"
                msg += "请输入: 积分数 原因\n"
                msg += "示例: 100 活动奖励\n"
                msg += f"{separator}\n"
                msg += "💡 回复 0 取消"
                
                self.session_manager.create_session(
                    session_id=session_id,
                    session_type="admin",
                    user_id=user_id,
                    step=1,
                    data={'action': 'points_add', 'target_user_id': target_user_id}
                )
                yield event.plain_result(msg)
            
            elif action == "member_up":
                # 会员升级入口
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                
                # 支持 JSON 格式和传统格式
                target_user_id = params.get('user_id', '') if params else sub_action
                if not target_user_id and len(parts) > 1:
                    target_user_id = ":".join(parts[1:])
                
                separator = get_separator()
                msg = f"👑 为用户升级会员\n\n"
                msg += f"目标用户: {target_user_id}\n\n"
                msg += "请输入: 等级 天数\n"
                msg += "等级: 1=高级 2=VIP\n"
                msg += "示例: 1 30\n"
                msg += f"{separator}\n"
                msg += "💡 回复 0 取消"
                
                self.session_manager.create_session(
                    session_id=session_id,
                    session_type="admin",
                    user_id=user_id,
                    step=1,
                    data={'action': 'member_up', 'target_user_id': target_user_id}
                )
                yield event.plain_result(msg)
            
            elif action == "user_search":
                # 用户搜索入口
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                
                # 显示搜索提示，并创建搜索会话
                message, keyboard = builder.build_search_prompt()
                
                self.session_manager.create_session(
                    session_id=session_id,
                    session_type="admin",
                    user_id=user_id,
                    step=1,
                    data={'action': 'user_search'},
                    capabilities=capabilities
                )
                
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "admin_back":
                # 返回管理员主菜单
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                
                stats = await self._get_admin_stats()
                message, keyboard = builder.build_admin_menu(stats)
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "quota_filter":
                # 配额规则筛选
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                
                plugin = params.get('plugin', 'all') if params else (sub_action or "all")
                rules, plugins = await self.session_handler.get_quota_rules(plugin)
                message, keyboard = builder.build_quota_rules_list(rules, plugins, plugin)
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "quota_manage":
                # 配额管理菜单
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                
                message, keyboard = builder.build_quota_manage_menu()
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "quota_stats":
                # 配额使用统计
                if not self._is_admin(user_id, event):
                    yield event.plain_result("❌ 权限不足")
                    return
                
                quota_stats = await self.session_handler.get_quota_statistics()
                message, keyboard = builder.build_quota_stats_menu(quota_stats)
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            # ==================== 用户反馈回调 ====================
            elif action == "feedback_menu":
                # 用户反馈菜单
                # 如果有活跃的反馈会话，先结束它
                session = self.session_manager.get_session(session_id)
                if session and session.get('type') == 'feedback':
                    self.session_manager.end_session(session_id)
                    logger.debug(f"[QuotaAdmin] 已结束反馈会话: {session_id}")
                
                message, keyboard = builder.build_feedback_type_menu()
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "my_feedbacks":
                # 我的反馈列表
                feedbacks = self.feedback_manager.get_user_feedbacks(user_id, limit=10)
                message, keyboard = builder.build_my_feedbacks(feedbacks, user_id)
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
            
            elif action == "feedback":
                # 反馈相关操作
                if sub_action == "type":
                    # 选择反馈类型，进入输入模式
                    extra = params.get('extra', []) if params else []
                    feedback_type = extra[0] if extra else "suggestion"
                    
                    # 获取当前消息ID（回调消息，即将被编辑为输入提示）
                    callback_msg_id = getattr(event.message_obj, 'message_id', None)
                    
                    # 创建会话等待用户输入，保存消息ID用于后续编辑
                    self.session_manager.create_session(
                        session_id=session_id,
                        session_type="feedback",
                        user_id=user_id,
                        step=1,
                        data={
                            'feedback_type': feedback_type,
                            'input_message_id': callback_msg_id  # 保存消息ID
                        },
                        capabilities=capabilities
                    )
                    
                    message, keyboard = builder.build_feedback_input_prompt(feedback_type)
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        yield result
                
                elif sub_action == "detail":
                    # 查看反馈详情
                    extra = params.get('extra', []) if params else []
                    feedback_id = int(extra[0]) if extra else 0
                    
                    feedback = self.feedback_manager.get_feedback_by_id(feedback_id)
                    if feedback:
                        is_admin = self._is_admin(user_id, event)
                        message, keyboard = builder.build_feedback_detail(feedback, is_admin)
                        async for result in MessageEditor.edit_or_send(event, message, keyboard):
                            yield result
                    else:
                        yield event.plain_result("❌ 反馈不存在")
                
                elif sub_action == "filter":
                    # 管理员筛选反馈
                    if not self._is_admin(user_id, event):
                        yield event.plain_result("❌ 权限不足")
                        return
                    
                    extra = params.get('extra', []) if params else []
                    status = extra[0] if extra else None
                    if status == "all":
                        status = None
                    
                    result = self.feedback_manager.get_feedback_list(status=status, limit=10)
                    message, keyboard = builder.build_admin_feedback_list(
                        feedbacks=result['feedbacks'],
                        pending_count=result['pending_count'],
                        total=result['total'],
                        current_status=status or "all"
                    )
                    async for r in MessageEditor.edit_or_send(event, message, keyboard):
                        yield r
                
                elif sub_action == "page":
                    # 管理员翻页
                    if not self._is_admin(user_id, event):
                        yield event.plain_result("❌ 权限不足")
                        return
                    
                    extra = params.get('extra', []) if params else []
                    page = int(extra[0]) if extra else 1
                    status = extra[1] if len(extra) > 1 else None
                    if status == "all":
                        status = None
                    
                    result = self.feedback_manager.get_feedback_list(status=status, limit=10, offset=(page-1)*10)
                    message, keyboard = builder.build_admin_feedback_list(
                        feedbacks=result['feedbacks'],
                        pending_count=result['pending_count'],
                        total=result['total'],
                        current_status=status or "all",
                        page=page
                    )
                    async for r in MessageEditor.edit_or_send(event, message, keyboard):
                        yield r
                
                elif sub_action == "resolve":
                    # 标记已解决
                    if not self._is_admin(user_id, event):
                        yield event.plain_result("❌ 权限不足")
                        return
                    
                    extra = params.get('extra', []) if params else []
                    feedback_id = int(extra[0]) if extra else 0
                    
                    success = self.feedback_manager.update_status(feedback_id, "resolved")
                    if success:
                        # 通知用户
                        feedback = self.feedback_manager.get_feedback_by_id(feedback_id)
                        if feedback:
                            await self._notify_feedback_user(event, feedback, "resolved")
                        
                        yield event.plain_result("✅ 已标记为已解决")
                        # 刷新详情页
                        feedback = self.feedback_manager.get_feedback_by_id(feedback_id)
                        if feedback:
                            message, keyboard = builder.build_feedback_detail(feedback, True)
                            async for r in MessageEditor.edit_or_send(event, message, keyboard):
                                yield r
                    else:
                        yield event.plain_result("❌ 操作失败")
                
                elif sub_action == "reject":
                    # 标记拒绝
                    if not self._is_admin(user_id, event):
                        yield event.plain_result("❌ 权限不足")
                        return
                    
                    extra = params.get('extra', []) if params else []
                    feedback_id = int(extra[0]) if extra else 0
                    
                    success = self.feedback_manager.update_status(feedback_id, "rejected")
                    if success:
                        yield event.plain_result("✅ 已标记为已拒绝")
                        feedback = self.feedback_manager.get_feedback_by_id(feedback_id)
                        if feedback:
                            message, keyboard = builder.build_feedback_detail(feedback, True)
                            async for r in MessageEditor.edit_or_send(event, message, keyboard):
                                yield r
                    else:
                        yield event.plain_result("❌ 操作失败")
                
                elif sub_action == "reply":
                    # 进入回复模式
                    if not self._is_admin(user_id, event):
                        yield event.plain_result("❌ 权限不足")
                        return
                    
                    extra = params.get('extra', []) if params else []
                    feedback_id = int(extra[0]) if extra else 0
                    
                    # 获取当前消息ID（回调消息，即将被编辑为回复提示）
                    callback_msg_id = getattr(event.message_obj, 'message_id', None)
                    
                    # 创建会话等待输入，保存消息ID用于后续编辑
                    self.session_manager.create_session(
                        session_id=session_id,
                        session_type="admin_feedback_reply",
                        user_id=user_id,
                        step=1,
                        data={
                            'feedback_id': feedback_id,
                            'reply_message_id': callback_msg_id  # 保存消息ID
                        },
                        capabilities=capabilities
                    )
                    
                    message, keyboard = builder.build_feedback_reply_prompt(feedback_id)
                    async for r in MessageEditor.edit_or_send(event, message, keyboard):
                        yield r
            
            
            elif action == "noop":
                # 空操作（用于显示页码等）
                pass

            else:
                logger.warning(f"[QuotaAdmin] 未知的回调操作: {action}")
                yield event.plain_result("❌ 未知的操作")
                
        except Exception as e:
            logger.error(f"[QuotaAdmin] 处理回调失败: {e}", exc_info=True)
            yield event.plain_result("❌ 操作失败，请稍后重试")
    
    # ==================== 会话处理 ====================
    
    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """处理会话中的消息"""
        # 无论是否处理消息，都先确保用户信息被保存/更新
        # 这样即使其他插件（如 douban）处理了消息，我们也能更新用户信息
        self._ensure_user_info(event)
        
        # 如果事件已经有结果，不处理
        if event.get_result():
            return  # 没有会话，不处理
        
        # 如果是命令，不处理
        message_str = event.message_str or ""
        if message_str.startswith("/"):
            return
        
        # 如果是回调消息，不处理
        if message_str.startswith("callback "):
            return
        
        # 检查是否有活跃会话
        session_id = event.get_session_id()
        session = self.session_manager.get_session(session_id, renew=True)
        
        if not session:
            return  # 没有会话，不处理
        
        # 保存/更新用户信息
        self._ensure_user_info(event)
        
        logger.info(f"[QuotaAdmin] 处理会话消息: session_id={session_id}, message={message_str}")
        
        # 检查系统可用性
        available, msg = self._check_system_available(event)
        if not available:
            yield event.plain_result(msg)
            event.stop_event()
            return
        
        # 检查会话类型，反馈会话由专门的方法处理
        session_type = session.get('type', '')
        if session_type in ['feedback', 'admin_feedback_reply']:
            # 反馈会话由 handle_feedback_session 方法处理
            return
        
        # 处理其他类型的会话消息
        result = await self.session_handler.handle_session_message(
            session_id, message_str, session,
            feedback_manager=self.feedback_manager
        )
        
        if result:
            # 处理返回值（可能是2个或3个元素）
            if len(result) == 3:
                message, keyboard, extra_data = result
            else:
                message, keyboard = result
                extra_data = None
            
            # 检查是否退出
            if message == "👋 已退出":
                # 飞书平台清理消息
                if LarkMessageHelper.should_use_lark_helper(event):
                    await LarkMessageHelper.cleanup_on_exit(event, session)
                
                # 删除会话
                self.session_manager.end_session(session_id)
                logger.debug(f"[QuotaAdmin] 会话已结束: {session_id}")
            
            # 检查是否需要通知管理员（反馈提交成功）
            if extra_data and extra_data.get('action') == 'feedback_submitted':
                await self._notify_admins_new_feedback(
                    event,
                    extra_data['feedback_id'],
                    extra_data['user_id'],
                    extra_data['feedback_type'],
                    extra_data['content']
                )
            
            # 飞书平台特殊处理
            if LarkMessageHelper.should_use_lark_helper(event):
                message_id = await LarkMessageHelper.send_and_track(
                    event, message, session, auto_cleanup=True
                )
                if message_id:
                    event.stop_event()
                    return
            
            # 其他平台
            async for res in MessageEditor.edit_or_send(event, message, keyboard):
                yield res
            
            event.stop_event()
    
    # ==================== 辅助方法 ====================
    
    async def _get_user_info(self, user_id: str) -> dict:
        """获取用户信息"""
        # 获取会员信息
        membership = await self.membership_manager.get_membership_info(user_id)
        
        # 获取积分信息
        points = await self.points_manager.get_account_info(user_id)
        points_balance = points.get('balance', 0) if points else 0
        
        # 获取配额使用情况
        quota_usage = await self._get_quota_usage(user_id)
        
        # 获取签到连续天数
        checkin_days = 0
        try:
            checkin_result = self.db.execute_one("""
                SELECT streak_days FROM checkin_records 
                WHERE user_id = ? ORDER BY checkin_date DESC LIMIT 1
            """, (user_id,))
            if checkin_result:
                checkin_days = checkin_result.get('streak_days', 0)
        except:
            pass
        
        # 会员等级处理
        level = membership.get('level') if membership else None
        if level is not None:
            if hasattr(level, 'value'):
                level_value = level.value
            else:
                level_value = level
        else:
            level_value = 0
        
        level_names = {0: 'free', 1: 'premium', 2: 'vip'}
        member_level = level_names.get(level_value, 'free')
        
        # 格式化配额使用（按插件分组）
        quota_dict = {}
        for q in quota_usage:
            plugin = q.get('plugin_name', 'unknown')
            action = q.get('action_type', '')
            if plugin not in quota_dict:
                quota_dict[plugin] = {}
            quota_dict[plugin][action] = {
                'used': q.get('used', 0),
                'limit': q.get('limit', 0),
                'remaining': q.get('remaining', 0)
            }
        
        return {
            'user_id': user_id,
            'member_level': member_level,
            'membership': membership or {},
            'points': points_balance,
            'quota_usage': quota_dict,
            'checkin_days': checkin_days
        }
    
    async def _get_quota_usage(self, user_id: str) -> list:
        """获取配额使用情况"""
        from datetime import date
        
        # 获取会员等级
        member_level = self.quota_validator._get_member_level(user_id)
        
        # 获取今日配额使用
        today = date.today()
        
        # 查询配额规则和使用情况
        rules = self.db.execute("""
            SELECT DISTINCT action_type, plugin_name, daily_limit
            FROM quota_rules
            WHERE member_level = ? AND is_active = 1
            ORDER BY plugin_name, action_type
        """, (member_level.value,))
        
        quota_data = []
        for rule in rules:
            action_type = rule['action_type']
            plugin_name = rule['plugin_name']
            daily_limit = rule['daily_limit']
            
            # 获取今日使用量
            used = self.quota_validator._get_today_usage(user_id, action_type, today)
            
            # 获取配额加成
            boost = self.quota_validator._get_active_boosts(user_id, action_type, today)
            
            total_limit = daily_limit + boost if daily_limit != -1 else -1
            remaining = total_limit - used if total_limit != -1 else -1
            
            quota_data.append({
                'action_type': action_type,
                'plugin_name': plugin_name,
                'used': used,
                'limit': total_limit,
                'remaining': remaining
            })
        
        return quota_data
    
    async def _get_admin_stats(self) -> dict:
        """获取管理员统计数据"""
        from datetime import date, timedelta
        
        today = date.today()
        today_str = today.strftime('%Y-%m-%d')
        yesterday_str = (today - timedelta(days=1)).strftime('%Y-%m-%d')
        week_ago_str = (today - timedelta(days=7)).strftime('%Y-%m-%d')
        
        # 总用户数
        total_users = self.db.execute_one("SELECT COUNT(*) as count FROM users")
        
        # 今日新增用户
        new_users_today = self.db.execute_one("""
            SELECT COUNT(*) as count FROM users 
            WHERE created_at LIKE ?
        """, (today_str + '%',))
        
        # 今日活跃用户数
        active_users = self.db.execute_one("""
            SELECT COUNT(DISTINCT user_id) as count
            FROM quota_usage
            WHERE usage_date = ?
        """, (today_str,))
        
        # 今日请求数
        today_requests = self.db.execute_one("""
            SELECT COALESCE(SUM(count), 0) as count
            FROM quota_usage
            WHERE usage_date = ?
        """, (today_str,))
        
        # 昨日请求数
        yesterday_requests = self.db.execute_one("""
            SELECT COALESCE(SUM(count), 0) as count
            FROM quota_usage
            WHERE usage_date = ?
        """, (yesterday_str,))
        
        # 7天总请求数
        week_requests = self.db.execute_one("""
            SELECT COALESCE(SUM(count), 0) as count
            FROM quota_usage
            WHERE usage_date >= ?
        """, (week_ago_str,))
        
        # 会员数量
        member_count = self.db.execute_one("""
            SELECT COUNT(*) as count
            FROM memberships
            WHERE level > 0 AND expire_date >= date('now')
        """)
        
        # 今日热门功能 TOP 10
        top_actions_today = self.db.execute("""
            SELECT action_type, SUM(count) as total
            FROM quota_usage
            WHERE usage_date = ?
            GROUP BY action_type
            ORDER BY total DESC
            LIMIT 10
        """, (today_str,))
        
        # 今日签到人数（签到表在单独的数据库中）
        checkin_today = None
        try:
            import sqlite3
            config = self.context.get_config()
            data_path = config.get("data_path", "data")
            checkin_db_path = os.path.join(data_path, "plugin_data", "checkin", "checkin.db")
            if os.path.exists(checkin_db_path):
                conn = sqlite3.connect(checkin_db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) as count FROM checkin_records
                    WHERE checkin_date = ?
                """, (today_str,))
                checkin_today = cursor.fetchone()
                conn.close()
        except Exception:
            checkin_today = None
        
        # 积分流通（今日发放/消耗）
        try:
            points_issued = self.db.execute_one("""
                SELECT COALESCE(SUM(amount), 0) as total
                FROM points_transactions
                WHERE created_at LIKE ? AND amount > 0
            """, (today_str + '%',))
            
            points_spent = self.db.execute_one("""
                SELECT COALESCE(ABS(SUM(amount)), 0) as total
                FROM points_transactions
                WHERE created_at LIKE ? AND amount < 0
            """, (today_str + '%',))
        except Exception:
            points_issued = None
            points_spent = None
        
        return {
            'total_users': total_users['count'] if total_users else 0,
            'new_users_today': new_users_today['count'] if new_users_today else 0,
            'active_users': active_users['count'] if active_users else 0,
            'today_requests': today_requests['count'] if today_requests else 0,
            'yesterday_requests': yesterday_requests['count'] if yesterday_requests else 0,
            'week_requests': week_requests['count'] if week_requests else 0,
            'member_count': member_count['count'] if member_count else 0,
            'top_actions_today': [dict(a) for a in top_actions_today] if top_actions_today else [],
            'checkin_today': checkin_today['count'] if checkin_today else 0,
            'points_issued': points_issued['total'] if points_issued else 0,
            'points_spent': points_spent['total'] if points_spent else 0,
        }
    
    # ==================== 管理员输入处理 ====================
    
    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def handle_admin_input(self, event: AstrMessageEvent):
        """处理管理员输入模式的消息"""
        if event.get_result():
            return
        
        user_id = get_unified_user_id(event)
        if not self._is_admin(user_id, event):
            return
        
        mode = self._get_admin_input_mode(user_id)
        if not mode:
            return
        
        message_text = (event.message_str or "").strip()
        if not message_text:
            return
        
        # 取消操作
        if message_text.lower() in ['取消', 'cancel', '0']:
            self._clear_admin_input_mode(user_id)
            yield event.plain_result("❌ 已取消操作")
            event.stop_event()
            return
        
        capabilities = get_platform_capabilities(event, "QuotaAdmin")
        builder = QuotaAdminResponseBuilder(capabilities)
        
        try:
            if mode == "blacklist_add":
                # 添加黑名单: 用户ID 原因
                parts = message_text.split(maxsplit=1)
                target_user = parts[0]
                reason = parts[1] if len(parts) > 1 else "管理员封禁"
                
                success = await self.session_handler.add_to_blacklist(target_user, reason, user_id)
                if success:
                    msg = f"✅ 已将用户 {target_user} 加入黑名单\n原因: {reason}"
                else:
                    msg = "❌ 添加黑名单失败"
                
                self._clear_admin_input_mode(user_id)
                blacklist = await self.session_handler.get_blacklist()
                message, keyboard = builder.build_blacklist_menu(blacklist)
                yield event.plain_result(msg)
                event.stop_event()
            
            elif mode == "points_add_single":
                # 单用户充值: 用户ID 积分数量
                parts = message_text.split()
                if len(parts) < 2:
                    yield event.plain_result("❌ 格式错误，请输入: 用户ID 积分数量")
                    event.stop_event()
                    return
                
                target_user = parts[0]
                try:
                    amount = int(parts[1])
                except ValueError:
                    yield event.plain_result("❌ 积分数量必须是数字")
                    event.stop_event()
                    return
                
                success = await self.session_handler.add_points_single(target_user, amount, user_id)
                if success:
                    msg = f"✅ 已给用户 {target_user} 充值 {amount} 积分"
                else:
                    msg = "❌ 充值失败"
                
                self._clear_admin_input_mode(user_id)
                yield event.plain_result(msg)
                event.stop_event()
            
            elif mode == "points_add_batch":
                # 批量充值: 积分数量
                try:
                    amount = int(message_text)
                except ValueError:
                    yield event.plain_result("❌ 积分数量必须是数字")
                    event.stop_event()
                    return
                
                count = await self.session_handler.add_points_batch(amount, user_id)
                if count > 0:
                    msg = f"✅ 已给 {count} 个用户各充值 {amount} 积分"
                else:
                    msg = "❌ 批量充值失败或没有用户"
                
                self._clear_admin_input_mode(user_id)
                yield event.plain_result(msg)
                event.stop_event()
            
            elif mode == "points_deduct":
                # 扣除积分: 用户ID 积分数量
                parts = message_text.split()
                if len(parts) < 2:
                    yield event.plain_result("❌ 格式错误，请输入: 用户ID 积分数量")
                    event.stop_event()
                    return
                
                target_user = parts[0]
                try:
                    amount = int(parts[1])
                except ValueError:
                    yield event.plain_result("❌ 积分数量必须是数字")
                    event.stop_event()
                    return
                
                success = await self.session_handler.deduct_points(target_user, amount, user_id)
                if success:
                    msg = f"✅ 已扣除用户 {target_user} 的 {amount} 积分"
                else:
                    msg = "❌ 扣除失败，用户可能不存在"
                
                self._clear_admin_input_mode(user_id)
                yield event.plain_result(msg)
                event.stop_event()
            
            elif mode == "announce_new":
                # 发送公告
                content = message_text
                ann_id = await self.session_handler.create_announcement(content, user_id)
                
                if ann_id:
                    # 获取所有用户（这里只是记录公告，实际推送需要额外实现）
                    msg = f"✅ 公告已创建 (ID: {ann_id})\n\n内容: {content[:100]}..."
                    msg += "\n\n💡 公告已保存，用户下次使用时可查看"
                else:
                    msg = "❌ 创建公告失败"
                
                self._clear_admin_input_mode(user_id)
                yield event.plain_result(msg)
                event.stop_event()
            
            elif mode == "ad_add":
                # 添加广告
                from common.ad_manager import get_ad_manager
                ad_manager = get_ad_manager(self.db)
                
                content = message_text.strip()
                if len(content) < 3:
                    yield event.plain_result("❌ 广告内容太短，请至少输入3个字符")
                    event.stop_event()
                    return
                
                ad_id = ad_manager.add_ad(content=content, weight=1, is_enabled=True)
                if ad_id:
                    self._clear_admin_input_mode(user_id)
                    # 返回广告列表
                    ads = ad_manager.get_all_ads()
                    stats = ad_manager.get_stats()
                    message, keyboard = builder.build_ad_manage_menu(ads, stats)
                    yield event.plain_result(f"✅ 广告已添加 (ID: {ad_id})")
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        pass  # 跳过，不需要多次yield
                else:
                    yield event.plain_result("❌ 添加广告失败")
                event.stop_event()
            
            elif mode == "ad_edit":
                # 编辑广告
                from common.ad_manager import get_ad_manager
                ad_manager = get_ad_manager(self.db)
                
                mode_data = self._get_admin_input_data(user_id)
                ad_id = mode_data.get('ad_id', 0) if mode_data else 0
                
                content = message_text.strip()
                if len(content) < 3:
                    yield event.plain_result("❌ 广告内容太短，请至少输入3个字符")
                    event.stop_event()
                    return
                
                success = ad_manager.update_ad(ad_id, content=content)
                self._clear_admin_input_mode(user_id)
                
                if success:
                    ad = ad_manager.get_ad(ad_id)
                    message, keyboard = builder.build_ad_detail(ad)
                    yield event.plain_result(f"✅ 广告 #{ad_id} 已更新")
                    async for result in MessageEditor.edit_or_send(event, message, keyboard):
                        pass
                else:
                    yield event.plain_result("❌ 更新广告失败")
                event.stop_event()
        
        except Exception as e:
            logger.error(f"[QuotaAdmin] 处理管理员输入失败: {e}", exc_info=True)
            self._clear_admin_input_mode(user_id)
            yield event.plain_result("❌ 操作失败，请稍后重试")
            event.stop_event()
    
    # ==================== 反馈会话处理 ====================
    
    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def handle_feedback_session(self, event: AstrMessageEvent):
        """处理反馈会话消息"""
        if event.get_result():
            return
        
        message_str = event.message_str or ""
        if message_str.startswith("/") or message_str.startswith("callback "):
            return
        
        session_id = event.get_session_id()
        session = self.session_manager.get_session(session_id, renew=True)
        
        if not session:
            return
        
        session_type = session.get('type', '')
        
        # 处理用户反馈输入
        if session_type == "feedback":
            user_id = get_unified_user_id(event)
            feedback_type = session.get('data', {}).get('feedback_type', 'suggestion')
            
            # 取消操作
            if message_str.lower() in ['取消', 'cancel', '0']:
                self.session_manager.end_session(session_id)
                yield event.plain_result("❌ 已取消反馈")
                event.stop_event()
                return
            
            # 提交反馈
            content = message_str.strip()
            if len(content) < 5:
                yield event.plain_result("❌ 反馈内容太短，请至少输入5个字符")
                event.stop_event()
                return
            
            feedback_id = self.feedback_manager.submit_feedback(
                user_id=user_id,
                content=content,
                feedback_type=feedback_type
            )
            
            if feedback_id:
                # 结束会话
                self.session_manager.end_session(session_id)
                
                # 通知管理员
                await self._notify_admins_new_feedback(event, feedback_id, user_id, feedback_type, content)
                
                # 显示成功页面 - 编辑之前的输入提示消息
                capabilities = get_platform_capabilities(event, "QuotaAdmin")
                builder = QuotaAdminResponseBuilder(capabilities)
                message, keyboard = builder.build_feedback_success(feedback_id, feedback_type)
                
                input_message_id = session.get('data', {}).get('input_message_id')
                if input_message_id:
                    try:
                        platform_name = event.get_platform_name()
                        if platform_name == "telegram":
                            # 编辑之前的消息为成功页面
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
                            logger.debug(f"[QuotaAdmin] 已编辑反馈消息为成功页面: {input_message_id}")
                        else:
                            # 其他平台发送新消息
                            yield event.plain_result(message)
                    except Exception as e:
                        logger.warning(f"[QuotaAdmin] 编辑消息失败: {e}")
                        # 编辑失败则发送新消息
                        yield event.plain_result(message)
                else:
                    # 没有保存的消息ID，发送新消息
                    yield event.plain_result(message)
            else:
                # 提交失败也要结束会话
                self.session_manager.end_session(session_id)
                yield event.plain_result("❌ 提交反馈失败，请稍后重试")
            
            event.stop_event()
        
        # 处理管理员回复反馈
        elif session_type == "admin_feedback_reply":
            user_id = get_unified_user_id(event)
            if not self._is_admin(user_id, event):
                return
            
            feedback_id = session.get('data', {}).get('feedback_id', 0)
            
            # 取消操作
            if message_str.lower() in ['取消', 'cancel', '0']:
                self.session_manager.end_session(session_id)
                yield event.plain_result("❌ 已取消回复")
                event.stop_event()
                return
            
            reply_content = message_str.strip()
            if len(reply_content) < 2:
                yield event.plain_result("❌ 回复内容太短")
                event.stop_event()
                return
            
            # 提交回复
            success = self.feedback_manager.reply_feedback(
                feedback_id=feedback_id,
                admin_id=user_id,
                reply=reply_content,
                status="resolved"
            )
            
            if success:
                # 结束会话
                self.session_manager.end_session(session_id)
                
                # 通知用户
                feedback = self.feedback_manager.get_feedback_by_id(feedback_id)
                if feedback:
                    await self._notify_feedback_user(event, feedback, "replied", reply_content)
                
                # 编辑之前的回复提示消息为反馈详情页面
                capabilities = get_platform_capabilities(event, "QuotaAdmin")
                builder = QuotaAdminResponseBuilder(capabilities)
                updated_feedback = self.feedback_manager.get_feedback_by_id(feedback_id)
                
                if updated_feedback:
                    message, keyboard = builder.build_feedback_detail(updated_feedback, True)
                    
                    reply_message_id = session.get('data', {}).get('reply_message_id')
                    if reply_message_id:
                        try:
                            platform_name = event.get_platform_name()
                            if platform_name == "telegram":
                                # 编辑之前的消息为反馈详情页面
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
                                    message_id=int(reply_message_id),
                                    text=message,
                                    reply_markup=tg_keyboard
                                )
                                logger.debug(f"[QuotaAdmin] 已编辑回复消息为反馈详情: {reply_message_id}")
                            else:
                                # 其他平台发送新消息
                                yield event.plain_result(message)
                        except Exception as e:
                            logger.warning(f"[QuotaAdmin] 编辑回复消息失败: {e}")
                            # 编辑失败则发送新消息
                            yield event.plain_result(f"✅ 已回复反馈 #{feedback_id}")
                    else:
                        # 没有保存的消息ID，发送新消息
                        yield event.plain_result(f"✅ 已回复反馈 #{feedback_id}")
                else:
                    yield event.plain_result(f"✅ 已回复反馈 #{feedback_id}")
            else:
                # 回复失败也要结束会话
                self.session_manager.end_session(session_id)
                yield event.plain_result("❌ 回复失败")
            
            event.stop_event()
    
    async def _notify_admins_new_feedback(self, event, feedback_id: int, user_id: str, feedback_type: str, content: str):
        """通知管理员有新反馈"""
        type_names = {
            'suggestion': '💡 建议',
            'bug': '🐛 Bug',
            'complaint': '😤 投诉',
            'praise': '👍 表扬'
        }
        type_name = type_names.get(feedback_type, '反馈')
        
        # 截断内容
        short_content = content[:100] + "..." if len(content) > 100 else content
        
        msg = f"📬 新反馈通知\n\n"
        msg += f"编号: #{feedback_id}\n"
        msg += f"类型: {type_name}\n"
        msg += f"用户: {user_id}\n"
        msg += f"内容: {short_content}\n"
        msg += f"\n使用 /管理 → 反馈管理 查看详情"
        
        # 记录日志
        logger.info(f"[QuotaAdmin] 新反馈通知: #{feedback_id} from {user_id}")
        
        # 向插件配置的管理员发送通知（如果启用了通知功能）
        if self.notification_enabled and self.admins and self.message_pusher:
            try:
                results = await self.message_pusher.broadcast_to_admins(
                    admin_list=self.admins,
                    message=msg,
                    context=self.context  # 传递插件 context 用于获取所有平台客户端
                )
                
                success_count = sum(1 for success in results.values() if success)
                logger.info(f"[QuotaAdmin] 管理员通知完成: {success_count}/{len(self.admins)} 成功")
                
            except Exception as e:
                logger.error(f"[QuotaAdmin] 通知管理员失败: {e}")
        else:
            logger.warning(f"[QuotaAdmin] 无管理员列表或消息推送器不可用")
    
    async def _notify_feedback_user(self, event, feedback: dict, action: str, reply: str = None):
        """通知用户反馈状态变更"""
        target_user_id = feedback.get('user_id', '')
        feedback_id = feedback.get('id', 0)
        
        status_msgs = {
            'resolved': '✅ 已解决',
            'rejected': '❌ 已拒绝',
            'replied': '💬 已回复'
        }
        status_msg = status_msgs.get(action, '已更新')
        
        msg = f"📬 反馈状态更新\n\n"
        msg += f"您的反馈 #{feedback_id} {status_msg}\n"
        
        if reply:
            msg += f"\n管理员回复:\n{reply}"
        
        msg += f"\n\n使用 /我 → 我的反馈 查看详情"
        
        # 记录日志
        logger.info(f"[QuotaAdmin] 反馈状态通知: #{feedback_id} -> {action} for {target_user_id}")
        
        # 向用户发送通知（如果启用了通知功能）
        if self.notification_enabled and target_user_id and self.message_pusher:
            try:
                success = await self.message_pusher.send_private_message(
                    user_id=target_user_id,
                    message=msg,
                    context=self.context  # 传递插件 context 用于获取所有平台客户端
                )
                
                if success:
                    logger.info(f"[QuotaAdmin] 用户通知发送成功: {target_user_id}")
                else:
                    logger.warning(f"[QuotaAdmin] 用户通知发送失败: {target_user_id}")
                    
            except Exception as e:
                logger.error(f"[QuotaAdmin] 通知用户失败: {e}")
        else:
            logger.warning(f"[QuotaAdmin] 无效的用户ID或消息推送器不可用: {target_user_id}")
    
    # ==================== 任务系统处理 ====================
    
    async def _handle_tasks_callback(self, event, user_id: str, sub_action: str, builder):
        """处理任务系统回调"""
        try:
            from common.task_manager import get_task_manager, TaskType
            
            task_manager = get_task_manager(self.db, self.points_manager)
            if not task_manager:
                yield event.plain_result("❌ 任务系统暂不可用")
                return
            
            # 任务类型映射
            type_map = {
                "daily": TaskType.DAILY,
                "weekly": TaskType.WEEKLY,
                "monthly": TaskType.MONTHLY,
                "onetime": TaskType.ONETIME,
                "": TaskType.DAILY  # 默认每日
            }
            
            if sub_action == "claim":
                # 一键领取
                count, total_points = task_manager.claim_all_rewards(user_id)
                if count > 0:
                    yield event.plain_result(f"🎉 领取成功！获得 {total_points} 积分（{count}个任务）")
                else:
                    yield event.plain_result("📭 暂无可领取的奖励")
                return
            
            # 获取任务类型
            task_type = type_map.get(sub_action, TaskType.DAILY)
            task_type_str = sub_action if sub_action in type_map else "daily"
            
            # 获取任务列表
            tasks = task_manager.get_user_tasks(user_id, task_type)
            
            # 计算可领取
            claimable_count = sum(1 for _, p in tasks if p.is_claimable)
            claimable_points = sum(t.reward_points for t, p in tasks if p.is_claimable)
            
            message, keyboard = builder.build_tasks_page(
                tasks=tasks,
                task_type=task_type_str,
                claimable_count=claimable_count,
                claimable_points=claimable_points
            )
            
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
                
        except Exception as e:
            logger.error(f"[QuotaAdmin] 任务回调处理失败: {e}")
            yield event.plain_result("❌ 任务系统暂不可用")
    
    # ==================== 邀请系统处理 ====================
    
    async def _handle_invite_callback(self, event, user_id: str, sub_action: str, builder):
        """处理邀请系统回调"""
        try:
            from common.invite_manager import get_invite_manager
            
            invite_manager = get_invite_manager(self.db, self.points_manager)
            if not invite_manager:
                yield event.plain_result("❌ 邀请系统暂不可用")
                return
            
            if sub_action == "rank":
                # 邀请排行榜
                leaderboard = invite_manager.get_leaderboard(limit=10)
                
                # 计算我的排名
                my_rank = 0
                for i, entry in enumerate(leaderboard, 1):
                    if entry.get('user_id') == user_id:
                        my_rank = i
                        break
                
                message, keyboard = builder.build_invite_rank_page(leaderboard, my_rank)
                async for result in MessageEditor.edit_or_send(event, message, keyboard):
                    yield result
                return
            
            # 默认显示邀请页面
            platform = event.get_platform_name()
            bot_username = None
            
            # 获取 Telegram bot username
            if platform == "telegram":
                try:
                    bot_info = await event.client.get_me()
                    bot_username = bot_info.username
                except Exception:
                    pass
            
            # 获取邀请信息
            invite_code, invite_link = invite_manager.get_invite_info(user_id, platform, bot_username)
            stats = invite_manager.get_invite_stats(user_id)
            invitees = invite_manager.get_invitees(user_id, limit=5)
            inviter = invite_manager.get_inviter(user_id)
            
            message, keyboard = builder.build_invite_page(
                invite_code=invite_code,
                invite_link=invite_link,
                stats=stats,
                invitees=invitees,
                inviter=inviter
            )
            
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
                
        except Exception as e:
            logger.error(f"[QuotaAdmin] 邀请回调处理失败: {e}")
            yield event.plain_result("❌ 邀请系统暂不可用")
    
    # ==================== 绑定邀请命令 ====================
    
    @filter.command("绑定邀请", "bind_invite")
    async def bind_invite_cmd(self, event: AstrMessageEvent, invite_code: str = ""):
        """绑定邀请码"""
        if not invite_code:
            yield event.plain_result("❌ 请提供邀请码\n\n用法: /绑定邀请 <邀请码>")
            return
        
        user_id = get_unified_user_id(event)
        
        try:
            from common.invite_manager import get_invite_manager
            from common.task_tracker import get_task_tracker, TaskTrigger
            
            invite_manager = get_invite_manager(self.db, self.points_manager)
            if not invite_manager:
                yield event.plain_result("❌ 邀请系统暂不可用")
                return
            
            success, msg = invite_manager.process_invite(user_id, invite_code)
            
            if success:
                # 追踪任务进度
                try:
                    tracker = get_task_tracker()
                    tracker.track(user_id, TaskTrigger.BIND_INVITE)
                except Exception:
                    pass
            
            yield event.plain_result(f"{'🎉' if success else '❌'} {msg}")
            
        except Exception as e:
            logger.error(f"[QuotaAdmin] 绑定邀请失败: {e}")
            yield event.plain_result("❌ 绑定失败，请稍后重试")
