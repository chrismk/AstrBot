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
        results = []
        
        # 收集所有结果
        async for result in func(*args, **kwargs):
            results.append(result)
        
        # 如果有结果，在最后一个结果上设置 stop_event
        if results:
            last_result = results[-1]
            if hasattr(last_result, 'stop_event'):
                last_result.stop_event()
        
        # yield 所有结果
        for result in results:
            yield result
            
        # ⚠️ 关键修复：无论是否有结果（例如 MessageEditor 编辑成功直接 return），
        # 都要尝试在 event 对象上调用 stop_event()
        if len(args) >= 2:
            event = args[1] # 第二个参数通常是 event
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
    回调处理器装饰器（增强版 - 支持 JSON 格式）
    
    自动注册回调路由并提取 action 参数，支持：
    1. 传统字符串格式：prefix:action
    2. JSON 格式：{"action": "...", ...}
    3. 嵌套 JSON 格式：{"action": "callback", "data": "prefix:action"}
    
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
        import json as json_module
        from astrbot.api import logger
        
        def _extract_callback_data(callback_data: str) -> Optional[str]:
            """
            提取回调数据，支持多种格式
            
            Returns:
                如果是本插件的回调，返回实际的回调数据；否则返回 None
            """
            if not callback_data:
                return None
            
            # 1. 检查传统字符串格式：prefix:action
            if callback_data.startswith(f"{prefix}:"):
                return callback_data
            
            # 2. 检查 JSON 格式
            if callback_data.startswith("{") and callback_data.endswith("}"):
                try:
                    json_data = json_module.loads(callback_data)
                    action_type = json_data.get("action", "")
                    
                    # 2.1 处理嵌套格式：{"action": "callback", "data": "prefix:action"}
                    if action_type == "callback":
                        nested_data = json_data.get("data", "")
                        if nested_data and nested_data.startswith(f"{prefix}:"):
                            logger.debug(f"[callback_handler] 提取嵌套回调: {nested_data}")
                            return nested_data
                        else:
                            # 不是本插件的回调
                            return None
                    
                    # 2.2 处理直接 JSON 格式：{"action": "prefix_action", ...}
                    # 检查 action 是否以 prefix_ 开头（如 douban_detail）
                    if action_type.startswith(f"{prefix}_"):
                        logger.debug(f"[callback_handler] 提取 JSON 回调: {callback_data}")
                        return callback_data
                    
                    # 不是本插件的回调
                    return None
                    
                except Exception as e:
                    logger.debug(f"[callback_handler] JSON 解析失败: {e}")
                    return None
            
            # 不是本插件的回调
            return None
        
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
                
                # 提取并检查回调数据（支持多种格式）
                extracted_data = _extract_callback_data(callback_data)
                if not extracted_data:
                    # 不是本插件的回调，直接返回
                    return
                
                # 如果提取的数据与原始数据不同，说明进行了格式转换
                # 需要更新 event.message_str，让插件接收到干净的回调数据
                if extracted_data != callback_data:
                    # 重建消息字符串：/callback extracted_data
                    event.message_str = f"{parts[0]} {extracted_data}"
                    logger.debug(f"[callback_handler] 已转换回调数据: {callback_data} -> {extracted_data}")
                
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
                
                # 提取并检查回调数据（支持多种格式）
                extracted_data = _extract_callback_data(callback_data)
                if not extracted_data:
                    # 不是本插件的回调，直接返回
                    return
                
                # 如果提取的数据与原始数据不同，说明进行了格式转换
                # 需要更新 event.message_str，让插件接收到干净的回调数据
                if extracted_data != callback_data:
                    # 重建消息字符串：/callback extracted_data
                    event.message_str = f"{parts[0]} {extracted_data}"
                    logger.debug(f"[callback_handler] 已转换回调数据: {callback_data} -> {extracted_data}")
                
                # 是本插件的回调，调用原函数
                return await func(self, event, *args, **kwargs)
        
        # 保留回调前缀信息
        wrapper._callback_prefix = prefix
        
        return wrapper
    
    return decorator
