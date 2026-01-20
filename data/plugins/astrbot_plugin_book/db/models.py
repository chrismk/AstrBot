"""数据模型"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class BookSearchCache:
    """书籍搜索结果缓存"""
    cache_key: str
    user_id: str
    keyword: str
    results: str  # JSON字符串
    total_count: int
    current_page: int
    created_time: datetime
    id: Optional[int] = None


@dataclass
class BookDownloadHistory:
    """书籍下载历史记录"""
    user_id: str
    book_ssid: str
    book_title: str
    author: str
    file_format: str
    file_size: int
    download_time: datetime
    id: Optional[int] = None


@dataclass
class UserBookQuota:
    """用户书籍下载配额"""
    user_id: str
    daily_quota: int  # 每日下载次数限制
    is_vip: int  # 0普通用户/1VIP
    created_time: datetime
    updated_time: datetime
    id: Optional[int] = None


@dataclass
class TelegramBookFileCache:
    """Telegram文件缓存"""
    book_ssid: str
    file_format: str
    file_tag: str # 文件唯一标识 (文件大小+格式)
    file_id: str
    file_size: Optional[int] = None
    file_name: Optional[str] = None
    book_info: Optional[str] = None  # 存储书籍详细信息的JSON字符串
    mime_type: Optional[str] = None
    uploaded_by: Optional[str] = None
    upload_time: Optional[datetime] = None
    use_count: int = 0
    is_valid: int = 1
    id: Optional[int] = None


@dataclass
class BookDetailCache:
    """书籍详情缓存"""
    book_ssid: str
    book_data: str  # JSON字符串，存储完整的书籍详情数据
    created_time: datetime
    expires_time: datetime
    id: Optional[int] = None
