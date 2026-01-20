"""
平台检测工具函数
提供便捷的平台判断和信息获取功能
"""
from typing import Optional
from astrbot.api.event import AstrMessageEvent


def get_platform_name(event: AstrMessageEvent) -> str:
    """
    获取平台名称
    
    Args:
        event: 消息事件对象
        
    Returns:
        平台名称（小写）
    """
    platform_name = (event.get_platform_name() or "").lower()
    return platform_name if platform_name else 'unknown'


def is_telegram(event: AstrMessageEvent) -> bool:
    """
    判断是否是 Telegram 平台
    
    Args:
        event: 消息事件对象
        
    Returns:
        是否是 Telegram 平台
    """
    return get_platform_name(event) == 'telegram'


def is_lark(event: AstrMessageEvent) -> bool:
    """
    判断是否是飞书平台
    
    Args:
        event: 消息事件对象
        
    Returns:
        是否是飞书平台
    """
    return get_platform_name(event) == 'lark'


def is_wechat(event: AstrMessageEvent) -> bool:
    """
    判断是否是微信平台
    
    Args:
        event: 消息事件对象
        
    Returns:
        是否是微信平台
    """
    return get_platform_name(event) == 'wechat'


def is_qq(event: AstrMessageEvent) -> bool:
    """
    判断是否是 QQ 平台
    
    Args:
        event: 消息事件对象
        
    Returns:
        是否是 QQ 平台
    """
    return get_platform_name(event) == 'qq'


def is_discord(event: AstrMessageEvent) -> bool:
    """
    判断是否是 Discord 平台
    
    Args:
        event: 消息事件对象
        
    Returns:
        是否是 Discord 平台
    """
    return get_platform_name(event) == 'discord'


def get_chat_id(event: AstrMessageEvent) -> Optional[str]:
    """
    统一获取聊天 ID
    
    Args:
        event: 消息事件对象
        
    Returns:
        聊天 ID 或 None
    """
    try:
        # 尝试获取群组 ID
        if hasattr(event, 'message_obj') and hasattr(event.message_obj, 'group_id'):
            group_id = event.message_obj.group_id
            if group_id:
                return str(group_id)
        
        # 否则返回发送者 ID
        return event.get_sender_id()
    except Exception:
        return None


def get_message_id(event: AstrMessageEvent) -> Optional[str]:
    """
    统一获取消息 ID
    
    Args:
        event: 消息事件对象
        
    Returns:
        消息 ID 或 None
    """
    try:
        if hasattr(event, 'message_obj') and hasattr(event.message_obj, 'message_id'):
            return str(event.message_obj.message_id)
        return None
    except Exception:
        return None


def get_user_name(event: AstrMessageEvent) -> str:
    """
    统一获取用户名称
    
    Args:
        event: 消息事件对象
        
    Returns:
        用户名称
    """
    try:
        return event.get_sender_name() or "未知用户"
    except Exception:
        return "未知用户"


def get_user_id(event: AstrMessageEvent) -> str:
    """
    统一获取用户 ID（使用统一格式 platform:raw_id）
    
    Args:
        event: 消息事件对象
        
    Returns:
        统一格式的用户 ID，如 "qq:123456789"
    """
    try:
        from .user_utils import get_unified_user_id
        return get_unified_user_id(event)
    except ImportError:
        # 兼容：如果 user_utils 不可用，返回原始ID
        return event.get_sender_id() or "unknown"
    except Exception:
        return "unknown"


def is_group_message(event: AstrMessageEvent) -> bool:
    """
    判断是否是群组消息
    
    Args:
        event: 消息事件对象
        
    Returns:
        是否是群组消息
    """
    try:
        if hasattr(event, 'message_obj') and hasattr(event.message_obj, 'group_id'):
            return event.message_obj.group_id is not None
        return False
    except Exception:
        return False


def is_private_message(event: AstrMessageEvent) -> bool:
    """
    判断是否是私聊消息
    
    Args:
        event: 消息事件对象
        
    Returns:
        是否是私聊消息
    """
    return not is_group_message(event)
