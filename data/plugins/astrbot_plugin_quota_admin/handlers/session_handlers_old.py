"""
会话处理器
使用会话控制实现多轮对话
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
from astrbot.api import logger


class SessionHandler:
    """会话处理器"""
    
    def __init__(self, quota_validator, membership_manager, points_manager, quota_analytics, admins: List[str]):
        self.quota_validator = quota_validator
        self.membership_manager = membership_manager
        self.points_manager = points_manager
        self.quota_analytics = quota_analytics
        self.admins = admins
        
        # 会话存储 {session_id: session_data}
        self.sessions: Dict[str, Dict[str, Any]] = {}
    
    def _is_admin(self, user_id: str) -> bool:
        """检查是否为管理员"""
        return user_id in self.admins
    
    def _create_session(self, session_id: str, session_type: str, user_id: str, data: Dict[str, Any] = None):
        """创建会话"""
        self.sessions[session_id] = {
            'type': session_type,
            'user_id': user_id,
            'step': 0,
            'data': data or {},
            'created_at': datetime.now()
        }
    
    def _get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话"""
        return self.sessions.get(session_id)
    
    def _update_session(self, session_id: str, step: int = None, data: Dict[str, Any] = None):
        """更新会话"""
        if session_id in self.sessions:
            if step is not None:
                self.sessions[session_id]['step'] = step
            if data is not None:
                self.sessions[session_id]['data'].update(data)
    
    def _end_session(self, session_id: str):
        """结束会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]
    
    # ==================== 我的信息会话 ====================
    
    async def start_my_info_session(self, user_id: str, session_id: str) -> str:
        """启动"我的信息"会话"""
        try:
            # 创建会话
            self._create_session(session_id, 'my_info', user_id)
            
            result = "👤 我的信息\n\n"
            result += "请选择要查询的信息：\n\n"
            result += "1. 我的配额 - 查看配额使用情况\n"
            result += "2. 我的积分 - 查看积分余额和流水\n"
            result += "3. 我的会员 - 查看会员信息\n"
            result += "4. 使用记录 - 查看历史使用记录\n"
            result += "0. 退出\n\n"
            result += "💡 请回复数字选择"
            
            return result
            
        except Exception as e:
            logger.error(f"[SessionHandler] 启动我的信息会话失败: {e}", exc_info=True)
            return f"❌ 启动会话失败: {e}"
    
    async def _handle_my_info_step(self, user_id: str, session_id: str, message: str) -> str:
        """处理"我的信息"会话的步骤"""
        try:
            session = self._get_session(session_id)
            if not session or session['type'] != 'my_info':
                return "❌ 会话已过期，请重新开始"
            
            step = session['step']
            
            if step == 0:
                # 选择查询类型
                message = message.strip()
                
                # 支持取消
                if message in ['0', '取消', 'q', 'Q']:
                    self._end_session(session_id)
                    return "✅ 已退出"
                
                try:
                    choice = int(message)
                except ValueError:
                    return "❌ 请输入有效的数字"
                
                if choice == 0:
                    self._end_session(session_id)
                    return "✅ 已退出"
                
                # 导入用户命令处理器
                from .user_commands import UserCommandHandler
                handler = UserCommandHandler(
                    self.quota_validator,
                    self.membership_manager,
                    self.points_manager
                )
                
                if choice == 1:
                    # 查询配额
                    result = await handler.handle_my_quota(user_id)
                    self._end_session(session_id)
                    return result
                
                elif choice == 2:
                    # 查询积分
                    result = await handler.handle_my_points(user_id)
                    self._end_session(session_id)
                    return result
                
                elif choice == 3:
                    # 查询会员
                    result = await handler.handle_my_membership(user_id)
                    self._end_session(session_id)
                    return result
                
                elif choice == 4:
                    # 查询使用记录 - 进入下一步选择天数
                    self._update_session(session_id, step=1)
                    return "💡 请输入要查询的天数（1-30天，默认7天）："
                
                else:
                    return "❌ 无效的选择，请输入0-4"
            
            elif step == 1:
                # 输入查询天数
                try:
                    days = int(message.strip())
                    days = min(max(days, 1), 30)  # 限制在1-30天
                except ValueError:
                    days = 7  # 默认7天
                
                from .user_commands import UserCommandHandler
                handler = UserCommandHandler(
                    self.quota_validator,
                    self.membership_manager,
                    self.points_manager
                )
                
                result = await handler.handle_usage_history(user_id, days)
                self._end_session(session_id)
                return result
            
        except Exception as e:
            logger.error(f"[SessionHandler] 处理我的信息步骤失败: {e}", exc_info=True)
            self._end_session(session_id)
            return f"❌ 查询失败: {e}"
    
    # ==================== 配额包兑换会话 ====================
    
    async def start_redeem_session(self, user_id: str, session_id: str) -> str:
        """启动配额包兑换会话"""
        try:
            # 获取用户积分
            account = self.points_manager.get_account(user_id)
            balance = account.balance if account else 0
            
            if balance <= 0:
                return "❌ 您的积分余额不足，无法兑换配额包\n\n💡 使用 /我的积分 查看积分余额"
            
            # 获取可用的配额包
            packages = self._get_available_packages()
            
            if not packages:
                return "❌ 暂无可兑换的配额包"
            
            # 创建会话
            self._create_session(session_id, 'redeem', user_id, {'balance': balance})
            
            result = f"🎁 配额包兑换\n\n"
            result += f"💰 您的积分余额：{balance}\n\n"
            result += "📦 可兑换的配额包：\n\n"
            
            for i, pkg in enumerate(packages, 1):
                result += f"{i}. {pkg['name']}\n"
                result += f"   积分：{pkg['points']} | 有效期：{pkg['duration']}小时\n"
                result += f"   内容：{pkg['description']}\n\n"
            
            result += "💡 请回复数字选择要兑换的配额包\n"
            result += "💡 回复 0 取消兑换"
            
            return result
            
        except Exception as e:
            logger.error(f"[SessionHandler] 启动兑换会话失败: {e}", exc_info=True)
            return f"❌ 启动兑换会话失败: {e}"
    
    def _get_available_packages(self) -> List[Dict[str, Any]]:
        """获取可用的配额包"""
        return [
            {
                'id': 'music_flac_5',
                'name': '无损音乐包（5次）',
                'points': 50,
                'duration': 24,
                'action_type': 'music_download_flac',
                'boost_count': 5,
                'description': '5次无损音乐下载'
            },
            {
                'id': 'music_320_10',
                'name': '高品质音乐包（10次）',
                'points': 30,
                'duration': 24,
                'action_type': 'music_download_320',
                'boost_count': 10,
                'description': '10次320k音乐下载'
            },
            {
                'id': 'yunpan_10',
                'name': '云盘资源包（10次）',
                'points': 40,
                'duration': 24,
                'action_type': 'yunpan_download',
                'boost_count': 10,
                'description': '10次云盘资源下载'
            },
            {
                'id': 'all_day_pass',
                'name': '全功能日卡',
                'points': 100,
                'duration': 24,
                'action_type': 'all',
                'boost_count': 50,
                'description': '所有操作+50次'
            }
        ]
    
    async def _handle_redeem_step(self, user_id: str, session_id: str, message: str) -> str:
        """处理兑换会话的步骤"""
        try:
            session = self._get_session(session_id)
            if not session or session['type'] != 'redeem':
                return "❌ 会话已过期，请重新开始"
            
            step = session['step']
            
            if step == 0:
                # 选择配额包
                try:
                    choice = int(message.strip())
                except ValueError:
                    return "❌ 请输入有效的数字"
                
                if choice == 0:
                    self._end_session(session_id)
                    return "✅ 已取消兑换"
                
                packages = self._get_available_packages()
                if choice < 1 or choice > len(packages):
                    return f"❌ 请输入1-{len(packages)}之间的数字"
                
                selected_pkg = packages[choice - 1]
                balance = session['data']['balance']
                
                if balance < selected_pkg['points']:
                    return f"❌ 积分不足\n需要：{selected_pkg['points']} 积分\n当前：{balance} 积分"
                
                # 更新会话
                self._update_session(session_id, step=1, data={'package': selected_pkg})
                
                result = f"📦 确认兑换\n\n"
                result += f"配额包：{selected_pkg['name']}\n"
                result += f"消耗积分：{selected_pkg['points']}\n"
                result += f"有效期：{selected_pkg['duration']}小时\n"
                result += f"内容：{selected_pkg['description']}\n\n"
                result += "💡 回复 Y 确认兑换，回复 N 取消"
                
                return result
            
            elif step == 1:
                # 确认兑换
                confirm = message.strip().upper()
                
                if confirm == 'N':
                    self._end_session(session_id)
                    return "✅ 已取消兑换"
                
                if confirm != 'Y':
                    return "❌ 请回复 Y 确认或 N 取消"
                
                # 执行兑换
                package = session['data']['package']
                
                # 扣除积分
                success = self.points_manager.consume(
                    user_id=user_id,
                    amount=package['points'],
                    description=f"兑换配额包: {package['name']}"
                )
                
                if not success:
                    self._end_session(session_id)
                    return "❌ 积分扣除失败，兑换取消"
                
                # 添加配额加成
                if package['action_type'] == 'all':
                    # 全功能日卡，为所有操作添加加成
                    action_types = ['music_download_flac', 'music_download_320', 'yunpan_download', 'douban_search']
                    for action_type in action_types:
                        self.points_manager.add_quota_boost(
                            user_id=user_id,
                            action_type=action_type,
                            boost_count=package['boost_count'],
                            duration_hours=package['duration'],
                            description=f"兑换: {package['name']}"
                        )
                else:
                    self.points_manager.add_quota_boost(
                        user_id=user_id,
                        action_type=package['action_type'],
                        boost_count=package['boost_count'],
                        duration_hours=package['duration'],
                        description=f"兑换: {package['name']}"
                    )
                
                self._end_session(session_id)
                
                # 获取剩余积分
                account = self.points_manager.get_account(user_id)
                remaining = account.balance if account else 0
                
                result = f"✅ 兑换成功！\n\n"
                result += f"配额包：{package['name']}\n"
                result += f"消耗积分：{package['points']}\n"
                result += f"剩余积分：{remaining}\n"
                result += f"有效期：{package['duration']}小时\n\n"
                result += "💡 配额已添加，立即生效"
                
                logger.info(f"[SessionHandler] 用户 {user_id} 兑换配额包: {package['name']}")
                return result
            
        except Exception as e:
            logger.error(f"[SessionHandler] 处理兑换步骤失败: {e}", exc_info=True)
            self._end_session(session_id)
            return f"❌ 兑换失败: {e}"
    
    # ==================== 管理员配额管理会话 ====================
    
    async def start_admin_session(self, user_id: str, session_id: str) -> str:
        """启动管理员管理会话"""
        try:
            if not self._is_admin(user_id):
                return "❌ 权限不足"
            
            # 创建会话
            self._create_session(session_id, 'admin', user_id)
            
            result = "👑 管理面板\n\n"
            result += "请选择操作：\n\n"
            result += "1. 充值积分 - 为用户充值积分\n"
            result += "2. 升级会员 - 为用户升级会员\n"
            result += "3. 查询用户 - 查询用户详细信息\n"
            result += "4. 重置配额 - 重置用户今日配额\n"
            result += "5. 配额加成 - 添加临时配额加成\n"
            result += "6. 配额统计 - 查看今日配额统计\n"
            result += "0. 退出\n\n"
            result += "💡 请回复数字选择操作"
            
            return result
            
        except Exception as e:
            logger.error(f"[SessionHandler] 启动管理会话失败: {e}", exc_info=True)
            return f"❌ 启动管理会话失败: {e}"
    
    async def _handle_admin_step(self, user_id: str, session_id: str, message: str) -> str:
        """处理管理员会话的步骤"""
        try:
            session = self._get_session(session_id)
            if not session or session['type'] != 'admin':
                return "❌ 会话已过期，请重新开始"
            
            if not self._is_admin(user_id):
                self._end_session(session_id)
                return "❌ 权限不足"
            
            step = session['step']
            message = message.strip()
            
            # 支持取消
            if message in ['0', '取消', 'q', 'Q'] and step == 0:
                self._end_session(session_id)
                return "✅ 已退出管理面板"
            
            if step == 0:
                # 选择操作
                try:
                    choice = int(message)
                except ValueError:
                    return "❌ 请输入有效的数字"
                
                if choice == 0:
                    self._end_session(session_id)
                    return "✅ 已退出管理面板"
                
                if choice == 1:
                    # 充值积分
                    self._update_session(session_id, step=1, data={'action': 'recharge'})
                    return "💡 请输入用户ID："
                
                elif choice == 2:
                    # 升级会员
                    self._update_session(session_id, step=1, data={'action': 'upgrade'})
                    return "💡 请输入用户ID："
                
                elif choice == 3:
                    # 查询用户
                    self._update_session(session_id, step=1, data={'action': 'query'})
                    return "💡 请输入用户ID："
                
                elif choice == 4:
                    # 重置配额
                    self._update_session(session_id, step=1, data={'action': 'reset'})
                    return "💡 请输入用户ID："
                
                elif choice == 5:
                    # 配额加成
                    self._update_session(session_id, step=1, data={'action': 'boost'})
                    return "💡 请输入用户ID："
                
                elif choice == 6:
                    # 查看配额统计
                    result = await self._show_quota_stats()
                    self._end_session(session_id)
                    return result
                
                else:
                    return "❌ 无效的选择，请输入0-6"
            
            elif step == 1:
                # 输入用户ID
                target_user_id = message
                action = session['data']['action']
                
                self._update_session(session_id, step=2, data={'target_user_id': target_user_id})
                
                if action == 'recharge':
                    return "💡 请输入充值积分数量："
                elif action == 'upgrade':
                    return "💡 请输入会员等级（1-高级会员，2-VIP会员）："
                elif action == 'query':
                    # 直接查询用户
                    from .admin_commands import AdminCommandHandler
                    handler = AdminCommandHandler(
                        self.quota_validator,
                        self.membership_manager,
                        self.points_manager,
                        self.admins
                    )
                    result = await handler.handle_query_user(target_user_id)
                    self._end_session(session_id)
                    return result
                elif action == 'reset':
                    return "💡 请输入要重置的操作类型（如：music_download_flac）："
                elif action == 'boost':
                    return "💡 请输入操作类型（如：music_download_flac）："
            
            elif step == 2:
                action = session['data']['action']
                
                if action == 'recharge':
                    # 充值积分
                    try:
                        amount = int(message)
                    except ValueError:
                        return "❌ 请输入有效的数字"
                    
                    if amount <= 0:
                        return "❌ 充值积分必须大于0"
                    
                    target_user_id = session['data']['target_user_id']
                    
                    success = self.points_manager.recharge(
                        user_id=target_user_id,
                        amount=amount,
                        description=f"管理员充值 (by {user_id})"
                    )
                    
                    self._end_session(session_id)
                    
                    if success:
                        result = f"✅ 充值成功！\n\n"
                        result += f"用户ID：{target_user_id}\n"
                        result += f"充值积分：{amount}\n"
                        
                        logger.info(f"[SessionHandler] 管理员 {user_id} 为用户 {target_user_id} 充值 {amount} 积分")
                        return result
                    else:
                        return "❌ 充值失败"
                
                elif action == 'upgrade':
                    # 升级会员 - 输入等级
                    try:
                        level = int(message)
                    except ValueError:
                        return "❌ 请输入有效的数字"
                    
                    if level not in [1, 2]:
                        return "❌ 会员等级必须是1或2"
                    
                    self._update_session(session_id, step=3, data={'level': level})
                    return "💡 请输入有效天数："
                
                elif action in ['reset', 'boost']:
                    action_type = message.strip()
                
                self._update_session(session_id, data={'action_type': action_type})
                
                if action == 'reset':
                    # 执行重置
                    target_user_id = session['data']['target_user_id']
                    
                    from datetime import date
                    today = date.today()
                    
                    self.quota_validator.db.execute_update(
                        "DELETE FROM quota_usage WHERE user_id = ? AND action_type = ? AND usage_date = ?",
                        (target_user_id, action_type, today)
                    )
                    
                    self._end_session(session_id)
                    
                    result = f"✅ 配额重置成功\n\n"
                    result += f"用户ID：{target_user_id}\n"
                    result += f"操作类型：{action_type}\n"
                    result += f"重置日期：{today}"
                    
                    logger.info(f"[SessionHandler] 管理员 {user_id} 重置用户 {target_user_id} 的 {action_type} 配额")
                    return result
                
                elif action == 'boost':
                    self._update_session(session_id, step=3)
                    return "💡 请输入加成数量："
            
            elif step == 3:
                action = session['data']['action']
                
                if action == 'upgrade':
                    # 升级会员 - 输入天数
                    try:
                        days = int(message)
                    except ValueError:
                        return "❌ 请输入有效的数字"
                    
                    if days <= 0:
                        return "❌ 有效天数必须大于0"
                    
                    target_user_id = session['data']['target_user_id']
                    level = session['data']['level']
                    
                    success = self.membership_manager.upgrade_membership(
                        user_id=target_user_id,
                        member_level=level,
                        duration_days=days
                    )
                    
                    self._end_session(session_id)
                    
                    if success:
                        level_name = "高级会员" if level == 1 else "VIP会员"
                        result = f"✅ 会员升级成功！\n\n"
                        result += f"用户ID：{target_user_id}\n"
                        result += f"会员等级：{level_name}\n"
                        result += f"有效期：{days}天\n"
                        
                        logger.info(f"[SessionHandler] 管理员 {user_id} 为用户 {target_user_id} 升级为 {level_name}")
                        return result
                    else:
                        return "❌ 升级失败"
                
                elif action == 'boost':
                    # 输入加成数量
                    try:
                        boost_count = int(message.strip())
                    except ValueError:
                        return "❌ 请输入有效的数字"
                    
                    if boost_count <= 0:
                        return "❌ 加成数量必须大于0"
                    
                    self._update_session(session_id, step=4, data={'boost_count': boost_count})
                    return "💡 请输入有效时长（小时）："
            
            elif step == 4:
                # 输入有效时长
                try:
                    hours = int(message.strip())
                except ValueError:
                    return "❌ 请输入有效的数字"
                
                if hours <= 0:
                    return "❌ 有效时长必须大于0"
                
                # 执行添加配额加成
                target_user_id = session['data']['target_user_id']
                action_type = session['data']['action_type']
                boost_count = session['data']['boost_count']
                
                success = self.points_manager.add_quota_boost(
                    user_id=target_user_id,
                    action_type=action_type,
                    boost_count=boost_count,
                    duration_hours=hours,
                    description=f"管理员添加 (by {user_id})"
                )
                
                self._end_session(session_id)
                
                if success:
                    result = f"✅ 配额加成添加成功\n\n"
                    result += f"用户ID：{target_user_id}\n"
                    result += f"操作类型：{action_type}\n"
                    result += f"加成数量：{boost_count}次\n"
                    result += f"有效时长：{hours}小时"
                    
                    logger.info(f"[SessionHandler] 管理员 {user_id} 为用户 {target_user_id} 添加 {action_type} 配额加成 {boost_count}次")
                    return result
                else:
                    return "❌ 添加配额加成失败"
            
        except Exception as e:
            logger.error(f"[SessionHandler] 处理管理步骤失败: {e}", exc_info=True)
            self._end_session(session_id)
            return f"❌ 操作失败: {e}"
    
    async def _show_quota_stats(self) -> str:
        """显示配额统计"""
        try:
            from datetime import date
            today = date.today()
            
            # 统计今日使用情况
            stats = self.quota_validator.db.execute_query(
                """
                SELECT action_type, plugin_name, COUNT(DISTINCT user_id) as user_count, SUM(count) as total_count
                FROM quota_usage
                WHERE usage_date = ?
                GROUP BY action_type, plugin_name
                ORDER BY total_count DESC
                LIMIT 10
                """,
                (today,)
            )
            
            result = f"📊 配额使用统计（今日）\n\n"
            
            if not stats:
                result += "暂无使用记录"
                return result
            
            for stat in stats:
                action_name = stat['action_type'].replace('_', ' ').title()
                plugin_name = stat['plugin_name']
                user_count = stat['user_count']
                total_count = stat['total_count']
                
                result += f"• {plugin_name} - {action_name}\n"
                result += f"  用户数：{user_count} | 总次数：{total_count}\n\n"
            
            return result
            
        except Exception as e:
            logger.error(f"[SessionHandler] 显示配额统计失败: {e}", exc_info=True)
            return f"❌ 显示统计失败: {e}"
    
    # ==================== 会话消息处理 ====================
    
    async def handle_session_message(self, user_id: str, session_id: str, message: str) -> Optional[str]:
        """处理会话中的消息"""
        try:
            session = self._get_session(session_id)
            if not session:
                return None
            
            session_type = session['type']
            
            if session_type == 'my_info':
                return await self._handle_my_info_step(user_id, session_id, message)
            elif session_type == 'redeem':
                return await self._handle_redeem_step(user_id, session_id, message)
            elif session_type == 'admin':
                return await self._handle_admin_step(user_id, session_id, message)
            else:
                return None
                
        except Exception as e:
            logger.error(f"[SessionHandler] 处理会话消息失败: {e}", exc_info=True)
            return f"❌ 处理消息失败: {e}"
