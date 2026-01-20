"""
邀请系统管理器

功能：
1. 邀请码生成与验证
2. 深度链接支持（Telegram）
3. 邀请关系追踪
4. 邀请奖励发放
5. 防刷机制

邀请方式：
1. 深度链接（Telegram）: https://t.me/{bot}?start=inv_{invite_code}
2. 邀请码（跨平台）: /绑定邀请 {invite_code}

使用示例：
    from common.invite_manager import get_invite_manager
    
    invite_manager = get_invite_manager(db, points_manager)
    
    # 获取邀请链接/码
    code, link = invite_manager.get_invite_info(user_id, platform, bot_username)
    
    # 处理邀请
    success, msg = invite_manager.process_invite(new_user_id, invite_code)
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
import hashlib
import secrets
import re

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from .database_manager import DatabaseManager


@dataclass
class InviteReward:
    """邀请奖励配置"""
    inviter_points: int = 50       # 邀请人获得积分
    invitee_points: int = 30       # 被邀请人获得积分
    inviter_quota_days: int = 0    # 邀请人获得配额天数
    invitee_quota_days: int = 0    # 被邀请人获得配额天数
    max_daily_invites: int = 10    # 每日最大邀请数
    max_total_invites: int = 100   # 总最大邀请数
    cooldown_hours: int = 24       # 新用户绑定邀请冷却时间


# 默认奖励配置
DEFAULT_REWARD = InviteReward(
    inviter_points=50,
    invitee_points=30,
    max_daily_invites=10,
    max_total_invites=100
)


class InviteManager:
    """邀请系统管理器"""
    
    def __init__(
        self, 
        db: DatabaseManager, 
        points_manager=None,
        reward_config: InviteReward = None
    ):
        """
        初始化邀请管理器
        
        Args:
            db: 数据库管理器
            points_manager: 积分管理器
            reward_config: 奖励配置
        """
        self.db = db
        self.points_manager = points_manager
        self.reward = reward_config or DEFAULT_REWARD
        self._init_tables()
    
    def _init_tables(self):
        """初始化数据库表"""
        try:
            # 邀请码表
            self.db.execute_write("""
                CREATE TABLE IF NOT EXISTS invite_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL UNIQUE,
                    invite_code TEXT NOT NULL UNIQUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_invite_code 
                ON invite_codes(invite_code)
            """)
            
            # 邀请关系表
            self.db.execute_write("""
                CREATE TABLE IF NOT EXISTS invite_relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    inviter_id TEXT NOT NULL,
                    invitee_id TEXT NOT NULL UNIQUE,
                    invite_code TEXT NOT NULL,
                    inviter_reward INTEGER DEFAULT 0,
                    invitee_reward INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    rewarded_at DATETIME
                )
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_invite_inviter 
                ON invite_relations(inviter_id)
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_invite_invitee 
                ON invite_relations(invitee_id)
            """)
            
            # 邀请统计表
            self.db.execute_write("""
                CREATE TABLE IF NOT EXISTS invite_stats (
                    user_id TEXT PRIMARY KEY,
                    total_invites INTEGER DEFAULT 0,
                    successful_invites INTEGER DEFAULT 0,
                    total_rewards INTEGER DEFAULT 0,
                    last_invite_at DATETIME,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            logger.info("[InviteManager] 数据库表初始化完成")
            
        except Exception as e:
            logger.error(f"[InviteManager] 数据库初始化失败: {e}")
    
    # ==================== 邀请码管理 ====================
    
    def _generate_invite_code(self, user_id: str) -> str:
        """
        生成邀请码
        
        规则：6位字母数字，基于用户ID哈希+随机数
        """
        # 基于用户ID的哈希前缀（保证同一用户生成相同前缀）
        hash_prefix = hashlib.md5(user_id.encode()).hexdigest()[:3].upper()
        # 随机后缀
        random_suffix = secrets.token_hex(2).upper()[:3]
        return f"{hash_prefix}{random_suffix}"
    
    def get_or_create_invite_code(self, user_id: str) -> str:
        """获取或创建用户的邀请码"""
        try:
            # 查询现有邀请码
            row = self.db.execute_one(
                "SELECT invite_code FROM invite_codes WHERE user_id = ?",
                (user_id,)
            )
            if row:
                return row['invite_code']
            
            # 生成新邀请码（确保唯一）
            for _ in range(10):
                code = self._generate_invite_code(user_id)
                existing = self.db.execute_one(
                    "SELECT id FROM invite_codes WHERE invite_code = ?",
                    (code,)
                )
                if not existing:
                    self.db.execute_write(
                        "INSERT INTO invite_codes (user_id, invite_code) VALUES (?, ?)",
                        (user_id, code)
                    )
                    logger.info(f"[InviteManager] 创建邀请码: user={user_id}, code={code}")
                    return code
            
            # 如果多次冲突，使用更长的随机码
            code = secrets.token_hex(4).upper()
            self.db.execute_write(
                "INSERT INTO invite_codes (user_id, invite_code) VALUES (?, ?)",
                (user_id, code)
            )
            return code
            
        except Exception as e:
            logger.error(f"[InviteManager] 获取邀请码失败: {e}")
            return ""
    
    def get_invite_info(
        self, 
        user_id: str, 
        platform: str = None,
        bot_username: str = None
    ) -> Tuple[str, Optional[str]]:
        """
        获取邀请信息
        
        Args:
            user_id: 用户ID
            platform: 平台名称
            bot_username: 机器人用户名（Telegram）
            
        Returns:
            (邀请码, 邀请链接)
        """
        code = self.get_or_create_invite_code(user_id)
        
        # 生成深度链接（仅 Telegram）
        link = None
        if platform == "telegram" and bot_username:
            link = f"https://t.me/{bot_username}?start=inv_{code}"
        
        return code, link
    
    def get_inviter_by_code(self, invite_code: str) -> Optional[str]:
        """根据邀请码获取邀请人ID"""
        try:
            row = self.db.execute_one(
                "SELECT user_id FROM invite_codes WHERE invite_code = ?",
                (invite_code.upper(),)
            )
            return row['user_id'] if row else None
        except Exception as e:
            logger.error(f"[InviteManager] 查询邀请人失败: {e}")
            return None
    
    # ==================== 邀请处理 ====================
    
    def can_be_invited(self, user_id: str) -> Tuple[bool, str]:
        """
        检查用户是否可以被邀请
        
        Returns:
            (可以, 原因)
        """
        try:
            # 检查是否已被邀请
            existing = self.db.execute_one(
                "SELECT inviter_id FROM invite_relations WHERE invitee_id = ?",
                (user_id,)
            )
            if existing:
                return False, "您已绑定过邀请人"
            
            # 检查账户创建时间（防止老用户绑定）
            # 这里可以根据实际情况调整逻辑
            
            return True, ""
            
        except Exception as e:
            logger.error(f"[InviteManager] 检查邀请资格失败: {e}")
            return False, "系统错误"
    
    def can_invite(self, inviter_id: str) -> Tuple[bool, str]:
        """
        检查用户是否可以邀请他人
        
        Returns:
            (可以, 原因)
        """
        try:
            stats = self.get_invite_stats(inviter_id)
            
            # 检查总邀请数
            if stats['successful_invites'] >= self.reward.max_total_invites:
                return False, f"已达到最大邀请数 {self.reward.max_total_invites}"
            
            # 检查今日邀请数
            today = datetime.now().date()
            today_count = self.db.execute_one("""
                SELECT COUNT(*) as count FROM invite_relations 
                WHERE inviter_id = ? AND DATE(created_at) = ?
            """, (inviter_id, today))
            
            if today_count and today_count['count'] >= self.reward.max_daily_invites:
                return False, f"今日邀请已达上限 {self.reward.max_daily_invites}"
            
            return True, ""
            
        except Exception as e:
            logger.error(f"[InviteManager] 检查邀请资格失败: {e}")
            return False, "系统错误"
    
    def process_invite(
        self, 
        invitee_id: str, 
        invite_code: str,
        auto_reward: bool = True
    ) -> Tuple[bool, str]:
        """
        处理邀请绑定
        
        Args:
            invitee_id: 被邀请人ID
            invite_code: 邀请码
            auto_reward: 是否自动发放奖励
            
        Returns:
            (成功, 消息)
        """
        try:
            invite_code = invite_code.upper().strip()
            
            # 验证邀请码
            inviter_id = self.get_inviter_by_code(invite_code)
            if not inviter_id:
                return False, "邀请码无效"
            
            # 不能邀请自己
            if inviter_id == invitee_id:
                return False, "不能使用自己的邀请码"
            
            # 检查被邀请人资格
            can_invited, reason = self.can_be_invited(invitee_id)
            if not can_invited:
                return False, reason
            
            # 检查邀请人资格
            can_inv, reason = self.can_invite(inviter_id)
            if not can_inv:
                return False, f"邀请人{reason}"
            
            # 创建邀请关系
            self.db.execute_write("""
                INSERT INTO invite_relations 
                (inviter_id, invitee_id, invite_code, status)
                VALUES (?, ?, ?, 'pending')
            """, (inviter_id, invitee_id, invite_code))
            
            # 更新统计
            self._update_stats(inviter_id)
            
            # 发放奖励
            if auto_reward:
                self._grant_rewards(inviter_id, invitee_id)
            
            logger.info(f"[InviteManager] 邀请成功: inviter={inviter_id}, invitee={invitee_id}")
            
            return True, f"绑定成功！您获得 {self.reward.invitee_points} 积分，邀请人获得 {self.reward.inviter_points} 积分"
            
        except Exception as e:
            logger.error(f"[InviteManager] 处理邀请失败: {e}")
            return False, "绑定失败，请稍后重试"
    
    def _grant_rewards(self, inviter_id: str, invitee_id: str):
        """发放邀请奖励"""
        try:
            if not self.points_manager:
                logger.warning("[InviteManager] 积分管理器不可用，跳过奖励发放")
                return
            
            # 发放邀请人奖励
            if self.reward.inviter_points > 0:
                self.points_manager.add_points(
                    inviter_id,
                    self.reward.inviter_points,
                    "invite_reward",
                    f"邀请新用户奖励"
                )
            
            # 发放被邀请人奖励
            if self.reward.invitee_points > 0:
                self.points_manager.add_points(
                    invitee_id,
                    self.reward.invitee_points,
                    "invite_bonus",
                    "新用户邀请奖励"
                )
            
            # 更新邀请关系状态
            self.db.execute_write("""
                UPDATE invite_relations 
                SET status = 'rewarded', 
                    inviter_reward = ?,
                    invitee_reward = ?,
                    rewarded_at = ?
                WHERE inviter_id = ? AND invitee_id = ?
            """, (
                self.reward.inviter_points,
                self.reward.invitee_points,
                datetime.now(),
                inviter_id,
                invitee_id
            ))
            
            # 追踪邀请人的任务进度
            try:
                from .task_tracker import get_task_tracker, TaskTrigger
                tracker = get_task_tracker()
                tracker.track(inviter_id, TaskTrigger.INVITE)
            except Exception:
                pass
            
        except Exception as e:
            logger.error(f"[InviteManager] 发放奖励失败: {e}")
    
    def _update_stats(self, inviter_id: str):
        """更新邀请统计"""
        try:
            # 计算统计数据
            stats = self.db.execute_one("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'rewarded' THEN 1 ELSE 0 END) as successful,
                    SUM(inviter_reward) as rewards
                FROM invite_relations 
                WHERE inviter_id = ?
            """, (inviter_id,))
            
            self.db.execute_write("""
                INSERT OR REPLACE INTO invite_stats 
                (user_id, total_invites, successful_invites, total_rewards, last_invite_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                inviter_id,
                stats['total'] or 0,
                stats['successful'] or 0,
                stats['rewards'] or 0,
                datetime.now(),
                datetime.now()
            ))
            
        except Exception as e:
            logger.error(f"[InviteManager] 更新统计失败: {e}")
    
    # ==================== 查询接口 ====================
    
    def get_invite_stats(self, user_id: str) -> Dict[str, Any]:
        """获取用户邀请统计"""
        try:
            row = self.db.execute_one(
                "SELECT * FROM invite_stats WHERE user_id = ?",
                (user_id,)
            )
            if row:
                return dict(row)
            return {
                'user_id': user_id,
                'total_invites': 0,
                'successful_invites': 0,
                'total_rewards': 0
            }
        except Exception as e:
            logger.error(f"[InviteManager] 获取统计失败: {e}")
            return {'total_invites': 0, 'successful_invites': 0, 'total_rewards': 0}
    
    def get_invitees(self, user_id: str, limit: int = 20) -> List[Dict]:
        """获取用户邀请的人列表"""
        try:
            rows = self.db.execute("""
                SELECT invitee_id, inviter_reward, status, created_at
                FROM invite_relations 
                WHERE inviter_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, limit))
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"[InviteManager] 获取邀请列表失败: {e}")
            return []
    
    def get_inviter(self, user_id: str) -> Optional[str]:
        """获取用户的邀请人"""
        try:
            row = self.db.execute_one(
                "SELECT inviter_id FROM invite_relations WHERE invitee_id = ?",
                (user_id,)
            )
            return row['inviter_id'] if row else None
        except Exception as e:
            logger.error(f"[InviteManager] 获取邀请人失败: {e}")
            return None
    
    def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        """获取邀请排行榜"""
        try:
            rows = self.db.execute("""
                SELECT user_id, successful_invites, total_rewards
                FROM invite_stats 
                WHERE successful_invites > 0
                ORDER BY successful_invites DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"[InviteManager] 获取排行榜失败: {e}")
            return []


# ==================== 全局实例 ====================

_invite_manager: Optional[InviteManager] = None


def get_invite_manager(
    db: DatabaseManager = None,
    points_manager=None,
    reward_config: InviteReward = None
) -> Optional[InviteManager]:
    """获取邀请管理器实例（单例模式）"""
    global _invite_manager
    
    if _invite_manager is None and db is not None:
        _invite_manager = InviteManager(db, points_manager, reward_config)
        logger.info("[InviteManager] 创建全局邀请管理器实例")
    
    return _invite_manager
