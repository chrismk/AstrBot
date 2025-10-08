import json
import os
import uuid
import base64
import lark_oapi as lark
from io import BytesIO
from typing import List
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain, Image as AstrBotImage, At, File as AstrBotFile, InlineKeyboard
from astrbot.core.utils.io import download_image_by_url
from lark_oapi.api.im.v1 import *
from astrbot import logger
from astrbot.core.utils.astrbot_path import get_astrbot_data_path


class LarkMessageEvent(AstrMessageEvent):
    def __init__(
        self, message_str, message_obj, platform_meta, session_id, bot: lark.Client
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.bot = bot

    @staticmethod
    async def _convert_to_lark(message: MessageChain, lark_client: lark.Client) -> tuple[dict, str]:
        """转换消息链为飞书格式，返回 (message_content, message_type)
        
        Returns:
            tuple: (消息内容, 消息类型)
                - 如果有交互式按钮，返回交互式卡片和 "interactive"
                - 否则返回富文本内容和 "post"
        """
        text_parts = []
        at_parts = []
        images = []
        keyboard = None
        has_files = False
        
        # 分离不同类型的组件
        for comp in message.chain:
            if isinstance(comp, Plain):
                text_parts.append(comp.text)
            elif isinstance(comp, At):
                at_parts.append({"tag": "at", "user_id": comp.qq, "style": []})
            elif isinstance(comp, AstrBotFile):
                # 文件需要单独处理，不能放在卡片中
                has_files = True
            elif isinstance(comp, AstrBotImage):
                file_path = ""
                image_file = None

                if comp.file and comp.file.startswith("file:///"):
                    file_path = comp.file.replace("file:///", "")
                elif comp.file and comp.file.startswith("http"):
                    image_file_path = await download_image_by_url(comp.file)
                    file_path = image_file_path
                elif comp.file and comp.file.startswith("base64://"):
                    base64_str = comp.file.removeprefix("base64://")
                    image_data = base64.b64decode(base64_str)
                    # save as temp file
                    temp_dir = os.path.join(get_astrbot_data_path(), "temp")
                    file_path = os.path.join(temp_dir, f"{uuid.uuid4()}_test.jpg")
                    with open(file_path, "wb") as f:
                        f.write(BytesIO(image_data).getvalue())
                else:
                    file_path = comp.file

                if image_file is None:
                    image_file = open(file_path, "rb")

                request = (
                    CreateImageRequest.builder()
                    .request_body(
                        CreateImageRequestBody.builder()
                        .image_type("message")
                        .image(image_file)
                        .build()
                    )
                    .build()
                )
                response = await lark_client.im.v1.image.acreate(request)
                if not response.success():
                    logger.error(f"无法上传飞书图片({response.code}): {response.msg}")
                else:
                    image_key = response.data.image_key
                    logger.debug(image_key)
                    images.append({"tag": "img", "image_key": image_key})
            elif isinstance(comp, InlineKeyboard):
                keyboard = comp
            else:
                logger.warning(f"飞书 暂时不支持消息段: {comp.type}")

        # 如果有交互式按钮，创建交互式卡片
        if keyboard and keyboard.buttons:
            logger.debug(f"[lark] 处理交互式键盘，按钮数量: {len(keyboard.buttons)}")
            card_elements = []
            
            # 添加文本内容（如果有）
            combined_text = "".join(text_parts).strip()
            if combined_text:
                card_elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": combined_text}
                })
            
            # 添加 @ 提及（如果有）
            if at_parts:
                # 在交互式卡片中，@ 需要特殊处理，这里先作为文本显示
                at_text = " ".join([f"@{at['user_id']}" for at in at_parts])
                card_elements.append({
                    "tag": "div", 
                    "text": {"tag": "plain_text", "content": at_text}
                })
            
            # 添加图片（如果有）
            for img in images:
                card_elements.append({
                    "tag": "img",
                    "img_key": img["image_key"],
                    "alt": {"tag": "plain_text", "content": "图片"}
                })
            
            # 添加按钮
            for row_idx, row in enumerate(keyboard.buttons):
                for btn_idx, button in enumerate(row):
                    logger.debug(f"[lark] 处理按钮 [{row_idx}][{btn_idx}]: {button}")
                    if "callback_data" in button:
                        # 回调按钮 - 根据飞书文档，value 字段应该直接包含回调数据
                        button_element = {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": button["text"]},
                            "type": "primary",
                            "value": {
                                "key": button["callback_data"]  # 直接使用 callback_data 作为 key
                            }
                        }
                        logger.debug(f"[lark] 创建回调按钮: {button_element}")
                        card_elements.append(button_element)
                    elif "url" in button:
                        # URL 按钮
                        button_element = {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": button["text"]},
                            "type": "default",
                            "url": button["url"]
                        }
                        logger.debug(f"[lark] 创建URL按钮: {button_element}")
                        card_elements.append(button_element)
            
            # 确保卡片至少有一些内容
            if not card_elements:
                card_elements.append({
                    "tag": "div",
                    "text": {"tag": "plain_text", "content": " "}  # 空内容占位符
                })
            
            # 创建交互式卡片
            card_content = {
                "config": {"wide_screen_mode": True},
                "elements": card_elements
            }
            logger.debug(f"[lark] 最终卡片内容: {json.dumps(card_content, ensure_ascii=False, indent=2)}")
            return card_content, "interactive"
        
        # 否则创建富文本消息
        else:
            content = []
            stage = []
            
            # 添加文本和 @
            for text in text_parts:
                if text.strip():
                    stage.append({"tag": "md", "text": text})
            
            for at in at_parts:
                stage.append(at)
            
            if stage:
                content.append(stage)
            
            # 添加图片
            for img in images:
                content.append([img])
            
            # 如果没有任何内容，添加一个空的文本段
            if not content:
                content.append([{"tag": "md", "text": " "}])  # 发送一个空格避免空消息
            
            wrapped = {
                "zh_cn": {
                    "title": "",
                    "content": content,
                }
            }
            return wrapped, "post"

    async def send(self, message: MessageChain):
        logger.debug(f"[lark] 开始发送消息，消息链长度: {len(message.chain)}")
        for i, comp in enumerate(message.chain):
            logger.debug(f"[lark] 消息组件 [{i}]: {type(comp).__name__} - {comp}")
            
        content, msg_type = await LarkMessageEvent._convert_to_lark(message, self.bot)
        
        logger.debug(f"[lark] 消息类型: {msg_type}")
        logger.debug(f"[lark] 发送内容: {json.dumps(content, ensure_ascii=False, indent=2)}")
        
        # 发送消息（统一处理）
        req = (
            ReplyMessageRequest.builder()
            .message_id(self.message_obj.message_id)
            .request_body(
                ReplyMessageRequestBody.builder()
                .content(json.dumps(content))
                .msg_type(msg_type)
                .uuid(str(uuid.uuid4()))
                .reply_in_thread(False)
                .build()
            )
            .build()
        )

        resp = await self.bot.im.v1.message.areply(req)
        if not resp.success():
            logger.error(f"回复飞书消息失败({resp.code}): {resp.msg}")
        else:
            logger.debug(f"[lark] 消息发送成功，消息ID: {resp.data.message_id if resp.data else 'N/A'}")

        # 针对文件段，逐个上传并发送 file 消息
        for comp in message.chain:
            if isinstance(comp, AstrBotFile):
                try:
                    # 获取可用的文件本地路径或 URL 下载到本地
                    # AstrBot File 提供 get_file(allow_return_url=True)
                    path_or_url = await comp.get_file(allow_return_url=True)

                    # 直传 file_key:xxxx 或 file_id:xxxx（无需上传；两者视为同义，统一映射为 file_key）
                    if isinstance(path_or_url, str) and (path_or_url.startswith("file_key:") or path_or_url.startswith("file_id:")):
                        file_key = path_or_url.split(":", 1)[1]
                        file_msg_req = (
                            ReplyMessageRequest.builder()
                            .message_id(self.message_obj.message_id)
                            .request_body(
                                ReplyMessageRequestBody.builder()
                                .content(json.dumps({"file_key": file_key}))
                                .msg_type("file")
                                .uuid(str(uuid.uuid4()))
                                .reply_in_thread(False)
                                .build()
                            )
                            .build()
                        )
                        file_msg_resp = await self.bot.im.v1.message.areply(file_msg_req)
                        if not file_msg_resp.success():
                            logger.error(f"发送飞书文件消息失败({file_msg_resp.code}): {file_msg_resp.msg}")
                        continue

                    # 确保我们有本地文件句柄
                    _file_handle = None
                    if path_or_url and path_or_url.startswith("http"):
                        # 下载到临时文件后上传
                        from astrbot.core.utils.io import download_file as dl
                        temp_dir = os.path.join(get_astrbot_data_path(), "temp")
                        os.makedirs(temp_dir, exist_ok=True)
                        temp_path = os.path.join(temp_dir, f"{uuid.uuid4()}")
                        await dl(path_or_url, temp_path)
                        _file_handle = open(temp_path, "rb")
                    else:
                        # 直接打开本地文件
                        _file_handle = open(path_or_url, "rb")

                    # 上传文件得到 file_key
                    file_upload_req = (
                        CreateFileRequest.builder()
                        .request_body(
                            CreateFileRequestBody.builder()
                            .file_type("opus")  # 文件类型占位，不影响上传；飞书会自动识别
                            .file_name(comp.name or "file")
                            .file(_file_handle)
                            .build()
                        )
                        .build()
                    )
                    file_resp = await self.bot.im.v1.file.acreate(file_upload_req)
                    if not file_resp.success():
                        logger.error(f"上传飞书文件失败({file_resp.code}): {file_resp.msg}")
                        if _file_handle:
                            _file_handle.close()
                        continue

                    file_key = file_resp.data.file_key
                    if _file_handle:
                        _file_handle.close()

                    # 发送 file 消息（回复）
                    file_msg_req = (
                        ReplyMessageRequest.builder()
                        .message_id(self.message_obj.message_id)
                        .request_body(
                            ReplyMessageRequestBody.builder()
                            .content(json.dumps({"file_key": file_key}))
                            .msg_type("file")
                            .uuid(str(uuid.uuid4()))
                            .reply_in_thread(False)
                            .build()
                        )
                        .build()
                    )
                    file_msg_resp = await self.bot.im.v1.message.areply(file_msg_req)
                    if not file_msg_resp.success():
                        logger.error(f"发送飞书文件消息失败({file_msg_resp.code}): {file_msg_resp.msg}")
                except Exception as e:
                    logger.error(f"发送飞书文件消息异常: {e}")

        await super().send(message)

    async def delete_message(self, message_id: str | None = None) -> bool:
        """删除（撤回）一条消息。飞书删除需要 original message_id。默认撤回当前被回复的消息。"""
        try:
            target_message_id = message_id or self.message_obj.message_id
            req = (
                DeleteMessageRequest.builder()
                .message_id(target_message_id)
                .build()
            )
            resp = await self.bot.im.v1.message.adelete(req)
            return bool(resp and resp.success())
        except Exception as e:
            logger.error(f"飞书删除消息失败: {e}")
            return False

    async def react(self, emoji: str):
        request = (
            CreateMessageReactionRequest.builder()
            .message_id(self.message_obj.message_id)
            .request_body(
                CreateMessageReactionRequestBody.builder()
                .reaction_type(Emoji.builder().emoji_type(emoji).build())
                .build()
            )
            .build()
        )
        response = await self.bot.im.v1.message_reaction.acreate(request)
        if not response.success():
            logger.error(f"发送飞书表情回应失败({response.code}): {response.msg}")
            return None

    async def edit_message(self, message_id: str | None, text: str, keyboard: InlineKeyboard = None) -> bool:
        """编辑消息（支持文本和交互式按钮）。
        若未指定 message_id，默认使用当前上下文的 message_id（通常只能编辑机器人自己发送且平台允许的消息）。
        注意：飞书不支持在同一消息中混合文本和交互式按钮，如果有键盘则只能编辑为交互式卡片。"""
        try:
            target_message_id = message_id or self.message_obj.message_id
            
            if keyboard and keyboard.buttons:
                # 如果有键盘，创建交互式卡片
                card_elements = []
                
                # 添加文本元素（如果有）
                if text.strip():
                    card_elements.append({
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": text}
                    })
                
                # 添加按钮
                for row in keyboard.buttons:
                    for button in row:
                        if "callback_data" in button:
                            card_elements.append({
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": button["text"]},
                                "type": "primary",
                                "value": {"key": "callback", "value": button["callback_data"]}
                            })
                        elif "url" in button:
                            card_elements.append({
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": button["text"]},
                                "type": "default",
                                "url": button["url"]
                            })
                
                card_content = {
                    "config": {"wide_screen_mode": True},
                    "elements": card_elements
                }
                
                req = (
                    UpdateMessageRequest.builder()
                    .message_id(target_message_id)
                    .request_body(
                        UpdateMessageRequestBody.builder()
                        .content(json.dumps(card_content))
                        .msg_type("interactive")
                        .build()
                    )
                    .build()
                )
            else:
                # 纯文本消息
                content = [[{"tag": "md", "text": text}]]
                wrapped = {
                    "zh_cn": {
                        "title": "",
                        "content": content,
                    }
                }
                
                req = (
                    UpdateMessageRequest.builder()
                    .message_id(target_message_id)
                    .request_body(
                        UpdateMessageRequestBody.builder()
                        .content(json.dumps(wrapped))
                        .msg_type("post")
                        .build()
                    )
                    .build()
                )
            
            resp = await self.bot.im.v1.message.aupdate(req)
            return bool(resp and resp.success())
        except Exception as e:
            logger.error(f"飞书编辑消息失败: {e}")
            return False

    async def send_streaming(self, generator, use_fallback: bool = False):
        buffer = None
        async for chain in generator:
            if not buffer:
                buffer = chain
            else:
                buffer.chain.extend(chain.chain)
        if not buffer:
            return
        buffer.squash_plain()
        await self.send(buffer)
        return await super().send_streaming(generator, use_fallback)
