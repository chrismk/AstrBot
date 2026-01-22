import base64
import asyncio
import json
import re
import time
import uuid
import astrbot.api.message_components as Comp

from astrbot.api.platform import (
    Platform,
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.api.event import MessageChain
from astrbot.core.platform.astr_message_event import MessageSesion
from .lark_event import LarkMessageEvent
from .card_service import get_card_service
from ...register import register_platform_adapter
from astrbot import logger
import lark_oapi as lark
from lark_oapi.api.im.v1 import *
from lark_oapi.api.contact.v3 import GetUserRequest


@register_platform_adapter(
    "lark", "飞书机器人官方 API 适配器", support_streaming_message=False
)
class LarkPlatformAdapter(Platform):
    def __init__(
        self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue
    ) -> None:
        super().__init__(platform_config, event_queue)

        self.config = platform_config

        self.unique_session = platform_settings["unique_session"]

        self.appid = platform_config["app_id"]
        self.appsecret = platform_config["app_secret"]
        self.domain = platform_config.get("domain", lark.FEISHU_DOMAIN)
        self.bot_name = platform_config.get("lark_bot_name", "astrbot")
        # 私发回复群组列表：在这些群组中收到消息后，私发回复给用户
        self.private_reply_groups = platform_config.get("private_reply_groups", [])

        if not self.bot_name:
            logger.warning("未设置飞书机器人名称，@ 机器人可能得不到回复。")

        async def unified_msg_handler(event: lark.im.v1.P2ImMessageReceiveV1):
            # 检查是否是交互式回调
            if hasattr(event, 'event') and hasattr(event.event, 'action'):
                await self.convert_interactive_msg(event)
            else:
                await self.convert_msg(event)

        def do_unified_msg_event(event: lark.im.v1.P2ImMessageReceiveV1):
            asyncio.create_task(unified_msg_handler(event))

        # 卡片交互回调处理
        def do_card_action_trigger(event):
            """处理卡片交互回调事件"""
            logger.debug(f"[lark-card-action] 收到卡片交互事件: {event}")
            
            # 解析操作类型以返回相应的Toast消息
            toast_message = "操作已处理"
            toast_message_en = "Operation processed"
            toast_type = "info"
            
            try:
                if hasattr(event, 'event') and hasattr(event.event, 'action'):
                    action = event.event.action
                    if hasattr(action, 'value') and action.value:
                        toast_message = "后台正在处理中..."
                        toast_message_en = "Background is processing..."
                        toast_type = "info"
            except Exception as e:
                logger.warning(f"[lark-card-action] 解析操作类型失败: {e}")
            
            # 异步处理实际的业务逻辑（不阻塞回调响应）
            asyncio.create_task(self.convert_card_action_msg(event))
            
            # 立即返回Toast响应
            response = {
                "toast": {
                    "type": toast_type,
                    "content": toast_message,
                    "i18n": {
                        "zh_cn": toast_message,
                        "en_us": toast_message_en
                    }
                }
            }
            
            logger.debug(f"[lark-card-action] 返回回调响应: {response}")
            return response

        self.event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(do_unified_msg_event)
            .register_p2_card_action_trigger(do_card_action_trigger)
            .build()
        )

        self.client = lark.ws.Client(
            app_id=self.appid,
            app_secret=self.appsecret,
            log_level=lark.LogLevel.ERROR,
            domain=self.domain,
            event_handler=self.event_handler,
        )

        self.lark_api = (
            lark.Client.builder().app_id(self.appid).app_secret(self.appsecret).build()
        )
        
        # 初始化卡片服务
        self.card_service = get_card_service(self.appid, self.appsecret)
        
        # 用户昵称缓存 {open_id: (nickname, timestamp)}
        self._user_name_cache: dict[str, tuple[str, float]] = {}
        self._cache_ttl = 3600  # 缓存1小时
    
    async def _get_user_nickname(self, open_id: str) -> str:
        """
        获取用户昵称（带缓存）
        
        Args:
            open_id: 用户的 open_id
            
        Returns:
            用户昵称，获取失败则返回 open_id 前8位
        """
        # 检查缓存
        if open_id in self._user_name_cache:
            nickname, cached_time = self._user_name_cache[open_id]
            if time.time() - cached_time < self._cache_ttl:
                return nickname
        
        # 调用 API 获取用户信息
        try:
            request = (
                GetUserRequest.builder()
                .user_id(open_id)
                .user_id_type("open_id")
                .build()
            )
            response = await self.lark_api.contact.v3.user.aget(request)
            
            if response.success() and response.data and response.data.user:
                user = response.data.user
                # 打印所有可用字段
                logger.info(f"[lark] 用户对象所有字段: {user.__dict__}")
                nickname = user.name or user.en_name or getattr(user, 'nickname', None) or open_id[:8]
                self._user_name_cache[open_id] = (nickname, time.time())
                logger.debug(f"[lark] 获取用户昵称成功: {open_id} -> {nickname}")
                return nickname
            else:
                logger.warning(f"[lark] 获取用户昵称失败: code={response.code}, msg={response.msg}")
        except Exception as e:
            logger.debug(f"[lark] 获取用户昵称异常: {e}")
        
        # 失败时使用 open_id 前8位
        fallback = open_id[:8]
        self._user_name_cache[open_id] = (fallback, time.time())
        return fallback

    async def send_by_session(
        self, session: MessageSesion, message_chain: MessageChain
    ):
        content, msg_type = await LarkMessageEvent._convert_to_lark(message_chain, self.lark_api)
        
        if session.message_type == MessageType.GROUP_MESSAGE:
            id_type = "chat_id"
            if "%" in session.session_id:
                session.session_id = session.session_id.split("%")[1]
        else:
            id_type = "open_id"

        # 发送消息（统一处理）
        request = (
            CreateMessageRequest.builder()
            .receive_id_type(id_type)
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(session.session_id)
                .content(json.dumps(content))
                .msg_type(msg_type)
                .uuid(str(uuid.uuid4()))
                .build()
            )
            .build()
        )

        response = await self.lark_api.im.v1.message.acreate(request)

        if not response.success():
            logger.error(f"发送飞书消息失败({response.code}): {response.msg}")

        await super().send_by_session(session, message_chain)

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="lark",
            description="飞书机器人官方 API 适配器",
            id=self.config.get("id"),
            support_streaming_message=False,
        )

    async def convert_msg(self, event: lark.im.v1.P2ImMessageReceiveV1):
        message = event.event.message
        abm = AstrBotMessage()
        abm.timestamp = int(message.create_time) / 1000
        abm.message = []
        abm.type = (
            MessageType.GROUP_MESSAGE
            if message.chat_type == "group"
            else MessageType.FRIEND_MESSAGE
        )
        if message.chat_type == "group":
            abm.group_id = message.chat_id
        abm.self_id = self.bot_name
        abm.message_str = ""

        at_list = {}
        if message.mentions:
            for m in message.mentions:
                at_list[m.key] = Comp.At(qq=m.id.open_id, name=m.name)
                if m.name == self.bot_name:
                    abm.self_id = m.id.open_id

        content_json_b = json.loads(message.content)

        if message.message_type == "text":
            message_str_raw = content_json_b["text"]  # 带有 @ 的消息
            at_pattern = r"(@_user_\d+)"  # 可以根据需求修改正则
            # at_users = re.findall(at_pattern, message_str_raw)
            # 拆分文本，去掉AT符号部分
            parts = re.split(at_pattern, message_str_raw)
            for i in range(len(parts)):
                s = parts[i].strip()
                if not s:
                    continue
                if s in at_list:
                    abm.message.append(at_list[s])
                else:
                    abm.message.append(Comp.Plain(parts[i].strip()))
        elif message.message_type == "post":
            _ls = []

            content_ls = content_json_b.get("content", [])
            for comp in content_ls:
                if isinstance(comp, list):
                    _ls.extend(comp)
                elif isinstance(comp, dict):
                    _ls.append(comp)
            content_json_b = _ls
        elif message.message_type == "image":
            content_json_b = [
                {"tag": "img", "image_key": content_json_b["image_key"], "style": []}
            ]

        if message.message_type in ("post", "image"):
            for comp in content_json_b:
                if comp["tag"] == "at":
                    abm.message.append(at_list[comp["user_id"]])
                elif comp["tag"] == "text" and comp["text"].strip():
                    abm.message.append(Comp.Plain(comp["text"].strip()))
                elif comp["tag"] == "img":
                    image_key = comp["image_key"]
                    request = (
                        GetMessageResourceRequest.builder()
                        .message_id(message.message_id)
                        .file_key(image_key)
                        .type("image")
                        .build()
                    )
                    response = await self.lark_api.im.v1.message_resource.aget(request)
                    if not response.success():
                        logger.error(f"无法下载飞书图片: {image_key}")
                    image_bytes = response.file.read()
                    image_base64 = base64.b64encode(image_bytes).decode()
                    abm.message.append(Comp.Image.fromBase64(image_base64))

        for comp in abm.message:
            if isinstance(comp, Comp.Plain):
                abm.message_str += comp.text
        abm.message_id = message.message_id
        abm.raw_message = message
        
        # 获取用户昵称
        open_id = event.event.sender.sender_id.open_id
        nickname = await self._get_user_nickname(open_id)
        abm.sender = MessageMember(
            user_id=open_id,
            nickname=nickname,
        )
        # 独立会话
        if not self.unique_session:
            if abm.type == MessageType.GROUP_MESSAGE:
                abm.session_id = abm.group_id
            else:
                abm.session_id = abm.sender.user_id
        else:
            if abm.type == MessageType.GROUP_MESSAGE:
                abm.session_id = f"{abm.sender.user_id}%{abm.group_id}"  # 也保留群组id
            else:
                abm.session_id = abm.sender.user_id

        logger.debug(abm)
        await self.handle_msg(abm)

    async def handle_msg(self, abm: AstrBotMessage):
        event = LarkMessageEvent(
            message_str=abm.message_str,
            message_obj=abm,
            platform_meta=self.meta(),
            session_id=abm.session_id,
            bot=self.lark_api,
        )
        # 注入卡片服务
        event.card_service = self.card_service
        # 注入私发回复群组配置
        event.private_reply_groups = self.private_reply_groups

        self._event_queue.put_nowait(event)

    async def run(self):
        # self.client.start()
        await self.client._connect()
        asyncio.create_task(self.client._ping_loop())  # 启动心跳保持连接

    async def terminate(self):
        await self.client._disconnect()
        logger.info("飞书(Lark) 适配器已被优雅地关闭")

    def get_client(self) -> lark.Client:
        return self.client
    
    async def convert_card_action_msg(self, event):
        """处理飞书卡片交互回调事件（异步版本，用于后台处理）"""
        try:
            # 解析卡片交互回调数据
            if hasattr(event, 'event') and hasattr(event.event, 'action'):
                action = event.event.action
                if hasattr(action, 'value') and action.value:
                    # 将完整的 action.value 作为 JSON 字符串传递给插件处理
                    callback_data = json.dumps(action.value, ensure_ascii=False)
                    
                    logger.debug(f"[lark-card-action] 原始回调数据: {action.value}")
                    logger.debug(f"[lark-card-action] 传递给插件的回调数据: {callback_data}")
                    
                    # 构造特殊的消息字符串，将完整的回调数据传递给插件
                    message_str = f"/callback {callback_data}"
                    
                    # 获取用户和会话信息
                    operator = event.event.operator
                    context = event.event.context
                    
                    # 获取token用于延时更新卡片
                    token = getattr(event.event, 'token', None)
                    
                    # 创建 AstrBotMessage
                    abm = AstrBotMessage()
                    abm.message_str = message_str
                    abm.message = [Comp.Plain(message_str)]  # 创建Plain消息组件
                    abm.raw_message = event  # 原始事件对象
                    abm.type = MessageType.GROUP_MESSAGE if hasattr(context, 'open_chat_id') else MessageType.PRIVATE_MESSAGE
                    
                    # 确保 user_id 不为 None
                    user_id = None
                    open_id = None
                    if hasattr(operator, 'user_id') and operator.user_id:
                        user_id = operator.user_id
                    if hasattr(operator, 'open_id') and operator.open_id:
                        open_id = operator.open_id
                        if not user_id:
                            user_id = open_id
                    if not user_id:
                        user_id = "unknown_user"  # 提供默认值
                    
                    # 获取用户昵称
                    nickname = await self._get_user_nickname(open_id) if open_id else "Unknown"
                    abm.sender = MessageMember(
                        user_id=user_id,
                        nickname=nickname,
                    )
                    abm.group_id = context.open_chat_id if hasattr(context, 'open_chat_id') else None
                    
                    # 确保 session_id 不为 None
                    if hasattr(context, 'open_chat_id') and context.open_chat_id:
                        abm.session_id = context.open_chat_id
                    elif hasattr(operator, 'open_id') and operator.open_id:
                        abm.session_id = operator.open_id
                    else:
                        abm.session_id = user_id  # 使用已经确保不为None的user_id
                    abm.self_id = self.appid  # 机器人ID
                    abm.platform_meta = PlatformMetadata(
                        name="lark",
                        description="飞书平台",
                        id=self.appid,
                    )
                    abm.message_id = context.open_message_id if hasattr(context, 'open_message_id') else str(event.event.token)
                    abm.timestamp = int(time.time())
                    abm.is_wake = True  # 标记为唤醒消息
                    abm.is_at_or_wake_command = True  # 标记为命令消息
                    
                    # 添加飞书特有的token信息用于延时更新卡片
                    if token:
                        abm.lark_card_token = token
                        logger.debug(f"[lark-card-action] 获取到卡片更新token: {token}")
                    
                    logger.debug(f"[lark-card-action] 处理卡片交互回调，传递给插件处理")
                    await self.handle_msg(abm)
                        
        except Exception as e:
            logger.error(f"[lark-card-action] 处理卡片交互回调失败: {e}")

