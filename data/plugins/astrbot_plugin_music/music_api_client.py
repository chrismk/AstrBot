"""音乐API客户端"""

import aiohttp
from typing import Optional, Dict, Any, List
import logging

from .utils.exceptions import MusicAPIError

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# 导入通用缓存管理器
try:
    from common.cache_manager import CacheManager, get_global_cache
except ImportError:
    CacheManager = None
    get_global_cache = None
    logger.warning("[MusicAPI] 无法导入 CacheManager，缓存功能将不可用")


class MusicAPIClient:
    """音乐API客户端"""
    
    def __init__(
        self,
        api_base_url: str,
        api_key: str,
        timeout: int = 30
    ):
        """
        初始化音乐API客户端
        
        Args:
            api_base_url: API基础URL
            api_key: API密钥
            timeout: 请求超时时间
        """
        self.api_base_url = api_base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=30)
        
        # 初始化缓存
        self.cache = None
        if get_global_cache:
            self.cache = get_global_cache()
            if self.cache is not None:
                logger.info("[MusicAPI] 使用全局 CacheManager")
        
        if self.cache is None and CacheManager:
            self.cache = CacheManager(default_ttl=3600)  # 默认1小时缓存
            logger.info("[MusicAPI] 创建新的 CacheManager (TTL=3600s)")
        
        logger.info(f"MusicAPIClient 初始化完成: {self.api_base_url}")

    async def search(
        self, 
        keyword: str, 
        platform: str = "netease",
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        搜索音乐
        
        Args:
            keyword: 关键词
            platform: 平台
            page: 页码
            limit: 每页数量
            
        Returns:
            搜索结果
        """
        # 检查缓存
        if self.cache is not None:
            cache_key = f"music:search:{platform}:{keyword}:{page}:{limit}"
            cached_data = self.cache.get(cache_key)
            if cached_data:
                logger.info(f"命中音乐搜索缓存: {cache_key}")
                return cached_data
        
        url = f"{self.api_base_url}/api/search"
        params = {
            "platform": platform,
            "keyword": keyword,
            "page": page,
            "limit": limit
        }
        headers = {"X-API-Key": self.api_key}
        
        logger.info(f"搜索请求 - URL: {url}")
        logger.info(f"搜索参数: {params}")
        
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, params=params, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"搜索失败: HTTP {response.status}, {error_text[:200]}")
                        raise MusicAPIError(f"搜索API请求失败: {response.status}")
                    
                    data = await response.json()
                    
                    if data.get("code") != 200:
                        msg = data.get('message', '未知错误')
                        logger.error(f"搜索API返回错误: {msg}")
                        raise MusicAPIError(f"搜索API返回错误: {msg}")

                    result_data = data.get("data", {})
                    items = result_data.get("items", [])
                    pagination = result_data.get("pagination", {})
                    
                    # 统一返回格式
                    result = {
                        "songs": items,  # 将items重命名为songs
                        "total": pagination.get("total_items", 0),
                        "page": pagination.get("current_page", page),
                        "limit": pagination.get("page_size", limit),
                        "has_next": pagination.get("has_next", False),
                        "has_prev": pagination.get("has_prev", False),
                        "keyword": result_data.get("keyword", keyword),
                        "platform": result_data.get("platform", platform)
                    }
                    
                    # 写入缓存（只缓存有结果的搜索）
                    if self.cache is not None and items:
                        cache_key = f"music:search:{platform}:{keyword}:{page}:{limit}"
                        self.cache.set(cache_key, result, ttl=3600)
                        logger.info(f"[MusicAPI] 写入搜索缓存: {cache_key}, ttl=3600s")
                    
                    return result

        except aiohttp.ClientError as e:
            logger.error(f"搜索请求失败: {e}", exc_info=True)
            raise MusicAPIError("网络请求失败，请稍后重试")
        except Exception as e:
            logger.error(f"搜索异常: {e}", exc_info=True)
            raise MusicAPIError("搜索服务异常，请稍后重试")

    async def get_details(
        self, 
        song_id: str, 
        platform: str = "netease"
    ) -> Optional[Dict[str, Any]]:
        """
        获取歌曲详情
        
        Args:
            song_id: 歌曲ID
            platform: 平台
            
        Returns:
            歌曲详情字典，失败返回None
        """
        # 检查缓存
        if self.cache is not None:
            cache_key = f"music:detail:{platform}:{song_id}"
            cached_data = self.cache.get(cache_key)
            if cached_data:
                logger.info(f"命中音乐详情缓存: {cache_key}")
                return cached_data
        
        # 直接调用 get_song_data 获取详情（/api/detail 接口已失效）
        result = await self.get_song_data(song_id, platform)
        
        if result:
            # 写入缓存
            if self.cache is not None:
                cache_key = f"music:detail:{platform}:{song_id}"
                self.cache.set(cache_key, result, ttl=3600)
                logger.info(f"[MusicAPI] 写入详情缓存: {cache_key}")
        
        return result
    
    async def get_song_data(
        self, 
        song_id: str, 
        platform: str = "netease",
        quality: str = "128"
    ) -> Optional[Dict[str, Any]]:
        """
        获取包含所有音质链接的完整歌曲数据
        
        Args:
            song_id: 歌曲ID
            platform: 平台
            quality: 期望的音质
            
        Returns:
            完整的歌曲数据字典，失败返回None
        """
        url = f"{self.api_base_url}/api/{platform}"
        
        # 音质参数映射
        # 网易云音乐不支持 hires 参数，映射为 flac
        if platform == "netease" and quality == "hires":
            q_param = "flac"
        else:
            # 动态构建q参数 (e.g., "128" -> "128", "flac" -> "flac")
            q_param = f"{quality}" if quality.isdigit() else quality
        
        if song_id.isdigit():
            params = {
                "id": song_id,
                "q": q_param
            }
        else:
            params = {
                "mid": song_id,
                "q": q_param
            }
        headers = {"X-API-Key": self.api_key}
        
        #logger.info(f"获取歌曲数据 - URL: {url}, Params: {params}")
        
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url, params=params, headers=headers) as response:
                    #logger.info(f"歌曲数据响应状态码: {response.status}")
                    
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"获取歌曲数据失败: HTTP {response.status}, {error_text[:500]}")
                        return None
                    
                    data = await response.json()
                    #logger.info(f"歌曲数据API响应: {data}")
                    
                    if data.get("code") != 200:
                        logger.warning(f"获取歌曲数据API返回错误: {data.get('message', '未知错误')}")
                        return None
                    
                    return data.get("data")
        except Exception as e:
            logger.error(f"获取歌曲数据异常: {e}", exc_info=True)
            return None

    async def get_play_url(
        self,
        song_id: str,
        platform: str = "netease",
        quality: str = "128"  # Expects keys like '128', '320', 'flac', 'aac_96'
    ) -> Optional[str]:
        """
        获取播放链接
        
        Args:
            song_id: 歌曲ID
            platform: 平台
            quality: 音质 (e.g., '128', '320', 'flac', 'aac_96')
            
        Returns:
            播放URL，失败返回None
        """
        song_data = await self.get_song_data(song_id, platform, quality)
        
        if not song_data:
            logger.warning(f"获取播放链接失败，因为无法获取歌曲数据: {song_id} @ {platform}")
            return None
            
        urls = song_data.get("urls", {})
        play_url = urls.get(quality)

        if not play_url:
            logger.warning(f"指定音质 '{quality}' 的播放链接为空: {song_id} @ {platform}")
            logger.warning(f"可用音质: {list(urls.keys())}")
            return None
        
        logger.info(f"获取播放链接成功 ({quality}): {play_url}")
        return play_url

    def get_platform_name(self, platform_key: str) -> str:
        """根据平台key获取平台名称"""
        platform_map = {
            "netease": "网易云",
            "qq": "QQ音乐",
            "kuwo": "酷我",
            "kugou": "酷狗"
        }
        return platform_map.get(platform_key, platform_key)

