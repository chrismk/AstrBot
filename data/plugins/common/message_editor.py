"""
消息编辑辅助类 - 通用跨平台模块
支持跨平台消息编辑、发送和自动清理
"""
from typing import Optional, Any, Dict
from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger
from astrbot.core.message.components import Plain

try:
    from astrbot.core.message.components import InlineKeyboard
except ImportError:
    InlineKeyboard = None


class MessageEditor:
    """消息编辑辅助类 - 统一处理不同平台的消息编辑和清理"""
    
    @staticmethod
    async def edit_or_send(
        event: AstrMessageEvent, 
        message: str, 
        keyboard: Any = None,
        session_context: Optional[Dict] = None,
        auto_cleanup: bool = True
    ):
        """
        尝试编辑消息，如果不支持则发送新消息（会话平台自动清理旧消息）
        
        Args:
            event: 消息事件
            message: 消息文本
            keyboard: InlineKeyboard 对象（可选）
            session_context: 会话上下文字典（用于追踪消息ID）
            auto_cleanup: 是否自动清理旧消息（默认True）
            
        Yields:
            消息结果
            
        Example:
            ```python
            from common.message_editor import MessageEditor
            
            # 基础用法（不清理）
            async for result in MessageEditor.edit_or_send(event, "消息", keyboard):
                yield result
            
            # 高级用法（自动清理旧消息）
            session = {'last_message_id': 'xxx', 'platform_name': 'lark'}
            async for result in MessageEditor.edit_or_send(
                event, "新消息", keyboard, 
                session_context=session,
                auto_cleanup=True
            ):
                yield result
            ```
        """
        platform_name = (event.get_platform_name() or "").lower()
        
        # 导入平台能力检测
        try:
            from .platform_capabilities import get_platform_capabilities
            capabilities = get_platform_capabilities(event, "MessageEditor")
        except:
            capabilities = {'supports_edit_message': False, 'supports_delete_message': False}
        
        try:
            logger.debug(f"[MessageEditor] 平台: {platform_name}, 能力: {capabilities}, auto_cleanup: {auto_cleanup}, has_session: {session_context is not None}")
            
            # 按钮平台：支持消息编辑
            if capabilities.get('supports_edit_message'):
                logger.debug(f"[MessageEditor] 进入编辑消息分支")
                # Telegram 平台
                if platform_name == "telegram":
                    success = await MessageEditor._edit_telegram_message(event, message, keyboard)
                    if success:
                        return
                
                # 飞书平台（卡片更新）
                elif platform_name == "lark":
                    success = await MessageEditor._edit_lark_message(event, message, keyboard)
                    if success:
                        return
            
            # 会话平台：发送新消息 + 自动清理旧消息
            else:
                logger.debug(f"[MessageEditor] 进入会话平台分支")
                # 1. 先删除旧消息（如果启用自动清理且平台支持）
                if auto_cleanup and session_context and capabilities.get('supports_delete_message'):
                    old_message_id = session_context.get('last_message_id')
                    logger.debug(f"[MessageEditor] 旧消息ID: {old_message_id}")
                    if old_message_id:
                        await MessageEditor._delete_message_safe(event, old_message_id, platform_name)
                else:
                    logger.debug(f"[MessageEditor] 跳过删除旧消息: auto_cleanup={auto_cleanup}, has_session={session_context is not None}, supports_delete={capabilities.get('supports_delete_message')}")
                
                # 2. 发送新消息并获取结果
                if keyboard:
                    chain = [Plain(message)]
                    if keyboard is not None:
                        chain.append(keyboard)
                    result = yield event.chain_result(chain)
                else:
                    result = yield event.plain_result(message)
                
                logger.debug(f"[MessageEditor] 发送消息后的result: {result}, 类型: {type(result)}")
                
                # 3. 保存新消息ID到会话上下文
                # 注意：在生成器中，yield返回的result通常是None
                # 真正的消息ID需要从event的结果中获取
                if session_context:
                    message_id = None
                    
                    # 方法1：从result获取
                    if result:
                        if hasattr(result, 'message_id'):
                            message_id = str(result.message_id)
                        elif hasattr(result, 'msg_id'):
                            message_id = str(result.msg_id)
                        elif isinstance(result, dict) and 'message_id' in result:
                            message_id = str(result['message_id'])
                    
                    # 方法2：从event.get_result()获取
                    if not message_id and hasattr(event, 'get_result'):
                        event_result = event.get_result()
                        if event_result and hasattr(event_result, 'message_id'):
                            message_id = str(event_result.message_id)
                    
                    # 方法3：从event.message_obj获取（这是用户消息ID，不是机器人消息ID）
                    # 注意：这个方法获取的是用户发送的消息ID，不适合用于删除机器人消息
                    # if not message_id and hasattr(event, 'message_obj'):
                    #     if hasattr(event.message_obj, 'message_id'):
                    #         message_id = str(event.message_obj.message_id)
                    
                    if message_id:
                        session_context['last_message_id'] = message_id
                        logger.debug(f"[MessageEditor] 已保存消息ID: {message_id}")
                    else:
                        logger.debug(f"[MessageEditor] 无法获取消息ID")
                        logger.debug(f"  - result: {result}")
                        logger.debug(f"  - event.get_result(): {event.get_result() if hasattr(event, 'get_result') else 'N/A'}")
                        logger.debug(f"  - event.message_obj: {event.message_obj if hasattr(event, 'message_obj') else 'N/A'}")
                
                return
            
            # 其他情况：发送新消息（不清理）
            if keyboard:
                chain = [Plain(message)]
                if keyboard is not None:
                    chain.append(keyboard)
                yield event.chain_result(chain)
            else:
                yield event.plain_result(message)
                
        except Exception as e:
            logger.error(f"[MessageEditor] 消息编辑/发送失败: {e}", exc_info=True)
            # 降级到纯文本
            yield event.plain_result(message)
    
    @staticmethod
    async def _edit_telegram_message(event: AstrMessageEvent, message: str, keyboard: Any = None) -> bool:
        """
        编辑 Telegram 消息
        
        Args:
            event: 消息事件
            message: 消息文本
            keyboard: InlineKeyboard 对象（可选）
            
        Returns:
            True 如果编辑成功，False 如果失败
        """
        try:
            from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
            
            if not isinstance(event, TelegramPlatformEvent):
                return False
            
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            
            # 转换键盘格式
            tg_keyboard = None
            if keyboard and hasattr(keyboard, 'buttons') and keyboard.buttons:
                tg_keyboard_buttons = []
                for row in keyboard.buttons:
                    tg_row = [
                        InlineKeyboardButton(text=btn['text'], callback_data=btn.get('callback_data', ''))
                        if 'callback_data' in btn
                        else InlineKeyboardButton(text=btn['text'], url=btn.get('url', ''))
                        for btn in row
                    ]
                    tg_keyboard_buttons.append(tg_row)
                tg_keyboard = InlineKeyboardMarkup(tg_keyboard_buttons)
            
            # 获取消息 ID 和聊天 ID
            msg_id = int(event.message_obj.message_id)
            chat_id = event.message_obj.group_id or event.get_sender_id()
            
            # 编辑消息
            await event.client.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=message,
                reply_markup=tg_keyboard
            )
            
            logger.debug(f"[MessageEditor] Telegram 消息编辑成功 - msg_id={msg_id}")
            return True
            
        except Exception as e:
            logger.warning(f"[MessageEditor] Telegram 消息编辑失败: {e}")
            return False
    
    @staticmethod
    async def _edit_lark_message(event: AstrMessageEvent, message: str, keyboard: Any = None) -> bool:
        """
        编辑飞书消息（卡片更新）
        
        Args:
            event: 消息事件
            message: 消息文本
            keyboard: InlineKeyboard 对象（可选）
            
        Returns:
            True 如果编辑成功，False 如果失败
        """
        try:
            from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent
            from astrbot.core.platform.sources.lark.card_service import get_card_service
            
            if not isinstance(event, LarkMessageEvent):
                return False
            
            # 获取卡片更新token
            card_token = getattr(event.message_obj, 'lark_card_token', None)
            if not card_token:
                logger.warning("[MessageEditor] 缺少飞书卡片更新token")
                return False
            
            # 获取飞书应用配置
            if not hasattr(event, 'bot') or not event.bot:
                logger.warning("[MessageEditor] 无法获取飞书bot对象")
                return False
            
            bot_config = getattr(event.bot, '_config', None) or getattr(event.bot, 'config', None)
            if not bot_config:
                logger.warning("[MessageEditor] 无法获取飞书bot配置")
                return False
            
            app_id = getattr(bot_config, 'app_id', None)
            app_secret = getattr(bot_config, 'app_secret', None)
            
            if not app_id or not app_secret:
                logger.warning(f"[MessageEditor] 飞书配置不完整")
                return False
            
            # 获取卡片服务并更新
            card_service = get_card_service(app_id, app_secret)
            success = await card_service.update_card(card_token, message, keyboard)
            
            if success:
                logger.debug("[MessageEditor] 飞书卡片更新成功")
            else:
                logger.warning("[MessageEditor] 飞书卡片更新失败")
            
            return success
            
        except Exception as e:
            logger.error(f"[MessageEditor] 更新飞书卡片异常: {e}")
            return False
    
    @staticmethod
    async def _delete_message_safe(event: AstrMessageEvent, message_id: str, platform_name: str):
        """
        安全地删除消息（静默失败）
        
        Args:
            event: 消息事件
            message_id: 要删除的消息ID
            platform_name: 平台名称
        """
        try:
            logger.debug(f"[MessageEditor] 尝试删除消息: platform={platform_name}, msg_id={message_id}")
            
            # Telegram 平台
            if platform_name == "telegram":
                await MessageEditor._delete_telegram_message(event, message_id)
            
            # 飞书平台
            elif platform_name == "lark":
                await MessageEditor._delete_lark_message(event, message_id)
            
            # QQ 平台
            elif platform_name == "qq":
                await MessageEditor._delete_qq_message(event, message_id)
            
            # 企业微信平台
            elif platform_name == "wechatwork":
                await MessageEditor._delete_wechatwork_message(event, message_id)
            
            # 钉钉平台
            elif platform_name == "dingtalk":
                await MessageEditor._delete_dingtalk_message(event, message_id)
            
            else:
                logger.debug(f"[MessageEditor] 平台 {platform_name} 不支持消息删除")
                
        except Exception as e:
            # 静默失败，不影响主流程
            logger.debug(f"[MessageEditor] 删除消息失败: {e}")
    
    @staticmethod
    async def _delete_telegram_message(event: AstrMessageEvent, message_id: str):
        """删除 Telegram 消息"""
        try:
            from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
            
            if not isinstance(event, TelegramPlatformEvent):
                return
            
            chat_id = event.message_obj.group_id or event.get_sender_id()
            await event.client.delete_message(chat_id=chat_id, message_id=int(message_id))
            logger.debug(f"[MessageEditor] Telegram 消息删除成功: {message_id}")
            
        except Exception as e:
            logger.debug(f"[MessageEditor] Telegram 消息删除失败: {e}")
    
    @staticmethod
    async def _delete_lark_message(event: AstrMessageEvent, message_id: str):
        """删除飞书消息"""
        try:
            from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent
            
            if not isinstance(event, LarkMessageEvent):
                return
            
            # 飞书删除消息（使用 AstrBot 封装的方法）
            if hasattr(event, 'delete_message') and message_id:
                await event.delete_message(message_id)
                logger.debug(f"[MessageEditor] 飞书消息删除成功: {message_id}")
            
        except Exception as e:
            logger.debug(f"[MessageEditor] 飞书消息删除失败: {e}")
    
    @staticmethod
    async def _delete_qq_message(event: AstrMessageEvent, message_id: str):
        """删除 QQ 消息"""
        try:
            # QQ 删除消息API调用（需要根据实际QQ平台实现）
            # 注意：QQ官方机器人API有2分钟删除时间限制
            logger.debug(f"[MessageEditor] QQ 消息删除: {message_id} (需要实现)")
            
        except Exception as e:
            logger.debug(f"[MessageEditor] QQ 消息删除失败: {e}")
    
    @staticmethod
    async def _delete_wechatwork_message(event: AstrMessageEvent, message_id: str):
        """删除企业微信消息"""
        try:
            # 企业微信删除消息API调用（需要根据实际实现）
            logger.debug(f"[MessageEditor] 企业微信消息删除: {message_id} (需要实现)")
            
        except Exception as e:
            logger.debug(f"[MessageEditor] 企业微信消息删除失败: {e}")
    
    @staticmethod
    async def _delete_dingtalk_message(event: AstrMessageEvent, message_id: str):
        """删除钉钉消息"""
        try:
            # 钉钉删除消息API调用（需要根据实际实现）
            logger.debug(f"[MessageEditor] 钉钉消息删除: {message_id} (需要实现)")
            
        except Exception as e:
            logger.debug(f"[MessageEditor] 钉钉消息删除失败: {e}")
