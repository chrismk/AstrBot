from typing import Any, Dict, List, Optional
import json
import aiohttp
import asyncio
import urllib.parse
import os
import hashlib
from pathlib import Path
from datetime import datetime

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.message.components import Image, Plain, InlineKeyboard, File
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# 导入通用配额系统
import sys
from pathlib import Path
plugin_root = Path(__file__).parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

try:
    from common.database_manager import DatabaseManager as CommonDatabaseManager
    from common.quota_validator import QuotaValidator
    QUOTA_SYSTEM_AVAILABLE = True
except ImportError:
    QUOTA_SYSTEM_AVAILABLE = False
    logger.warning("[Yunpan] 通用配额系统不可用，将使用插件内置配额管理")

# 内部模块
from .db.database import BookDatabaseManager
from .db.models import BookSearchCache, BookDownloadHistory
from .quota_manager import BookQuotaManager, BookQuotaExceededError
from .file_cache_manager import BookFileCacheManager


async def is_image_url_valid(url: str) -> bool:
    """检查图片URL是否有效"""
    if not url or not url.startswith("http"):
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=5) as response:
                return response.status == 200 and "image" in response.headers.get(
                    "Content-Type", ""
                )
    except Exception:
        return False


# 书籍API接口
API_BASE = "http://bookapi.wowoziyuan.com"

# 书库接口
EBOOKLIB_API_URL = f"{API_BASE}/api/search_ebooklib"
GET_UPLOAD_BOOK_API_URL = f"{API_BASE}/api/get_upload_book"


