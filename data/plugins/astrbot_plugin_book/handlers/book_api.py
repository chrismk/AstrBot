"""
书籍搜索 API 封装
"""
import json
import aiohttp
from typing import Any, Dict, List, Optional, Tuple
from astrbot.api import logger

# 导入通用缓存管理器
try:
    from common.cache_manager import CacheManager, get_global_cache
except ImportError:
    CacheManager = None
    get_global_cache = None
    logger.warning("[BookAPI] 无法导入 CacheManager，缓存功能将不可用")

# API 接口配置
API_BASE = "http://bookapi.wowoziyuan.com"
EBOOKLIB_API_URL = f"{API_BASE}/api/search_ebooklib"
GET_UPLOAD_BOOK_API_URL = f"{API_BASE}/api/get_upload_book"
ALTERNATIVE_API_URL = "https://m.zslren.com/api/v1/resources/search"


def _safe_json_loads(text_body: str) -> Optional[Dict[str, Any]]:
    """安全解析 JSON"""
    try:
        data = json.loads(text_body)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


class BookAPI:
    """书籍搜索 API"""
    
    def __init__(self):
        self.timeout = 15
        
        # 初始化缓存
        self.cache = None
        if get_global_cache:
            self.cache = get_global_cache()
            if self.cache is not None:
                logger.info("[BookAPI] 使用全局 CacheManager")
        
        if self.cache is None and CacheManager:
            self.cache = CacheManager(default_ttl=3600)  # 默认1小时缓存
            logger.info("[BookAPI] 创建新的 CacheManager (TTL=3600s)")
    
    async def search_books(
        self, 
        keyword: str, 
        page: int = 1, 
        size: int = 16,
        api_source: str = "default"
    ) -> Tuple[List[Dict], int]:
        """
        搜索书籍
        
        Args:
            keyword: 搜索关键词
            page: 页码
            size: 每页数量
            api_source: API源 (default/alternative)
            
        Returns:
            (书籍列表, 总数)
        """
        # 检查缓存
        if self.cache is not None:
            cache_key = f"book:search:{api_source}:{keyword}:{page}:{size}"
            cached_data = self.cache.get(cache_key)
            if cached_data:
                logger.info(f"命中书籍搜索缓存: {cache_key}")
                return cached_data['books'], cached_data['total']

        try:
            async with aiohttp.ClientSession() as session:
                if api_source == "alternative":
                    data = await self._search_via_alternative(session, keyword, page, size)
                else:
                    data = await self._search_via_ebooklib(session, keyword, page, size)
                
                books = data.get("books") or []
                total = int(data.get("total") or 0)
                
                # 写入缓存（只缓存有结果的搜索）
                if self.cache is not None and books:
                    cache_key = f"book:search:{api_source}:{keyword}:{page}:{size}"
                    self.cache.set(cache_key, {'books': books, 'total': total}, ttl=3600)
                    logger.info(f"[BookAPI] 写入搜索缓存: {cache_key}, ttl=3600s")
                
                return books, total
                
        except Exception as e:
            logger.error(f"[BookAPI] 搜索失败: {e}")
            return [], 0
    
    async def _search_via_ebooklib(
        self, 
        session: aiohttp.ClientSession, 
        keyword: str, 
        page: int = 1, 
        size: int = 16
    ) -> Dict[str, Any]:
        """
        使用 ebooklib 接口搜索
        - keyword 为 8 位数字：使用 query=id:XXXXXXXX
        - 否则：使用 title=keyword
        """
        try:
            is_eight_digits = keyword.isdigit() and len(keyword) == 8
            if is_eight_digits:
                cmd = f"offset=0&limit={int(size)}&query=id:{keyword}"
            else:
                offset = max(0, (int(page) - 1) * int(size))
                cmd = f"offset={offset}&limit={int(size)}&title={keyword}"

            body = {"cmd": cmd}
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            
            async with session.post(EBOOKLIB_API_URL, json=body, headers=headers, timeout=self.timeout) as resp:
                text_body = await resp.text()
                data = _safe_json_loads(text_body) or {}
                data.setdefault("total", 0)
                data.setdefault("offset", 0)
                data.setdefault("limit", size)
                data.setdefault("books", [])
                return data
                
        except Exception as e:
            logger.error(f"[BookAPI] ebooklib 搜索失败: {e}")
            return {"total": 0, "offset": 0, "limit": size, "books": []}
    
    async def _search_via_alternative(
        self, 
        session: aiohttp.ClientSession, 
        keyword: str, 
        page: int = 1, 
        size: int = 16
    ) -> Dict[str, Any]:
        """使用备用 API 搜索"""
        try:
            params = {
                "keyword": keyword,
                "category": "books",
                "page": page,
                "page_size": size,
                "source": "hunter"
            }
            
            async with session.get(ALTERNATIVE_API_URL, params=params, timeout=self.timeout) as resp:
                data = await resp.json()
                
                # 转换数据格式
                books = []
                for item in data.get("data", []):
                    title = str(item.get("title", ""))
                    link = str(item.get("link", ""))
                    
                    book = {
                        "id": str(item.get("doc_id", "")),
                        "title": title,
                        "author": "",
                        "extension": str(item.get("file_type", "")),
                        "filesize": int(item.get("file_size", 0)),
                        "link": link
                    }
                    books.append(book)
                
                meta = data.get("meta", {})
                return {
                    "books": books,
                    "total": int(meta.get("total", 0)),
                    "offset": (page - 1) * size,
                    "limit": size
                }
                
        except Exception as e:
            logger.error(f"[BookAPI] 备用API搜索失败: {e}")
            return {"books": [], "total": 0, "offset": 0, "limit": size}
    
    async def get_book_formats(self, ssid: str) -> List[Dict[str, Any]]:
        """
        获取书籍的可用格式列表
        
        Args:
            ssid: 书籍 SSID
            
        Returns:
            格式列表
        """
        # 检查缓存
        if self.cache is not None:
            cache_key = f"book:formats:{ssid}"
            cached_data = self.cache.get(cache_key)
            if cached_data:
                logger.info(f"命中书籍格式缓存: {cache_key}")
                return cached_data

        try:
            async with aiohttp.ClientSession() as session:
                payload = {"ssid": str(ssid)}
                headers = {"Content-Type": "application/json", "Accept": "application/json"}
                
                async with session.post(GET_UPLOAD_BOOK_API_URL, json=payload, headers=headers, timeout=self.timeout) as resp:
                    text_body = await resp.text()
                    data = _safe_json_loads(text_body) or {}
                    
                    result = []
                    if int(data.get("state", 0)) == 1:
                        msg_raw = data.get("msg", "")
                        try:
                            items = json.loads(msg_raw)
                            if isinstance(items, list):
                                # 检查是否有 PDF 文件
                                has_pdf = any(str(item.get("extension", "")).lower() == "pdf" for item in items)
                                
                                if has_pdf:
                                    result = items
                                else:
                                    # 没有 PDF，尝试备用搜索
                                    logger.info(f"[BookAPI] 无 PDF，尝试备用搜索: {ssid}")
                                    backup_results = await self._search_backup_formats(session, ssid)
                                    result = items + backup_results
                        except Exception:
                            pass
                    
                    # 写入缓存
                    if self.cache is not None and result:
                        cache_key = f"book:formats:{ssid}"
                        self.cache.set(cache_key, result, ttl=3600)
                        logger.info(f"[BookAPI] 写入书籍格式缓存: {cache_key}")
                    
                    return result
                    
        except Exception as e:
            logger.error(f"[BookAPI] 获取格式失败: {e}")
            return []
    
    async def _search_backup_formats(
        self, 
        session: aiohttp.ClientSession, 
        ssid: str
    ) -> List[Dict[str, Any]]:
        """使用备用搜索接口搜索书籍格式"""
        try:
            url = f"{ALTERNATIVE_API_URL}?keyword={ssid}&category=books&page=1&page_size=10&source=hunter"
            
            async with session.get(url, timeout=self.timeout) as resp:
                text_body = await resp.text()
                data = _safe_json_loads(text_body) or {}
                
                items = data.get("data", [])
                if not items:
                    return []
                
                formatted_items = []
                for item in items:
                    file_type = str(item.get("file_type", "")).lower()
                    file_size = int(item.get("file_size", 0))
                    link = str(item.get("link", ""))
                    
                    # 解析链接提取群ID和消息ID
                    group_id = None
                    message_id = None
                    if link and "/c/" in link:
                        try:
                            parts = link.split("/c/")[1].split("/")
                            if len(parts) >= 2:
                                group_id = f"-100{parts[0]}"
                                message_id = parts[1]
                        except Exception:
                            pass
                    
                    if group_id and message_id:
                        formatted_items.append({
                            "extension": file_type,
                            "file_size": file_size,
                            "tag": f"{group_id}.{message_id}",
                            "source": "backup_search"
                        })
                
                return formatted_items
                
        except Exception as e:
            logger.error(f"[BookAPI] 备用格式搜索失败: {e}")
            return []
    
    async def send_book(self, tag: str, user_id: str, chat_id: str, message_id: str, platform: str) -> str:
        """
        发送书籍文件
        
        Args:
            tag: 文件标签
            user_id: 用户ID
            chat_id: 会话ID
            message_id: 消息ID
            platform: 平台名称
            
        Returns:
            API 返回的消息
        """
        try:
            payload = {
                "tag": str(tag).strip(),
                "user_id": user_id,
                "chat_id": chat_id,
                "message_id": message_id,
                "platform": platform,
                "content": "",
            }
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.post(f"{API_BASE}/api/send_book", json=payload, headers=headers, timeout=self.timeout) as resp:
                    text_body = await resp.text()
                    data = _safe_json_loads(text_body) or {}
                    return str(data.get("msg", ""))
                    
        except Exception as e:
            logger.error(f"[BookAPI] 发送书籍失败: {e}")
            raise
    
    async def copy_message(
        self, 
        from_peer: str, 
        to_peer: str, 
        message_id: int, 
        caption: str
    ) -> bool:
        """
        复制消息（用于转发文件）
        
        Args:
            from_peer: 源会话
            to_peer: 目标会话
            message_id: 消息ID
            caption: 文件说明
            
        Returns:
            是否成功
        """
        try:
            params = {
                "data[from_peer]": from_peer,
                "data[to_peer]": to_peer,
                "data[id][0]": message_id,
                "data[caption]": caption,
            }
            
            url = "http://tglyjapi.zslren.com/api/copyMessages/"
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.get(url, params=params, timeout=self.timeout) as resp:
                    await resp.text()
                    return True
                    
        except Exception as e:
            logger.error(f"[BookAPI] 复制消息失败: {e}")
            return False
