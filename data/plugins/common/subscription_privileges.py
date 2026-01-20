"""
订阅权益配置模块

整合现有会员系统，为订阅功能提供差异化权益
支持通过管理员界面动态配置
"""
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from .quota_validator import MemberLevel, QuotaValidator

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


# 订阅权益默认配置（数据库无数据时使用）
DEFAULT_SUBSCRIPTION_PRIVILEGES = {
    MemberLevel.FREE: {
        'max_subscriptions': 3,           # 最多订阅3个源
        'push_frequency': 'daily',        # 每日推送
        'push_times': ['19:00'],          # 固定时间
        'source_access': [0],             # AccessLevel.PUBLIC
        'history_days': 7,                # 历史记录保留天数
        'ad_enabled': True,               # 显示广告
        'custom_push_time': False,        # 不支持自定义推送时间
        'priority_push': False,           # 不支持优先推送
    },
    MemberLevel.PREMIUM: {
        'max_subscriptions': 20,          # 最多订阅20个源
        'push_frequency': 'custom',       # 自定义频率
        'push_times': 'custom',           # 自定义时间
        'source_access': [0, 1, 2],       # PUBLIC + REGISTERED + MEMBER
        'history_days': 90,
        'ad_enabled': False,
        'custom_push_time': True,
        'priority_push': False,
    },
    MemberLevel.VIP: {
        'max_subscriptions': -1,          # 无限
        'push_frequency': 'realtime',     # 实时推送
        'push_times': 'custom',
        'source_access': [0, 1, 2, 3],    # 全部 + VIP专属
        'history_days': -1,               # 永久
        'ad_enabled': False,
        'custom_push_time': True,
        'priority_push': True,            # 优先推送
    }
}

# 向后兼容：保持旧的变量名
SUBSCRIPTION_PRIVILEGES = DEFAULT_SUBSCRIPTION_PRIVILEGES

