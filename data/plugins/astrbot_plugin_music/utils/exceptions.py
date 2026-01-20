"""自定义异常类"""


class MusicPluginError(Exception):
    """插件基础异常"""
    pass


class MusicAPIError(MusicPluginError):
    """音乐API调用错误"""
    pass


class QuotaExceededError(MusicPluginError):
    """配额超限错误"""
    
    def __init__(self, message: str, quota_type: str = "daily"):
        super().__init__(message)
        self.quota_type = quota_type


class TelegramAPIError(MusicPluginError):
    """Telegram API调用错误"""
    pass


class DatabaseError(MusicPluginError):
    """数据库操作错误"""
    pass


class ConfigError(MusicPluginError):
    """配置错误"""
    pass

