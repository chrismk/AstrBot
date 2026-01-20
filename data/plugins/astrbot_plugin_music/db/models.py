"""数据模型"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class SearchCache:
    """搜索结果缓存"""
    cache_key: str
    user_id: str
    keyword: str
    platform: str
    results: str  # JSON字符串
    total_count: int
    current_page: int
    created_time: datetime
    id: Optional[int] = None


@dataclass
class DownloadHistory:
    """下载历史记录"""
    user_id: str
    song_id: str
    song_name: str
    artist: str
    music_platform: str
    quality_level: str
    file_size: int
    download_time: datetime
    id: Optional[int] = None


@dataclass
class UserQuota:
    """用户配额配置"""
    user_id: str
    daily_quotas: str  # JSON字符串 e.g., '{"128": 50, "320": 20, "flac": 5}'
    is_vip: int  # 0普通用户/1VIP
    created_time: datetime
    updated_time: datetime
    id: Optional[int] = None


@dataclass
class TelegramFileCache:
    """Telegram文件缓存"""
    song_id: str
    music_platform: str
    quality_level: str
    file_id: str
    file_unique_id: Optional[str]
    file_size: Optional[int]
    file_name: Optional[str]
    duration: Optional[int]
    title: Optional[str]
    performer: Optional[str]
    caption: Optional[str]
    mime_type: Optional[str]
    uploaded_by: Optional[str]
    upload_time: datetime
    use_count: int
    is_valid: int  # 1有效/0失效
    id: Optional[int] = None


@dataclass
class SongDetailCache:
    """歌曲详情缓存"""
    song_id: str
    music_platform: str
    song_data: str  # JSON字符串，存储完整的歌曲详情数据
    created_time: datetime
    expires_time: datetime
    id: Optional[int] = None

