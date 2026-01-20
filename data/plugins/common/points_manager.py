"""
积分管理器

负责：
1. 积分充值/消费
2. 积分流水记录
3. 临时配额包（流量包）管理
4. 积分兑换功能
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict
from .database_manager import DatabaseManager

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class PointsManager:
    """积分管理器"""
    
    # 积分兑换配额包配置
    BOOST_PACKAGES = {
        "music_flac_5": {
            "action_type": "music_download_flac",
            "boost_amount": 5,
            "points_cost": 50,
            "days": 1,
            "description": "5次无损音乐下载（24小时有效）"
        },
        "music_320_10": {
            "action_type": "music_download_320",
            "boost_amount": 10,
            "points_cost": 30,
            "days": 1,
            "description": "10次320k音乐下载（24小时有效）"
        },
        "yunpan_10": {
            "action_type": "yunpan_download",
            "boost_amount": 10,
            "points_cost": 40,
            "days": 1,
            "description": "10次云盘资源下载（24小时有效）"
        },
        "all_day_pass": {
            "action_type": None,  # None 表示全局加成
            "boost_amount": 50,
            "points_cost": 100,
            "days": 1,
            "description": "全功能日卡（所有操作+50次，24小时有效）"
        },
        # 订阅相关配额包
        "subscription_5": {
            "action_type": "subscription_subscribe",
            "boost_amount": 5,
            "points_cost": 30,
            "days": 30,
            "description": "订阅额度+5（30天有效）"
        },
        "subscription_10": {
            "action_type": "subscription_subscribe",
            "boost_amount": 10,
            "points_cost": 50,
            "days": 30,
            "description": "订阅额度+10（30天有效）"
        },
        "subscription_unlimited_7d": {
            "action_type": "subscription_subscribe",
            "boost_amount": 100,
            "points_cost": 80,
            "days": 7,
            "description": "无限订阅（7天有效）"
        },
        "vip_source_access_7d": {
            "action_type": "subscription_source_access",
            "boost_amount": 0,
            "points_cost": 50,
            "days": 7,
            "description": "VIP订阅源访问权（7天）",
            "extra": {"access_level": 3}
        }
    }
    
    def __init__(self, db_manager: DatabaseManager):
        """
        初始化积分管理器
        
        Args:
            db_manager: 数据库管理器实例
        """
        self.db = db_manager
    
    async def recharge(
        self, 
        user_id: str, 
        amount: int, 
        source: str = "payment",
        order_id: str = None,
        description: str = "积分充值",
        idempotency_key: str = None
    ) -> tuple[bool, str]:
        """
        充值积分（幂等、原子操作）
        
        Args:
            user_id: 用户ID
            amount: 充值金额
            source: 来源 (payment/admin/gift/system)
            order_id: 订单ID
            description: 描述
            idempotency_key: 幂等性键（防止重复充值）
            
        Returns:
            (是否成功, 提示消息)
        """
        # 1. 参数验证
        if amount <= 0:
            return False, "❌ 充值金额必须大于0"
        
        if amount > 1000000:
            return False, "❌ 单次充值不能超过100万积分"
        
        if source not in ["payment", "admin", "gift", "system"]:
            return False, f"❌ 无效的充值来源: {source}"
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # 2. 幂等性检查（防止重复充值）
                if idempotency_key:
                    cursor.execute("""
                        SELECT id FROM points_transactions
                        WHERE related_order_id = ? AND type = 'recharge'
                    """, (idempotency_key,))
                    
                    if cursor.fetchone():
                        logger.warning(f"[PointsManager] 重复充值请求: {idempotency_key}")
                        return False, "❌ 该订单已处理，请勿重复充值"
                
                # 3. 确保用户有积分账户
                cursor.execute("""
                    INSERT OR IGNORE INTO points_accounts 
                    (user_id, balance, total_earned, total_spent, created_at, updated_at)
                    VALUES (?, 0, 0, 0, ?, ?)
                """, (user_id, datetime.now(), datetime.now()))
                
                # 4. 原子更新余额（使用事务保证一致性）
                cursor.execute("""
                    UPDATE points_accounts 
                    SET balance = balance + ?,
                        total_earned = total_earned + ?,
                        updated_at = ?
                    WHERE user_id = ?
                """, (amount, amount, datetime.now(), user_id))
                
                if cursor.rowcount == 0:
                    conn.rollback()
                    return False, "❌ 用户账户不存在"
                
                # 5. 获取更新后余额
                cursor.execute("""
                    SELECT balance FROM points_accounts WHERE user_id = ?
                """, (user_id,))
                row = cursor.fetchone()
                balance_after = row[0] if row else 0
                
                # 6. 记录流水（使用幂等性键）
                cursor.execute("""
                    INSERT INTO points_transactions
                    (user_id, amount, balance_after, type, source, description, related_order_id, created_at)
                    VALUES (?, ?, ?, 'recharge', ?, ?, ?, ?)
                """, (user_id, amount, balance_after, source, description, idempotency_key or order_id, datetime.now()))
                
                conn.commit()
                logger.info(f"[PointsManager] 用户 {user_id} 充值 {amount} 积分 (来源: {source}, 余额: {balance_after})")
                return True, f"✅ 充值成功！+{amount}积分，当前余额: {balance_after}"
                
        except Exception as e:
            logger.error(f"[PointsManager] 充值积分失败: {e}", exc_info=True)
            return False, "❌ 充值失败，请稍后重试"
    
    async def get_balance(self, user_id: str) -> int:
        """
        获取积分余额
        
        Args:
            user_id: 用户ID
            
        Returns:
            积分余额
        """
        try:
            row = self.db.execute_one("""
                SELECT balance FROM points_accounts WHERE user_id = ?
            """, (user_id,))
            
            return row['balance'] if row else 0
            
        except Exception as e:
            logger.error(f"[PointsManager] 获取积分余额失败: {e}")
            return 0
    
    async def get_account_info(self, user_id: str) -> Optional[Dict]:
        """
        获取积分账户信息
        
        Args:
            user_id: 用户ID
            
        Returns:
            账户信息字典
        """
        try:
            row = self.db.execute_one("""
                SELECT balance, total_earned, total_spent, created_at
                FROM points_accounts
                WHERE user_id = ?
            """, (user_id,))
            
            if not row:
                return {
                    "balance": 0,
                    "total_earned": 0,
                    "total_spent": 0,
                    "created_at": None
                }
            
            return {
                "balance": row['balance'],
                "total_earned": row['total_earned'],
                "total_spent": row['total_spent'],
                "created_at": row['created_at']
            }
            
        except Exception as e:
            logger.error(f"[PointsManager] 获取账户信息失败: {e}")
            return None
    
    async def add_boost(
        self,
        user_id: str,
        action_type: Optional[str],
        boost_amount: int,
        days: int = 1,
        source: str = "points",
        description: str = "积分兑换配额加成"
    ) -> bool:
        """
        添加临时配额加成（流量包）
        
        Args:
            user_id: 用户ID
            action_type: 操作类型 (None表示全局加成)
            boost_amount: 加成数量
            days: 有效天数
            source: 来源 (points/gift/event)
            description: 描述
            
        Returns:
            是否成功
        """
        try:
            expire_date = (datetime.now() + timedelta(days=days)).date()
            
            self.db.execute_write("""
                INSERT INTO quota_boosts
                (user_id, action_type, boost_amount, expire_date, source, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, action_type, boost_amount, expire_date, source, description, datetime.now()))
            
            logger.info(f"[PointsManager] 用户 {user_id} 获得配额加成: {action_type} +{boost_amount} (有效期至 {expire_date})")
            return True
            
        except Exception as e:
            logger.error(f"[PointsManager] 添加配额加成失败: {e}")
            return False
    
    async def exchange_boost_package(self, user_id: str, package_id: str) -> tuple[bool, str]:
        """
        兑换配额包
        
        Args:
            user_id: 用户ID
            package_id: 配额包ID
            
        Returns:
            (是否成功, 提示消息)
        """
        try:
            # 1. 检查配额包是否存在
            if package_id not in self.BOOST_PACKAGES:
                return False, f"❌ 配额包不存在: {package_id}"
            
            package = self.BOOST_PACKAGES[package_id]
            points_cost = package["points_cost"]
            
            # 2. 检查积分余额
            balance = await self.get_balance(user_id)
            if balance < points_cost:
                return False, f"❌ 积分不足\n需要{points_cost}积分，当前{balance}积分"
            
            # 3. 原子扣除积分（确保余额充足）
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # 使用 WHERE 条件确保余额充足（原子操作）
                cursor.execute("""
                    UPDATE points_accounts 
                    SET balance = balance - ?,
                        total_spent = total_spent + ?,
                        updated_at = ?
                    WHERE user_id = ? AND balance >= ?
                """, (points_cost, points_cost, datetime.now(), user_id, points_cost))
                
                # 检查是否更新成功
                if cursor.rowcount == 0:
                    conn.rollback()
                    return False, f"❌ 积分不足或账户异常\n需要{points_cost}积分"
                
                # 获取更新后余额
                cursor.execute("""
                    SELECT balance FROM points_accounts WHERE user_id = ?
                """, (user_id,))
                row = cursor.fetchone()
                balance_after = row[0] if row else 0
                
                # 记录流水
                cursor.execute("""
                    INSERT INTO points_transactions
                    (user_id, amount, balance_after, type, source, description, created_at)
                    VALUES (?, ?, ?, 'consume', 'boost_exchange', ?, ?)
                """, (user_id, -points_cost, balance_after, f"兑换配额包: {package['description']}", datetime.now()))
                
                # 提交事务
                conn.commit()
                
                logger.info(f"[PointsManager] 用户 {user_id} 扣除 {points_cost} 积分，余额: {balance_after}")
            
            # 4. 添加配额加成
            success = await self.add_boost(
                user_id,
                package["action_type"],
                package["boost_amount"],
                package["days"],
                "points",
                package["description"]
            )
            
            if success:
                return True, f"✅ 兑换成功！\n{package['description']}\n剩余积分: {balance_after}"
            else:
                # 兑换失败，退还积分
                await self.recharge(user_id, points_cost, "system", description="配额包兑换失败退款")
                return False, "❌ 兑换失败，积分已退还"
                
        except Exception as e:
            logger.error(f"[PointsManager] 兑换配额包失败: {e}", exc_info=True)
            return False, "❌ 兑换失败，请稍后重试"
    
    async def get_transactions(self, user_id: str, limit: int = 10) -> List[Dict]:
        """
        获取积分流水
        
        Args:
            user_id: 用户ID
            limit: 返回条数
            
        Returns:
            流水记录列表
        """
        try:
            rows = self.db.execute("""
                SELECT amount, balance_after, type, source, description, created_at
                FROM points_transactions
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, limit))
            
            transactions = []
            for row in rows:
                transactions.append({
                    "amount": row['amount'],
                    "balance_after": row['balance_after'],
                    "type": row['type'],
                    "source": row['source'],
                    "description": row['description'],
                    "created_at": row['created_at']
                })
            
            return transactions
            
        except Exception as e:
            logger.error(f"[PointsManager] 获取积分流水失败: {e}")
            return []
    
    async def get_active_boosts(self, user_id: str) -> List[Dict]:
        """
        获取用户的有效配额加成
        
        Args:
            user_id: 用户ID
            
        Returns:
            配额加成列表
        """
        try:
            today = date.today()
            rows = self.db.execute("""
                SELECT action_type, boost_amount, expire_date, description
                FROM quota_boosts
                WHERE user_id = ? AND expire_date >= ? AND is_used = 0
                ORDER BY expire_date ASC
            """, (user_id, today))
            
            boosts = []
            for row in rows:
                boosts.append({
                    "action_type": row['action_type'] or "全局",
                    "boost_amount": row['boost_amount'],
                    "expire_date": row['expire_date'],
                    "description": row['description']
                })
            
            return boosts
            
        except Exception as e:
            logger.error(f"[PointsManager] 获取配额加成失败: {e}")
            return []
    
    def get_boost_packages(self) -> Dict:
        """获取所有可兑换的配额包"""
        return self.BOOST_PACKAGES
    
    def has_active_boost(self, user_id: str, package_key: str) -> bool:
        """
        检查用户是否有有效的配额加成包
        
        Args:
            user_id: 用户ID
            package_key: 配额包键名
            
        Returns:
            是否有有效的配额加成
        """
        try:
            today = date.today()
            row = self.db.execute_one("""
                SELECT id FROM quota_boosts
                WHERE user_id = ? AND action_type = ? AND expire_date >= ? AND is_used = 0
                LIMIT 1
            """, (user_id, package_key, today))
            
            return row is not None
        except Exception as e:
            logger.error(f"[PointsManager] 检查配额加成失败: {e}")
            return False


# ==================== 全局实例 ====================

_points_manager: Optional[PointsManager] = None


def get_points_manager(db: DatabaseManager = None) -> Optional[PointsManager]:
    """
    获取积分管理器实例（单例模式）
    
    Args:
        db: 数据库管理器（首次调用时必须提供）
    
    Returns:
        PointsManager 实例
    """
    global _points_manager
    
    if _points_manager is None and db is not None:
        _points_manager = PointsManager(db)
        logger.info("[PointsManager] 创建全局积分管理器实例")
    
    return _points_manager
