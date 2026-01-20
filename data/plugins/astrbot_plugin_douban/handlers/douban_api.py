"""
豆瓣API调用模块
负责所有与豆瓣API的交互
"""
import aiohttp
import json
from typing import Optional, Tuple, List, Dict
from astrbot.api import logger

# 导入通用缓存管理器
try:
    from common.cache_manager import CacheManager, get_global_cache
except ImportError:
    CacheManager = None
    get_global_cache = None
    logger.warning("[DoubanAPI] 无法导入 CacheManager，缓存功能将不可用")

# 导入通用搜索统计
try:
    from common import get_search_statistics
except ImportError:
    get_search_statistics = None
    logger.warning("[DoubanAPI] 无法导入 SearchStatistics，统计功能将不可用")

# 导入 Cookies 管理器
from .cookies_manager import CookiesManager


class DoubanAPI:
    """豆瓣API调用类"""
    
    def __init__(self, timeout: int = 15):
        self.douban_image_api = "http://api.wowoziyuan.com/douban/index.php"
        self.douban_comment_api = "https://m.douban.com/rexxar/api/v2"
        self.screenshot_api = "http://43.139.224.42:19002/screenshot"
        self.timeout = timeout  # API请求超时时间（秒）
        
        self.headers = {
            'user-agent': 'Mozilla/5.0 (Linux; Android) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.109 Safari/537.36 CrKey/1.54.248666 Edg/127.0.0.0'
        }
        
        # 初始化缓存（使用全局缓存或新建）
        self.cache = None
        if get_global_cache:
            self.cache = get_global_cache()
            if self.cache is not None:
                logger.info("[DoubanAPI] 使用全局 CacheManager")
            
        if self.cache is None and CacheManager:
            self.cache = CacheManager(default_ttl=3600)  # 默认1小时缓存
            logger.info("[DoubanAPI] 创建新的 CacheManager (TTL=3600s)")
            
        if self.cache is None:
            logger.warning("[DoubanAPI] 缓存未启用 (CacheManager不可用)")
        
        # 初始化 Cookies 管理器
        self.cookies_manager = CookiesManager()
        logger.info("[DoubanAPI] Cookies管理器初始化完成")
        
        # 初始化通用搜索统计
        self.search_stats = None
        self.search_history = None
        if get_search_statistics:
            try:
                import os
                from common import DatabaseManager
                data_path = os.environ.get('ASTRBOT_DATA_PATH', 'data')
                db_path = os.path.join(data_path, "quota_system.db")
                db = DatabaseManager(db_path)
                self.search_stats = get_search_statistics(db)
                self.search_history = self.search_stats  # search_history 是 search_stats 的别名
                logger.info("[DoubanAPI] 通用搜索统计初始化完成")
            except Exception as e:
                logger.warning(f"[DoubanAPI] 搜索统计初始化失败: {e}")
    
    async def get_douban_image(self, douban_type: str, douban_id: str) -> Optional[bytes]:
        """
        获取豆瓣评分图片（带备用方案）
        
        Args:
            douban_type: 类型 (movie/book)
            douban_id: 豆瓣ID
            
        Returns:
            图片字节数据或None
        """
        # 优先尝试直接获取图片
        try:
            direct_image_url = f"http://api.wowoziyuan.com/douban/image_api.php?type={douban_type}&id={douban_id}"
            logger.info(f"尝试直接获取豆瓣图片: {direct_image_url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(direct_image_url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status == 200:
                        content_type = response.headers.get('Content-Type', '')
                        if 'image' in content_type:
                            image_bytes = await response.read()
                            # 简单验证，判断是否是有效图片（大于2KB）
                            if len(image_bytes) > 2048:
                                logger.info(f"成功通过直接API获取豆瓣图片: {direct_image_url}")
                                return image_bytes
                            else:
                                logger.info("直接API获取的图片过小，可能无效，尝试备用方案")
                        else:
                            logger.info(f"直接API返回非图片内容: {content_type}，尝试备用方案")
                    else:
                        logger.info(f"直接API获取图片失败，状态码: {response.status}，尝试备用方案")
        except Exception as e:
            logger.warning(f"直接获取豆瓣图片异常: {e}，尝试备用方案")
        
        # 如果直接获取失败，使用备用的截图服务
        try:
            douban_page_url = f"{self.douban_image_api}?type={douban_type}&id={douban_id}&download=0"
            
            payload = {
                "url": douban_page_url,
                "selector": "img",
                "waitFor": 2000
            }
            
            logger.info(f"请求截图服务: {self.screenshot_api} for url: {douban_page_url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.screenshot_api, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        content_type = response.headers.get('Content-Type', '')
                        if 'image' in content_type:
                            logger.info(f"成功获取豆瓣图片: {douban_page_url}")
                            return await response.read()
                        else:
                            logger.warning(f"截图服务返回非图片内容: {content_type}")
                            return None
                    else:
                        logger.warning(f"截图服务失败，状态码: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"截图服务异常: {e}")
            return None
    
    async def get_douban_title(self, douban_type: str, douban_id: str) -> Optional[str]:
        """
        获取豆瓣标题
        
        Args:
            douban_type: 类型 (movie/book)
            douban_id: 豆瓣ID
            
        Returns:
            标题或None
        """
        try:
            # 使用第三方API获取标题（更稳定）
            title_api_url = f"http://api.wowoziyuan.com/douban/api.php?type={douban_type}&id={douban_id}"
            
            logger.info(f"请求豆瓣标题API: {title_api_url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(title_api_url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=self.timeout)) as response:
                    if response.status == 200:
                        data = await response.json()
                        title = data.get("title")
                        if title:
                            logger.info(f"成功获取豆瓣标题: {title}")
                            return title
                        else:
                            logger.warning("API返回数据中没有标题字段")
                            return None
                    else:
                        logger.warning(f"获取豆瓣标题失败，状态码: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"获取豆瓣标题异常: {e}")
            return None
    
    async def get_douban_comments(self, douban_type: str, douban_id: str) -> dict:
        """
        获取豆瓣评论
        
        Args:
            douban_type: 类型 (movie/book)
            douban_id: 豆瓣ID
            
        Returns:
            评论数据字典
        """
        try:
            # 构建评论API URL
            comment_url = f"{self.douban_comment_api}/{douban_type}/{douban_id}/interests"
            
            params = {
                'count': 4,
                'order_by': 'hot',
                'anony': 0,
                'start': 0,
                'ck': 'XTON',
                'for_mobile': 1
            }
            
            logger.info(f"请求豆瓣评论API: {comment_url}")
            
            # 添加 Referer header
            request_headers = self.headers.copy()
            request_headers['Referer'] = f'https://m.douban.com/{douban_type}/{douban_id}/'
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    comment_url,
                    params=params,
                    headers=request_headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"成功获取评论数据，评论数量: {len(data.get('interests', []))}")
                        return data
                    else:
                        logger.warning(f"获取豆瓣评论失败，状态码: {response.status}")
                        return {}
                        
        except Exception as e:
            logger.error(f"获取豆瓣评论异常: {e}", exc_info=True)
            return {}
    
    async def search_douban(
        self, 
        keyword: str, 
        search_type: str = "book", 
        page: int = 1,
        user_id: Optional[str] = None
    ) -> Tuple[List[Dict], int]:
        """
        搜索豆瓣信息（使用网页搜索）
        
        Args:
            keyword: 搜索关键词
            search_type: 搜索类型 (book/movie)
            page: 页码
            user_id: 用户ID，用于获取该用户的 cookies
        """
        # 1. 检查缓存
        if self.cache is not None:
            cache_key = f"douban:search:{search_type}:{keyword}:{page}"
            cached_data = self.cache.get(cache_key)
            if cached_data:
                logger.info(f"命中豆瓣搜索缓存: {cache_key}")
                return cached_data['results'], cached_data['total']
                
        try:
            from urllib.parse import quote
            import re
            import json
            
            # 构建搜索URL（使用网页搜索）
            if search_type == "book":
                url = f"https://search.douban.com/book/subject_search?search_text={quote(keyword)}&cat=1001&start={(page-1)*15}"
                headers = {
                    "Host": "search.douban.com",
                    "Referer": "https://book.douban.com/",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
                }
            elif search_type == "movie":
                url = f"https://search.douban.com/movie/subject_search?search_text={quote(keyword)}&cat=1002&start={(page-1)*15}"
                headers = {
                    "Host": "search.douban.com",
                    "Referer": "https://movie.douban.com/",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
                }
            else:
                logger.error(f"不支持的搜索类型: {search_type}")
                return [], 0
            
            # 获取用户的 cookies（如果有）
            if user_id:
                dbcl2 = self.cookies_manager.get_cookie(user_id)
                if dbcl2:
                    headers["Cookie"] = f"dbcl2={dbcl2}"
                    logger.info(f"[DoubanAPI] 使用用户 cookies: user_id={user_id}")
            
            logger.info(f"搜索豆瓣{search_type}: {url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status != 200:
                        logger.warning(f"搜索请求失败，状态码: {response.status}")
                        return [], 0
                    
                    html_content = await response.text()
                    
                    # 使用正则表达式提取 window.__DATA__ 中的JSON数据
                    matches = re.findall(r'window\.__DATA__\s*=\s*({.*?});', html_content, re.DOTALL)
                    if not matches:
                        logger.warning("未找到 window.__DATA__ 数据（可能页面结构变更）")
                        return [], 0
                    
                    # 解析JSON数据
                    data = json.loads(matches[0])
                    
                    # 检查是否被限制（豆瓣会在 error_info 中返回错误信息）
                    error_info = data.get("error_info", "")
                    if error_info:
                        logger.warning(f"[DoubanAPI] 豆瓣返回错误: {error_info}, 关键词: {keyword}")
                        return [], 0
                    
                    total_count = data.get("total", 0)
                    items = data.get("items", [])
                    
                    results = []
                    for item in items:
                        try:
                            # 过滤掉非搜索结果项目
                            if item.get("tpl_name") != "search_subject":
                                continue
                            
                            # 提取基本信息
                            result = {
                                'id': str(item.get("id", "")),
                                'title': item.get("title", ""),
                                'url': item.get("url", ""),
                                'cover_url': item.get("cover_url", ""),
                                'type': search_type,
                                'rating': item.get("rating", {}).get("value", 0),
                                'rating_count': item.get("rating", {}).get("count", 0),
                                'year': ''
                            }
                            
                            # 从abstract中提取信息
                            abstract = item.get("abstract", "")
                            abstract_2 = item.get("abstract_2", "")
                            
                            if search_type == "book":
                                # 书籍格式: "作者 / 出版社 / 年份 / 价格"
                                if abstract:
                                    parts = abstract.split(" / ")
                                    result['author'] = [parts[0]] if len(parts) >= 1 else []
                                    result['publisher'] = parts[2] if len(parts) >= 3 else ''
                                    if len(parts) >= 4:
                                        year_match = re.search(r'(\d{4})', parts[3])
                                        if year_match:
                                            result['year'] = year_match.group(1)
                            
                            elif search_type == "movie":
                                # 从title中提取年份
                                title = result.get('title', '')
                                year_match = re.search(r'\((\d{4})\)', title)
                                if year_match:
                                    result['year'] = year_match.group(1)
                                
                                # 从abstract_2中提取导演和演员
                                if abstract_2:
                                    actors_parts = abstract_2.split(" / ")
                                    result['directors'] = [actors_parts[0]] if len(actors_parts) >= 1 else []
                                    result['actors'] = actors_parts[1:4] if len(actors_parts) > 1 else []
                                
                                # 从abstract中提取类型
                                if abstract:
                                    parts = abstract.split(" / ")
                                    result['genres'] = [parts[1]] if len(parts) >= 2 else []
                            
                            results.append(result)
                            
                        except Exception as e:
                            logger.warning(f"解析搜索结果项失败: {e}")
                            continue
                    
                    logger.info(f"搜索成功: 关键词={keyword}, 类型={search_type}, 结果数={len(results)}/{total_count}")
                    
                    # 记录搜索统计（使用通用模块）
                    if user_id and self.search_stats:
                        self.search_stats.record_search(
                            user_id=user_id,
                            plugin_name='douban',
                            keyword=keyword,
                            result_count=total_count,
                            search_type=search_type
                        )
                    
                    # 写入缓存
                    if self.cache is not None:
                        cache_key = f"douban:search:{search_type}:{keyword}:{page}"
                        # 如果有结果，缓存1小时；如果无结果（但成功解析），缓存5分钟
                        ttl = 3600 if results else 300
                        try:
                            self.cache.set(cache_key, {
                                'results': results,
                                'total': total_count
                            }, ttl=ttl)
                            logger.info(f"[DoubanAPI] 写入搜索缓存: {cache_key}, ttl={ttl}s")
                        except Exception as e:
                            logger.error(f"写入缓存失败: {e}")
                        
                    return results, total_count
                    
        except Exception as e:
            logger.error(f"搜索豆瓣异常: {e}", exc_info=True)
            return [], 0
    
    async def get_douban_detail_info(self, douban_type: str, douban_id: str, user_id: Optional[str] = None) -> dict:
        """
        获取豆瓣详细信息用于AI解读
        
        Args:
            douban_type: 类型 (book/movie)
            douban_id: 豆瓣ID
            user_id: 用户ID，用于记录查看历史
        """
        # 1. 检查缓存
        if self.cache is not None:
            cache_key = f"douban:detail:{douban_type}:{douban_id}"
            cached_data = self.cache.get(cache_key)
            if cached_data:
                logger.info(f"命中豆瓣详情缓存: {cache_key}")
                return cached_data
                
        try:
            # 使用 wowoziyuan API（与旧代码一致）
            detail_api_url = f"https://api.wowoziyuan.com/douban/api.php?type={douban_type}&id={douban_id}"
            
            logger.info(f"请求豆瓣详细信息API: {detail_api_url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(detail_api_url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        title = data.get('title', 'Unknown')
                        logger.info(f"成功获取豆瓣详细信息: {title}")
                        
                        # 记录详情查看历史
                        if user_id and data and self.search_history:
                            try:
                                self.search_history.record_detail_click(user_id, douban_id, douban_type, title)
                            except Exception as e:
                                logger.debug(f"[DoubanAPI] 记录搜索历史失败: {e}")
                        
                        # 写入缓存
                        if self.cache is not None and data:
                            cache_key = f"douban:detail:{douban_type}:{douban_id}"
                            self.cache.set(cache_key, data)
                            logger.info(f"[DoubanAPI] 写入详情缓存: {cache_key}")
                            
                        return data
                    else:
                        logger.warning(f"获取豆瓣详细信息失败，状态码: {response.status}")
                        return {}
                        
        except Exception as e:
            logger.error(f"获取豆瓣详细信息异常: {e}")
            return {}
