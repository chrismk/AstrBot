"""配额管理器"""

import json
from typing import Dict, Optional, Any
from datetime import datetime

from .db.database import DatabaseManager
from .db.models import UserQuota, DownloadHistory
from .utils.exceptions import QuotaExceededError

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class QuotaManager:
    """配额管理器"""

    def __init__(self, db: DatabaseManager, default_quotas: Dict[str, Any], vip_multiplier: int = 3):
        self.db = db
        self.default_quotas = default_quotas
        self.vip_multiplier = vip_multiplier
    
    def get_user_quota(self, user_id: str) -> UserQuota:
        """
        获取用户配额，不存在则创建
        """
        quota = self.db.get_user_quota(user_id)
        if not quota:
            quota = self.db.create_default_quota(user_id, self.default_quotas)
            logger.info(f"为用户 {user_id} 创建默认配额")
        return quota
    
    def check_quota(self, user_id: str, quality: str) -> bool:
        """
        检查用户配额是否充足 (动态)
        """
        quota_obj = self.get_user_quota(user_id)
        if not quota_obj:
            return False
            
        # 获取用户的所有配额设置
        try:
            user_quotas = json.loads(quota_obj.daily_quotas)
        except (json.JSONDecodeError, TypeError):
            user_quotas = self.default_quotas

        # 获取特定音质的配额上限
        limit = user_quotas.get(quality, 0)
        
        # VIP用户倍数加成
        if quota_obj.is_vip:
            limit *= self.vip_multiplier
            
        # 获取今日已使用次数
        used_count = self.db.get_user_daily_downloads(user_id, quality)
        
        has_quota = used_count < limit
        
        if not has_quota:
            logger.info(f"用户 {user_id} 配额不足: {quality} {used_count}/{limit}")
        
        return has_quota
    
    def consume_quota(
        self,
        user_id: str,
        song_id: str,
        song_name: str,
        artist: str,
        platform: str,
        quality: str,
        file_size: int = 0
    ) -> bool:
        """
        消耗配额并记录下载历史
        """
        if not self.check_quota(user_id, quality):
            raise QuotaExceededError(
                f"今日{quality}配额已用完",
                quota_type=quality
            )
        
        # 记录下载历史
        history = DownloadHistory(
            user_id=user_id,
            song_id=song_id,
            song_name=song_name,
            artist=artist,
            music_platform=platform,
            quality_level=quality,
            file_size=file_size,
            download_time=datetime.now()
        )
        
        success = self.db.add_download_history(history)
        
        if success:
            logger.info(f"用户 {user_id} 消耗配额: {quality} - {song_name}")
        else:
            logger.error(f"用户 {user_id} 配额消耗失败: {quality} - {song_name}")
        
        return success
    
    def get_quota_status(self, user_id: str) -> Dict[str, Dict[str, int]]:
        """
        获取用户配额状态 (动态)
        """
        quota_obj = self.get_user_quota(user_id)
        if not quota_obj:
            return {}
            
        try:
            user_quotas = json.loads(quota_obj.daily_quotas)
        except (json.JSONDecodeError, TypeError):
            user_quotas = self.default_quotas

        status = {}
        
        for quality_key, limit in user_quotas.items():
            # VIP加成
            if quota_obj.is_vip:
                limit *= self.vip_multiplier
                
            used = self.db.get_user_daily_downloads(user_id, quality_key)

            status[quality_key] = {
                "used": used,
                "limit": limit,
                "remaining": max(0, limit - used)
            }
        
        return status
    
    def format_quota_status(self, user_id: str) -> str:
        """
        格式化配额状态为文本 (动态)
        """
        status = self.get_quota_status(user_id)
        quota_obj = self.get_user_quota(user_id)
        
        if not status or not quota_obj:
            return "❌ 无法获取配额信息"
        
        vip_badge = "👑 VIP" if quota_obj.is_vip else "👤 普通用户"
        
        # 定义显示名称和顺序
        quality_display_map = {
            "128": "🎵 标准音质",
            "320": "🎧 较高音質",
            "flac": "💎 无损音质",

            "aac_96": "🎵 AAC 96k",
            "aac_48": "🎵 AAC 48k",
            "ogg_192": "🎧 OGG 192k",
            "ogg_96": "🎵 OGG 96k",
        }
        
        lines = [
            f"📊 今日配额状态 ({vip_badge})",
            ""
        ]
        
        # 按照预定顺序显示
        for key, display_name in quality_display_map.items():
            if key in status:
                s = status[key]
                lines.append(f"{display_name}: {s['remaining']}/{s['limit']} 剩余")
        
        # 显示其他未在map中定义的音质
        for key, s in status.items():
            if key not in quality_display_map:
                lines.append(f"{key}: {s['remaining']}/{s['limit']} 剩余")
        
        return "\n".join(lines)

