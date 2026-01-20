"""搜索处理器"""

import json
import hashlib
from typing import Dict, Any, List
from datetime import datetime

from astrbot.core.message.components import InlineKeyboard

from ..music_api_client import MusicAPIClient
from ..db.database import DatabaseManager
from ..db.models import SearchCache
from ..utils.callback_encoder import CallbackEncoder
from ..utils.exceptions import MusicAPIError

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class SearchHandler:
    """搜索命令处理器"""
    
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
    
    def _generate_cache_key(self, user_id: str, keyword: str, platform: str, page: int) -> str:
        """生成缓存键"""
        raw = f"{user_id}:{keyword}:{platform}:{page}"
        return hashlib.md5(raw.encode()).hexdigest()
    
    async def handle_search(
        self,
        user_id: str,
        keyword: str,
        platform: str = "netease",
        page: int = 1
    ) -> tuple[str, InlineKeyboard]:
        """
        处理搜索请求
        
        Args:
            user_id: 用户ID
            keyword: 搜索关键词
            platform: 平台
            page: 页码
            
        Returns:
            (消息文本, 内联键盘)
        """
        try:
            # 执行搜索
            logger.info(f"搜索音乐: {keyword} @ {platform} (第{page}页)")
            
            result = await self.music_api.search(
                keyword=keyword,
                platform=platform,
                page=page,
                limit=16
            )
            
            # 调试日志
            logger.debug(f"API返回结果类型: {type(result)}")
            logger.debug(f"API返回结果内容: {result}")
            
            songs = result.get("songs", [])
            total = result.get("total", 0)
            
            logger.debug(f"解析后songs数量: {len(songs)}, total: {total}")
            
            if not songs:
                logger.warning(f"未找到歌曲，原始结果: {result}")
                return "❌ 未找到相关歌曲", InlineKeyboard([])
            
            # 生成缓存键并保存
            cache_key = self._generate_cache_key(user_id, keyword, platform, page)
            logger.debug(f"生成缓存键: {cache_key} (user_id={user_id}, keyword={keyword}, platform={platform}, page={page})")
            
            cache = SearchCache(
                cache_key=cache_key,
                user_id=user_id,
                keyword=keyword,
                platform=platform,
                results=json.dumps(songs, ensure_ascii=False),
                total_count=total,
                current_page=page,
                created_time=datetime.now()
            )
            self.db.save_search_cache(cache)
            
            # 格式化消息
            message = self._format_search_results(songs, keyword, platform, page, total)
            
            # 生成键盘
            keyboard = self._build_search_keyboard(cache_key, songs, page, total, platform, keyword)
            
            return message, keyboard
            
        except MusicAPIError as e:
            logger.error(f"搜索失败: {e}", exc_info=True)
            return f"❌ 搜索失败: {e}", InlineKeyboard([])
        except Exception as e:
            logger.error(f"搜索异常: {e}", exc_info=True)
            return f"❌ 搜索出错: {e}", InlineKeyboard([])
    
    def _format_search_results(
        self,
        songs: List[Dict[str, Any]],
        keyword: str,
        platform: str,
        page: int,
        total: int
    ) -> str:
        """格式化搜索结果"""
        lines = []
        
        for idx, song in enumerate(songs, 1):
            name = song.get("name", "未知")
            artist = song.get("artist", "未知")
            duration = song.get("duration", 0)
            
            minutes = duration // 60000
            seconds = (duration % 60000) // 1000
            duration_str = f"{minutes}:{seconds:02d}"
            
            lines.append(f"{idx}. {name} - {artist} [{duration_str}]")
        
        # 获取平台显示名称（只包含已完善的平台）
        platform_names = {
            "qq": "QQ音乐",
            "netease": "网易云",
            # "kugou": "酷狗",  # 开发中，暂时隐藏
            #"kuwo": "酷我"
        }
        platform_display = platform_names.get(platform, platform.upper())
        
        lines.append("")
        lines.append(f"💡 点击数字查看详情 | 第 {page} 页 | 共 {total} 首 | {platform_display}")
        
        return "\n".join(lines)
    
    def _build_search_keyboard(
        self,
        cache_key: str,
        songs: List[Dict[str, Any]],
        page: int,
        total: int,
        platform: str,
        keyword: str
    ) -> InlineKeyboard:
        """构建搜索结果键盘"""
        buttons = []
        
        # 详情按钮（数字），每行最多8个
        detail_buttons = []
        for i, song in enumerate(songs):
            callback_data = self.encoder.encode_detail(
                platform=platform,
                song_id=str(song.get("id", ""))
            )
            detail_buttons.append({"text": str(i + 1), "callback_data": callback_data})

        for i in range(0, len(detail_buttons), 8):
            buttons.append(detail_buttons[i:i+8])

        # 翻页按钮
        nav_row = []
        
        if page > 1:
            prev_callback = self.encoder.encode_page(keyword=keyword, platform=platform, page=page - 1)
            nav_row.append({"text": "⬅️ 上一页", "callback_data": prev_callback})
        
        home_callback = self.encoder.encode_page(keyword=keyword, platform=platform, page=1)
        nav_row.append({"text": "🏠 首页", "callback_data": home_callback})
        
        # 判断是否有下一页（每页16首）
        if len(songs) >= 16:
            next_callback = self.encoder.encode_page(keyword=keyword, platform=platform, page=page + 1)
            nav_row.append({"text": "➡️ 下一页", "callback_data": next_callback})
        
        if nav_row:
            buttons.append(nav_row)
        
        # 换源搜按钮
        switch_row = []
        
        # 定义可用的音乐源（只包含已完善的平台）
        available_sources = {
            "qq": "🎵 QQ音乐",
            "netease": "🎧 网易云",
            # "kugou": "🎤 酷狗",  # 开发中，暂时隐藏
            #"kuwo": "🎶 酷我"
        }
        
        # 添加其他源的按钮（排除当前源）
        for source_key, source_name in available_sources.items():
            if source_key != platform:
                switch_callback = self.encoder.encode_switch_source(
                    keyword=keyword,
                    current_platform=platform,
                    target_platform=source_key
                )
                switch_row.append({"text": source_name, "callback_data": switch_callback})
        
        # 每行最多放2个换源按钮
        for i in range(0, len(switch_row), 2):
            buttons.append(switch_row[i:i+2])
        
        return InlineKeyboard(buttons)
    
    async def handle_switch_source(self, callback_data: Dict[str, Any]) -> tuple[str, InlineKeyboard]:
        """
        处理换源搜索请求
        
        Args:
            callback_data: 回调数据
            
        Returns:
            (消息文本, 内联键盘)
        """
        keyword = callback_data.get("keyword", "")
        target_platform = callback_data.get("target_platform", "netease")
        
        if not keyword:
            return "❌ 搜索参数丢失，请重新搜索", InlineKeyboard([])
        
        # 使用固定的用户ID（从最近缓存中获取）
        recent_caches = self.db.get_recent_search_caches(limit=5)
        user_id = "default"
        if recent_caches:
            user_id = recent_caches[0].user_id
        
        # 使用新的平台重新搜索
        return await self.handle_search(
            user_id=user_id,
            keyword=keyword,
            platform=target_platform,
            page=1  # 换源后重置到第一页
        )
    
    async def handle_page_change(self, callback_data: Dict[str, Any]) -> tuple[str, InlineKeyboard]:
        """
        处理翻页请求
        
        Args:
            callback_data: 回调数据
            
        Returns:
            (消息文本, 内联键盘)
        """
        keyword = callback_data.get("keyword", "")
        platform = callback_data.get("platform", "netease")
        new_page = callback_data.get("page", 1)
        
        if not keyword:
            return "❌ 搜索参数丢失，请重新搜索", InlineKeyboard([])
        
        # 使用固定的用户ID（从最近缓存中获取）
        recent_caches = self.db.get_recent_search_caches(limit=5)
        user_id = "default"
        if recent_caches:
            user_id = recent_caches[0].user_id
        
        # 重新搜索新页
        return await self.handle_search(
            user_id=user_id,
            keyword=keyword,
            platform=platform,
            page=new_page
        )

