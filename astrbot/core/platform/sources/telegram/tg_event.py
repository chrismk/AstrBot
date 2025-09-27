import os
import re
import asyncio
import telegramify_markdown
from typing import Optional
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata, MessageType
from astrbot.api.message_components import (
    Plain,
    Image,
    Reply,
    At,
    File,
    Record,
    InlineKeyboard,
)
from telegram.ext import ExtBot
from astrbot.core.utils.io import download_file
from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


class TelegramPlatformEvent(AstrMessageEvent):
    # Telegram 的最大消息长度限制
    MAX_MESSAGE_LENGTH = 4096

    SPLIT_PATTERNS = {
        "paragraph": re.compile(r"\n\n"),
        "line": re.compile(r"\n"),
        "sentence": re.compile(r"[.!?。！？]"),
        "word": re.compile(r"\s"),
    }

    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        client: ExtBot,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client

    @classmethod
    def _split_message(cls, text: str) -> list[str]:
        if len(text) <= cls.MAX_MESSAGE_LENGTH:
            return [text]

        chunks = []
        while text:
            if len(text) <= cls.MAX_MESSAGE_LENGTH:
                chunks.append(text)
                break

            split_point = cls.MAX_MESSAGE_LENGTH
            segment = text[: cls.MAX_MESSAGE_LENGTH]

            for _, pattern in cls.SPLIT_PATTERNS.items():
                if matches := list(pattern.finditer(segment)):
                    last_match = matches[-1]
                    split_point = last_match.end()
                    break

            chunks.append(text[:split_point])
            text = text[split_point:].lstrip()

        return chunks

    @classmethod
    async def send_with_client(
        cls, client: ExtBot, message: MessageChain, user_name: str
    ) -> Optional[int]:
        image_path = None

        has_reply = False
        reply_message_id = None
        at_user_id = None
        for i in message.chain:
            if isinstance(i, Reply):
                has_reply = True
                reply_message_id = i.id
            if isinstance(i, At):
                at_user_id = i.name

        at_flag = False
        message_thread_id = None
        if "#" in user_name:
            # it's a supergroup chat with message_thread_id
            user_name, message_thread_id = user_name.split("#")
        
        # 预处理：收集文本内容和键盘
        text_content = ""
        keyboard_markup = None
        other_components = []
        used_keyboard = False
        
        for i in message.chain:
            if isinstance(i, Plain):
                if at_user_id and not at_flag:
                    text_content += f"@{at_user_id} {i.text}"
                    at_flag = True
                else:
                    text_content += i.text
            elif isinstance(i, InlineKeyboard):
                # 处理内联键盘组件
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                
                keyboard_buttons = []
                for row in i.buttons:
                    row_buttons = []
                    for button in row:
                        if "url" in button:
                            # URL 按钮
                            row_buttons.append(InlineKeyboardButton(
                                text=button["text"],
                                url=button["url"]
                            ))
                        elif "callback_data" in button:
                            # 回调按钮
                            row_buttons.append(InlineKeyboardButton(
                                text=button["text"],
                                callback_data=button["callback_data"]
                            ))
                        else:
                            # 默认回调按钮
                            row_buttons.append(InlineKeyboardButton(
                                text=button["text"],
                                callback_data=button.get("text", "")
                            ))
                    keyboard_buttons.append(row_buttons)
                
                if keyboard_buttons:
                    keyboard_markup = InlineKeyboardMarkup(keyboard_buttons)
            else:
                other_components.append(i)
        
        # 如果有文本内容和键盘，发送带键盘的文本消息
        if text_content and keyboard_markup:
            payload = {
                "chat_id": user_name,
            }
            if has_reply:
                payload["reply_to_message_id"] = reply_message_id
            if message_thread_id:
                payload["message_thread_id"] = message_thread_id
            
            chunks = cls._split_message(text_content)
            last_message_id = None
            for chunk in chunks:
                try:
                    md_text = telegramify_markdown.markdownify(
                        chunk, max_line_length=None, normalize_whitespace=False
                    )
                    msg = await client.send_message(
                        text=md_text, parse_mode="MarkdownV2", reply_markup=keyboard_markup, **payload
                    )
                    last_message_id = msg.message_id
                except Exception as e:
                    logger.warning(
                        f"MarkdownV2 send failed: {e}. Using plain text instead."
                    )
                    msg = await client.send_message(text=chunk, reply_markup=keyboard_markup, **payload)
                    last_message_id = msg.message_id
            used_keyboard = True
        elif text_content:
            # 只有文本内容，没有键盘
            payload = {
                "chat_id": user_name,
            }
            if has_reply:
                payload["reply_to_message_id"] = reply_message_id
            if message_thread_id:
                payload["message_thread_id"] = message_thread_id
            
            chunks = cls._split_message(text_content)
            last_message_id = None
            for chunk in chunks:
                try:
                    md_text = telegramify_markdown.markdownify(
                        chunk, max_line_length=None, normalize_whitespace=False
                    )
                    msg = await client.send_message(
                        text=md_text, parse_mode="MarkdownV2", **payload
                    )
                    last_message_id = msg.message_id
                except Exception as e:
                    logger.warning(
                        f"MarkdownV2 send failed: {e}. Using plain text instead."
                    )
                    msg = await client.send_message(text=chunk, **payload)
                    last_message_id = msg.message_id
        
        # 处理其他组件
        for i in other_components:
            payload = {
                "chat_id": user_name,
            }
            if has_reply:
                payload["reply_to_message_id"] = reply_message_id
            if message_thread_id:
                payload["message_thread_id"] = message_thread_id

            if isinstance(i, Plain):
                if at_user_id and not at_flag:
                    i.text = f"@{at_user_id} {i.text}"
                    at_flag = True
                chunks = cls._split_message(i.text)
                for chunk in chunks:
                    try:
                        md_text = telegramify_markdown.markdownify(
                            chunk, max_line_length=None, normalize_whitespace=False
                        )
                        await client.send_message(
                            text=md_text, parse_mode="MarkdownV2", **payload
                        )
                    except Exception as e:
                        logger.warning(
                            f"MarkdownV2 send failed: {e}. Using plain text instead."
                        )
                        await client.send_message(text=chunk, **payload)
            elif isinstance(i, Image):
                image_path = await i.convert_to_file_path()
                caption = getattr(i, "caption", None) or None
                if caption:
                    try:
                        md_caption = telegramify_markdown.markdownify(
                            caption, max_line_length=None, normalize_whitespace=False
                        )
                    except Exception:
                        md_caption = caption
                    if keyboard_markup and not used_keyboard:
                        await client.send_photo(photo=image_path, caption=md_caption, parse_mode="MarkdownV2", reply_markup=keyboard_markup, **payload)
                        used_keyboard = True
                    else:
                        await client.send_photo(photo=image_path, caption=md_caption, parse_mode="MarkdownV2", **payload)
                else:
                    if keyboard_markup and not used_keyboard:
                        await client.send_photo(photo=image_path, reply_markup=keyboard_markup, **payload)
                        used_keyboard = True
                    else:
                        await client.send_photo(photo=image_path, **payload)
            elif isinstance(i, File):
                # Determine document source priority:
                # 1) explicit telegram file_id:xxxx
                # 2) http/https URL -> download to local path
                # 3) existing local path
                document_src = None
                if i.file and str(i.file).startswith("file_id:"):
                    document_src = str(i.file).split(":", 1)[1]
                elif i.file and str(i.file).startswith("http"):
                    temp_dir = os.path.join(get_astrbot_data_path(), "temp")
                    path = os.path.join(temp_dir, i.name)
                    await download_file(i.file, path)
                    i.file = path
                    document_src = i.file
                else:
                    document_src = i.file
                if not document_src:
                    # fallback to raw value (may be Telegram file_id)
                    raw_value = getattr(i, "file_", None)
                    if raw_value:
                        if str(raw_value).startswith("file_id:"):
                            document_src = str(raw_value).split(":", 1)[1]
                        else:
                            document_src = raw_value
                # optional caption support
                caption = getattr(i, "caption", None) or None
                if caption:
                    try:
                        md_caption = telegramify_markdown.markdownify(
                            caption, max_line_length=None, normalize_whitespace=False
                        )
                    except Exception:
                        md_caption = caption
                    if keyboard_markup and not used_keyboard:
                        await client.send_document(document=document_src, filename=i.name, caption=md_caption, parse_mode="MarkdownV2", reply_markup=keyboard_markup, **payload)
                        used_keyboard = True
                    else:
                        await client.send_document(document=document_src, filename=i.name, caption=md_caption, parse_mode="MarkdownV2", **payload)
                else:
                    if keyboard_markup and not used_keyboard:
                        await client.send_document(document=document_src, filename=i.name, reply_markup=keyboard_markup, **payload)
                        used_keyboard = True
                    else:
                        await client.send_document(document=document_src, filename=i.name, **payload)
            elif isinstance(i, Record):
                path = await i.convert_to_file_path()
                await client.send_voice(voice=path, **payload)
            elif isinstance(i, InlineKeyboard):
                # InlineKeyboard 已在预处理中处理，跳过
                continue
        
        # 返回最后发送的消息ID
        return last_message_id

    async def send(self, message: MessageChain):
        if self.get_message_type() == MessageType.GROUP_MESSAGE:
            message_id = await self.send_with_client(self.client, message, self.message_obj.group_id)
        else:
            message_id = await self.send_with_client(self.client, message, self.get_sender_id())
        
        # 设置消息ID到MessageEventResult
        if hasattr(message, 'message_id'):
            message.message_id = message_id
            
        await super().send(message)

    async def delete_message(self, message_id: int) -> bool:
        """删除一条消息。需要提供目标 message_id。"""
        try:
            if self.get_message_type() == MessageType.GROUP_MESSAGE:
                chat_id = self.message_obj.group_id
            else:
                chat_id = self.get_sender_id()
            await self.client.delete_message(chat_id=chat_id, message_id=message_id)
            return True
        except Exception as e:
            logger.warning(f"Telegram 删除消息失败: {e!s}")
            return False

    async def edit_message(self, message_id: int | None, text: str) -> bool:
        """编辑一条已发送的文本消息内容为 text（MarkdownV2）。"""
        try:
            if self.get_message_type() == MessageType.GROUP_MESSAGE:
                chat_id = self.message_obj.group_id
            else:
                chat_id = self.get_sender_id()

            try:
                md_text = telegramify_markdown.markdownify(
                    text, max_line_length=None, normalize_whitespace=False
                )
            except Exception:
                md_text = text

            await self.client.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=md_text, parse_mode="MarkdownV2"
            )
            return True
        except Exception as e:
            logger.warning(f"Telegram 编辑消息失败: {e!s}")
            return False

    async def send_streaming(self, generator, use_fallback: bool = False):
        message_thread_id = None

        if self.get_message_type() == MessageType.GROUP_MESSAGE:
            user_name = self.message_obj.group_id
        else:
            user_name = self.get_sender_id()

        if "#" in user_name:
            # it's a supergroup chat with message_thread_id
            user_name, message_thread_id = user_name.split("#")
        payload = {
            "chat_id": user_name,
        }
        if message_thread_id:
            payload["reply_to_message_id"] = message_thread_id

        delta = ""
        current_content = ""
        message_id = None
        last_edit_time = 0  # 上次编辑消息的时间
        throttle_interval = 0.6  # 编辑消息的间隔时间 (秒)

        async for chain in generator:
            if isinstance(chain, MessageChain):
                if chain.type == "break":
                    # 分割符
                    message_id = None  # 重置消息 ID
                    delta = ""  # 重置 delta
                    continue

                # 处理消息链中的每个组件
                for i in chain.chain:
                    if isinstance(i, Plain):
                        delta += i.text
                    elif isinstance(i, Image):
                        image_path = await i.convert_to_file_path()
                        caption = getattr(i, "caption", None) or None
                        if caption:
                            try:
                                md_caption = telegramify_markdown.markdownify(
                                    caption, max_line_length=None, normalize_whitespace=False
                                )
                            except Exception:
                                md_caption = caption
                            await self.client.send_photo(photo=image_path, caption=md_caption, parse_mode="MarkdownV2", **payload)
                        else:
                            await self.client.send_photo(photo=image_path, **payload)
                        continue
                    elif isinstance(i, File):
                        # Determine document source priority (streaming path):
                        # file_id:xxxx > http(s) download > local path
                        document_src = None
                        if i.file and str(i.file).startswith("file_id:"):
                            document_src = str(i.file).split(":", 1)[1]
                        elif i.file and str(i.file).startswith("http"):
                            temp_dir = os.path.join(get_astrbot_data_path(), "temp")
                            path = os.path.join(temp_dir, i.name)
                            await download_file(i.file, path)
                            i.file = path
                            document_src = i.file
                        else:
                            document_src = i.file
                        if not document_src:
                            raw_value = getattr(i, "file_", None)
                            if raw_value:
                                if str(raw_value).startswith("file_id:"):
                                    document_src = str(raw_value).split(":", 1)[1]
                                else:
                                    document_src = raw_value
                        # optional caption support
                        caption = getattr(i, "caption", None) or None
                        if caption:
                            try:
                                md_caption = telegramify_markdown.markdownify(
                                    caption, max_line_length=None, normalize_whitespace=False
                                )
                            except Exception:
                                md_caption = caption
                            await self.client.send_document(
                                document=document_src, filename=i.name, caption=md_caption, parse_mode="MarkdownV2", **payload
                            )
                        else:
                            await self.client.send_document(
                                document=document_src, filename=i.name, **payload
                            )
                        continue
                    elif isinstance(i, Record):
                        path = await i.convert_to_file_path()
                        await self.client.send_voice(voice=path, **payload)
                        continue
                    elif isinstance(i, InlineKeyboard):
                        # InlineKeyboard 已在预处理中处理，跳过
                        continue
                    else:
                        logger.warning(f"不支持的消息类型: {type(i)}")
                        continue

                # Plain
                if message_id and len(delta) <= self.MAX_MESSAGE_LENGTH:
                    current_time = asyncio.get_event_loop().time()
                    time_since_last_edit = current_time - last_edit_time

                    # 如果距离上次编辑的时间 >= 设定的间隔，等待一段时间
                    if time_since_last_edit >= throttle_interval:
                        # 编辑消息
                        try:
                            await self.client.edit_message_text(
                                text=delta,
                                chat_id=payload["chat_id"],
                                message_id=message_id,
                            )
                            current_content = delta
                        except Exception as e:
                            logger.warning(f"编辑消息失败(streaming): {e!s}")
                        last_edit_time = (
                            asyncio.get_event_loop().time()
                        )  # 更新上次编辑的时间
                else:
                    # delta 长度一般不会大于 4096，因此这里直接发送
                    try:
                        msg = await self.client.send_message(text=delta, **payload)
                        current_content = delta
                    except Exception as e:
                        logger.warning(f"发送消息失败(streaming): {e!s}")
                    message_id = msg.message_id
                    last_edit_time = (
                        asyncio.get_event_loop().time()
                    )  # 记录初始消息发送时间

        try:
            if delta and current_content != delta:
                try:
                    markdown_text = telegramify_markdown.markdownify(
                        delta, max_line_length=None, normalize_whitespace=False
                    )
                    await self.client.edit_message_text(
                        text=markdown_text,
                        chat_id=payload["chat_id"],
                        message_id=message_id,
                        parse_mode="MarkdownV2",
                    )
                except Exception as e:
                    logger.warning(f"Markdown转换失败，使用普通文本: {e!s}")
                    await self.client.edit_message_text(
                        text=delta, chat_id=payload["chat_id"], message_id=message_id
                    )
        except Exception as e:
            logger.warning(f"编辑消息失败(streaming): {e!s}")

        return await super().send_streaming(generator, use_fallback)
