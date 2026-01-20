"""
配额验证器

核心功能：
1. 检查用户配额是否充足
2. 支持会员等级差异化配额
3. 支持积分抵扣
4. 支持临时配额加成（流量包）
5. 消费配额并记录
"""

from enum import IntEnum
from typing import Optional, Tuple
from datetime import date, datetime
from .database_manager import DatabaseManager
from .rate_limiter import get_rate_limiter

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class MemberLevel(IntEnum):
    """会员等级"""
    FREE = 0      # 免费用户
    PREMIUM = 1   # 高级会员 ¥19.9/月
    VIP = 2       # VIP会员 ¥399/年


class QuotaResult:
    """配额检查结果"""
    def __init__(self, allowed: bool, message: str = "", 
                 remaining: int = 0, points_cost: int = 0):
        self.allowed = allowed          # 是否允许操作
        self.message = message          # 提示消息
        self.remaining = remaining      # 剩余次数
        self.points_cost = points_cost  # 需要消耗的积分


class QuotaValidator:
    """
    配额验证器 - 统一管理所有插件的配额
    
    使用示例:
        validator = QuotaValidator(db_path)
        
        # 检查配额
        result = await validator.check_quota(
            user_id="user123",
            action_type="music_download_flac",
            plugin_name="music",
            use_points=True
        )
        
        if result.allowed:
            # 执行操作...
            # 消费配额
            await validator.consume_quota(
                user_id="user123",
                action_type="music_download_flac",
                plugin_name="music",
                points_cost=result.points_cost
            )
        else:
            # 显示提示消息
            print(result.message)
    """
    
    def __init__(self, db_manager: DatabaseManager):
        """
        初始化配额验证器
        
        Args:
            db_manager: 数据库管理器实例
        """
        self.db = db_manager
        self.rate_limiter = get_rate_limiter()
    
    async def check_quota(
        self, 
        user_id: str, 
        action_type: str,
        plugin_name: str,
        use_points: bool = False,
        enable_rate_limit: bool = True,
        username: str = None,
        platform: str = None,
        platform_user_id: str = None
    ) -> QuotaResult:
        """
        检查用户配额（带速率限制和预警）
        
        Args:
            user_id: 用户ID
            action_type: 操作类型 (如 music_download_flac)
            plugin_name: 插件名称 (如 music)
            use_points: 是否允许使用积分抵扣
            enable_rate_limit: 是否启用速率限制
            username: 用户昵称（用于保存/更新用户信息）
            platform: 平台名称（用于保存/更新用户信息）
            platform_user_id: 平台用户ID（用于保存/更新用户信息）
            
        Returns:
            QuotaResult 配额检查结果
        """
        try:
            # 0. 速率限制检查（防止恶意刷请求）
            if enable_rate_limit:
                member_level = self._get_member_level(user_id)
                is_allowed, rate_msg = self.rate_limiter.is_allowed(
                    user_id, 
                    action_type, 
                    member_level.value
                )
                if not is_allowed:
                    return QuotaResult(
                        allowed=False,
                        message=rate_msg,
                        remaining=0
                    )
            # 1. 确保用户存在（并更新用户信息）
            self._ensure_user_exists(user_id, username, platform, platform_user_id)
            
            # 2. 获取用户会员等级
            member_level = self._get_member_level(user_id)
            
            # 3. 获取配额规则
            rule = self._get_quota_rule(action_type, member_level)
            if not rule:
                # 没有配置规则，默认允许
                logger.warning(f"[QuotaValidator] 未找到配额规则: {action_type} (level={member_level})")
                return QuotaResult(allowed=True, message="操作允许（无规则限制）")
            
            daily_limit, points_cost = rule
            
            # 4. 检查是否无限制
            if daily_limit == -1:
                return QuotaResult(
                    allowed=True, 
                    message="会员用户无限制",
                    remaining=-1
                )
            
            # 5. 查询今日已使用次数
            today = date.today()
            used_count = self._get_today_usage(user_id, action_type, today)
            
            # 6. 查询临时加成（流量包）
            boost_amount = self._get_active_boosts(user_id, action_type, today)
            
            # 7. 计算可用配额
            total_limit = daily_limit + boost_amount
            remaining = total_limit - used_count
            
            # 8. 判断是否超限
            if remaining <= 0:
                # 超限，检查是否可以用积分抵扣
                if use_points and points_cost > 0:
                    points_balance = self._get_points_balance(user_id)
                    if points_balance >= points_cost:
                        # 积分足够，允许操作
                        logger.info(f"[QuotaValidator] 用户 {user_id} 使用 {points_cost} 积分抵扣 {action_type}")
                        return QuotaResult(
                            allowed=True,
                            message=f"使用{points_cost}积分抵扣",
                            remaining=0,
                            points_cost=points_cost
                        )
                    else:
                        return QuotaResult(
                            allowed=False,
                            message=f"⚠️ 今日配额已用完，积分不足\n需要{points_cost}积分，当前{points_balance}积分",
                            remaining=0
                        )
                else:
                    # 生成升级提示
                    upgrade_msg = self._generate_upgrade_message(
                        action_type, member_level, daily_limit
                    )
                    return QuotaResult(
                        allowed=False,
                        message=upgrade_msg,
                        remaining=0
                    )
            
            # 9. 配额充足，允许操作（添加预警）
            logger.debug(f"[QuotaValidator] 用户 {user_id} 配额检查通过: {action_type} (剩余{remaining}次)")
            
            # 生成预警消息
            warning_msg = self._generate_warning_message(remaining, total_limit)
            message = f"操作允许，今日剩余{remaining}次"
            if warning_msg:
                message += "\n" + warning_msg
            
            return QuotaResult(
                allowed=True,
                message=message,
                remaining=remaining
            )
            
        except Exception as e:
            logger.error(f"[QuotaValidator] 配额检查失败: {e}")
            # 出错时默认允许，避免影响用户体验
            return QuotaResult(allowed=True, message="配额检查异常，默认允许")
    
    async def consume_quota(
        self, 
        user_id: str, 
        action_type: str,
        plugin_name: str,
        points_cost: int = 0
    ) -> tuple[bool, str]:
        """
        消费配额（原子操作）
        
        Args:
            user_id: 用户ID
            action_type: 操作类型
            plugin_name: 插件名称
            points_cost: 积分消耗（如果>0则扣除积分）
            
        Returns:
            (是否成功, 提示消息)
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                today = date.today()
                
                # 1. 记录配额使用
                cursor.execute("""
                    INSERT INTO quota_usage 
                    (user_id, action_type, plugin_name, usage_date, count, points_spent, created_at)
                    VALUES (?, ?, ?, ?, 1, ?, ?)
                """, (user_id, action_type, plugin_name, today, points_cost, datetime.now()))
                
                # 2. 如果消耗积分，原子扣除积分
                if points_cost > 0:
                    success = self._deduct_points(cursor, user_id, points_cost, f"{action_type} 积分抵扣")
                    if not success:
                        conn.rollback()
                        return False, "❌ 积分扣除失败，余额不足"
                
                # 3. 更新用户最后活跃时间
                cursor.execute("""
                    UPDATE users SET last_active_at = ? WHERE user_id = ?
                """, (datetime.now(), user_id))
                
                conn.commit()
                logger.info(f"[QuotaValidator] 用户 {user_id} 消费配额: {action_type} (积分:{points_cost})")
                return True, "✅ 配额消费成功"
                
        except Exception as e:
            logger.error(f"[QuotaValidator] 消费配额失败: {e}", exc_info=True)
            return False, "❌ 消费失败，请稍后重试"
    
    def _ensure_user_exists(
        self, 
        user_id: str, 
        username: str = None, 
        platform: str = None,
        platform_user_id: str = None
    ):
        """
        确保用户记录存在，并更新用户信息
        
        Args:
            user_id: 用户ID
            username: 用户昵称
            platform: 平台名称
            platform_user_id: 平台用户ID
        """
        now = datetime.now()
        
        row = self.db.execute_one("""
            SELECT user_id, username, platform FROM users WHERE user_id = ?
        """, (user_id,))
        
        if not row:
            # 创建用户记录
            self.db.execute_write("""
                INSERT INTO users 
                (user_id, username, platform, platform_user_id, created_at, last_active_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                user_id, 
                username or '', 
                platform or 'unknown', 
                platform_user_id or user_id, 
                now,
                now
            ))
            
            # 检查并创建积分账户（如果不存在）
            points_row = self.db.execute_one("""
                SELECT user_id FROM points_accounts WHERE user_id = ?
            """, (user_id,))
            
            if not points_row:
                self.db.execute_write("""
                    INSERT INTO points_accounts 
                    (user_id, balance, total_earned, total_spent, created_at, updated_at)
                    VALUES (?, 0, 0, 0, ?, ?)
                """, (user_id, now, now))
            
            # 检查并创建免费会员记录（如果不存在）
            member_row = self.db.execute_one("""
                SELECT user_id FROM memberships WHERE user_id = ?
            """, (user_id,))
            
            if not member_row:
                self.db.execute_write("""
                    INSERT INTO memberships 
                    (user_id, level, created_at, updated_at)
                    VALUES (?, 0, ?, ?)
                """, (user_id, now, now))
            
            logger.info(f"[QuotaValidator] 创建新用户: {user_id} ({username or '无昵称'}, {platform or 'unknown'})")
        else:
            # 用户已存在，更新信息（如果有新信息）
            updates = []
            params = []
            
            # 更新昵称（如果提供了新昵称且当前为空或不同）
            if username and (not row['username'] or row['username'] != username):
                updates.append("username = ?")
                params.append(username)
            
            # 更新平台（如果当前是 unknown 且提供了新平台）
            if platform and row['platform'] == 'unknown' and platform != 'unknown':
                logger.info(f"[QuotaValidator] 更新用户平台: {user_id} -> {platform}")
                updates.append("platform = ?")
                params.append(platform)
                if platform_user_id:
                    updates.append("platform_user_id = ?")
                    params.append(platform_user_id)
            
            # 更新最后活跃时间
            updates.append("last_active_at = ?")
            params.append(now)
            
            if updates:
                params.append(user_id)
                self.db.execute_write(f"""
                    UPDATE users SET {', '.join(updates)} WHERE user_id = ?
                """, tuple(params))
            
            # 确保积分账户存在（即使用户已存在）
            points_row = self.db.execute_one("""
                SELECT user_id FROM points_accounts WHERE user_id = ?
            """, (user_id,))
            
            if not points_row:
                self.db.execute_write("""
                    INSERT INTO points_accounts 
                    (user_id, balance, total_earned, total_spent, created_at, updated_at)
                    VALUES (?, 0, 0, 0, ?, ?)
                """, (user_id, now, now))
                logger.info(f"[QuotaValidator] 为已存在用户创建积分账户: {user_id}")
            
            # 确保会员记录存在（即使用户已存在）
            member_row = self.db.execute_one("""
                SELECT user_id FROM memberships WHERE user_id = ?
            """, (user_id,))
            
            if not member_row:
                self.db.execute_write("""
                    INSERT INTO memberships 
                    (user_id, level, created_at, updated_at)
                    VALUES (?, 0, ?, ?)
                """, (user_id, now, now))
                logger.info(f"[QuotaValidator] 为已存在用户创建会员记录: {user_id}")
    
    def get_user_level(self, user_id: str) -> MemberLevel:
        """获取用户会员等级（公开方法）"""
        return self._get_member_level(user_id)
    
    def _get_member_level(self, user_id: str) -> MemberLevel:
        """获取用户会员等级"""
        row = self.db.execute_one("""
            SELECT level, expire_date 
            FROM memberships 
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
        """, (user_id,))
        
        if not row:
            return MemberLevel.FREE
        
        level = row['level']
        expire_date = row['expire_date']
        
        # 检查是否过期
        if expire_date:
            try:
                expire = datetime.strptime(expire_date, "%Y-%m-%d").date()
                if expire < date.today():
                    logger.info(f"[QuotaValidator] 用户 {user_id} 会员已过期")
                    return MemberLevel.FREE
            except:
                pass
        
        return MemberLevel(level)
    
    def _get_quota_rule(self, action_type: str, member_level: MemberLevel) -> Optional[Tuple[int, int]]:
        """获取配额规则"""
        row = self.db.execute_one("""
            SELECT daily_limit, points_cost
            FROM quota_rules
            WHERE action_type = ? AND member_level = ? AND is_active = 1
        """, (action_type, member_level.value))
        
        if row:
            return (row['daily_limit'], row['points_cost'])
        return None
    
    def _get_today_usage(self, user_id: str, action_type: str, today: date) -> int:
        """获取今日已使用次数"""
        row = self.db.execute_one("""
            SELECT COALESCE(SUM(count), 0) as total
            FROM quota_usage
            WHERE user_id = ? AND action_type = ? AND usage_date = ?
        """, (user_id, action_type, today))
        
        return row['total'] if row else 0
    
    def _get_active_boosts(self, user_id: str, action_type: str, today: date) -> int:
        """获取有效的临时加成"""
        row = self.db.execute_one("""
            SELECT COALESCE(SUM(boost_amount), 0) as total
            FROM quota_boosts
            WHERE user_id = ? 
              AND (action_type = ? OR action_type IS NULL)
              AND expire_date >= ?
              AND is_used = 0
        """, (user_id, action_type, today))
        
        return row['total'] if row else 0
    
    def _get_points_balance(self, user_id: str) -> int:
        """获取积分余额"""
        row = self.db.execute_one("""
            SELECT balance FROM points_accounts WHERE user_id = ?
        """, (user_id,))
        
        return row['balance'] if row else 0
    
    def _deduct_points(self, cursor, user_id: str, amount: int, description: str) -> bool:
        """原子扣除积分（确保余额充足）"""
        # 1. 原子更新余额（使用 WHERE 条件确保余额充足）
        cursor.execute("""
            UPDATE points_accounts 
            SET balance = balance - ?,
                total_spent = total_spent + ?,
                updated_at = ?
            WHERE user_id = ? AND balance >= ?
        """, (amount, amount, datetime.now(), user_id, amount))
        
        # 检查是否更新成功
        if cursor.rowcount == 0:
            logger.warning(f"[QuotaValidator] 用户 {user_id} 积分不足，无法扣除 {amount} 积分")
            return False
        
        # 2. 获取更新后余额
        cursor.execute("""
            SELECT balance FROM points_accounts WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        balance_after = row[0] if row else 0
        
        # 3. 记录流水
        cursor.execute("""
            INSERT INTO points_transactions
            (user_id, amount, balance_after, type, source, description, created_at)
            VALUES (?, ?, ?, 'consume', 'quota', ?, ?)
        """, (user_id, -amount, balance_after, description, datetime.now()))
        
        return True
    
    def _generate_warning_message(self, remaining: int, total_limit: int) -> str:
        """生成配额预警消息"""
        if total_limit <= 0:
            return ""
        
        usage_percent = (total_limit - remaining) / total_limit * 100
        
        if usage_percent >= 90:
            return f"⚠️ 配额即将用完（仅剩{remaining}次）"
        elif usage_percent >= 80:
            return f"💡 配额剩余不多（剩余{remaining}次）"
        elif usage_percent >= 50:
            return f"📊 已使用{int(usage_percent)}%配额"
        
        return ""
    
    def _generate_upgrade_message(self, action_type: str, member_level: MemberLevel, daily_limit: int) -> str:
        """生成升级提示消息"""
        
        action_name_map = {
            "music_download_flac": "无损音乐下载",
            "music_download_320": "320k音乐下载",
            "music_download_128": "128k音乐下载",
            "yunpan_download": "云盘资源下载",
            "douban_view": "豆瓣评分查看",
            "music_search": "音乐搜索",
            "yunpan_search": "云盘搜索",
        }
        
        action_name = action_name_map.get(action_type, "该操作")
        
        if member_level == MemberLevel.FREE:
            return f"""⚠️ 今日{action_name}次数已用完
免费用户每日限{daily_limit}次

💎 升级会员享受：
• 高级会员(¥19.9/月): 大幅提升配额
• VIP会员(¥399/年): 无限次数
• 无广告体验
• 优先获取资源
• 专属客服支持

💰 或使用积分抵扣：
• 查看积分余额: /积分
• 充值积分: /充值

👉 立即升级: /upgrade"""
        else:
            return f"""⚠️ 今日{action_name}次数已用完
高级会员每日限{daily_limit}次

💎 升级VIP会员(¥399/年)享受：
• 所有操作无限次数
• 无广告体验
• 优先获取资源
• 专属客服支持

💰 或使用积分抵扣：
• 查看积分余额: /积分
• 充值积分: /充值

👉 立即升级: /upgrade"""
    
    # ==================== 插件配额注册 API ====================
    
    def register_quota_rules(
        self, 
        plugin_name: str, 
        rules: list,
        override: bool = False
    ) -> bool:
        """
        注册插件的配额规则
        
        Args:
            plugin_name: 插件名称
            rules: 配额规则列表
            override: 是否覆盖已存在的规则
            
        Returns:
            是否注册成功
            
        Example:
            rules = [
                {
                    'action_type': 'music_download_flac',
                    'free': {'daily_limit': 1, 'points_cost': 10},
                    'premium': {'daily_limit': 10, 'points_cost': 5},
                    'vip': {'daily_limit': -1, 'points_cost': 0},
                    'description': '下载无损音质'
                },
                {
                    'action_type': 'music_search',
                    'free': {'daily_limit': 10, 'points_cost': 0},
                    'premium': {'daily_limit': -1, 'points_cost': 0},
                    'vip': {'daily_limit': -1, 'points_cost': 0},
                    'description': '音乐搜索'
                }
            ]
            
            validator.register_quota_rules('music', rules)
        """
        try:
            now = datetime.now()
            registered_count = 0
            
            for rule in rules:
                action_type = rule.get('action_type')
                if not action_type:
                    logger.warning(f"[Quota] 规则缺少 action_type，跳过: {rule}")
                    continue
                
                description = rule.get('description', '')
                
                # 为每个会员等级注册规则
                for level_name, level_value in [('free', 0), ('premium', 1), ('vip', 2)]:
                    if level_name not in rule:
                        logger.debug(f"[Quota] 规则缺少 {level_name} 配置，跳过: {action_type}")
                        continue
                    
                    level_config = rule[level_name]
                    daily_limit = level_config.get('daily_limit', 0)
                    points_cost = level_config.get('points_cost', 0)
                    
                    # 检查是否已存在
                    existing = self.db.execute_one("""
                        SELECT id FROM quota_rules
                        WHERE action_type = ? AND plugin_name = ? AND member_level = ?
                    """, (action_type, plugin_name, level_value))
                    
                    if existing and not override:
                        logger.debug(f"[Quota] 规则已存在，跳过: {plugin_name}.{action_type}.{level_name}")
                        continue
                    
                    # 插入或更新规则
                    if existing and override:
                        self.db.execute_write("""
                            UPDATE quota_rules
                            SET daily_limit = ?, points_cost = ?, description = ?, updated_at = ?
                            WHERE id = ?
                        """, (daily_limit, points_cost, description, now, existing['id']))
                        logger.debug(f"[Quota] 更新规则: {plugin_name}.{action_type}.{level_name}")
                    else:
                        self.db.execute_write("""
                            INSERT INTO quota_rules
                            (action_type, plugin_name, member_level, daily_limit, points_cost, description, is_active, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                        """, (action_type, plugin_name, level_value, daily_limit, points_cost, description, now, now))
                        logger.debug(f"[Quota] 注册规则: {plugin_name}.{action_type}.{level_name}")
                    
                    registered_count += 1
            
            logger.info(f"[Quota] 插件 '{plugin_name}' 成功注册 {registered_count} 条配额规则")
            return True
            
        except Exception as e:
            logger.error(f"[Quota] 注册配额规则失败: {e}", exc_info=True)
            return False
    
    def unregister_quota_rules(self, plugin_name: str) -> bool:
        """
        卸载插件的配额规则（禁用而非删除）
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            是否卸载成功
        """
        try:
            self.db.execute("""
                UPDATE quota_rules
                SET is_active = 0, updated_at = ?
                WHERE plugin_name = ?
            """, (datetime.now(), plugin_name))
            
            self.db.commit()
            logger.info(f"[Quota] 插件 '{plugin_name}' 的配额规则已禁用")
            return True
            
        except Exception as e:
            logger.error(f"[Quota] 卸载配额规则失败: {e}", exc_info=True)
            return False
    
    def get_plugin_rules(self, plugin_name: str) -> list:
        """
        获取插件的所有配额规则
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            规则列表
        """
        try:
            rows = self.db.execute("""
                SELECT action_type, member_level, daily_limit, points_cost, description, is_active
                FROM quota_rules
                WHERE plugin_name = ?
                ORDER BY action_type, member_level
            """, (plugin_name,))
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"[Quota] 获取插件规则失败: {e}", exc_info=True)
            return []
    
    async def refund_quota(
        self,
        user_id: str,
        action_type: str,
        plugin_name: str
    ) -> bool:
        """
        退还配额（操作失败时）
        
        Args:
            user_id: 用户ID
            action_type: 操作类型
            plugin_name: 插件名称
            
        Returns:
            是否退还成功
        """
        try:
            today = date.today()
            
            # 减少使用计数
            self.db.execute("""
                UPDATE quota_usage
                SET count = count - 1
                WHERE user_id = ? AND action_type = ? AND usage_date = ?
                AND count > 0
            """, (user_id, action_type, today))
            
            affected = self.db.cursor.rowcount
            self.db.commit()
            
            if affected > 0:
                logger.info(f"[Quota] 退还配额: {user_id} - {plugin_name}.{action_type}")
                return True
            else:
                logger.warning(f"[Quota] 退还配额失败，未找到使用记录: {user_id} - {plugin_name}.{action_type}")
                return False
            
        except Exception as e:
            logger.error(f"[Quota] 退还配额失败: {e}", exc_info=True)
            return False


# ==================== 全局实例 ====================

_quota_validator: Optional[QuotaValidator] = None


def get_quota_validator(db_manager=None) -> Optional[QuotaValidator]:
    """
    获取配额验证器实例（单例模式）
    
    Args:
        db_manager: 数据库管理器（首次调用时必须提供）
    
    Returns:
        QuotaValidator 实例
    """
    global _quota_validator
    
    if _quota_validator is None and db_manager is not None:
        _quota_validator = QuotaValidator(db_manager)
        logger.info("[QuotaValidator] 创建全局配额验证器实例")
    
    return _quota_validator
