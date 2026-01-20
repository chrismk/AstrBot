"""File ID 缓存管理器"""

from typing import Optional, Dict, Any
from datetime import datetime

from ..db.database import DatabaseManager
from ..db.models import TelegramFileCache

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class FileCacheManager:
    """Telegram File ID 缓存管理器"""
    
    def __init__(self, db: DatabaseManager, logger_param=None):
        self.db = db
        # logger_param已废弃，使用全局logger
    
    def get_cache(
        self,
        song_id: str,
        platform: str,
        quality: str
    ) -> Optional[TelegramFileCache]:
        """
        获取完整的文件缓存对象
        
        Args:
            song_id: 歌曲ID
            platform: 平台
            quality: 音质
            
        Returns:
            TelegramFileCache对象或None
        """
        cache = self.db.get_file_cache(song_id, platform, quality)
        if cache and cache.is_valid:
            logger.debug(
                f"File ID缓存命中(完整): {song_id}/{platform}/{quality} "
                f"(使用次数: {cache.use_count})"
            )
            return cache
        
        logger.debug(f"File ID缓存未命中(完整): {song_id}/{platform}/{quality}")
        return None

    def get_cached_file_id(
        self,
        song_id: str,
        platform: str,
        quality: str
    ) -> Optional[str]:
        """
        获取缓存的file_id
        
        Args:
            song_id: 歌曲ID
            platform: 平台
            quality: 音质
            
        Returns:
            file_id或None
        """
        cache = self.db.get_file_cache(song_id, platform, quality)
        
        if cache and cache.is_valid:
            logger.debug(
                f"File ID缓存命中: {song_id}/{platform}/{quality} "
                f"(使用次数: {cache.use_count})"
            )
            return cache.file_id
        
        logger.debug(f"File ID缓存未命中: {song_id}/{platform}/{quality}")
        return None
    
    def save_file_id(
        self,
        song_id: str,
        platform: str,
        quality: str,
        file_id: str,
        file_info: Dict[str, Any],
        uploaded_by: str
    ) -> bool:
        """
        保存file_id到缓存
        
        Args:
            song_id: 歌曲ID
            platform: 平台
            quality: 音质
            file_id: Telegram file_id
            file_info: 文件信息字典
            uploaded_by: 上传者用户ID
            
        Returns:
            是否成功
        """
        cache = TelegramFileCache(
            song_id=song_id,
            music_platform=platform,
            quality_level=quality,
            file_id=file_id,
            file_unique_id=file_info.get("file_unique_id"),
            file_size=file_info.get("file_size"),
            file_name=file_info.get("file_name"),
            duration=file_info.get("duration"),
            title=file_info.get("title"),
            performer=file_info.get("performer"),
            caption=file_info.get("caption"),
            mime_type=file_info.get("mime_type"),
            uploaded_by=uploaded_by,
            upload_time=datetime.now(),
            use_count=1,
            is_valid=1
        )
        
        success = self.db.save_file_cache(cache)
        
        if success:
            logger.info(
                f"保存File ID成功: {song_id}/{platform}/{quality} -> {file_id[:20]}..."
            )
        else:
            logger.error(
                f"保存File ID失败: {song_id}/{platform}/{quality}"
            )
        
        return success
    
    def increment_use_count(
        self,
        song_id: str,
        platform: str,
        quality: str
    ) -> bool:
        """
        增加缓存使用次数
        
        Args:
            song_id: 歌曲ID
            platform: 平台
            quality: 音质
            
        Returns:
            是否成功
        """
        return self.db.increment_cache_use_count(song_id, platform, quality)
    
    def mark_invalid(
        self,
        song_id: str,
        platform: str,
        quality: str
    ) -> bool:
        """
        标记file_id失效
        
        Args:
            song_id: 歌曲ID
            platform: 平台
            quality: 音质
            
        Returns:
            是否成功
        """
        logger.warning(
            f"标记File ID失效: {song_id}/{platform}/{quality}"
        )
        return self.db.mark_cache_invalid(song_id, platform, quality)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            统计信息字典
        """
        # TODO: 实现统计逻辑
        return {
            "total_cached": 0,
            "valid_cached": 0,
            "invalid_cached": 0,
        }

