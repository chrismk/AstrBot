"""下载处理器"""

import json
from typing import Dict, Any, Optional
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Audio

from ..music_api_client import MusicAPIClient
from ..db.database import DatabaseManager
from .telegram_file_cache import FileCacheManager
from ..utils.exceptions import MusicAPIError, QuotaExceededError

try:
    from astrbot.api import logger
    from common import LoadingIndicator
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    LoadingIndicator = None


class DownloadHandler:
    """下载处理器"""
    
    def __init__(
        self,
        music_api: MusicAPIClient,
        db: DatabaseManager,
        quota_mgr,  # 已废弃，保留兼容
        cache_mgr: FileCacheManager,
        telegram_api=None,  # 已废弃，保留兼容
        logger_param=None,
        common_quota_validator=None  # 通用配额验证器
    ):
        self.music_api = music_api
        self.db = db
        self.cache_mgr = cache_mgr
        self.common_quota_validator = common_quota_validator
    
    async def handle_download(
        self,
        user_id: str,
        chat_id: str,
        callback_data: Dict[str, Any],
        event: AstrMessageEvent
    ) -> Optional[str]:
        """
        处理下载请求
        
        Args:
            user_id: 用户ID
            chat_id: 聊天ID
            callback_data: 回调数据
            event: 消息事件对象
            
        Returns:
            状态消息 or None on success
        """
        song_id = callback_data.get("song_id", "")
        platform = callback_data.get("platform", "netease")
        quality = callback_data.get("quality", "standard")
        
        logger.debug(f"处理下载 - song_id: {song_id}, platform: {platform}, quality: {quality}")

        loading_msg_id = None
        try:
            # 1. 发送进度提示消息（使用统一的 LoadingIndicator）
            if LoadingIndicator:
                loading_msg_id = await LoadingIndicator.show(event, 'download')

            # 2. 执行下载和发送逻辑
            bot_username = event.get_self_id() or "zslraibot"
            return await self._execute_download(event, user_id, chat_id, callback_data, bot_username)

        finally:
            # 3. 删除进度提示消息
            if LoadingIndicator:
                await LoadingIndicator.hide(event, loading_msg_id)

    def _build_caption(self, song: Dict[str, Any], platform: str, quality: str, bot_username: str) -> str:
        """构建Caption文本"""
        song_name = song.get("name", "未知歌曲")
        artist = song.get("artist", "未知")
        album = song.get("album_name", song.get("album", "未知专辑"))
        
        composer = song.get("composer", "")
        arranger = song.get("arranger", "")
        genre = song.get("genre", "")
        bpm = song.get("bpm", "")
        publish_time = song.get("publish_time", "")
        
        publish_year = ""
        if publish_time:
            try:
                publish_year = publish_time.split("-")[0] if "-" in str(publish_time) else str(publish_time)[:4]
            except:
                publish_year = ""

        quality_map = {
            "128": "标准音质",
            "320": "较高音质",
            "flac": "无损音质",
            "aac_96": "AAC 96k",
            "aac_48": "AAC 48k",
            "ogg_192": "OGG 192k",
            "ogg_96": "OGG 96k"
        }
        quality_name = quality_map.get(quality, quality)
        
        caption_parts = [
            f"👤 歌手: {artist}",
            f"💿 专辑: {album}"
        ]
        
        if publish_year:
            caption_parts.append(f"📅 发行: {publish_year}年")
        
        if composer:
            caption_parts.append(f"🎼 作曲: {composer}")
        if arranger:
            caption_parts.append(f"🎹 编曲: {arranger}")
        
        music_info = []
        if genre:
            music_info.append(f"🎭 风格: {genre}")
        if bpm:
            music_info.append(f"🥁 BPM: {bpm}")
        
        if music_info:
            caption_parts.append("")
            caption_parts.extend(music_info)
        
        caption_parts.extend([
            "",
            f"💎 音质: {quality_name}",
            "",
            f"#{artist} #{song_name}",
            "",
            f"via @{bot_username}",
            "",
        ])
        
        return "\n".join(caption_parts)

    async def _execute_download(
        self,
        event: AstrMessageEvent,
        user_id: str,
        chat_id: str,
        callback_data: Dict[str, Any],
        bot_username: str = "zslraibot"
    ) -> Optional[str]:
        """封装核心的下载和发送逻辑"""
        song_id = callback_data.get("song_id", "")
        platform = callback_data.get("platform", "netease")
        quality = callback_data.get("quality", "standard")
        
        # 0. 优先检查 File ID 缓存 (完整缓存)
        file_cache = self.cache_mgr.get_cache(song_id, platform, quality)
        if file_cache:
            # 检查配额
            quota_check_result = None
            if self.common_quota_validator:
                try:
                    action_type = f"music_download_{quality}"
                    quota_check_result = await self.common_quota_validator.check_quota(
                        user_id=user_id,
                        action_type=action_type,
                        plugin_name="music",
                        use_points=True
                    )
                    if not quota_check_result.allowed:
                        return quota_check_result.message
                except Exception as e:
                    logger.error(f"配额检查失败: {e}", exc_info=True)
                    return "❌ 配额检查失败，请稍后重试"
            
            # 构建 Caption
            caption = file_cache.caption
            if not caption:
                # 如果缓存没有caption，尝试重新构建
                song = None
                try:
                    detail_cache = self.db.get_song_detail_cache(song_id, platform)
                    if detail_cache:
                        song = json.loads(detail_cache.song_data)
                except Exception:
                    pass
                
                if song:
                    caption = self._build_caption(song, platform, quality, bot_username)
                else:
                    # 简易 Caption
                    quality_map = {
                        "128": "标准音质", "320": "较高音质", "flac": "无损音质",
                        "aac_96": "AAC 96k", "aac_48": "AAC 48k", "ogg_192": "OGG 192k", "ogg_96": "OGG 96k"
                    }
                    quality_name = quality_map.get(quality, quality)
                    caption = f"👤 歌手: {file_cache.performer}\n💎 音质: {quality_name}\n#{file_cache.performer} #{file_cache.title}\n\nvia @{bot_username}"

            # 使用缓存发送
            try:
                audio = Audio.fromFileId(
                    file_id=file_cache.file_id,
                    title=file_cache.title,
                    performer=file_cache.performer,
                    caption=caption
                )
                audio.duration = file_cache.duration
                
                await event.send(MessageChain([audio]))
                
                self.cache_mgr.increment_use_count(song_id, platform, quality)
                
                if self.common_quota_validator and quota_check_result:
                    await self.common_quota_validator.consume_quota(
                        user_id=user_id,
                        action_type=f"music_download_{quality}",
                        plugin_name="music",
                        points_cost=quota_check_result.points_cost
                    )
                
                logger.info(f"✅ 缓存命中发送成功: {file_cache.title}")
                return None
                
            except Exception as e:
                logger.warning(f"缓存发送失败，标记失效: {e}")
                self.cache_mgr.mark_invalid(song_id, platform, quality)
                # 继续下面的流程
        
        try:
            song = None
            # 1. 优先尝试从歌曲详情缓存获取（包含完整的urls数据）
            try:
                detail_cache = self.db.get_song_detail_cache(song_id, platform)
                if detail_cache:
                    song = json.loads(detail_cache.song_data)
                    logger.info(f"从歌曲详情缓存获取数据: {song.get('name')}")
            except Exception as e:
                logger.warning(f"从歌曲详情缓存获取失败: {e}")

            # 2. 如果缓存未命中，直接从API获取
            if not song:
                logger.info(f"缓存未命中，从API获取歌曲信息: song_id={song_id}")
                song = await self.music_api.get_song_data(song_id, platform, quality)

            if not song:
                logger.warning(f"无法获取歌曲信息: song_id={song_id}, platform={platform}")
                return "❌ 歌曲信息已过期或无法获取，请重新搜索"
            
            # 提取歌曲信息
            song_name = song.get("name", "未知歌曲")
            artist = song.get("artist", "未知")
            duration_ms = song.get("duration", 0)
            
            caption = self._build_caption(song, platform, quality, bot_username)
            
            # 1. 检查配额
            quota_check_result = None
            if self.common_quota_validator:
                try:
                    action_type = f"music_download_{quality}"
                    quota_check_result = await self.common_quota_validator.check_quota(
                        user_id=user_id,
                        action_type=action_type,
                        plugin_name="music",
                        use_points=True
                    )
                    
                    if not quota_check_result.allowed:
                        return quota_check_result.message
                except Exception as e:
                    logger.error(f"配额检查失败: {e}", exc_info=True)
                    return "❌ 配额检查失败，请稍后重试"
            else:
                logger.error("通用配额系统未初始化")
                return "❌ 配额系统未初始化，请联系管理员"
            
            # 2. 检查File ID缓存
            cached_file_id = self.cache_mgr.get_cached_file_id(song_id, platform, quality)
            duration_sec = duration_ms // 1000 if duration_ms else 0
            cover_url = song.get("pic", song.get("cover", ""))
            
            if cached_file_id:
                # 使用缓存发送
                try:
                    audio = Audio.fromFileId(
                        file_id=cached_file_id,
                        title=song_name,
                        performer=artist,
                        caption=caption
                    )
                    audio.duration = duration_sec
                    
                    # 通过 event 发送
                    await event.send(MessageChain([audio]))
                    
                    # 成功，增加使用次数
                    self.cache_mgr.increment_use_count(song_id, platform, quality)
                    
                    # 消耗配额
                    if self.common_quota_validator and quota_check_result:
                        await self.common_quota_validator.consume_quota(
                            user_id=user_id,
                            action_type=f"music_download_{quality}",
                            plugin_name="music",
                            points_cost=quota_check_result.points_cost
                        )
                    
                    logger.info(f"✅ 缓存命中发送成功: {song_name}")
                    return None
                    
                except Exception as e:
                    logger.warning(f"缓存发送失败，尝试URL发送: {e}")
                    self.cache_mgr.mark_invalid(song_id, platform, quality)
            
            # 3. 获取播放URL
            play_url = None
            
            if platform == 'netease':
                if song:
                    play_url = song.get('url')
                if play_url:
                    logger.info("从缓存的网易云音乐数据中获取播放链接")
            else:
                if song and "urls" in song:
                    urls = song.get("urls", {})
                    play_url = urls.get(quality)
                    if play_url:
                        logger.info(f"从缓存数据中获取播放链接: {quality}")
            
            if not play_url:
                logger.info(f"缓存无有效URL，从API获取新链接: {song_id}@{platform}:{quality}")
                fresh_song_data = await self.music_api.get_song_data(song_id, platform, quality)
                
                if fresh_song_data:
                    if platform == 'netease':
                        play_url = fresh_song_data.get('url')
                    else:
                        play_url = fresh_song_data.get('urls', {}).get(quality)
            
            if not play_url:
                logger.error(f"播放链接获取失败: song_id={song_id}, platform={platform}, quality={quality}")
                return f"❌ 无法获取{quality}音质的播放链接，该音质可能不可用"
            
            logger.info(f"播放链接获取成功: {play_url[:100]}...")
            
            # 4. 通过URL发送音频（使用 Audio 组件）
            try:
                audio = Audio.fromURL(
                    url=play_url,
                    title=song_name,
                    performer=artist,
                    duration=duration_sec,
                    thumbnail=cover_url,
                    caption=caption
                )
                
                # 通过 event 发送，获取返回结果
                send_result = await event.send(MessageChain([audio]))
                
                # 从发送结果中提取 file_id 并缓存
                if send_result:
                    audio_info = send_result.get("audio")
                    if audio_info and audio_info.get("file_id"):
                        # 将生成的 caption 加入 info
                        audio_info["caption"] = caption
                        
                        self.cache_mgr.save_file_id(
                            song_id=song_id,
                            platform=platform,
                            quality=quality,
                            file_id=audio_info["file_id"],
                            file_info=audio_info,
                            uploaded_by=user_id
                        )
                        logger.info(f"已缓存 file_id: {audio_info['file_id'][:20]}...")
                
                # 消耗配额
                if self.common_quota_validator and quota_check_result:
                    await self.common_quota_validator.consume_quota(
                        user_id=user_id,
                        action_type=f"music_download_{quality}",
                        plugin_name="music",
                        points_cost=quota_check_result.points_cost
                    )
                
                logger.info(f"✅ URL发送成功: {song_name}")
                return None
                    
            except Exception as e:
                logger.error(f"发送音频失败: {e}", exc_info=True)
                return "❌ 发送失败，请稍后重试"
            
        except QuotaExceededError as e:
            logger.warning(f"配额超限: {e}")
            return f"❌ {e}"
        except MusicAPIError as e:
            logger.error(f"音乐API错误: {e}", exc_info=True)
            # 不暴露详细错误信息给用户
            return "❌ 获取音乐失败，请稍后重试"
        except Exception as e:
            logger.error(f"下载处理异常: {e}", exc_info=True)
            # 不暴露详细错误信息给用户
            return "❌ 处理失败，请稍后重试"

