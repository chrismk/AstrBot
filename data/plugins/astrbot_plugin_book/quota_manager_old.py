"""配额管理器"""

from typing import Optional
from datetime import datetime

from .db.database import BookDatabaseManager
from .db.models import UserBookQuota, BookDownloadHistory

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class BookQuotaExceededError(Exception):
    """配额超限异常"""
    pass


class BookQuotaManager:
    """书籍下载配额管理器"""

    def __init__(self, db: BookDatabaseManager, default_quota: int = 10, vip_multiplier: int = 3):
        self.db = db
        self.default_quota = default_quota
        self.vip_multiplier = vip_multiplier
    
    def get_user_quota(self, user_id: str) -> UserBookQuota:
        """
        获取用户配额，不存在则创建
        """
        quota = self.db.get_user_quota(user_id)
        if not quota:
            quota = self.db.create_default_quota(user_id, self.default_quota)
            logger.info(f"为用户 {user_id} 创建默认书籍配额: {self.default_quota}")
        return quota
    
    def check_quota(self, user_id: str) -> bool:
        """
        检查用户今日配额是否充足
        """
        quota_obj = self.get_user_quota(user_id)
        if not quota_obj:
            return False
            
        # 获取用户配额上限
        daily_limit = quota_obj.daily_quota
        if quota_obj.is_vip:
            daily_limit *= self.vip_multiplier
            
        # 获取今日已使用次数
        today_count = self.db.get_daily_download_count(user_id)
        
        logger.debug(f"用户 {user_id} 今日配额检查: {today_count}/{daily_limit}")
        return today_count < daily_limit
    
    def consume_quota(self, user_id: str, book_ssid: str, book_title: str, 
                     author: str = "", file_format: str = "", file_size: int = 0) -> bool:
        """
        消费配额（记录下载历史）
        """
        if not self.check_quota(user_id):
            raise BookQuotaExceededError("今日下载配额已用完")
        
        # 记录下载历史
        history = BookDownloadHistory(
            user_id=user_id,
            book_ssid=book_ssid,
            book_title=book_title,
            author=author,
            file_format=file_format,
            file_size=file_size,
            download_time=datetime.now()
        )
        
        success = self.db.add_download_history(history)
        if success:
            logger.info(f"用户 {user_id} 下载书籍: {book_title} ({file_format})")
        
        return success
    
    def get_quota_status(self, user_id: str) -> str:
        """
        获取配额状态信息
        """
        quota_obj = self.get_user_quota(user_id)
        daily_limit = quota_obj.daily_quota
        if quota_obj.is_vip:
            daily_limit *= self.vip_multiplier
            
        today_count = self.db.get_daily_download_count(user_id)
        remaining = daily_limit - today_count
        
        status_lines = [
            "📊 今日书籍下载配额",
            f"已使用: {today_count} 次",
            f"剩余: {remaining} 次",
            f"总配额: {daily_limit} 次"
        ]
        
        if quota_obj.is_vip:
            status_lines.append("👑 VIP用户享受3倍配额")
        
        return "\n".join(status_lines)
    
    def set_vip_status(self, user_id: str, is_vip: bool) -> bool:
        """
        设置用户VIP状态（管理员功能）
        """
        # 这里可以添加管理员权限检查
        # 暂时简化实现，实际使用时需要添加权限验证
        try:
            quota_obj = self.get_user_quota(user_id)
            # 这里需要在数据库管理器中添加更新VIP状态的方法
            # 暂时返回True，实际实现时需要完善
            logger.info(f"设置用户 {user_id} VIP状态: {is_vip}")
            return True
        except Exception as e:
            logger.error(f"设置VIP状态失败: {e}")
            return False
