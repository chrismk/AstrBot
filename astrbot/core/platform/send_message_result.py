"""统一的消息发送结果数据类

提供跨平台统一的消息发送结果结构，支持获取消息 ID、文件 ID 等信息。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SendMessageResult:
    """消息发送结果
    
    统一的消息发送结果结构，包含消息 ID 和平台特定的数据。
    
    Attributes:
        message_ids: 发送的消息 ID 列表（一次发送可能产生多条消息）
        platform: 平台名称（如 telegram, lark）
        raw: 平台原始返回数据列表，每个元素对应一条发送的消息
        
    Example:
        ```python
        result = await event.send(MessageChain([Plain("Hello")]))
        if result:
            # 获取第一条消息的 ID
            msg_id = result.message_id
            
            # 获取所有消息 ID
            all_ids = result.message_ids
            
            # 获取 Telegram 文件信息
            if result.platform == "telegram":
                file_id = result.get("document", {}).get("file_id")
                
            # 获取飞书文件信息
            if result.platform == "lark":
                file_key = result.get("file_key")
        ```
    """
    
    message_ids: list[str] = field(default_factory=list)
    """发送的消息 ID 列表"""
    
    platform: str = ""
    """平台名称"""
    
    raw: list[dict[str, Any]] = field(default_factory=list)
    """平台原始返回数据列表"""
    
    @property
    def message_id(self) -> str | None:
        """获取第一条消息的 ID（便捷属性）"""
        return self.message_ids[0] if self.message_ids else None
    
    def get(self, key: str, default: Any = None) -> Any:
        """从第一条原始数据中获取指定字段
        
        Args:
            key: 字段名
            default: 默认值
            
        Returns:
            字段值，如果不存在则返回默认值
        """
        if self.raw:
            return self.raw[0].get(key, default)
        return default
    
    def get_all(self, key: str) -> list[Any]:
        """从所有原始数据中获取指定字段
        
        Args:
            key: 字段名
            
        Returns:
            所有消息中该字段的值列表
        """
        return [item.get(key) for item in self.raw if key in item]
    
    def __bool__(self) -> bool:
        """判断是否有发送结果"""
        return bool(self.message_ids)
    
    def __repr__(self) -> str:
        return f"SendMessageResult(platform={self.platform!r}, message_ids={self.message_ids}, raw_count={len(self.raw)})"
