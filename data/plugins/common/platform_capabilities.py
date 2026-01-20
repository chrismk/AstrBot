"""
平台能力检测模块 - 跨平台交互设计

提供统一的平台能力检测功能，避免每个插件重复实现。
"""
from typing import Dict, Optional
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


class PlatformCapabilities:
    """平台能力检测器"""
    
    # 全局缓存
    _cache: Dict[str, dict] = {}
    
    # 平台能力映射（标准配置）
    PLATFORM_FEATURES = {
        # 按钮模式平台
        'telegram': {
            'supports_buttons': True,
            'supports_inline_keyboard': True,
            'supports_edit_message': True,
            'supports_delete_message': True,
            'delete_time_limit': None,  # 无时间限制
            'max_button_per_row': 8,
            'max_caption_length': 1024,
            'platform_name': 'telegram'
        },
        'discord': {
            'supports_buttons': True,
            'supports_inline_keyboard': True,
            'supports_edit_message': True,
            'supports_delete_message': True,
            'delete_time_limit': None,  # 无时间限制
            'max_button_per_row': 5,
            'max_caption_length': 2000,
            'platform_name': 'discord'
        },
        # 会话模式平台（使用文字菜单）
        'lark': {
            'supports_buttons': False,
            'supports_inline_keyboard': False,
            'supports_edit_message': False,
            'supports_delete_message': True,
            'delete_time_limit': 86400,  # 24小时内可删除
            'max_message_length': 2000,
            'platform_name': 'lark'
        },
        'wechat': {
            'supports_buttons': False,
            'supports_inline_keyboard': False,
            'supports_edit_message': False,
            'supports_delete_message': False,  # 微信公众号不支持删除
            'delete_time_limit': None,
            'max_message_length': 2000,
            'platform_name': 'wechat'
        },
        'qq': {
            'supports_buttons': False,
            'supports_inline_keyboard': False,
            'supports_edit_message': False,
            'supports_delete_message': True,
            'delete_time_limit': 120,  # 2分钟内可删除
            'max_message_length': 2000,
            'platform_name': 'qq'
        },
        'wechatwork': {
            'supports_buttons': False,
            'supports_inline_keyboard': False,
            'supports_edit_message': False,
            'supports_delete_message': True,
            'delete_time_limit': 300,  # 5分钟内可删除
            'max_message_length': 2000,
            'platform_name': 'wechatwork'
        },
        'dingtalk': {
            'supports_buttons': False,
            'supports_inline_keyboard': False,
            'supports_edit_message': False,
            'supports_delete_message': True,
            'delete_time_limit': 86400,  # 24小时内可删除
            'max_message_length': 2000,
            'platform_name': 'dingtalk'
        }
    }
    
    # 默认能力（会话模式）
    DEFAULT_CAPABILITIES = {
        'supports_buttons': False,
        'supports_inline_keyboard': False,
        'supports_edit_message': False,
        'supports_delete_message': False,
        'delete_time_limit': None,
        'max_message_length': 2000,
        'platform_name': 'unknown'
    }
    
    @classmethod
    def get(cls, event: AstrMessageEvent, plugin_name: Optional[str] = None) -> dict:
        """
        获取平台能力
        
        Args:
            event: 消息事件对象
            plugin_name: 插件名称（可选，用于日志）
            
        Returns:
            平台能力字典
        """
        platform_name = (event.get_platform_name() or "").lower()
        if not platform_name:
            platform_name = 'unknown'
        
        # 缓存检查
        if platform_name in cls._cache:
            return cls._cache[platform_name]
        
        # 获取平台能力
        capabilities = cls.PLATFORM_FEATURES.get(platform_name, cls.DEFAULT_CAPABILITIES.copy())
        
        # 如果是未知平台，设置正确的平台名称
        if platform_name not in cls.PLATFORM_FEATURES:
            capabilities = cls.DEFAULT_CAPABILITIES.copy()
            capabilities['platform_name'] = platform_name
        
        # 缓存结果
        cls._cache[platform_name] = capabilities
        
        # 日志输出
        log_prefix = f"[{plugin_name}] " if plugin_name else ""
        logger.debug(f"{log_prefix}平台能力检测 - {platform_name}: {capabilities}")
        
        return capabilities
    
    @classmethod
    def supports_buttons(cls, event: AstrMessageEvent) -> bool:
        """
        检查平台是否支持按钮
        
        Args:
            event: 消息事件对象
            
        Returns:
            是否支持按钮
        """
        capabilities = cls.get(event)
        return capabilities.get('supports_buttons', False)
    
    @classmethod
    def supports_edit_message(cls, event: AstrMessageEvent) -> bool:
        """
        检查平台是否支持消息编辑
        
        Args:
            event: 消息事件对象
            
        Returns:
            是否支持消息编辑
        """
        capabilities = cls.get(event)
        return capabilities.get('supports_edit_message', False)
    
    @classmethod
    def get_platform_name(cls, event: AstrMessageEvent) -> str:
        """
        获取平台名称
        
        Args:
            event: 消息事件对象
            
        Returns:
            平台名称
        """
        capabilities = cls.get(event)
        return capabilities.get('platform_name', 'unknown')
    
    @classmethod
    def is_button_mode(cls, event: AstrMessageEvent) -> bool:
        """
        判断是否是按钮模式平台
        
        Args:
            event: 消息事件对象
            
        Returns:
            是否是按钮模式
        """
        return cls.supports_buttons(event)
    
    @classmethod
    def is_session_mode(cls, event: AstrMessageEvent) -> bool:
        """
        判断是否是会话模式平台
        
        Args:
            event: 消息事件对象
            
        Returns:
            是否是会话模式
        """
        return not cls.supports_buttons(event)
    
    @classmethod
    def clear_cache(cls):
        """清空缓存（用于测试或重新加载配置）"""
        cls._cache.clear()
        logger.info("[PlatformCapabilities] 已清空平台能力缓存")
    
    @classmethod
    def register_platform(cls, platform_name: str, capabilities: dict):
        """
        注册自定义平台能力
        
        Args:
            platform_name: 平台名称
            capabilities: 平台能力字典
        """
        cls.PLATFORM_FEATURES[platform_name.lower()] = capabilities
        # 清除该平台的缓存
        if platform_name.lower() in cls._cache:
            del cls._cache[platform_name.lower()]
        logger.info(f"[PlatformCapabilities] 已注册平台能力: {platform_name}")


