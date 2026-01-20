"""AstrBot 音乐搜索插件"""

import os
import yaml
import json
import re
import aiohttp
from pathlib import Path
from typing import Optional

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import InlineKeyboard, Image, Plain

# 导入通用配额系统
import sys
from pathlib import Path
plugin_root = Path(__file__).parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

try:
    from common.database_manager import DatabaseManager as CommonDatabaseManager
    from common.quota_validator import QuotaValidator
    QUOTA_SYSTEM_AVAILABLE = True
except ImportError:
    QUOTA_SYSTEM_AVAILABLE = False
    logger.warning("[Music] 通用配额系统不可用，将使用插件内置配额管理")


async def is_image_url_valid(url: str) -> bool:
    """检查图片URL是否有效"""
    if not url or not url.startswith("http"):
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=5) as response:
                return response.status == 200 and "image" in response.headers.get(
                    "Content-Type", ""
                )
    except Exception:
        return False


# 内部模块
from .music_api_client import MusicAPIClient
from .db.database import DatabaseManager
from .quota_manager import QuotaManager
from .file_cache_manager import FileCacheManager
from .telegram_bot_api import TelegramBotAPI
from .handlers import SearchHandler, DetailHandler, DownloadHandler, QuotaHandler
from .utils.callback_encoder import CallbackEncoder


