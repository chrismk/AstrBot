"""
插件配额与限流配置标准化模块

设计理念：
1. 插件配置作为配额和限流规则的唯一来源（Single Source of Truth）
2. 数据库仅用于运行时状态存储（使用记录、积分等）
3. 每次插件加载时，自动同步配置到数据库和限流器
4. 支持热重载，修改配置后重载插件即可生效

使用方式：
1. 在插件的 _conf_schema.json 中定义配额和限流配置
2. 在插件 __init__ 中调用 sync_plugin_quota() 同步配额
3. 在插件 __init__ 中调用 sync_plugin_rate_limit() 同步限流
4. 配额验证时使用 QuotaValidator（不变）

标准配置项命名规范：

【配额配置】
- quota_{action}_daily_limit: 每日限制 (-1=无限)
- quota_{action}_points_cost: 积分消耗 (0=免费)

【限流配置】
- rate_limit_{action}_max: 时间窗口内最大请求数
- rate_limit_{action}_window: 时间窗口（秒）
"""

from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class PluginQuotaConfig:
    """
    插件配额配置管理器
    
    负责将插件配置中的配额设置同步到数据库
    """
    
    # 标准配额配置项前缀
    QUOTA_PREFIX = "quota_"
    
    # 会员等级映射
    LEVEL_MAP = {
        'free': 0,
        'premium': 1,
        'vip': 2
    }
    
    @classmethod
    def sync_from_config(
        cls,
        plugin_name: str,
        plugin_config: Dict[str, Any],
        quota_validator,
        actions: List[Dict[str, str]]
    ) -> bool:
        """
        从插件配置同步配额规则到数据库
        
        Args:
            plugin_name: 插件名称
            plugin_config: 插件配置字典（从 AstrBotConfig 获取）
            quota_validator: QuotaValidator 实例
            actions: 操作类型列表，格式如下：
                [
                    {'action': 'view', 'action_type': 'douban_view', 'description': '查看豆瓣详情'},
                    {'action': 'search', 'action_type': 'douban_search', 'description': '搜索豆瓣'}
                ]
        
        Returns:
            是否同步成功
            
        Example:
            # 在插件 __init__ 中调用
            PluginQuotaConfig.sync_from_config(
                plugin_name='douban',
                plugin_config=self.plugin_config,
                quota_validator=self.quota_validator,
                actions=[
                    {'action': 'view', 'action_type': 'douban_view', 'description': '查看豆瓣详情'},
                    {'action': 'search', 'action_type': 'douban_search', 'description': '搜索豆瓣'}
                ]
            )
        """
        if not quota_validator:
            logger.warning(f"[PluginQuotaConfig] {plugin_name}: QuotaValidator 未初始化，跳过配额同步")
            return False
        
        try:
            rules = []
            
            for action_info in actions:
                action = action_info['action']  # 短名称，如 'view'
                action_type = action_info['action_type']  # 完整名称，如 'douban_view'
                description = action_info.get('description', '')
                
                # 从配置中读取各等级的配额设置
                rule = {
                    'action_type': action_type,
                    'description': description
                }
                
                for level_name in ['free', 'premium', 'vip']:
                    # 配置项命名：quota_{action}_{level}_limit / quota_{action}_{level}_points
                    limit_key = f"quota_{action}_{level_name}_limit"
                    points_key = f"quota_{action}_{level_name}_points"
                    
                    # 获取配置值，使用默认值
                    daily_limit = plugin_config.get(limit_key, -1 if level_name == 'vip' else -1)
                    points_cost = plugin_config.get(points_key, 0)
                    
                    rule[level_name] = {
                        'daily_limit': daily_limit,
                        'points_cost': points_cost
                    }
                
                rules.append(rule)
                logger.debug(f"[PluginQuotaConfig] {plugin_name}: 解析配额规则 {action_type}")
            
            # 同步到数据库（override=True 确保配置生效）
            success = quota_validator.register_quota_rules(
                plugin_name=plugin_name,
                rules=rules,
                override=True  # 始终使用插件配置覆盖数据库
            )
            
            if success:
                logger.info(f"[PluginQuotaConfig] {plugin_name}: 成功同步 {len(rules)} 条配额规则")
            else:
                logger.warning(f"[PluginQuotaConfig] {plugin_name}: 配额规则同步失败")
            
            return success
            
        except Exception as e:
            logger.error(f"[PluginQuotaConfig] {plugin_name}: 同步配额配置失败: {e}")
            return False
    
    @classmethod
    def generate_schema(cls, actions: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        生成标准的配额配置 Schema（用于 _conf_schema.json）
        
        Args:
            actions: 操作类型列表
            
        Returns:
            配置 Schema 字典
            
        Example:
            schema = PluginQuotaConfig.generate_schema([
                {'action': 'view', 'description': '查看详情'},
                {'action': 'search', 'description': '搜索'}
            ])
            # 输出可直接合并到 _conf_schema.json
        """
        schema = {}
        
        for action_info in actions:
            action = action_info['action']
            desc = action_info.get('description', action)
            
            # 免费用户配置
            schema[f"quota_{action}_free_limit"] = {
                "type": "int",
                "description": f"{desc} - 免费用户每日限制",
                "hint": f"免费用户每天可以{desc}的次数。-1 表示无限制",
                "default": -1
            }
            schema[f"quota_{action}_free_points"] = {
                "type": "int",
                "description": f"{desc} - 免费用户积分消耗",
                "hint": f"免费用户每次{desc}消耗的积分。0 表示免费",
                "default": 0
            }
            
            # 高级会员配置
            schema[f"quota_{action}_premium_limit"] = {
                "type": "int",
                "description": f"{desc} - 高级会员每日限制",
                "hint": f"高级会员每天可以{desc}的次数。-1 表示无限制",
                "default": -1
            }
            schema[f"quota_{action}_premium_points"] = {
                "type": "int",
                "description": f"{desc} - 高级会员积分消耗",
                "hint": f"高级会员每次{desc}消耗的积分。0 表示免费",
                "default": 0
            }
            
            # VIP配置（通常无限制）
            schema[f"quota_{action}_vip_limit"] = {
                "type": "int",
                "description": f"{desc} - VIP每日限制",
                "hint": f"VIP用户每天可以{desc}的次数。-1 表示无限制",
                "default": -1
            }
            schema[f"quota_{action}_vip_points"] = {
                "type": "int",
                "description": f"{desc} - VIP积分消耗",
                "hint": f"VIP用户每次{desc}消耗的积分。0 表示免费",
                "default": 0
            }
        
        return schema
    
    @classmethod
    def get_simple_schema(cls, actions: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        生成简化版配额配置 Schema（只配置免费用户，VIP始终无限制）
        
        适用于大多数插件，减少配置复杂度
        
        Args:
            actions: 操作类型列表
            
        Returns:
            简化版配置 Schema
        """
        schema = {}
        
        for action_info in actions:
            action = action_info['action']
            desc = action_info.get('description', action)
            
            # 只暴露免费用户的限制配置
            schema[f"quota_{action}_daily_limit"] = {
                "type": "int",
                "description": f"{desc}每日次数限制",
                "hint": f"每个用户每天可以{desc}的次数。-1 表示无限制，VIP用户始终无限制",
                "default": -1
            }
            schema[f"quota_{action}_points_cost"] = {
                "type": "int",
                "description": f"{desc}消耗积分",
                "hint": f"每次{desc}消耗的积分数量。0 表示免费，VIP用户始终免费",
                "default": 0
            }
        
        return schema
    
    @classmethod
    def sync_simple_config(
        cls,
        plugin_name: str,
        plugin_config: Dict[str, Any],
        quota_validator,
        actions: List[Dict[str, str]]
    ) -> bool:
        """
        从简化版配置同步配额规则
        
        简化版配置：
        - 免费用户和高级会员使用相同配置
        - VIP 始终无限制、免费
        
        Args:
            plugin_name: 插件名称
            plugin_config: 插件配置
            quota_validator: QuotaValidator 实例
            actions: 操作类型列表
            
        Returns:
            是否同步成功
        """
        if not quota_validator:
            logger.warning(f"[PluginQuotaConfig] {plugin_name}: QuotaValidator 未初始化，跳过配额同步")
            return False
        
        try:
            rules = []
            
            for action_info in actions:
                action = action_info['action']
                action_type = action_info['action_type']
                description = action_info.get('description', '')
                
                # 从简化配置中读取
                daily_limit = plugin_config.get(f"quota_{action}_daily_limit", -1)
                points_cost = plugin_config.get(f"quota_{action}_points_cost", 0)
                
                rule = {
                    'action_type': action_type,
                    'description': description,
                    'free': {'daily_limit': daily_limit, 'points_cost': points_cost},
                    'premium': {'daily_limit': daily_limit, 'points_cost': points_cost},
                    'vip': {'daily_limit': -1, 'points_cost': 0}  # VIP 始终无限制
                }
                
                rules.append(rule)
            
            success = quota_validator.register_quota_rules(
                plugin_name=plugin_name,
                rules=rules,
                override=True
            )
            
            if success:
                logger.info(f"[PluginQuotaConfig] {plugin_name}: 成功同步 {len(rules)} 条配额规则（简化模式）")
            
            return success
            
        except Exception as e:
            logger.error(f"[PluginQuotaConfig] {plugin_name}: 同步配额配置失败: {e}")
            return False


class PluginRateLimitConfig:
    """
    插件限流配置管理器
    
    负责将插件配置中的限流设置同步到 RateLimiter
    """
    
    @classmethod
    def sync_from_config(
        cls,
        plugin_name: str,
        plugin_config: Dict[str, Any],
        actions: List[Dict[str, str]],
        rate_limiter = None
    ) -> bool:
        """
        从插件配置同步限流规则到 RateLimiter
        
        Args:
            plugin_name: 插件名称
            plugin_config: 插件配置字典
            actions: 操作类型列表
            rate_limiter: RateLimiter 实例（可选，默认使用全局实例）
            
        Returns:
            是否同步成功
        """
        try:
            # 获取 RateLimiter 实例
            if rate_limiter is None:
                from .rate_limiter import get_rate_limiter
                rate_limiter = get_rate_limiter()
            
            if not rate_limiter:
                logger.warning(f"[PluginRateLimitConfig] {plugin_name}: RateLimiter 不可用")
                return False
            
            synced_count = 0
            
            for action_info in actions:
                action = action_info['action']
                action_type = action_info['action_type']
                
                # 从配置中读取限流设置
                max_requests = plugin_config.get(f"rate_limit_{action}_max", 60)
                window_seconds = plugin_config.get(f"rate_limit_{action}_window", 60)
                
                # 注册到 RateLimiter
                rate_limiter.register_limit(action_type, max_requests, window_seconds)
                synced_count += 1
                
                logger.debug(f"[PluginRateLimitConfig] {plugin_name}: 注册限流 {action_type} = {max_requests}次/{window_seconds}秒")
            
            logger.info(f"[PluginRateLimitConfig] {plugin_name}: 成功同步 {synced_count} 条限流规则")
            return True
            
        except Exception as e:
            logger.error(f"[PluginRateLimitConfig] {plugin_name}: 同步限流配置失败: {e}")
            return False
    
    @classmethod
    def get_schema(cls, actions: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        生成限流配置 Schema（用于 _conf_schema.json）
        
        Args:
            actions: 操作类型列表
            
        Returns:
            配置 Schema 字典
        """
        schema = {}
        
        for action_info in actions:
            action = action_info['action']
            desc = action_info.get('description', action)
            
            schema[f"rate_limit_{action}_max"] = {
                "type": "int",
                "description": f"{desc} - 限流最大请求数",
                "hint": f"每个用户在时间窗口内最多可以{desc}的次数。防止恶意刷请求",
                "default": 60
            }
            schema[f"rate_limit_{action}_window"] = {
                "type": "int",
                "description": f"{desc} - 限流时间窗口（秒）",
                "hint": f"限流的时间窗口，与最大请求数配合使用。例如：60次/60秒",
                "default": 60
            }
        
        return schema


# ==================== 便捷函数 ====================

def sync_plugin_quota(
    plugin_name: str,
    plugin_config: Dict[str, Any],
    quota_validator,
    actions: List[Dict[str, str]],
    simple_mode: bool = True
) -> bool:
    """
    同步插件配额配置的便捷函数
    
    Args:
        plugin_name: 插件名称
        plugin_config: 插件配置
        quota_validator: QuotaValidator 实例
        actions: 操作类型列表
        simple_mode: 是否使用简化模式（推荐）
        
    Returns:
        是否同步成功
    """
    if simple_mode:
        return PluginQuotaConfig.sync_simple_config(
            plugin_name, plugin_config, quota_validator, actions
        )
    else:
        return PluginQuotaConfig.sync_from_config(
            plugin_name, plugin_config, quota_validator, actions
        )


def sync_plugin_rate_limit(
    plugin_name: str,
    plugin_config: Dict[str, Any],
    actions: List[Dict[str, str]],
    rate_limiter = None
) -> bool:
    """
    同步插件限流配置的便捷函数
    
    Args:
        plugin_name: 插件名称
        plugin_config: 插件配置
        actions: 操作类型列表
        rate_limiter: RateLimiter 实例（可选）
        
    Returns:
        是否同步成功
    """
    return PluginRateLimitConfig.sync_from_config(
        plugin_name, plugin_config, actions, rate_limiter
    )


def sync_plugin_quota_and_rate_limit(
    plugin_name: str,
    plugin_config: Dict[str, Any],
    quota_validator,
    actions: List[Dict[str, str]],
    rate_limiter = None
) -> Tuple[bool, bool]:
    """
    同时同步配额和限流配置的便捷函数
    
    Args:
        plugin_name: 插件名称
        plugin_config: 插件配置
        quota_validator: QuotaValidator 实例
        actions: 操作类型列表
        rate_limiter: RateLimiter 实例（可选）
        
    Returns:
        (配额同步成功, 限流同步成功)
    """
    quota_success = sync_plugin_quota(
        plugin_name, plugin_config, quota_validator, actions
    )
    
    rate_limit_success = sync_plugin_rate_limit(
        plugin_name, plugin_config, actions, rate_limiter
    )
    
    return quota_success, rate_limit_success
