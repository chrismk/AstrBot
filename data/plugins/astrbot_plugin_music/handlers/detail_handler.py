"""歌曲详情处理器"""

import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from astrbot.core.message.components import InlineKeyboard
from astrbot.core.message.components import Image

from ..music_api_client import MusicAPIClient
from ..db.database import DatabaseManager
from ..db.models import SongDetailCache
from ..utils.callback_encoder import CallbackEncoder
from ..utils.exceptions import MusicAPIError

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class DetailHandler:
    """歌曲详情处理器"""
    
    def __init__(
        self,
        music_api: MusicAPIClient,
        db: DatabaseManager,
        logger_param=None
    ):
        self.music_api = music_api
        self.db = db
        # logger_param已废弃，使用全局logger
        self.encoder = CallbackEncoder()
        self.QUALITY_MAP = {
            "128": "🎵 标准",
            "320": "🎧 高品质",
            "flac": "💎 无损",
            "hires": "Hi-Res",
            "jyeffect": "Jyeffect",
            "sky": "Sky",
            "master": "Master",
            "aac_96": "AAC 96k",
            "aac_48": "AAC 48k",
            "ogg_192": "OGG 192k",
            "ogg_96": "OGG 96k"
        }
        self.QUALITY_ORDER = ["128", "320", "flac", "hires", "jyeffect", "sky", "master", "aac_96", "aac_48", "ogg_192", "ogg_96"]
        self.NETEASE_QUALITY_MAP = {
            "standard": "128", "exhigh": "320", "lossless": "flac",
            "hires": "hires", "jyeffect": "jyeffect", "sky": "sky",
            "jymaster": "master"
        }

    def _get_from_detail_cache(self, song_id: str, platform: str) -> Optional[SongDetailCache]:
        """从详情缓存中获取数据"""
        try:
            return self.db.get_song_detail_cache(song_id, platform)
        except Exception as e:
            logger.warning(f"从详情缓存获取数据失败: {e}")
            return None

    async def handle_detail(
        self,
        user_id: str,
        callback_data: Dict[str, Any],
        bot_username: str = "zslraibot"
    ) -> tuple[Optional[str], str, InlineKeyboard]:
        """
        处理歌曲详情请求
        
        Args:
            user_id: 用户ID
            callback_data: 回调数据
            
        Returns:
            (封面URL, 消息文本, 内联键盘)
        """
        try:
            song_id = callback_data.get("song_id", "")
            platform = callback_data.get("platform", "netease")
            
            logger.debug(f"获取歌曲详情 - song_id: {song_id}, platform: {platform}")
            
            # 1. 优先从详情缓存获取
            cached_song = self._get_from_detail_cache(song_id, platform)
            
            if cached_song:
                logger.debug(f"从缓存加载歌曲详情: {song_id} @ {platform}")
                song_data = json.loads(cached_song.song_data)
            else:
                # 调用API获取完整的歌曲数据，包含所有音质
                song_data = await self.music_api.get_song_data(song_id, platform)
                
                if not song_data:
                    logger.warning(f"无法获取歌曲数据: song_id={song_id}, platform={platform}")
                    return None, "❌ 无法获取歌曲的详细信息，请稍后再试", InlineKeyboard([])
                
                # 缓存歌曲详情数据（1小时过期）
                try:
                    cache = SongDetailCache(
                        song_id=song_id,
                        music_platform=platform,
                        song_data=json.dumps(song_data, ensure_ascii=False),
                        created_time=datetime.now(),
                        expires_time=datetime.now() + timedelta(hours=1)
                    )
                    self.db.save_song_detail_cache(cache)
                    logger.debug(f"缓存歌曲详情: {song_id} @ {platform}")
                except Exception as e:
                    logger.warning(f"缓存歌曲详情失败: {e}")

            # 格式化详情
            cover_url = song_data.get("pic", song_data.get("cover_url"))
            message = self._format_song_detail(song_data, platform, bot_username)
            
            # 从返回数据中提取可用的音质
            available_qualities = []
            if platform == 'netease':
                actual_quality = song_data.get('quality_actual')
                if actual_quality:
                    standard_quality = self.NETEASE_QUALITY_MAP.get(actual_quality)
                    if standard_quality:
                        available_qualities = [standard_quality]
            else: # QQ音乐等平台
                urls = song_data.get("urls", {})
                available_qualities = [q for q, url in urls.items() if url] if urls else []
            
            # 检查是否有歌词
            has_lyrics = bool(song_data.get("lyric", "").strip())
            
            # 生成音质选择键盘
            keyboard = self._build_quality_keyboard(song_id, platform, available_qualities, has_lyrics, bot_username)
            
            logger.info(f"查看详情: {song_data.get('name')} ({song_id})")
            
            return cover_url, message, keyboard
            
        except Exception as e:
            logger.error(f"获取详情异常: {e}", exc_info=True)
            return None, f"❌ 获取详情失败: {e}", InlineKeyboard([])
    
    def _format_song_detail(self, song: Dict[str, Any], platform: str, bot_username: str = "zslraibot") -> str:
        """格式化歌曲详情"""
        name = song.get("name", "未知")
        artist = song.get("artist", "未知")
        album = song.get("album_name", song.get("album", "未知"))  # 优先使用 album_name
        duration = song.get("duration", 0)
        
        # 提取更多详细信息
        composer = song.get("composer", "")
        arranger = song.get("arranger", "")
        genre = song.get("genre", "")
        bpm = song.get("bpm", "")
        publish_time = song.get("publish_time", "")
        
        # 提取发行年份
        publish_year = ""
        if publish_time:
            try:
                publish_year = publish_time.split("-")[0] if "-" in str(publish_time) else str(publish_time)[:4]
            except:
                publish_year = ""
        
        # 仅在duration有效时格式化并添加
        if duration and duration > 0:
            minutes = duration // 60000
            seconds = (duration % 60000) // 1000
            duration_str = f"**{minutes}:{seconds:02d}**"
        else:
            duration_str = None
        
        platform_name = self.music_api.get_platform_name(platform)
        
        # 构建丰富的详情信息
        lines = [
            f"🎵 歌名：{name}",
            f"👤 歌手: {artist}",
            f"💿 专辑: {album}"
        ]
        
        # 添加发行年份（如果有）
        if publish_year:
            lines.append(f"📅 发行: {publish_year}年")
        # 添加音乐创作信息（如果有）
        if composer:
            lines.append(f"🎼 作曲: {composer}")
        if arranger:
            lines.append(f"🎹 编曲: {arranger}")
        if duration_str:
            lines.append(f"⏱️ 时长: {duration_str}")
        # 添加音乐风格和BPM（如果有）
        music_info = []
        if genre:
            music_info.append(f"🎭 风格: {genre}")
        if bpm:
            music_info.append(f"🥁 BPM: {bpm}")
        
        if music_info:
            lines.append("")
            lines.extend(music_info)
        
        # 添加平台信息
        lines.extend([
            "",
            f"via @{bot_username}",
            "",
            "💡 请选择音质下载:",
        ])
        
        return "\n".join(lines)
    
    def _get_song_detail_url(self, platform: str, song_id: str) -> Optional[str]:
        """生成歌曲详情页URL"""
        if platform == 'netease':
            return f"https://music.163.com/#/song?id={song_id}"
        elif platform == 'qq':
            return f"https://y.qq.com/n/ryqq/songDetail/{song_id}"
        return None
    
    def _build_quality_keyboard(
        self,
        song_id: str,
        platform: str,
        available_qualities: list[str],
        has_lyrics: bool = False,
        bot_username: str = "zslraibot"
    ) -> InlineKeyboard:
        """根据可用音质列表构建键盘"""
        buttons = []
        all_buttons = []  # 存储所有按钮，统一排列
        
        # 定义音质显示名称和顺序
        quality_map = {
            "128": "🎵 标准",
            "320": "🎧 高品质",
            "flac": "💎 无损",
            "aac_96": "AAC 96k",
            "aac_48": "AAC 48k",
            "ogg_192": "OGG 192k",
            "ogg_96": "OGG 96k"
        }
        
        # 按照预定顺序排序可用音质
        sorted_qualities = sorted(
            available_qualities,
            key=lambda q: list(quality_map.keys()).index(q) if q in quality_map else 99
        )
        
        # 生成音质下载按钮（深度链接）
        for quality in sorted_qualities:
            display_name = quality_map.get(quality, quality)
            # 生成深度链接参数
            deep_link_param = f"music_{platform}_{song_id}_{quality}"
            deep_link_url = f"https://t.me/{bot_username}/?start={deep_link_param}"
            all_buttons.append({"text": display_name, "url": deep_link_url})
        
        # 如果有歌词，添加歌词按钮（改为深度链接）
        if has_lyrics:
            lyric_deep_link_param = f"lyric_{platform}_{song_id}"
            lyric_deep_link_url = f"https://t.me/{bot_username}/?start={lyric_deep_link_param}"
            all_buttons.append({"text": "📝 获取歌词", "url": lyric_deep_link_url})
        
        # 添加歌曲详情按钮
        detail_url = self._get_song_detail_url(platform, song_id)
        if detail_url:
            all_buttons.append({"text": "ℹ️ 歌曲详情", "url": detail_url})

        # 统一排列所有按钮，每行最多3个
        for idx in range(0, len(all_buttons), 3):
            row = all_buttons[idx:idx+3]
            buttons.append(row)
            
        return InlineKeyboard(buttons)

