"""
命令处理器装饰器 - 自动停止事件传播

提供 @auto_stop_command 装饰器，用于命令处理函数，自动在函数执行前停止事件传播，
避免命令消息继续传播到 on_message 或 LLM。

使用示例:
    from common.command_handler import auto_stop_command
    
    @filter.command("签")
    @auto_stop_command
    async def checkin_cmd(self, event):
        # 不需要手动调用 event.stop_event()
        yield event.plain_result("消息")
"""
from functools import wraps
from typing import Callable
from astrbot.api.event import AstrMessageEvent


def auto_stop_command(func: Callable):
    """
    命令处理器装饰器 - 自动停止事件传播
    
    专门用于 @filter.command 装饰的命令处理函数。
    在函数执行前就停止事件传播，避免消息继续传播到 on_message 或其他插件。
    
    使用方法:
        @filter.command("签")
        @auto_stop_command
        async def checkin_cmd(self, event):
            # 不需要手动调用 event.stop_event()
            if keyboard:
                yield event.chain_result([Plain(message_text), keyboard])
            else:
                yield event.plain_result(message_text)
    
    特点:
    - 在函数执行前就停止事件传播（比 @auto_stop_event 更早）
    - 适用于命令处理器，避免命令消息被重复处理
    - 支持 async generator 函数
    - 支持直接 return 的函数
    
    Args:
        func: 命令处理函数（async generator 或 async function）
        
    Returns:
        包装后的函数
    """
    import inspect
    
    # 检查是否是 async generator 函数
    if inspect.isasyncgenfunction(func):
        @wraps(func)
        async def wrapper(self, event: AstrMessageEvent, *args, **kwargs):
            # ⭐ 关键：在执行前就停止事件传播
            event.stop_event()
            
            # 执行原函数并 yield 所有结果
            async for result in func(self, event, *args, **kwargs):
                yield result
        
        return wrapper
    
    # 普通 async 函数
    elif inspect.iscoroutinefunction(func):
        @wraps(func)
        async def wrapper(self, event: AstrMessageEvent, *args, **kwargs):
            # ⭐ 关键：在执行前就停止事件传播
            event.stop_event()
            
            # 执行原函数并返回结果
            return await func(self, event, *args, **kwargs)
        
        return wrapper
    
    else:
        # 不是 async 函数，直接返回原函数
        return func
