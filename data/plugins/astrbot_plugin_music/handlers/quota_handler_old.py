"""配额查询处理器"""

from ..quota_manager import QuotaManager

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class QuotaHandler:
    """配额查询处理器"""
    
    def __init__(self, quota_mgr: QuotaManager, logger_param=None):
        self.quota_mgr = quota_mgr
        # logger_param已废弃，使用全局logger
    
    def handle_quota_query(self, user_id: str) -> str:
        """
        处理配额查询
        
        Args:
            user_id: 用户ID
            
        Returns:
            配额状态文本
        """
        try:
            status = self.quota_mgr.format_quota_status(user_id)
            logger.debug(f"查询配额")
            return status
        except Exception as e:
            logger.error(f"查询配额失败: {e}", exc_info=True)
            return f"❌ 查询失败: {e}"

