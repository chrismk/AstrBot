"""
盘搜API处理模块
负责与盘搜后端API交互
"""
import asyncio
import aiohttp
from typing import Dict, List, Optional, Tuple
from astrbot.api import logger

# 导入通用缓存管理器
try:
    from common.cache_manager import CacheManager, get_global_cache
except ImportError:
    CacheManager = None
    get_global_cache = None
    logger.warning("[PansouAPI] 无法导入 CacheManager，缓存功能将不可用")


class PansouAPI:
    """盘搜API处理器"""
    
    def __init__(self, api_base_url: str = "http://43.129.194.21:19005"):
        """
        初始化API处理器
        
        Args:
            api_base_url: API基础URL
        """
        self.api_base_url = api_base_url.rstrip('/')
        self.search_endpoint = f"{self.api_base_url}/api/search"
        self.timeout = aiohttp.ClientTimeout(total=60)  # 增加超时时间到60秒
        
        # 初始化缓存（使用全局缓存或新建）
        self.cache = None
        if get_global_cache:
            self.cache = get_global_cache()
            if self.cache is not None:
                logger.info("[PansouAPI] 使用全局 CacheManager")
            
        if self.cache is None and CacheManager:
            self.cache = CacheManager(default_ttl=600)  # 默认10分钟缓存
            logger.info("[PansouAPI] 创建新的 CacheManager (TTL=600s)")
        
        if self.cache is None:
            logger.warning("[PansouAPI] 缓存未启用 (CacheManager不可用)")
    
    async def search(
        self,
        keyword: str,
        channels: Optional[str] = None,
        cloud_types: Optional[str] = None,
        src: str = "all",
        res: str = "merge",
        page: int = 1,
        page_size: int = 15
    ) -> Tuple[List[Dict], int]:
        """
        搜索资源
        """
        # 1. 检查缓存
        if self.cache is not None:
            cache_key = f"pansou:search:{keyword}:{cloud_types}:{page}"
            cached_data = self.cache.get(cache_key)
            if cached_data:
                logger.info(f"命中盘搜搜索缓存: {cache_key}")
                return cached_data['results'], cached_data['total']
                
        try:
            params = {
                "kw": keyword,
                "res": res,
                "src": src
            }
            
            if channels:
                params["channels"] = channels
            if cloud_types:
                params["cloud_types"] = cloud_types
            
            logger.info(f"[Pansou] 搜索资源: {keyword}, 参数: {params}")
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(self.search_endpoint, params=params) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        
                        # 检查API返回格式
                        if response_data.get('code') != 0:
                            logger.error(f"[Pansou] API返回错误: {response_data.get('message')}")
                            return [], 0
                        
                        # 提取实际数据
                        data = response_data.get('data', {})
                        
                        # 根据res参数解析不同的返回结构
                        if res == "merge":
                            results = self._parse_merged_results(data)
                        elif res == "results":
                            results = self._parse_results(data)
                        else:  # all
                            results = self._parse_all_results(data)
                        
                        # 分页处理
                        total = len(results)
                        start_idx = (page - 1) * page_size
                        end_idx = start_idx + page_size
                        page_results = results[start_idx:end_idx]
                        
                        logger.info(f"[Pansou] 搜索成功: 共{total}条结果，返回第{page}页")
                        
                        # 写入缓存
                        if self.cache is not None and page_results:
                            cache_key = f"pansou:search:{keyword}:{cloud_types}:{page}"
                            self.cache.set(cache_key, {
                                'results': page_results,
                                'total': total
                            }, ttl=600)  # 显式指定TTL为600秒
                            
                        return page_results, total
                    else:
                        logger.error(f"[Pansou] API请求失败: {response.status}")
                        return [], 0
                        
        except asyncio.TimeoutError:
            logger.error(f"[Pansou] 搜索超时 (>{self.timeout.total}秒): {keyword}")
            return None, -1  # 返回 None 表示异常
        except Exception as e:
            logger.error(f"[Pansou] 搜索异常: {type(e).__name__}: {e}")
            return None, -1  # 返回 None 表示异常
    
    def _parse_merged_results(self, data: Dict) -> List[Dict]:
        """
        解析merge类型的结果
        
        Returns:
            标准化的结果列表
        """
        results = []
        merged_by_type = data.get("merged_by_type", {})
        
        for cloud_type, links in merged_by_type.items():
            for link_data in links:
                result = {
                    "type": "merged",
                    "cloud_type": cloud_type,
                    "url": link_data.get("url", ""),
                    "password": link_data.get("password", ""),
                    "note": link_data.get("note", ""),
                    "datetime": link_data.get("datetime", ""),
                    "source": link_data.get("source", "unknown"),
                    "images": link_data.get("images", [])
                }
                results.append(result)
        
        return results
    
    def _parse_results(self, data: Dict) -> List[Dict]:
        """
        解析results类型的结果
        
        Returns:
            标准化的结果列表
        """
        results = []
        search_results = data.get("results", [])
        
        for item in search_results:
            # 每个SearchResult可能包含多个链接
            links = item.get("links", [])
            for link in links:
                result = {
                    "type": "result",
                    "cloud_type": link.get("type", "unknown"),
                    "url": link.get("url", ""),
                    "password": link.get("password", ""),
                    "title": item.get("title", ""),
                    "content": item.get("content", ""),
                    "channel": item.get("channel", ""),
                    "datetime": link.get("datetime", item.get("datetime", "")),
                    "work_title": link.get("work_title", ""),
                    "images": item.get("images", [])
                }
                results.append(result)
        
        return results
    
    def _parse_all_results(self, data: Dict) -> List[Dict]:
        """
        解析all类型的结果（优先使用merged）
        
        Returns:
            标准化的结果列表
        """
        # 优先使用merged结果
        if "merged_by_type" in data and data["merged_by_type"]:
            return self._parse_merged_results(data)
        else:
            return self._parse_results(data)
    
    @staticmethod
    def get_cloud_type_name(cloud_type: str) -> str:
        """
        获取网盘类型的中文名称
        
        Args:
            cloud_type: 网盘类型代码
            
        Returns:
            中文名称
        """
        cloud_names = {
            "baidu": "百度网盘",
            "aliyun": "阿里云盘",
            "quark": "夸克网盘",
            "tianyi": "天翼云盘",
            "uc": "UC网盘",
            "mobile": "移动云盘",
            "115": "115网盘",
            "pikpak": "PikPak",
            "xunlei": "迅雷网盘",
            "123": "123网盘",
            "magnet": "磁力链接",
            "ed2k": "电驴链接"
        }
        return cloud_names.get(cloud_type.lower(), cloud_type)
    
    @staticmethod
    def get_cloud_type_emoji(cloud_type: str) -> str:
        """
        获取网盘类型的emoji图标
        
        Args:
            cloud_type: 网盘类型代码
            
        Returns:
            emoji图标
        """
        cloud_emojis = {
            "baidu": "☁️",
            "aliyun": "💾",
            "quark": "⚡",
            "tianyi": "📱",
            "uc": "🌐",
            "mobile": "📲",
            "115": "💿",
            "pikpak": "📦",
            "xunlei": "⚡",
            "123": "💽",
            "magnet": "🧲",
            "ed2k": "🔗"
        }
        return cloud_emojis.get(cloud_type.lower(), "📁")
