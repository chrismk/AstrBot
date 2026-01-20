"""
配额预留机制

功能：
1. 预留配额（避免检查通过但操作失败导致配额浪费）
2. 确认消费预留的配额
3. 取消预留（操作失败时）
4. 自动清理过期预留
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple
from .database_manager import DatabaseManager

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class QuotaReservation:
    """配额预留管理器"""
    
    # 预留超时时间（秒）
    DEFAULT_TIMEOUT = 300  # 5分钟
    
    def __init__(self, db_manager: DatabaseManager, quota_validator):
        """
        初始化配额预留管理器
        
        Args:
            db_manager: 数据库管理器实例
            quota_validator: 配额验证器实例
        """
        self.db = db_manager
        self.validator = quota_validator
    
    async def reserve(
        self,
        user_id: str,
        action_type: str,
        plugin_name: str,
        timeout: int = DEFAULT_TIMEOUT,
        use_points: bool = False
    ) -> Tuple[Optional[str], str]:
        """
        预留配额
        
        Args:
            user_id: 用户ID
            action_type: 操作类型
            plugin_name: 插件名称
            timeout: 超时时间（秒）
            use_points: 是否允许使用积分
            
        Returns:
            (预留ID, 提示消息)
        """
        try:
            # 1. 检查配额
            result = await self.validator.check_quota(
                user_id, action_type, plugin_name, use_points
            )
            
            if not result.allowed:
                return None, result.message
            
            # 2. 生成预留ID
            reservation_id = str(uuid.uuid4())
            expire_at = datetime.now() + timedelta(seconds=timeout)
            
            # 3. 创建预留记录
            self.db.execute_write("""
                INSERT INTO quota_reservations
                (reservation_id, user_id, action_type, plugin_name, points_cost, expire_at, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'reserved', ?)
            """, (reservation_id, user_id, action_type, plugin_name, result.points_cost, expire_at, datetime.now()))
            
            logger.info(
                f"[QuotaReservation] 预留配额成功: "
                f"user={user_id}, action={action_type}, id={reservation_id}"
            )
            
            return reservation_id, f"✅ 配额预留成功（{timeout}秒内有效）"
            
        except Exception as e:
            logger.error(f"[QuotaReservation] 预留配额失败: {e}", exc_info=True)
            return None, "❌ 预留失败，请稍后重试"
    
    async def confirm(self, reservation_id: str) -> Tuple[bool, str]:
        """
        确认消费预留的配额
        
        Args:
            reservation_id: 预留ID
            
        Returns:
            (是否成功, 提示消息)
        """
        try:
            # 1. 查询预留记录
            row = self.db.execute_one("""
                SELECT user_id, action_type, plugin_name, points_cost, expire_at, status
                FROM quota_reservations
                WHERE reservation_id = ?
            """, (reservation_id,))
            
            if not row:
                return False, "❌ 预留记录不存在"
            
            if row['status'] != 'reserved':
                return False, f"❌ 预留状态异常: {row['status']}"
            
            # 2. 检查是否过期
            expire_at = datetime.fromisoformat(row['expire_at'])
            if datetime.now() > expire_at:
                # 更新状态为已过期
                self.db.execute_write("""
                    UPDATE quota_reservations
                    SET status = 'expired', updated_at = ?
                    WHERE reservation_id = ?
                """, (datetime.now(), reservation_id))
                
                return False, "❌ 预留已过期"
            
            # 3. 消费配额
            success, msg = await self.validator.consume_quota(
                row['user_id'],
                row['action_type'],
                row['plugin_name'],
                row['points_cost']
            )
            
            if not success:
                # 消费失败，更新状态
                self.db.execute_write("""
                    UPDATE quota_reservations
                    SET status = 'failed', updated_at = ?
                    WHERE reservation_id = ?
                """, (datetime.now(), reservation_id))
                
                return False, msg
            
            # 4. 更新预留状态为已确认
            self.db.execute_write("""
                UPDATE quota_reservations
                SET status = 'confirmed', confirmed_at = ?, updated_at = ?
                WHERE reservation_id = ?
            """, (datetime.now(), datetime.now(), reservation_id))
            
            logger.info(
                f"[QuotaReservation] 确认配额消费: "
                f"user={row['user_id']}, action={row['action_type']}, id={reservation_id}"
            )
            
            return True, "✅ 配额消费成功"
            
        except Exception as e:
            logger.error(f"[QuotaReservation] 确认配额失败: {e}", exc_info=True)
            return False, "❌ 确认失败，请稍后重试"
    
    async def cancel(self, reservation_id: str) -> Tuple[bool, str]:
        """
        取消预留
        
        Args:
            reservation_id: 预留ID
            
        Returns:
            (是否成功, 提示消息)
        """
        try:
            # 查询预留记录
            row = self.db.execute_one("""
                SELECT status FROM quota_reservations
                WHERE reservation_id = ?
            """, (reservation_id,))
            
            if not row:
                return False, "❌ 预留记录不存在"
            
            if row['status'] != 'reserved':
                return False, f"❌ 预留状态异常，无法取消: {row['status']}"
            
            # 更新状态为已取消
            self.db.execute_write("""
                UPDATE quota_reservations
                SET status = 'cancelled', updated_at = ?
                WHERE reservation_id = ?
            """, (datetime.now(), reservation_id))
            
            logger.info(f"[QuotaReservation] 取消预留: id={reservation_id}")
            
            return True, "✅ 预留已取消"
            
        except Exception as e:
            logger.error(f"[QuotaReservation] 取消预留失败: {e}", exc_info=True)
            return False, "❌ 取消失败，请稍后重试"
    
    async def cleanup_expired(self) -> int:
        """
        清理过期的预留记录（定时任务）
        
        Returns:
            清理的记录数
        """
        try:
            now = datetime.now()
            
            # 更新过期的预留状态
            result = self.db.execute_write("""
                UPDATE quota_reservations
                SET status = 'expired', updated_at = ?
                WHERE status = 'reserved' AND expire_at < ?
            """, (now, now))
            
            count = result if isinstance(result, int) else 0
            
            if count > 0:
                logger.info(f"[QuotaReservation] 清理了 {count} 条过期预留记录")
            
            return count
            
        except Exception as e:
            logger.error(f"[QuotaReservation] 清理过期预留失败: {e}")
            return 0
    
    async def get_reservation_info(self, reservation_id: str) -> Optional[dict]:
        """
        获取预留信息
        
        Args:
            reservation_id: 预留ID
            
        Returns:
            预留信息字典
        """
        try:
            row = self.db.execute_one("""
                SELECT user_id, action_type, plugin_name, points_cost, 
                       expire_at, status, created_at, confirmed_at
                FROM quota_reservations
                WHERE reservation_id = ?
            """, (reservation_id,))
            
            if not row:
                return None
            
            return {
                "reservation_id": reservation_id,
                "user_id": row['user_id'],
                "action_type": row['action_type'],
                "plugin_name": row['plugin_name'],
                "points_cost": row['points_cost'],
                "expire_at": row['expire_at'],
                "status": row['status'],
                "created_at": row['created_at'],
                "confirmed_at": row['confirmed_at']
            }
            
        except Exception as e:
            logger.error(f"[QuotaReservation] 获取预留信息失败: {e}")
            return None
