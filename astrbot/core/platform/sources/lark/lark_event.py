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
    async def _convert_to_lark(message: MessageChain, lark_client: lark.Client) -> List:
        ret = []
        _stage = []
        for comp in message.chain:
            if isinstance(comp, Plain):
                _stage.append({"tag": "md", "text": comp.text})
            elif isinstance(comp, At):
                _stage.append({"tag": "at", "user_id": comp.qq, "style": []})
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
                image_key = response.data.image_key
                logger.debug(image_key)
                ret.append(_stage)
                ret.append([{"tag": "img", "image_key": image_key}])
                _stage.clear()
            elif isinstance(comp, InlineKeyboard):
                # 处理内联键盘组件 - 转换为飞书消息卡片
                if comp.buttons:
                    # 创建消息卡片
                    card_elements = []
                    
                    # 添加按钮
                    for row in comp.buttons:
                        for button in row:
                            if "callback_data" in button:
                                # 回调按钮 - 使用交互式按钮
                                card_elements.append({
                                    "tag": "button",
                                    "text": {"tag": "plain_text", "content": button["text"]},
                                    "type": "primary",
                                    "value": {"key": "callback", "value": button["callback_data"]}
                                })
                            elif "url" in button:
                                # URL 按钮 - 使用链接按钮
                                card_elements.append({
                                    "tag": "button",
                                    "text": {"tag": "plain_text", "content": button["text"]},
                                    "type": "default",
                                    "url": button["url"]
                                })
                    
                    if card_elements:
                        # 创建消息卡片
                        card_content = {
                            "config": {"wide_screen_mode": True},
                            "elements": card_elements
                        }
                        
                        ret.append(_stage)
                        ret.append([{"tag": "interactive", "card": card_content}])
                        _stage.clear()
            else:
                logger.warning(f"飞书 暂时不支持消息段: {comp.type}")

        if _stage:
            ret.append(_stage)
        return ret

    async def send(self, message: MessageChain):
        res = await LarkMessageEvent._convert_to_lark(message, self.bot)
        wrapped = {
            "zh_cn": {
                "title": "",
                "content": res,
            }
        }

        # 先发送富文本 Post（文本与图片）
        post_req = (
            ReplyMessageRequest.builder()
            .message_id(self.message_obj.message_id)
            .request_body(
                ReplyMessageRequestBody.builder()
                .content(json.dumps(wrapped))
                .msg_type("post")
                .uuid(str(uuid.uuid4()))
                .reply_in_thread(False)
                .build()
            )
            .build()
        )

        post_resp = await self.bot.im.v1.message.areply(post_req)
        if not post_resp.success():
            logger.error(f"回复飞书消息失败({post_resp.code}): {post_resp.msg}")

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

    async def edit_message(self, message_id: str | None, text: str, keyboard: InlineKeyboard = None) -> bool:
        """编辑消息（支持文本和交互式按钮）。
        若未指定 message_id，默认使用当前上下文的 message_id（通常只能编辑机器人自己发送且平台允许的消息）。"""
        try:
            target_message_id = message_id or self.message_obj.message_id
            
            # 构建消息内容
            content = [[{"tag": "md", "text": text}]]
            
            # 如果有键盘，添加交互式按钮
            if keyboard and keyboard.buttons:
                card_elements = []
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
                
                if card_elements:
                    card_content = {
                        "config": {"wide_screen_mode": True},
                        "elements": card_elements
                    }
                    content.append([{"tag": "interactive", "card": card_content}])
            
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
