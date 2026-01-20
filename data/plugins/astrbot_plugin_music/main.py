"""
音乐搜索插件
支持多平台音乐搜索、下载和歌词查看
"""
import os
import sys
import json
import re
import yaml
import aiohttp
from pathlib import Path
from typing import Any, Dict, Optional

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.message.components import Image, Plain, InlineKeyboard
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.core import callback_handler, auto_stop_event

# 添加插件根目录到 sys.path
plugin_root = Path(__file__).parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

# 导入通用模块
try:
    from common.platform_capabilities import get_platform_capabilities
    from common.loading_indicator import LoadingIndicator
    from common.database_manager import DatabaseManager as CommonDatabaseManager
    from common.quota_validator import QuotaValidator
    from common.session_manager import get_session_manager
    from common.search_statistics import get_search_statistics
    from common.message_editor import MessageEditor
    from common.user_utils import get_unified_user_id
    from common.search_helper import SearchHelper
    from common.message_formatter import get_separator
    COMMON_MODULES_AVAILABLE = True
except ImportError as e:
    COMMON_MODULES_AVAILABLE = False
    logger.warning(f"[Music] 通用模块不可用: {e}")
    def get_unified_user_id(event):
        return event.get_sender_id()

# 导入内部模块
from .music_api_client import MusicAPIClient
from .db.database import DatabaseManager
from .handlers.telegram_file_cache import FileCacheManager
from .handlers import (
    SearchHandler, DetailHandler, DownloadHandler,
    MusicFormatter, MusicResponseBuilder, MusicSessionHandler
)
from .utils.callback_encoder import CallbackEncoder


async def is_image_url_valid(url: str) -> bool:
    """检查图片URL是否有效"""
    if not url or not url.startswith("http"):
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=5) as response:
                return response.status == 200 and "image" in response.headers.get("Content-Type", "")
    except Exception:
        return False