# 订阅配额包（可用积分兑换）
SUBSCRIPTION_BOOST_PACKAGES = {
    "subscription_5": {
        "action_type": "subscription_subscribe",
        "boost_amount": 5,
        "points_cost": 30,
        "days": 30,
        "description": "订阅额度+5（30天有效）"
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

# 订阅相关积分奖励
SUBSCRIPTION_POINTS_REWARDS = {
    'first_subscribe': 10,        # 首次订阅奖励
    'subscribe_5': 20,            # 订阅满5个源
    'subscribe_10': 50,           # 订阅满10个源
    'daily_read_push': 2,         # 每日阅读推送
    'continuous_read_7d': 30,     # 连续7天阅读
    'share_source': 5,            # 分享订阅源
    'invite_subscribe': 20,       # 邀请好友订阅
}


class SubscriptionPrivilegeManager:
    """订阅权益管理器 - 支持数据库持久化配置"""
    
    # 会员等级名称映射
    LEVEL_NAMES = {
        MemberLevel.FREE: '免费用户',
        MemberLevel.PREMIUM: '高级会员',
        MemberLevel.VIP: 'VIP会员'
    }
    
    # 订阅源访问等级名称
    ACCESS_LEVEL_NAMES = {
        0: '公开',
        1: '注册用户',
        2: '高级会员',
        3: 'VIP'
    }
    
    def __init__(self, quota_validator: QuotaValidator = None, db_manager = None):
        self.quota_validator = quota_validator
        self.db = db_manager
        self._config_cache: Dict[int, Dict[str, Any]] = {}  # level -> config
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = 300  # 缓存5分钟
        
        # 初始化数据库表
        if self.db:
            self._init_database()
    
    def set_db_manager(self, db_manager):
        """设置数据库管理器"""
        self.db = db_manager
        if self.db:
            self._init_database()
    
    def _init_database(self):
        """初始化数据库表"""
        try:
            self.db.execute_write('''
                CREATE TABLE IF NOT EXISTS subscription_privilege_config (
                    level INTEGER PRIMARY KEY,
                    max_subscriptions INTEGER DEFAULT 3,
                    source_access TEXT DEFAULT '[0]',
                    ad_enabled INTEGER DEFAULT 1,
                    custom_push_time INTEGER DEFAULT 0,
                    priority_push INTEGER DEFAULT 0,
                    history_days INTEGER DEFAULT 7,
                    updated_at TEXT
                )
            ''')
            logger.debug("[SubscriptionPrivileges] 数据库表初始化完成")
        except Exception as e:
            logger.error(f"[SubscriptionPrivileges] 初始化数据库失败: {e}")
    
    def _get_config_from_db(self, level: MemberLevel) -> Optional[Dict[str, Any]]:
        """从数据库获取配置"""
        if not self.db:
            return None
        
        try:
            row = self.db.execute(
                'SELECT * FROM subscription_privilege_config WHERE level = ?',
                (level.value,)
            )
            if row:
                row = row[0]
                return {
                    'max_subscriptions': row['max_subscriptions'],
                    'source_access': json.loads(row['source_access']) if row['source_access'] else [0],
                    'ad_enabled': bool(row['ad_enabled']),
                    'custom_push_time': bool(row['custom_push_time']),
                    'priority_push': bool(row['priority_push']),
                    'history_days': row['history_days']
                }
        except Exception as e:
            logger.error(f"[SubscriptionPrivileges] 读取配置失败: {e}")
        return None
    
    def _get_level_config(self, level: MemberLevel) -> Dict[str, Any]:
        """获取指定等级的配置（优先数据库，否则默认值）"""
        # 检查缓存
        if self._cache_time and (datetime.now() - self._cache_time).total_seconds() < self._cache_ttl:
            if level.value in self._config_cache:
                return self._config_cache[level.value]
        
        # 从数据库读取
        db_config = self._get_config_from_db(level)
        if db_config:
            self._config_cache[level.value] = db_config
            self._cache_time = datetime.now()
            return db_config
        
        # 使用默认配置
        return DEFAULT_SUBSCRIPTION_PRIVILEGES.get(level, DEFAULT_SUBSCRIPTION_PRIVILEGES[MemberLevel.FREE])
    
    def get_all_level_configs(self) -> Dict[int, Dict[str, Any]]:
        """获取所有等级的配置"""
        configs = {}
        for level in [MemberLevel.FREE, MemberLevel.PREMIUM, MemberLevel.VIP]:
            configs[level.value] = self._get_level_config(level)
            configs[level.value]['level_name'] = self.LEVEL_NAMES.get(level, '未知')
        return configs
    
    def update_level_config(self, level: MemberLevel, config: Dict[str, Any]) -> bool:
        """更新指定等级的配置"""
        if not self.db:
            logger.warning("[SubscriptionPrivileges] 数据库未初始化，无法保存配置")
            return False
        
        try:
            now = datetime.now().isoformat()
            source_access_json = json.dumps(config.get('source_access', [0]))
            
            self.db.execute_write('''
                INSERT OR REPLACE INTO subscription_privilege_config 
                (level, max_subscriptions, source_access, ad_enabled, custom_push_time, priority_push, history_days, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                level.value,
                config.get('max_subscriptions', 3),
                source_access_json,
                1 if config.get('ad_enabled', True) else 0,
                1 if config.get('custom_push_time', False) else 0,
                1 if config.get('priority_push', False) else 0,
                config.get('history_days', 7),
                now
            ))
            
            # 清除缓存
            self._config_cache.clear()
            self._cache_time = None
            
            logger.info(f"[SubscriptionPrivileges] 更新 {self.LEVEL_NAMES.get(level)} 配置成功")
            return True
            
        except Exception as e:
            logger.error(f"[SubscriptionPrivileges] 更新配置失败: {e}")
            return False
    
    def update_subscription_limit(self, level: MemberLevel, max_subscriptions: int) -> bool:
        """更新指定等级的订阅数量限制"""
        config = self._get_level_config(level)
        config['max_subscriptions'] = max_subscriptions
        return self.update_level_config(level, config)
    
    def update_source_access(self, level: MemberLevel, access_levels: List[int]) -> bool:
        """更新指定等级的订阅源访问权限"""
        config = self._get_level_config(level)
        config['source_access'] = access_levels
        return self.update_level_config(level, config)
    
    def get_user_privileges(self, user_id: str) -> Dict[str, Any]:
        """获取用户订阅权益"""
        # 获取用户会员等级
        level = MemberLevel.FREE
        if self.quota_validator:
            level = self.quota_validator.get_user_level(user_id)
        
        return self._get_level_config(level)
    
    def get_max_subscriptions(self, user_id: str) -> int:
        """获取用户最大订阅数"""
        from .points_manager import get_points_manager
        
        privileges = self.get_user_privileges(user_id)
        max_subs = privileges.get('max_subscriptions', 3)
        
        # 检查是否有临时配额加成包
        points_manager = get_points_manager()
        if points_manager:
            # 检查订阅配额加成包
            for package_key in ['subscription_5', 'subscription_10', 'subscription_unlimited_7d']:
                if points_manager.has_active_boost(user_id, package_key):
                    if package_key == 'subscription_unlimited_7d':
                        return -1  # 无限订阅
                    elif package_key == 'subscription_10':
                        max_subs = max(max_subs, 10) if max_subs != -1 else -1
                    elif package_key == 'subscription_5':
                        max_subs = max(max_subs, 5) if max_subs != -1 else -1
        
        return max_subs
    
    def can_subscribe(self, user_id: str, current_count: int) -> tuple[bool, str]:
        """检查用户是否可以订阅"""
        max_subs = self.get_max_subscriptions(user_id)
        
        if max_subs == -1:
            return True, ""
        
        if current_count >= max_subs:
            return False, f"订阅数已达上限 ({current_count}/{max_subs})\n\n💡 升级会员可获得更多订阅额度"
        
        return True, ""
    
    def can_access_source(self, user_id: str, source_access_level: int) -> tuple[bool, str]:
        """检查用户是否可以访问订阅源"""
        from .points_manager import get_points_manager
        
        privileges = self.get_user_privileges(user_id)
        allowed_levels = privileges.get('source_access', [0])
        
        # 检查是否有临时VIP源访问权限包
        points_manager = get_points_manager()
        if points_manager and source_access_level == 3:  # VIP源
            if points_manager.has_active_boost(user_id, 'vip_source_access_7d'):
                return True, ""
        
        if source_access_level in allowed_levels:
            return True, ""
        
        # 获取所需等级名称
        required_level = self.ACCESS_LEVEL_NAMES.get(source_access_level, 'VIP')
        
        return False, f"该订阅源为 {required_level} 专属\n\n💎 升级会员即可订阅"
    
    def get_push_priority(self, user_id: str) -> int:
        """获取用户推送优先级（数字越大优先级越高）"""
        privileges = self.get_user_privileges(user_id)
        
        if privileges.get('priority_push'):
            return 10  # VIP最高优先级
        
        level = MemberLevel.FREE
        if self.quota_validator:
            level = self.quota_validator.get_user_level(user_id)
        
        return level.value  # 0=FREE, 1=PREMIUM, 2=VIP
    
    def should_show_ad(self, user_id: str) -> bool:
        """是否应该显示广告"""
        privileges = self.get_user_privileges(user_id)
        return privileges.get('ad_enabled', True)
    
    def format_ad_message(self, content: str, user_id: str) -> str:
        """格式化带广告的消息"""
        if not self.should_show_ad(user_id):
            return content
        
        # 使用广告管理器获取随机广告
        try:
            from .ad_manager import get_ad_manager
            ad_manager = get_ad_manager(self.db)
            
            # 获取用户等级
            user_level = 0
            if self.quota_validator:
                user_level = self.quota_validator.get_user_level(user_id).value
            
            ad_content = ad_manager.get_random_ad(user_level=user_level)
            if ad_content:
                return content + f"\n\n---\n{ad_content}"
        except Exception as e:
            logger.debug(f"[SubscriptionPrivileges] 获取广告失败: {e}")
        
        # 没有配置广告时，不添加任何广告内容
        return content


# 单例
_privilege_manager: Optional[SubscriptionPrivilegeManager] = None


def get_subscription_privilege_manager(quota_validator: QuotaValidator = None, db_manager = None) -> SubscriptionPrivilegeManager:
    """获取订阅权益管理器单例"""
    global _privilege_manager
    if _privilege_manager is None:
        _privilege_manager = SubscriptionPrivilegeManager(quota_validator, db_manager)
    elif db_manager and not _privilege_manager.db:
        _privilege_manager.set_db_manager(db_manager)
    return _privilege_manager


def init_subscription_privileges(quota_validator: QuotaValidator, db_manager = None) -> SubscriptionPrivilegeManager:
    """初始化订阅权益管理器"""
    global _privilege_manager
    _privilege_manager = SubscriptionPrivilegeManager(quota_validator, db_manager)
    logger.info("[SubscriptionPrivileges] 订阅权益管理器初始化完成")
    return _privilege_manager
