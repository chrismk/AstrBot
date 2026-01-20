"""
飞书平台消息辅助类

解决飞书平台消息ID获取和自动清理的问题，提供统一的消息发送、删除和跟踪功能。

核心功能：
- 发送消息并自动获取消息ID
- 自动删除旧消息（消息清理）
- 会话上下文集成
- 退出时清理消息

使用场景：
1. 会话模式下的消息自动清理
2. 命令响应的消息ID跟踪
3. 退出时的消息清理

使用示例：
    from common import LarkMessageHelper
    
    # 基础用法：发送并跟踪消息
    message_id = await LarkMessageHelper.send_and_track(
        event, 
        "欢迎使用！", 
        session=session,
        auto_cleanup=True
    )
    
    # 退出时清理
    await LarkMessageHelper.cleanup_on_exit(event, session)
    
    # 手动删除
    await LarkMessageHelper.delete_message(event, message_id)

注意事项：
- 仅适用于飞书平台
- 需要 event 是 LarkMessageEvent 实例
- 消息删除有24小时时间限制
"""

from typing import Optional, Dict, Any
from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain


class LarkMessageHelper:
    """飞书平台消息辅助类 - 处理消息ID保存和清理"""
    
    @staticmethod
    def is_lark_event(event) -> bool:
        """
        检查是否是飞书事件
        
        Args:
            event: 事件对象
        
        Returns:
            是否是飞书事件
        """
        try:
            from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent
            return isinstance(event, LarkMessageEvent) and hasattr(event, 'bot')
        except ImportError:
            return False
    
    @staticmethod
    async def send_and_track(
        event,
        message: str,
        session: Optional[Dict[str, Any]] = None,
        auto_cleanup: bool = True,
        msg_type: str = "post",  # 保留参数以兼容旧代码，但不再使用
        session_key: str = "last_message_id"
    ) -> Optional[str]:
        """
        发送飞书消息并跟踪消息ID
        
        Args:
            event: 飞书事件对象
            message: 消息内容
            session: 会话上下文（用于保存消息ID）
            auto_cleanup: 是否自动删除旧消息
            msg_type: 已废弃，保留以兼容旧代码
            session_key: 在session中保存消息ID的键名
        
        Returns:
            消息ID（如果成功），失败返回 None
        
        示例：
            # 发送并自动清理旧消息
            msg_id = await LarkMessageHelper.send_and_track(
                event, "Hello", session, auto_cleanup=True
            )
            
            # 仅发送，不清理
            msg_id = await LarkMessageHelper.send_and_track(
                event, "Hello", auto_cleanup=False
            )
        """
        try:
            # 验证是否是飞书平台
            if not LarkMessageHelper.is_lark_event(event):
                logger.debug("[LarkMessageHelper] 不是有效的飞书事件")
                return None
            
            # 1. 删除旧消息（如果启用自动清理）
            if auto_cleanup and session and session.get(session_key):
                old_msg_id = session[session_key]
                await LarkMessageHelper.delete_message(event, old_msg_id)
                logger.debug(f"[LarkMessageHelper] 已删除旧消息: {old_msg_id}")
            
            # 2. 使用统一的 event.send() 发送消息
            result = await event.send(MessageChain([Plain(message)]))
            
            if result and result.message_id:
                message_id = result.message_id
                
                # 3. 保存消息ID到会话
                if session is not None:
                    session[session_key] = message_id
                    logger.debug(f"[LarkMessageHelper] 消息发送成功，已保存ID: {message_id}")
                
                return message_id
            else:
                logger.warning("[LarkMessageHelper] 消息发送失败：未获取到消息ID")
                return None
            
        except Exception as e:
            logger.error(f"[LarkMessageHelper] 发送失败: {e}", exc_info=True)
            return None
    
    @staticmethod
    async def delete_message(event, message_id: str) -> bool:
        """
        删除飞书消息
        
        Args:
            event: 飞书事件对象
            message_id: 要删除的消息ID
        
        Returns:
            是否删除成功
        
        注意：
            - 飞书消息删除有24小时时间限制
            - 删除失败不会抛出异常，只会记录日志
        """
        try:
            if not message_id:
                return False
            
            if hasattr(event, 'delete_message'):
                await event.delete_message(message_id)
                logger.debug(f"[LarkMessageHelper] 消息删除成功: {message_id}")
                return True
            else:
                logger.warning("[LarkMessageHelper] event 不支持 delete_message 方法")
                return False
                
        except Exception as e:
            logger.debug(f"[LarkMessageHelper] 消息删除失败: {message_id}, error: {e}")
            return False
    
    @staticmethod
    async def cleanup_on_exit(
        event, 
        session: Dict[str, Any],
        session_key: str = "last_message_id"
    ) -> bool:
        """
        退出时清理消息
        
        Args:
            event: 飞书事件对象
            session: 会话上下文
            session_key: 消息ID在session中的键名
        
        Returns:
            是否清理成功
        
        使用场景：
            用户输入 0 退出会话时，清理最后一条消息，保持界面整洁
        
        示例：
            if message in ['0', '退出']:
                await LarkMessageHelper.cleanup_on_exit(event, session)
                session_manager.end_session(session_id)
                return  # 不发送退出消息
        """
        if session and session.get(session_key):
            message_id = session[session_key]
            success = await LarkMessageHelper.delete_message(event, message_id)
            if success:
                # 清除session中的消息ID
                session[session_key] = None
                logger.debug(f"[LarkMessageHelper] 退出清理完成: {message_id}")
            return success
        return False
    
    @staticmethod
    async def send_with_fallback(
        event,
        message: str,
        session: Optional[Dict[str, Any]] = None,
        auto_cleanup: bool = True,
        fallback_yield = None
    ):
        """
        发送消息，失败时降级到普通方式
        
        Args:
            event: 事件对象
            message: 消息内容
            session: 会话上下文
            auto_cleanup: 是否自动清理
            fallback_yield: 降级时的 yield 函数
        
        Returns:
            消息ID（成功）或 None（降级）
        
        使用场景：
            在命令处理器中，优先使用飞书API，失败时降级到普通方式
        
        示例：
            async def my_command(self, event):
                platform = event.get_platform_name()
                
                if platform == "lark":
                    msg_id = await LarkMessageHelper.send_with_fallback(
                        event, message, session, auto_cleanup=True,
                        fallback_yield=lambda: (yield event.plain_result(message))
                    )
                    if msg_id:
                        event.stop_event()
                        return
                else:
                    yield event.plain_result(message)
        """
        # 尝试使用飞书API
        message_id = await LarkMessageHelper.send_and_track(
            event, message, session, auto_cleanup
        )
        
        if message_id:
            return message_id
        
        # 降级到普通方式
        if fallback_yield:
            logger.debug("[LarkMessageHelper] 降级到普通发送方式")
            return fallback_yield()
        
        return None
    
    @staticmethod
    def should_use_lark_helper(event) -> bool:
        """
        判断是否应该使用飞书辅助类
        
        Args:
            event: 事件对象
        
        Returns:
            是否应该使用
        
        使用场景：
            在插件中判断是否需要特殊处理飞书平台
        
        示例：
            if LarkMessageHelper.should_use_lark_helper(event):
                # 使用飞书特殊处理
                await LarkMessageHelper.send_and_track(...)
            else:
                # 使用通用方式
                yield event.plain_result(...)
        """
        platform_name = (event.get_platform_name() or "").lower()
        return platform_name == "lark" and LarkMessageHelper.is_lark_event(event)