@register("music-search", "Chrismk", "音乐搜索插件 - 支持多平台音乐搜索和下载", "2.0.0")
class MusicPlugin(Star):
    """音乐搜索插件"""
    
    PAGE_SIZE = 15  # API 最大支持 15
    SESSION_TIMEOUT_MINUTES = 1
    
    def __init__(self, context: Context, plugin_config: AstrBotConfig = None):
        super().__init__(context)
        self.plugin_config = plugin_config or {}
        
        # 加载插件配置
        self._load_plugin_config()
        
        # 加载配置
        self.config = self._load_config()
        
        # 数据库
        config = self.context.get_config()
        data_path = config.get("data_path", "data")
        
        plugin_data_dir = os.path.join(data_path, "plugin_data", "music")
        os.makedirs(plugin_data_dir, exist_ok=True)
        db_path = os.path.join(plugin_data_dir, "music.db")
        
        self.db = DatabaseManager(db_path, None)
        
        # 音乐API客户端
        self.music_api = MusicAPIClient(
            api_base_url=self.config["music_api"]["base_url"],
            api_key=self.config["music_api"]["api_key"]
        )
        
        # File ID缓存管理器
        self.cache_mgr = FileCacheManager(self.db, None)
        
        # 会话管理器和处理器
        self.session_manager = None
        self.session_handler = None
        self.quota_validator = None
        self.search_stats = None
        
        if COMMON_MODULES_AVAILABLE:
            self.session_manager = get_session_manager(timeout_minutes=self.SESSION_TIMEOUT_MINUTES)
            self.session_handler = MusicSessionHandler(self.session_manager, self.music_api)
            logger.info("[Music] SessionManager 初始化完成")
            
            # 配额系统和搜索统计
            try:
                quota_db_path = os.path.join(data_path, "quota_system.db")
                common_db = CommonDatabaseManager(quota_db_path)
                self.quota_validator = QuotaValidator(common_db)
                self.search_stats = get_search_statistics(common_db)
                # 搜索辅助器
                self.search_helper = SearchHelper(
                    plugin_name='music',
                    search_stats=self.search_stats,
                    page_size=self.PAGE_SIZE
                )
                self._register_quota_rules()
                logger.info("[Music] 配额系统和搜索统计初始化完成")
            except Exception as e:
                logger.error(f"[Music] 配额系统初始化失败: {e}")
        
        # 旧版处理器（保持兼容）
        self.search_handler = SearchHandler(self.music_api, self.db, None)
        self.detail_handler = DetailHandler(self.music_api, self.db, None)
        self.download_handler = DownloadHandler(
            self.music_api, self.db, None,
            self.cache_mgr, None, None,  # telegram_api 已废弃，使用 Audio 组件
            common_quota_validator=self.quota_validator
        )
        
        # 回调编码器
        self.encoder = CallbackEncoder()
        
        logger.info("[Music] 音乐插件初始化完成")
    
    def _load_config(self) -> dict:
        """加载配置文件"""
        config_path = Path(__file__).parent / "config.yaml"
        
        if not config_path.exists():
            logger.warning("配置文件不存在，使用默认配置")
            return self._get_default_config()
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config
        except Exception as e:
            logger.error(f"配置加载失败: {e}")
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
            }
        }
    
    def _load_plugin_config(self):
        """加载插件配置"""
        defaults = {
            'page_size': 16,
            'session_timeout': 1,
            'default_platform': 'qq',
            'quota_search_daily_limit': -1,
            'quota_search_points_cost': 0,
            'quota_download_daily_limit': -1,
            'quota_download_points_cost': 0,
            'rate_limit_search_max': 60,
            'rate_limit_search_window': 60,
            'rate_limit_download_max': 60,
            'rate_limit_download_window': 60
        }
        for key, default in defaults.items():
            if key not in self.plugin_config:
                self.plugin_config[key] = default
        
        # 应用配置
        self.PAGE_SIZE = self.plugin_config.get('page_size', 16)
        self.SESSION_TIMEOUT_MINUTES = self.plugin_config.get('session_timeout', 1)
    
    def _register_quota_rules(self):
        """注册配额和限流规则（使用标准化配置）"""
        if not self.quota_validator:
            return
        
        try:
            from common.plugin_quota_config import sync_plugin_quota_and_rate_limit
            
            actions = [
                {'action': 'search', 'action_type': 'music_search', 'description': '音乐搜索'},
                {'action': 'download', 'action_type': 'music_download', 'description': '音乐下载'}
            ]
            
            quota_success, rate_limit_success = sync_plugin_quota_and_rate_limit(
                plugin_name='music',
                plugin_config=self.plugin_config,
                quota_validator=self.quota_validator,
                actions=actions
            )
            
            if quota_success:
                logger.info("[Music] 配额规则同步成功")
            if rate_limit_success:
                logger.info("[Music] 限流规则同步成功")
                
        except ImportError:
            # 兼容旧版
            quota_rules = [
                {
                    'action_type': 'music_search',
                    'free': {'daily_limit': -1, 'points_cost': 0},
                    'premium': {'daily_limit': -1, 'points_cost': 0},
                    'vip': {'daily_limit': -1, 'points_cost': 0},
                    'description': '音乐搜索'
                },
                {
                    'action_type': 'music_download',
                    'free': {'daily_limit': -1, 'points_cost': 0},
                    'premium': {'daily_limit': -1, 'points_cost': 0},
                    'vip': {'daily_limit': -1, 'points_cost': 0},
                    'description': '音乐下载'
                }
            ]
            try:
                self.quota_validator.register_quota_rules(plugin_name='music', rules=quota_rules, override=False)
            except Exception as e:
                logger.error(f"[Music] 注册配额规则失败: {e}")
    
    @filter.command(command_name="歌", command_alias=["music", "song"])
    async def handle_search_command(self, event: AstrMessageEvent):
        """处理音乐搜索命令"""
        text = event.message_str or ""
        keyword = text.split(maxsplit=1)[1].strip() if " " in text else ""
        user_id = get_unified_user_id(event)
        
        if not keyword:
            # 使用搜索辅助器显示提示
            if COMMON_MODULES_AVAILABLE and hasattr(self, 'search_helper'):
                hint = self.search_helper.get_empty_search_hint(user_id)
                yield event.plain_result(hint)
            else:
                yield event.plain_result("💡 使用方法: /歌 关键词\n示例: /歌 周杰伦 晴天")
            return
        session_id = event.get_session_id()
        capabilities = get_platform_capabilities(event, "Music") if COMMON_MODULES_AVAILABLE else {}
        is_button_mode = capabilities.get('supports_buttons', False)
        
        loading_msg_id = await LoadingIndicator.show(event, 'search') if COMMON_MODULES_AVAILABLE else None
        
        try:
            platform = self.config["music_api"].get("default_platform", "qq")
            result = await self.music_api.search(keyword, platform, 1, self.PAGE_SIZE)
            
            songs = result.get("songs", [])
            total = result.get("total", 0)
            
            # 记录搜索统计
            if self.search_stats:
                self.search_stats.record_search(
                    user_id=user_id,
                    plugin_name='music',
                    keyword=keyword,
                    result_count=total,
                    platform=platform
                )
            
            if not songs:
                # 使用搜索辅助器显示无结果提示
                if COMMON_MODULES_AVAILABLE and hasattr(self, 'search_helper'):
                    hint = self.search_helper.format_no_result_hint(keyword, user_id)
                    yield event.plain_result(hint)
                else:
                    yield event.plain_result(f"❌ 未找到「{keyword}」相关歌曲")
                return
            
            if is_button_mode:
                # 按钮模式
                message, _ = MusicFormatter.format_search_results(
                    songs, 1, self.PAGE_SIZE, total, platform, keyword, False
                )
                builder = MusicResponseBuilder(capabilities)
                keyboard = builder.build_search_keyboard(songs, keyword, 1, self.PAGE_SIZE, total, platform)
                yield event.chain_result([Plain(message), keyboard]) if keyboard else event.plain_result(message)
            else:
                # 会话模式
                if self.session_manager is not None:
                    self.session_manager.create_session(
                        session_id=session_id,
                        session_type="music_search",
                        user_id=user_id,
                        step=0,
                        capabilities=capabilities,
                        data={
                            'keyword': keyword,
                            'page': 1,
                            'page_size': self.PAGE_SIZE,
                            'total': total,
                            'results': songs,
                            'platform': platform
                        }
                    )
                
                message, _ = MusicFormatter.format_search_results(
                    songs, 1, self.PAGE_SIZE, total, platform, keyword, True, self.SESSION_TIMEOUT_MINUTES
                )
                yield event.plain_result(message)
                
        except Exception as e:
            logger.error(f"[Music] 搜索失败: {e}", exc_info=True)
            yield event.plain_result("❌ 搜索失败，请稍后重试")
        finally:
            if COMMON_MODULES_AVAILABLE and loading_msg_id:
                await LoadingIndicator.hide(event, loading_msg_id)
        
        event.stop_event()
    
    @filter.command("callback")
    @callback_handler("music")
    @auto_stop_event
    async def handle_callback(self, event: AstrMessageEvent, data: str = ""):
        """处理回调按钮 - 使用统一的 music: 前缀"""
        # 去掉可能的 music: 前缀
        if data.startswith("music:"):
            data = data[6:]
        
        # 解析回调数据
        callback_data = self.encoder.decode(data) if data else None
        if not callback_data:
            yield event.plain_result("❌ 无效的回调数据")
            return
        
        action = callback_data.get("action", "")
        if action.startswith("music_"):
            action = action[6:]
            
        user_id = get_unified_user_id(event)
        capabilities = get_platform_capabilities(event, "Music") if COMMON_MODULES_AVAILABLE else {}
        
        try:
            if action == "detail":
                async for result in self._handle_detail_callback(event, callback_data, capabilities):
                    yield result
            elif action == "download":
                async for result in self._handle_download_callback(event, callback_data):
                    yield result
            elif action == "lyric":
                async for result in self._handle_lyric_callback(event, callback_data):
                    yield result
            elif action == "page":
                async for result in self._handle_page_callback(event, callback_data, capabilities):
                    yield result
            elif action == "switch":
                async for result in self._handle_switch_callback(event, callback_data, capabilities):
                    yield result
            elif action == "exit":
                async for result in self._handle_exit_callback(event):
                    yield result
            else:
                yield event.plain_result(f"❌ 未知操作: {action}")
        except Exception as e:
            logger.error(f"[Music] 回调处理失败: {e}", exc_info=True)
            yield event.plain_result("❌ 处理失败，请稍后重试")
    
    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """处理会话消息和QQ音乐链接"""
        if event.get_result():
            return
        
        message_text = (event.message_str or "").strip()
        if not message_text or message_text.startswith('/') or message_text.startswith('callback '):
            return
        
        # 检查QQ音乐链接
        if self._is_qq_music_url(message_text):
            async for result in self._handle_qq_music_link(event, message_text):
                yield result
            event.stop_event()
            return
        
        # 会话模式处理
        if self.session_manager is None:
            return
        
        session_id = event.get_session_id()
        
        # 使用 match_session 进行类型检查和自动续期
        if self.session_manager.match_session(session_id, 'music_search'):
            logger.debug(f"[Music] on_message: 检测到会话 - session_id={session_id}, message={message_text}")
            
            if self.session_handler:
                result = await self.session_handler.handle_session_message(
                    get_unified_user_id(event), session_id, message_text
                )
                
                if result:
                    # 处理特殊返回标记
                    if isinstance(result, tuple) and len(result) >= 2:
                        if result[0] == "SHOW_SONG_DETAIL":
                            song_id, platform = result[1], result[2]
                            capabilities = get_platform_capabilities(event, "Music") if COMMON_MODULES_AVAILABLE else {}
                            
                            # 添加加载提示
                            loading_msg_id = await LoadingIndicator.show(event, 'get_detail') if COMMON_MODULES_AVAILABLE else None
                            try:
                                async for r in self._show_song_detail(event, song_id, platform, capabilities):
                                    yield r
                            finally:
                                if COMMON_MODULES_AVAILABLE and loading_msg_id:
                                    await LoadingIndicator.hide(event, loading_msg_id)
                                    
                            event.stop_event()
                            return
                        
                        if result[0] == "SHOW_LYRIC":
                            song_id, platform = result[1], result[2]
                            
                            # 添加加载提示
                            loading_msg_id = await LoadingIndicator.show(event, 'get_lyric') if COMMON_MODULES_AVAILABLE else None
                            try:
                                async for r in self._show_lyric(event, song_id, platform):
                                    yield r
                            finally:
                                if COMMON_MODULES_AVAILABLE and loading_msg_id:
                                    await LoadingIndicator.hide(event, loading_msg_id)
                                    
                            event.stop_event()
                            return
                        
                        if result[0] == "TRIGGER_DOWNLOAD":
                            # 会话模式下检查平台是否支持发送文件
                            capabilities = get_platform_capabilities(event, "Music") if COMMON_MODULES_AVAILABLE else {}
                            platform_name = capabilities.get('platform_name', '').lower()
                            
                            if platform_name != 'telegram':
                                bot_username = event.get_self_id() or "zslraibot"
                                yield event.plain_result(f"❌ 当前平台不支持发送音乐文件，请在 TG @{bot_username} 中使用此功能")
                                event.stop_event()
                                return
                            
                            song_id, platform, quality = result[1], result[2], result[3]
                            async for r in self._handle_download(event, song_id, platform, quality):
                                yield r
                            event.stop_event()
                            return
                        
                        # 普通消息
                        message, keyboard = result
                        if isinstance(message, str):
                            if keyboard:
                                yield event.chain_result([Plain(message), keyboard])
                            else:
                                yield event.plain_result(message)
                    
                    event.stop_event()
                    return
    
    @filter.command("start")
    async def handle_start_command(self, event: AstrMessageEvent):
        """处理 /start 深度链接"""
        text = event.message_str or ""
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return
        
        param = parts[1].strip()
        
        # 音乐下载深度链接
        if param.startswith("music_"):
            param_parts = param.split("_", 3)
            if len(param_parts) >= 4:
                _, platform, song_id, quality = param_parts
                async for result in self._handle_download(event, song_id, platform, quality):
                    yield result
                event.stop_event()
                return
        
        # 歌词深度链接
        if param.startswith("lyric_"):
            param_parts = param.split("_", 2)
            if len(param_parts) >= 3:
                _, platform, song_id = param_parts
                async for result in self._show_lyric(event, song_id, platform):
                    yield result
                event.stop_event()
                return
    
    def _is_qq_music_url(self, text: str) -> bool:
        """检查是否是QQ音乐链接"""
        return ('y.qq.com' in text and ('songDetail' in text or 'song.html' in text or 'portal/song' in text)) or 'c6.y.qq.com' in text
    
    async def _extract_qq_music_mid(self, url: str) -> Optional[str]:
        """从QQ音乐链接提取歌曲ID"""
        # 短链处理
        short_link_match = re.search(r'(https?://c6\.y\.qq\.com/base/fcgi-bin/u\?__=[A-Za-z0-9]+)', url)
        if short_link_match:
            short_link = short_link_match.group(1)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(short_link, allow_redirects=False) as response:
                        if response.status in (301, 302, 307, 308) and 'Location' in response.headers:
                            redirected_url = response.headers['Location']
                            song_mid_match = re.search(r'[?&]songmid=([A-Za-z0-9]+)', redirected_url)
                            if song_mid_match:
                                return song_mid_match.group(1)
            except Exception as e:
                logger.error(f"解析QQ音乐短链失败: {e}")
                return None
        
        # 标准链接
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
                return match.group(1)
        
        return None
    
    async def _handle_qq_music_link(self, event: AstrMessageEvent, message_text: str):
        """处理QQ音乐链接"""
        loading_msg_id = await LoadingIndicator.show(event, 'get_detail') if COMMON_MODULES_AVAILABLE else None
        
        try:
            song_mid = await self._extract_qq_music_mid(message_text)
            if not song_mid:
                yield event.plain_result("❌ 无法从链接中提取歌曲ID")
                return
            
            capabilities = get_platform_capabilities(event, "Music") if COMMON_MODULES_AVAILABLE else {}
            async for result in self._show_song_detail(event, song_mid, "qq", capabilities):
                yield result
                
        except Exception as e:
            logger.error(f"[Music] 处理QQ音乐链接失败: {e}", exc_info=True)
            yield event.plain_result("❌ 处理链接失败，请稍后重试")
        finally:
            if COMMON_MODULES_AVAILABLE and loading_msg_id:
                await LoadingIndicator.hide(event, loading_msg_id)
    
    async def _show_song_detail(self, event: AstrMessageEvent, song_id: str, platform: str, capabilities: Dict):
        """显示歌曲详情"""
        is_button_mode = capabilities.get('supports_buttons', False)
        platform_name = capabilities.get('platform_name', '').lower()
        
        # 获取歌曲详情
        song_data = await self.music_api.get_details(song_id, platform)
        if not song_data:
            yield event.plain_result("❌ 获取歌曲详情失败")
            return
        
        # 获取可用音质
        available_qualities = list(song_data.get("urls", {}).keys())
        if not available_qualities:
            available_qualities = ["128", "320", "flac"]
        
        # 检查是否有歌词
        has_lyrics = bool(song_data.get("lyric", "").strip())
        
        # 获取机器人用户名
        bot_username = event.get_self_id() or "zslraibot"
        
        # 格式化详情
        caption = MusicFormatter.format_song_detail(song_data, platform, available_qualities, bot_username)
        
        keyboard = None
        if is_button_mode:
            builder = MusicResponseBuilder(capabilities)
            keyboard = builder.build_detail_keyboard(song_id, platform, available_qualities, has_lyrics, bot_username)
        else:
            # 会话模式提示
            separator = get_separator(platform_name)
            quality_hints = " | ".join([f"{i+1}-{q}" for i, q in enumerate(available_qualities)])
            lyric_hint = "l-歌词 | " if has_lyrics else ""
            caption += f"\n\n{separator}\n💡 {quality_hints}\n💡 {lyric_hint}b-返回 | 0-退出"
        
        # 发送封面和详情
        cover_url = song_data.get("pic") or song_data.get("cover_url") or song_data.get("cover", "")
        if cover_url and await is_image_url_valid(cover_url):
            img = Image(file=cover_url, caption=caption if platform_name == "telegram" else "")
            if platform_name == "telegram":
                yield event.chain_result([img, keyboard]) if keyboard else event.chain_result([img])
            elif platform_name == "lark":
                yield event.chain_result([img, Plain(caption), keyboard]) if keyboard else event.chain_result([img, Plain(caption)])
            else:
                yield event.chain_result([Plain(caption), img])
        else:
            yield event.chain_result([Plain(caption), keyboard]) if keyboard else event.plain_result(caption)
    
    async def _show_lyric(self, event: AstrMessageEvent, song_id: str, platform: str):
        """显示歌词"""
        try:
            song_data = await self.music_api.get_song_data(song_id, platform)
            if not song_data:
                yield event.plain_result("❌ 获取歌曲信息失败")
                return
            
            lyric_content = song_data.get("lyric", "")
            if not lyric_content or not lyric_content.strip():
                yield event.plain_result("❌ 该歌曲暂无歌词信息")
                return
            
            formatted_lyric = MusicFormatter.format_lyric(lyric_content)
            yield event.plain_result(formatted_lyric)
            
        except Exception as e:
            logger.error(f"[Music] 获取歌词失败: {e}", exc_info=True)
            yield event.plain_result("❌ 获取歌词失败，请稍后重试")
    
    async def _handle_exit_callback(self, event: AstrMessageEvent):
        """处理退出回调 - 使用统一退出处理器"""
        from common.exit_handler import handle_exit
        async for result in handle_exit(event, self.session_manager, plugin_name="Music"):
            yield result
    
    async def _handle_download(self, event: AstrMessageEvent, song_id: str, platform: str, quality: str):
        """处理下载"""
        user_id = get_unified_user_id(event)
        
        # 配额检查
        quota_result = None
        if self.quota_validator:
            quota_result = await self.quota_validator.check_quota(user_id, 'music_download', 'music', use_points=True)
            if not quota_result.allowed:
                yield event.plain_result(quota_result.message)
                return
        
        chat_id = event.get_sender_id()
        callback_data = {
            "action": "download",
            "platform": platform,
            "song_id": song_id,
            "quality": quality
        }
        
        status_msg = await self.download_handler.handle_download(
            user_id=user_id,
            chat_id=chat_id,
            callback_data=callback_data,
            event=event
        )
        
        # 记录下载统计和消费配额（status_msg 为 None 表示成功）
        if status_msg is None:
            # 消费配额
            if self.quota_validator and quota_result:
                await self.quota_validator.consume_quota(user_id, 'music_download', 'music', quota_result.points_cost)
        
        if status_msg is None and self.search_stats:
            self.search_stats.record_download(
                user_id=user_id,
                plugin_name='music',
                item_id=song_id,
                platform=platform,
                quality=quality
            )
        
        if status_msg is not None:
            yield event.plain_result(status_msg)
    
    async def _handle_detail_callback(self, event: AstrMessageEvent, callback_data: Dict, capabilities: Dict):
        """处理详情回调"""
        song_id = callback_data.get("song_id", "")
        platform = callback_data.get("platform", "qq")
        
        loading_msg_id = await LoadingIndicator.show(event, 'get_detail') if COMMON_MODULES_AVAILABLE else None
        try:
            async for result in self._show_song_detail(event, song_id, platform, capabilities):
                yield result
        finally:
            if COMMON_MODULES_AVAILABLE and loading_msg_id:
                await LoadingIndicator.hide(event, loading_msg_id)
    
    async def _handle_download_callback(self, event: AstrMessageEvent, callback_data: Dict):
        """处理下载回调"""
        song_id = callback_data.get("song_id", "")
        platform = callback_data.get("platform", "qq")
        quality = callback_data.get("quality", "128")
        
        async for result in self._handle_download(event, song_id, platform, quality):
            yield result
    
    async def _handle_lyric_callback(self, event: AstrMessageEvent, callback_data: Dict):
        """处理歌词回调"""
        song_id = callback_data.get("song_id", "")
        platform = callback_data.get("platform", "qq")
        
        async for result in self._show_lyric(event, song_id, platform):
            yield result
    
    async def _handle_page_callback(self, event: AstrMessageEvent, callback_data: Dict, capabilities: Dict):
        """处理翻页回调"""
        keyword = callback_data.get("keyword", "")
        platform = callback_data.get("platform", "qq")
        page = callback_data.get("page", 1)
        
        # 按钮模式下使用轻量级的 typing 状态，不发送实际消息
        if COMMON_MODULES_AVAILABLE:
            await LoadingIndicator.send_typing(event)
        
        result = await self.music_api.search(keyword, platform, page, self.PAGE_SIZE)
        songs = result.get("songs", [])
        total = result.get("total", 0)
        
        message, _ = MusicFormatter.format_search_results(
            songs, page, self.PAGE_SIZE, total, platform, keyword, False
        )
        builder = MusicResponseBuilder(capabilities)
        keyboard = builder.build_search_keyboard(songs, keyword, page, self.PAGE_SIZE, total, platform)
        
        if COMMON_MODULES_AVAILABLE:
            async for r in MessageEditor.edit_or_send(event, message, keyboard):
                yield r
        else:
            yield event.chain_result([Plain(message), keyboard]) if keyboard else event.plain_result(message)
    
    async def _handle_switch_callback(self, event: AstrMessageEvent, callback_data: Dict, capabilities: Dict):
        """处理换源回调"""
        keyword = callback_data.get("keyword", "")
        platform = callback_data.get("platform", "qq")
        
        # 按钮模式下使用轻量级的 typing 状态，不发送实际消息
        if COMMON_MODULES_AVAILABLE:
            await LoadingIndicator.send_typing(event)
        
        result = await self.music_api.search(keyword, platform, 1, self.PAGE_SIZE)
        songs = result.get("songs", [])
        total = result.get("total", 0)
        
        message, _ = MusicFormatter.format_search_results(
            songs, 1, self.PAGE_SIZE, total, platform, keyword, False
        )
        builder = MusicResponseBuilder(capabilities)
        keyboard = builder.build_search_keyboard(songs, keyword, 1, self.PAGE_SIZE, total, platform)
        
        if COMMON_MODULES_AVAILABLE:
            async for r in MessageEditor.edit_or_send(event, message, keyboard):
                yield r
        else:
            yield event.chain_result([Plain(message), keyboard]) if keyboard else event.plain_result(message)
    
    async def terminate(self):
        """插件卸载时的清理工作"""
        logger.info("[Music] 音乐插件正在卸载...")
        if self.session_manager:
            self.session_manager.cleanup_expired()
