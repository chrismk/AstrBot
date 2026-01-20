"""
统一退出处理器

提供标准化的退出回调处理，支持跨平台消息删除和会话清理。

使用示例：
    from common.exit_handler import ExitHandler
    
    async def _handle_exit_callback(self, event: AstrMessageEvent):
        async for result in ExitHandler.handle_exit(event, self.session_manager):
            yield result
"""

from typing import Optional, AsyncGenerator, Any
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent


class ExitHandler:
    """统一退出处理器"""
    
    @staticmethod
    async def handle_exit(
        event: AstrMessageEvent,
        session_manager = None,
        session_id: str = None,
        delete_message: bool = True,
        silent: bool = True,
        plugin_name: str = None
    ) -> AsyncGenerator[Any, None]:
        """
        统一退出处理逻辑
        
        Args:
            event: 消息事件
            session_manager: 会话管理器实例（可选）
            session_id: 会话ID（可选，默认从event获取）
            delete_message: 是否删除消息
            silent: 是否静默退出（不发送退出提示）
            plugin_name: 插件名称（用于日志）
            
        Yields:
            退出结果（如果非静默模式）
        """
        log_prefix = f"[{plugin_name}] " if plugin_name else "[ExitHandler] "
        
        try:
            # 1. 获取会话ID
            if session_id is None:
                session_id = event.get_session_id()
            
            # 2. 结束会话
            if session_manager is not None:
                try:
                    session_manager.end_session(session_id)
                    logger.debug(f"{log_prefix}会话已结束: {session_id}")
                except Exception as e:
                    logger.warning(f"{log_prefix}结束会话失败: {e}")
            
            # 3. 删除消息（跨平台兼容）
            if delete_message:
                deleted = await ExitHandler._delete_message(event, log_prefix)
                if deleted:
                    logger.debug(f"{log_prefix}消息已删除")
                    # 静默退出，不返回任何消息
                    if silent:
                        return
            
            # 4. 非静默模式或删除失败，发送退出提示
            if not silent:
                yield event.plain_result("✅ 已退出")
                
        except Exception as e:
            logger.error(f"{log_prefix}退出处理失败: {e}")
            if not silent:
                yield event.plain_result("✅ 已退出")
    
    @staticmethod
    async def _delete_message(event: AstrMessageEvent, log_prefix: str = "") -> bool:
        """
        删除消息（跨平台兼容）
        
        Args:
            event: 消息事件
            log_prefix: 日志前缀
            
        Returns:
            是否成功删除
        """
        try:
            platform_name = (event.get_platform_name() or "").lower()
            callback_msg_id = getattr(event.message_obj, 'message_id', None)
            
            if not callback_msg_id:
                logger.debug(f"{log_prefix}无法获取消息ID，跳过删除")
                return False
            
            # Telegram 平台
            if platform_name == "telegram":
                chat_id = getattr(event.message_obj, 'group_id', None) or event.get_sender_id()
                if hasattr(event, 'client') and event.client:
                    await event.client.delete_message(
                        chat_id=chat_id, 
                        message_id=int(callback_msg_id)
                    )
                    return True
            
            # Discord 平台
            elif platform_name == "discord":
                if hasattr(event, 'delete_message'):
                    await event.delete_message(callback_msg_id)
                    return True
            
            # 飞书平台
            elif platform_name == "lark":
                if hasattr(event, 'client') and event.client:
                    try:
                        await event.client.delete_message(message_id=str(callback_msg_id))
                        return True
                    except Exception as e:
                        logger.debug(f"{log_prefix}飞书删除消息失败: {e}")
            
            # QQ 平台（有时间限制）
            elif platform_name in ("qq", "aiocqhttp", "nakuru"):
                if hasattr(event, 'delete_message'):
                    await event.delete_message(callback_msg_id)
                    return True
            
            # 其他平台 - 尝试通用方法
            else:
                if hasattr(event, 'delete_message'):
                    await event.delete_message(callback_msg_id)
                    return True
            
            return False
            
        except Exception as e:
            logger.debug(f"{log_prefix}删除消息失败: {e}")
            return False
    
    @staticmethod
    async def cleanup_and_exit(
        event: AstrMessageEvent,
        session_manager = None,
        cleanup_func = None,
        plugin_name: str = None
    ) -> AsyncGenerator[Any, None]:
        """
        清理资源并退出
        
        Args:
            event: 消息事件
            session_manager: 会话管理器
            cleanup_func: 自定义清理函数（异步）
            plugin_name: 插件名称
            
        Yields:
            退出结果
        """
        log_prefix = f"[{plugin_name}] " if plugin_name else "[ExitHandler] "
        
        # 执行自定义清理
        if cleanup_func:
            try:
                await cleanup_func()
                logger.debug(f"{log_prefix}自定义清理完成")
            except Exception as e:
                logger.warning(f"{log_prefix}自定义清理失败: {e}")
        
        # 执行标准退出
        async for result in ExitHandler.handle_exit(
            event, session_manager, plugin_name=plugin_name
        ):
            yield result


# 便捷函数
async def handle_exit(
    event: AstrMessageEvent,
    session_manager = None,
    plugin_name: str = None,
    silent: bool = True
) -> AsyncGenerator[Any, None]:
    """
    处理退出（便捷函数）
    
    Args:
        event: 消息事件
        session_manager: 会话管理器
        plugin_name: 插件名称
        silent: 是否静默退出
        
    Yields:
        退出结果
        
    Example:
        async def _handle_exit_callback(self, event):
            async for result in handle_exit(event, self.session_manager, "MyPlugin"):
                yield result
    """
    async for result in ExitHandler.handle_exit(
        event, session_manager, plugin_name=plugin_name, silent=silent
    ):
        yield result