# 便捷函数
def get_platform_capabilities(event: AstrMessageEvent, plugin_name: Optional[str] = None) -> dict:
    """
    获取平台能力（便捷函数）
    
    Args:
        event: 消息事件对象
        plugin_name: 插件名称（可选，用于日志）
        
    Returns:
        平台能力字典
        
    Example:
        ```python
        from common.platform_capabilities import get_platform_capabilities
        
        capabilities = get_platform_capabilities(event, "MyPlugin")
        if capabilities['supports_buttons']:
            # 使用按钮模式
            pass
        else:
            # 使用会话模式
            pass
        ```
    """
    return PlatformCapabilities.get(event, plugin_name)


def supports_buttons(event: AstrMessageEvent) -> bool:
    """
    检查平台是否支持按钮（便捷函数）
    
    Args:
        event: 消息事件对象
        
    Returns:
        是否支持按钮
    """
    return PlatformCapabilities.supports_buttons(event)


def is_button_mode(event: AstrMessageEvent) -> bool:
    """
    判断是否是按钮模式平台（便捷函数）
    
    Args:
        event: 消息事件对象
        
    Returns:
        是否是按钮模式
    """
    return PlatformCapabilities.is_button_mode(event)


def is_session_mode(event: AstrMessageEvent) -> bool:
    """
    判断是否是会话模式平台（便捷函数）
    
    Args:
        event: 消息事件对象
        
    Returns:
        是否是会话模式
    """
    return PlatformCapabilities.is_session_mode(event)