def _safe_json_loads(text_body: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(text_body)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def _extract_msg_from_legacy(data: Any) -> str:
    if isinstance(data, dict) and "msg" in data:
        v = data["msg"]
        return str(v)
    return str(data)


def _encode_callback_data(keyword: str, page: int, size: int, llm: int = 0, prefix: str = "disk", api_source: str = "default") -> str:
    """简单编码 callback_data，直接使用关键词"""
    try:
        # 直接使用关键词，避免特殊字符
        # 替换可能的问题字符
        safe_keyword = str(keyword).replace("|", "_").replace("=", "_").replace("&", "_")
        
        # 使用简单格式：<prefix>|<keyword>|<page>|<size>|<llm>|<api_source>
        callback_data = f"{prefix}|{safe_keyword}|{page}|{size}|{llm}|{api_source}"
        
        # 检查长度限制
        if len(callback_data) > 64:
            # 如果超长，截断关键词
            max_keyword_len = 64 - len(f"{prefix}||{page}|{size}|{llm}|{api_source}")
            if max_keyword_len > 0:
                truncated_keyword = safe_keyword[:max_keyword_len]
                callback_data = f"{prefix}|{truncated_keyword}|{page}|{size}|{llm}|{api_source}"
            else:
                return None
        
        return callback_data
    except Exception as e:
        logger.error(f"[yunpan] 编码 callback_data 失败: {e}")
        return None


def _decode_callback_data(data: str) -> Dict[str, Any]:
    """简单解码 callback_data"""
    try:
        # 支持 disk|... 与 book|...
        if not (data.startswith("disk|") or data.startswith("book|")):
            return {}
        
        # 解析格式：<prefix>|<keyword>|<page>|<size>|<llm>|<api_source>
        parts = data.split("|")
        if len(parts) < 5:
            return {}
        
        try:
            keyword = parts[1]
            page = int(parts[2])
            size = int(parts[3])
            llm = int(parts[4])
            api_source = parts[5] if len(parts) > 5 else "default"
        except ValueError:
            return {}
        
        return {
            "prefix": parts[0],
            "k": keyword,
            "p": page,
            "s": size,
            "llm": llm,
            "api_source": api_source
        }
    except Exception as e:
        logger.error(f"[yunpan] 解码 callback_data 失败: {e}")
        return {}


def _bytes_to_human(size_bytes: int) -> str:
    try:
        size = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:
                if unit == "B":
                    return f"{int(size)}B"
                return f"{size:.2f}{unit}"
            size /= 1024.0
        return f"{size:.2f}PB"
    except Exception:
        return str(size_bytes)


def _build_duxiu_cover_url(eight_digits: str) -> str:
    # 复用原有封面拼接算法
    try:
        chars = list(eight_digits)
        parts = []
        for idx, ch in enumerate(chars):
            seg = "6" + ch
            if idx == 1:
                seg += "5F"
            if idx == 4:
                seg += "5F"
            parts.append(seg)
        modified = "".join(parts)
        return (
            "https://unicover.duxiu.com/coverNew/CoverNew.dll?iid="
            + modified
            + "9C97569E9F8FA791A495A29D91A29B566131688929249994130"
        )
    except Exception:
        return ""


async def _search_via_ebooklib(session: aiohttp.ClientSession, keyword: str, page: int = 1, size: int = 20) -> Dict[str, Any]:
    """
    新书库接口：/api/search_ebooklib
    - keyword 为 8 位数字：使用 query=id:XXXXXXXX
    - 否则：使用 title=keyword
    返回：{"total":int,"offset":int,"limit":int,"books":[...]}（原样返回）
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
        async with session.post(EBOOKLIB_API_URL, json=body, headers=headers, timeout=15) as resp:
            text_body = await resp.text()
            data = _safe_json_loads(text_body) or {}
            # 兜底字段
            data.setdefault("total", 0)
            data.setdefault("offset", 0)
            data.setdefault("limit", size)
            data.setdefault("books", [])
            return data
    except Exception as e:
        logger.error(f"[yunpan-book] ebooklib api failed: {e}")
        return {"total": 0, "offset": 0, "limit": size, "books": []}


async def _search_via_alternative_api(session: aiohttp.ClientSession, keyword: str, page: int = 1, size: int = 16) -> Dict[str, Any]:
    """
    备用书籍搜索API：https://m.zslren.com/api/v1/resources/search
    返回格式与 _search_via_ebooklib 兼容
    """
    try:
        url = "https://m.zslren.com/api/v1/resources/search"
        params = {
            "keyword": keyword,
            "category": "books",
            "page": page,
            "page_size": size,
            "source": "hunter"
        }
        
        async with session.get(url, params=params, timeout=15) as resp:
            data = await resp.json()
            
            # 转换数据格式以兼容现有逻辑
            books = []
            for item in data.get("data", []):
                # 从title中尝试提取作者信息（如果有的话）
                title = str(item.get("title", ""))
                author = ""
                link = str(item.get("link", ""))  # 保留原始链接信息
                
                book = {
                    "id": str(item.get("doc_id", "")),
                    "title": title,
                    "author": author,
                    "extension": str(item.get("file_type", "")),
                    "filesize": int(item.get("file_size", 0)),
                    "link": link  # 保留link字段用于后续处理
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
        logger.error(f"[yunpan-book] alternative api failed: {e}")
        return {"books": [], "total": 0, "offset": 0, "limit": size}


async def _fetch_upload_book_formats(session: aiohttp.ClientSession, ssid: str) -> List[Dict[str, Any]]:
    """
    调用 /api/get_upload_book 获取该 SSID 已上传的文件列表。
    如果没有PDF文件，则使用备用搜索接口累加更多结果。
    返回列表元素包含 extension, file_size 等字段。
    """
    try:
        payload = {"ssid": str(ssid)}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        async with session.post(GET_UPLOAD_BOOK_API_URL, json=payload, headers=headers, timeout=15) as resp:
            text_body = await resp.text()
            data = _safe_json_loads(text_body) or {}
            if int(data.get("state", 0)) != 1:
                return []
            msg_raw = data.get("msg", "")
            # msg 是字符串形式的 JSON 数组
            try:
                items = json.loads(msg_raw)
                if isinstance(items, list):
                    # 检查是否有PDF文件
                    has_pdf = any(str(item.get("extension", "")).lower() == "pdf" for item in items)
                    
                    if has_pdf:
                        # 有PDF文件，直接返回原始结果
                        return items
                    else:
                        # 没有PDF文件，先返回原始结果，再尝试备用搜索
                        logger.info(f"[yunpan-book] No PDF found in upload_book, trying backup search for SSID: {ssid}")
                        backup_results = await _search_backup_book_formats(session, ssid)
                        
                        # 合并原始结果和备用搜索结果
                        combined_results = items.copy()
                        if backup_results:
                            combined_results.extend(backup_results)
                        
                        return combined_results
            except Exception:
                return []
            return []
    except Exception as e:
        logger.error(f"[yunpan-book] get_upload_book api failed: {e}")
        return []


async def _search_backup_book_formats(session: aiohttp.ClientSession, ssid: str) -> List[Dict[str, Any]]:
    """
    使用备用搜索接口搜索书籍格式。
    返回格式化的结果列表。
    """
    try:
        url = f"https://m.zslren.com/api/v1/resources/search?keyword={ssid}&category=books&page=1&page_size=10&source=hunter"
        async with session.get(url, timeout=15) as resp:
            text_body = await resp.text()
            data = _safe_json_loads(text_body) or {}
            
            items = data.get("data", [])
            if not items:
                return []
            
            # 转换数据格式以匹配原始接口格式
            formatted_items = []
            for item in items:
                file_type = str(item.get("file_type", "")).lower()
                file_size = int(item.get("file_size", 0))
                link = str(item.get("link", ""))
                
                # 从链接提取群ID和消息ID
                # 格式: https://t.me/c/2011682900/668274
                group_id = None
                message_id = None
                if link and "/c/" in link:
                    try:
                        parts = link.split("/c/")[1].split("/")
                        if len(parts) >= 2:
                            group_id = f"-100{parts[0]}"  # 添加-100前缀
                            message_id = parts[1]
                    except Exception:
                        pass
                
                if group_id and message_id:
                    formatted_item = {
                        "extension": file_type,
                        "file_size": file_size,
                        "tag": f"{group_id}.{message_id}",  # 用于回调识别
                        "source": "backup_search"
                    }
                    formatted_items.append(formatted_item)
            
            return formatted_items
            
    except Exception as e:
        logger.error(f"[yunpan-book] backup search failed for SSID {ssid}: {e}")
        return []


async def _send_book(tag: str, event: AstrMessageEvent) -> str:
    """
    调用 /api/send_book 将书籍发送任务下发到后端。
    返回后端的 msg 文本（若有）。
    """
    try:
        payload = {
            "tag": str(tag).strip(),
            "user_id": event.get_sender_id(),
            "chat_id": event.get_group_id() or event.get_session_id(),
            "message_id": event.message_obj.message_id,
            "platform": event.get_platform_name(),
            "content": event.message_str or "",
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.post(f"{API_BASE}/api/send_book", json=payload, headers=headers, timeout=15) as resp:
                text_body = await resp.text()
                data = _safe_json_loads(text_body) or {}
                return str(data.get("msg", ""))
            
    except Exception as e:
        logger.error(f"[yunpan-book] send_book failed: {e}")
        raise


async def _maybe_copy_messages(event: AstrMessageEvent, msg_str: str, file_tag: str = None) -> tuple[bool, str | None]:
    """
    当后端返回的 msg 是 JSON 且 status=="发送文件" 时，调用 tglyjapi 复制消息。
    返回 (是否触发复制, 可选的人类可读信息document_url)。
    """
    try:
        info = json.loads(msg_str)
        if not isinstance(info, dict):
            return (False, None)
        if str(info.get("status", "")) != "发送文件":
            return (False, None)
        message_info = str(info.get("message_info", ""))
        if "." not in message_info:
            return (False, None)
        from_peer_str, msg_id_str = message_info.split(".", 1)
        from_peer = int(from_peer_str)
        msg_id = int(msg_id_str)
        to_peer = f"@{event.get_self_id()}"
        # 处理 document_url，去掉"详情：XXX"和"解压：XXX"行，替换转义字符
        document_url = info.get('document_url', '')
        if document_url:
            lines = document_url.split('\n')
            filtered_lines = []
            for line in lines:
                line = line.strip()
                # 过滤掉"详情："和"解压："开头的行
                if not line.startswith('详情：') and not line.startswith('解压：'):
                    # 替换 \* 为 *
                    line = line.replace('\\*', '*')
                    filtered_lines.append(line)
            document_url = '\n'.join(filtered_lines)
        
        # 统一 caption 格式：receive:{sender_id}|book_info:{book_info}
        # 如果有 file_tag，尝试从中提取文件大小和格式信息
        book_info = document_url or ""
        if file_tag:
            import re
            match = re.match(r'(\d+)([a-z]+)', file_tag)
            if match:
                api_size = match.group(1)
                api_format = match.group(2)
                # 在 book_info 前面添加结构化信息
                if book_info:
                    book_info = f"SSID_SIZE_FORMAT:{api_size}:{api_format}\n{book_info}"
                else:
                    book_info = f"SSID_SIZE_FORMAT:{api_size}:{api_format}"
        
        caption = f"receive:{event.get_sender_id()}|book_info:{book_info}"

        params = {
            "data[from_peer]": from_peer,
            "data[to_peer]": to_peer,
            "data[id][0]": msg_id,
            "data[caption]": caption,
        }
        url = "http://tglyjapi.zslren.com/api/copyMessages/"
        async with aiohttp.ClientSession(trust_env=True) as session:
            async with session.get(url, params=params, timeout=15) as resp:
                _ = await resp.text()
        return (True, str(info.get("document_url") or ""))
    except Exception as e:
        logger.error(f"[yunpan-book] copyMessages failed: {e}")
        return (False, None)


def _format_disk_results(data: Dict[str, Any]) -> str:
    # 期望结构: { code, msg, data: { total, list: [ { disk_name, link, disk_type, disk_pass, share_user, shared_time } ] } }
    try:
        if data.get("code") != 200:
            return ""
        payload = data.get("data") or {}
        result_list: List[Dict[str, Any]] = payload.get("list") or []
        if not result_list:
            return ""

        lines: List[str] = []
        for item in result_list[:15]:  # 限制前 10 条
            name = str(item.get("disk_name") or "").replace("\u003cem\u003e", "").replace("\u003c/em\u003e", "")
            link = item.get("link") or ""
            pwd = item.get("disk_pass") or ""
            suffix = f" 提取码:{pwd}" if pwd else ""
            line = f"{name}\n{link}"
            lines.append(line)
        return "\n\n".join(lines).strip()
    except Exception:
        return ""


async def _search_via_disk_api(session: aiohttp.ClientSession, keyword: str, page: int = 1, size: int = 15) -> str:
    body = {
        "q": keyword,
        "type": "",
        "exact": True,
        "user": "",     
        "share_time": "",
        "format": [],
        "page": max(1, int(page)),
        "size": max(1, min(50, int(size)))
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*"
    }
    async with session.post(DISK_API_URL, json=body, headers=headers, timeout=15) as resp:
        text_body = await resp.text()
        data = _safe_json_loads(text_body)
        if not data:
            # 返回非 JSON 时，直接回传文本
            return text_body.strip()
        pretty = _format_disk_results(data)
        return pretty


async def _search_via_legacy_api(session: aiohttp.ClientSession, keyword: str) -> str:
    payload = {
        "cmd": keyword,
        "platform": "fwh",
        "user_id": 0,
        "chat_id": 0,
        "message_id": 0
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*"
    }
    async with session.post(f"{API_BASE}/api/search_yunpan", json=payload, headers=headers, timeout=15) as resp:
        text_body = await resp.text()
        data = _safe_json_loads(text_body)
        if data is not None:
            return _extract_msg_from_legacy(data) or text_body
        return text_body


async def _search_via_book_api(session: aiohttp.ClientSession, keyword: str, user_id: int = 0, chat_id: int = 0, bot_id: int = 0, platform: str = "fwh") -> Dict[str, str]:
    payload = {
        "cmd": keyword,
        "user_id": user_id,
        "chat_id": chat_id,
        "bot_id": bot_id,
        "platform": platform
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*"
    }
    async with session.post(f"{API_BASE}/api/search_ebook", json=payload, headers=headers, timeout=15) as resp:
        text_body = await resp.text()
        logger.debug(f"[yunpan-book] API 返回原始文本: {text_body[:200]}...")

        result_text = ""
        cover_url = ""

        # 尝试解析 JSON
        try:
            data = json.loads(text_body)
            logger.info(f"[yunpan-book] JSON 解析成功，类型: {type(data)}")
            if isinstance(data, dict):
                # 检查是否有 msg 字段，如果有，尝试解析它
                if "msg" in data:
                    msg_content = data["msg"]
                    logger.info(f"[yunpan-book] 找到 msg 字段，类型: {type(msg_content)}")

                    # 如果 msg 是字符串，尝试解析为 JSON
                    if isinstance(msg_content, str):
                        try:
                            msg_data = json.loads(msg_content)
                            logger.info(f"[yunpan-book] msg 解析成功，类型: {type(msg_data)}")
                            if isinstance(msg_data, dict):
                                result_text = str(msg_data.get("book_info", "") or "")
                                cover_url = str(msg_data.get("cover_url", "") or "")
                        except json.JSONDecodeError:
                            logger.warning(f"[yunpan-book] msg 字段不是有效的 JSON")
                            result_text = str(msg_content)

                # 没有 msg 或未解析出
                if not result_text:
                    # 如果没有 msg 字段，尝试直接提取 book_info
                    result_text = str(data.get("book_info", "") or "")

        except json.JSONDecodeError as e:
            logger.error(f"[yunpan-book] JSON 解析失败: {e}")
            logger.error(f"[yunpan-book] 原始文本: {text_body[:500]}")
            result_text = text_body

        # 最后兜底
        if not result_text:
            result_text = text_body

        return {"text": result_text, "cover_url": cover_url}


@register("yunpan-search", "you", "命令 /搜 触发，优先走 search disk，无结果回退旧接口", "1.1.0", "")
class YunpanSearchPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 会话级短期缓存：key=session_id, value={"keyword":str,"page":int,"size":int,"ts":float}
        self._session_cache: dict[str, dict] = {}
        self._cache_ttl_seconds: int = 600  # 10分钟
        
        # 初始化数据库和管理器
        config = self.context.get_config()
        data_path = config.get("data_path", "data")
        
        # 将数据库移动到 plugin_data 目录，实现数据与插件分离
        plugin_data_dir = os.path.join(data_path, "plugin_data", "yunpan")
        os.makedirs(plugin_data_dir, exist_ok=True)
        db_path = os.path.join(plugin_data_dir, "yunpan.db")
        
        # 数据库管理器
        self.db = BookDatabaseManager(db_path)
        
        # 配额管理器（已废弃，使用通用配额系统）
        # self.quota_mgr = BookQuotaManager(self.db, default_quota=10, vip_multiplier=3)
        self.quota_mgr = None  # 不再使用内置配额管理器
        
        # 通用配额系统（优先使用）
        self.common_quota_validator = None
        if QUOTA_SYSTEM_AVAILABLE:
            try:
                quota_db_path = os.path.join(data_path, "quota_system.db")
                common_db = CommonDatabaseManager(quota_db_path)
                self.common_quota_validator = QuotaValidator(common_db)
                logger.info("[Yunpan] 通用配额系统初始化完成")
            except Exception as e:
                logger.error(f"[Yunpan] 通用配额系统初始化失败: {e}")
        
        # 文件缓存管理器
        self.cache_mgr = BookFileCacheManager(self.db)
        
        # 启动时清理旧缓存
        try:
            self.db.cleanup_old_caches(days=7)
        except Exception as e:
            logger.error(f"清理旧缓存失败: {e}")
        
        logger.info("云盘插件初始化完成，已启用缓存和配额管理")

    def _set_callback_response(self, event, toast_type: str, message_zh: str, message_en: str, card_data: dict = None):
        """设置飞书卡片回调响应"""
        try:
            if hasattr(event, 'callback_response') and event.callback_response:
                # 构造Toast响应
                response = {
                    "toast": {
                        "type": toast_type,  # info, success, warning, error
                        "content": message_zh,
                        "i18n": {
                            "zh_cn": message_zh,
                            "en_us": message_en
                        }
                    }
                }
                
                # 如果提供了卡片数据，添加到响应中
                if card_data:
                    response["card"] = card_data
                
                event.callback_response["response"] = response
                logger.debug(f"[yunpan-callback] 设置回调响应: {response}")
        except Exception as e:
            logger.warning(f"[yunpan-callback] 设置回调响应失败: {e}")
    
    async def _handle_pagination_callback(self, event: AstrMessageEvent, data: str, card_token: str = None):
        """处理分页回调，支持飞书延时更新卡片"""
        try:
            platform_name = (event.get_platform_name() or "").lower()
            
            # 解析回调数据
            decoded = _decode_callback_data(data)
            if not decoded:
                yield event.plain_result("❌ 无效的回调数据")
                return
            
            prefix = data.split("|")[0]  # book 或 disk
            keyword = decoded["k"]  # 修复键名不匹配问题
            page = decoded["p"]     # 修复键名不匹配问题
            size = decoded["s"]     # 修复键名不匹配问题
            api_source = decoded.get("api_source", "default")
            
            # 执行搜索
            async with aiohttp.ClientSession() as session:
                if prefix == "book":
                    # 书籍搜索
                    if api_source == "alternative":
                        data_result = await _search_via_alternative_api(session, keyword, page=page, size=size)
                    else:
                        data_result = await _search_via_ebooklib(session, keyword, page=page, size=size)
                    
                    books = data_result.get("books") or []
                    total = int(data_result.get("total") or 0)
                    offset = int(data_result.get("offset") or 0)
                    limit = int(data_result.get("limit") or size)
                    
                    # 构建搜索结果文本和按钮
                    lines = []
                    detail_buttons = []
                    for idx, b in enumerate(books, start=1):
                        ssid = str(b.get("id") or "")
                        title = str(b.get("title") or "")
                        author = str(b.get("author") or "").strip()
                        ext = str(b.get("extension") or "").lower()
                        fs = int(b.get("filesize") or 0)
                        size_h = _bytes_to_human(fs)
                        
                        # 构建显示行
                        if api_source == "alternative":
                            if author and author != "":
                                line = f"{idx}.【{ssid}】{title} - {author} {size_h}"
                            else:
                                line = f"{idx}.【{ssid}】{title} {size_h}"
                        else:
                            if author and author != "":
                                line = f"{idx}.【{ssid}】{title} - {author}.{ext} {size_h}"
                            else:
                                line = f"{idx}.【{ssid}】{title}.{ext} {size_h}"
                        lines.append(line)
                        
                        # 创建详情按钮
                        if ssid.isdigit() and len(ssid) == 8:
                            cb = f"book_detail|{ssid}"
                            detail_buttons.append({"text": str(idx), "callback_data": cb})
                    
                    # 组装消息文本
                    text_out = "\n\n".join(lines) if lines else "未找到任何结果，请尝试换源搜索"
                    current_page = (offset // limit) + 1
                    source_text = "备用源" if api_source == "alternative" else "默认源"
                    if lines:
                        text_out += f"\n\n💡 点击数字查看详情 | 第 {current_page} 页 | {source_text}"
                    
                    # 生成键盘
                    kb = InlineKeyboard()
                    
                    # 详情按钮（数字），每行8个
                    if detail_buttons:
                        for i in range(0, len(detail_buttons), 8):
                            kb.add_row(*detail_buttons[i:i+8])
                    
                    # 翻页按钮
                    total_pages = max(1, (total + limit - 1) // limit)
                    prev_p = max(1, page - 1)
                    next_p = page + 1
                    
                    prev_cb = _encode_callback_data(keyword, prev_p, size, 0, prefix="book", api_source=api_source)
                    next_cb = _encode_callback_data(keyword, next_p, size, 0, prefix="book", api_source=api_source)
                    home_cb = _encode_callback_data(keyword, 1, size, 0, prefix="book", api_source=api_source)
                    
                    nav_row = []
                    if page > 1 and prev_cb:
                        nav_row.append({"text": "⬅️ 上一页", "callback_data": prev_cb})
                    if page > 1 and home_cb:
                        nav_row.append({"text": "🏠 首页", "callback_data": home_cb})
                    if page < total_pages and next_cb:
                        nav_row.append({"text": "➡️ 下一页", "callback_data": next_cb})
                    
                    if nav_row:
                        kb.add_row(*nav_row)
                    
                    # 换源按钮
                    switch_source = "default" if api_source == "alternative" else "alternative"
                    switch_text = "🔄 默认搜" if api_source == "alternative" else "🔄 换源搜"
                    switch_cb = _encode_callback_data(keyword, 1, size, 0, prefix="book", api_source=switch_source)
                    if switch_cb:
                        kb.add_row({"text": switch_text, "callback_data": switch_cb})
                    
                    # 尝试使用飞书延时更新卡片
                    if platform_name == "lark" and card_token:
                        logger.debug(f"[yunpan-pagination] 尝试更新飞书卡片，token: {card_token[:20]}...")
                        try:
                            success = await event.update_card_delayed(card_token, text_out, kb)
                            if success:
                                logger.debug("[yunpan-pagination] 飞书卡片更新成功")
                                return
                            else:
                                logger.warning("[yunpan-pagination] 飞书卡片更新失败，回退到发送新消息")
                        except Exception as e:
                            logger.error(f"[yunpan-pagination] 飞书卡片更新异常: {e}")
                    else:
                        logger.debug(f"[yunpan-pagination] 跳过卡片更新 - platform: {platform_name}, token: {'有' if card_token else '无'}")
                    
                    # 回退到发送新消息
                    logger.debug("[yunpan-pagination] 发送新消息作为翻页结果")
                    yield event.chain_result([Plain(text_out), kb])
                    
                else:
                    # disk搜索等其他类型，使用原有逻辑
                    text_out = await _search_via_disk_api(session, keyword, page=page, size=size)
                    yield event.plain_result(text_out)
                    
        except Exception as e:
            logger.error(f"[yunpan-pagination] 处理分页回调失败: {e}")
            yield event.plain_result(f"❌ 分页处理失败: {e}")

    def _generate_cache_key(self, user_id: str, keyword: str, page: int) -> str:
        """生成搜索缓存键"""
        raw = f"{user_id}:{keyword}:{page}"
        return hashlib.md5(raw.encode()).hexdigest()
    
    def _build_rich_caption_from_cache(self, cached_file) -> str:
        """从缓存文件信息构建丰富的Caption"""
        try:
            import json
            if cached_file.book_info:
                # 解析 book_info JSON
                book_info = json.loads(cached_file.book_info)
                
                # 检查是否有嵌套的 book_data 字段
                book_details = book_info
                if 'book_data' in book_info and isinstance(book_info['book_data'], str):
                    try:
                        # 解析嵌套的 book_data JSON 字符串
                        book_details = json.loads(book_info['book_data'])
                    except json.JSONDecodeError:
                        logger.warning(f"解析嵌套 book_data 失败，使用顶层数据")
                        book_details = book_info
                
                details = []
                if book_details.get('title'):
                    details.append(f"书名: {book_details.get('title')}")
                if book_details.get('author'):
                    details.append(f"作者: {book_details.get('author')}")
                if book_details.get('publisher'):
                    details.append(f"出版: {book_details.get('publisher')}")
                if book_details.get('year'):
                    details.append(f"年份: {book_details.get('year')}")
                if book_details.get('pages'):
                    details.append(f"页数: {book_details.get('pages')}")
                if book_details.get('isbn'):
                    details.append(f"ISBN: {book_details.get('isbn')}")
                
                # SSID 总是从缓存对象的顶层获取
                if cached_file.book_ssid:
                    details.append(f"SSID: {cached_file.book_ssid}")

                return "\n".join(details)
            else:
                # 兼容旧的缓存格式
                return (
                    f"书名: {cached_file.file_name or 'N/A'}\n"
                    f"作者: N/A\n"
                    f"SSID: {cached_file.book_ssid}"
                )
        except Exception as e:
            logger.error(f"构建缓存文件caption失败: {e}")
            return (
                f"书名: {cached_file.file_name or 'N/A'}\n"
                f"SSID: {cached_file.book_ssid}"
            )

    async def _show_book_details(self, event: AstrMessageEvent, ssid: str, session: aiohttp.ClientSession, books: Optional[List[Dict[str, Any]]] = None):
        """显示单本书的详细信息和下载选项"""
        # 先检查是否已有详情缓存
        cached_detail = self.db.get_book_detail_cache(ssid)
        has_cache = cached_detail and cached_detail.expires_time > datetime.now()
        logger.info(f"🔍 缓存检查: ssid={ssid}, cached_detail存在={cached_detail is not None}, has_cache={has_cache}")
        
        if books is None:
            if has_cache:
                logger.debug(f"使用书籍详情缓存: {ssid}")
                try:
                    book_data = json.loads(cached_detail.book_data)
                    books = [book_data]
                except Exception as e:
                    logger.error(f"解析详情缓存失败: {e}")
                    books = []
            
            if not books:
                logger.info(f"🔍 获取书籍详情: {ssid}")
                data = await _search_via_ebooklib(session, ssid, page=1, size=1)
                books = data.get("books") or []
                logger.info(f"📚 API返回书籍数量: {len(books)}")
        else:
            # 即使传入了books数据，也要检查并保存缓存
            logger.info(f"📚 使用传入的书籍数据，数量: {len(books)}")
        
        # 保存详情缓存（如果还没有缓存且有数据）
        if books and not has_cache:
            try:
                from datetime import timedelta
                from .db.models import BookDetailCache
                expires_time = datetime.now() + timedelta(hours=24)
                detail_cache = BookDetailCache(
                    book_ssid=ssid,
                    book_data=json.dumps(books[0], ensure_ascii=False),
                    created_time=datetime.now(),
                    expires_time=expires_time
                )
                self.db.save_book_detail_cache(detail_cache)
                logger.info(f"✅ 保存书籍详情缓存: {ssid}")
                logger.info(f"📖 缓存的详细数据: {detail_cache.book_data}")
            except Exception as e:
                logger.error(f"❌ 保存详情缓存失败: {e}")
        elif not books:
            logger.warning(f"⚠️ 无书籍数据，无法缓存详情: {ssid}")
        elif has_cache:
            logger.info(f"📋 详情缓存已存在，跳过保存: {ssid}")
        else:
            logger.warning(f"❓ 未知情况: books={bool(books)}, has_cache={has_cache}, ssid={ssid}")

        if books:
            # 使用第一条构造 caption
            b0 = books[0]
            ssid = str(b0.get("id") or ssid)
            title = str(b0.get("title") or "")
            author = str(b0.get("author") or "")
            publisher = str(b0.get("publisher") or "")
            year = str(b0.get("year") or "")
            pages = str(b0.get("pages") or "")
            isbn = str(b0.get("isbn") or "")

            caption_lines = []
            if title:
                caption_lines.append(f"书名:{title}")
            if author:
                caption_lines.append(f"作者:{author}")
            if publisher:
                caption_lines.append(f"出版:{publisher}")
            if year:
                caption_lines.append(f"年份:{year}")
            if pages:
                caption_lines.append(f"页数:{pages}")
            if isbn:
                caption_lines.append(f"ISBN:{isbn}")
            if ssid:
                caption_lines.append(f"SSID:{ssid}")
            caption = "\n".join(caption_lines).strip()

            # 生成格式按钮（同一书多版本） - 每行最多 2 个按钮
            kb = InlineKeyboard()
            fmt_buttons = []
            try:
                upload_files = await _fetch_upload_book_formats(session, ssid)
            except Exception:
                upload_files = []

            if upload_files:
                for item in upload_files:
                    ext_raw = str(item.get("extension") or "")
                    if not ext_raw:
                        continue
                    ext_up = ext_raw.upper()
                    ext_low = ext_raw.lower()
                    fs = int(item.get("file_size") or 0)
                    tag_val = str(item.get("tag") or "").strip()
                    source = str(item.get("source") or "")
                    
                    file_tag = f"{fs}{ext_low}"
                    backend_tag = tag_val if tag_val else file_tag

                    # 根据数据来源生成不同的深度链接格式
                    if source == "backup_search" and tag_val:
                        # 备用搜索的结果，使用群组复制格式，包含SSID
                        # 将特殊字符编码：. -> d, - -> m
                        encoded_tag = tag_val.replace(".", "d").replace("-", "m")
                        deep_link_param = f"gb_{ssid}_{file_tag}_{encoded_tag}"
                    else:
                        # 原始接口的结果
                        deep_link_param = f"bk_{ssid}_{file_tag}_{backend_tag}"
                    
                    deep_link = f"https://t.me/zslraibot/?start={deep_link_param}"
                    fmt_buttons.append({"text": f"{ext_up}/{_bytes_to_human(fs)}", "url": deep_link})
                
                # 添加AI解读按钮到格式按钮列表中
                ai_interpret_param = f"ai_interpret_{ssid}"
                ai_interpret_url = f"https://t.me/zslraibot/?start={ai_interpret_param}"
                fmt_buttons.append({"text": "🤖 AI解读", "url": ai_interpret_url})
                
                # 统一排列所有按钮，每行最多2个
                for idx in range(0, len(fmt_buttons), 2):
                    row = fmt_buttons[idx:idx+2]
                    kb.add_row(*row)
            else:
                # 空结果时显示暂无文件按钮和AI解读按钮
                ai_interpret_param = f"ai_interpret_{ssid}"
                ai_interpret_url = f"https://t.me/zslraibot/?start={ai_interpret_param}"
                kb.add_row({"text": "暂无书籍文件"}, {"text": "🤖 AI解读", "url": ai_interpret_url})

            # 封面
            picture_url = _build_duxiu_cover_url(ssid)

            platform_name = (event.get_platform_name() or "").lower()
            if await is_image_url_valid(picture_url):
                image_component = Image(file=picture_url, caption=caption)
                if platform_name == "telegram":
                    try:
                        if kb.buttons:
                            yield event.chain_result([image_component, kb])  # Telegram: 图片caption足够
                        else:
                            yield event.chain_result([image_component])
                    except Exception:
                        yield event.chain_result([Plain(caption), image_component])
                elif platform_name == "lark":
                    try:
                        if kb.buttons:
                            yield event.chain_result([Plain(caption), image_component, kb])  # 飞书: 需要显式文本
                        else:
                            yield event.chain_result([Plain(caption), image_component])
                    except Exception:
                        yield event.chain_result([Plain(caption), image_component])
                else:
                    yield event.chain_result([Plain(caption), image_component])
                    if kb.buttons:
                        yield event.chain_result([kb])
            else:
                logger.warning(f"书籍封面图片加载失败: {picture_url}")
                # 图片无效，只发送文本和键盘
                plain_text_with_warning = f"🖼️ 封面加载失败\n\n{caption}"
                if kb.buttons:
                    yield event.chain_result([Plain(plain_text_with_warning), kb])
                else:
                    yield event.plain_result(plain_text_with_warning)
        else:
            # 8位数字但搜索结果为空，使用默认图片
            caption = "暂无此书籍数据"
            default_ssid = "33006915"
            picture_url = _build_duxiu_cover_url(default_ssid)
            
            platform_name = (event.get_platform_name() or "").lower()
            if await is_image_url_valid(picture_url):
                image_component = Image(file=picture_url, caption=caption)
                if platform_name == "telegram":
                    try:
                        yield event.chain_result([image_component])
                    except Exception:
                        yield event.plain_result(caption)
                else:
                    try:
                        yield event.chain_result([Plain(caption), image_component])
                    except Exception:
                        yield event.plain_result(caption)
            else:
                logger.warning(f"默认书籍封面图片加载失败: {picture_url}")
                yield event.plain_result(caption)

    def _now(self) -> float:
        import time
        return time.time()

    def _cache_set(self, session_id: str, keyword: str, page: int, size: int):
        self._session_cache[session_id] = {
            "keyword": keyword,
            "page": int(page),
            "size": int(size),
            "ts": self._now(),
        }

    def _cache_get(self, session_id: str) -> dict | None:
        item = self._session_cache.get(session_id)
        if not item:
            return None
        if self._now() - float(item.get("ts", 0)) > self._cache_ttl_seconds:
            # 过期
            self._session_cache.pop(session_id, None)
            return None
        return item

    @filter.command("start")
    async def handle_start_command(self, event: AstrMessageEvent):
        """处理 /start 命令，支持从豆瓣插件跳转过来的搜索"""
        text = event.message_str or ""
        
        parts = text.split(maxsplit=1)
        
        if len(parts) < 2:
            # 普通的 /start 命令，不做处理
            return
        
        param = parts[1].strip()
        
        # 处理AI解读请求
        if param.startswith("ai_interpret_"):
            # 解析格式：ai_interpret_{ssid}
            ssid = param[13:]  # 去掉 "ai_interpret_" 前缀
            async for result in self._handle_ai_interpret(event, ssid):
                yield result
            event.stop_event()
            return
        
        # 处理新的简化格式
        if param.startswith("gb_"):
            # 解析格式：gb_{ssid}_{file_tag}_{encoded_tag}
            parts = param.split("_", 3)
            if len(parts) >= 4:
                ssid, file_tag, encoded_tag = parts[1], parts[2], parts[3]
                # 解码特殊字符：d -> ., m -> -
                decoded_tag = encoded_tag.replace("d", ".").replace("m", "-")
                converted_param = f"op_getgroupbook|{ssid}|{file_tag}|{decoded_tag}"
                async for result in self._handle_op_getgroupbook(event, converted_param):
                    yield result
                event.stop_event()
                return
        
        if param.startswith("bk_"):
            # 解析格式：bk_{ssid}_{file_tag}_{backend_tag}
            parts = param.split("_", 3)
            if len(parts) >= 4:
                ssid, file_tag, backend_tag = parts[1], parts[2], parts[3]
                converted_param = f"op_getbook|{ssid}|{file_tag}|{backend_tag}"
                async for result in self._handle_op_getbook(event, converted_param):
                    yield result
                event.stop_event()
                return
        
        # 处理豆瓣插件跳转过来的搜索请求
        if param.startswith("op_"):
            try:
                import base64
                import json
                
                # 解码参数
                encoded_payload = param[3:]  # 移除 "op_" 前缀
                decoded_bytes = base64.urlsafe_b64decode(encoded_payload)
                payload = json.loads(decoded_bytes.decode('utf-8'))
                
                douban_type = payload.get("type")
                douban_id = payload.get("id")
                
                if not douban_id:
                    yield event.plain_result("❌ 搜索参数不完整")
                    event.stop_event()
                    return

                # 从API获取标题
                title = await self._get_douban_title_by_id(douban_type, douban_id)
                if not title:
                    yield event.plain_result("❌ 无法获取豆瓣标题，搜索失败")
                    event.stop_event()
                    return
                
                logger.info(f"[yunpan-start] 从豆瓣插件接收搜索请求: type={douban_type}, id={douban_id}, title={title}")
                
                # 根据类型调用相应的搜索流程
                if douban_type == "movie":
                    # 调用电影搜索流程（/搜 命令的逻辑）
                    async for result in self._handle_movie_search(event, title):
                        yield result
                elif douban_type == "book":
                    # 调用书籍搜索流程（/书 命令的逻辑）
                    async for result in self._handle_book_search(event, title):
                        yield result
                else:
                    yield event.plain_result(f"❌ 不支持的搜索类型: {douban_type}")
                
                event.stop_event()
                return
                    
            except Exception as e:
                logger.error(f"[yunpan-start] 解析豆瓣跳转参数失败: {e}")
                yield event.plain_result("❌ 搜索参数解析失败")
                event.stop_event()
                return
        
        # 其他 /start 参数不处理，让其他插件处理
        return

    async def _get_douban_title_by_id(self, douban_type: str, douban_id: str) -> Optional[str]:
        """
        通过豆瓣类型和ID获取标题
        """
        try:
            api_url = f"https://api.wowoziyuan.com/douban/api.php?type={douban_type}&id={douban_id}"
            logger.info(f"[yunpan-douban] 请求豆瓣标题API: {api_url}")
            
            headers = {
                'user-agent': 'Mozilla/5.0 (Linux; Android) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/88.0.4324.109 Safari/537.36 CrKey/1.54.248666 Edg/127.0.0.0'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        title = data.get("title")
                        if title:
                            logger.info(f"[yunpan-douban] 成功获取豆瓣标题: {title}")
                            return title
                        else:
                            logger.warning("[yunpan-douban] API返回数据中没有标题字段")
                            return None
                    else:
                        logger.warning(f"[yunpan-douban] 获取豆瓣标题失败，状态码: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"[yunpan-douban] 获取豆瓣标题异常: {e}")
            return None

    async def _handle_movie_search(self, event: AstrMessageEvent, keyword: str):
        """处理电影搜索（复用 /搜 命令的逻辑）"""
        logger.info(f"[yunpan-movie-search] keyword={keyword}")

        try:
            # progress message
            progress_msg_id = None
            platform_name = (event.get_platform_name() or "").lower()
            try:
                if platform_name == "telegram":
                    from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent  # type: ignore
                    if isinstance(event, TelegramPlatformEvent):
                        chat_id = event.message_obj.group_id or event.get_sender_id()
                        msg = await event.client.send_message(chat_id=chat_id, text="正在全力搜索中....")
                        progress_msg_id = getattr(msg, "message_id", None)
            except Exception:
                pass

            async with aiohttp.ClientSession() as session:
                # 1) 优先调用新接口
                try:
                    disk_out = await _search_via_disk_api(session, keyword)
                except Exception as e:
                    logger.error(f"[yunpan-movie-search] disk api failed: {e}")
                    disk_out = ""

                if disk_out and disk_out.strip():
                    # 记录会话级缓存（第一页）
                    self._cache_set(event.get_session_id(), keyword, 1, 15)
                    
                    # 如果是 Telegram 或飞书，使用 InlineKeyboard 组件
                    platform_name = (event.get_platform_name() or "").lower()
                    if platform_name in ["telegram", "lark"]:
                        page = 1
                        size = 15
                        kw = keyword
                        prev_cb = _encode_callback_data(kw, max(1, page-1), size, 0)
                        next_cb = _encode_callback_data(kw, page+1, size, 0)
                        
                        # 兼容 callback_data 限制
                        if prev_cb and next_cb:
                            keyboard = InlineKeyboard()
                            
                            # 第一页时只显示下一页按钮
                            if page > 1:
                                prev_text = "⬅️ 上一页"
                                home_text = "🏠 首页"
                                next_text = "➡️ 下一页"
                                home_cb = _encode_callback_data(kw, 1, size, 0)
                                
                                keyboard.add_button(prev_text, callback_data=prev_cb)
                                keyboard.add_button(home_text, callback_data=home_cb)
                                keyboard.add_button(next_text, callback_data=next_cb)
                            else:
                                # 第一页时只显示下一页
                                next_text = "➡️ 下一页"
                                keyboard.add_button(next_text, callback_data=next_cb)
                            
                            # 在同一个消息中发送文本和键盘
                            yield event.chain_result([Plain(disk_out), keyboard])
                        else:
                            yield event.plain_result(disk_out)
                    else:
                        yield event.plain_result(disk_out)
                    # delete progress after sending
                    if progress_msg_id is not None and hasattr(event, "delete_message"):
                        try:
                            await event.delete_message(progress_msg_id)
                        except Exception:
                            pass
                    return

                # 2) 回退到旧接口
                try:
                    legacy_out = await _search_via_legacy_api(session, keyword)
                except Exception as e:
                    logger.error(f"[yunpan-movie-search] legacy api failed: {e}")
                    legacy_out = ""
                yield event.plain_result(legacy_out or "未找到任何结果，请尝试换源搜索")
                # delete progress after sending
                if progress_msg_id is not None and hasattr(event, "delete_message"):
                    try:
                        await event.delete_message(progress_msg_id)
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"[yunpan-movie-search] 调用异常: {e}")
            yield event.plain_result(f"搜索失败：{e}")

    async def _handle_book_search(self, event: AstrMessageEvent, keyword: str):
        """处理书籍搜索（复用 /书 命令的逻辑）"""
        logger.info(f"[yunpan-book-search] keyword={keyword}")
        
        # 直接调用 /书 命令的核心逻辑
        async for result in self._execute_book_search(event, keyword):
            yield result

    async def _handle_op_getgroupbook(self, event: AstrMessageEvent, data: str):
        """处理 op_getgroupbook 回调的独立函数"""
        try:
            # 解析格式：op_getgroupbook|{ssid}|{file_tag}|{group_id.message_id}
            parts = data.split("|", 3)
            if len(parts) < 4:
                return
            ssid, file_tag, group_info = [p.strip() for p in parts[1:]]
        except Exception:
            ssid, file_tag, group_info = "", "", ""

        if not ssid or not file_tag or not group_info or "." not in group_info:
            return

        user_id = event.get_sender_id()

        # 检查文件缓存
        cached_file = self.cache_mgr.get_cached_file(ssid, file_tag)
        if cached_file:
            logger.info(f"缓存命中 (groupbook): {ssid}/{file_tag}")
            # 检查配额（使用通用系统）
            quota_check_result = None
            if self.common_quota_validator:
                quota_check_result = await self.common_quota_validator.check_quota(
                    user_id=user_id,
                    action_type="yunpan_download",
                    plugin_name="yunpan",
                    use_points=True
                )
                
                if not quota_check_result.allowed:
                    yield event.plain_result(quota_check_result.message)
                    return
            else:
                logger.error("通用配额系统未初始化")
                yield event.plain_result("❌ 配额系统未初始化，请联系管理员")
                return
            
            # 从缓存发送文件，生成包含转发信息的caption
            rich_caption = self._build_rich_caption_from_cache(cached_file)
            caption = f"receive:{user_id}|book_info:SSID:{ssid},size:{cached_file.file_size or 0},format:{cached_file.file_format.replace('.', '') if cached_file.file_format else 'unknown'}\n{rich_caption}"

            # 使用Telegram客户端发送文档（带caption）
            try:
                await event.client.send_document(
                    chat_id=str(user_id),
                    document=cached_file.file_id,
                    caption=caption
                )
                # 发送文件后终止事件传播，不让LLM处理
                event.stop_event()
            except Exception as e:
                logger.error(f"发送缓存文件失败: {e}")
                yield event.plain_result(f"❌ 发送文件失败: {e}")
                return
            
            # 消费配额（使用通用系统）
            if self.common_quota_validator and quota_check_result:
                await self.common_quota_validator.consume_quota(
                    user_id=user_id,
                    action_type="yunpan_download",
                    plugin_name="yunpan",
                    points_cost=quota_check_result.points_cost
                )
            return

        # 检查配额（使用通用系统）
        quota_check_result = None
        if self.common_quota_validator:
            try:
                quota_check_result = await self.common_quota_validator.check_quota(
                    user_id=user_id,
                    action_type="yunpan_download",
                    plugin_name="yunpan",
                    use_points=True
                )
                
                if not quota_check_result.allowed:
                    yield event.plain_result(quota_check_result.message)
                    return
            except Exception as e:
                logger.error(f"配额检查失败: {e}")
                yield event.plain_result(f"❌ 配额检查失败: {e}")
                return
        else:
            logger.error("通用配额系统未初始化")
            yield event.plain_result("❌ 配额系统未初始化，请联系管理员")

        try:
            # 发送提示消息并获取消息ID
            progress_msg_id = None
            platform_name = (event.get_platform_name() or "").lower()
            try:
                if platform_name == "telegram":
                    from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                    if isinstance(event, TelegramPlatformEvent):
                        chat_id = event.message_obj.group_id or event.get_sender_id()
                        msg = await event.client.send_message(chat_id=chat_id, text="文件发送任务已提交，请稍等待...")
                        progress_msg_id = getattr(msg, "message_id", None)
                elif platform_name == "lark":
                    from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody
                    req = (
                        ReplyMessageRequest.builder()
                        .message_id(event.message_obj.message_id)
                        .request_body(
                            ReplyMessageRequestBody.builder()
                            .content(json.dumps({"zh_cn": {"title": "", "content": [[{"tag": "md", "text": "文件发送任务已提交，请稍等待..."}]]}}))
                            .msg_type("post")
                            .build()
                        )
                        .build()
                    )
                    resp = await event.bot.im.v1.message.areply(req)
                    if resp and resp.success():
                        progress_msg_id = getattr(resp.data, "message_id", None)
            except Exception:
                pass
            
            # 解析群ID和消息ID
            group_id_str, message_id_str = group_info.split(".", 1)
            group_id = int(group_id_str)
            message_id = int(message_id_str)
            
            # 构建复制消息的参数
            from_peer = group_id
            to_peer = f"@{event.get_self_id()}"
            # 从 file_tag 中提取文件大小和格式信息
            # file_tag 格式: {size}{format} 例如: "15515814pdf"
            import re
            match = re.match(r'(\d+)([a-z]+)', file_tag)
            if match:
                api_size = match.group(1)
                api_format = match.group(2)
                book_info = f"SSID:{ssid},size:{api_size},format:{api_format}"
            else:
                book_info = f"SSID:{ssid}" if ssid else ""
            caption = f"receive:{event.get_sender_id()}|book_info:{book_info}"
            
            params = {
                "data[from_peer]": from_peer,
                "data[to_peer]": to_peer,
                "data[id][0]": message_id,
                "data[caption]": caption,
            }
            
            # 调用复制消息接口
            url = "http://tglyjapi.zslren.com/api/copyMessages/"
            async with aiohttp.ClientSession(trust_env=True) as session:
                async with session.get(url, params=params, timeout=15) as resp:
                    _ = await resp.text()
            
            # 复制成功，等待文件转发完成后再删除提示消息
            if progress_msg_id is not None:
                # 等待一段时间让文件转发插件处理文件
                await asyncio.sleep(3)
                if hasattr(event, "delete_message"):
                    try:
                        await event.delete_message(progress_msg_id)
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"[yunpan-groupbook] copy group message failed: {e}")
            yield event.plain_result("文件发送任务失败，请稍后重试或反馈管理员。")

    async def _handle_op_getbook(self, event: AstrMessageEvent, data: str):
        """处理 op_getbook 回调的独立函数"""
        try:
            parts = data.split("|", 3)
            if len(parts) < 4:
                return
            book_ssid, file_tag, tag = [p.strip() for p in parts[1:]]
        except Exception as e:
            logger.error(f"[yunpan-getbook] 解析参数异常: {e}")
            book_ssid, file_tag, tag = "", "", ""

        if not book_ssid or not file_tag or not tag:
            return

        user_id = event.get_sender_id()
        
        # 检查文件缓存
        cached_file = self.cache_mgr.get_cached_file(book_ssid, file_tag)
        if cached_file:
            logger.info(f"缓存命中 (getbook): {book_ssid}/{file_tag}")
            # 检查配额（使用通用系统）
            quota_check_result = None
            if self.common_quota_validator:
                quota_check_result = await self.common_quota_validator.check_quota(
                    user_id=user_id,
                    action_type="yunpan_download",
                    plugin_name="yunpan",
                    use_points=True
                )
                
                if not quota_check_result.allowed:
                    yield event.plain_result(quota_check_result.message)
                    return
            else:
                logger.error("通用配额系统未初始化")
                yield event.plain_result("❌ 配额系统未初始化，请联系管理员")
                return
            
            # 从缓存发送文件，使用统一的caption生成方法
            caption = self._build_rich_caption_from_cache(cached_file)
            logger.info(f"从缓存发送文件，使用统一的caption生成方法: {caption}")

            # 使用Telegram客户端发送文档（带caption）
            try:
                await event.client.send_document(
                    chat_id=str(user_id),
                    document=cached_file.file_id,
                    caption=caption
                )
                # 发送文件后终止事件传播，不让LLM处理
                event.stop_event()
            except Exception as e:
                logger.error(f"发送缓存文件失败: {e}")
                yield event.plain_result(f"❌ 发送文件失败: {e}")
                return
            
            # 消费配额（使用通用系统）
            if self.common_quota_validator and quota_check_result:
                await self.common_quota_validator.consume_quota(
                    user_id=user_id,
                    action_type="yunpan_download",
                    plugin_name="yunpan",
                    points_cost=quota_check_result.points_cost
                )
            return

        # 检查配额（使用通用系统）
        quota_check_result = None
        if self.common_quota_validator:
            try:
                quota_check_result = await self.common_quota_validator.check_quota(
                    user_id=user_id,
                    action_type="yunpan_download",
                    plugin_name="yunpan",
                    use_points=True
                )
                
                if not quota_check_result.allowed:
                    yield event.plain_result(quota_check_result.message)
                    return
            except Exception as e:
                logger.error(f"配额检查失败: {e}")
                yield event.plain_result(f"❌ 配额检查失败: {e}")
                return
        else:
            logger.error("通用配额系统未初始化")
            yield event.plain_result("❌ 配额系统未初始化，请联系管理员")
        
        try:
            # 发送提示消息并获取消息ID
            progress_msg_id = None
            platform_name = (event.get_platform_name() or "").lower()
            try:
                if platform_name == "telegram":
                    from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                    if isinstance(event, TelegramPlatformEvent):
                        chat_id = event.message_obj.group_id or event.get_sender_id()
                        msg = await event.client.send_message(chat_id=chat_id, text="文件发送任务已提交，请稍等待...")
                        progress_msg_id = getattr(msg, "message_id", None)
                elif platform_name == "lark":
                    from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody
                    req = (
                        ReplyMessageRequest.builder()
                        .message_id(event.message_obj.message_id)
                        .request_body(
                            ReplyMessageRequestBody.builder()
                            .content(json.dumps({"zh_cn": {"title": "", "content": [[{"tag": "md", "text": "文件发送任务已提交，请稍等待..."}]]}}))
                            .msg_type("post")
                            .build()
                        )
                        .build()
                    )
                    resp = await event.bot.im.v1.message.areply(req)
                    if resp and resp.success():
                        progress_msg_id = getattr(resp.data, "message_id", None)
            except Exception:
                pass
            
            msg = await _send_book(tag, event)
            copied, doc_url = await _maybe_copy_messages(event, msg, file_tag)
            
            # 无论成功还是失败，都终止事件传播，不让LLM处理
            event.stop_event()
            
            # 如果复制成功，消费配额
            if copied:
                try:
                    # 从tag和doc_url中提取书籍信息
                    book_title = "未知书籍"
                    author = "未知作者"
                    file_format = "未知格式"
                    file_size = 0
                    # book_ssid 已经在函数开始时定义了，这里不需要重新赋值
                    
                    if doc_url:
                        # 尝试从doc_url中提取书籍信息
                        lines = doc_url.split('\n')
                        for line in lines:
                            line = line.strip()
                            if line.startswith('书名:'):
                                book_title = line.replace('书名:', '').strip()
                            elif line.startswith('作者:'):
                                author = line.replace('作者:', '').strip()
                            elif line.startswith('SSID:'):
                                book_ssid = line.replace('SSID:', '').strip()
                    
                    # 从tag中提取文件格式和大小信息
                    if tag:
                        # tag格式通常是: 文件大小+格式，例如 "12345678pdf"
                        import re
                        match = re.match(r'(\d+)([a-zA-Z]+)$', tag)
                        if match:
                            file_size = int(match.group(1))
                            file_format = match.group(2).lower()
                    
                    # 消费配额（使用通用系统）
                    if self.common_quota_validator and quota_check_result:
                        await self.common_quota_validator.consume_quota(
                            user_id=user_id,
                            action_type="yunpan_download",
                            plugin_name="yunpan",
                            points_cost=quota_check_result.points_cost
                        )
                    
                    # 记录文件传输信息（虽然无法获取真实file_id，但可以记录传输记录）
                    if book_ssid and file_format:
                        try:
                            # 尝试从书籍详情缓存获取完整信息
                            book_info_json = None
                            logger.info(f"🔍 查询书籍详情缓存: {book_ssid}")
                            cached_detail = self.db.get_book_detail_cache(book_ssid)
                            logger.info(f"📋 缓存查询结果: {cached_detail is not None}")
                            if cached_detail and cached_detail.expires_time > datetime.now():
                                # 使用缓存中的完整书籍详情
                                escaped_book_data = cached_detail.book_data.replace('"', '\\"')
                                book_info_json = f'{{"book_data": "{escaped_book_data}", "book_ssid": "{book_ssid}"}}'
                                logger.info(f"✅ 使用详情缓存保存文件缓存: {book_ssid}")
                                logger.info(f"📖 缓存的完整书籍详情: {cached_detail.book_data}")
                            else:
                                # 回退到基本信息
                                book_info_json = f'{{"book_data": "{{\\"title\\": \\"{book_title}\\", \\"author\\": \\"{author}\\"}}", "book_ssid": "{book_ssid}"}}'
                                logger.info(f"⚠️ 未找到详情缓存，使用基本信息保存文件缓存: {book_ssid}")
                                logger.info(f"📝 基本书籍信息: title='{book_title}', author='{author}'")
                            
                            self.cache_mgr.cache_file_id(
                                book_ssid=book_ssid,
                                file_format=file_format,
                                file_tag=tag,
                                file_id=f"sent_{tag}_{datetime.now().timestamp()}",  # 生成唯一标识
                                file_size=file_size,
                                file_name=f"{book_title}.{file_format}",
                                book_info=book_info_json,
                                uploaded_by=user_id
                            )
                            logger.debug(f"记录文件传输: {book_ssid}/{file_format}")
                        except Exception as e:
                            logger.error(f"记录文件缓存失败: {e}")
                except BookQuotaExceededError:
                    # 理论上不应该到这里，因为前面已经检查过配额
                    pass
                except Exception as e:
                    logger.error(f"配额消费失败: {e}")
            
            # 如果复制成功，等待文件转发完成后再删除提示消息
            if copied and progress_msg_id is not None:
                # 等待一段时间让文件转发插件处理文件
                await asyncio.sleep(3)
                if hasattr(event, "delete_message"):
                    try:
                        await event.delete_message(progress_msg_id)
                    except Exception:
                        pass
            
        except Exception:
            yield event.plain_result("文件发送速率限制，请稍后重试。")

    async def _handle_ai_interpret(self, event: AstrMessageEvent, ssid: str):
        """处理AI解读请求"""
        try:
            # 获取书籍详细信息
            async with aiohttp.ClientSession() as session:
                # 先检查详情缓存
                cached_detail = self.db.get_book_detail_cache(ssid)
                books = []
                
                if cached_detail and cached_detail.expires_time > datetime.now():
                    logger.debug(f"使用书籍详情缓存进行AI解读: {ssid}")
                    try:
                        book_data = json.loads(cached_detail.book_data)
                        books = [book_data]
                    except Exception as e:
                        logger.error(f"解析缓存数据失败: {e}")
                        books = []
                
                if not books:
                    # 从API获取书籍信息
                    data = await _search_via_ebooklib(session, ssid, page=1, size=1)
                    books = data.get("books") or []
                
                if not books:
                    yield event.plain_result("❌ 未找到该书籍的详细信息，无法进行AI解读")
                    return
                
                # 构造书籍信息
                book = books[0]
                book_info = self._format_book_info_for_ai(book, ssid)
                
                # 构造AI解读提示词
                ai_prompt = f"""请对以下书籍进行专业解读和分析：

{book_info}

请从以下几个方面进行分析：
1. 📚 **内容概述**：简要介绍这本书的主要内容和核心观点
2. 🎯 **适合读者**：分析这本书适合哪些读者群体
3. ⭐ **推荐理由**：说明为什么值得阅读，有什么独特价值
4. 💡 **核心收获**：读者可以从中获得什么知识或启发
5. 📖 **阅读建议**：给出阅读方法或注意事项

请用简洁明了的语言，提供有价值的见解。"""

                # 调用LLM进行解读
                try:
                    provider = self.context.get_using_provider(umo=event.unified_msg_origin)
                    if not provider:
                        yield event.plain_result("❌ 未配置AI服务，无法进行解读")
                        return
                    
                    # 发送解读开始提示并获取消息ID
                    progress_msg_id = None
                    platform_name = (event.get_platform_name() or "").lower()
                    try:
                        if platform_name == "telegram":
                            from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                            if isinstance(event, TelegramPlatformEvent):
                                chat_id = event.message_obj.group_id or event.get_sender_id()
                                msg = await event.client.send_message(chat_id=chat_id, text="🤖 AI正在解读这本书，请稍等...")
                                progress_msg_id = getattr(msg, "message_id", None)
                        elif platform_name == "lark":
                            from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody
                            req = (
                                ReplyMessageRequest.builder()
                                .message_id(event.message_obj.message_id)
                                .request_body(
                                    ReplyMessageRequestBody.builder()
                                    .content(json.dumps({"zh_cn": {"title": "", "content": [[{"tag": "md", "text": "🤖 AI正在解读这本书，请稍等..."}]]}}))
                                    .msg_type("post")
                                    .build()
                                )
                                .build()
                            )
                            resp = await event.bot.im.v1.message.areply(req)
                            if resp and resp.success():
                                progress_msg_id = getattr(resp.data, "message_id", None)
                    except Exception:
                        # 如果发送进度消息失败，仍然继续AI解读
                        yield event.plain_result("🤖 AI正在解读这本书，请稍等...")
                    
                    # 直接调用text_chat方法（非流式）
                    response = await provider.text_chat(
                        prompt=ai_prompt,
                        session_id=f"ai_interpret_{ssid}_{event.get_sender_id()}",
                        system_prompt="你是一个专业的图书推荐和解读专家，能够对各类书籍进行深入分析和客观评价。"
                    )
                    
                    if response and hasattr(response, 'result_chain') and response.result_chain:
                        # 提取文本内容
                        response_text = ""
                        for component in response.result_chain.chain:
                            if hasattr(component, 'text'):
                                response_text += component.text
                        
                        if response_text.strip():
                            # 格式化回复
                            formatted_response = f"🤖 **AI书籍解读**\n\n{response_text.strip()}"
                            yield event.plain_result(formatted_response)
                        else:
                            yield event.plain_result("❌ AI解读返回空内容，请稍后重试")
                    else:
                        yield event.plain_result("❌ AI解读失败，请稍后重试")
                    
                    # 删除进度提示消息
                    if progress_msg_id is not None:
                        try:
                            if platform_name == "telegram":
                                from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                                if isinstance(event, TelegramPlatformEvent):
                                    chat_id = event.message_obj.group_id or event.get_sender_id()
                                    await event.client.delete_message(
                                        chat_id=chat_id, 
                                        message_id=progress_msg_id
                                    )
                            elif platform_name == "lark":
                                # Lark平台的消息删除（如果支持的话）
                                pass  # 飞书可能不支持删除消息，暂时跳过
                        except Exception as e:
                            logger.warning(f"删除AI解读进度消息失败: {e}")
                        
                except Exception as e:
                    logger.error(f"AI解读失败: {e}")
                    yield event.plain_result("❌ AI解读过程中出现错误，请稍后重试")
                    
                    # 即使出错也要尝试删除进度消息
                    if 'progress_msg_id' in locals() and progress_msg_id is not None:
                        try:
                            if platform_name == "telegram":
                                from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                                if isinstance(event, TelegramPlatformEvent):
                                    chat_id = event.message_obj.group_id or event.get_sender_id()
                                    await event.client.delete_message(
                                        chat_id=chat_id, 
                                        message_id=progress_msg_id
                                    )
                        except Exception:
                            pass
                    
        except Exception as e:
            logger.error(f"处理AI解读请求失败: {e}")
            yield event.plain_result("❌ 处理AI解读请求失败，请稍后重试")
    
    def _format_book_info_for_ai(self, book: dict, ssid: str) -> str:
        """格式化书籍信息用于AI解读"""
        info_lines = []
        
        # 安全地获取并转换字段，处理可能的整数类型
        title = str(book.get("title", "")).strip()
        author = str(book.get("author", "")).strip()
        publisher = str(book.get("publisher", "")).strip()
        year = str(book.get("year", "")).strip()
        pages = str(book.get("pages", "")).strip()
        isbn = str(book.get("isbn", "")).strip()
        ssid_str = str(ssid).strip()
        
        if title and title != "":
            info_lines.append(f"📖 书名：{title}")
        if author and author != "":
            info_lines.append(f"✍️ 作者：{author}")
        if publisher and publisher != "":
            info_lines.append(f"🏢 出版社：{publisher}")
        if year and year != "":
            info_lines.append(f"📅 出版年份：{year}")
        if pages and pages != "":
            info_lines.append(f"📄 页数：{pages}")
        if isbn and isbn != "":
            info_lines.append(f"🔢 ISBN：{isbn}")
        if ssid_str and ssid_str != "":
            info_lines.append(f"🆔 SSID：{ssid_str}")
        
        return "\n".join(info_lines) if info_lines else "书籍信息不完整"

    async def _execute_book_search(self, event: AstrMessageEvent, keyword: str, api_source: str = "default"):
        """书籍搜索的核心逻辑，被 /书 命令和 /start 跳转共同使用"""
        try:
            # 获取当前机器人相关信息
            user_id = event.get_sender_id()
            chat_id = event.get_group_id() if event.get_group_id() else event.get_session_id()
            bot_id = event.get_self_id()
            platform = event.get_platform_name()
            # progress message
            progress_msg_id = None
            platform_name = (platform or "").lower()
            try:
                if platform_name == "telegram":
                    from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent  # type: ignore
                    if isinstance(event, TelegramPlatformEvent):
                        chat = event.message_obj.group_id or event.get_sender_id()
                        search_source_text = "备用源" if api_source == "alternative" else "默认源"
                        msg = await event.client.send_message(chat_id=chat, text=f"正在使用{search_source_text}全力搜索中....")
                        progress_msg_id = getattr(msg, "message_id", None)
                elif platform_name == "lark":
                    from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody  # type: ignore
                    req = (
                        ReplyMessageRequest.builder()
                        .message_id(event.message_obj.message_id)
                        .request_body(
                            ReplyMessageRequestBody.builder()
                            .content(json.dumps({"zh_cn": {"title": "", "content": [[{"tag": "md", "text": "正在全力搜索中...."}]]}}))
                            .msg_type("post")
                            .build()
                        )
                        .build()
                    )
                    resp = await event.bot.im.v1.message.areply(req)  # type: ignore
                    if resp and resp.success():
                        progress_msg_id = getattr(resp.data, "message_id", None)
            except Exception:
                pass
            
            async with aiohttp.ClientSession() as session:
                # 新接口：/api/search_ebooklib 或备用API
                # 调整 size=16 以支持 2x8 按钮
                is_eight_digits = keyword.isdigit() and len(keyword) == 8
                page_size = 1 if is_eight_digits else 16
                
                # 对于非8位数字的搜索，先检查缓存
                user_id = event.get_sender_id()
                
                # 用户配额记录由通用系统自动管理，无需手动创建
                
                cache_key = None
                if not is_eight_digits:
                    # 缓存键包含API源信息
                    cache_key = self._generate_cache_key(user_id, f"{keyword}_{api_source}", 1)
                    cached_result = self.db.get_search_cache(cache_key)
                    if cached_result:
                        logger.debug(f"使用搜索缓存: {keyword} ({api_source})")
                        books = json.loads(cached_result.results)
                        total = cached_result.total_count
                        limit = page_size
                        offset = 0
                    else:
                        # 根据API源选择搜索函数
                        if api_source == "alternative":
                            data = await _search_via_alternative_api(session, keyword, page=1, size=page_size)
                        else:
                            data = await _search_via_ebooklib(session, keyword, page=1, size=page_size)
                        
                        books = data.get("books") or []
                        total = int(data.get("total") or 0)
                        offset = int(data.get("offset") or 0)
                        limit = int(data.get("limit") or page_size)
                        
                        # 保存到搜索缓存
                        if books:
                            search_cache = BookSearchCache(
                                cache_key=cache_key,
                                user_id=user_id,
                                keyword=f"{keyword}_{api_source}",  # 包含API源信息
                                results=json.dumps(books, ensure_ascii=False),
                                total_count=total,
                                current_page=1,
                                created_time=datetime.now()
                            )
                            self.db.save_search_cache(search_cache)
                else:
                    # 8位数字只使用默认API
                    data = await _search_via_ebooklib(session, keyword, page=1, size=page_size)
                    books = data.get("books") or []
                    total = int(data.get("total") or 0)
                    offset = int(data.get("offset") or 0)
                    limit = int(data.get("limit") or page_size)

                # 写入会话缓存（用于回首页）
                self._cache_set(event.get_session_id(), keyword, 1, limit)

                if is_eight_digits:
                    async for r in self._show_book_details(event, keyword, session, books=books):
                        yield r
                    
                    # 删除进度条
                    if progress_msg_id is not None and hasattr(event, "delete_message"):
                        try:
                            await event.delete_message(progress_msg_id)
                        except Exception:
                            pass
                    return

                # 关键词检索：列表 + 快捷按钮 + 翻页
                lines = []
                detail_buttons = []
                for idx, b in enumerate(books, start=1):
                    ssid = str(b.get("id") or "")
                    title = str(b.get("title") or "")
                    author = str(b.get("author") or "").strip()
                    ext = str(b.get("extension") or "").lower()
                    fs = int(b.get("filesize") or 0)
                    size_h = _bytes_to_human(fs)
                    
                    # 构建显示行，包含作者信息
                    if api_source == "alternative":
                        # 备用API：标题通常已包含文件后缀，避免重复
                        if author and author != "":
                            line = f"{idx}.【{ssid}】{title} - {author} {size_h}"
                        else:
                            line = f"{idx}.【{ssid}】{title} {size_h}"
                    else:
                        # 默认API：需要添加文件后缀
                        if author and author != "":
                            line = f"{idx}.【{ssid}】{title} - {author}.{ext} {size_h}"
                        else:
                            line = f"{idx}.【{ssid}】{title}.{ext} {size_h}"
                    lines.append(line)
                    
                    # 根据API源创建不同的详情按钮
                    if api_source == "alternative":
                        # 备用API：从原始数据中获取link信息用于直接复制消息
                        try:
                            link = b.get("link", "")
                            if link:
                                group_id = ""
                                message_id = ""
                                
                                if "/c/" in link:
                                    # 格式1：https://t.me/c/2011682900/668274
                                    parts = link.split("/c/")[1].split("/")
                                    if len(parts) >= 2:
                                        group_id = f"-100{parts[0]}"
                                        message_id = parts[1]
                                elif "t.me/" in link and "/c/" not in link:
                                    # 格式2：https://t.me/WaiKan2023/50282
                                    parts = link.split("t.me/")[1].split("/")
                                    if len(parts) >= 2:
                                        group_id = f"@{parts[0]}"  # 用户名格式
                                        message_id = parts[1]
                                
                                if group_id and message_id:
                                    # 简化callback_data格式，只保留必要信息
                                    cb = f"book_alt_copy|{group_id}|{message_id}|{idx}"
                                    detail_buttons.append({"text": str(idx), "callback_data": cb})
                        except Exception:
                            # 如果解析失败，仍然创建默认的详情按钮
                            if ssid.isdigit() and len(ssid) == 8:
                                cb = f"book_detail|{ssid}"
                                detail_buttons.append({"text": str(idx), "callback_data": cb})
                    else:
                        # 默认API：为有效的8位SSID创建详情按钮
                        if ssid.isdigit() and len(ssid) == 8:
                            cb = f"book_detail|{ssid}"
                            detail_buttons.append({"text": str(idx), "callback_data": cb})

                # 组装消息文本
                text_out = "\n\n".join(lines) if lines else "未找到任何结果，请尝试换源搜索"
                current_page = (offset // limit) + 1
                source_text = "备用源" if api_source == "alternative" else "默认源"
                if lines:
                    text_out += f"\n\n💡 点击数字查看详情 | 第 {current_page} 页 | {source_text}"

                # 键盘：详情按钮 + 翻页按钮 + 换源按钮
                kb = InlineKeyboard()
                
                # 详情按钮（数字），每行8个
                if detail_buttons:
                    for i in range(0, len(detail_buttons), 8):
                        kb.add_row(*detail_buttons[i:i+8])

                # 翻页按钮
                total_pages = max(1, (total + limit - 1) // limit)
                prev_page = max(1, current_page - 1)
                next_page = min(total_pages, current_page + 1)

                prev_cb = _encode_callback_data(keyword, prev_page, limit, 0, prefix="book", api_source=api_source)
                next_cb = _encode_callback_data(keyword, next_page, limit, 0, prefix="book", api_source=api_source)
                home_cb = _encode_callback_data(keyword, 1, limit, 0, prefix="book", api_source=api_source)
                
                nav_row = []
                if current_page > 1 and prev_cb:
                    nav_row.append({"text": "⬅️ 上一页", "callback_data": prev_cb})
                if current_page > 1 and home_cb:
                    nav_row.append({"text": "🏠 首页", "callback_data": home_cb})
                if current_page < total_pages and next_cb:
                    nav_row.append({"text": "➡️ 下一页", "callback_data": next_cb})
                
                if nav_row:
                    kb.add_row(*nav_row)

                # 换源按钮（只对非8位数字搜索显示）
                if not is_eight_digits:
                    switch_source = "default" if api_source == "alternative" else "alternative"
                    switch_text = "🔄 默认搜" if api_source == "alternative" else "🔄 换源搜"
                    switch_cb = _encode_callback_data(keyword, 1, limit, 0, prefix="book", api_source=switch_source)
                    if switch_cb:
                        kb.add_row({"text": switch_text, "callback_data": switch_cb})

                if kb.buttons:
                    yield event.chain_result([Plain(text_out), kb])
                else:
                    yield event.plain_result(text_out)
                # 删除进度条（发送结果后）
                if progress_msg_id is not None and hasattr(event, "delete_message"):
                    try:
                        await event.delete_message(progress_msg_id)
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"[yunpan-book-search] 调用异常: {e}")
            yield event.plain_result(f"搜索失败：{e}")

    @filter.command("搜")
    async def search_cmd(self, event: AstrMessageEvent):
        text = event.message_str or ""
        keyword = text.split(maxsplit=1)[1].strip() if " " in text else ""
        if not keyword:
            yield event.plain_result("请提供关键词，例如：/搜 三体")
            return

        logger.info(f"[yunpan-search] keyword={keyword}")
        
        # 配额检查（使用通用系统）
        user_id = event.get_sender_id()
        if self.common_quota_validator:
            result = await self.common_quota_validator.check_quota(
                user_id=user_id,
                action_type="yunpan_search",
                plugin_name="yunpan",
                use_points=True
            )
            
            if not result.allowed:
                yield event.plain_result(result.message)
                return

        try:
            # progress message
            progress_msg_id = None
            platform_name = (event.get_platform_name() or "").lower()
            try:
                if platform_name == "telegram":
                    from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent  # type: ignore
                    if isinstance(event, TelegramPlatformEvent):
                        chat_id = event.message_obj.group_id or event.get_sender_id()
                        msg = await event.client.send_message(chat_id=chat_id, text="正在全力搜索中....")
                        progress_msg_id = getattr(msg, "message_id", None)
                elif platform_name == "lark":
                    from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody  # type: ignore
                    req = (
                        ReplyMessageRequest.builder()
                        .message_id(event.message_obj.message_id)
                        .request_body(
                            ReplyMessageRequestBody.builder()
                            .content(json.dumps({"zh_cn": {"title": "", "content": [[{"tag": "md", "text": "正在全力搜索中...."}]]}}))
                            .msg_type("post")
                            .build()
                        )
                        .build()
                    )
                    resp = await event.bot.im.v1.message.areply(req)  # type: ignore
                    if resp and resp.success():
                        progress_msg_id = getattr(resp.data, "message_id", None)
            except Exception:
                pass

            async with aiohttp.ClientSession() as session:
                # 1) 优先调用新接口
                try:
                    disk_out = await _search_via_disk_api(session, keyword)
                except Exception as e:
                    logger.error(f"[yunpan-search] disk api failed: {e}")
                    disk_out = ""

                if disk_out and disk_out.strip():
                    # 搜索成功，消费配额
                    if self.common_quota_validator:
                        await self.common_quota_validator.consume_quota(
                            user_id=user_id,
                            action_type="yunpan_search",
                            plugin_name="yunpan",
                            points_cost=result.points_cost if 'result' in locals() and hasattr(result, 'points_cost') else 0
                        )
                    
                    # 记录会话级缓存（第一页）
                    self._cache_set(event.get_session_id(), keyword, 1, 15)
                    
                    # 如果是 Telegram 或飞书，使用 InlineKeyboard 组件
                    platform_name = (event.get_platform_name() or "").lower()
                    if platform_name in ["telegram", "lark"]:
                        page = 1
                        size = 15
                        kw = keyword
                        prev_cb = _encode_callback_data(kw, max(1, page-1), size, 0)
                        next_cb = _encode_callback_data(kw, page+1, size, 0)
                        
                        # 兼容 callback_data 限制
                        if prev_cb and next_cb:
                            keyboard = InlineKeyboard()
                            
                            # 第一页时只显示下一页按钮
                            if page > 1:
                                prev_text = "⬅️ 上一页"
                                home_text = "🏠 首页"
                                next_text = "➡️ 下一页"
                                home_cb = _encode_callback_data(kw, 1, size, 0)
                                
                                keyboard.add_button(prev_text, callback_data=prev_cb)
                                keyboard.add_button(home_text, callback_data=home_cb)
                                keyboard.add_button(next_text, callback_data=next_cb)
                            else:
                                # 第一页时只显示下一页
                                next_text = "➡️ 下一页"
                                keyboard.add_button(next_text, callback_data=next_cb)
                            
                            # 在同一个消息中发送文本和键盘
                            yield event.chain_result([Plain(disk_out), keyboard])
                        else:
                            yield event.plain_result(disk_out)
                    else:
                        yield event.plain_result(disk_out)
                    # delete progress after sending
                    if progress_msg_id is not None and hasattr(event, "delete_message"):
                        try:
                            await event.delete_message(progress_msg_id)
                        except Exception:
                            pass
                    return

                # 2) 回退到旧接口
                try:
                    legacy_out = await _search_via_legacy_api(session, keyword)
                except Exception as e:
                    logger.error(f"[yunpan-search] legacy api failed: {e}")
                    legacy_out = ""
                yield event.plain_result(legacy_out or "未找到任何结果，请尝试换源搜索")
                # delete progress after sending
                if progress_msg_id is not None and hasattr(event, "delete_message"):
                    try:
                        await event.delete_message(progress_msg_id)
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"[yunpan-search] 调用异常: {e}")
            yield event.plain_result(f"搜索失败：{e}")

    @filter.command("书")
    async def search_book_cmd(self, event: AstrMessageEvent):
        text = event.message_str or ""
        keyword = text.split(maxsplit=1)[1].strip() if " " in text else ""
        if not keyword:
            yield event.plain_result("请提供关键词，例如：/书 三体")
            return

        logger.info(f"[yunpan-book] keyword={keyword}")

        # 调用公共的搜索逻辑
        async for result in self._execute_book_search(event, keyword):
            yield result

    @filter.command("书配额")
    async def book_quota_cmd(self, event: AstrMessageEvent):
        """查询书籍下载配额"""
        try:
            user_id = event.get_sender_id()
            # 使用通用配额系统查询
            if self.common_quota_validator:
                # 获取今日已使用次数
                from datetime import date
                today = date.today()
                used_count = self.common_quota_validator.db.execute_one(
                    "SELECT COALESCE(SUM(count), 0) as total FROM quota_usage WHERE user_id = ? AND action_type = 'yunpan_download' AND usage_date = ?",
                    (user_id, today)
                )
                used = used_count['total'] if used_count else 0
                
                # 获取会员等级和配额限制
                member_level = self.common_quota_validator._get_member_level(user_id)
                rule = self.common_quota_validator._get_quota_rule('yunpan_download', member_level)
                
                if rule:
                    daily_limit, points_cost = rule
                    if daily_limit == -1:
                        quota_status = f"📊 云盘下载配额\n\n✅ 会员用户：无限制"
                    else:
                        remaining = max(0, daily_limit - used)
                        quota_status = f"📊 云盘下载配额\n\n今日已用：{used}次\n今日剩余：{remaining}次\n每日限额：{daily_limit}次"
                else:
                    quota_status = "📊 云盘下载配额\n\n❌ 未找到配额规则"
                
                yield event.plain_result(quota_status)
            else:
                yield event.plain_result("❌ 配额系统未初始化")
        except Exception as e:
            logger.error(f"[yunpan-quota] 查询配额异常: {e}")
            yield event.plain_result(f"❌ 查询配额失败: {e}")

    @filter.command("callback")
    async def callback_handler(self, event: AstrMessageEvent):
        """处理 Telegram 回调翻页：/callback disk:k=xxx|p=2|s=15"""
        try:
            platform_name = (event.get_platform_name() or "").lower()
            if platform_name not in ["telegram", "lark"]:
                return

            raw = event.message_str or ""
            parts = raw.split(" ", 1)
            if len(parts) < 2:
                return
            data = parts[1].strip()
            if not data:
                return

            # 检查是否是我们处理的回调类型
            is_json_callback = False
            json_data = None
            
            # 尝试解析 JSON 格式的回调数据（飞书新版本）
            if data.startswith("{") and data.endswith("}"):
                try:
                    import json
                    json_data = json.loads(data)
                    action_type = json_data.get("action", "")
                    if action_type in ["download_pdf", "ai_interpret", "callback"]:
                        is_json_callback = True
                        logger.debug(f"[yunpan-callback] 解析到JSON回调: {json_data}")
                except Exception as e:
                    logger.debug(f"[yunpan-callback] JSON解析失败: {e}")
            
            # 检查传统格式的回调类型
            if not is_json_callback and not (data.startswith("book_detail|") or 
                    data.startswith("book_alt_copy|") or
                    data.startswith("disk|") or 
                    data.startswith("book|") or
                    data.startswith("download_pdf_") or
                    data.startswith("ai_interpret_")):
                # 不是我们处理的回调类型，直接返回，让其他插件处理
                return

            # 处理 JSON 格式的飞书回调
            if is_json_callback and json_data:
                action_type = json_data.get("action", "")
                
                if action_type == "download_pdf":
                    try:
                        # 解析 JSON 格式：{"action": "download_pdf", "ssid": "xxx", "file_id": "xxx"}
                        ssid = json_data.get("ssid", "")
                        file_id = json_data.get("file_id", "")
                        
                        if not ssid or not file_id:
                            # 设置回调响应
                            self._set_callback_response(event, "error", "回调数据不完整", "Callback data incomplete")
                            yield event.plain_result("❌ 回调数据不完整")
                            return
                        
                        user_id = event.get_sender_id()
                        
                        # 检查配额（使用通用系统）
                        quota_check_result = None
                        if self.common_quota_validator:
                            quota_check_result = await self.common_quota_validator.check_quota(
                                user_id=user_id,
                                action_type="yunpan_download",
                                plugin_name="yunpan",
                                use_points=True
                            )
                            
                            if not quota_check_result.allowed:
                                self._set_callback_response(event, "warning", "今日下载配额已用完", "Daily download quota exhausted")
                                yield event.plain_result(quota_check_result.message)
                                return
                        
                        # 设置成功的回调响应
                        self._set_callback_response(event, "success", "PDF下载请求已提交", "PDF download request submitted")
                        
                        # 构造下载链接
                        download_url = f"https://t.me/zslraibot/?start=gb_{ssid}_{file_id}"
                        
                        # 消费配额（使用通用系统）
                        if self.common_quota_validator and quota_check_result:
                            await self.common_quota_validator.consume_quota(
                                user_id=user_id,
                                action_type="yunpan_download",
                                plugin_name="yunpan",
                                points_cost=quota_check_result.points_cost
                            )
                        
                        # 发送下载链接
                        yield event.plain_result(f"📄 PDF下载链接：\n{download_url}\n\n💡 请复制链接到浏览器打开")
                        return
                    except Exception as e:
                        logger.error(f"[yunpan-json-pdf] 处理JSON PDF下载回调失败: {e}")
                        # 设置错误回调响应
                        self._set_callback_response(event, "error", "PDF下载失败", "PDF download failed")
                        yield event.plain_result(f"❌ PDF下载失败: {e}")
                        return
                
                elif action_type == "ai_interpret":
                    try:
                        # 解析 JSON 格式：{"action": "ai_interpret", "ssid": "xxx"}
                        ssid = json_data.get("ssid", "")
                        
                        if not ssid:
                            # 设置回调响应
                            self._set_callback_response(event, "error", "回调数据不完整", "Callback data incomplete")
                            yield event.plain_result("❌ 回调数据不完整")
                            return
                        
                        if ssid.isdigit() and len(ssid) == 8:
                            # 设置成功的回调响应
                            self._set_callback_response(event, "success", "AI解读请求已提交", "AI interpretation request submitted")
                            
                            # 直接执行AI解读，而不是返回链接
                            logger.debug(f"[yunpan-json-ai] 直接执行AI解读: {ssid}")
                            async for result in self._handle_ai_interpret(event, ssid):
                                yield result
                        else:
                            # 设置错误回调响应
                            self._set_callback_response(event, "error", "无效的书籍ID", "Invalid book ID")
                            yield event.plain_result("❌ 无效的书籍ID")
                        return
                    except Exception as e:
                        logger.error(f"[yunpan-json-ai] 处理JSON AI解读回调失败: {e}")
                        # 设置错误回调响应
                        self._set_callback_response(event, "error", "AI解读失败", "AI interpretation failed")
                        yield event.plain_result(f"❌ AI解读失败: {e}")
                        return
                
                elif action_type == "pagination":
                    try:
                        # 处理分页回调：{"action": "pagination", "type": "book", "keyword": "xxx", "page": 2, ...}
                        callback_type = json_data.get("type", "")
                        keyword = json_data.get("keyword", "")
                        page = json_data.get("page", 1)
                        size = json_data.get("size", 15)
                        llm = json_data.get("llm", 0)
                        api_source = json_data.get("api_source", "default")
                        
                        if not callback_type or not keyword:
                            # 设置回调响应
                            self._set_callback_response(event, "error", "回调数据不完整", "Callback data incomplete")
                            yield event.plain_result("❌ 回调数据不完整")
                            return
                        
                        # 设置成功的回调响应
                        self._set_callback_response(event, "success", "正在加载页面", "Loading page")
                        
                        # 构造传统格式的回调数据进行处理
                        traditional_data = f"{callback_type}|{keyword}|{page}|{size}|{llm}|{api_source}"
                        logger.debug(f"[yunpan-json-pagination] 转换为传统格式: {traditional_data}")
                        
                        # 获取飞书卡片更新token
                        card_token = getattr(event.message_obj, 'lark_card_token', None)
                        logger.debug(f"[yunpan-json-pagination] 获取到卡片token: {'有' if card_token else '无'}")
                        if card_token:
                            logger.debug(f"[yunpan-json-pagination] 卡片token前20字符: {card_token[:20]}...")
                        
                        # 处理分页逻辑
                        async for result in self._handle_pagination_callback(event, traditional_data, card_token):
                            yield result
                        return
                    except Exception as e:
                        logger.error(f"[yunpan-json-pagination] 处理JSON分页回调失败: {e}")
                        # 设置错误回调响应
                        self._set_callback_response(event, "error", "分页处理失败", "Pagination failed")
                        yield event.plain_result(f"❌ 分页处理失败: {e}")
                        return
                
                elif action_type == "yunpan_douban_search":
                    try:
                        # 处理豆瓣搜索回调：{"action": "yunpan_douban_search", "type": "book", "id": "xxx", "title": "xxx"}
                        douban_type = json_data.get("type", "")
                        douban_id = json_data.get("id", "")
                        title = json_data.get("title", "")
                        
                        if not douban_type or not douban_id:
                            # 设置回调响应
                            self._set_callback_response(event, "error", "回调数据不完整", "Callback data incomplete")
                            yield event.plain_result("❌ 回调数据不完整")
                            return
                        
                        # 设置成功的回调响应
                        self._set_callback_response(event, "success", "正在搜索资源", "Searching resources")
                        
                        # 根据类型调用相应的搜索流程
                        logger.debug(f"[yunpan-douban-search] 豆瓣搜索请求: type={douban_type}, id={douban_id}, title={title}")
                        
                        if douban_type == "movie":
                            # 调用电影搜索流程
                            async for result in self._handle_movie_search(event, title):
                                yield result
                        elif douban_type == "book":
                            # 调用书籍搜索流程
                            async for result in self._handle_book_search(event, title):
                                yield result
                        else:
                            yield event.plain_result(f"❌ 不支持的搜索类型: {douban_type}")
                        
                        return
                    except Exception as e:
                        logger.error(f"[yunpan-douban-search] 处理豆瓣搜索回调失败: {e}")
                        # 设置错误回调响应
                        self._set_callback_response(event, "error", "搜索失败", "Search failed")
                        yield event.plain_result(f"❌ 搜索失败: {e}")
                        return
                
                elif action_type == "callback":
                    try:
                        # 处理通用回调数据：{"action": "callback", "data": "xxx"}
                        callback_data = json_data.get("data", "")
                        if callback_data:
                            logger.debug(f"[yunpan-json-callback] 处理通用回调: {callback_data}")
                            
                            # 先尝试解析嵌套 JSON（豆瓣->云盘的直连回调）
                            is_douban_search = False
                            try:
                                if callback_data.startswith('{') and callback_data.endswith('}'):
                                    nested = json.loads(callback_data)
                                    if nested.get('action') == 'yunpan_douban_search':
                                        is_douban_search = True
                                        douban_type = nested.get('type', '')
                                        douban_id = nested.get('id', '')
                                        title = nested.get('title', '')
                                        if not douban_type or not douban_id:
                                            self._set_callback_response(event, "error", "回调数据不完整", "Callback data incomplete")
                                            yield event.plain_result("❌ 回调数据不完整")
                                            return
 
                                        
                                        # 执行搜索
                                        if douban_type == 'movie':
                                            async for r in self._handle_movie_search(event, title):
                                                yield r
                                        elif douban_type == 'book':
                                            async for r in self._handle_book_search(event, title):
                                                yield r
                                        else:
                                            yield event.plain_result(f"❌ 不支持的搜索类型: {douban_type}")
                                        
                            except Exception as e:
                                logger.debug(f"[yunpan-json-callback] 嵌套JSON解析失败: {e}")
                            
                            # 检查是否是云盘插件的常规回调
                            if not (callback_data.startswith("book|") or 
                                    callback_data.startswith("disk|") or
                                    callback_data.startswith("book_detail|") or
                                    callback_data.startswith("book_alt_copy|") or
                                    callback_data.startswith("download_pdf_") or
                                    callback_data.startswith("ai_interpret_")):
                                # 不是云盘插件的回调，直接返回让其他插件处理
                                logger.debug(f"[yunpan-json-callback] 非云盘回调，跳过: {callback_data}")
                                return
                            
                            # 获取飞书卡片更新token
                            card_token = getattr(event.message_obj, 'lark_card_token', None)
                            logger.debug(f"[yunpan-json-callback] 获取到卡片token: {'有' if card_token else '无'}")
                            if card_token:
                                logger.debug(f"[yunpan-json-callback] 卡片token前20字符: {card_token[:20]}...")
                            
                            # 直接处理分页逻辑，避免递归调用丢失token
                            if callback_data.startswith("book|") or callback_data.startswith("disk|"):
                                async for result in self._handle_pagination_callback(event, callback_data, card_token):
                                    yield result
                            else:
                                # 其他类型的回调，重新构造事件消息处理
                                event.message_str = f"/callback {callback_data}"
                                async for result in self.callback_handler(event):
                                    yield result
                        return
                    except Exception as e:
                        logger.error(f"[yunpan-json-callback] 处理JSON通用回调失败: {e}")
                        yield event.plain_result(f"❌ 回调处理失败: {e}")
                        return

            # 处理传统格式的飞书PDF下载回调
            if data.startswith("download_pdf_"):
                try:
                    # 解析格式：download_pdf_{ssid}_{file_id}
                    parts = data.split("_", 2)
                    if len(parts) >= 3:
                        ssid = parts[1]
                        file_id = parts[2]
                        
                        user_id = event.get_sender_id()
                        
                        # 检查配额（使用通用系统）
                        quota_check_result = None
                        if self.common_quota_validator:
                            quota_check_result = await self.common_quota_validator.check_quota(
                                user_id=user_id,
                                action_type="yunpan_download",
                                plugin_name="yunpan",
                                use_points=True
                            )
                            
                            if not quota_check_result.allowed:
                                yield event.plain_result(quota_check_result.message)
                                return
                        
                        # 检查平台类型，飞书使用Toast提示
                        platform_name = (event.get_platform_name() or "").lower()
                        
                        if platform_name == "lark":
                            # 飞书平台：发送Toast提示 + 私聊发送下载链接
                            # 构造下载链接
                            download_url = f"https://t.me/zslraibot/?start=gb_{ssid}_{file_id}"
                            
                            # 消费配额（使用通用系统）
                            if self.common_quota_validator and quota_check_result:
                                await self.common_quota_validator.consume_quota(
                                    user_id=user_id,
                                    action_type="yunpan_download",
                                    plugin_name="yunpan",
                                    points_cost=quota_check_result.points_cost
                                )
                            
                            # 发送下载链接到私聊
                            yield event.plain_result(f"📄 PDF下载链接已发送到您的私聊\n\n下载链接：{download_url}\n\n💡 请复制链接到浏览器打开")
                        else:
                            # 其他平台：发送进度提示
                            yield event.plain_result("📚 正在获取PDF文件，请稍等...")
                            
                            # 构造下载链接
                            download_url = f"https://t.me/zslraibot/?start=gb_{ssid}_{file_id}"
                            
                            # 消费配额（使用通用系统）
                            if self.common_quota_validator and quota_check_result:
                                await self.common_quota_validator.consume_quota(
                                    user_id=user_id,
                                    action_type="yunpan_download",
                                    plugin_name="yunpan",
                                    points_cost=quota_check_result.points_cost
                                )
                            
                            # 发送下载链接
                            yield event.plain_result(f"📄 PDF下载链接：\n{download_url}\n\n💡 请复制链接到浏览器打开")
                        return
                except Exception as e:
                    logger.error(f"[yunpan-lark-pdf] 处理PDF下载回调失败: {e}")
                    yield event.plain_result(f"❌ PDF下载失败: {e}")
                    return
            
            # 处理飞书AI解读回调
            if data.startswith("ai_interpret_"):
                try:
                    # 解析格式：ai_interpret_{ssid}
                    ssid = data.replace("ai_interpret_", "")
                    
                    if ssid.isdigit() and len(ssid) == 8:
                        # 构造AI解读链接
                        ai_url = f"https://t.me/zslraibot/?start=ai_interpret_{ssid}"
                        yield event.plain_result(f"🤖 AI解读链接：\n{ai_url}\n\n💡 请复制链接到浏览器打开")
                    else:
                        yield event.plain_result("❌ 无效的书籍ID")
                    return
                except Exception as e:
                    logger.error(f"[yunpan-lark-ai] 处理AI解读回调失败: {e}")
                    yield event.plain_result(f"❌ AI解读失败: {e}")
                    return

            # 优先处理备用API的直接复制回调
            if data.startswith("book_alt_copy|"):
                try:
                    # 解析格式：book_alt_copy|{group_id}|{message_id}|{idx}
                    parts = data.split("|", 3)
                    if len(parts) >= 4:
                        group_id, message_id, book_idx = parts[1], parts[2], parts[3]
                        
                        user_id = event.get_sender_id()
                        
                        # 检查配额（使用通用系统）
                        quota_check_result = None
                        if self.common_quota_validator:
                            quota_check_result = await self.common_quota_validator.check_quota(
                                user_id=user_id,
                                action_type="yunpan_download",
                                plugin_name="yunpan",
                                use_points=True
                            )
                            
                            if not quota_check_result.allowed:
                                yield event.plain_result(quota_check_result.message)
                                return
                        
                        # 发送进度提示
                        progress_msg_id = None
                        platform_name = (event.get_platform_name() or "").lower()
                        try:
                            if platform_name == "telegram":
                                from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                                if isinstance(event, TelegramPlatformEvent):
                                    chat_id = event.message_obj.group_id or event.get_sender_id()
                                    msg = await event.client.send_message(chat_id=chat_id, text="文件发送任务已提交，请稍等待...")
                                    progress_msg_id = getattr(msg, "message_id", None)
                        except Exception:
                            pass
                        
                        # 构建复制消息的参数
                        if group_id.startswith("@"):
                            # 用户名格式：@WaiKan2023
                            from_peer = group_id
                        else:
                            # 数字ID格式：-1002011682900
                            from_peer = int(group_id)
                        
                        to_peer = f"@{event.get_self_id()}"
                        msg_id = int(message_id)
                        
                        # 构建书籍信息（简化版，因为没有详细信息）
                        book_info = f"备用源文件,索引:{book_idx}"
                        caption = f"receive:{event.get_sender_id()}|book_info:{book_info}"
                        
                        params = {
                            "data[from_peer]": from_peer,
                            "data[to_peer]": to_peer,
                            "data[id][0]": msg_id,
                            "data[caption]": caption,
                        }
                        
                        # 调用复制消息接口
                        url = "http://tglyjapi.zslren.com/api/copyMessages/"
                        async with aiohttp.ClientSession(trust_env=True) as session:
                            async with session.get(url, params=params, timeout=15) as resp:
                                _ = await resp.text()
                        
                        # 消费配额（使用通用系统）
                        if self.common_quota_validator and quota_check_result:
                            try:
                                await self.common_quota_validator.consume_quota(
                                    user_id=user_id,
                                    action_type="yunpan_download",
                                    plugin_name="yunpan",
                                    points_cost=quota_check_result.points_cost
                                )
                            except Exception as e:
                                logger.error(f"消耗配额失败: {e}")
                        
                        # 等待文件转发完成后删除提示消息
                        if progress_msg_id is not None:
                            await asyncio.sleep(3)
                            if hasattr(event, "delete_message"):
                                try:
                                    await event.delete_message(progress_msg_id)
                                except Exception:
                                    pass
                        
                except Exception as e:
                    logger.error(f"[yunpan-alt-copy] 处理备用API复制失败: {e}")
                    yield event.plain_result("文件发送任务失败，请稍后重试或反馈管理员。")
                return

            # 处理书籍详情回调（默认API）
            if data.startswith("book_detail|"):
                progress_msg_id = None
                try:
                    ssid = data.split("|", 1)[1].strip()
                    if ssid:
                        # 1. 发送进度提示消息
                        platform_name = (event.get_platform_name() or "").lower()
                        if platform_name == "telegram":
                            from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent  # type: ignore
                            if isinstance(event, TelegramPlatformEvent):
                                chat_id = event.message_obj.group_id or event.get_sender_id()
                                msg = await event.client.send_message(chat_id=chat_id, text="🔍 正在获取书籍详情，请稍候...")
                                progress_msg_id = getattr(msg, "message_id", None)

                        # 2. 获取并发送书籍详情
                        async with aiohttp.ClientSession() as session:
                            async for r in self._show_book_details(event, ssid, session):
                                yield r

                finally:
                    # 3. 删除进度提示消息
                    if progress_msg_id:
                        try:
                            platform_name = (event.get_platform_name() or "").lower()
                            if platform_name == "telegram":
                                from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                                if isinstance(event, TelegramPlatformEvent):
                                    chat_id = event.message_obj.group_id or event.get_sender_id()
                                    await event.client.delete_message(
                                        chat_id=chat_id, 
                                        message_id=progress_msg_id
                                    )
                        except Exception as e:
                            logger.warning(f"删除书籍详情进度消息失败: {e}")
                return

            # 解析 callback_data（标准分页回调）
            params = _decode_callback_data(data)
            if not params:
                return
            
            prefix = params.get("prefix", "")
            keyword = params.get("k", "")
            page = params.get("p", 1)
            size = params.get("s", 15)
            api_source = params.get("api_source", "default")

            if not keyword:
                return

            # 执行搜索
            async with aiohttp.ClientSession() as session:
                if prefix == "disk":
                    text_out = await _search_via_disk_api(session, keyword, page=page, size=size)
                elif prefix == "book":
                    # 关键词分页：根据 page/size 取 offset，支持API源切换
                    if api_source == "alternative":
                        data = await _search_via_alternative_api(session, keyword, page=page, size=size)
                    else:
                        data = await _search_via_ebooklib(session, keyword, page=page, size=size)
                    
                    books = data.get("books") or []
                    total = int(data.get("total") or 0)
                    offset = int(data.get("offset") or 0)
                    limit = int(data.get("limit") or size)

                    lines: List[str] = []
                    detail_buttons = []
                    for idx, b in enumerate(books, start=1):
                        ssid = str(b.get("id") or "")
                        title = str(b.get("title") or "")
                        author = str(b.get("author") or "").strip()
                        ext = str(b.get("extension") or "").lower()
                        fs = int(b.get("filesize") or 0)
                        size_h = _bytes_to_human(fs)
                        
                        # 构建显示行，包含作者信息
                        if api_source == "alternative":
                            # 备用API：标题通常已包含文件后缀，避免重复
                            if author and author != "":
                                line = f"{idx}.【{ssid}】{title} - {author} {size_h}"
                            else:
                                line = f"{idx}.【{ssid}】{title} {size_h}"
                        else:
                            # 默认API：需要添加文件后缀
                            if author and author != "":
                                line = f"{idx}.【{ssid}】{title} - {author}.{ext} {size_h}"
                            else:
                                line = f"{idx}.【{ssid}】{title}.{ext} {size_h}"
                        lines.append(line)
                        
                        # 根据API源创建不同的详情按钮
                        if api_source == "alternative":
                            # 备用API：从原始数据中获取link信息用于直接复制消息
                            try:
                                link = b.get("link", "")
                                if link:
                                    group_id = ""
                                    message_id = ""
                                    
                                    if "/c/" in link:
                                        # 格式1：https://t.me/c/2011682900/668274
                                        parts = link.split("/c/")[1].split("/")
                                        if len(parts) >= 2:
                                            group_id = f"-100{parts[0]}"
                                            message_id = parts[1]
                                    elif "t.me/" in link and "/c/" not in link:
                                        # 格式2：https://t.me/WaiKan2023/50282
                                        parts = link.split("t.me/")[1].split("/")
                                        if len(parts) >= 2:
                                            group_id = f"@{parts[0]}"  # 用户名格式
                                            message_id = parts[1]
                                    
                                    if group_id and message_id:
                                        # 简化callback_data格式，只保留必要信息
                                        cb = f"book_alt_copy|{group_id}|{message_id}|{idx}"
                                        detail_buttons.append({"text": str(idx), "callback_data": cb})
                            except Exception:
                                # 如果解析失败，仍然创建默认的详情按钮
                                if ssid.isdigit() and len(ssid) == 8:
                                    cb = f"book_detail|{ssid}"
                                    detail_buttons.append({"text": str(idx), "callback_data": cb})
                        else:
                            # 默认API：为有效的8位SSID创建详情按钮
                            if ssid.isdigit() and len(ssid) == 8:
                                cb = f"book_detail|{ssid}"
                                detail_buttons.append({"text": str(idx), "callback_data": cb})

                    # 组装消息文本
                    text_out = "\n\n".join(lines) if lines else "未找到任何结果，请尝试换源搜索"
                    current_page = (offset // limit) + 1
                    source_text = "备用源" if api_source == "alternative" else "默认源"
                    if lines:
                        text_out += f"\n\n💡 点击数字查看详情 | 第 {current_page} 页 | {source_text}"
                else:
                    text_out = ""

            # 生成新的键盘
            kb = InlineKeyboard()
            
            # 为书籍搜索添加详情按钮（数字），每行8个
            if prefix == "book" and 'detail_buttons' in locals():
                for i in range(0, len(detail_buttons), 8):
                    kb.add_row(*detail_buttons[i:i+8])
            
            # 翻页按钮
            prev_p = max(1, page - 1)
            next_p = page + 1
            cb_prefix = "disk" if prefix == "disk" else ("book" if prefix == "book" else "disk")
            
            # 计算总页数（对于书籍搜索）
            total_pages = 1
            if prefix == "book" and 'total' in locals() and 'limit' in locals():
                total_pages = max(1, (total + limit - 1) // limit)
            
            prev_cb = _encode_callback_data(keyword, prev_p, size, 0, prefix=cb_prefix, api_source=api_source)
            next_cb = _encode_callback_data(keyword, next_p, size, 0, prefix=cb_prefix, api_source=api_source)
            
            # 优先尝试编辑原消息（包含键盘）
            ok = False
            if prev_cb and next_cb:
                try:
                    if platform_name == "telegram":
                        from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                        if isinstance(event, TelegramPlatformEvent):
                            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                            
                            keyboard_buttons = []
                            
                            # 为书籍搜索添加详情按钮（数字），每行8个
                            if prefix == "book" and 'detail_buttons' in locals():
                                for i in range(0, len(detail_buttons), 8):
                                    row = [InlineKeyboardButton(text=btn['text'], callback_data=btn['callback_data']) 
                                           for btn in detail_buttons[i:i+8]]
                                    keyboard_buttons.append(row)
                            
                            # 翻页按钮
                            nav_row = []
                            
                            if page > 1:
                                prev_text = "⬅️ 上一页"
                                home_text = "🏠 首页"
                                home_cb = _encode_callback_data(keyword, 1, size, 0, prefix=cb_prefix, api_source=api_source)
                                
                                nav_row.extend([
                                    InlineKeyboardButton(prev_text, callback_data=prev_cb), 
                                    InlineKeyboardButton(home_text, callback_data=home_cb)
                                ])
                            
                            # 只有当前页小于总页数时才显示下一页按钮
                            if page < total_pages:
                                next_text = "➡️ 下一页"
                                nav_row.append(InlineKeyboardButton(next_text, callback_data=next_cb))
                            
                            if nav_row:
                                keyboard_buttons.append(nav_row)
                            
                            # 换源按钮（只对书籍搜索显示）
                            if prefix == "book":
                                switch_source = "default" if api_source == "alternative" else "alternative"
                                switch_text = "🔄 默认搜" if api_source == "alternative" else "🔄 换源搜"
                                switch_cb = _encode_callback_data(keyword, 1, size, 0, prefix="book", api_source=switch_source)
                                if switch_cb:
                                    keyboard_buttons.append([InlineKeyboardButton(switch_text, callback_data=switch_cb)])
                            
                            reply_markup = InlineKeyboardMarkup(keyboard_buttons)
                            
                            msg_id = int(event.message_obj.message_id)
                            chat_id = event.message_obj.group_id or event.get_sender_id()
                            
                            # 编辑消息文本和键盘
                            await event.client.edit_message_text(
                                chat_id=chat_id,
                                message_id=msg_id,
                                text=text_out,
                                reply_markup=reply_markup
                            )
                            ok = True
                    elif platform_name == "lark":
                        # 飞书平台：编辑消息（飞书支持编辑消息）
                        keyboard = InlineKeyboard()
                        
                        # 为书籍搜索添加详情按钮（数字），每行8个
                        if prefix == "book" and 'detail_buttons' in locals():
                            for i in range(0, len(detail_buttons), 8):
                                keyboard.add_row(*detail_buttons[i:i+8])
                        
                        # 翻页按钮
                        nav_row = []
                        
                        if page > 1:
                            prev_text = "⬅️ 上一页"
                            home_text = "🏠 首页"
                            home_cb = _encode_callback_data(keyword, 1, size, 0, prefix=cb_prefix, api_source=api_source)
                            
                            nav_row.extend([
                                {"text": prev_text, "callback_data": prev_cb},
                                {"text": home_text, "callback_data": home_cb}
                            ])
                        
                        # 只有当前页小于总页数时才显示下一页按钮
                        if page < total_pages:
                            next_text = "➡️ 下一页"
                            nav_row.append({"text": next_text, "callback_data": next_cb})
                        
                        if nav_row:
                            keyboard.add_row(*nav_row)
                        
                        # 换源按钮（只对书籍搜索显示）
                        if prefix == "book":
                            switch_source = "default" if api_source == "alternative" else "alternative"
                            switch_text = "🔄 默认搜" if api_source == "alternative" else "🔄 换源搜"
                            switch_cb = _encode_callback_data(keyword, 1, size, 0, prefix="book", api_source=switch_source)
                            if switch_cb:
                                keyboard.add_row({"text": switch_text, "callback_data": switch_cb})
                        
                        # 编辑原消息（包含键盘）
                        msg_id = event.message_obj.message_id
                        success = await event.edit_message(msg_id, text_out, keyboard)
                        if success:
                            ok = True
                        else:
                            # 编辑失败，发送新消息
                            yield event.chain_result([Plain(text_out), keyboard])
                            ok = True
                except Exception as e:
                    logger.warning(f"[yunpan-callback] 编辑消息失败: {e}")
                    ok = False

            if ok:
                return

            # 编辑失败：发送新消息 + 键盘
            try:
                if prev_cb and next_cb:
                    # 使用之前已经创建的键盘（包含数字按钮）
                    nav_row = []
                    
                    if page > 1:
                        prev_text = "⬅️ 上一页"
                        home_text = "🏠 首页"
                        home_cb = _encode_callback_data(keyword, 1, size, 0, api_source=api_source)
                        
                        nav_row.extend([
                            {"text": prev_text, "callback_data": prev_cb},
                            {"text": home_text, "callback_data": home_cb}
                        ])
                    
                    # 只有当前页小于总页数时才显示下一页按钮
                    if page < total_pages:
                        next_text = "➡️ 下一页"
                        nav_row.append({"text": next_text, "callback_data": next_cb})
                    
                    if nav_row:
                        kb.add_row(*nav_row)
                    
                    # 换源按钮（只对书籍搜索显示）
                    if prefix == "book":
                        switch_source = "default" if api_source == "alternative" else "alternative"
                        switch_text = "🔄 默认搜" if api_source == "alternative" else "🔄 换源搜"
                        switch_cb = _encode_callback_data(keyword, 1, size, 0, prefix="book", api_source=switch_source)
                        if switch_cb:
                            kb.add_row({"text": switch_text, "callback_data": switch_cb})
                    
                    # 在同一个消息中发送文本和键盘
                    yield event.chain_result([Plain(text_out), kb])
                else:
                    yield event.plain_result(text_out)
            except Exception as e:
                logger.error(f"[yunpan-callback] 处理回调时出错: {e}")
        except Exception as e:
            logger.error(f"[yunpan-callback] 未知错误: {e}")
 