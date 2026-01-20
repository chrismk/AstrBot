"""
会员管理器

负责：
1. 会员升级/续费
2. 会员过期检查
3. 会员信息查询
"""

from datetime import datetime, date, timedelta
from typing import Optional, Dict
from .database_manager import DatabaseManager
from .quota_validator import MemberLevel

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class MembershipManager:
    """会员管理器"""
    
    # 会员价格配置（单位：元）
    MEMBERSHIP_PRICES = {
        MemberLevel.PREMIUM: {
            "monthly": 19.9,
            "quarterly": 49.9,
            "yearly": 199.0,
        },
        MemberLevel.VIP: {
            "yearly": 399.0,
        }
    }
    
    def __init__(self, db_manager: DatabaseManager):
        """
        初始化会员管理器
        
        Args:
            db_manager: 数据库管理器实例
        """
        self.db = db_manager
    
    async def upgrade(
        self,
        user_id: str,
        level: MemberLevel,
        months: int = 1
    ) -> bool:
        """
        升级会员
        
        Args:
            user_id: 用户ID
            level: 会员等级
            months: 月数
            
        Returns:
            是否成功
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # 1. 查询现有会员信息
                cursor.execute("""
                    SELECT level, expire_date FROM memberships WHERE user_id = ?
                    ORDER BY id DESC LIMIT 1
                """, (user_id,))
                
                row = cursor.fetchone()
                
                if row:
                    current_level = row[0]
                    current_expire = row[1]
                    
                    # 解析到期日期
                    if current_expire:
                        try:
                            current_expire_date = datetime.strptime(current_expire, "%Y-%m-%d").date()
                        except:
                            current_expire_date = date.today()
                    else:
                        current_expire_date = date.today()
                    
                    # 如果当前会员未过期，从到期日开始续期
                    if current_expire_date > date.today():
                        new_expire = current_expire_date + timedelta(days=30 * months)
                    else:
                        new_expire = date.today() + timedelta(days=30 * months)
                    
                    # 更新会员信息
                    cursor.execute("""
                        UPDATE memberships
                        SET level = ?, expire_date = ?, updated_at = ?
                        WHERE user_id = ? AND id = (
                            SELECT id FROM memberships WHERE user_id = ? ORDER BY id DESC LIMIT 1
                        )
                    """, (level.value, new_expire, datetime.now(), user_id, user_id))
                else:
                    # 创建新会员
                    new_expire = date.today() + timedelta(days=30 * months)
                    cursor.execute("""
                        INSERT INTO memberships
                        (user_id, level, expire_date, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (user_id, level.value, new_expire, datetime.now(), datetime.now()))
                
                conn.commit()
                logger.info(f"[MembershipManager] 用户 {user_id} 升级到 {level.name} (有效期至 {new_expire})")
                return True
                
        except Exception as e:
            logger.error(f"[MembershipManager] 升级会员失败: {e}")
            return False
    
    async def get_membership_info(self, user_id: str) -> Optional[Dict]:
        """
        获取会员信息
        
        Args:
            user_id: 用户ID
            
        Returns:
            会员信息字典，包含 level, expire_date, is_expired, days_remaining
        """
        try:
            row = self.db.execute_one("""
                SELECT level, expire_date, created_at
                FROM memberships
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 1
            """, (user_id,))
            
            if not row:
                return {
                    "level": MemberLevel.FREE,
                    "level_name": "免费用户",
                    "expire_date": None,
                    "is_expired": False,
                    "days_remaining": None
                }
            
            level = MemberLevel(row['level'])
            expire_date_str = row['expire_date']
            
            # 解析到期日期
            is_expired = False
            days_remaining = None
            
            if expire_date_str:
                try:
                    expire_date = datetime.strptime(expire_date_str, "%Y-%m-%d").date()
                    today = date.today()
                    
                    if expire_date < today:
                        is_expired = True
                        level = MemberLevel.FREE
                    else:
                        days_remaining = (expire_date - today).days
                except:
                    pass
            
            level_names = {
                MemberLevel.FREE: "免费用户",
                MemberLevel.PREMIUM: "高级会员",
                MemberLevel.VIP: "VIP会员"
            }
            
            return {
                "level": level,
                "level_name": level_names.get(level, "未知"),
                "expire_date": expire_date_str,
                "is_expired": is_expired,
                "days_remaining": days_remaining
            }
            
        except Exception as e:
            logger.error(f"[MembershipManager] 获取会员信息失败: {e}")
            return None
    
    async def check_and_expire_memberships(self) -> int:
        """
        检查并处理过期会员（定时任务）
        
        Returns:
            处理的过期会员数量
        """
        try:
            today = date.today()
            
            # 查询所有过期但未降级的会员
            rows = self.db.execute("""
                SELECT user_id, level, expire_date
                FROM memberships
                WHERE expire_date < ? AND level > 0
            """, (today,))
            
            count = 0
            for row in rows:
                user_id = row['user_id']
                # 降级为免费用户
                self.db.execute_write("""
                    UPDATE memberships
                    SET level = 0, updated_at = ?
                    WHERE user_id = ?
                """, (datetime.now(), user_id))
                
                logger.info(f"[MembershipManager] 用户 {user_id} 会员已过期，降级为免费用户")
                count += 1
            
            return count
            
        except Exception as e:
            logger.error(f"[MembershipManager] 检查过期会员失败: {e}")
            return 0
    
    def get_price(self, level: MemberLevel, period: str = "monthly") -> Optional[float]:
        """
        获取会员价格
        
        Args:
            level: 会员等级
            period: 周期 (monthly/quarterly/yearly)
            
        Returns:
            价格（元）
        """
        if level in self.MEMBERSHIP_PRICES:
            return self.MEMBERSHIP_PRICES[level].get(period)
        return None
