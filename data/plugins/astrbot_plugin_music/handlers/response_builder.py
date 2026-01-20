"""
音乐搜索响应构建器
根据平台能力构建适当的响应（按钮模式或会话模式）
"""
import json
from typing import Dict, List, Any, Optional, Tuple
from astrbot.api import logger

try:
    from astrbot.core.message.components import InlineKeyboard
except ImportError:
    InlineKeyboard = None
    logger.warning("[MusicResponseBuilder] InlineKeyboard 不可用")


class MusicResponseBuilder:
    """音乐搜索响应构建器"""
    
    # 平台名称映射
    PLATFORM_NAMES = {
        "qq": "QQ音乐",
        "netease": "网易云"
    }
    
    # 可切换的平台列表
    SWITCHABLE_PLATFORMS = ["qq", "netease"]
    
    def __init__(self, capabilities: Dict[str, Any]):
        """
        初始化响应构建器
        
        Args:
            capabilities: 平台能力字典
        """
        self.capabilities = capabilities
        self.platform_name = capabilities.get('platform_name', '').lower()
        
        # 飞书平台目前按钮支持不完善，强制禁用
        if self.platform_name == "lark":
            self.supports_buttons = False
        else:
            self.supports_buttons = capabilities.get('supports_buttons', False)
    
    def is_button_mode(self) -> bool:
        """是否为按钮模式"""
        return self.supports_buttons and InlineKeyboard is not None
    
    def build_search_keyboard(
        self,
        songs: List[Dict],
        keyword: str,
        page: int,
        page_size: int,
        total: int,
        platform: str
    ) -> Optional[Any]:
        """
        构建搜索结果键盘
        
        Args:
            songs: 歌曲列表
            keyword: 搜索关键词
            page: 当前页码
            page_size: 每页数量
            total: 总数
            platform: 当前平台
            
        Returns:
            InlineKeyboard 或 None
        """
        if not self.supports_buttons or InlineKeyboard is None:
            return None
        
        keyboard = InlineKeyboard()
        use_json_format = self.platform_name == "lark"
        
        # 生成序号按钮
        number_buttons = []
        for i, song in enumerate(songs):
            song_id = song.get("id", "")
            
            if use_json_format:
                callback = json.dumps({
                    "action": "music_detail",
                    "song_id": str(song_id),
                    "platform": platform
                }, ensure_ascii=False)
            else:
                callback = f"music:detail:{platform}:{song_id}"
            
            btn_config = {"text": str(i + 1), "callback_data": callback}
            if use_json_format:
                 btn_config["button_size"] = "tiny"
                 btn_config["button_type"] = "default"

            number_buttons.append(btn_config)
        
        # 添加按钮行（每行8个）
        for i in range(0, len(number_buttons), 8):
             row = number_buttons[i:i+8]
             if row:
                keyboard.buttons.append(row)
        
        # 添加翻页按钮
        total_pages = max(1, (total + page_size - 1) // page_size)
        page_buttons = []
        
        # 上一页
        if page > 1:
            if use_json_format:
                prev_callback = json.dumps({
                    "action": "music_page",
                    "keyword": keyword,
                    "page": page - 1,
                    "platform": platform
                }, ensure_ascii=False)
            else:
                prev_callback = f"music:page:{platform}:{page - 1}:{keyword}"
            page_buttons.append({"text": "⬅️ 上页", "callback_data": prev_callback})
        
        # 回首页 (只在第3页及以上显示)
        if page >= 3:
            if use_json_format:
                home_callback = json.dumps({
                    "action": "music_page",
                    "keyword": keyword,
                    "page": 1,
                    "platform": platform
                }, ensure_ascii=False)
            else:
                home_callback = f"music:page:{platform}:1:{keyword}"
            page_buttons.append({"text": "🏠 首页", "callback_data": home_callback})

        # 下一页
        if page < total_pages:
            if use_json_format:
                next_callback = json.dumps({
                    "action": "music_page",
                    "keyword": keyword,
                    "page": page + 1,
                    "platform": platform
                }, ensure_ascii=False)
            else:
                next_callback = f"music:page:{platform}:{page + 1}:{keyword}"
            page_buttons.append({"text": "➡️ 下页", "callback_data": next_callback})
        
        if page_buttons:
            keyboard.buttons.append(page_buttons)
        
        # 添加换源按钮 + 退出按钮
        action_buttons = []
        try:
            current_index = self.SWITCHABLE_PLATFORMS.index(platform)
            next_index = (current_index + 1) % len(self.SWITCHABLE_PLATFORMS)
            next_platform = self.SWITCHABLE_PLATFORMS[next_index]
            next_platform_name = self.PLATFORM_NAMES.get(next_platform, next_platform)
            
            if use_json_format:
                switch_callback = json.dumps({
                    "action": "music_switch",
                    "keyword": keyword,
                    "platform": next_platform
                }, ensure_ascii=False)
            else:
                switch_callback = f"music:switch:{next_platform}:{keyword}"
                
            action_buttons.append({"text": f"🔄 切换源 ({next_platform_name})", "callback_data": switch_callback})
        except ValueError:
            pass
        
        # 添加退出按钮
        if use_json_format:
            exit_callback = json.dumps({
                "action": "music_exit",
                "delete_message": True
            }, ensure_ascii=False)
        else:
            exit_callback = "music:exit"
        action_buttons.append({"text": "❌ 退出", "callback_data": exit_callback})
            
        if action_buttons:
            keyboard.buttons.append(action_buttons)
        
        return keyboard
    
    def build_detail_keyboard(
        self,
        song_id: str,
        platform: str,
        available_qualities: List[str] = None,
        has_lyrics: bool = False,
        bot_username: str = "zslraibot"
    ) -> Optional[Any]:
        """
        构建歌曲详情键盘（使用深度链接）
        
        Args:
            song_id: 歌曲ID
            platform: 平台
            available_qualities: 可用音质列表
            has_lyrics: 是否有歌词
            bot_username: 机器人用户名
            
        Returns:
            InlineKeyboard 或 None
        """
        if not self.supports_buttons or InlineKeyboard is None:
            return None
        
        if not available_qualities:
            available_qualities = ["128", "320", "flac"]
        
        keyboard = InlineKeyboard()
        
        # 音质名称映射（与图片样式一致）
        quality_names = {
            "128": "🎵 标准",
            "320": "🎧 高品质",
            "flac": "💎 无损",
            "aac_96": "AAC 96k",
            "aac_48": "AAC 48k",
            "ogg_192": "OGG 192k",
            "ogg_96": "OGG 96k"
        }
        
        # 音质排序
        quality_order = ["128", "320", "flac", "aac_96", "aac_48", "ogg_192", "ogg_96"]
        sorted_qualities = sorted(
            available_qualities,
            key=lambda q: quality_order.index(q) if q in quality_order else 99
        )
        
        # 收集所有按钮
        all_buttons = []
        
        # 生成音质下载按钮（深度链接）
        for quality in sorted_qualities:
            display_name = quality_names.get(quality, quality)
            deep_link_param = f"music_{platform}_{song_id}_{quality}"
            deep_link_url = f"https://t.me/{bot_username}/?start={deep_link_param}"
            all_buttons.append({"text": display_name, "url": deep_link_url})
        
        # 如果有歌词，添加歌词按钮
        if has_lyrics:
            lyric_deep_link_param = f"lyric_{platform}_{song_id}"
            lyric_deep_link_url = f"https://t.me/{bot_username}/?start={lyric_deep_link_param}"
            all_buttons.append({"text": "📝 获取歌词", "url": lyric_deep_link_url})
        
        # 添加歌曲详情按钮（链接到原平台）
        detail_url = self._get_song_detail_url(platform, song_id)
        if detail_url:
            all_buttons.append({"text": "ℹ️ 歌曲详情", "url": detail_url})
        
        # 每行3个按钮
        for i in range(0, len(all_buttons), 3):
            row = all_buttons[i:i+3]
            keyboard.buttons.append(row)
        
        return keyboard
    
    def _get_song_detail_url(self, platform: str, song_id: str) -> Optional[str]:
        """生成歌曲详情页URL"""
        if platform == 'netease':
            return f"https://music.163.com/#/song?id={song_id}"
        elif platform == 'qq':
            return f"https://y.qq.com/n/ryqq/songDetail/{song_id}"
        elif platform == 'kugou':
            return f"https://www.kugou.com/song/#hash={song_id}"
        elif platform == 'kuwo':
            return f"https://www.kuwo.cn/play_detail/{song_id}"
        return None
    
    def build_empty_keyboard(
        self,
        keyword: str,
        current_platform: str
    ) -> Optional[Any]:
        """
        构建空结果键盘（仅换源按钮）
        
        Args:
            keyword: 搜索关键词
            current_platform: 当前平台
            
        Returns:
            InlineKeyboard 或 None
        """
        if not self.supports_buttons or InlineKeyboard is None:
            return None
        
        keyboard = InlineKeyboard()
        use_json_format = self.platform_name == "lark"
        
        # 添加换源按钮
        switch_buttons = []
        for p in self.SWITCHABLE_PLATFORMS:
            if p != current_platform:
                p_name = self.PLATFORM_NAMES.get(p, p)
                if use_json_format:
                    switch_callback = json.dumps({
                        "action": "music_switch",
                        "keyword": keyword,
                        "platform": p,
                        "page": 1
                    }, ensure_ascii=False)
                else:
                    switch_callback = f"music:switch:{p}:{keyword}:1"
                switch_buttons.append({"text": p_name, "callback_data": switch_callback})
                
                if len(switch_buttons) >= 3:
                    keyboard.buttons.append(switch_buttons)
                    switch_buttons = []
        
        if switch_buttons:
            keyboard.buttons.append(switch_buttons)
        
        return keyboard
