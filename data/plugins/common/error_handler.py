"""
统一错误处理模块
提供标准化的错误消息格式和异常处理
"""
from typing import Optional
from astrbot.api import logger


class PluginErrorHandler:
    """统一的插件错误处理器"""
    
    # 错误类型图标映射
    ERROR_ICONS = {
        'network': '🌐',      # 网络错误
        'quota': '⚠️',        # 配额错误
        'timeout': '⏱️',      # 超时错误
        'permission': '🔒',   # 权限错误
        'validation': '❌',   # 验证错误
        'system': '⚙️',       # 系统错误
        'notfound': '🔍',     # 未找到
        'database': '💾',     # 数据库错误
    }
    
    @staticmethod
    def format_error(
        error_type: str, 
        message: str, 
        show_hint: bool = True,
        hint: Optional[str] = None
    ) -> str:
        """
        格式化错误消息
        
        Args:
            error_type: 错误类型 (network/quota/timeout/permission/validation/system/notfound/database)
            message: 错误消息
            show_hint: 是否显示提示
            hint: 自定义提示（如果为None则使用默认提示）
            
        Returns:
            格式化后的错误消息
        """
        icon = PluginErrorHandler.ERROR_ICONS.get(error_type, '❌')
        result = f"{icon} {message}"
        
        if show_hint:
            if hint:
                result += f"\n\n💡 {hint}"
            else:
                # 默认提示
                default_hints = {
                    'network': '请检查网络连接后重试',
                    'quota': '请联系管理员增加配额',
                    'timeout': '请稍后重试',
                    'permission': '请联系管理员获取权限',
                    'validation': '请检查输入格式',
                    'system': '请稍后重试或联系管理员',
                    'notfound': '请检查输入是否正确',
                    'database': '请稍后重试',
                }
                default_hint = default_hints.get(error_type, '请稍后重试')
                result += f"\n\n💡 {default_hint}"
        
        return result
    
    @staticmethod
    def handle_exception(
        e: Exception, 
        context: str = "",
        plugin_name: str = "Plugin"
    ) -> str:
        """
        统一异常处理
        
        Args:
            e: 异常对象
            context: 上下文信息
            plugin_name: 插件名称
            
        Returns:
            用户友好的错误消息
        """
        # 记录详细错误日志
        if context:
            logger.error(f"[{plugin_name}] {context} 异常: {e}", exc_info=True)
        else:
            logger.error(f"[{plugin_name}] 异常: {e}", exc_info=True)
        
        # 根据异常类型返回友好消息
        if isinstance(e, TimeoutError):
            return PluginErrorHandler.format_error('timeout', '请求超时')
        elif isinstance(e, PermissionError):
            return PluginErrorHandler.format_error('permission', '权限不足')
        elif isinstance(e, FileNotFoundError):
            return PluginErrorHandler.format_error('notfound', '文件未找到')
        elif isinstance(e, ValueError):
            return PluginErrorHandler.format_error('validation', '输入值错误')
        elif isinstance(e, ConnectionError):
            return PluginErrorHandler.format_error('network', '网络连接失败')
        else:
            return PluginErrorHandler.format_error('system', '系统错误')
    
    @staticmethod
    def success(message: str, hint: Optional[str] = None) -> str:
        """
        格式化成功消息
        
        Args:
            message: 成功消息
            hint: 可选的提示信息
            
        Returns:
            格式化后的成功消息
        """
        result = f"✅ {message}"
        if hint:
            result += f"\n\n💡 {hint}"
        return result
    
    @staticmethod
    def warning(message: str, hint: Optional[str] = None) -> str:
        """
        格式化警告消息
        
        Args:
            message: 警告消息
            hint: 可选的提示信息
            
        Returns:
            格式化后的警告消息
        """
        result = f"⚠️ {message}"
        if hint:
            result += f"\n\n💡 {hint}"
        return result
    
    @staticmethod
    def info(message: str, icon: str = "ℹ️") -> str:
        """
        格式化信息消息
        
        Args:
            message: 信息消息
            icon: 图标
            
        Returns:
            格式化后的信息消息
        """
        return f"{icon} {message}"