@register("music-search", "Chrismk", "音乐搜索插件 - 支持多平台音乐搜索和下载", "1.0.0")
class MusicPlugin(Star):
    """音乐搜索插件主类"""
    
    def __init__(self, context: Context):
        super().__init__(context)
        # 使用AstrBot官方logger
        # self.logger = PluginLogger("astrbot_plugin_music")  # 改用官方logger
        
        # 配置
        self.config = self._load_config()
        
        # 数据库
        config = self.context.get_config()
        data_path = config.get("data_path", "data")
        
        # 将数据库移动到 plugin_data 目录，实现数据与插件分离
        plugin_data_dir = os.path.join(data_path, "plugin_data", "music")
        os.makedirs(plugin_data_dir, exist_ok=True)
        db_path = os.path.join(plugin_data_dir, "music.db")

        self.db = DatabaseManager(db_path, None)
        
        # 音乐API客户端
        self.music_api = MusicAPIClient(
            api_base_url=self.config["music_api"]["base_url"],
            api_key=self.config["music_api"]["api_key"]
        )
        
        # 配额管理器（已废弃，使用通用配额系统）
        # quota_config = self.config.get("quota", {})
        # self.quota_mgr = QuotaManager(
        #     db=self.db,
        #     default_quotas=quota_config.get("default_quotas", {}),
        #     vip_multiplier=quota_config.get("vip_multiplier", 3)
        # )
        self.quota_mgr = None  # 不再使用内置配额管理器
        
        # File ID缓存管理器
        self.cache_mgr = FileCacheManager(self.db, None)
        
        # Telegram Bot API
        telegram_config = self.config.get("telegram", {})
        self.telegram_api = None
        if telegram_config.get("enabled"):
            self.telegram_api = TelegramBotAPI(
                bot_token=telegram_config.get("bot_token", ""),
                api_server=telegram_config.get("api_server")
            )
        
        # 通用配额系统（优先使用）
        self.common_quota_validator = None
        if QUOTA_SYSTEM_AVAILABLE:
            try:
                quota_db_path = os.path.join(data_path, "quota_system.db")
                common_db = CommonDatabaseManager(quota_db_path)
                self.common_quota_validator = QuotaValidator(common_db)
                logger.info("[Music] 通用配额系统初始化完成")
            except Exception as e:
                logger.error(f"[Music] 通用配额系统初始化失败: {e}")
        
        # 处理器（传入通用配额验证器）
        self.search_handler = SearchHandler(self.music_api, self.db, None)
        self.detail_handler = DetailHandler(self.music_api, self.db, None)
        self.download_handler = DownloadHandler(
            self.music_api, self.db, None,  # quota_mgr 设为 None
            self.cache_mgr, self.telegram_api, None,
            common_quota_validator=self.common_quota_validator  # 只使用通用配额验证器
        )
        # self.quota_handler = QuotaHandler(self.quota_mgr, None)  # 不再需要
        
        # 回调编码器
        self.encoder = CallbackEncoder()
        
        logger.info("音乐插件初始化完成")
    
    def _load_config(self) -> dict:
        """加载配置文件"""
        config_path = Path(__file__).parent / "config.yaml"
        
        if not config_path.exists():
            logger.warning("配置文件不存在，使用默认配置")
            return self._get_default_config()
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                logger.info("配置加载成功")
                return config
        except Exception as e:
            logger.error(f"配置加载失败: {e}", exc_info=True)
            return self._get_default_config()
    
    def _get_default_config(self) -> dict:
        """获取默认配置"""
        return {
            "music_api": {
                "base_url": "http://43.129.194.21:19003",
                "api_key": "your-api-key",
                "default_platform": "qq"
            },
            "telegram": {
                "enabled": False,
                "bot_token": "",
                "api_server": None
            },
            "quota": {
                "enabled": True,
                "default_quotas": {
                    "128": 20,
                    "320": 20,
                    "flac": 10,
                    "aac_96": 20,
                    "aac_48": 20,
                    "ogg_192": 20,
                    "ogg_96": 20
                },
                "vip_multiplier": 3
            }
        }
    
    def _format_lyric(self, lyric_content: str) -> str:
        """格式化歌词内容"""
        if not lyric_content or not lyric_content.strip():
            return "❌ 歌词内容为空"
        
        lines = []
        lyric_lines = lyric_content.strip().split('\n')
        
        # 提取歌曲信息（如果有的话）
        song_info = []
        lyric_body = []
        
        for line in lyric_lines:
            line = line.strip()
            if not line:
                continue
            
            # 检查是否是标签行（如 [ti:歌名]）
            if line.startswith('[') and ']:' in line and not line.startswith('[0'):
                # 这是歌曲信息标签
                if line.startswith('[ti:'):
                    song_info.append(f"🎵 歌名: {line[4:-1]}")
                elif line.startswith('[ar:'):
                    song_info.append(f"👤 歌手: {line[4:-1]}")
                elif line.startswith('[al:'):
                    song_info.append(f"💿 专辑: {line[4:-1]}")
                elif line.startswith('[by:'):
                    song_info.append(f"📝 制作: {line[4:-1]}")
            else:
                # 处理时间标签的歌词行
                if line.startswith('[') and ']' in line:
                    # 移除时间标签，只保留歌词内容
                    try:
                        # 找到最后一个']'，之后的就是歌词
                        last_bracket = line.rfind(']')
                        if last_bracket != -1:
                            lyric_text = line[last_bracket + 1:].strip()
                            if lyric_text:  # 只添加非空歌词
                                lyric_body.append(lyric_text)
                    except:
                        # 如果解析失败，直接添加原始行
                        lyric_body.append(line)
                else:
                    # 不是标准LRC格式，直接添加
                    lyric_body.append(line)
        
        # 组装最终结果
        if song_info:
            lines.extend(song_info)
            lines.append("")  # 空行分隔
        
        if lyric_body:
            lines.append("")
            lines.extend(lyric_body)
        else:
            lines.append("❌ 未找到有效歌词内容")
        
        # 限制总长度，避免消息过长
        result = "\n".join(lines)
        if len(result) > 4000:  # Telegram消息长度限制
            result = result[:3900] + "\n\n... (歌词过长，已截断)"
        
        return result
    
    async def _extract_qq_music_mid(self, url: str) -> Optional[str]:
        """从QQ音乐链接中提取歌曲ID，支持短链"""
        # 检查是否为短链
        short_link_match = re.search(r'(https?://c6\.y\.qq\.com/base/fcgi-bin/u\?__=[A-Za-z0-9]+)', url)
        if short_link_match:
            short_link = short_link_match.group(1)
            logger.info(f"检测到QQ音乐短链: {short_link}")
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(short_link, allow_redirects=False) as response:
                        if response.status in (301, 302, 307, 308) and 'Location' in response.headers:
                            redirected_url = response.headers['Location']
                            logger.info(f"短链重定向至: {redirected_url}")
                            
                            # 从重定向链接中提取songmid
                            song_mid_match = re.search(r'[?&]songmid=([A-Za-z0-9]+)', redirected_url)
                            if song_mid_match:
                                song_mid = song_mid_match.group(1)
                                logger.info(f"从重定向链接中提取到songmid: {song_mid}")
                                return song_mid
            except Exception as e:
                logger.error(f"解析QQ音乐短链失败: {e}", exc_info=True)
                return None

        # QQ音乐链接格式示例：
        # https://y.qq.com/n/ryqq/songDetail/002Il7Ya1tZ6UZ
        # https://y.qq.com/n/m/song.html?id=002Il7Ya1tZ6UZ
        # https://y.qq.com/portal/song/002Il7Ya1tZ6UZ.html
        
        patterns = [
            r'y\.qq\.com/n/ryqq/songDetail/([A-Za-z0-9]+)',
            r'y\.qq\.com/n/m/song\.html\?id=([A-Za-z0-9]+)',
            r'y\.qq\.com/portal/song/([A-Za-z0-9]+)\.html',
            r'y\.qq\.com.*[?&]id=([A-Za-z0-9]+)',
            r'i\.y\.qq\.com/v8/playsong\.html.*[?&]songmid=([A-Za-z0-9]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                song_mid = match.group(1)
                logger.info(f"从QQ音乐链接提取到歌曲MID: {song_mid}")
                return song_mid
        
        return None
    
    def _is_qq_music_url(self, text: str) -> bool:
        """检查文本是否包含QQ音乐链接"""
        return ('y.qq.com' in text and ('songDetail' in text or 'song.html' in text or 'portal/song' in text)) or 'c6.y.qq.com' in text

    @filter.command("start")
    async def handle_start_command(self, event: AstrMessageEvent):
        """处理 /start 命令，支持深度链接音乐下载"""
        text = event.message_str or ""
        
        parts = text.split(maxsplit=1)
        
        if len(parts) < 2:
            # 普通的 /start 命令，不做处理
            return
        
        param = parts[1].strip()
        
        # 处理音乐下载深度链接请求
        if param.startswith("music_"):
            # 解析格式：music_{platform}_{song_id}_{quality}
            param_parts = param.split("_", 3)
            if len(param_parts) >= 4:
                _, platform, song_id, quality = param_parts
                
                # 构造下载回调数据
                callback_data = {
                    "action": "download",
                    "platform": platform,
                    "song_id": song_id,
                    "quality": quality
                }
                
                # 直接调用下载处理逻辑
                user_id = event.get_sender_id()
                
                if not self.telegram_api:
                    yield event.plain_result("❌ Telegram功能未启用")
                    return
                
                # 获取chat_id
                chat_id = event.get_sender_id()
                
                status_msg = await self.download_handler.handle_download(
                    user_id=user_id,
                    chat_id=chat_id,
                    callback_data=callback_data,
                    event=event
                )
                
                # 仅在有状态消息（通常是错误消息）时发送
                if status_msg is not None:
                    yield event.plain_result(status_msg)
                
                # 无论成功还是失败，都终止事件传播，避免转发给LLM
                event.stop_event()
                return
        
        # 处理歌词深度链接请求
        if param.startswith("lyric_"):
            # 解析格式：lyric_{platform}_{song_id}
            param_parts = param.split("_", 2)
            if len(param_parts) >= 3:
                _, platform, song_id = param_parts
                
                # 获取歌词
                try:
                    if not song_id:
                        yield event.plain_result("❌ 歌曲ID缺失")
                        return
                    
                    # 尝试从歌曲详情缓存获取歌词
                    detail_cache = self.db.get_song_detail_cache(song_id, platform)
                    lyric_content = ""
                    
                    if detail_cache:
                        try:
                            song_data = json.loads(detail_cache.song_data)
                            lyric_content = song_data.get("lyric", "")
                        except Exception as e:
                            logger.warning(f"解析缓存歌词失败: {e}")
                    
                    # 如果缓存中没有，从API获取
                    if not lyric_content:
                        song_data = await self.music_api.get_song_data(song_id, platform)
                        if song_data:
                            lyric_content = song_data.get("lyric", "")
                    
                    if not lyric_content or not lyric_content.strip():
                        yield event.plain_result("❌ 该歌曲暂无歌词信息")
                        event.stop_event()
                        return
                    
                    # 格式化歌词
                    formatted_lyric = self._format_lyric(lyric_content)
                    yield event.plain_result(formatted_lyric)
                    
                except Exception as e:
                    logger.error(f"获取歌词异常: {e}", exc_info=True)
                    yield event.plain_result(f"❌ 获取歌词失败: {e}")
                
                # 歌词处理完成，终止事件传播
                event.stop_event()
                return
        
        # 如果不是音乐插件的深度链接，不做处理
        return

    @filter.command("歌")
    async def handle_search_command(self, event: AstrMessageEvent, keyword: str = ""):
        """处理搜索命令 - 搜索音乐"""
        if not keyword:
            yield event.plain_result("💡 使用方法: /歌 关键词\n示例: /歌 周杰伦 晴天")
            return
        
        user_id = event.get_sender_id()
        
        # 配额检查（使用通用系统）
        if self.common_quota_validator:
            result = await self.common_quota_validator.check_quota(
                user_id=user_id,
                action_type="music_search",
                plugin_name="music",
                use_points=True
            )
            
            if not result.allowed:
                yield event.plain_result(result.message)
                return
        
        progress_msg_id = None
        try:
            # 1. 发送进度提示消息
            platform_name = (event.get_platform_name() or "").lower()
            if platform_name == "telegram":
                from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                if isinstance(event, TelegramPlatformEvent):
                    chat_id = event.message_obj.group_id or event.get_sender_id()
                    msg = await event.client.send_message(chat_id=chat_id, text="🔍 正在全力搜索，请稍候...")
                    progress_msg_id = getattr(msg, "message_id", None)

            # 2. 执行搜索
            try:
                result = await self.search_handler.handle_search(
                    user_id=user_id,
                    keyword=keyword,
                    platform=self.config["music_api"].get("default_platform", "netease")
                )
                
                if isinstance(result, tuple) and len(result) == 2:
                    message, keyboard = result
                    if isinstance(message, str):
                        # 搜索成功，消费配额
                        if self.common_quota_validator:
                            await self.common_quota_validator.consume_quota(
                                user_id=user_id,
                                action_type="music_search",
                                plugin_name="music",
                                points_cost=result.points_cost if hasattr(result, 'points_cost') else 0
                            )
                        
                        yield event.chain_result([Plain(message), keyboard])
                    else:
                        logger.error(f"消息不是字符串类型: {type(message)} - {message}")
                        yield event.plain_result("❌ 搜索结果格式错误")
                else:
                    logger.error(f"搜索返回值格式错误: {type(result)} - {result}")
                    yield event.plain_result("❌ 搜索返回值格式错误")
                
            except Exception as e:
                logger.error(f"搜索处理异常: {e}", exc_info=True)
                yield event.plain_result(f"❌ 搜索失败: {e}")

        finally:
            # 3. 删除进度提示消息
            if progress_msg_id:
                try:
                    platform_name = (event.get_platform_name() or "").lower()
                    if platform_name == "telegram":
                        from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                        if isinstance(event, TelegramPlatformEvent):
                            chat_id = event.message_obj.group_id or event.get_sender_id()
                            await event.client.delete_message(
                                chat_id=chat_id, 
                                message_id=progress_msg_id
                            )
                except Exception as e:
                    logger.warning(f"删除搜索提示消息失败: {e}")

    @filter.command("配额")
    async def handle_quota_command(self, event: AstrMessageEvent):
        """处理配额查询命令 - 查看今日下载配额"""
        user_id = event.get_sender_id()
        
        try:
            status = self.quota_handler.handle_quota_query(user_id)
            yield event.plain_result(status)
        except Exception as e:
            logger.error(f"配额查询异常: {e}", exc_info=True)
            yield event.plain_result(f"❌ 查询失败: {e}")
    
    async def _handle_qq_music_link(self, event: AstrMessageEvent, message_text: str):
        """处理QQ音乐链接的内部方法"""
        logger.info(f"检测到QQ音乐链接: {message_text}")
        
        loading_msg_id = None
        try:
            # 提取歌曲ID
            song_mid = await self._extract_qq_music_mid(message_text)
            if not song_mid:
                yield event.plain_result("❌ 无法从链接中提取歌曲ID")
                return
            
            # 发送加载消息并获取其ID
            platform_name = (event.get_platform_name() or "").lower()
            if platform_name == "telegram":
                from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                if isinstance(event, TelegramPlatformEvent):
                    chat_id = event.message_obj.group_id or event.get_sender_id()
                    msg = await event.client.send_message(chat_id=chat_id, text="🔍 正在获取歌曲详情...")
                    loading_msg_id = getattr(msg, "message_id", None)
            else:
                # 对于其他平台，可能需要不同的实现方式
                # 暂时保留原有逻辑，但可能无法删除
                yield event.plain_result("🔍 正在获取歌曲详情...")

            # 调用详情处理器获取歌曲详情
            user_id = event.get_sender_id()
            cover_url, message, keyboard = await self.detail_handler.handle_detail(
                user_id=user_id,
                callback_data={
                    "song_id": song_mid,
                    "platform": "qq"
                }
            )
            
            if cover_url and message and keyboard:
                # 检查图片链接是否有效
                if await is_image_url_valid(cover_url):
                    # 发送图片和详情
                    image_component = Image.fromURL(cover_url, caption=message)
                    yield event.chain_result([image_component, keyboard])
                else:
                    # 图片链接无效，只发送文本和键盘
                    logger.warning(f"图片链接无效或加载失败: {cover_url}")
                    error_message = f"🖼️ 图片加载失败\n\n{message}"
                    yield event.chain_result([Plain(error_message), keyboard])
            else:
                yield event.plain_result("❌ 获取歌曲详情失败")
                
        except Exception as e:
            logger.error(f"处理QQ音乐链接异常: {e}", exc_info=True)
            yield event.plain_result(f"❌ 处理链接失败: {e}")
            
        finally:
            # 删除加载消息
            if loading_msg_id and hasattr(event, 'client') and hasattr(event.client, 'delete_message'):
                try:
                    platform_name = (event.get_platform_name() or "").lower()
                    if platform_name == "telegram":
                        from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                        if isinstance(event, TelegramPlatformEvent):
                            chat_id = event.message_obj.group_id or event.get_sender_id()
                            await event.client.delete_message(
                                chat_id=chat_id,
                                message_id=loading_msg_id
                            )
                except Exception as e:
                    logger.debug(f"删除加载消息失败: {e}")
    
    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """处理所有消息，检查是否包含QQ音乐链接"""
        # 获取完整的消息文本
        message_text = event.message_str.strip()
        
        # 检查是否是QQ音乐链接
        if self._is_qq_music_url(message_text):
            async for result in self._handle_qq_music_link(event, message_text):
                yield result
            return
        
        # 如果不是QQ音乐链接，不做任何处理（让其他插件处理）
        return

    @filter.command("callback")
    async def handle_callback(self, event: AstrMessageEvent, data: str = ""):
        """处理回调按钮 - 处理用户点击的按钮操作"""
        # 解析回调数据
        callback_str = data.strip() if data else ""
        logger.debug(f"收到回调数据: {callback_str}")
        
        # 检查是否是音乐插件的回调格式
        if not (callback_str.startswith("detail:") or 
                callback_str.startswith("download:") or 
                callback_str.startswith("page:") or 
                callback_str.startswith("switch:") or
                callback_str.startswith("lyric:")):
            # 不是音乐插件的回调格式，直接返回，让其他插件处理
            return
        
        callback_data = self.encoder.decode(callback_str)
        
        if not callback_data:
            yield event.plain_result("❌ 无效的回调数据")
            return
        
        action = callback_data.get("action", "")
        user_id = event.get_sender_id()
        
        try:
            # 根据action分发处理
            if action == "page":
                # 翻页 - 使用编辑消息的方式
                try:
                    # 1. 获取新页面的内容和键盘
                    message, keyboard = await self.search_handler.handle_page_change(callback_data)
                    
                    # 2. 尝试编辑原消息
                    platform_name = (event.get_platform_name() or "").lower()
                    if platform_name == "telegram":
                        from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                        if isinstance(event, TelegramPlatformEvent):
                            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                            
                            # 将AstrBot的InlineKeyboard转换为telegram.InlineKeyboardMarkup
                            tg_keyboard_buttons = []
                            if keyboard.buttons:
                                for row in keyboard.buttons:
                                    tg_row = [InlineKeyboardButton(text=btn['text'], callback_data=btn['callback_data']) for btn in row]
                                    tg_keyboard_buttons.append(tg_row)
                            
                            tg_keyboard = InlineKeyboardMarkup(tg_keyboard_buttons)
                            
                            msg_id = int(event.message_obj.message_id)
                            chat_id = event.message_obj.group_id or event.get_sender_id()
                            
                            await event.client.edit_message_text(
                                chat_id=chat_id,
                                message_id=msg_id,
                                text=message,
                                reply_markup=tg_keyboard
                            )
                            # 编辑成功后，不需要再发送新消息，直接返回
                            return
                            
                    # 对于不支持编辑消息的平台，或者编辑失败，回退到发送新消息
                    yield event.chain_result([Plain(message), keyboard])

                except Exception as e:
                    logger.error(f"翻页（编辑消息）失败: {e}", exc_info=True)
                    # 失败时尝试发送一条提示消息
                    yield event.plain_result("❌ 翻页失败，请重试")

            elif action == "detail":
                progress_msg_id = None
                try:
                    # 1. 发送进度提示消息
                    platform_name = (event.get_platform_name() or "").lower()
                    if platform_name == "telegram":
                        # 尝试导入Telegram特定事件类
                        from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                        if isinstance(event, TelegramPlatformEvent):
                            chat_id = event.message_obj.group_id or event.get_sender_id()
                            msg = await event.client.send_message(chat_id=chat_id, text="🔍 正在获取歌曲详情，请稍候...")
                            progress_msg_id = getattr(msg, "message_id", None)
                    
                    # 2. 获取详情
                    cover_url, message, keyboard = await self.detail_handler.handle_detail(
                        user_id=user_id,
                        callback_data=callback_data
                    )
                    
                    # 3. 发送最终结果
                    if cover_url:
                        if await is_image_url_valid(cover_url):
                            # 将文本作为图片的caption，合并发送
                            image_component = Image.fromURL(url=cover_url, caption=message)
                            yield event.chain_result([image_component, keyboard])
                        else:
                            logger.warning(f"图片链接无效或加载失败: {cover_url}")
                            error_message = f"🖼️ 图片加载失败\n\n{message}"
                            yield event.chain_result([Plain(error_message), keyboard])
                    else:
                        # 仅文本 + 键盘
                        yield event.chain_result([Plain(message), keyboard])

                finally:
                    # 4. 删除进度提示消息
                    if progress_msg_id and hasattr(event, "delete_message"):
                        try:
                            await event.delete_message(progress_msg_id)
                        except Exception as e:
                            logger.warning(f"删除进度消息失败: {e}")
            
            elif action == "download":
                # 下载音频
                if not self.telegram_api:
                    yield event.plain_result("❌ Telegram功能未启用")
                    return
                
                # 获取chat_id（需要根据实际平台调整）
                chat_id = event.get_sender_id()
                
                status_msg = await self.download_handler.handle_download(
                    user_id=user_id,
                    chat_id=chat_id,
                    callback_data=callback_data,
                    event=event  # 传递 event 对象
                )
                
                # 仅在有状态消息（通常是错误消息）时发送
                if status_msg is not None:
                    yield event.plain_result(status_msg)
                
                # 下载处理完成，终止事件传播
                event.stop_event()
            
            elif action == "lyric":
                # 获取歌词
                try:
                    song_id = callback_data.get("song_id", "")
                    platform = callback_data.get("platform", "qq")
                    
                    if not song_id:
                        yield event.plain_result("❌ 歌曲ID缺失")
                        return
                    
                    # 尝试从歌曲详情缓存获取歌词
                    detail_cache = self.db.get_song_detail_cache(song_id, platform)
                    lyric_content = ""
                    
                    if detail_cache:
                        try:
                            song_data = json.loads(detail_cache.song_data)
                            lyric_content = song_data.get("lyric", "")
                        except Exception as e:
                            logger.warning(f"解析缓存歌词失败: {e}")
                    
                    # 如果缓存中没有，从API获取
                    if not lyric_content:
                        song_data = await self.music_api.get_song_data(song_id, platform)
                        if song_data:
                            lyric_content = song_data.get("lyric", "")
                    
                    if not lyric_content or not lyric_content.strip():
                        yield event.plain_result("❌ 该歌曲暂无歌词信息")
                        event.stop_event()
                        return
                    
                    # 格式化歌词
                    formatted_lyric = self._format_lyric(lyric_content)
                    yield event.plain_result(formatted_lyric)
                    
                except Exception as e:
                    logger.error(f"获取歌词异常: {e}", exc_info=True)
                    yield event.plain_result(f"❌ 获取歌词失败: {e}")
                
                # 歌词处理完成，终止事件传播
                event.stop_event()
            
            elif action == "switch":
                # 换源搜索
                try:
                    # 1. 获取新平台的搜索结果
                    message, keyboard = await self.search_handler.handle_switch_source(callback_data)
                    
                    # 2. 尝试编辑原消息
                    platform_name = (event.get_platform_name() or "").lower()
                    if platform_name == "telegram":
                        from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                        if isinstance(event, TelegramPlatformEvent):
                            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                            
                            # 将AstrBot的InlineKeyboard转换为telegram.InlineKeyboardMarkup
                            tg_keyboard_buttons = []
                            if keyboard.buttons:
                                for row in keyboard.buttons:
                                    tg_row = [InlineKeyboardButton(text=btn['text'], callback_data=btn['callback_data']) for btn in row]
                                    tg_keyboard_buttons.append(tg_row)
                            
                            tg_keyboard = InlineKeyboardMarkup(tg_keyboard_buttons)
                            
                            msg_id = int(event.message_obj.message_id)
                            chat_id = event.message_obj.group_id or event.get_sender_id()
                            
                            await event.client.edit_message_text(
                                chat_id=chat_id,
                                message_id=msg_id,
                                text=message,
                                reply_markup=tg_keyboard
                            )
                            # 编辑成功后，不需要再发送新消息，终止事件传播
                            event.stop_event()
                            return
                            
                    # 对于不支持编辑消息的平台，或者编辑失败，回退到发送新消息
                    yield event.chain_result([Plain(message), keyboard])
                    event.stop_event()

                except Exception as e:
                    logger.error(f"换源搜索失败: {e}", exc_info=True)
                    yield event.plain_result("❌ 换源搜索失败，请重试")
                    event.stop_event()
            
            else:
                yield event.plain_result(f"❌ 未知操作: {action}")
                event.stop_event()
                
        except Exception as e:
            logger.error(f"回调处理异常: {e}", exc_info=True)
            yield event.plain_result(f"❌ 处理失败: {e}")
            event.stop_event()

    async def terminate(self):
        """插件卸载时的清理工作"""
        logger.info("音乐插件正在卸载...")

