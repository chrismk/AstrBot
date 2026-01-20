"""
会话处理器 - 标准化版本
使用通用 SessionManager 管理会话
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from astrbot.api import logger

from common import SessionManager
from .response_builder import QuotaAdminResponseBuilder


class SessionHandler:
    """会话处理器 - 标准化版本"""
    
    def __init__(
        self, 
        quota_validator, 
        membership_manager, 
        points_manager, 
        quota_analytics,
        session_manager: SessionManager,
        admins: List[str],
        context = None  # 新增 context 参数
    ):
        self.quota_validator = quota_validator
        self.membership_manager = membership_manager
        self.points_manager = points_manager
        self.quota_analytics = quota_analytics
        self.session_manager = session_manager
        self.admins = admins
        self.context = context
        
        # 注册会话处理器
        self.session_manager.register_handler('my_info', self._handle_my_info)
        self.session_manager.register_handler('admin', self._handle_admin)
        
        logger.info("[QuotaAdmin] SessionHandler 初始化完成（标准化版本）")
    
    def _is_admin(self, user_id: str) -> bool:
        """检查是否为管理员"""
        # 1. 检查插件配置
        if user_id in self.admins:
            return True
            
        # 2. 检查全局配置
        if self.context:
            global_admins = self.context.get_config().get("admins_id", [])
            if user_id in global_admins:
                return True
                
        return False
    
    async def handle_session_message(
        self, 
        session_id: str, 
        message: str, 
        session: Dict[str, Any],
        **context
    ) -> Optional[Tuple[str, Any]]:
        """
        处理会话消息（统一入口）
        
        Args:
            session_id: 会话ID
            message: 用户消息
            session: 会话数据
            
        Returns:
            (消息文本, 键盘对象) 或 None
        """
        session_type = session.get('type')
        user_id = session.get('user_id')
        
        logger.debug(f"[QuotaAdmin] 处理会话消息: type={session_type}, user={user_id}, msg={message}")
        
        # 检查退出命令
        if message in ["0", "取消", "退出", "exit", "quit"]:
            return "👋 已退出", None
        
        # 根据会话类型调用对应的处理器
        if session_type == "my_info":
            return await self._handle_my_info(session_id, message, session, **context)
        elif session_type == "admin":
            return await self._handle_admin(session_id, message, session, **context)
        
        logger.warning(f"[QuotaAdmin] 未找到会话处理器: {session_type}")
        return "❌ 会话类型错误", None
    
    async def _handle_my_info(
        self, 
        session_id: str, 
        message: str, 
        session: Dict[str, Any],
        **context
    ) -> Optional[Tuple[str, Any]]:
        """
        处理"我的信息"会话
        
        Args:
            session_id: 会话ID
            message: 用户消息
            session: 会话数据
            
        Returns:
            (消息文本, 键盘对象) 或 None
        """
        user_id = session.get('user_id')
        step = session.get('step', 0)
        capabilities = session.get('capabilities', {})
        
        # 创建响应构建器
        builder = QuotaAdminResponseBuilder(capabilities)
        
        # 主菜单（step=0）
        if step == 0:
            if message == "1":
                # 签到
                try:
                    from astrbot_plugin_checkin.checkin_manager import CheckinManager
                    checkin_manager = CheckinManager()
                    result = await checkin_manager.checkin(user_id)
                    self.session_manager.update_session(session_id, step=1, data={'action': 'checkin'})
                    return result, None
                except Exception as e:
                    return f"❌ 签到功能暂不可用: {e}", None
            
            elif message == "2":
                # 兑换配额包
                packages = self.points_manager.get_boost_packages()
                balance = await self.points_manager.get_balance(user_id)
                self.session_manager.update_session(
                    session_id, 
                    step=2, 
                    data={'action': 'redeem', 'packages': list(packages.keys())}
                )
                return builder.build_redeem_menu(packages, balance, step=2)
            
            elif message == "3":
                # 公告
                # TODO: 实现公告功能
                self.session_manager.update_session(session_id, step=1, data={'action': 'announcements'})
                return "📢 公告功能开发中...", None
            
            elif message == "4":
                # 查看配额详情
                quota_data = await self._get_quota_usage(user_id)
                self.session_manager.update_session(session_id, step=1, data={'action': 'quota'})
                return builder.build_quota_usage_response(quota_data, step=1)
            
            elif message == "5":
                # 查看积分流水
                transactions = await self.points_manager.get_transactions(user_id, limit=10)
                transactions_data = [dict(t) for t in transactions]
                self.session_manager.update_session(session_id, step=1, data={'action': 'transactions'})
                return builder.build_points_transactions_response(transactions_data, step=1)
            
            elif message == "6":
                # 查看配额加成
                boosts = await self.points_manager.get_active_boosts(user_id)
                self.session_manager.update_session(session_id, step=1, data={'action': 'boosts'})
                return builder.build_quota_boosts_response(boosts, step=1)
            
            elif message == "7":
                # 反馈
                self.session_manager.update_session(session_id, step=3, data={'action': 'feedback'})
                return "📬 请输入您的反馈内容：", None
            
            else:
                return "❌ 无效的选项，请输入 1-7 或 0 退出", None
        
        # 子菜单（step=1）
        elif step == 1:
            if message == "1":
                # 返回主菜单
                user_info = await self._get_user_info(user_id)
                self.session_manager.update_session(session_id, step=0, data={})
                return builder.build_my_info_menu(user_info, step=0)
            else:
                return "❌ 无效的选项，请输入 1 返回或 0 退出", None
        
        # 兑换菜单（step=2）
        elif step == 2:
            action = session.get('data', {}).get('action')
            
            if action == 'redeem':
                packages_list = session.get('data', {}).get('packages', [])
                
                if message == "1":
                    # 返回主菜单
                    user_info = await self._get_user_info(user_id)
                    self.session_manager.update_session(session_id, step=0, data={})
                    return builder.build_my_info_menu(user_info, step=0)
                
                # 验证输入
                try:
                    choice = int(message)
                    if 1 <= choice <= len(packages_list):
                        package_id = packages_list[choice - 1]
                        
                        # 执行兑换
                        success, result_msg = await self.points_manager.exchange_boost_package(
                            user_id, package_id
                        )
                        
                        if success:
                            # 兑换成功，返回主菜单
                            result_msg += "\n\n回复 1 返回主菜单"
                            self.session_manager.update_session(session_id, step=1, data={})
                            return result_msg, None
                        else:
                            # 兑换失败，返回兑换菜单
                            result_msg += "\n\n回复 1 返回主菜单"
                            return result_msg, None
                    else:
                        return f"❌ 无效的选项，请输入 1-{len(packages_list)} 或 0 退出", None
                except ValueError:
                    return "❌ 请输入数字", None
            
            return "❌ 会话状态错误", None
        
        # 反馈输入（step=3）
        elif step == 3:
            action = session.get('data', {}).get('action')
            
            if action == 'feedback':
                # 处理反馈内容
                feedback_content = message.strip()
                
                if len(feedback_content) < 5:
                    return "❌ 反馈内容太短，请至少输入5个字符", None
                
                if len(feedback_content) > 1000:
                    return "❌ 反馈内容太长，请控制在1000字符以内", None
                
                try:
                    # 保存反馈
                    feedback_manager = context.get('feedback_manager')
                    if feedback_manager:
                        feedback_id = feedback_manager.submit_feedback(
                            user_id=user_id,
                            feedback_type='suggestion',
                            content=feedback_content
                        )
                        
                        # 结束会话
                        self.session_manager.end_session(session_id)
                        
                        # 返回成功消息和反馈信息（用于通知管理员）
                        result_msg = f"✅ 反馈提交成功！\n反馈编号：#{feedback_id}\n\n感谢您的宝贵意见，我们会认真处理。"
                        # 返回第三个元素：反馈信息，用于通知管理员
                        return result_msg, None, {
                            'action': 'feedback_submitted',
                            'feedback_id': feedback_id,
                            'user_id': user_id,
                            'feedback_type': 'suggestion',
                            'content': feedback_content
                        }
                    else:
                        return "❌ 反馈系统暂不可用", None
                        
                except Exception as e:
                    return f"❌ 提交失败：{e}", None
            
            return "❌ 会话状态错误", None
        
        return "❌ 会话状态错误", None
    
    
    async def _handle_admin(
        self, 
        session_id: str, 
        message: str, 
        session: Dict[str, Any],
        **context
    ) -> Optional[Tuple[str, Any]]:
        """
        处理"管理员"会话
        
        Args:
            session_id: 会话ID
            message: 用户消息
            session: 会话数据
            
        Returns:
            (消息文本, 键盘对象) 或 None
        """
        user_id = session.get('user_id')
        step = session.get('step', 0)
        capabilities = session.get('capabilities', {})
        
        # 验证管理员权限
        if not self._is_admin(user_id):
            return "❌ 权限不足", None
        
        # 创建响应构建器
        builder = QuotaAdminResponseBuilder(capabilities)
        
        # 主菜单（step=0）
        if step == 0:
            if message == "1":
                # 用户管理
                result = "👤 用户管理\n\n"
                result += "请输入用户ID查询用户信息\n"
                result += "格式: platform:user_id\n"
                result += "示例: telegram:123456789\n\n"
                result += "回复 1 返回主菜单"
                self.session_manager.update_session(session_id, step=1, data={'action': 'user_mgmt'})
                return result, None
            
            elif message == "2":
                # 配额管理
                result = "📊 配额管理\n\n"
                result += "功能开发中...\n\n"
                result += "回复 1 返回主菜单"
                self.session_manager.update_session(session_id, step=1, data={'action': 'quota_mgmt'})
                return result, None
            
            elif message == "3":
                # 积分管理
                result = "💰 积分管理\n\n"
                result += "请输入充值信息\n"
                result += "格式: 用户ID 积分数 原因\n"
                result += "示例: telegram:123456789 100 活动奖励\n\n"
                result += "回复 1 返回主菜单"
                self.session_manager.update_session(session_id, step=1, data={'action': 'points_mgmt'})
                return result, None
            
            elif message == "4":
                # 公告管理
                result = "📢 公告管理\n\n"
                result += "功能开发中...\n\n"
                result += "回复 1 返回主菜单"
                self.session_manager.update_session(session_id, step=1, data={'action': 'announce_mgmt'})
                return result, None
            
            elif message == "5":
                # 数据统计
                stats = await self.quota_analytics.get_usage_stats(days=7)
                
                result = "📊 数据统计（最近7天）\n\n"
                
                # 热门操作
                if stats.get('top_actions'):
                    result += "🔥 热门操作 TOP 5：\n"
                    for i, action in enumerate(stats['top_actions'][:5], 1):
                        result += f"{i}. {action['action_type']}: {action['total_count']}次\n"
                    result += "\n"
                
                # 会员统计
                if stats.get('member_stats'):
                    result += "👥 会员等级统计：\n"
                    level_names = {0: "免费", 1: "高级", 2: "VIP"}
                    for member in stats['member_stats']:
                        level_name = level_names.get(member['level'], "未知")
                        result += f"{level_name}: {member['active_users']}人, {member['total_usage']}次\n"
                    result += "\n"
                
                result += "回复 1 返回主菜单"
                self.session_manager.update_session(session_id, step=1, data={'action': 'data_stats'})
                return result, None
            
            elif message == "6":
                # 反馈管理
                try:
                    feedback_manager = context.get('feedback_manager')
                    if feedback_manager:
                        feedback_data = feedback_manager.get_feedback_list(limit=10)
                        feedbacks = feedback_data.get('feedbacks', [])
                        pending_count = feedback_data.get('pending_count', 0)
                        
                        result = f"📬 反馈管理\n\n"
                        result += f"待处理: {pending_count}条\n\n"
                        
                        if feedbacks:
                            result += "最近10条反馈：\n"
                            for fb in feedbacks:
                                status_emoji = {"pending": "🟡", "processing": "🔵", "resolved": "🟢", "rejected": "🔴"}.get(fb.get('status', 'pending'), "🟡")
                                content_preview = fb.get('content', '')[:20]
                                if len(fb.get('content', '')) > 20:
                                    content_preview += "..."
                                
                                # 解析用户信息
                                user_id = fb.get('user_id', '')
                                username = fb.get('username', '')
                                
                                # 提取平台信息
                                if ':' in user_id:
                                    platform = user_id.split(':', 1)[0]
                                    platform_emoji = {
                                        'telegram': '📱TG',
                                        'lark': '🟦飞书',
                                        'qq': '🐧QQ',
                                        'wechat': '💬微信'
                                    }.get(platform, f'📋{platform}')
                                else:
                                    platform_emoji = '❓未知'
                                
                                # 显示用户名或用户ID的简短形式
                                if username:
                                    user_display = username[:8]
                                else:
                                    # 显示用户ID的后几位
                                    if ':' in user_id:
                                        raw_id = user_id.split(':', 1)[1]
                                        if len(raw_id) > 8:
                                            user_display = f"...{raw_id[-6:]}"
                                        else:
                                            user_display = raw_id
                                    else:
                                        user_display = user_id[:8] if user_id else "未知"
                                
                                result += f"{status_emoji} #{fb.get('id')} {platform_emoji} {user_display}\n"
                                result += f"    {content_preview}\n"
                        else:
                            result += "暂无反馈"
                        result += "\n回复 1 返回主菜单"
                        self.session_manager.update_session(session_id, step=1, data={'action': 'feedback_mgmt'})
                        return result, None
                    else:
                        return "❌ 反馈系统不可用", None
                except Exception as e:
                    return f"❌ 获取反馈失败: {e}", None
            
            elif message == "7":
                # 限流配置
                from common import get_rate_limiter
                rate_limiter = get_rate_limiter()
                stats = rate_limiter.get_stats()
                
                result = "⚡ 限流配置\n\n"
                result += f"👥 当前活跃用户: {stats['total_users']}人\n"
                result += f"📊 总请求数: {stats['total_requests']}次\n"
                result += f"📊 平均请求/用户: {stats['avg_requests_per_user']:.2f}次\n\n"
                result += "💡 限流配置（推广期）：\n"
                result += "- 所有操作: 60次/分钟\n\n"
                result += "🎯 会员倍率：\n"
                result += "- 免费: 1倍\n"
                result += "- 高级: 2倍\n"
                result += "- VIP: 5倍\n\n"
                result += "回复 1 返回主菜单"
                self.session_manager.update_session(session_id, step=1, data={'action': 'rate_config'})
                return result, None
            
            elif message == "8":
                # 系统状态
                result = "🖥️ 系统状态\n\n"
                result += "功能开发中...\n\n"
                result += "回复 1 返回主菜单"
                self.session_manager.update_session(session_id, step=1, data={'action': 'system_status'})
                return result, None
            
            else:
                return "❌ 无效的选项，请输入 1-8 或 0 退出", None
        
        # 子菜单（step=1）
        elif step == 1:
            action = session.get('data', {}).get('action')
            
            if message == "1":
                # 返回主菜单
                stats = await self._get_admin_stats()
                self.session_manager.update_session(session_id, step=0, data={})
                return builder.build_admin_menu(stats, step=0)
            
            # 处理具体操作
            if action == 'user_mgmt':
                # 查询用户信息
                target_user_id = message.strip()
                user_info = await self._get_user_info(target_user_id)
                
                result = f"👤 用户信息: {target_user_id}\n\n"
                
                # 会员信息
                membership = user_info.get('membership', {})
                if membership:
                    result += f"会员等级: {membership.get('level_name', '免费')}\n"
                    if membership.get('expire_date'):
                        result += f"到期时间: {membership['expire_date']}\n"
                
                # 积分信息
                points = user_info.get('points', {})
                if points:
                    result += f"\n积分余额: {points.get('balance', 0)}\n"
                    result += f"累计获得: {points.get('total_earned', 0)}\n"
                    result += f"累计消费: {points.get('total_spent', 0)}\n"
                
                result += "\n回复 1 返回主菜单"
                return result, None
            
            elif action == 'points_mgmt':
                # 充值积分
                try:
                    parts = message.split()
                    if len(parts) < 3:
                        return "❌ 格式错误，请按格式输入: 用户ID 积分数 原因", None
                    
                    target_user_id = parts[0]
                    points = int(parts[1])
                    reason = " ".join(parts[2:])
                    
                    # 执行充值
                    success, msg = await self.points_manager.recharge(
                        target_user_id,
                        points,
                        source="admin",
                        description=f"管理员充值: {reason}",
                        idempotency_key=f"admin_{user_id}_{target_user_id}_{datetime.now().timestamp()}"
                    )
                    
                    if success:
                        result = f"✅ {msg}\n用户: {target_user_id}\n原因: {reason}\n\n"
                        result += "回复 1 返回主菜单"
                        return result, None
                    else:
                        return f"❌ {msg}\n\n回复 1 返回主菜单", None
                        
                except (ValueError, IndexError) as e:
                    return f"❌ 格式错误: {e}\n请按格式输入: 用户ID 积分数 原因", None
            
            elif action == 'member_mgmt':
                # 升级会员
                try:
                    parts = message.split()
                    if len(parts) < 3:
                        return "❌ 格式错误，请按格式输入: 用户ID 等级 天数", None
                    
                    target_user_id = parts[0]
                    level = int(parts[1])
                    days = int(parts[2])
                    
                    if level not in [1, 2]:
                        return "❌ 等级必须是 1(高级) 或 2(VIP)", None
                    
                    # 执行升级
                    success, msg = await self.membership_manager.upgrade_membership(
                        target_user_id, level, days
                    )
                    
                    if success:
                        level_name = "高级" if level == 1 else "VIP"
                        result = f"✅ 升级成功\n用户: {target_user_id}\n等级: {level_name}\n天数: {days}\n\n"
                        result += "回复 1 返回主菜单"
                        return result, None
                    else:
                        return f"❌ {msg}\n\n回复 1 返回主菜单", None
                        
                except (ValueError, IndexError) as e:
                    return f"❌ 格式错误: {e}\n请按格式输入: 用户ID 等级 天数", None
            
            elif action == 'points_add':
                # 从用户详情页发起的积分充值（已有目标用户ID）
                try:
                    target_user_id = session.get('data', {}).get('target_user_id')
                    if not target_user_id:
                        return "❌ 目标用户丢失，请重新操作", None
                    
                    parts = message.split(maxsplit=1)
                    if len(parts) < 2:
                        return "❌ 格式错误，请输入: 积分数 原因", None
                    
                    points = int(parts[0])
                    reason = parts[1]
                    
                    # 执行充值
                    success, msg = await self.points_manager.recharge(
                        target_user_id,
                        points,
                        source="admin",
                        description=f"管理员充值: {reason}",
                        idempotency_key=f"admin_{user_id}_{target_user_id}_{datetime.now().timestamp()}"
                    )
                    
                    self.session_manager.end_session(session_id)
                    
                    if success:
                        return f"✅ {msg}\n用户: {target_user_id}\n原因: {reason}", None
                    else:
                        return f"❌ {msg}", None
                        
                except ValueError as e:
                    return f"❌ 积分数必须是数字", None
            
            elif action == 'member_up':
                # 从用户详情页发起的会员升级（已有目标用户ID）
                try:
                    target_user_id = session.get('data', {}).get('target_user_id')
                    if not target_user_id:
                        return "❌ 目标用户丢失，请重新操作", None
                    
                    parts = message.split()
                    if len(parts) < 2:
                        return "❌ 格式错误，请输入: 等级 天数", None
                    
                    level = int(parts[0])
                    days = int(parts[1])
                    
                    if level not in [1, 2]:
                        return "❌ 等级必须是 1(高级) 或 2(VIP)", None
                    
                    # 执行升级
                    success, msg = await self.membership_manager.upgrade_membership(
                        target_user_id, level, days
                    )
                    
                    self.session_manager.end_session(session_id)
                    
                    if success:
                        level_name = "高级" if level == 1 else "VIP"
                        return f"✅ 升级成功\n用户: {target_user_id}\n等级: {level_name}\n天数: {days}", None
                    else:
                        return f"❌ {msg}", None
                        
                except ValueError as e:
                    return f"❌ 格式错误，等级和天数必须是数字", None
            
            elif action == 'user_search':
                # 用户搜索
                keyword = message.strip()
                
                # 检查返回命令
                if keyword.lower() == 'b':
                    stats = await self._get_admin_stats()
                    self.session_manager.end_session(session_id)
                    return builder.build_admin_menu(stats, step=0)
                
                if not keyword:
                    return "❌ 请输入搜索关键词", None
                
                # 执行搜索
                users, total = await self.search_users(keyword)
                
                # 如果只找到一个用户，直接显示详情
                if total == 1 and users:
                    user_info = await self._get_user_detail(users[0]['user_id'])
                    self.session_manager.end_session(session_id)
                    return builder.build_user_detail(user_info)
                
                # 显示搜索结果（保持会话以便继续搜索）
                return builder.build_search_results(keyword, users, total)
            
            return "❌ 未知的操作", None
        
        return "❌ 会话状态错误", None
    
    # ==================== 辅助方法 ====================
    
    async def _get_user_info(self, user_id: str) -> dict:
        """获取用户信息"""
        # 获取会员信息
        membership = await self.membership_manager.get_membership_info(user_id)
        
        # 获取积分信息
        points = await self.points_manager.get_account_info(user_id)
        
        return {
            'membership': membership or {},
            'points': points or {}
        }
    
    async def _get_quota_usage(self, user_id: str) -> list:
        """获取配额使用情况"""
        from datetime import date
        
        # 获取会员等级
        member_level = self.quota_validator._get_member_level(user_id)
        
        # 获取今日配额使用
        today = date.today()
        
        # 查询配额规则和使用情况
        rules = self.quota_validator.db.execute("""
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
        from astrbot.api import logger
        
        today = date.today()
        today_str = today.strftime('%Y-%m-%d')
        yesterday_str = (today - timedelta(days=1)).strftime('%Y-%m-%d')
        week_ago_str = (today - timedelta(days=7)).strftime('%Y-%m-%d')
        db = self.quota_validator.db
        
        # 调试：打印数据库路径
        logger.info(f"[AdminStats] 数据库路径: {db.db_path}")
        
        # 总用户数
        total_users = db.execute_one("SELECT COUNT(*) as count FROM users")
        logger.info(f"[AdminStats] 总用户数查询结果: {total_users}, 类型: {type(total_users)}")
        
        # 今日新增用户（使用 LIKE 匹配日期前缀，兼容各种 datetime 格式）
        new_users_today = db.execute_one("""
            SELECT COUNT(*) as count FROM users 
            WHERE created_at LIKE ?
        """, (today_str + '%',))
        
        # 今日活跃用户数
        active_users = db.execute_one("""
            SELECT COUNT(DISTINCT user_id) as count
            FROM quota_usage
            WHERE usage_date = ?
        """, (today_str,))
        
        # 今日请求数
        today_requests = db.execute_one("""
            SELECT COALESCE(SUM(count), 0) as count
            FROM quota_usage
            WHERE usage_date = ?
        """, (today_str,))
        
        # 昨日请求数（用于对比）
        yesterday_requests = db.execute_one("""
            SELECT COALESCE(SUM(count), 0) as count
            FROM quota_usage
            WHERE usage_date = ?
        """, (yesterday_str,))
        
        # 7天总请求数
        week_requests = db.execute_one("""
            SELECT COALESCE(SUM(count), 0) as count
            FROM quota_usage
            WHERE usage_date >= ?
        """, (week_ago_str,))
        
        # 会员数量
        member_count = db.execute_one("""
            SELECT COUNT(*) as count
            FROM memberships
            WHERE level > 0 AND expire_date >= date('now')
        """)
        
        # 今日热门功能 TOP 3
        top_actions_today = db.execute("""
            SELECT action_type, SUM(count) as total
            FROM quota_usage
            WHERE usage_date = ?
            GROUP BY action_type
            ORDER BY total DESC
            LIMIT 3
        """, (today_str,))
        
        # 今日签到人数
        checkin_today = db.execute_one("""
            SELECT COUNT(*) as count FROM checkin_records
            WHERE checkin_date LIKE ?
        """, (today_str + '%',))
        
        # 积分流通（今日发放/消耗）
        points_issued = db.execute_one("""
            SELECT COALESCE(SUM(amount), 0) as total
            FROM points_transactions
            WHERE created_at LIKE ? AND amount > 0
        """, (today_str + '%',))
        
        points_spent = db.execute_one("""
            SELECT COALESCE(ABS(SUM(amount)), 0) as total
            FROM points_transactions
            WHERE created_at LIKE ? AND amount < 0
        """, (today_str + '%',))
        
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

    async def _get_user_list(self, platform: str = "all", page: int = 1, page_size: int = 10) -> dict:
        """
        获取用户列表（分页）
        
        Args:
            platform: 平台筛选（all表示全部）
            page: 页码（从1开始）
            page_size: 每页数量
            
        Returns:
            {users: list, total: int, page: int, total_pages: int, platforms: list}
        """
        db = self.quota_validator.db
        offset = (page - 1) * page_size
        
        # 构建查询条件
        where_clause = ""
        params = []
        if platform and platform != "all":
            where_clause = "WHERE u.platform = ?"
            params.append(platform)
        
        # 查询总数
        count_sql = f"""
            SELECT COUNT(*) as count FROM users u {where_clause}
        """
        count_result = db.execute_one(count_sql, tuple(params))
        total = count_result['count'] if count_result else 0
        total_pages = max(1, (total + page_size - 1) // page_size)
        
        # 查询用户列表（关联会员和积分信息）
        list_sql = f"""
            SELECT 
                u.user_id,
                u.username,
                u.platform,
                u.created_at,
                u.last_active_at,
                COALESCE(m.level, 0) as level,
                m.expire_date,
                COALESCE(p.balance, 0) as balance
            FROM users u
            LEFT JOIN memberships m ON u.user_id = m.user_id
            LEFT JOIN points_accounts p ON u.user_id = p.user_id
            {where_clause}
            ORDER BY u.created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([page_size, offset])
        users = db.execute(list_sql, tuple(params))
        users_list = [dict(u) for u in users] if users else []
        
        # 获取所有平台
        platforms_result = db.execute("""
            SELECT DISTINCT platform FROM users ORDER BY platform
        """)
        platforms = ["all"] + [p['platform'] for p in platforms_result] if platforms_result else ["all"]
        
        return {
            'users': users_list,
            'total': total,
            'page': page,
            'total_pages': total_pages,
            'platforms': platforms
        }

    async def _get_user_detail(self, user_id: str) -> dict:
        """获取用户详细信息"""
        db = self.quota_validator.db
        
        # 基本信息
        user = db.execute_one("""
            SELECT user_id, username, platform, created_at, last_active_at
            FROM users WHERE user_id = ?
        """, (user_id,))
        
        if not user:
            return {}
        
        result = dict(user)
        
        # 会员信息
        membership = await self.membership_manager.get_membership_info(user_id)
        result['membership'] = membership or {}
        
        # 积分信息
        points = await self.points_manager.get_account_info(user_id)
        result['points'] = points or {}
        
        return result
    
    async def search_users(self, keyword: str, limit: int = 10) -> Tuple[List[Dict], int]:
        """
        搜索用户
        
        Args:
            keyword: 搜索关键词（支持用户ID、昵称、平台用户ID的模糊匹配）
            limit: 返回结果数量限制
            
        Returns:
            (用户列表, 匹配总数)
        """
        db = self.quota_validator.db
        keyword_pattern = f"%{keyword}%"
        
        # 查询匹配总数
        count_result = db.execute_one("""
            SELECT COUNT(*) as count FROM users
            WHERE user_id LIKE ? OR username LIKE ? OR platform_user_id LIKE ?
        """, (keyword_pattern, keyword_pattern, keyword_pattern))
        total = count_result['count'] if count_result else 0
        
        # 查询用户列表
        users = db.execute("""
            SELECT 
                u.user_id,
                u.username,
                u.platform,
                u.platform_user_id,
                u.created_at,
                u.last_active_at,
                COALESCE(m.level, 0) as level,
                COALESCE(p.balance, 0) as balance
            FROM users u
            LEFT JOIN memberships m ON u.user_id = m.user_id
            LEFT JOIN points_accounts p ON u.user_id = p.user_id
            WHERE u.user_id LIKE ? OR u.username LIKE ? OR u.platform_user_id LIKE ?
            ORDER BY 
                CASE 
                    WHEN u.user_id = ? THEN 0
                    WHEN u.username = ? THEN 1
                    WHEN u.user_id LIKE ? THEN 2
                    ELSE 3
                END,
                u.last_active_at DESC
            LIMIT ?
        """, (keyword_pattern, keyword_pattern, keyword_pattern, 
              keyword, keyword, f"{keyword}%", limit))
        
        users_list = [dict(u) for u in users] if users else []
        
        return users_list, total
    
    async def get_quota_rules(self, plugin: str = "all") -> Tuple[List[Dict], List[str]]:
        """
        获取配额规则列表
        
        Args:
            plugin: 插件名筛选（all表示全部）
            
        Returns:
            (规则列表, 插件列表)
        """
        db = self.quota_validator.db
        
        # 获取所有插件
        plugins_result = db.execute("""
            SELECT DISTINCT plugin_name FROM quota_rules ORDER BY plugin_name
        """)
        plugins = [p['plugin_name'] for p in plugins_result] if plugins_result else []
        
        # 构建查询
        if plugin and plugin != "all":
            rules = db.execute("""
                SELECT 
                    plugin_name,
                    action_type,
                    description,
                    member_level,
                    daily_limit,
                    points_cost
                FROM quota_rules
                WHERE plugin_name = ? AND is_active = 1
                ORDER BY plugin_name, action_type, member_level
            """, (plugin,))
        else:
            rules = db.execute("""
                SELECT 
                    plugin_name,
                    action_type,
                    description,
                    member_level,
                    daily_limit,
                    points_cost
                FROM quota_rules
                WHERE is_active = 1
                ORDER BY plugin_name, action_type, member_level
            """)
        
        # 整理规则数据（按 action_type 聚合各等级限制）
        rules_map = {}
        for rule in rules or []:
            key = f"{rule['plugin_name']}:{rule['action_type']}"
            if key not in rules_map:
                rules_map[key] = {
                    'plugin_name': rule['plugin_name'],
                    'action_type': rule['action_type'],
                    'description': rule['description'] or rule['action_type'],
                    'free_limit': -1,
                    'premium_limit': -1,
                    'vip_limit': -1,
                }
            
            level = rule['member_level']
            limit = rule['daily_limit']
            if level == 0:
                rules_map[key]['free_limit'] = limit
            elif level == 1:
                rules_map[key]['premium_limit'] = limit
            elif level == 2:
                rules_map[key]['vip_limit'] = limit
        
        return list(rules_map.values()), plugins
    
    async def get_points_stats(self) -> Dict[str, Any]:
        """
        获取积分统计数据
        
        Returns:
            积分统计字典
        """
        db = self.quota_validator.db
        
        # 用户总数
        total_users = db.execute_one("SELECT COUNT(*) as count FROM users")
        
        # 有积分用户数和总积分
        points_stats = db.execute_one("""
            SELECT 
                COUNT(*) as users_with_points,
                COALESCE(SUM(balance), 0) as total_balance,
                COALESCE(AVG(balance), 0) as avg_balance
            FROM points_accounts
            WHERE balance > 0
        """)
        
        # 近7天积分流动
        flow_stats = db.execute_one("""
            SELECT 
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as total_earned,
                COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as total_spent
            FROM points_transactions
            WHERE created_at >= date('now', '-7 days')
        """)
        
        # 积分来源分布
        source_dist = db.execute("""
            SELECT 
                source,
                SUM(amount) as amount
            FROM points_transactions
            WHERE amount > 0 AND created_at >= date('now', '-7 days')
            GROUP BY source
            ORDER BY amount DESC
            LIMIT 5
        """)
        
        # 积分排行
        top_users = db.execute("""
            SELECT 
                u.username,
                p.balance
            FROM points_accounts p
            JOIN users u ON p.user_id = u.user_id
            ORDER BY p.balance DESC
            LIMIT 5
        """)
        
        total_earned = flow_stats['total_earned'] if flow_stats else 0
        total_spent = flow_stats['total_spent'] if flow_stats else 0
        
        return {
            'total_users': total_users['count'] if total_users else 0,
            'users_with_points': points_stats['users_with_points'] if points_stats else 0,
            'total_balance': points_stats['total_balance'] if points_stats else 0,
            'avg_balance': points_stats['avg_balance'] if points_stats else 0,
            'total_earned_7d': total_earned,
            'total_spent_7d': total_spent,
            'net_flow_7d': total_earned - total_spent,
            'source_distribution': [dict(s) for s in source_dist] if source_dist else [],
            'top_users': [dict(u) for u in top_users] if top_users else [],
        }
    
    async def get_search_stats(self) -> Dict[str, Any]:
        """
        获取搜索统计数据
        
        Returns:
            搜索统计字典
        """
        db = self.quota_validator.db
        
        # 总搜索次数（近7天）
        total = db.execute_one("""
            SELECT COUNT(*) as count FROM search_statistics
            WHERE created_at >= date('now', '-7 days')
        """)
        
        # 搜索用户数
        users = db.execute_one("""
            SELECT COUNT(DISTINCT user_id) as count FROM search_statistics
            WHERE created_at >= date('now', '-7 days')
        """)
        
        # 平均结果数
        avg = db.execute_one("""
            SELECT AVG(result_count) as avg FROM search_statistics
            WHERE created_at >= date('now', '-7 days')
        """)
        
        # 按插件+类型+平台统计（细分）
        by_detail = db.execute("""
            SELECT 
                plugin_name as plugin, 
                search_type as type,
                platform,
                COUNT(*) as count
            FROM search_statistics
            WHERE created_at >= date('now', '-7 days')
            GROUP BY plugin_name, search_type, platform
            ORDER BY count DESC
        """)
        
        # 热门搜索关键词
        hot_keywords = db.execute("""
            SELECT keyword, plugin_name as plugin, COUNT(*) as count
            FROM search_statistics
            WHERE created_at >= date('now', '-7 days')
            GROUP BY keyword, plugin_name
            ORDER BY count DESC
            LIMIT 10
        """)
        
        return {
            'total_searches': total['count'] if total else 0,
            'unique_users': users['count'] if users else 0,
            'avg_results': avg['avg'] if avg and avg['avg'] else 0,
            'by_detail': [dict(d) for d in by_detail] if by_detail else [],
            'hot_keywords': [dict(k) for k in hot_keywords] if hot_keywords else [],
        }
    
    async def get_download_stats(self) -> Dict[str, Any]:
        """
        获取下载统计数据
        
        Returns:
            下载统计字典
        """
        db = self.quota_validator.db
        
        # 总下载次数（近7天）
        total = db.execute_one("""
            SELECT COUNT(*) as count FROM download_statistics
            WHERE created_at >= date('now', '-7 days')
        """)
        
        # 下载用户数
        users = db.execute_one("""
            SELECT COUNT(DISTINCT user_id) as count FROM download_statistics
            WHERE created_at >= date('now', '-7 days')
        """)
        
        # 按插件+平台/源统计（细分）
        by_detail = db.execute("""
            SELECT 
                plugin_name as plugin, 
                platform,
                source,
                COUNT(*) as count
            FROM download_statistics
            WHERE created_at >= date('now', '-7 days')
            GROUP BY plugin_name, platform, source
            ORDER BY count DESC
        """)
        
        # 热门下载
        hot_items = db.execute("""
            SELECT item_id, item_name as name, plugin_name as plugin, COUNT(*) as count
            FROM download_statistics
            WHERE created_at >= date('now', '-7 days')
            GROUP BY item_id, plugin_name
            ORDER BY count DESC
            LIMIT 10
        """)
        
        return {
            'total_downloads': total['count'] if total else 0,
            'unique_users': users['count'] if users else 0,
            'by_detail': [dict(d) for d in by_detail] if by_detail else [],
            'hot_items': [dict(i) for i in hot_items] if hot_items else [],
        }
    
    # ==================== 配额规则编辑 ====================
    
    async def cleanup_duplicate_quota_rules(self):
        """清理重复的配额规则，只保留每个 plugin_name + action_type 的最新记录"""
        db = self.quota_validator.db
        try:
            # 删除重复记录，保留 id 最大的
            db.execute_write("""
                DELETE FROM quota_rules 
                WHERE id NOT IN (
                    SELECT MAX(id) FROM quota_rules 
                    GROUP BY plugin_name, action_type
                )
            """)
            logger.info("[QuotaAdmin] 已清理重复的配额规则")
        except Exception as e:
            logger.error(f"[QuotaAdmin] 清理重复配额规则失败: {e}")
    
    async def get_quota_plugins(self) -> List[str]:
        """获取所有有配额规则的插件列表"""
        db = self.quota_validator.db
        result = db.execute("""
            SELECT DISTINCT plugin_name FROM quota_rules ORDER BY plugin_name
        """)
        return [r['plugin_name'] for r in result] if result else []
    
    async def get_plugin_quota_rules(self, plugin: str) -> List[Dict]:
        """获取指定插件的配额规则（聚合各等级）"""
        db = self.quota_validator.db
        # 表结构是每个 member_level 一条记录，需要聚合
        result = db.execute("""
            SELECT 
                plugin_name, 
                action_type, 
                MAX(description) as description,
                MAX(CASE WHEN member_level = 0 THEN daily_limit END) as free_daily_limit,
                MAX(CASE WHEN member_level = 0 THEN points_cost END) as free_points_cost,
                MAX(CASE WHEN member_level = 1 THEN daily_limit END) as premium_daily_limit,
                MAX(CASE WHEN member_level = 1 THEN points_cost END) as premium_points_cost,
                MAX(CASE WHEN member_level = 2 THEN daily_limit END) as vip_daily_limit,
                MAX(CASE WHEN member_level = 2 THEN points_cost END) as vip_points_cost
            FROM quota_rules 
            WHERE plugin_name = ? AND is_active = 1
            GROUP BY plugin_name, action_type
        """, (plugin,))
        return [dict(r) for r in result] if result else []
    
    async def get_quota_rule(self, plugin: str, action: str) -> Optional[Dict]:
        """获取单条配额规则（聚合各等级）"""
        db = self.quota_validator.db
        result = db.execute_one("""
            SELECT 
                plugin_name, 
                action_type, 
                MAX(description) as description,
                MAX(CASE WHEN member_level = 0 THEN daily_limit END) as free_daily_limit,
                MAX(CASE WHEN member_level = 0 THEN points_cost END) as free_points_cost,
                MAX(CASE WHEN member_level = 1 THEN daily_limit END) as premium_daily_limit,
                MAX(CASE WHEN member_level = 1 THEN points_cost END) as premium_points_cost,
                MAX(CASE WHEN member_level = 2 THEN daily_limit END) as vip_daily_limit,
                MAX(CASE WHEN member_level = 2 THEN points_cost END) as vip_points_cost
            FROM quota_rules 
            WHERE plugin_name = ? AND action_type = ? AND is_active = 1
            GROUP BY plugin_name, action_type
        """, (plugin, action))
        return dict(result) if result else None
    
    async def update_quota_rule(self, plugin: str, action: str, level: str, daily_limit: int, points_cost: int) -> bool:
        """更新配额规则"""
        db = self.quota_validator.db
        # level: free=0, premium=1, vip=2
        level_map = {'free': 0, 'premium': 1, 'vip': 2}
        member_level = level_map.get(level, 0)
        try:
            db.execute_write("""
                UPDATE quota_rules 
                SET daily_limit = ?, points_cost = ?, updated_at = datetime('now')
                WHERE plugin_name = ? AND action_type = ? AND member_level = ?
            """, (daily_limit, points_cost, plugin, action, member_level))
            return True
        except Exception as e:
            logger.error(f"更新配额规则失败: {e}")
            return False
    
    async def set_rule_unlimited(self, plugin: str, action: str) -> bool:
        """设置规则为无限制（所有等级）"""
        db = self.quota_validator.db
        try:
            db.execute_write("""
                UPDATE quota_rules 
                SET daily_limit = -1, points_cost = 0, updated_at = datetime('now')
                WHERE plugin_name = ? AND action_type = ?
            """, (plugin, action))
            return True
        except Exception as e:
            logger.error(f"设置无限制失败: {e}")
            return False
    
    async def set_rule_limited(self, plugin: str, action: str) -> bool:
        """恢复规则为默认限制"""
        db = self.quota_validator.db
        try:
            # free: 10次/天, 1积分
            db.execute_write("""
                UPDATE quota_rules 
                SET daily_limit = 10, points_cost = 1, updated_at = datetime('now')
                WHERE plugin_name = ? AND action_type = ? AND member_level = 0
            """, (plugin, action))
            # premium: 50次/天, 1积分
            db.execute_write("""
                UPDATE quota_rules 
                SET daily_limit = 50, points_cost = 1, updated_at = datetime('now')
                WHERE plugin_name = ? AND action_type = ? AND member_level = 1
            """, (plugin, action))
            # vip: 无限, 0积分
            db.execute_write("""
                UPDATE quota_rules 
                SET daily_limit = -1, points_cost = 0, updated_at = datetime('now')
                WHERE plugin_name = ? AND action_type = ? AND member_level = 2
            """, (plugin, action))
            return True
        except Exception as e:
            logger.error(f"恢复限制失败: {e}")
            return False
    
    # ==================== 黑名单管理 ====================
    
    async def get_blacklist(self) -> List[Dict]:
        """获取黑名单列表"""
        db = self.quota_validator.db
        # 检查表是否存在，不存在则创建
        db.execute_write("""
            CREATE TABLE IF NOT EXISTS blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                reason TEXT,
                banned_by TEXT,
                banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        result = db.execute("""
            SELECT * FROM blacklist ORDER BY banned_at DESC
        """)
        return [dict(r) for r in result] if result else []
    
    async def add_to_blacklist(self, user_id: str, reason: str, banned_by: str) -> bool:
        """添加用户到黑名单"""
        db = self.quota_validator.db
        try:
            db.execute_write("""
                INSERT OR REPLACE INTO blacklist (user_id, reason, banned_by, banned_at)
                VALUES (?, ?, ?, datetime('now'))
            """, (user_id, reason, banned_by))
            return True
        except Exception as e:
            logger.error(f"添加黑名单失败: {e}")
            return False
    
    async def remove_from_blacklist(self, user_id: str) -> bool:
        """从黑名单移除用户"""
        db = self.quota_validator.db
        try:
            db.execute_write("""
                DELETE FROM blacklist WHERE user_id = ?
            """, (user_id,))
            return True
        except Exception as e:
            logger.error(f"移除黑名单失败: {e}")
            return False
    
    async def is_blacklisted(self, user_id: str) -> bool:
        """检查用户是否在黑名单"""
        db = self.quota_validator.db
        result = db.execute_one("""
            SELECT 1 FROM blacklist WHERE user_id = ?
        """, (user_id,))
        return result is not None
    
    # ==================== 积分操作 ====================
    
    async def add_points_single(self, user_id: str, amount: int, admin_id: str) -> bool:
        """给单个用户充值积分"""
        db = self.quota_validator.db
        try:
            # 确保用户存在
            db.execute_write("""
                INSERT OR IGNORE INTO points_account (user_id, balance, created_at)
                VALUES (?, 0, datetime('now'))
            """, (user_id,))
            
            # 增加积分
            db.execute_write("""
                UPDATE points_account SET balance = balance + ?, updated_at = datetime('now')
                WHERE user_id = ?
            """, (amount, user_id))
            
            # 记录交易
            db.execute_write("""
                INSERT INTO points_transaction (user_id, amount, type, source, description, created_at)
                VALUES (?, ?, 'earn', 'admin', ?, datetime('now'))
            """, (user_id, amount, f"管理员{admin_id}充值"))
            
            return True
        except Exception as e:
            logger.error(f"充值积分失败: {e}")
            return False
    
    async def add_points_batch(self, amount: int, admin_id: str) -> int:
        """批量给所有用户充值积分，返回充值用户数"""
        db = self.quota_validator.db
        try:
            # 获取所有用户
            users = db.execute("SELECT user_id FROM points_account")
            if not users:
                return 0
            
            count = 0
            for user in users:
                user_id = user['user_id']
                db.execute_write("""
                    UPDATE points_account SET balance = balance + ?, updated_at = datetime('now')
                    WHERE user_id = ?
                """, (amount, user_id))
                
                db.execute_write("""
                    INSERT INTO points_transaction (user_id, amount, type, source, description, created_at)
                    VALUES (?, ?, 'earn', 'admin', ?, datetime('now'))
                """, (user_id, amount, f"管理员{admin_id}批量充值"))
                count += 1
            
            return count
        except Exception as e:
            logger.error(f"批量充值失败: {e}")
            return 0
    
    async def deduct_points(self, user_id: str, amount: int, admin_id: str) -> bool:
        """扣除用户积分"""
        db = self.quota_validator.db
        try:
            # 检查余额
            account = db.execute_one("""
                SELECT balance FROM points_account WHERE user_id = ?
            """, (user_id,))
            
            if not account:
                return False
            
            # 扣除积分（允许扣成负数）
            db.execute_write("""
                UPDATE points_account SET balance = balance - ?, updated_at = datetime('now')
                WHERE user_id = ?
            """, (amount, user_id))
            
            # 记录交易
            db.execute_write("""
                INSERT INTO points_transaction (user_id, amount, type, source, description, created_at)
                VALUES (?, ?, 'spend', 'admin', ?, datetime('now'))
            """, (user_id, -amount, f"管理员{admin_id}扣除"))
            
            return True
        except Exception as e:
            logger.error(f"扣除积分失败: {e}")
            return False
    
    # ==================== 公告管理 ====================
    
    async def get_announcements(self, limit: int = 10) -> List[Dict]:
        """获取公告列表"""
        db = self.quota_validator.db
        # 确保表存在
        db.execute_write("""
            CREATE TABLE IF NOT EXISTS announcements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        result = db.execute("""
            SELECT * FROM announcements ORDER BY created_at DESC LIMIT ?
        """, (limit,))
        return [dict(r) for r in result] if result else []
    
    async def create_announcement(self, content: str, admin_id: str) -> int:
        """创建公告，返回公告ID"""
        db = self.quota_validator.db
        try:
            # 确保表存在
            db.execute_write("""
                CREATE TABLE IF NOT EXISTS announcements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    created_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            db.execute_write("""
                INSERT INTO announcements (content, created_by, created_at)
                VALUES (?, ?, datetime('now'))
            """, (content, admin_id))
            
            # 获取新创建的ID - 使用更可靠的方式
            result = db.execute_one("SELECT MAX(id) as id FROM announcements")
            ann_id = result['id'] if result else 0
            logger.info(f"[QuotaAdmin] 公告创建成功: id={ann_id}, content={content[:50]}")
            return ann_id
        except Exception as e:
            logger.error(f"创建公告失败: {e}", exc_info=True)
            return 0
    
    async def get_all_user_ids(self) -> List[str]:
        """获取所有用户ID（用于发送公告）"""
        db = self.quota_validator.db
        result = db.execute("SELECT DISTINCT user_id FROM users")
        return [r['user_id'] for r in result] if result else []
    
    # ==================== 用户详情 ====================
    
    async def get_user_detail(self, user_id: str) -> Dict[str, Any]:
        """获取用户详细信息"""
        db = self.quota_validator.db
        
        # 基本信息（表名是 users）
        user_info = db.execute_one("""
            SELECT * FROM users WHERE user_id = ?
        """, (user_id,))
        
        # 会员信息
        membership = await self.membership_manager.get_membership_info(user_id)
        
        # 积分信息
        points = await self.points_manager.get_account_info(user_id)
        
        # 今日配额使用
        quota_usage = {}
        try:
            usage = db.execute("""
                SELECT action_type, SUM(used_count) as count
                FROM quota_usage
                WHERE user_id = ? AND date(usage_date) = date('now')
                GROUP BY action_type
            """, (user_id,))
            if usage:
                quota_usage = {r['action_type']: r['count'] for r in usage}
        except:
            pass
        
        return {
            'user_info': dict(user_info) if user_info else {'user_id': user_id},
            'membership': membership or {},
            'points': points or {},
            'quota_usage': quota_usage
        }
    
    async def set_user_membership(self, user_id: str, level: int, months: int = 1) -> bool:
        """设置用户会员等级"""
        from common.quota_validator import MemberLevel
        try:
            member_level = MemberLevel(level)
            return await self.membership_manager.upgrade(user_id, member_level, months)
        except Exception as e:
            logger.error(f"设置会员等级失败: {e}")
            return False
    
    # ==================== 配额统计 ====================
    
    async def get_quota_statistics(self) -> Dict[str, Any]:
        """获取配额使用统计"""
        db = self.quota_validator.db
        
        # 功能使用排行 TOP 10
        top_actions = db.execute("""
            SELECT action_type, COUNT(*) as total_count
            FROM quota_usage
            GROUP BY action_type
            ORDER BY total_count DESC
            LIMIT 10
        """)
        
        # 用户使用排行 TOP 10
        top_users = db.execute("""
            SELECT u.user_id, u.username, COUNT(*) as total_count
            FROM quota_usage q
            JOIN users u ON q.user_id = u.user_id
            GROUP BY q.user_id
            ORDER BY total_count DESC
            LIMIT 10
        """)
        
        # 插件使用对比
        plugin_stats = db.execute("""
            SELECT plugin_name, COUNT(*) as total_count
            FROM quota_usage
            GROUP BY plugin_name
            ORDER BY total_count DESC
        """)
        
        return {
            'top_actions': [dict(row) for row in top_actions] if top_actions else [],
            'top_users': [dict(row) for row in top_users] if top_users else [],
            'plugin_stats': [dict(row) for row in plugin_stats] if plugin_stats else []
        }
    
    # ==================== 系统状态 ====================
    
    async def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        import psutil
        import os
        from datetime import datetime
        
        db = self.quota_validator.db
        
        # 服务器运行状态
        server_status = {}
        try:
            # 进程信息
            process = psutil.Process(os.getpid())
            
            # 运行时间
            create_time = datetime.fromtimestamp(process.create_time())
            uptime_seconds = (datetime.now() - create_time).total_seconds()
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            if days > 0:
                uptime_str = f"{days}天{hours}小时{minutes}分"
            elif hours > 0:
                uptime_str = f"{hours}小时{minutes}分"
            else:
                uptime_str = f"{minutes}分钟"
            
            # CPU和内存
            cpu_percent = process.cpu_percent(interval=0.1)
            memory_info = process.memory_info()
            memory_used_mb = memory_info.rss / 1024 / 1024
            memory_percent = process.memory_percent()
            
            # 磁盘空间
            disk = psutil.disk_usage('/')
            disk_total_gb = disk.total / 1024 / 1024 / 1024
            disk_used_gb = disk.used / 1024 / 1024 / 1024
            disk_free_gb = disk.free / 1024 / 1024 / 1024
            disk_percent = disk.percent
            
            server_status = {
                'uptime': uptime_str,
                'cpu_percent': cpu_percent,
                'memory_used_mb': memory_used_mb,
                'memory_percent': memory_percent,
                'disk_total_gb': disk_total_gb,
                'disk_used_gb': disk_used_gb,
                'disk_free_gb': disk_free_gb,
                'disk_percent': disk_percent
            }
        except Exception as e:
            logger.warning(f"获取服务器状态失败: {e}")
            server_status = {
                'uptime': '未知',
                'cpu_percent': 0,
                'memory_used_mb': 0,
                'memory_percent': 0,
                'disk_total_gb': 0,
                'disk_used_gb': 0,
                'disk_free_gb': 0,
                'disk_percent': 0
            }
        
        # 数据库统计
        user_count = db.execute_one("SELECT COUNT(*) as count FROM users")
        quota_count = db.execute_one("SELECT COUNT(*) as count FROM quota_usage")
        transaction_count = db.execute_one("SELECT COUNT(*) as count FROM points_transactions")
        
        # 限流器状态
        from common.rate_limiter import get_rate_limiter
        rate_limiter = get_rate_limiter()
        rate_stats = rate_limiter.get_stats()
        
        # 插件列表（从context获取）
        plugins = []
        if self.context:
            try:
                plugin_manager = self.context.get_registered_star()
                for star in plugin_manager:
                    plugins.append({
                        'name': star.star_cls.name if hasattr(star, 'star_cls') else str(star),
                        'enabled': True
                    })
            except:
                pass
        
        # 未推送公告数
        unread = db.execute_one("""
            SELECT COUNT(*) as count FROM announcements 
            WHERE created_at > datetime('now', '-7 days')
        """)
        
        return {
            'server': server_status,
            'database': {
                'user_count': user_count['count'] if user_count else 0,
                'quota_count': quota_count['count'] if quota_count else 0,
                'transaction_count': transaction_count['count'] if transaction_count else 0
            },
            'rate_limiter': rate_stats,
            'plugins': plugins,
            'unread_announcements': unread['count'] if unread else 0
        }
    
    # ==================== 公告被动通知 ====================
    
    async def get_unread_announcements(self, user_id: str) -> List[Dict]:
        """获取用户未读公告"""
        db = self.quota_validator.db
        
        # 确保表存在
        db.execute_write("""
            CREATE TABLE IF NOT EXISTS user_announcement_read (
                user_id TEXT,
                announcement_id INTEGER,
                read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, announcement_id)
            )
        """)
        
        # 获取用户未读的公告（最近7天内）
        result = db.execute("""
            SELECT a.* FROM announcements a
            WHERE a.created_at > datetime('now', '-7 days')
            AND a.id NOT IN (
                SELECT announcement_id FROM user_announcement_read WHERE user_id = ?
            )
            ORDER BY a.created_at DESC
        """, (user_id,))
        
        return [dict(r) for r in result] if result else []
    
    async def mark_announcement_read(self, user_id: str, announcement_id: int) -> bool:
        """标记公告已读"""
        db = self.quota_validator.db
        try:
            db.execute_write("""
                INSERT OR IGNORE INTO user_announcement_read (user_id, announcement_id, read_at)
                VALUES (?, ?, datetime('now'))
            """, (user_id, announcement_id))
            return True
        except Exception as e:
            logger.error(f"标记公告已读失败: {e}")
            return False
    
    async def mark_all_announcements_read(self, user_id: str) -> int:
        """标记所有公告已读"""
        db = self.quota_validator.db
        try:
            # 获取所有未读公告
            unread = await self.get_unread_announcements(user_id)
            for ann in unread:
                await self.mark_announcement_read(user_id, ann['id'])
            return len(unread)
        except Exception as e:
            logger.error(f"标记所有公告已读失败: {e}")
            return 0
