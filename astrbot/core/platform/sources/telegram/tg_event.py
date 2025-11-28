import os
import re
import asyncio
import telegramify_markdown
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata, MessageType
from astrbot.core.platform import SendMessageResult
from astrbot.api.message_components import (
    Plain,
    Image,
    Reply,
    At,
    File,
    Record,
    Audio,
    InlineKeyboard,
)
from telegram.ext import ExtBot
from telegram import ReactionTypeEmoji, ReactionTypeCustomEmoji
from astrbot.core.utils.io import download_file
from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


class TelegramPlatformEvent(AstrMessageEvent):
    # Telegram 的最大消息长度限制
    MAX_MESSAGE_LENGTH = 4096
    
    @staticmethod
    def _extract_message_info(msg) -> dict:
        """从 Telegram Message 对象中提取信息
        
        Args:
            msg: Telegram Message 对象
            
        Returns:
            dict: 包含消息信息的字典
        """
        if not msg:
            return {}
        
        info = {
            "message_id": str(msg.message_id),
            "date": msg.date.isoformat() if msg.date else None,
            "chat_id": str(msg.chat.id) if msg.chat else None,
        }
        
        # 提取文本
        if msg.text:
            info["text"] = msg.text
        
        # 提取图片信息（取最大尺寸）
        if msg.photo:
            largest_photo = max(msg.photo, key=lambda p: p.file_size or 0)
            info["photo"] = {
                "file_id": largest_photo.file_id,
                "file_unique_id": largest_photo.file_unique_id,
                "file_size": largest_photo.file_size,
                "width": largest_photo.width,
                "height": largest_photo.height,
            }
        
        # 提取文档/文件信息
        if msg.document:
            info["document"] = {
                "file_id": msg.document.file_id,
                "file_unique_id": msg.document.file_unique_id,
                "file_name": msg.document.file_name,
                "file_size": msg.document.file_size,
                "mime_type": msg.document.mime_type,
            }
        
        # 提取音频信息
        if msg.audio:
            info["audio"] = {
                "file_id": msg.audio.file_id,
                "file_unique_id": msg.audio.file_unique_id,
                "file_size": msg.audio.file_size,
                "duration": msg.audio.duration,
                "title": msg.audio.title,
                "performer": msg.audio.performer,
                "mime_type": msg.audio.mime_type,
            }
        
        # 提取语音信息
        if msg.voice:
            info["voice"] = {
                "file_id": msg.voice.file_id,
                "file_unique_id": msg.voice.file_unique_id,
                "file_size": msg.voice.file_size,
                "duration": msg.voice.duration,
                "mime_type": msg.voice.mime_type,
            }
        
        # 提取视频信息
        if msg.video:
            info["video"] = {
                "file_id": msg.video.file_id,
                "file_unique_id": msg.video.file_unique_id,
                "file_size": msg.video.file_size,
                "duration": msg.video.duration,
                "width": msg.video.width,
                "height": msg.video.height,
                "mime_type": msg.video.mime_type,
            }
        
        # 提取贴纸信息
        if msg.sticker:
            info["sticker"] = {
                "file_id": msg.sticker.file_id,
                "file_unique_id": msg.sticker.file_unique_id,
                "type": msg.sticker.type,
                "width": msg.sticker.width,
                "height": msg.sticker.height,
                "emoji": msg.sticker.emoji,
                "set_name": msg.sticker.set_name,
            }
        
        # 提取动画/GIF信息
        if msg.animation:
            info["animation"] = {
                "file_id": msg.animation.file_id,
                "file_unique_id": msg.animation.file_unique_id,
                "file_size": msg.animation.file_size,
                "duration": msg.animation.duration,
                "width": msg.animation.width,
                "height": msg.animation.height,
                "mime_type": msg.animation.mime_type,
            }
        
        return info

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
    ) -> SendMessageResult:
        """发送消息并返回发送结果
        
        Returns:
            SendMessageResult: 统一的发送结果对象
        """
        image_path = None
        result = SendMessageResult(platform="telegram")  # 统一结果对象

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
            for chunk in chunks:
                try:
                    md_text = telegramify_markdown.markdownify(
                        chunk, max_line_length=None, normalize_whitespace=False
                    )
                    msg = await client.send_message(
                        text=md_text, parse_mode="MarkdownV2", reply_markup=keyboard_markup, **payload
                    )
                except Exception as e:
                    logger.warning(
                        f"MarkdownV2 send failed: {e}. Using plain text instead."
                    )
                    msg = await client.send_message(text=chunk, reply_markup=keyboard_markup, **payload)
                if msg:
                    info = cls._extract_message_info(msg)
                    result.message_ids.append(info.get("message_id", ""))
                    result.raw.append(info)
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
            for chunk in chunks:
                try:
                    md_text = telegramify_markdown.markdownify(
                        chunk, max_line_length=None, normalize_whitespace=False
                    )
                    msg = await client.send_message(
                        text=md_text, parse_mode="MarkdownV2", **payload
                    )
                except Exception as e:
                    logger.warning(
                        f"MarkdownV2 send failed: {e}. Using plain text instead."
                    )
                    msg = await client.send_message(text=chunk, **payload)
                if msg:
                    info = cls._extract_message_info(msg)
                    result.message_ids.append(info.get("message_id", ""))
                    result.raw.append(info)
        
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
                        msg = await client.send_message(
                            text=md_text, parse_mode="MarkdownV2", **payload
                        )
                    except Exception as e:
                        logger.warning(
                            f"MarkdownV2 send failed: {e}. Using plain text instead."
                        )
                        msg = await client.send_message(text=chunk, **payload)
                    if msg:
                        info = cls._extract_message_info(msg)
                        result.message_ids.append(info.get("message_id", ""))
                        result.raw.append(info)
            elif isinstance(i, Image):
                image_path = await i.convert_to_file_path()
                caption = getattr(i, "caption", None) or None
                msg = None
                if caption:
                    try:
                        md_caption = telegramify_markdown.markdownify(
                            caption, max_line_length=None, normalize_whitespace=False
                        )
                    except Exception:
                        md_caption = caption
                    if keyboard_markup and not used_keyboard:
                        msg = await client.send_photo(photo=image_path, caption=md_caption, parse_mode="MarkdownV2", reply_markup=keyboard_markup, **payload)
                        used_keyboard = True
                    else:
                        msg = await client.send_photo(photo=image_path, caption=md_caption, parse_mode="MarkdownV2", **payload)
                else:
                    if keyboard_markup and not used_keyboard:
                        msg = await client.send_photo(photo=image_path, reply_markup=keyboard_markup, **payload)
                        used_keyboard = True
                    else:
                        msg = await client.send_photo(photo=image_path, **payload)
                if msg:
                    info = cls._extract_message_info(msg)
                    result.message_ids.append(info.get("message_id", ""))
                    result.raw.append(info)
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
                msg = None
                if caption:
                    try:
                        md_caption = telegramify_markdown.markdownify(
                            caption, max_line_length=None, normalize_whitespace=False
                        )
                    except Exception:
                        md_caption = caption
                    if keyboard_markup and not used_keyboard:
                        msg = await client.send_document(document=document_src, filename=i.name, caption=md_caption, parse_mode="MarkdownV2", reply_markup=keyboard_markup, **payload)
                        used_keyboard = True
                    else:
                        msg = await client.send_document(document=document_src, filename=i.name, caption=md_caption, parse_mode="MarkdownV2", **payload)
                else:
                    if keyboard_markup and not used_keyboard:
                        msg = await client.send_document(document=document_src, filename=i.name, reply_markup=keyboard_markup, **payload)
                        used_keyboard = True
                    else:
                        msg = await client.send_document(document=document_src, filename=i.name, **payload)
                if msg:
                    info = cls._extract_message_info(msg)
                    result.message_ids.append(info.get("message_id", ""))
                    result.raw.append(info)
            elif isinstance(i, Record):
                path = await i.convert_to_file_path()
                msg = await client.send_voice(voice=path, **payload)
                if msg:
                    info = cls._extract_message_info(msg)
                    result.message_ids.append(info.get("message_id", ""))
                    result.raw.append(info)
            elif isinstance(i, Audio):
                # 处理音频组件（带元数据的音乐）
                audio_msg, audio_info = await cls._send_audio_static(client, i, payload, keyboard_markup if not used_keyboard else None)
                if audio_msg:
                    result.message_ids.append(str(audio_msg.message_id))
                    result.raw.append(audio_info)
                if keyboard_markup and not used_keyboard:
                    used_keyboard = True
            elif isinstance(i, InlineKeyboard):
                # InlineKeyboard 已在预处理中处理，跳过
                continue
        
        return result

    async def send(self, message: MessageChain, target: str = None) -> SendMessageResult:
        """发送消息并返回发送结果
        
        Args:
            message: 消息链
            target: 目标用户/群组 ID，如果不指定则发送给当前消息的发送者
        
        Returns:
            SendMessageResult: 统一的发送结果对象，包含消息 ID 和平台特定数据
            
        Example:
            ```python
            # 回复当前用户
            result = await event.send(MessageChain([Plain("Hello")]))
            
            # 发送到指定用户
            result = await event.send(MessageChain([Plain("Hello")]), target="123456789")
            
            print(f"消息 ID: {result.message_id}")
            
            # 获取文件 ID（发送文件/图片/音频后）
            file_id = result.get("document", {}).get("file_id")
            photo_id = result.get("photo", {}).get("file_id")
            audio_id = result.get("audio", {}).get("file_id")
            ```
        """
        # 确定发送目标
        if target:
            chat_id = target
        elif self.get_message_type() == MessageType.GROUP_MESSAGE:
            chat_id = self.message_obj.group_id
        else:
            chat_id = self.get_sender_id()
        
        result = await self.send_with_client(self.client, message, chat_id)
        await super().send(message, target)
        return result

    @classmethod
    async def _send_audio_static(cls, client: ExtBot, audio: Audio, payload: dict, keyboard_markup=None) -> tuple:
        """发送音频文件（带元数据）
        
        Args:
            client: Telegram Bot 客户端
            audio: Audio 组件
            payload: 发送参数
            keyboard_markup: 可选的键盘
            
        Returns:
            tuple: (Message 对象, 提取的信息字典)
        """
        try:
            # 构建发送参数
            send_kwargs = {**payload}
            
            if audio.title:
                send_kwargs["title"] = audio.title
            if audio.performer:
                send_kwargs["performer"] = audio.performer
            if audio.duration and audio.duration > 0:
                send_kwargs["duration"] = audio.duration
            if audio.caption:
                send_kwargs["caption"] = audio.caption
            if keyboard_markup:
                send_kwargs["reply_markup"] = keyboard_markup
            
            msg = None
            
            # 1. 优先使用 file_id（最快）
            if audio.file_id:
                try:
                    msg = await client.send_audio(audio=audio.file_id, **send_kwargs)
                except Exception as e:
                    logger.warning(f"使用 file_id 发送失败: {e}")
            
            # 2. 使用 URL 直接发送（Telegram 服务器下载）
            if not msg:
                file_url = audio.file or audio.url
                if file_url and file_url.startswith("http"):
                    try:
                        # 处理封面
                        thumbnail = audio.thumbnail if audio.thumbnail else None
                        if thumbnail:
                            send_kwargs["thumbnail"] = thumbnail
                        
                        msg = await client.send_audio(audio=file_url, **send_kwargs)
                    except Exception as e:
                        logger.warning(f"使用 URL 发送失败，尝试本地文件: {e}")
            
            # 3. 降级：下载到本地后发送
            if not msg:
                try:
                    file_path = await audio.convert_to_file_path()
                    with open(file_path, "rb") as f:
                        msg = await client.send_audio(audio=f, **send_kwargs)
                except Exception as e:
                    logger.error(f"发送本地音频失败: {e}")
                    return None, {}
            
            # 提取完整信息返回
            if msg:
                info = cls._extract_message_info(msg)
                if msg.audio:
                    logger.info(f"音频发送成功: {msg.audio.title}, file_id: {msg.audio.file_id[:20]}...")
                return msg, info
            
            return None, {}
            
        except Exception as e:
            logger.error(f"发送音频失败: {e}", exc_info=True)
            return None, {}

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

    async def react(self, emoji: str | None, big: bool = False):
        """
        给原消息添加 Telegram 反应：
        - 普通 emoji：传入 '👍'、'😂' 等
        - 自定义表情：传入其 custom_emoji_id（纯数字字符串）
        - 取消本机器人的反应：传入 None 或空字符串
        """
        try:
            # 解析 chat_id（去掉超级群的 "#<thread_id>" 片段）
            if self.get_message_type() == MessageType.GROUP_MESSAGE:
                chat_id = (self.message_obj.group_id or "").split("#")[0]
            else:
                chat_id = self.get_sender_id()

            message_id = int(self.message_obj.message_id)

            # 组装 reaction 参数（必须是 ReactionType 的列表）
            if not emoji:  # 清空本 bot 的反应
                reaction_param = []  # 空列表表示移除本 bot 的反应
            elif emoji.isdigit():  # 自定义表情：传 custom_emoji_id
                reaction_param = [ReactionTypeCustomEmoji(emoji)]
            else:  # 普通 emoji
                reaction_param = [ReactionTypeEmoji(emoji)]

            await self.client.set_message_reaction(
                chat_id=chat_id,
                message_id=message_id,
                reaction=reaction_param,  # 注意是列表
                is_big=big,  # 可选：大动画
            )
        except Exception as e:
            logger.error(f"[Telegram] 添加反应失败: {e}")

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
                    elif isinstance(i, Audio):
                        # 处理音频组件（带元数据的音乐）
                        await self._send_audio_static(self.client, i, payload, None)
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
