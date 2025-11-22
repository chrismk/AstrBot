"""
回调路由器 - 优化插件回调处理性能
"""
from typing import Dict, Callable, Optional, Any


def auto_stop_event(func: Callable) -> Callable:
    """
    自动停止事件传播的装饰器
    
    用于 async generator 函数，自动在最后一个 yield 的结果上调用 .stop_event()
    
    使用示例:
        @auto_stop_event
        async def handle_callback(self, event, data=""):
            yield event.plain_result("...")
            # 不需要手动调用 event.stop_event()
    """
    import functools
    import inspect
    
    if not inspect.isasyncgenfunction(func):
        # 如果不是 async generator，直接返回原函数
        return func
    
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        last_result = None
        has_yielded = False
        
        async for result in func(*args, **kwargs):
            has_yielded = True
            last_result = result
            yield result
        
        # 如果有 yield 过结果，在函数结束时调用 stop_event
        if has_yielded and len(args) >= 2:
            event = args[1]  # 第二个参数通常是 event
            if hasattr(event, 'stop_event'):
                event.stop_event()
    
    return wrapper


class CallbackRouter:
    """
    回调路由器
    
    用于优化插件回调处理，避免所有插件都接收所有回调消息。
    插件可以注册自己的回调前缀，框架会直接路由到对应的处理器。
    """
    
    # 全局路由表 {prefix: handler_function}
    _routes: Dict[str, Callable] = {}
    
    # 插件实例映射 {prefix: plugin_instance}
    _plugin_instances: Dict[str, Any] = {}
    
    @classmethod
    def register(cls, prefix: str, handler: Callable, plugin_instance: Any = None):
        """
        注册回调处理器
        
        Args:
            prefix: 回调前缀（如 "checkin", "douban"）
            handler: 处理函数
            plugin_instance: 插件实例（可选）
        """
        from astrbot.api import logger
        
        if prefix in cls._routes:
            logger.warning(f"[CallbackRouter] 回调前缀 '{prefix}' 已被注册，将被覆盖")
        
        cls._routes[prefix] = handler
        if plugin_instance:
            cls._plugin_instances[prefix] = plugin_instance
        
        logger.info(f"[CallbackRouter] 注册回调路由: {prefix} -> {handler.__name__}")
    
    @classmethod
    def unregister(cls, prefix: str):
        """
        注销回调处理器
        
        Args:
            prefix: 回调前缀
        """
        from astrbot.api import logger
        
        if prefix in cls._routes:
            del cls._routes[prefix]
            logger.info(f"[CallbackRouter] 注销回调路由: {prefix}")
        
        if prefix in cls._plugin_instances:
            del cls._plugin_instances[prefix]
    
    @classmethod
    def get_handler(cls, callback_data: str) -> Optional[Callable]:
        """
        获取回调处理器
        
        Args:
            callback_data: 回调数据（如 "checkin:home"）
            
        Returns:
            处理函数，如果没有找到则返回 None
        """
        if not callback_data or ":" not in callback_data:
            return None
        
        prefix = callback_data.split(":", 1)[0]
        return cls._routes.get(prefix)
    
    @classmethod
    def get_plugin_instance(cls, prefix: str) -> Optional[Any]:
        """
        获取插件实例
        
        Args:
            prefix: 回调前缀
            
        Returns:
            插件实例，如果没有找到则返回 None
        """
        return cls._plugin_instances.get(prefix)
    
    @classmethod
    def extract_action(cls, callback_data: str) -> Optional[str]:
        """
        提取回调动作（去掉前缀）
        
        Args:
            callback_data: 回调数据（如 "checkin:home"）
            
        Returns:
            动作字符串（如 "home"），如果格式不正确则返回 None
        """
        if not callback_data or ":" not in callback_data:
            return None
        
        parts = callback_data.split(":", 1)
        return parts[1] if len(parts) > 1 else None
    
    @classmethod
    def list_routes(cls) -> Dict[str, str]:
        """
        列出所有注册的路由
        
        Returns:
            {prefix: handler_name} 字典
        """
        return {prefix: handler.__name__ for prefix, handler in cls._routes.items()}
    
    @classmethod
    def clear(cls):
        """清空所有路由（用于测试）"""
        from astrbot.api import logger
        
        cls._routes.clear()
        cls._plugin_instances.clear()
        logger.info("[CallbackRouter] 清空所有回调路由")


def callback_handler(prefix: str):
    """
    回调处理器装饰器
    
    自动注册回调路由并提取 action 参数
    
    使用示例:
        @callback_handler("checkin")
        async def handle_callback(self, event: AstrMessageEvent, action: str):
            if action == "home":
                # 处理返回首页
                pass
    
    Args:
        prefix: 回调前缀
    """
    def decorator(func: Callable) -> Callable:
        import functools
        import inspect
        
        # 检查原函数是否是 async generator
        is_async_gen = inspect.isasyncgenfunction(func)
        
        if is_async_gen:
            # 如果是 async generator，返回 async generator
            @functools.wraps(func)
            async def wrapper(self, event, *args, **kwargs):
                # 从消息中提取回调数据
                raw = event.message_str.strip()
                parts = raw.split(" ", 1)
                if len(parts) < 2:
                    return
                
                callback_data = parts[1].strip()
                
                # 检查前缀（快速过滤，不是本插件的回调直接返回）
                if not callback_data or not callback_data.startswith(f"{prefix}:"):
                    return
                
                # 是本插件的回调，调用原函数并 yield 结果
                async for result in func(self, event, *args, **kwargs):
                    yield result
        else:
            # 如果是普通 async 函数
            @functools.wraps(func)
            async def wrapper(self, event, *args, **kwargs):
                # 从消息中提取回调数据
                raw = event.message_str.strip()
                parts = raw.split(" ", 1)
                if len(parts) < 2:
                    return
                
                callback_data = parts[1].strip()
                
                # 检查前缀（快速过滤，不是本插件的回调直接返回）
                if not callback_data or not callback_data.startswith(f"{prefix}:"):
                    return
                
                # 是本插件的回调，调用原函数
                return await func(self, event, *args, **kwargs)
        
        # 保留回调前缀信息
        wrapper._callback_prefix = prefix
        
        return wrapper
    
    return decorator
