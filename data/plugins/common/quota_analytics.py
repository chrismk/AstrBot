"""
配额统计分析模块

功能：
1. 使用统计（按操作、会员等级、时间）
2. 配额超限统计
3. 转化漏斗分析
4. 用户行为分析
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from .database_manager import DatabaseManager

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class QuotaAnalytics:
    """配额统计分析器"""
    
    def __init__(self, db_manager: DatabaseManager):
        """
        初始化统计分析器
        
        Args:
            db_manager: 数据库管理器实例
        """
        self.db = db_manager
    
    async def get_usage_stats(self, days: int = 7, start_days_ago: int = 0) -> Dict:
        """
        获取使用统计
        
        Args:
            days: 统计天数
            start_days_ago: 从几天前开始统计（0=今天，1=昨天）
            
        Returns:
            统计数据字典
        """
        try:
            # start_days_ago=1, days=1 表示统计昨天一整天
            today = date.today()
            end_date = today - timedelta(days=start_days_ago - 1) if start_days_ago > 0 else today + timedelta(days=1)
            start_date = end_date - timedelta(days=days)
            
            # 1. 按操作类型统计
            action_stats = self.db.execute("""
                SELECT action_type, 
                       COUNT(DISTINCT user_id) as user_count,
                       SUM(count) as total_count,
                       SUM(points_spent) as total_points
                FROM quota_usage
                WHERE usage_date >= ? AND usage_date < ?
                GROUP BY action_type
                ORDER BY total_count DESC
            """, (start_date, end_date))
            
            # 2. 按会员等级统计
            member_stats = self.db.execute("""
                SELECT m.level,
                       COUNT(DISTINCT qu.user_id) as active_users,
                       SUM(qu.count) as total_usage,
                       SUM(qu.points_spent) as total_points
                FROM quota_usage qu
                JOIN memberships m ON qu.user_id = m.user_id
                WHERE qu.usage_date >= ? AND qu.usage_date < ?
                GROUP BY m.level
                ORDER BY m.level
            """, (start_date, end_date))
            
            # 3. 每日趋势
            daily_stats = self.db.execute("""
                SELECT usage_date,
                       COUNT(DISTINCT user_id) as active_users,
                       SUM(count) as total_usage
                FROM quota_usage
                WHERE usage_date >= ? AND usage_date < ?
                GROUP BY usage_date
                ORDER BY usage_date
            """, (start_date, end_date))
            
            # 4. 热门操作 TOP 10
            top_actions = self.db.execute("""
                SELECT action_type,
                       SUM(count) as total_count
                FROM quota_usage
                WHERE usage_date >= ? AND usage_date < ?
                GROUP BY action_type
                ORDER BY total_count DESC
                LIMIT 10
            """, (start_date, end_date))
            
            return {
                "period": f"最近{days}天",
                "action_stats": [dict(row) for row in action_stats],
                "member_stats": [dict(row) for row in member_stats],
                "daily_stats": [dict(row) for row in daily_stats],
                "top_actions": [dict(row) for row in top_actions]
            }
            
        except Exception as e:
            logger.error(f"[QuotaAnalytics] 获取使用统计失败: {e}")
            return {}
    
    async def get_quota_exceeded_stats(self, days: int = 7) -> Dict:
        """
        获取配额超限统计
        
        Args:
            days: 统计天数
            
        Returns:
            超限统计数据
        """
        try:
            start_date = date.today() - timedelta(days=days)
            
            # 1. 按操作类型统计超限次数
            exceeded_by_action = self.db.execute("""
                SELECT action_type, 
                       COUNT(*) as exceeded_count,
                       COUNT(DISTINCT user_id) as affected_users
                FROM quota_exceeded_logs
                WHERE log_date >= ?
                GROUP BY action_type
                ORDER BY exceeded_count DESC
            """, (start_date,))
            
            # 2. 按会员等级统计
            exceeded_by_level = self.db.execute("""
                SELECT m.level,
                       COUNT(*) as exceeded_count,
                       COUNT(DISTINCT qel.user_id) as affected_users
                FROM quota_exceeded_logs qel
                JOIN memberships m ON qel.user_id = m.user_id
                WHERE qel.log_date >= ?
                GROUP BY m.level
                ORDER BY m.level
            """, (start_date,))
            
            # 3. 每日超限趋势
            daily_exceeded = self.db.execute("""
                SELECT log_date,
                       COUNT(*) as exceeded_count,
                       COUNT(DISTINCT user_id) as affected_users
                FROM quota_exceeded_logs
                WHERE log_date >= ?
                GROUP BY log_date
                ORDER BY log_date
            """, (start_date,))
            
            return {
                "period": f"最近{days}天",
                "by_action": [dict(row) for row in exceeded_by_action],
                "by_level": [dict(row) for row in exceeded_by_level],
                "daily_trend": [dict(row) for row in daily_exceeded]
            }
            
        except Exception as e:
            logger.error(f"[QuotaAnalytics] 获取超限统计失败: {e}")
            return {}
    
    async def get_conversion_funnel(self, days: int = 30) -> Dict:
        """
        获取转化漏斗（配额不足 -> 充值 -> 升级会员）
        
        Args:
            days: 统计天数
            
        Returns:
            转化漏斗数据
        """
        try:
            start_date = date.today() - timedelta(days=days)
            start_datetime = datetime.combine(start_date, datetime.min.time())
            
            # 1. 配额不足次数
            exceeded_count = self.db.execute_one("""
                SELECT COUNT(*) as count,
                       COUNT(DISTINCT user_id) as unique_users
                FROM quota_exceeded_logs
                WHERE log_date >= ?
            """, (start_date,))
            
            # 2. 积分充值次数
            recharge_count = self.db.execute_one("""
                SELECT COUNT(*) as count,
                       COUNT(DISTINCT user_id) as unique_users,
                       SUM(amount) as total_amount
                FROM points_transactions
                WHERE type = 'recharge' 
                  AND created_at >= ?
            """, (start_datetime,))
            
            # 3. 会员升级次数
            upgrade_count = self.db.execute_one("""
                SELECT COUNT(*) as count,
                       COUNT(DISTINCT user_id) as unique_users
                FROM memberships
                WHERE level > 0 
                  AND created_at >= ?
            """, (start_datetime,))
            
            # 4. 配额包兑换次数
            boost_exchange_count = self.db.execute_one("""
                SELECT COUNT(*) as count,
                       COUNT(DISTINCT user_id) as unique_users
                FROM points_transactions
                WHERE source = 'boost_exchange'
                  AND created_at >= ?
            """, (start_datetime,))
            
            # 计算转化率
            exceeded_users = exceeded_count['unique_users'] if exceeded_count else 0
            recharged_users = recharge_count['unique_users'] if recharge_count else 0
            upgraded_users = upgrade_count['unique_users'] if upgrade_count else 0
            
            recharge_rate = (recharged_users / exceeded_users * 100) if exceeded_users > 0 else 0
            upgrade_rate = (upgraded_users / exceeded_users * 100) if exceeded_users > 0 else 0
            
            return {
                "period": f"最近{days}天",
                "funnel": {
                    "quota_exceeded": {
                        "count": exceeded_count['count'] if exceeded_count else 0,
                        "unique_users": exceeded_users
                    },
                    "recharged": {
                        "count": recharge_count['count'] if recharge_count else 0,
                        "unique_users": recharged_users,
                        "total_amount": recharge_count['total_amount'] if recharge_count else 0,
                        "conversion_rate": f"{recharge_rate:.2f}%"
                    },
                    "upgraded": {
                        "count": upgrade_count['count'] if upgrade_count else 0,
                        "unique_users": upgraded_users,
                        "conversion_rate": f"{upgrade_rate:.2f}%"
                    },
                    "boost_exchanged": {
                        "count": boost_exchange_count['count'] if boost_exchange_count else 0,
                        "unique_users": boost_exchange_count['unique_users'] if boost_exchange_count else 0
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"[QuotaAnalytics] 获取转化漏斗失败: {e}")
            return {}
    
    async def get_user_behavior(self, user_id: str, days: int = 30) -> Dict:
        """
        获取用户行为分析
        
        Args:
            user_id: 用户ID
            days: 统计天数
            
        Returns:
            用户行为数据
        """
        try:
            start_date = date.today() - timedelta(days=days)
            
            # 1. 使用频率
            usage_frequency = self.db.execute("""
                SELECT usage_date,
                       SUM(count) as daily_usage
                FROM quota_usage
                WHERE user_id = ? AND usage_date >= ?
                GROUP BY usage_date
                ORDER BY usage_date
            """, (user_id, start_date))
            
            # 2. 操作偏好
            action_preference = self.db.execute("""
                SELECT action_type,
                       SUM(count) as total_count,
                       SUM(points_spent) as total_points
                FROM quota_usage
                WHERE user_id = ? AND usage_date >= ?
                GROUP BY action_type
                ORDER BY total_count DESC
            """, (user_id, start_date))
            
            # 3. 配额超限记录
            exceeded_history = self.db.execute("""
                SELECT log_date, action_type, member_level
                FROM quota_exceeded_logs
                WHERE user_id = ? AND log_date >= ?
                ORDER BY log_date DESC
            """, (user_id, start_date))
            
            # 4. 积分流水
            points_history = self.db.execute("""
                SELECT created_at, type, amount, balance_after, description
                FROM points_transactions
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 20
            """, (user_id,))
            
            return {
                "user_id": user_id,
                "period": f"最近{days}天",
                "usage_frequency": [dict(row) for row in usage_frequency],
                "action_preference": [dict(row) for row in action_preference],
                "exceeded_history": [dict(row) for row in exceeded_history],
                "points_history": [dict(row) for row in points_history]
            }
            
        except Exception as e:
            logger.error(f"[QuotaAnalytics] 获取用户行为失败: {e}")
            return {}
    
    async def get_revenue_stats(self, days: int = 30) -> Dict:
        """
        获取收入统计
        
        Args:
            days: 统计天数
            
        Returns:
            收入统计数据
        """
        try:
            start_datetime = datetime.now() - timedelta(days=days)
            
            # 1. 积分充值收入
            recharge_revenue = self.db.execute_one("""
                SELECT COUNT(*) as transaction_count,
                       SUM(amount) as total_points,
                       AVG(amount) as avg_points
                FROM points_transactions
                WHERE type = 'recharge' 
                  AND source = 'payment'
                  AND created_at >= ?
            """, (start_datetime,))
            
            # 2. 会员订阅数
            membership_stats = self.db.execute("""
                SELECT level,
                       COUNT(*) as member_count
                FROM memberships
                WHERE level > 0
                  AND expire_date >= date('now')
                GROUP BY level
            """)
            
            # 3. 每日收入趋势
            daily_revenue = self.db.execute("""
                SELECT date(created_at) as revenue_date,
                       SUM(amount) as daily_points
                FROM points_transactions
                WHERE type = 'recharge'
                  AND source = 'payment'
                  AND created_at >= ?
                GROUP BY date(created_at)
                ORDER BY revenue_date
            """, (start_datetime,))
            
            return {
                "period": f"最近{days}天",
                "recharge_revenue": dict(recharge_revenue) if recharge_revenue else {},
                "membership_stats": [dict(row) for row in membership_stats],
                "daily_revenue": [dict(row) for row in daily_revenue]
            }
            
        except Exception as e:
            logger.error(f"[QuotaAnalytics] 获取收入统计失败: {e}")
            return {}
    
    async def log_quota_exceeded(
        self,
        user_id: str,
        action_type: str,
        member_level: int,
        plugin_name: str
    ) -> bool:
        """
        记录配额超限日志
        
        Args:
            user_id: 用户ID
            action_type: 操作类型
            member_level: 会员等级
            plugin_name: 插件名称
            
        Returns:
            是否成功
        """
        try:
            self.db.execute_write("""
                INSERT INTO quota_exceeded_logs
                (user_id, action_type, member_level, plugin_name, log_date, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, action_type, member_level, plugin_name, date.today(), datetime.now()))
            
            return True
            
        except Exception as e:
            logger.error(f"[QuotaAnalytics] 记录配额超限日志失败: {e}")
            return False
