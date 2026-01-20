"""
音乐格式化器
负责格式化搜索结果和歌曲详情的显示
"""
from typing import Dict, List, Any, Optional, Tuple
import sys
from pathlib import Path
plugin_root = Path(__file__).parent.parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))
from common.message_formatter import get_separator


class MusicFormatter:
    """音乐格式化工具类"""
    
    # 平台名称映射
    PLATFORM_NAMES = {
        "qq": "QQ音乐",
        "netease": "网易云",
        "kugou": "酷狗",
        "kuwo": "酷我",
        "migu": "咪咕"
    }
    
    # 音质名称映射
    QUALITY_NAMES = {
        "128": "标准 128K",
        "320": "高品 320K",
        "flac": "无损 FLAC",
        "aac_96": "AAC 96K",
        "aac_48": "AAC 48K",
        "ogg_192": "OGG 192K",
        "ogg_96": "OGG 96K"
    }
    
    @classmethod
    def format_search_results(
        cls,
        songs: List[Dict],
        page: int,
        page_size: int,
        total: int,
        platform: str,
        keyword: str,
        show_hints: bool = False,
        timeout_minutes: int = 1
    ) -> Tuple[str, None]:
        """
        格式化搜索结果列表
        
        Args:
            songs: 歌曲列表
            page: 当前页码
            page_size: 每页数量
            total: 总数
            platform: 平台
            keyword: 搜索关键词
            show_hints: 是否显示操作提示（会话模式）
            timeout_minutes: 会话超时时间
            
        Returns:
            (格式化的消息, None)
        """
        if not songs:
            return f"❌ 未找到「{keyword}」相关歌曲", None
        
        platform_name = cls.PLATFORM_NAMES.get(platform, platform)
        total_pages = max(1, (total + page_size - 1) // page_size)
        
        lines = []
        
        for i, song in enumerate(songs, 1):
            name = song.get("name", "未知歌曲")
            artist = song.get("artist", "未知歌手")
            # 截断过长的歌曲名和歌手名
            if len(name) > 20:
                name = name[:18] + "..."
            if len(artist) > 15:
                artist = artist[:13] + "..."
            lines.append(f"{i}. {name} - {artist}")
        
        lines.append("")
        separator = get_separator()
        lines.append(separator)
        lines.append(f"🎵 {platform_name} 搜索结果 (第 {page}/{total_pages} 页，共 {total} 首)")
        
        if show_hints:
            # 添加导航提示（仅会话模式，按钮模式不显示）
            lines.append("💡 请输入序号查看详情")
            
            nav_parts = []
            if page > 1:
                nav_parts.append("p-上页")
            if page < total_pages:
                nav_parts.append("n-下页")
            if page >= 3:
                nav_parts.append("h-首页")
            
            # 显示下一个平台（只支持 QQ音乐 和 网易云）
            if platform == "qq":
                nav_parts.append("s-网易云")
            else:
                nav_parts.append("s-QQ音乐")
            
            nav_parts.append("0-退出")
            
            lines.append(f"💡 {' | '.join(nav_parts)}")
            lines.append(f"⏱️ 请在 {timeout_minutes} 分钟内输入")
        else:
            lines.append(separator)
        
        return "\n".join(lines), None
    
    @classmethod
    def format_song_detail(
        cls,
        song: Dict,
        platform: str,
        available_qualities: List[str] = None,
        bot_username: str = "zslraibot"
    ) -> str:
        """
        格式化歌曲详情
        
        Args:
            song: 歌曲信息
            platform: 平台
            available_qualities: 可用音质列表
            bot_username: 机器人用户名
            
        Returns:
            格式化的详情文本
        """
        name = song.get("name", "未知歌曲")
        artist = song.get("artist", "未知歌手")
        album = song.get("album_name") or song.get("album", "未知专辑")
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
        
        # 格式化时长（毫秒转换）
        duration_str = None
        if duration and duration > 0:
            if duration > 1000:  # 毫秒
                minutes = duration // 60000
                seconds = (duration % 60000) // 1000
            else:  # 秒
                minutes = duration // 60
                seconds = duration % 60
            duration_str = f"{minutes}:{seconds:02d}"
        
        # 构建详情信息
        lines = [
            f"🎵 歌名：{name}",
            f"👤 歌手: {artist}",
            f"💿 专辑: {album}"
        ]
        
        # 添加时长
        if duration_str:
            lines.append(f"⏱️ 时长: {duration_str}")
        
        # 添加发行年份
        if publish_year:
            lines.append(f"📅 发行: {publish_year}年")
        
        # 添加音乐创作信息
        if composer:
            lines.append(f"🎼 作曲: {composer}")
        if arranger:
            lines.append(f"🎹 编曲: {arranger}")
        
        # 添加音乐风格和BPM
        if genre:
            lines.append(f"🎭 风格: {genre}")
        if bpm:
            lines.append(f"🥁 BPM: {bpm}")
        
        # 添加平台信息
        lines.extend([
            "",
            f"via @{bot_username}",
            "",
            "💡 请选择音质下载:",
        ])
        
        return "\n".join(lines)
    
    @classmethod
    def format_download_buttons(
        cls,
        song_id: str,
        platform: str,
        available_qualities: List[str] = None
    ) -> List[Dict]:
        """
        格式化下载按钮信息
        
        Args:
            song_id: 歌曲ID
            platform: 平台
            available_qualities: 可用音质列表
            
        Returns:
            按钮信息列表 [{"text": "按钮文本", "quality": "音质代码"}, ...]
        """
        if not available_qualities:
            available_qualities = ["128", "320", "flac"]
        
        buttons = []
        for quality in available_qualities:
            quality_name = cls.QUALITY_NAMES.get(quality, quality)
            buttons.append({
                "text": f"⬇️ {quality_name}",
                "quality": quality,
                "song_id": song_id,
                "platform": platform
            })
        
        return buttons
    
    @classmethod
    def format_lyric(cls, lyric_content: str) -> str:
        """
        格式化歌词内容
        
        Args:
            lyric_content: 原始歌词内容（LRC格式）
            
        Returns:
            格式化后的歌词
        """
        if not lyric_content or not lyric_content.strip():
            return "❌ 歌词内容为空"
        
        lines = []
        lyric_lines = lyric_content.strip().split('\n')
        
        # 提取歌曲信息
        song_info = []
        lyric_body = []
        
        for line in lyric_lines:
            line = line.strip()
            if not line:
                continue
            
            # 检查是否是标签行
            if line.startswith('[') and ']:' in line and not line.startswith('[0'):
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
                    try:
                        last_bracket = line.rfind(']')
                        if last_bracket != -1:
                            lyric_text = line[last_bracket + 1:].strip()
                            if lyric_text:
                                lyric_body.append(lyric_text)
                    except:
                        lyric_body.append(line)
                else:
                    lyric_body.append(line)
        
        # 组装结果
        if song_info:
            lines.extend(song_info)
            lines.append("")
        
        if lyric_body:
            lines.append("")
            lines.extend(lyric_body)
        else:
            lines.append("❌ 未找到有效歌词内容")
        
        # 限制长度
        result = "\n".join(lines)
        if len(result) > 4000:
            result = result[:3900] + "\n\n... (歌词过长，已截断)"
        
        return result
    
    @classmethod
    def get_platform_icon(cls, platform: str) -> str:
        """获取平台图标"""
        icons = {
            "qq": "🟢",
            "netease": "🔴",
            "kugou": "🔵",
            "kuwo": "🟡",
            "migu": "🟣"
        }
        return icons.get(platform, "🎵")
