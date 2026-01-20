"""日志工具模块"""

import logging
from typing import Optional


class PluginLogger:
    """插件日志管理器"""
    
    def __init__(self, plugin_name: str = "astrbot_plugin_music"):
        self.plugin_name = plugin_name
        self.logger = logging.getLogger(plugin_name)
        
    def info(self, message: str, user_id: Optional[str] = None):
        """记录信息日志"""
        prefix = f"[{user_id}] " if user_id else ""
        self.logger.info(f"{prefix}{message}")
        
    def warning(self, message: str, user_id: Optional[str] = None):
        """记录警告日志"""
        prefix = f"[{user_id}] " if user_id else ""
        self.logger.warning(f"{prefix}{message}")
        
    def error(self, message: str, user_id: Optional[str] = None, exc_info: bool = False):
        """记录错误日志"""
        prefix = f"[{user_id}] " if user_id else ""
        self.logger.error(f"{prefix}{message}", exc_info=exc_info)
        
    def debug(self, message: str, user_id: Optional[str] = None):
        """记录调试日志"""
        prefix = f"[{user_id}] " if user_id else ""
        self.logger.debug(f"{prefix}{message}")

