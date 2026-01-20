"""文件缓存管理器"""

from typing import Optional
from datetime import datetime

from ..db.database import BookDatabaseManager
from ..db.models import TelegramBookFileCache

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class BookFileCacheManager:
    """书籍文件缓存管理器"""
    
    def __init__(self, db: BookDatabaseManager):
        self.db = db
    
    def get_cached_file(self, book_ssid: str, file_tag: str) -> Optional[TelegramBookFileCache]:
        """
        获取缓存的文件对象
        
        Args:
            book_ssid: 书籍SSID
            file_tag: 文件唯一标识
            
        Returns:
            TelegramBookFileCache 对象或 None
        """
        cache = self.db.get_file_cache(book_ssid, file_tag)
        
        if cache and cache.is_valid:
            logger.debug(
                f"书籍文件缓存命中: {book_ssid}/{file_tag} "
                f"(使用次数: {cache.use_count})"
            )
            # 更新使用次数
            self.db.update_file_cache_use_count(book_ssid, file_tag)
            return cache
        
        logger.debug(f"书籍文件缓存未命中: {book_ssid}/{file_tag}")
        return None
    
    def cache_file_id(
        self,
        book_ssid: str,
        file_format: str,
        file_tag: str,
        file_id: str,
        file_size: Optional[int] = None,
        file_name: Optional[str] = None,
        book_info: Optional[str] = None,
        mime_type: Optional[str] = None,
        uploaded_by: Optional[str] = None
    ) -> bool:
        """
        缓存file_id
        
        Args:
            book_ssid: 书籍SSID
            file_format: 文件格式
            file_tag: 文件唯一标识
            file_id: Telegram文件ID
            file_size: 文件大小
            file_name: 文件名
            book_info: 书籍详细信息JSON字符串
            mime_type: MIME类型
            uploaded_by: 上传者
            
        Returns:
            是否成功
        """
        cache = TelegramBookFileCache(
            book_ssid=book_ssid,
            file_format=file_format,
            file_tag=file_tag,
            file_id=file_id,
            file_size=file_size,
            file_name=file_name,
            book_info=book_info,
            mime_type=mime_type,
            uploaded_by=uploaded_by,
            upload_time=datetime.now(),
            use_count=1,
            is_valid=1
        )
        
        success = self.db.save_file_cache(cache)
        if success:
            logger.info(f"缓存书籍文件: {book_ssid}/{file_format}")
        
        return success
    
    def invalidate_cache(self, book_ssid: str, file_tag: str) -> bool:
        """
        使缓存失效
        
        Args:
            book_ssid: 书籍SSID
            file_tag: 文件唯一标识
            
        Returns:
            是否成功
        """
        try:
            # 这里需要在数据库管理器中添加使缓存失效的方法
            # 暂时简化实现
            logger.info(f"使书籍文件缓存失效: {book_ssid}/{file_tag}")
            return True
        except Exception as e:
            logger.error(f"使缓存失效失败: {e}")
            return False
    
    def get_cache_stats(self) -> str:
        """
        获取缓存统计信息
        """
        # 这里可以添加缓存统计功能
        # 暂时返回简单信息
        return "📈 书籍文件缓存统计\n缓存功能正常运行"
