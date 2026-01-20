"""
书籍搜索插件
支持多平台书籍资源搜索、下载和 AI 解读
"""
import json
import os
import re
import sys
import asyncio
import aiohttp
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.message.components import Image, Plain, InlineKeyboard, File
from astrbot.api.event import MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.core import callback_handler, auto_stop_event

# 添加插件根目录到 sys.path
plugin_root = Path(__file__).parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

# 导入通用模块
try:
    from common.platform_capabilities import get_platform_capabilities
    from common.loading_indicator import LoadingIndicator
    from common.database_manager import DatabaseManager as CommonDatabaseManager
    from common.quota_validator import QuotaValidator
    from common.session_manager import get_session_manager
    from common.search_statistics import get_search_statistics
    from common.user_utils import get_unified_user_id
    from common.search_helper import SearchHelper
    from common.message_formatter import get_separator
    COMMON_MODULES_AVAILABLE = True
except ImportError as e:
    COMMON_MODULES_AVAILABLE = False
    logger.warning(f"[Book] 通用模块不可用: {e}")
    # 兼容函数
    def get_unified_user_id(event):
        return event.get_sender_id()

# 导入内部模块
from .handlers.book_api import BookAPI
from .handlers.book_formatter import BookFormatter
from .handlers.session_handler import BookSessionHandler
from .handlers.response_builder import BookResponseBuilder
from .db.database import BookDatabaseManager
from .handlers.telegram_file_cache import BookFileCacheManager


async def is_image_url_valid(url: str) -> bool:
    """检查图片URL是否有效"""
    if not url or not url.startswith("http"):
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, timeout=5) as response:
                return response.status == 200 and "image" in response.headers.get("Content-Type", "")
    except Exception:
        return False


