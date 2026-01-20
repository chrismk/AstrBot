"""
通用配额系统管理插件
提供配额查询、记录查询、管理员管理等功能
"""
from typing import Any
import os
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# 导入通用配额系统
import sys
plugin_root = Path(__file__).parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

try:
    from common.database_manager import DatabaseManager
    from common.quota_validator import QuotaValidator
    from common.membership_manager import MembershipManager
    from common.points_manager import PointsManager
    from common.rate_limiter import get_rate_limiter
    from common.quota_reservation import QuotaReservation
    from common.quota_analytics import QuotaAnalytics
    QUOTA_SYSTEM_AVAILABLE = True
except ImportError as e:
    QUOTA_SYSTEM_AVAILABLE = False
    logger.error(f"[QuotaAdmin] 通用配额系统不可用: {e}")

# 导入处理器
from .handlers.user_commands import UserCommandHandler
from .handlers.admin_commands import AdminCommandHandler
from .handlers.session_handlers import SessionHandler


@register("quota_admin", "AstrBot Team", "通用配额系统管理插件", "1.0.0")
class QuotaAdminPlugin(Star):
    """通用配额系统管理插件"""
    
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context, config)
        self.context = context
        self.config = config or {}
        
        # 管理员列表（从配置文件读取）
        self.admins = self.config.get("admins", [])
        
        # 初始化通用配额系统
        self.db = None
        self.quota_validator = None
        self.membership_manager = None
        self.points_manager = None
        self.rate_limiter = None
        self.quota_reservation = None
        self.quota_analytics = None
        self.system_available = QUOTA_SYSTEM_AVAILABLE
        
        if self.system_available:
            try:
                # 获取数据路径
                data_path = self.context.get_config().get("data_path", "data")
                quota_db_path = os.path.join(data_path, "quota_system.db")
                
                # 初始化管理器
                self.db = DatabaseManager(quota_db_path)
                self.quota_validator = QuotaValidator(self.db)
                self.membership_manager = MembershipManager(self.db)
                self.points_manager = PointsManager(self.db)
                
                # 初始化新模块
                self.rate_limiter = get_rate_limiter()
                self.quota_reservation = QuotaReservation(self.db, self.quota_validator)
                self.quota_analytics = QuotaAnalytics(self.db)
                
                logger.info("[QuotaAdmin] 通用配额系统初始化完成（包含新优化模块）")
            except Exception as e:
                logger.error(f"[QuotaAdmin] 通用配额系统初始化失败: {e}")
                self.system_available = False
        
        # 初始化处理器
        if self.system_available:
            self.user_handler = UserCommandHandler(
                self.quota_validator,
                self.membership_manager,
                self.points_manager,
                self.quota_analytics
            )
            self.admin_handler = AdminCommandHandler(
                self.quota_validator,
                self.membership_manager,
                self.points_manager,
                self.quota_analytics,
                self.rate_limiter,
                self.admins
            )
            self.session_handler = SessionHandler(
                self.quota_validator,
                self.membership_manager,
                self.points_manager,
                self.quota_analytics,
                self.admins
            )
        else:
            logger.warning("[QuotaAdmin] 配额系统不可用，插件功能受限")
    
    def _check_system_available(self, event: AstrMessageEvent):
        """检查系统是否可用"""
        if not self.system_available:
            return False, "❌ 配额系统未初始化，请联系管理员"
        return True, None
    
    def _is_admin(self, user_id: str) -> bool:
        """检查用户是否为管理员"""
        return user_id in self.admins
    
    # ==================== 用户命令 ====================
    
    @filter.command("我")
    async def my_info_cmd(self, event: AstrMessageEvent):
        """我的信息（多轮对话）"""
        available, msg = self._check_system_available(event)
        if not available:
            yield event.plain_result(msg)
            return
        
        user_id = event.get_sender_id()
        session_id = event.get_session_id()
        
        # 启动"我的信息"会话
        result = await self.session_handler.start_my_info_session(user_id, session_id)
        yield event.plain_result(result)
    
    @filter.command("兑换")
    async def redeem_cmd(self, event: AstrMessageEvent):
        """兑换配额包（多轮对话）"""
        available, msg = self._check_system_available(event)
        if not available:
            yield event.plain_result(msg)
            return
        
        user_id = event.get_sender_id()
        session_id = event.get_session_id()
        
        # 启动兑换会话
        result = await self.session_handler.start_redeem_session(user_id, session_id)
        yield event.plain_result(result)
    
    # ==================== 管理员命令 ====================
    
    @filter.command("管理")
    async def admin_cmd(self, event: AstrMessageEvent):
        """管理员管理面板（多轮对话）"""
        available, msg = self._check_system_available(event)
        if not available:
            yield event.plain_result(msg)
            return
        
        user_id = event.get_sender_id()
        if not self._is_admin(user_id):
            yield event.plain_result("❌ 权限不足，仅管理员可用")
            return
        
        session_id = event.get_session_id()
        
        # 启动管理会话
        result = await self.session_handler.start_admin_session(user_id, session_id)
        yield event.plain_result(result)
    
    @filter.command("统计")
    async def stats_cmd(self, event: AstrMessageEvent):
        """查看配额统计（管理员）"""
        available, msg = self._check_system_available(event)
        if not available:
            yield event.plain_result(msg)
            return
        
        user_id = event.get_sender_id()
        if not self._is_admin(user_id):
            yield event.plain_result("❌ 权限不足，仅管理员可用")
            return
        
        # 获取统计数据
        stats = await self.quota_analytics.get_usage_stats(days=7)
        
        result = "📊 配额使用统计（最近7天）\n\n"
        
        # 热门操作 TOP 5
        if stats.get('top_actions'):
            result += "🔥 热门操作 TOP 5：\n"
            for i, action in enumerate(stats['top_actions'][:5], 1):
                result += f"{i}. {action['action_type']}: {action['total_count']}次\n"
            result += "\n"
        
        # 会员等级统计
        if stats.get('member_stats'):
            result += "👥 会员等级统计：\n"
            level_names = {0: "免费", 1: "高级", 2: "VIP"}
            for member in stats['member_stats']:
                level_name = level_names.get(member['level'], "未知")
                result += f"{level_name}: {member['active_users']}人, {member['total_usage']}次\n"
            result += "\n"
        
        result += "💡 输入 /管理 查看更多统计信息"
        
        yield event.plain_result(result)
    
    @filter.command("限流")
    async def rate_limit_cmd(self, event: AstrMessageEvent):
        """查看速率限制状态（管理员）"""
        available, msg = self._check_system_available(event)
        if not available:
            yield event.plain_result(msg)
            return
        
        user_id = event.get_sender_id()
        if not self._is_admin(user_id):
            yield event.plain_result("❌ 权限不足，仅管理员可用")
            return
        
        # 获取限流统计
        stats = self.rate_limiter.get_stats()
        
        result = "⚡ 速率限制状态\n\n"
        result += f"👥 当前活跃用户: {stats['total_users']}人\n"
        result += f"📊 总请求数: {stats['total_requests']}次\n"
        result += f"📊 平均请求/用户: {stats['avg_requests_per_user']:.2f}次\n\n"
        result += "💡 限流配置：\n"
        result += "- 默认: 10次/分钟\n"
        result += "- 音乐下载: 5次/分钟\n"
        result += "- 云盘下载: 3次/分钟\n"
        result += "- 搜索: 20次/分钟\n\n"
        result += "🎯 会员倍率：\n"
        result += "- 免费: 1倍\n"
        result += "- 高级: 2倍\n"
        result += "- VIP: 5倍"
        
        yield event.plain_result(result)
    
    @filter.command("帮助")
    async def help_cmd(self, event: AstrMessageEvent):
        """显示帮助信息"""
        user_id = event.get_sender_id()
        is_admin = self._is_admin(user_id)
        
        help_text = "📚 配额系统帮助\n\n"
        help_text += "👤 用户命令：\n"
        help_text += "/我 - 查询我的信息（配额/积分/会员/记录）\n"
        help_text += "/兑换 - 兑换配额包\n"
        help_text += "/帮助 - 显示此帮助信息\n"
        
        if is_admin:
            help_text += "\n👑 管理员命令：\n"
            help_text += "/管理 - 管理面板（配额/积分/会员）\n"
            help_text += "/统计 - 查看配额使用统计\n"
            help_text += "/限流 - 查看速率限制状态\n"
        
        help_text += "\n💡 提示：\n"
        help_text += "- 所有功能都使用多轮对话，按提示操作即可\n"
        help_text += "- 积分可用于抵扣配额或兑换配额包\n"
        help_text += "- 会员享有更高的配额限制和限流倍率\n"
        help_text += "- 配额每日0点重置\n"
        help_text += "- 请求过于频繁会被限流，请合理使用\n"
        help_text += "- 回复 0 或 取消 可随时退出对话"
        
        yield event.plain_result(help_text)
    
    # ==================== 会话处理 ====================
    
    @filter.command_group("quota_session")
    async def handle_session_message(self, event: AstrMessageEvent):
        """处理会话中的消息"""
        available, msg = self._check_system_available(event)
        if not available:
            yield event.plain_result(msg)
            return
        
        user_id = event.get_sender_id()
        session_id = event.get_session_id()
        message = event.message_str or ""
        
        # 处理会话消息
        result = await self.session_handler.handle_session_message(
            user_id, session_id, message
        )
        
        if result:
            yield event.plain_result(result)
