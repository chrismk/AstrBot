"""
用户ID工具模块
提供统一的用户ID生成和解析功能，解决跨平台用户ID冲突问题

统一ID格式: platform:raw_id
示例:
  - qq:123456789
  - telegram:987654321
  - lark:ou_6f688xxxxx
  - wechat:wxid_xxxxx
"""
from typing import Tuple, Optional
from astrbot.api import logger


def get_unified_user_id(event) -> str:
    """
    从事件中获取统一格式的 user_id
    
    格式: platform:raw_id
    
    Args:
        event: AstrMessageEvent 事件对象
        
    Returns:
        统一格式的用户ID，如 "qq:123456789"
    """
    try:
        platform = event.get_platform_name() or "unknown"
        raw_id = event.get_sender_id() or "anonymous"
        return f"{platform}:{raw_id}"
    except Exception as e:
        logger.warning(f"[UserUtils] 获取统一用户ID失败: {e}")
        return "unknown:anonymous"


def parse_unified_user_id(unified_id: str) -> Tuple[str, str]:
    """
    解析统一格式的用户ID
    
    Args:
        unified_id: 统一格式的用户ID，如 "qq:123456789"
        
    Returns:
        (platform, raw_id) 元组
    """
    if ':' in unified_id:
        parts = unified_id.split(':', 1)
        return (parts[0], parts[1])
    # 兼容旧格式（无平台前缀）
    return ('unknown', unified_id)


def get_platform_from_user_id(unified_id: str) -> str:
    """
    从统一用户ID中提取平台名称
    
    Args:
        unified_id: 统一格式的用户ID
        
    Returns:
        平台名称
    """
    platform, _ = parse_unified_user_id(unified_id)
    return platform


def get_raw_id_from_user_id(unified_id: str) -> str:
    """
    从统一用户ID中提取原始ID
    
    Args:
        unified_id: 统一格式的用户ID
        
    Returns:
        原始用户ID
    """
    _, raw_id = parse_unified_user_id(unified_id)
    return raw_id


def get_display_user_id(unified_id: str, max_length: int = 15) -> str:
    """
    获取用于显示的用户ID（隐藏部分信息）
    
    Args:
        unified_id: 统一格式的用户ID
        max_length: 最大显示长度
        
    Returns:
        截断后的显示ID
    """
    if len(unified_id) <= max_length:
        return unified_id
    return unified_id[:max_length-3] + "..."