@register("book-search", "Chrismk", "书籍搜索插件，支持多平台书籍资源搜索", "2.0.0", "")
class BookSearchPlugin(Star):
    """书籍搜索插件"""
    
    PAGE_SIZE = 16
    SESSION_TIMEOUT_MINUTES = 1
    
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.plugin_config = config or {}
        
        # 加载插件配置
        self._load_plugin_config()
        
        astrbot_config = self.context.get_config()
        data_path = astrbot_config.get("data_path", "data")
        
        plugin_data_dir = os.path.join(data_path, "plugin_data", "book")
        os.makedirs(plugin_data_dir, exist_ok=True)
        db_path = os.path.join(plugin_data_dir, "book.db")
        
        self.db = BookDatabaseManager(db_path)
        self.book_api = BookAPI()
        
        self.session_manager = None
        self.session_handler = None
        self.quota_validator = None
        self.search_stats = None
        
        if COMMON_MODULES_AVAILABLE:
            self.session_manager = get_session_manager(timeout_minutes=self.SESSION_TIMEOUT_MINUTES)
            self.session_handler = BookSessionHandler(self.session_manager, self.book_api)
            
            try:
                quota_db_path = os.path.join(data_path, "quota_system.db")
                common_db = CommonDatabaseManager(quota_db_path)
                self.quota_validator = QuotaValidator(common_db)
                self.search_stats = get_search_statistics(common_db)
                # 搜索辅助器
                self.search_helper = SearchHelper(
                    plugin_name='book',
                    search_stats=self.search_stats,
                    page_size=self.PAGE_SIZE
                )
                self._register_quota_rules()
            except Exception as e:
                logger.error(f"[Book] 配额系统初始化失败: {e}")
        
        self.cache_mgr = BookFileCacheManager(self.db)
        
        try:
            self.db.cleanup_old_caches(days=7)
        except Exception:
            pass
        
        logger.info("[Book] 书籍搜索插件初始化完成")
    
    def _load_plugin_config(self):
        """加载插件配置"""
        defaults = {
            'page_size': 16,
            'session_timeout': 1,
            'quota_search_daily_limit': -1,
            'quota_search_points_cost': 0,
            'quota_download_daily_limit': -1,
            'quota_download_points_cost': 0,
            'rate_limit_search_max': 60,
            'rate_limit_search_window': 60,
            'rate_limit_download_max': 60,
            'rate_limit_download_window': 60,
            'rate_limit_ai_max': 60,
            'rate_limit_ai_window': 60
        }
        for key, default in defaults.items():
            if key not in self.plugin_config:
                self.plugin_config[key] = default
        
        # 应用配置
        self.PAGE_SIZE = self.plugin_config.get('page_size', 16)
        self.SESSION_TIMEOUT_MINUTES = self.plugin_config.get('session_timeout', 1)
    
    def _register_quota_rules(self):
        """注册配额和限流规则（使用标准化配置）"""
        if not self.quota_validator:
            return
        
        try:
            from common.plugin_quota_config import sync_plugin_quota_and_rate_limit
            
            actions = [
                {'action': 'search', 'action_type': 'book_search', 'description': '书籍搜索'},
                {'action': 'download', 'action_type': 'book_download', 'description': '书籍下载'},
                {'action': 'ai', 'action_type': 'book_ai', 'description': 'AI解读'}
            ]
            
            quota_success, rate_limit_success = sync_plugin_quota_and_rate_limit(
                plugin_name='book',
                plugin_config=self.plugin_config,
                quota_validator=self.quota_validator,
                actions=actions
            )
            
            if quota_success:
                logger.info("[Book] 配额规则同步成功")
            if rate_limit_success:
                logger.info("[Book] 限流规则同步成功")
                
        except ImportError:
            # 兼容旧版
            quota_rules = [
                {
                    'action_type': 'book_search',
                    'free': {'daily_limit': -1, 'points_cost': 0},
                    'premium': {'daily_limit': -1, 'points_cost': 0},
                    'vip': {'daily_limit': -1, 'points_cost': 0},
                    'description': '书籍搜索'
                },
                {
                    'action_type': 'book_download',
                    'free': {'daily_limit': -1, 'points_cost': 0},
                    'premium': {'daily_limit': -1, 'points_cost': 0},
                    'vip': {'daily_limit': -1, 'points_cost': 0},
                    'description': '书籍下载'
                }
            ]
            try:
                self.quota_validator.register_quota_rules(plugin_name='book', rules=quota_rules, override=False)
            except Exception as e:
                logger.error(f"[Book] 注册配额规则失败: {e}")
    
    @filter.command(command_name="书", command_alias=["book", "shu"])
    async def handle_book_command(self, event: AstrMessageEvent):
        """处理书籍搜索命令"""
        text = event.message_str or ""
        keyword = text.split(maxsplit=1)[1].strip() if " " in text else ""
        user_id = get_unified_user_id(event)
        
        if not keyword:
            # 使用搜索辅助器显示提示
            if COMMON_MODULES_AVAILABLE and hasattr(self, 'search_helper'):
                hint = self.search_helper.get_empty_search_hint(user_id)
                yield event.plain_result(hint)
            else:
                yield event.plain_result("请提供关键词，例如：/书 三体")
            return
        session_id = event.get_session_id()
        capabilities = get_platform_capabilities(event, "Book") if COMMON_MODULES_AVAILABLE else {}
        is_button_mode = capabilities.get('supports_buttons', False)
        
        # 检查配额
        if self.quota_validator:
            quota_result = await self.quota_validator.check_quota(
                user_id, 'book_search', 'book',
                username=event.get_sender_name(),
                platform=event.get_platform_name(),
                platform_user_id=user_id
            )
            if not quota_result.allowed:
                yield event.plain_result(quota_result.message)
                return
        
        loading_msg_id = await LoadingIndicator.show(event, 'search') if COMMON_MODULES_AVAILABLE else None
        
        try:
            is_eight_digits = keyword.isdigit() and len(keyword) == 8
            
            if is_eight_digits:
                # 记录ID搜索统计和配额消费
                if self.search_stats:
                    self.search_stats.record_search(user_id, 'book', keyword, 1, 'id', platform='default')
                if self.quota_validator:
                    await self.quota_validator.consume_quota(user_id, 'book_search', 'book')
                async for result in self._show_book_details(event, keyword, capabilities):
                    yield result
            else:
                books, total = await self.book_api.search_books(keyword, 1, self.PAGE_SIZE, "default")
                
                # 记录关键词搜索统计和配额消费
                if self.search_stats:
                    self.search_stats.record_search(user_id, 'book', keyword, total, 'keyword', platform='default')
                if self.quota_validator:
                    await self.quota_validator.consume_quota(user_id, 'book_search', 'book')
                
                if is_button_mode:
                    message, _ = BookFormatter.format_search_results(books, 1, self.PAGE_SIZE, total, "default", False)
                    builder = BookResponseBuilder(capabilities)
                    keyboard = builder.build_search_keyboard(books, keyword, 1, self.PAGE_SIZE, total, "default")
                    yield event.chain_result([Plain(message), keyboard]) if keyboard else event.plain_result(message)
                else:
                    if self.session_manager is not None:
                        self.session_manager.create_session(session_id=session_id, session_type="book_search", user_id=user_id, step=0, capabilities=capabilities, data={'keyword': keyword, 'page': 1, 'page_size': self.PAGE_SIZE, 'total': total, 'results': books, 'api_source': 'default'})
                    message, _ = BookFormatter.format_search_results(books, 1, self.PAGE_SIZE, total, "default", True, self.SESSION_TIMEOUT_MINUTES)
                    yield event.plain_result(message)
        except Exception as e:
            logger.error(f"[Book] 搜索失败: {e}", exc_info=True)
            yield event.plain_result("❌ 搜索失败，请稍后重试")
        finally:
            if COMMON_MODULES_AVAILABLE and loading_msg_id:
                await LoadingIndicator.hide(event, loading_msg_id)
        event.stop_event()
    
    @filter.command("callback")
    @callback_handler("book")
    @auto_stop_event
    async def handle_callback(self, event: AstrMessageEvent, data: str = ""):
        """处理回调 - 使用统一的 book: 前缀"""
        # 去掉可能的 book: 前缀
        if data.startswith("book:"):
            data = data[5:]
        
        if not data:
            return
        
        try:
            # 解析回调格式: action:params...
            parts = data.split(":", 1)
            action = parts[0]
            params = parts[1] if len(parts) > 1 else ""
            
            if action == "detail":
                # book:detail:ssid
                if params:
                    capabilities = get_platform_capabilities(event, "Book") if COMMON_MODULES_AVAILABLE else {}
                    async for result in self._show_book_details(event, params, capabilities):
                        yield result
            elif action == "alt_copy":
                # book:alt_copy:idx
                async for result in self._handle_alt_copy(event, params):
                    yield result
            elif action == "page":
                # book:page:keyword:page_num:page_size:api_source
                async for result in self._handle_pagination(event, params):
                    yield result
            elif action == "exit":
                async for result in self._handle_exit_callback(event):
                    yield result
        except Exception as e:
            logger.error(f"[Book] 回调处理失败: {e}", exc_info=True)
            yield event.plain_result("❌ 处理失败，请稍后重试")
    
    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """处理会话消息"""
        if event.get_result():
            return
        message_text = (event.message_str or "").strip()
        if not message_text or message_text.startswith('/') or message_text.startswith('callback '):
            return
        if self.session_manager is None:
            return
        session_id = event.get_session_id()
        
        # 优先处理会话消息
        # 使用 match_session 进行类型检查和自动续期
        if self.session_manager.match_session(session_id, 'book_search'):
            logger.debug(f"[Book] on_message: 检测到会话 - session_id={session_id}, message={message_text}")
            
            if self.session_handler:
                result = await self.session_handler.handle_session_message(get_unified_user_id(event), session_id, message_text)
                logger.debug(f"[Book] on_message: session_handler 返回 - result={result}")
                if result:
                    # 处理特殊返回标记
                    if isinstance(result, tuple) and len(result) >= 2:
                        if result[0] == "SHOW_BOOK_DETAIL":
                            capabilities = get_platform_capabilities(event, "Book") if COMMON_MODULES_AVAILABLE else {}
                            loading_msg_id = await LoadingIndicator.show(event, 'get_detail') if COMMON_MODULES_AVAILABLE else None
                            try:
                                async for r in self._show_book_details(event, result[1], capabilities):
                                    yield r
                            finally:
                                if COMMON_MODULES_AVAILABLE and loading_msg_id:
                                    await LoadingIndicator.hide(event, loading_msg_id)
                            event.stop_event()
                            return
                        if result[0] == "TRIGGER_AI_INTERPRET":
                            async for r in self._handle_ai_interpret(event, result[1]):
                                yield r
                            event.stop_event()
                            return
                        if result[0] == "TRIGGER_DOWNLOAD":
                            # 会话模式下检查平台是否支持发送文件
                            capabilities = get_platform_capabilities(event, "Book") if COMMON_MODULES_AVAILABLE else {}
                            platform_name = capabilities.get('platform_name', '').lower()
                            
                            if platform_name != 'telegram':
                                bot_username = event.get_self_id() or "zslraibot"
                                yield event.plain_result(f"❌ 当前平台不支持发送书籍文件，请在 TG @{bot_username} 中使用此功能")
                                event.stop_event()
                                return
                            
                            ssid, file_tag, backend_tag, source_type = result[1], result[2], result[3], result[4]
                            async for r in self._handle_book_download(event, ssid, file_tag, backend_tag, source_type):
                                yield r
                            event.stop_event()
                            return
                        if result[0] == "TRIGGER_PAGE":
                            # 翻页操作
                            new_page = result[1]
                            loading_msg_id = await LoadingIndicator.show(event, 'search') if COMMON_MODULES_AVAILABLE else None
                            try:
                                async for r in self._handle_session_page(event, session_id, new_page):
                                    yield r
                            finally:
                                if COMMON_MODULES_AVAILABLE and loading_msg_id:
                                    await LoadingIndicator.hide(event, loading_msg_id)
                            event.stop_event()
                            return
                        if result[0] == "TRIGGER_SWITCH":
                            # 换源操作
                            new_source = result[1]
                            loading_msg_id = await LoadingIndicator.show(event, 'search') if COMMON_MODULES_AVAILABLE else None
                            try:
                                async for r in self._handle_session_switch(event, session_id, new_source):
                                    yield r
                            finally:
                                if COMMON_MODULES_AVAILABLE and loading_msg_id:
                                    await LoadingIndicator.hide(event, loading_msg_id)
                            event.stop_event()
                            return
                    
                    # 普通消息
                    message, keyboard = result
                    if isinstance(message, str):
                        logger.debug(f"[Book] on_message: 发送消息 - message_len={len(message)}")
                        if keyboard:
                            yield event.chain_result([Plain(message), keyboard])
                        else:
                            yield event.plain_result(message)
                    event.stop_event()
                    return
        else:
            logger.debug(f"[Book] on_message: 没有会话或类型不匹配 - session_id={session_id}")
            return
    
    @filter.command("start")
    async def handle_start_command(self, event: AstrMessageEvent):
        """处理 /start 命令"""
        text = event.message_str or ""
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return
        param = parts[1].strip()
        
        if param.startswith("ai_interpret_"):
            async for result in self._handle_ai_interpret(event, param[13:]):
                yield result
            event.stop_event()
        elif param.startswith("bks_"):
            # 从豆瓣插件跳转过来的书籍搜索请求
            async for result in self._handle_douban_book_search(event, param[4:]):
                yield result
            event.stop_event()
        elif param.startswith("gb_"):
            p = param.split("_", 3)
            if len(p) >= 4:
                async for result in self._handle_book_download(event, p[1], p[2], p[3].replace("d", ".").replace("m", "-"), "group"):
                    yield result
                event.stop_event()
        elif param.startswith("bk_"):
            p = param.split("_", 3)
            if len(p) >= 4:
                async for result in self._handle_book_download(event, p[1], p[2], p[3], "api"):
                    yield result
                event.stop_event()
    
    async def _handle_douban_book_search(self, event: AstrMessageEvent, encoded_payload: str):
        """
        处理从豆瓣插件跳转过来的书籍搜索请求
        
        Args:
            event: 消息事件
            encoded_payload: Base64 编码的 payload，包含豆瓣 ID
        """
        import base64
        import json as json_module
        
        try:
            # 解码 payload
            decoded_bytes = base64.urlsafe_b64decode(encoded_payload)
            payload = json_module.loads(decoded_bytes.decode('utf-8'))
            douban_id = payload.get('id', '')
            
            if not douban_id:
                yield event.plain_result("❌ 搜索参数不完整")
                return
            
            # 从豆瓣 API 获取书籍标题
            title = await self._get_douban_book_title(douban_id)
            if not title:
                yield event.plain_result("❌ 无法获取豆瓣书籍信息")
                return
            
            logger.info(f"[Book] 从豆瓣插件接收搜索请求: douban_id={douban_id}, title={title}")
            
            # 执行书籍搜索 - 复用现有的搜索逻辑
            user_id = get_unified_user_id(event)
            capabilities = get_platform_capabilities(event, "Book") if COMMON_MODULES_AVAILABLE else {}
            is_button_mode = capabilities.get('supports_buttons', False)
            
            loading_msg_id = await LoadingIndicator.show(event, 'search') if COMMON_MODULES_AVAILABLE else None
            
            try:
                books, total = await self.book_api.search_books(title, 1, self.PAGE_SIZE, "default")
                
                # 记录搜索统计
                if self.search_stats:
                    self.search_stats.record_search(user_id, 'book', title, total, 'douban', platform='default')
                
                if is_button_mode:
                    message, _ = BookFormatter.format_search_results(books, 1, self.PAGE_SIZE, total, "default", False)
                    builder = BookResponseBuilder(capabilities)
                    keyboard = builder.build_search_keyboard(books, title, 1, self.PAGE_SIZE, total, "default")
                    yield event.chain_result([Plain(message), keyboard]) if keyboard else event.plain_result(message)
                else:
                    session_id = event.get_session_id()
                    if self.session_manager is not None:
                        self.session_manager.create_session(
                            session_id=session_id, 
                            session_type="book_search", 
                            user_id=user_id, 
                            step=0, 
                            capabilities=capabilities, 
                            data={'keyword': title, 'page': 1, 'page_size': self.PAGE_SIZE, 'total': total, 'results': books, 'api_source': 'default'}
                        )
                    message, _ = BookFormatter.format_search_results(books, 1, self.PAGE_SIZE, total, "default", True, self.SESSION_TIMEOUT_MINUTES)
                    yield event.plain_result(message)
            finally:
                if COMMON_MODULES_AVAILABLE and loading_msg_id:
                    await LoadingIndicator.hide(event, loading_msg_id)
                
        except Exception as e:
            logger.error(f"[Book] 解析豆瓣跳转参数失败: {e}")
            yield event.plain_result("❌ 搜索参数解析失败")
    
    async def _get_douban_book_title(self, douban_id: str) -> Optional[str]:
        """从豆瓣 API 获取书籍标题"""
        try:
            # 尝试从缓存获取
            from common.cache_manager import get_global_cache
            cache = get_global_cache()
            if cache is not None:
                cache_key = f"douban:book:{douban_id}"
                cached = cache.get(cache_key)
                if cached and isinstance(cached, dict):
                    return cached.get('title')
            
            # 从豆瓣 API 获取
            from astrbot_plugin_douban.handlers.douban_api import DoubanAPI
            douban_api = DoubanAPI()
            title = await douban_api.get_douban_title("book", douban_id)
            if title:
                return title
        except Exception as e:
            logger.error(f"[Book] 获取豆瓣书籍标题失败: {e}")
        return None
    
    async def _handle_exit_callback(self, event: AstrMessageEvent):
        """处理退出回调 - 使用统一退出处理器"""
        from common.exit_handler import handle_exit
        async for result in handle_exit(event, self.session_manager, plugin_name="Book"):
            yield result
    
    async def _show_book_details(self, event: AstrMessageEvent, ssid: str, capabilities: Dict):
        is_button_mode = capabilities.get('supports_buttons', False)
        platform_name = capabilities.get('platform_name', '').lower()
        
        # 获取机器人用户名
        bot_username = event.get_self_id() or "zslraibot"
        
        books, _ = await self.book_api.search_books(ssid, 1, 1, "default")
        if not books:
            yield event.plain_result("❌ 未找到该书籍信息")
            return
        
        book = books[0]
        
        # 保存书籍详情到缓存
        try:
            from .db.models import BookDetailCache
            expires_time = datetime.now() + timedelta(days=30)
            detail_cache = BookDetailCache(
                book_ssid=ssid,
                book_data=json.dumps(book, ensure_ascii=False),
                created_time=datetime.now(),
                expires_time=expires_time
            )
            self.db.save_book_detail_cache(detail_cache)
            logger.debug(f"[Book] 已缓存书籍详情: {ssid}")
        except Exception as e:
            logger.debug(f"[Book] 缓存书籍详情失败: {e}")
        
        caption = BookFormatter.format_book_detail(book, ssid)
        formats = await self.book_api.get_book_formats(ssid)
        format_buttons = BookFormatter.format_file_formats(formats, ssid, bot_username)
        
        keyboard = None
        if is_button_mode:
            builder = BookResponseBuilder(capabilities)
            keyboard = builder.build_detail_keyboard(ssid, format_buttons, bot_username)
        else:
            # 会话模式：显示文件格式信息
            format_text, format_list = BookFormatter.format_file_formats_for_session(formats)
            if format_text:
                caption += f"\n\n{format_text}"
                # 保存格式列表到会话
                session_id = event.get_session_id()
                if self.session_manager:
                    session = self.session_manager.get_session(session_id)
                    if session:
                        data = session.get('data', {})
                        data['available_formats'] = format_list
                        self.session_manager.update_session(session_id, data=data)
            separator = get_separator(platform_name)
            caption += f"\n\n{separator}\n💡 a-AI解读 | b-返回 | 0-退出"
        
        cover_url = BookFormatter.get_cover_url(ssid)
        if await is_image_url_valid(cover_url):
            img = Image(file=cover_url, caption=caption if platform_name == "telegram" else "")
            if platform_name == "telegram":
                yield event.chain_result([img, keyboard]) if keyboard else event.chain_result([img])
            elif platform_name == "lark":
                yield event.chain_result([img, Plain(caption), keyboard]) if keyboard else event.chain_result([img, Plain(caption)])
            else:
                yield event.chain_result([Plain(caption), img])
        else:
            yield event.chain_result([Plain(f"🖼️ 封面加载失败\n\n{caption}"), keyboard]) if keyboard else event.plain_result(f"🖼️ 封面加载失败\n\n{caption}")
    
    async def _handle_session_page(self, event: AstrMessageEvent, session_id: str, new_page: int):
        """处理会话模式翻页"""
        session = self.session_manager.get_session(session_id)
        if not session:
            yield event.plain_result("❌ 会话已过期，请重新搜索")
            return
        
        data = session.get('data', {})
        keyword = data.get('keyword', '')
        api_source = data.get('api_source', 'default')
        
        books, total = await self.book_api.search_books(keyword, new_page, self.PAGE_SIZE, api_source)
        
        # 更新会话数据
        data['page'] = new_page
        data['results'] = books
        data['total'] = total
        self.session_manager.update_session(session_id, data=data)
        
        # 格式化并发送结果
        message, _ = BookFormatter.format_search_results(
            books, new_page, self.PAGE_SIZE, total, api_source,
            show_hints=True, timeout_minutes=1
        )
        yield event.plain_result(message)
    
    async def _handle_session_switch(self, event: AstrMessageEvent, session_id: str, new_source: str):
        """处理会话模式换源"""
        session = self.session_manager.get_session(session_id)
        if not session:
            yield event.plain_result("❌ 会话已过期，请重新搜索")
            return
        
        data = session.get('data', {})
        keyword = data.get('keyword', '')
        user_id = get_unified_user_id(event)
        
        books, total = await self.book_api.search_books(keyword, 1, self.PAGE_SIZE, new_source)
        
        # 记录换源搜索统计
        if self.search_stats:
            self.search_stats.record_search(user_id, 'book', keyword, total, 'keyword', platform=new_source)
        
        # 更新会话数据
        data['api_source'] = new_source
        data['page'] = 1
        data['results'] = books
        data['total'] = total
        self.session_manager.update_session(session_id, data=data)
        
        # 格式化并发送结果
        message, _ = BookFormatter.format_search_results(
            books, 1, self.PAGE_SIZE, total, new_source,
            show_hints=True, timeout_minutes=1
        )
        yield event.plain_result(message)
    
    async def _handle_ai_interpret(self, event: AstrMessageEvent, ssid: str):
        """使用统一 AI 解读接口"""
        books, _ = await self.book_api.search_books(ssid, 1, 1, "default")
        if not books:
            yield event.plain_result("❌ 未找到该书籍信息")
            return
        
        book = books[0]
        title = book.get('title', '未知')
        
        # 获取配置中的 AI 提示词和字数限制
        custom_prompt = self.plugin_config.get('ai_prompt', '').strip()
        max_length = self.plugin_config.get('ai_max_length', 300)
        
        loading_msg_id = await LoadingIndicator.show(event, 'process') if COMMON_MODULES_AVAILABLE else None
        try:
            from common.ai_interpreter import get_ai_interpreter, AIInterpreter
            
            # 构建标准内容信息
            content_info = AIInterpreter.build_book_info(book)
            
            # 获取 AI 解读器
            interpreter = get_ai_interpreter(self.context)
            
            # 调用统一解读接口
            result = await interpreter.interpret(
                content_type='book',
                content_info=content_info,
                event=event,
                custom_prompt=custom_prompt if custom_prompt else None,
                max_length=max_length
            )
            
            if result:
                formatted = interpreter.format_result('book', title, result)
                yield event.plain_result(formatted)
            else:
                yield event.plain_result("❌ AI 解读失败")
        except Exception as e:
            logger.error(f"[Book] AI 解读失败: {e}")
            yield event.plain_result("❌ AI 解读出错")
        finally:
            if COMMON_MODULES_AVAILABLE and loading_msg_id:
                await LoadingIndicator.hide(event, loading_msg_id)
    
    async def _handle_book_download(self, event: AstrMessageEvent, ssid: str, file_tag: str, backend_tag: str, source_type: str):
        user_id = get_unified_user_id(event)
        quota_result = None
        if self.quota_validator:
            quota_result = await self.quota_validator.check_quota(user_id, 'book_download', 'book', use_points=True)
            if not quota_result.allowed:
                yield event.plain_result(quota_result.message)
                return
        
        cached = self.cache_mgr.get_cached_file(ssid, file_tag)
        if cached:
            try:
                # 从缓存的 book_info 中生成完整 caption
                cache_caption = f"SSID: {ssid}"
                if cached.book_info:
                    try:
                        info = json.loads(cached.book_info)
                        book_data = info.get('book_data', '')
                        if book_data:
                            book = json.loads(book_data) if isinstance(book_data, str) else book_data
                            from .handlers.book_formatter import BookFormatter
                            cache_caption = BookFormatter.format_book_detail(book, ssid)
                    except Exception:
                        pass
                # 使用统一的 event.send() 发送缓存文件
                file_comp = File(file=f"file_id:{cached.file_id}", name="", caption=cache_caption)
                await event.send(MessageChain([file_comp]))
                if self.quota_validator and quota_result:
                    await self.quota_validator.consume_quota(user_id, 'book_download', 'book', quota_result.points_cost)
                # 记录下载统计
                if self.search_stats:
                    self.search_stats.record_download(user_id, 'book', ssid, item_type='book', quality=file_tag, source='cache')
                event.stop_event()
                return
            except Exception:
                pass
        
        async with LoadingIndicator(event, "sending_file"):
            try:
                # 从 file_tag 中提取 API 返回的文件大小和格式，用于缓存匹配
                # file_tag 格式: {size}{format} 例如: "94651103pdf"
                api_size_format = ""
                match = re.match(r'(\d+)([a-z]+)', file_tag)
                if match:
                    api_size = match.group(1)
                    api_format = match.group(2)
                    api_size_format = f"SSID_SIZE_FORMAT:{api_size}:{api_format}\n"
                
                caption = f"receive:{user_id}|book_info:{api_size_format}SSID:{ssid}"
                
                if source_type == "group" and "." in backend_tag:
                    gid, mid = backend_tag.split(".", 1)
                    await self.book_api.copy_message(int(gid), f"@{event.get_self_id()}", int(mid), caption)
                else:
                    msg = await self.book_api.send_book(backend_tag, user_id, event.get_group_id() or event.get_session_id(), event.message_obj.message_id, event.get_platform_name())
                    try:
                        info = json.loads(msg)
                        if isinstance(info, dict) and info.get("status") == "发送文件" and "." in str(info.get("message_info", "")):
                            fp, mi = str(info["message_info"]).split(".", 1)
                            await self.book_api.copy_message(int(fp), f"@{event.get_self_id()}", int(mi), caption)
                    except Exception:
                        pass
                if self.quota_validator and quota_result:
                    await self.quota_validator.consume_quota(user_id, 'book_download', 'book', quota_result.points_cost)
                # 记录下载统计
                if self.search_stats:
                    self.search_stats.record_download(user_id, 'book', ssid, item_type='book', quality=file_tag, source=source_type)
            except Exception as e:
                logger.error(f"[Book] 下载失败: {e}")
                yield event.plain_result("❌ 文件发送失败")
    
    async def _handle_alt_copy(self, event: AstrMessageEvent, data: str):
        """处理备用复制回调，格式: group_id:message_id:idx"""
        parts = data.split(":")
        if len(parts) < 3:
            return
        gid, mid, idx = parts[0], parts[1], parts[2]
        user_id = get_unified_user_id(event)
        
        quota_result = None
        if self.quota_validator:
            quota_result = await self.quota_validator.check_quota(user_id, 'book_download', 'book', use_points=True)
            if not quota_result.allowed:
                yield event.plain_result(quota_result.message)
                return
        
        async with LoadingIndicator(event, "sending_file"):
            try:
                from_peer = gid if gid.startswith("@") else int(gid)
                await self.book_api.copy_message(from_peer, f"@{event.get_self_id()}", int(mid), f"receive:{user_id}|book_info:备用源文件")
                if self.quota_validator and quota_result:
                    await self.quota_validator.consume_quota(user_id, 'book_download', 'book', quota_result.points_cost)
                # 记录下载统计
                if self.search_stats:
                    self.search_stats.record_download(user_id, 'book', f"alt_{idx}", item_type='book', source='alt_copy')
            except Exception as e:
                logger.error(f"[Book] 备用复制失败: {e}")
                yield event.plain_result("❌ 文件发送失败")
    
    async def _handle_pagination(self, event: AstrMessageEvent, data: str):
        """处理翻页回调，格式: keyword:page:size:api_source"""
        parts = data.split(":")
        if len(parts) < 4:
            return
        keyword, page, size = parts[0], int(parts[1]), int(parts[2])
        api_source = parts[3] if len(parts) > 3 else "default"
        
        books, total = await self.book_api.search_books(keyword, page, size, api_source)
        
        # 记录搜索统计（翻页/换源时也记录）
        if self.search_stats and page == 1:
            # 只在第一页（换源时）记录，避免翻页重复计数
            user_id = get_unified_user_id(event)
            self.search_stats.record_search(user_id, 'book', keyword, total, 'keyword', platform=api_source)
        
        capabilities = get_platform_capabilities(event, "Book") if COMMON_MODULES_AVAILABLE else {}
        message, _ = BookFormatter.format_search_results(books, page, size, total, api_source, False)
        builder = BookResponseBuilder(capabilities)
        keyboard = builder.build_search_keyboard(books, keyword, page, size, total, api_source)
        
        try:
            if capabilities.get('platform_name', '').lower() == "telegram":
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                btns = [[InlineKeyboardButton(b['text'], url=b.get('url'), callback_data=b.get('callback_data')) for b in row] for row in (keyboard.buttons if keyboard else [])]
                await event.client.edit_message_text(chat_id=event.message_obj.group_id or event.get_sender_id(), message_id=int(event.message_obj.message_id), text=message, reply_markup=InlineKeyboardMarkup(btns) if btns else None)  # chat_id 保持原始ID
                return
        except Exception:
            pass
        yield event.chain_result([Plain(message), keyboard]) if keyboard else event.plain_result(message)
    
    async def terminate(self):
        logger.info("[Book] 插件正在卸载...")
        if self.session_manager:
            self.session_manager.cleanup_expired()
