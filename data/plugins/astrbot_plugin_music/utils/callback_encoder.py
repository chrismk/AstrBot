"""回调数据编码器"""

import json
import base64
from typing import Dict, Any, Optional


class CallbackEncoder:
    """
    回调数据编码/解码器
    使用简单的字符串格式，避免base64编码的长度限制
    """
    
    @classmethod
    def encode_detail(cls, platform: str, song_id: str) -> str:
        """
        编码歌曲详情回调数据
        
        Args:
            platform: 音乐平台
            song_id: 歌曲ID
            
        Returns:
            格式: "detail:{platform}:{song_id}"
        """
        return f"detail:{platform}:{song_id}"
    
    @classmethod
    def encode_download(cls, platform: str, song_id: str, quality: str) -> str:
        """
        编码下载回调数据
        
        Args:
            platform: 音乐平台
            song_id: 歌曲ID
            quality: 音质
            
        Returns:
            格式: "download:{platform}:{song_id}:{quality}"
        """
        return f"download:{platform}:{song_id}:{quality}"
    
    @classmethod
    def encode_page(cls, keyword: str, platform: str, page: int) -> str:
        """
        编码翻页回调数据
        
        Args:
            keyword: 搜索关键词
            platform: 音乐平台
            page: 页码
            
        Returns:
            格式: "page:{platform}:{page}:{keyword}"
        """
        # 限制关键词长度，避免超过64字符限制
        max_keyword_len = 64 - len(f"page:{platform}:{page}:") - 5  # 留5字符余量
        if len(keyword) > max_keyword_len:
            keyword = keyword[:max_keyword_len]
        return f"page:{platform}:{page}:{keyword}"
    
    @classmethod
    def encode_lyric(cls, platform: str, song_id: str) -> str:
        """
        编码歌词回调数据
        
        Args:
            platform: 音乐平台
            song_id: 歌曲ID
            
        Returns:
            格式: "lyric:{platform}:{song_id}"
        """
        return f"lyric:{platform}:{song_id}"
    
    @classmethod
    def encode_switch_source(cls, keyword: str, current_platform: str, target_platform: str) -> str:
        """
        编码换源搜索回调数据
        
        Args:
            keyword: 搜索关键词
            current_platform: 当前平台
            target_platform: 目标平台
            
        Returns:
            格式: "switch:{target_platform}:{keyword}"
        """
        # 限制关键词长度，避免超过64字符限制
        max_keyword_len = 64 - len(f"switch:{target_platform}:") - 5  # 留5字符余量
        if len(keyword) > max_keyword_len:
            keyword = keyword[:max_keyword_len]
        return f"switch:{target_platform}:{keyword}"
    
    @classmethod
    def decode(cls, callback_data: str) -> Optional[Dict[str, Any]]:
        """
        解码回调数据
        
        Args:
            callback_data: 回调数据字符串
            
        Returns:
            解码后的数据字典，失败返回None
        """
        try:
            if callback_data.strip().startswith('{'):
                return json.loads(callback_data)
            
            # 处理简单的单词回调（如 "exit"）
            if callback_data == "exit":
                return {"action": "exit"}
            
            # 去掉可能的 music: 前缀（兼容处理）
            if callback_data.startswith("music:"):
                callback_data = callback_data[6:]
                
            parts = callback_data.split(":", 3)  # 最多分割3次
            if len(parts) < 2:
                return None
            
            action = parts[0]
            
            if action == "detail":
                # detail:{platform}:{song_id}
                if len(parts) >= 3:
                    return {
                        "action": "detail",
                        "platform": parts[1],
                        "song_id": parts[2]
                    }
            
            elif action == "download":
                # download:{platform}:{song_id}:{quality}
                if len(parts) >= 4:
                    return {
                        "action": "download",
                        "platform": parts[1],
                        "song_id": parts[2],
                        "quality": parts[3]
                    }
            
            elif action == "page":
                # page:{platform}:{page}:{keyword}
                if len(parts) >= 4:
                    return {
                        "action": "page",
                        "platform": parts[1],
                        "page": int(parts[2]),
                        "keyword": parts[3]
                    }
            
            elif action == "lyric":
                # lyric:{platform}:{song_id}
                if len(parts) >= 3:
                    return {
                        "action": "lyric",
                        "platform": parts[1],
                        "song_id": parts[2]
                    }
            
            elif action == "switch":
                # switch:{target_platform}:{keyword}
                if len(parts) >= 3:
                    return {
                        "action": "switch",
                        "platform": parts[1],  # 统一使用 platform
                        "keyword": parts[2]
                    }
            
            return None
        except Exception as e:
            return None
    
    # 保持向后兼容的方法
    @classmethod
    def encode(cls, data: Dict[str, Any]) -> str:
        """向后兼容的编码方法"""
        action = data.get("action", "")
        
        if action == "detail":
            return cls.encode_detail(
                data.get("platform", "netease"),
                data.get("song_id", "")
            )
        elif action == "download":
            return cls.encode_download(
                data.get("platform", "netease"),
                data.get("song_id", ""),
                data.get("quality", "standard")
            )
        elif action == "page":
            return cls.encode_page(
                data.get("keyword", ""),
                data.get("platform", "netease"),
                data.get("page", 1)
            )
        
        # 默认返回空字符串
        return ""
    
    @classmethod
    def encode_simple(cls, action: str, **kwargs) -> str:
        """
        简化的编码方法
        
        Args:
            action: 操作类型
            **kwargs: 其他参数
            
        Returns:
            编码后的字符串
        """
        data = {"action": action, **kwargs}
        return cls.encode(data)

