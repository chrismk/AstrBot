"""AstrBot 豆瓣评分图片显示插件"""

import os
import re
import json
import aiohttp
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from urllib.parse import urlparse, parse_qs, quote

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter, MessageChain
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Plain, Image
from astrbot.core.utils.callback_router import CallbackRouter, callback_handler, auto_stop_event
from astrbot.core.platform.sources.telegram.tg_event import InlineKeyboard

# 导入通用模块
import sys
from pathlib import Path
plugin_root = Path(__file__).parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

from common import (
    DatabaseManager,
    QuotaValidator,
    get_platform_capabilities,
    MessageEditor,
    CacheManager,
    SessionManager,
    LarkMessageHelper,
    LoadingIndicator
)

# 导入插件特定的处理器
from .handlers import (
    DoubanResponseBuilder,
    SessionHandler,
    DoubanAPI,
    DoubanURLParser,
    DoubanFormatter
)


@register("douban-rating", "Chrismk", "豆瓣评分图片显示插件 - 自动识别豆瓣链接并生成评分图片", "1.0.0")
class DoubanPlugin(Star):
    """豆瓣评分插件主类"""
    
    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context
        
        # 初始化API调用器
        self.douban_api = DoubanAPI()
        logger.info("[Douban] API调用器初始化完成")
        
        # 初始化SessionManager
        self.session_manager = SessionManager(timeout_minutes=5)
        logger.info("[Douban] SessionManager初始化完成")
        
        # 注册回调路由
        CallbackRouter.register("douban", self.handle_callback, plugin_instance=self)
        logger.info("[Douban] 已注册回调路由: douban")
        
        # 初始化缓存管理器
        self.cache = CacheManager(default_ttl=600)  # 10分钟缓存
        logger.info("[Douban] 缓存管理器初始化完成")
        
        # 初始化配额系统
        self.quota_validator = None
        try:
            config = self.context.get_config()
            data_path = config.get("data_path", "data")
            db_path = os.path.join(data_path, "quota_system.db")
            self.db = DatabaseManager(db_path)
            self.quota_validator = QuotaValidator(self.db)
            logger.info("[Douban] 配额系统初始化完成")
            
            # 注册配额规则
            self._register_quota_rules()
        except Exception as e:
            logger.error(f"[Douban] 配额系统初始化失败: {e}")
        
        # 初始化会话处理器（传入所有依赖）
        self.session_handler = SessionHandler(
            plugin=self,
            session_manager=self.session_manager,
            douban_api=self.douban_api
        )
        logger.info("[Douban] 会话处理器初始化完成")
        
        logger.info("豆瓣评分插件初始化完成")
    
    def _register_quota_rules(self):
        """注册插件的配额规则"""
        rules = [
            {
                'action_type': 'douban_view',
                'free': {'daily_limit': 10, 'points_cost': 0},
                'premium': {'daily_limit': -1, 'points_cost': 0},
                'vip': {'daily_limit': -1, 'points_cost': 0},
                'description': '查看豆瓣评分'
            },
            {
                'action_type': 'douban_search',
                'free': {'daily_limit': 5, 'points_cost': 0},
                'premium': {'daily_limit': -1, 'points_cost': 0},
                'vip': {'daily_limit': -1, 'points_cost': 0},
                'description': '搜索豆瓣'
            }
        ]
        
        success = self.quota_validator.register_quota_rules(
            plugin_name='douban',
            rules=rules,
            override=False  # 不覆盖已存在的规则
        )
        
        if success:
            logger.info("[Douban] 配额规则注册成功")
        else:
            logger.warning("[Douban] 配额规则注册失败")
    
    def _extract_douban_info(self, url: str) -> Optional[Tuple[str, str]]:
        """
        从豆瓣链接中提取类型和ID
        
        支持的链接格式：
        - https://movie.douban.com/subject/36208369/
        - https://movie.douban.com/subject/36208369/?icn=index-latestbook-subject
        - https://book.douban.com/subject/37375410/
        - https://book.douban.com/subject/37375410/?icn=index-latestbook-subject
        - https://m.douban.com/book/subject/37353424/?source=collection
        - https://m.douban.com/movie/subject/36455616/
        - https://www.douban.com/doubanapp/dispatch/movie/36402017
        - https://www.douban.com/doubanapp/dispatch/book/37353424
        
        返回: (type, id) 或 None
        """
        try:
            # 豆瓣链接匹配模式
            patterns = [
                # 桌面版电影链接
                (r'https?://movie\.douban\.com/subject/(\d+)', 'movie'),
                # 桌面版图书链接  
                (r'https?://book\.douban\.com/subject/(\d+)', 'book'),
                # 移动版电影链接
                (r'https?://m\.douban\.com/movie/subject/(\d+)', 'movie'),
                # 移动版图书链接
                (r'https?://m\.douban\.com/book/subject/(\d+)', 'book'),
                # App调度链接 - 电影
                (r'https?://www\.douban\.com/doubanapp/dispatch/movie/(\d+)', 'movie'),
                # App调度链接 - 图书
                (r'https?://www\.douban\.com/doubanapp/dispatch/book/(\d+)', 'book'),
                # 电视剧链接（也归类为movie）
                (r'https?://movie\.douban\.com/subject/(\d+)', 'movie'),
                (r'https?://m\.douban\.com/tv/subject/(\d+)', 'movie'),
            ]
            
            # 遍历所有模式进行匹配
            for pattern, douban_type in patterns:
                match = re.search(pattern, url)
                if match:
                    subject_id = match.group(1)
                    logger.info(f"匹配到豆瓣链接: type={douban_type}, id={subject_id}, pattern={pattern}")
                    return (douban_type, subject_id)
            
            logger.warning(f"未能匹配豆瓣链接格式: {url}")
            return None
                
        except Exception as e:
            logger.error(f"解析豆瓣链接失败: {e}")
            return None
    
    async def _search_douban(self, keyword: str, search_type: str = "book", page: int = 1) -> Tuple[List[Dict], int]:
        """
        搜索豆瓣信息
        
        Args:
            keyword: 搜索关键词
            search_type: 搜索类型 ("book" 或 "movie")
            page: 页码
            
        Returns:
            (搜索结果列表, 总条数)
        """
        try:
            # 构建搜索URL
            if search_type == "book":
                # 书籍搜索端点
                url = f"https://search.douban.com/book/subject_search?search_text={quote(keyword)}&cat=1001&start={(page-1)*15}"
                headers = {
                    "Host": "search.douban.com",
                    "Referer": "https://book.douban.com/",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
                }
            elif search_type == "movie":
                # 电影搜索端点
                url = f"https://search.douban.com/movie/subject_search?search_text={quote(keyword)}&cat=1002&start={(page-1)*15}"
                headers = {
                    "Host": "search.douban.com", 
                    "Referer": "https://movie.douban.com/",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
                }
            else:
                logger.error(f"不支持的搜索类型: {search_type}")
                return []
            
            logger.info(f"搜索豆瓣{search_type}: {url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=15) as response:
                    if response.status == 200:
                        html_content = await response.text()
                        
                        # 使用正则表达式提取 window.__DATA__ 中的JSON数据
                        import re
                        matches = re.findall(r'window\.__DATA__\s*=\s*({.*?});', html_content, re.DOTALL)
                        if not matches:
                            logger.warning("未找到 window.__DATA__ 数据")
                            return []
                        
                        # 解码JSON字符串
                        import json
                        try:
                            # 直接解析JSON对象
                            data = json.loads(matches[0])
                            
                            # 获取总条数信息
                            total_count = data.get("total", 0)
                            logger.info(f"豆瓣搜索返回总条数: {total_count}")
                            
                            items = data.get("items", [])
                            if items:
                                # 转换为统一格式
                                results = []
                                for item in items:
                                    # 过滤掉非搜索结果项目（如search_more）
                                    if item.get("tpl_name") != "search_subject":
                                        continue
                                    
                                    # 提取基本信息
                                    result_item = {
                                        "id": str(item.get("id", "")),
                                        "title": item.get("title", ""),
                                        "url": item.get("url", ""),
                                        "pic": item.get("cover_url", ""),
                                        "type": "b" if search_type == "book" else "movie",
                                        "rating": item.get("rating", {})  # 保存评分信息
                                    }
                                    
                                    # 从abstract中提取作者/导演和年份信息
                                    abstract = item.get("abstract", "")
                                    abstract_2 = item.get("abstract_2", "")
                                    
                                    if search_type == "book":
                                        if abstract:
                                            # 书籍格式: "吴承恩 / 黄肃秋 注释 / 人民文学出版社 / 2004-8 / 47.20元"
                                            parts = abstract.split(" / ")
                                            if len(parts) >= 1:
                                                result_item["author_name"] = parts[0]
                                                
                                                # 提取出版社信息
                                                if len(parts) >= 3:
                                                    result_item["publisher"] = parts[2]
                                                
                                                # 尝试提取年份和价格
                                                if len(parts) >= 4:
                                                    year_part = parts[3]
                                                    year_match = re.search(r'(\d{4})', year_part)
                                                    if year_match:
                                                        result_item["year"] = year_match.group(1)
                                                
                                                # 提取价格信息
                                                if len(parts) >= 5:
                                                    price_part = parts[4]
                                                    price_match = re.search(r'([\d.]+元)', price_part)
                                                    if price_match:
                                                        result_item["price"] = price_match.group(1)
                                    else:  # movie
                                        if abstract:
                                            # 电影格式: "中国大陆 / 剧情 / Mr. Tree / 88分钟"
                                            parts = abstract.split(" / ")
                                            if len(parts) >= 2:
                                                # 第一个通常是国家/地区，第二个是类型
                                                result_item["country"] = parts[0]
                                                result_item["genre"] = parts[1]
                                                
                                                # 从title中提取年份 (格式如: "Hello！树先生‎ (2011)")
                                                title = result_item.get("title", "")
                                                year_match = re.search(r'\((\d{4})\)', title)
                                                if year_match:
                                                    result_item["year"] = year_match.group(1)
                                        
                                        # 从abstract_2中提取导演和演员信息
                                        if abstract_2:
                                            # abstract_2格式: "韩杰 / 王宝强 / 谭卓 / 何洁 / 白培将 / 王大治 / 王亚彬 / 李京忆 / 邱士鉴"
                                            actors_parts = abstract_2.split(" / ")
                                            if len(actors_parts) >= 1:
                                                result_item["director"] = actors_parts[0]  # 第一个通常是导演
                                                if len(actors_parts) > 1:
                                                    # 其余的是演员，取前几个主要演员
                                                    main_actors = actors_parts[1:4]  # 取前3个演员
                                                    result_item["actors"] = " / ".join(main_actors)
                                    
                                    results.append(result_item)
                                
                                logger.info(f"成功获取豆瓣搜索结果，共{len(results)}条")
                                return results, total_count
                            else:
                                logger.info("搜索结果为空")
                                return [], total_count
                                
                        except json.JSONDecodeError as e:
                            logger.error(f"解析JSON数据失败: {e}")
                            return [], 0
                        except Exception as e:
                            logger.error(f"处理搜索数据失败: {e}")
                            return [], 0
                    else:
                        logger.warning(f"豆瓣搜索失败，状态码: {response.status}")
                        return [], 0
                        
        except Exception as e:
            logger.error(f"搜索豆瓣异常: {e}")
            return [], 0
    
    def _format_search_results(self, results: List[Dict], search_type: str, page: int = 1, page_size: int = 15, total_count: int = 0) -> Tuple[str, List[Dict]]:
        """
        格式化搜索结果
        
        Args:
            results: 搜索结果列表
            search_type: 搜索类型 ("book" 或 "movie")
            page: 当前页码
            page_size: 每页显示数量
            total_count: 总条数
            
        Returns:
            (格式化消息, 当前页结果列表)
        """
        if not results:
            return "❌ 未找到相关内容", []
        
        # 新端点每页返回固定数量的结果，不需要客户端分页
        lines = []
        
        for idx, item in enumerate(results, 1):
            # 获取基本信息
            title = item.get("title", "未知标题")
            
            # 获取评分信息
            rating = item.get("rating", {})
            rating_value = rating.get("value", 0)
            star_count = rating.get("star_count", 0)
            
            # 生成星级显示
            stars = ""
            if star_count > 0:
                full_stars = int(star_count)
                half_star = star_count - full_stars >= 0.5
                stars = "⭐" * full_stars
                if half_star:
                    stars += "☆"  # 半星使用空心星表示
            
            if search_type == "book":
                author = item.get("author_name", "未知作者")
                year = item.get("year", "")
                publisher = item.get("publisher", "")
                price = item.get("price", "")
                rating_count = rating.get("count", 0)
                
                # 构建基本信息行
                info_parts = [f"{idx}.{title}", f"{author}"]
                #if year:
                    #info_parts.append(f"({year})")
                if publisher:
                    info_parts.append(f"{publisher}")
                if price:
                    info_parts.append(f"{price}")
                
                line = " - ".join(info_parts)
                lines.append(line)
                
                # 评分单独一行，使用特殊字符代替缩进
                if rating_value > 0:
                    rating_line = f"└ {rating_value}分{stars}"
                    if rating_count > 0:
                        rating_line += f" ({rating_count}人评价)\n"
                    lines.append(rating_line)
            else:  # movie
                director = item.get("director", "")
                actors = item.get("actors", "")
                year = item.get("year", "")
                rating_count = rating.get("count", 0)
                
                # 构建基本信息行
                movie_parts = [f"{idx}.{title}"]
                #if year:
                    #movie_parts.append(f"({year})")
                if director:
                    movie_parts.append(f"/{director}")
                if actors:
                    movie_parts.append(f"/{actors}")
                
                movie_info = " ".join(movie_parts)
                lines.append(movie_info)
                
                # 评分单独一行，使用特殊字符代替缩进
                if rating_value > 0:
                    rating_line = f"└ {rating_value}分{stars}"
                    if rating_count > 0:
                        rating_line += f" ({rating_count}人评价)\n"
                    lines.append(rating_line)
        
        # 底部提示信息
        type_name = "书籍" if search_type == "book" else "电影"
        if total_count > 0:
            lines.append(f"💡 点击数字查看详情 | 第 {page} 页 | 共 {total_count} 条 | {type_name}")
        else:
            lines.append(f"💡 点击数字查看详情 | 第 {page} 页 | 共 {len(results)} 条 | {type_name}")
        
        return "\n".join(lines), results
    
    async def _update_lark_card(self, event, text: str, keyboard: InlineKeyboard) -> bool:
        """更新飞书卡片内容"""
        try:
            from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent
            from astrbot.core.platform.sources.lark.card_service import get_card_service
            
            if not isinstance(event, LarkMessageEvent):
                logger.warning("[douban] 事件不是飞书消息事件")
                return False
            
            # 获取卡片更新token
            card_token = getattr(event.message_obj, 'lark_card_token', None)
            if not card_token:
                logger.warning("[douban] 缺少飞书卡片更新token")
                return False
            
            # 获取飞书应用配置 - 从事件的bot对象获取
            if not hasattr(event, 'bot') or not event.bot:
                logger.warning("[douban] 无法获取飞书bot对象")
                return False
            
            # 从bot的配置中获取app_id和app_secret
            bot_config = getattr(event.bot, '_config', None) or getattr(event.bot, 'config', None)
            if not bot_config:
                logger.warning("[douban] 无法获取飞书bot配置")
                return False
            
            app_id = getattr(bot_config, 'app_id', None)
            app_secret = getattr(bot_config, 'app_secret', None)
            
            if not app_id or not app_secret:
                logger.warning(f"[douban] 飞书配置不完整: app_id={bool(app_id)}, app_secret={bool(app_secret)}")
                return False
            
            # 获取卡片服务并更新
            card_service = get_card_service(app_id, app_secret)
            success = await card_service.update_card(card_token, text, keyboard)
            
            if success:
                logger.debug("[douban] 飞书卡片更新成功")
            else:
                logger.warning("[douban] 飞书卡片更新失败")
            
            return success
            
        except Exception as e:
            logger.error(f"[douban] 更新飞书卡片异常: {e}")
            return False
    
    async def _handle_douban_search(
        self, 
        keyword: str, 
        search_type: str = "book", 
        page: int = 1, 
        capabilities: dict = None,
        session_id: str = None,
        user_id: str = None
    ) -> Tuple[str, InlineKeyboard]:
        """
        处理豆瓣搜索
        
        Args:
            keyword: 搜索关键词
            search_type: 搜索类型
            page: 页码
            capabilities: 平台能力字典
            session_id: 会话ID（会话模式需要）
            user_id: 用户ID（会话模式需要）
            
        Returns:
            (消息文本, 键盘)
        """
        # 搜索豆瓣
        results, total_count = await self._search_douban(keyword, search_type, page)
        
        # 使用响应构建器
        builder = DoubanResponseBuilder(capabilities or {})
        
        if not results:
            empty_keyboard = builder.build_empty_search_keyboard(search_type, keyword)
            return f"❌ 未找到关于「{keyword}」的{('书籍' if search_type == 'book' else '电影')}信息", empty_keyboard
        
        # 缓存搜索结果（用于详情显示）
        cache_key = f"search:{search_type}:{keyword}:{page}"
        self.cache.set(cache_key, results, ttl=600)  # 10分钟缓存
        
        # 会话模式：启动会话
        if session_id and user_id and not builder.is_button_mode():
            logger.info(f"[Douban] 启动搜索会话: session_id={session_id}, type={search_type}")
            return await self.session_handler.start_search_menu(
                user_id=user_id,
                session_id=session_id,
                search_type=search_type,
                keyword=keyword,
                results=results,
                total=total_count,
                page=page,
                capabilities=capabilities or {}
            )
        
        # 按钮模式：直接返回键盘
        # 格式化结果（新端点每页固定15条）
        message, page_results = self._format_search_results(results, search_type, page, 15, total_count)
        
        # 创建键盘（新端点每页固定15条）
        keyboard = builder.build_search_result_keyboard(results, search_type, keyword, page, 15, total_count)
        
        return message, keyboard
    
    def _is_douban_url(self, text: str) -> bool:
        """检查文本是否包含豆瓣链接"""
        douban_indicators = [
            # 桌面版
            'movie.douban.com/subject/',
            'book.douban.com/subject/',
            # 移动版
            'm.douban.com/movie/subject/',
            'm.douban.com/book/subject/',
            'm.douban.com/tv/subject/',
            # App调度链接
            'www.douban.com/doubanapp/dispatch/movie/',
            'www.douban.com/doubanapp/dispatch/book/',
        ]
        
        return any(indicator in text for indicator in douban_indicators)
    
    async def _get_douban_image(self, douban_type: str, douban_id: str) -> Optional[bytes]:
        """
        获取豆瓣评分图片
        
        Args:
            douban_type: 类型 (movie/book)
            douban_id: 豆瓣ID
            
        Returns:
            图片 bytes 或 None
        """
        # 优先尝试直接获取图片
        try:
            direct_image_url = f"http://api.wowoziyuan.com/douban/image_api.php?type={douban_type}&id={douban_id}"
            logger.info(f"尝试直接获取豆瓣图片: {direct_image_url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(direct_image_url, timeout=15) as response:
                    if response.status == 200:
                        content_type = response.headers.get('Content-Type', '')
                        if 'image' in content_type:
                            image_bytes = await response.read()
                            # 简单的验证，判断是否是有效的图片（比如，不是一个极小的错误提示图片）
                            if len(image_bytes) > 2048: # 大于2KB通常认为是有效图片
                                logger.info(f"成功通过直接API获取豆瓣图片: {direct_image_url}")
                                return image_bytes
                            else:
                                logger.info("直接API获取的图片过小，可能无效，尝试备用方案。")
                        else:
                            logger.info(f"直接API返回非图片内容: {content_type}，尝试备用方案。")
                    else:
                        logger.info(f"直接API获取图片失败，状态码: {response.status}，尝试备用方案。")

        except Exception as e:
            logger.warning(f"直接获取豆瓣图片异常: {e}，尝试备用方案。")

        # 如果直接获取失败，使用备用的截图服务
        try:
            # 构建API请求URL
            douban_page_url = f"{self.douban_image_api}?type={douban_type}&id={douban_id}&download=0"
            
            payload = {
                "url": douban_page_url,
                "selector": "img",
                "waitFor": 2000
            }

            logger.info(f"请求截图服务: {self.screenshot_api} for url: {douban_page_url}")

            async with aiohttp.ClientSession() as session:
                async with session.post(self.screenshot_api, json=payload, timeout=30) as response:
                    if response.status == 200:
                        # 检查响应类型是否为图片
                        content_type = response.headers.get('Content-Type', '')
                        if 'image' in content_type:
                            logger.info(f"成功获取豆瓣图片: {douban_page_url}")
                            return await response.read()
                        else:
                            logger.warning(f"API返回非图片内容: {content_type}")
                            return None
                    else:
                        logger.warning(f"获取豆瓣图片失败，状态码: {response.status}, response: {await response.text()}")
                        return None
                        
        except Exception as e:
            logger.error(f"获取豆瓣图片异常: {e}")
            return None
    
    async def _get_douban_title(self, douban_type: str, douban_id: str) -> Optional[str]:
        """
        获取豆瓣标题
        
        Args:
            douban_type: 类型 (movie/book)
            douban_id: 豆瓣ID
            
        Returns:
            标题或None
        """
        try:
            # 构建标题API请求URL
            title_api_url = f"https://api.wowoziyuan.com/douban/api.php?type={douban_type}&id={douban_id}"
            
            logger.info(f"请求豆瓣标题API: {title_api_url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(title_api_url, headers=self.headers, timeout=10) as response:
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

    async def _get_douban_comments(self, douban_type: str, douban_id: str) -> str:
        """
        获取豆瓣评论
        
        Args:
            douban_type: 类型 (movie/book)
            douban_id: 豆瓣ID
            
        Returns:
            格式化的评论文本
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
            
            request_headers = self.headers.copy()
            request_headers['Referer'] = f'https://m.douban.com/{douban_type}/{douban_id}/'

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    comment_url, 
                    params=params, 
                    headers=request_headers, 
                    timeout=10
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"成功获取评论数据，评论数量: {len(data.get('interests', []))}")
                        return self._format_comments(data)
                    else:
                        logger.warning(f"获取豆瓣评论失败，状态码: {response.status}")
                        return "暂无评论数据"
                        
        except Exception as e:
            logger.error(f"获取豆瓣评论异常: {e}", exc_info=True)
            return "获取评论失败"
    
    def _format_comments(self, comment_data: dict) -> str:
        """
        格式化评论数据
        
        Args:
            comment_data: 评论API返回的JSON数据
            
        Returns:
            格式化的评论文本
        """
        try:
            interests = comment_data.get('interests', [])
            if not interests:
                return "暂无评论"
            
            comments = []
            total_chars = 0
            max_chars = 1200  # 限制总字符数，避免caption过长
            
            for interest in interests:
                comment = interest.get('comment', '').strip()
                if not comment:
                    continue
                
                # 获取评分信息
                rating = interest.get('rating')
                rating_text = ""
                if rating and rating.get('value'):
                    stars = "⭐" * rating.get('star_count', 0)
                    rating_text = f" {stars}"
                
                vote_count = interest.get('vote_count', 0)
                if vote_count > 0:
                    rating_text += f" 👍 {vote_count}"

                # 获取用户信息
                user = interest.get('user', {})
                username = user.get('name', '匿名用户')
                location = interest.get('ip_location', '')
                
                # 格式化单条评论
                formatted_comment = f"👤 {username}"
                if location:
                    formatted_comment += f"({location})"
                if rating_text:
                    formatted_comment += rating_text
                formatted_comment += f"\n{comment}\n"
                
                # 检查是否超过字符限制
                if total_chars + len(formatted_comment) > max_chars:
                    if comments:  # 如果已经有评论了，就停止添加
                        break
                    else:  # 如果是第一条评论但太长，截断它
                        remaining_chars = max_chars - total_chars - 50  # 留一些空间给省略号
                        if remaining_chars > 100:  # 至少保留100个字符
                            comment = comment[:remaining_chars] + "..."
                            formatted_comment = f"👤 {username}"
                            if location:
                                formatted_comment += f"({location})"
                            if rating_text:
                                formatted_comment += rating_text
                            formatted_comment += f":\n{comment}\n"
                
                comments.append(formatted_comment)
                total_chars += len(formatted_comment)
            
            if not comments:
                return "暂无有效评论"
            
            result = "\n".join(comments).strip()
            logger.info(f"格式化评论完成，总字符数: {len(result)}")
            return result
            
        except Exception as e:
            logger.error(f"格式化评论失败: {e}")
            return "评论格式化失败"
    
    @filter.command("豆")
    async def handle_search_command(self, event: AstrMessageEvent, keyword: str = ""):
        """处理豆瓣搜索命令 - 搜索豆瓣信息"""
        if not keyword:
            yield event.plain_result("💡 使用方法: /豆 关键词\n示例: /豆 中国的妇女与财产")
            return
        
        # 配额检查
        if self.quota_validator:
            user_id = event.get_sender_id()
            result = await self.quota_validator.check_quota(
                user_id=user_id,
                action_type="douban_search",
                plugin_name="douban",
                use_points=True
            )
            
            if not result.allowed:
                yield event.plain_result(result.message)
                return
        
        progress_msg_id = None
        try:
            # 1. 发送进度提示消息
            platform_name = (event.get_platform_name() or "").lower()
            if platform_name == "telegram":
                from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                if isinstance(event, TelegramPlatformEvent):
                    chat_id = event.message_obj.group_id or event.get_sender_id()
                    msg = await event.client.send_message(chat_id=chat_id, text="🔍 正在搜索豆瓣信息，请稍候...")
                    progress_msg_id = getattr(msg, "message_id", None)
            elif platform_name == "lark":
                from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent
                if isinstance(event, LarkMessageEvent):
                    from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody
                    req = (
                        ReplyMessageRequest.builder()
                        .message_id(event.message_obj.message_id)
                        .request_body(
                            ReplyMessageRequestBody.builder()
                            .content(json.dumps({"zh_cn": {"title": "", "content": [[{"tag": "md", "text": "🔍 正在搜索豆瓣信息，请稍候..."}]]}}))
                            .msg_type("post")
                            .build()
                        )
                        .build()
                    )
                    resp = await event.bot.im.v1.message.areply(req)
                    if resp and resp.success():
                        progress_msg_id = getattr(resp.data, "message_id", None)

            # 2. 执行搜索
            user_id = event.get_sender_id()
            session_id = event.get_session_id()
            try:
                # 获取平台能力
                capabilities = get_platform_capabilities(event, "Douban")
                
                result = await self._handle_douban_search(
                    keyword=keyword,
                    search_type="book",  # 默认搜索书籍
                    page=1,
                    capabilities=capabilities,
                    session_id=session_id,
                    user_id=user_id
                )
                
                if isinstance(result, tuple) and len(result) == 2:
                    message, keyboard = result
                    if isinstance(message, str):
                        # 搜索成功，消费配额
                        if self.quota_validator:
                            await self.quota_validator.consume_quota(
                                user_id=user_id,
                                action_type="douban_search",
                                plugin_name="douban",
                                points_cost=result.points_cost if hasattr(result, 'points_cost') else 0
                            )
                        
                        # 构建消息链（只在 keyboard 不为 None 时添加）
                        chain = [Plain(message)]
                        if keyboard is not None:
                            chain.append(keyboard)
                        yield event.chain_result(chain)
                    else:
                        logger.error(f"消息不是字符串类型: {type(message)} - {message}")
                        yield event.plain_result("❌ 搜索结果格式错误")
                else:
                    logger.error(f"搜索返回值格式错误: {type(result)} - {result}")
                    yield event.plain_result("❌ 搜索返回值格式错误")
                
            except Exception as e:
                logger.error(f"搜索处理异常: {e}", exc_info=True)
                yield event.plain_result(f"❌ 搜索失败: {e}")

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
                    elif platform_name == "lark":
                        # 飞书平台支持删除消息
                        if hasattr(event, 'delete_message'):
                            try:
                                await event.delete_message(progress_msg_id)
                                logger.debug(f"[douban] 成功删除飞书搜索进度消息: {progress_msg_id}")
                            except Exception as e:
                                logger.warning(f"[douban] 删除飞书搜索进度消息失败: {e}")
                except Exception as e:
                    logger.warning(f"删除搜索提示消息失败: {e}")

    @filter.command("start")
    async def handle_start_command(self, event: AstrMessageEvent):
        """处理 /start 命令，支持AI解读回调"""
        text = event.message_str or ""
        
        parts = text.split(maxsplit=1)
        
        if len(parts) < 2:
            # 普通的 /start 命令，不做处理
            return
        
        param = parts[1].strip()
        
        # 处理豆瓣AI解读请求
        if param.startswith("dbai_"):
            try:
                import base64
                import json
                
                encoded_payload = param[5:] # remove "dbai_"
                decoded_bytes = base64.urlsafe_b64decode(encoded_payload)
                payload = json.loads(decoded_bytes.decode('utf-8'))
                
                douban_type = payload.get("type")
                douban_id = payload.get("id")

                if douban_type and douban_id:
                    async for result in self._handle_douban_ai_interpret(event, douban_type, douban_id):
                        yield result
            except Exception as e:
                logger.error(f"解析豆瓣AI解读回调参数失败: {e}")
            return
    
    async def _get_douban_detail_info(self, douban_type: str, douban_id: str) -> dict:
        """
        获取豆瓣详细信息用于AI解读
        
        Args:
            douban_type: 类型 (movie/book)
            douban_id: 豆瓣ID
            
        Returns:
            包含详细信息的字典
        """
        try:
            # 构建详细信息API请求URL
            detail_api_url = f"https://api.wowoziyuan.com/douban/api.php?type={douban_type}&id={douban_id}"
            
            logger.info(f"请求豆瓣详细信息API: {detail_api_url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(detail_api_url, headers=self.headers, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"成功获取豆瓣详细信息: {data.get('title', 'Unknown')}")
                        return data
                    else:
                        logger.warning(f"获取豆瓣详细信息失败，状态码: {response.status}")
                        return {}
                        
        except Exception as e:
            logger.error(f"获取豆瓣详细信息异常: {e}")
            return {}
    
    def _format_douban_info_for_ai(self, douban_info: dict, douban_type: str, douban_id: str) -> str:
        """格式化豆瓣信息用于AI解读"""
        info_lines = []
        
        # 安全地获取并转换字段
        title = str(douban_info.get("title", "")).strip()
        rating = str(douban_info.get("rating", "")).strip()
        genres = douban_info.get("genres", [])
        directors = douban_info.get("directors", [])
        actors = douban_info.get("actors", [])
        authors = douban_info.get("authors", [])
        publisher = str(douban_info.get("publisher", "")).strip()
        year = str(douban_info.get("year", "")).strip()
        summary = str(douban_info.get("summary", "")).strip()
        
        if title and title != "":
            if douban_type == "movie":
                info_lines.append(f"🎬 影片名称：{title}")
            else:
                info_lines.append(f"📚 书籍名称：{title}")
        
        if rating and rating != "" and rating != "0":
            info_lines.append(f"⭐ 豆瓣评分：{rating}")
        
        if year and year != "":
            if douban_type == "movie":
                info_lines.append(f"📅 上映年份：{year}")
            else:
                info_lines.append(f"📅 出版年份：{year}")
        
        if genres and len(genres) > 0:
            genres_str = " / ".join([str(g).strip() for g in genres if str(g).strip()])
            if genres_str:
                info_lines.append(f"🏷️ 类型：{genres_str}")
        
        if douban_type == "movie":
            if directors and len(directors) > 0:
                directors_str = " / ".join([str(d).strip() for d in directors if str(d).strip()])
                if directors_str:
                    info_lines.append(f"🎬 导演：{directors_str}")
            
            if actors and len(actors) > 0:
                # 限制演员数量避免信息过长
                actors_list = [str(a).strip() for a in actors[:5] if str(a).strip()]
                if actors_list:
                    actors_str = " / ".join(actors_list)
                    if len(actors) > 5:
                        actors_str += " 等"
                    info_lines.append(f"👥 主演：{actors_str}")
        
        elif douban_type == "book":
            if authors and len(authors) > 0:
                authors_str = " / ".join([str(a).strip() for a in authors if str(a).strip()])
                if authors_str:
                    info_lines.append(f"✍️ 作者：{authors_str}")
            
            if publisher and publisher != "":
                info_lines.append(f"🏢 出版社：{publisher}")
        
        if summary and summary != "":
            # 限制简介长度
            if len(summary) > 200:
                summary = summary[:200] + "..."
            info_lines.append(f"📖 简介：{summary}")
        
        if douban_id:
            info_lines.append(f"🆔 豆瓣ID：{douban_id}")
        
        return "\n".join(info_lines) if info_lines else "信息不完整"
    
    async def _handle_douban_ai_interpret(self, event: AstrMessageEvent, douban_type: str, douban_id: str):
        """处理豆瓣AI解读请求"""
        try:
            # 获取豆瓣详细信息
            douban_info = await self._get_douban_detail_info(douban_type, douban_id)
            
            if not douban_info:
                yield event.plain_result("❌ 未找到该作品的详细信息，无法进行AI解读")
                return
            
            # 构造作品信息
            work_info = self._format_douban_info_for_ai(douban_info, douban_type, douban_id)
            
            # 构造AI解读提示词
            if douban_type == "movie":
                ai_prompt = f"""请对以下影视作品进行专业解读和分析：

{work_info}

请从以下几个方面进行分析：
1. 🎬 **作品概述**：简要介绍这部影视作品的主要内容和核心主题
2. 🎯 **适合观众**：分析这部作品适合哪些观众群体
3. ⭐ **推荐理由**：说明为什么值得观看，有什么独特价值
4. 💡 **观影收获**：观众可以从中获得什么启发或感悟
5. 📽️ **观看建议**：给出观看方法或注意事项

请用简洁明了的语言，提供有价值的见解。"""
            else:
                ai_prompt = f"""请对以下书籍进行专业解读和分析：

{work_info}

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
                            msg = await event.client.send_message(chat_id=chat_id, text="🤖 AI正在解读这部作品，请稍等...")
                            progress_msg_id = getattr(msg, "message_id", None)
                    elif platform_name == "lark":
                        from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent
                        if isinstance(event, LarkMessageEvent):
                            from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody
                            req = (
                                ReplyMessageRequest.builder()
                                .message_id(event.message_obj.message_id)
                                .request_body(
                                    ReplyMessageRequestBody.builder()
                                    .content(json.dumps({"zh_cn": {"title": "", "content": [[{"tag": "md", "text": "🤖 AI正在解读这部作品，请稍等..."}]]}}))
                                    .msg_type("post")
                                    .build()
                                )
                                .build()
                            )
                            resp = await event.bot.im.v1.message.areply(req)
                            if resp and resp.success():
                                progress_msg_id = getattr(resp.data, "message_id", None)
                                logger.debug(f"[douban-ai] 飞书进度消息发送成功，消息ID: {progress_msg_id}")
                            else:
                                logger.warning("[douban-ai] 飞书进度消息发送失败")
                except Exception as e:
                    logger.warning(f"[douban-ai] 发送进度消息异常: {e}")
                    # 如果发送进度消息失败，仍然继续AI解读
                    yield event.plain_result("🤖 AI正在解读这部作品，请稍等...")
                
                # 直接调用text_chat方法（非流式）
                response = await provider.text_chat(
                    prompt=ai_prompt,
                    session_id=f"douban_ai_interpret_{douban_type}_{douban_id}_{event.get_sender_id()}",
                    system_prompt="你是一个专业的影视和图书评论专家，能够对各类作品进行深入分析和客观评价。"
                )
                
                if response and hasattr(response, 'result_chain') and response.result_chain:
                    # 提取文本内容
                    response_text = ""
                    for component in response.result_chain.chain:
                        if hasattr(component, 'text'):
                            response_text += component.text
                    
                    if response_text.strip():
                        # 格式化回复
                        work_type_name = "影视作品" if douban_type == "movie" else "书籍"
                        formatted_response = f"🤖 **AI{work_type_name}解读**\n\n{response_text.strip()}"
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
                            # 飞书平台支持删除消息
                            if hasattr(event, 'delete_message'):
                                try:
                                    await event.delete_message(progress_msg_id)
                                    logger.debug(f"[douban] 成功删除飞书AI解读进度消息: {progress_msg_id}")
                                except Exception as e:
                                    logger.warning(f"[douban] 删除飞书AI解读进度消息失败: {e}")
                    except Exception as e:
                        logger.warning(f"删除豆瓣AI解读进度消息失败: {e}")
                    
            except Exception as e:
                logger.error(f"豆瓣AI解读失败: {e}")
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
            logger.error(f"处理豆瓣AI解读请求失败: {e}")
            yield event.plain_result("❌ 处理AI解读请求失败，请稍后重试")
    
    async def _handle_douban_link(self, event: AstrMessageEvent, message_text: str):
        """处理豆瓣链接的内部方法"""
        logger.info(f"检测到豆瓣链接: {message_text}")
        
        # 配额检查
        if self.quota_validator:
            user_id = event.get_sender_id()
            result = await self.quota_validator.check_quota(
                user_id=user_id,
                action_type="douban_view",
                plugin_name="douban",
                use_points=True
            )
            
            if not result.allowed:
                yield event.plain_result(result.message)
                return
        
        try:
            # 1. 提取豆瓣信息
            douban_info = self._extract_douban_info(message_text)
            if not douban_info:
                yield event.plain_result("❌ 无法从链接中提取豆瓣信息")
                return
            
            douban_type, douban_id = douban_info
            logger.info(f"提取到豆瓣信息: type={douban_type}, id={douban_id}")
            
            # 2. 发送处理中提示
            loading_msg = None
            try:
                platform_name = (event.get_platform_name() or "").lower()
                if platform_name == "telegram":
                    from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                    if isinstance(event, TelegramPlatformEvent):
                        chat_id = event.message_obj.group_id or event.get_sender_id()
                        loading_msg = await event.client.send_message(chat_id=chat_id, text="🔍 正在获取豆瓣评分信息...")
                elif platform_name == "lark":
                    from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent
                    if isinstance(event, LarkMessageEvent):
                        from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody
                        req = (
                            ReplyMessageRequest.builder()
                            .message_id(event.message_obj.message_id)
                            .request_body(
                                ReplyMessageRequestBody.builder()
                                .content(json.dumps({"zh_cn": {"title": "", "content": [[{"tag": "md", "text": "🔍 正在获取豆瓣评分信息..."}]]}}))
                                .msg_type("post")
                                .build()
                            )
                            .build()
                        )
                        resp = await event.bot.im.v1.message.areply(req)
                        if resp and resp.success():
                            loading_msg = resp.data
                else:
                    # 对于其他平台，暂时无法获取消息ID来删除，直接发送
                    yield event.plain_result("🔍 正在获取豆瓣评分信息...")
            except Exception as e:
                logger.debug(f"发送加载消息失败: {e}")


            try:
                # 3. 先获取图片和评论，然后获取标题
                import asyncio
                image_task = self._get_douban_image(douban_type, douban_id)
                comments_task = self._get_douban_comments(douban_type, douban_id)
                
                # 并行获取图片和评论
                image_bytes, comments = await asyncio.gather(image_task, comments_task)
                
                # 在图片生成后获取标题（因为标题API依赖于图片生成过程）
                title = await self._get_douban_title(douban_type, douban_id)
                
                # 如果评论获取失败，提供一个默认消息
                if comments in ["获取评论失败", "暂无评论数据"]:
                    if douban_type == "book":
                        comments = f"📚 《{title or '未知书籍'}》\n\n点击下方按钮搜索资源或查看详情"
                    else:
                        comments = f"🎬 《{title or '未知影片'}》\n\n点击下方按钮搜索资源或查看详情"
                
                # 4. 创建操作键盘
                capabilities = get_platform_capabilities(event, "Douban")
                builder = DoubanResponseBuilder(capabilities)
                keyboard = builder.build_action_keyboard(douban_type, douban_id, title)
                
                # 5. 发送结果
                if image_bytes:
                    # 发送图片 + 评论作为caption + 操作按钮
                    logger.info(f"发送图片消息，图片大小: {len(image_bytes)} bytes")
                    image_component = Image.fromBytes(image_bytes)
                    image_component.caption = comments
                    
                    # 根据平台采用不同的发送策略
                    if platform_name == "telegram":
                        try:
                            if keyboard.buttons:
                                yield event.chain_result([image_component, keyboard])  # Telegram: 图片caption足够
                            else:
                                yield event.chain_result([image_component])
                        except Exception:
                            yield event.chain_result([Plain(comments), image_component])
                    elif platform_name == "lark":
                        try:
                            if keyboard.buttons:
                                yield event.chain_result([Plain(comments), image_component, keyboard])  # 飞书: 需要显式文本
                            else:
                                yield event.chain_result([Plain(comments), image_component])
                        except Exception:
                            yield event.chain_result([Plain(comments), image_component])
                    else:
                        yield event.chain_result([Plain(comments), image_component])
                        if keyboard.buttons:
                            yield event.chain_result([keyboard])
                else:
                    # 只发送评论 + 操作按钮
                    logger.info("图片获取失败，仅发送文本消息")
                    yield event.chain_result([Plain(f"📊 豆瓣评分信息\n\n{comments}"), keyboard])
                
                # 成功显示豆瓣信息，消费配额
                if self.quota_validator:
                    await self.quota_validator.consume_quota(
                        user_id=user_id,
                        action_type="douban_view",
                        plugin_name="douban",
                        points_cost=result.points_cost if 'result' in locals() and hasattr(result, 'points_cost') else 0
                    )
            finally:
                # 删除加载消息
                if loading_msg:
                    try:
                        platform_name = (event.get_platform_name() or "").lower()
                        if platform_name == "telegram":
                            from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
                            if isinstance(event, TelegramPlatformEvent) and hasattr(event, 'client') and hasattr(event.client, 'delete_message'):
                                chat_id = event.message_obj.group_id or event.get_sender_id()
                                await event.client.delete_message(
                                    chat_id=chat_id,
                                    message_id=getattr(loading_msg, "message_id", None)
                                )
                        elif platform_name == "lark":
                            # 飞书平台支持删除消息
                            if hasattr(event, 'delete_message'):
                                try:
                                    message_id = getattr(loading_msg, "message_id", None)
                                    if message_id:
                                        await event.delete_message(message_id)
                                        logger.debug(f"[douban] 成功删除飞书进度消息: {message_id}")
                                except Exception as e:
                                    logger.warning(f"[douban] 删除飞书进度消息失败: {e}")
                    except Exception as e:
                        logger.debug(f"删除加载消息失败: {e}")

        except Exception as e:
            logger.error(f"处理豆瓣链接异常: {e}")
            yield event.plain_result(f"❌ 处理豆瓣链接失败: {e}")
    
    def _set_callback_response(self, event: AstrMessageEvent, toast_type: str, message_zh: str, message_en: str):
        """设置飞书回调响应（Toast消息）"""
        try:
            platform_name = (event.get_platform_name() or "").lower()
            if platform_name == "lark" and hasattr(event.message_obj, 'callback_response'):
                event.message_obj.callback_response = {
                    "toast": {
                        "type": toast_type,  # "success", "warning", "error", "info"
                        "content": message_zh,
                        "i18n": {
                            "zh_cn": message_zh,
                            "en_us": message_en
                        }
                    }
                }
                logger.debug(f"[douban-callback] 设置回调响应: {toast_type} - {message_zh}")
        except Exception as e:
            logger.warning(f"[douban-callback] 设置回调响应失败: {e}")

    @filter.command("callback")
    @callback_handler("douban")
    @auto_stop_event
    async def handle_callback(self, event: AstrMessageEvent, data: str = ""):
        """
        处理回调按钮 - 处理用户点击的按钮操作
        
        使用回调路由器，只接收 douban: 开头的回调
        装饰器已经过滤了前缀，这里只需要提取 action
        """
        try:
            # 从消息中提取回调数据并去掉前缀
            raw = event.message_str.strip()
            parts = raw.split(" ", 1)
            if len(parts) < 2:
                return
            callback_data = parts[1].strip()
            
            logger.debug(f"[Douban] 收到回调数据: {callback_data}")

            # @callback_handler 装饰器已经过滤了非豆瓣插件的回调
            # 这里只需要解析回调数据格式即可
            
            is_json_callback = False
            json_data = None
            actual_callback_data = callback_data
            
            # 检查是否是JSON格式的回调数据（飞书平台）
            if callback_data.startswith("{") and callback_data.endswith("}"):
                try:
                    import json
                    json_data = json.loads(callback_data)
                    action_type = json_data.get("action", "")
                    
                    # 处理嵌套的回调格式：{"action": "callback", "data": "douban:..."}
                    if action_type == "callback":
                        nested_data = json_data.get("data", "")
                        if nested_data:
                            # 尝试解析嵌套的数据
                            try:
                                nested_json = json.loads(nested_data)
                                nested_action = nested_json.get("action", "")
                                if nested_action in ["douban_detail", "douban_page", "douban_switch", "douban_ai_interpret"]:
                                    json_data = nested_json
                                    action_type = nested_action
                                    actual_callback_data = nested_data
                                    is_json_callback = True
                                    logger.debug(f"[douban-callback] 解析到嵌套JSON回调: {json_data}")
                            except Exception:
                                # 不是JSON格式，是字符串格式
                                actual_callback_data = nested_data
                                logger.debug(f"[douban-callback] 解析到嵌套字符串回调: {nested_data}")
                    elif action_type in ["douban_detail", "douban_page", "douban_switch", "douban_ai_interpret", "yunpan_douban_search"]:
                        is_json_callback = True
                        logger.debug(f"[douban-callback] 解析到JSON回调: {json_data}")
                except Exception as e:
                    logger.debug(f"[douban-callback] JSON解析失败: {e}")
            
            # 移除 "douban:" 前缀（如果存在）
            if actual_callback_data.startswith("douban:"):
                actual_callback_data = actual_callback_data[7:]  # 移除 "douban:" 前缀
                logger.debug(f"[Douban] 移除前缀后的回调数据: {actual_callback_data}")

            # 处理JSON格式的飞书回调
            if is_json_callback and json_data:
                action_type = json_data.get("action", "")
                
                if action_type == "douban_detail":
                    try:
                        douban_type = json_data.get("type", "")
                        douban_id = json_data.get("id", "")
                        
                        if not douban_type or not douban_id:
                            self._set_callback_response(event, "error", "回调数据不完整", "Callback data incomplete")
                            yield event.plain_result("❌ 回调数据不完整")
                            event.stop_event()  # 中止事件流转
                            return
                        
                        self._set_callback_response(event, "success", "正在获取详情", "Loading details")
                        async for result in self._handle_detail_callback(event, douban_type, douban_id):
                            yield result
                        event.stop_event()  # 中止事件流转
                        return
                    except Exception as e:
                        logger.error(f"[douban-json-detail] 处理JSON详情回调失败: {e}")
                        self._set_callback_response(event, "error", "获取详情失败", "Failed to load details")
                        yield event.plain_result(f"❌ 获取详情失败: {e}")
                        event.stop_event()  # 中止事件流转
                        return
                
                elif action_type == "douban_page":
                    try:
                        search_type = json_data.get("search_type", "")
                        keyword = json_data.get("keyword", "")
                        page = json_data.get("page", 1)
                        
                        if not search_type or not keyword:
                            self._set_callback_response(event, "error", "回调数据不完整", "Callback data incomplete")
                            yield event.plain_result("❌ 回调数据不完整")
                            event.stop_event()  # 中止事件流转
                            return
                        
                        self._set_callback_response(event, "success", "正在翻页", "Loading page")
                        
                        # 获取飞书卡片更新token
                        card_token = getattr(event.message_obj, 'lark_card_token', None)
                        logger.debug(f"[douban-json-page] 获取到卡片token: {'有' if card_token else '无'}")
                        
                        async for result in self._handle_page_callback(event, search_type, keyword, page):
                            yield result
                        event.stop_event()  # 中止事件流转
                        return
                    except Exception as e:
                        logger.error(f"[douban-json-page] 处理JSON翻页回调失败: {e}")
                        self._set_callback_response(event, "error", "翻页失败", "Pagination failed")
                        yield event.plain_result(f"❌ 翻页失败: {e}")
                        event.stop_event()  # 中止事件流转
                        return
                
                elif action_type == "douban_switch":
                    try:
                        search_type = json_data.get("search_type", "")
                        keyword = json_data.get("keyword", "")
                        page = json_data.get("page", 1)
                        
                        if not search_type or not keyword:
                            self._set_callback_response(event, "error", "回调数据不完整", "Callback data incomplete")
                            yield event.plain_result("❌ 回调数据不完整")
                            event.stop_event()  # 中止事件流转
                            return
                        
                        self._set_callback_response(event, "success", "正在换源", "Switching source")
                        async for result in self._handle_switch_callback(event, search_type, keyword, page):
                            yield result
                        event.stop_event()  # 中止事件流转
                        return
                    except Exception as e:
                        logger.error(f"[douban-json-switch] 处理JSON换源回调失败: {e}")
                        self._set_callback_response(event, "error", "换源失败", "Switch failed")
                        yield event.plain_result(f"❌ 换源失败: {e}")
                        event.stop_event()  # 中止事件流转
                        return
                
                elif action_type == "douban_ai_interpret":
                    try:
                        douban_type = json_data.get("type", "")
                        douban_id = json_data.get("id", "")
                        
                        if not douban_type or not douban_id:
                            self._set_callback_response(event, "error", "回调数据不完整", "Callback data incomplete")
                            yield event.plain_result("❌ 回调数据不完整")
                            event.stop_event()  # 中止事件流转
                            return
                        
                        self._set_callback_response(event, "success", "AI解读请求已提交", "AI interpretation request submitted")
                        
                        # 直接执行AI解读，而不是返回链接
                        logger.debug(f"[douban-json-ai] 直接执行AI解读: {douban_type} - {douban_id}")
                        async for result in self._handle_douban_ai_interpret(event, douban_type, douban_id):
                            yield result
                        event.stop_event()  # 中止事件流转
                        return
                    except Exception as e:
                        logger.error(f"[douban-json-ai] 处理JSON AI解读回调失败: {e}")
                        self._set_callback_response(event, "error", "AI解读失败", "AI interpretation failed")
                        yield event.plain_result(f"❌ AI解读失败: {e}")
                        event.stop_event()  # 中止事件流转
                        return
                
                # 未知的JSON回调类型
                logger.warning(f"[douban-json] 未知的JSON回调类型: {action_type}")
                return

            # 处理传统格式的回调（保持向后兼容）
            callback_str = actual_callback_data
        
        except Exception as e:
            logger.error(f"[douban-callback] 回调数据解析失败: {e}")
            yield event.plain_result("❌ 回调数据解析失败")
            return
        
        try:
            if callback_str.startswith("detail:"):
                # 显示详情: detail:type:id
                parts = callback_str.split(":", 2)
                if len(parts) >= 3:
                    _, douban_type, douban_id = parts
                    async for result in self._handle_detail_callback(event, douban_type, douban_id):
                        yield result
                else:
                    yield event.plain_result("❌ 详情回调数据格式错误")
                    
            elif callback_str.startswith("page:"):
                # 翻页: page:type:keyword:page
                parts = callback_str.split(":", 3)
                if len(parts) >= 4:
                    _, search_type, keyword, page_str = parts
                    try:
                        page = int(page_str)
                        async for result in self._handle_page_callback(event, search_type, keyword, page):
                            yield result
                    except ValueError:
                        yield event.plain_result("❌ 页码格式错误")
                else:
                    yield event.plain_result("❌ 翻页回调数据格式错误")
                    
            elif callback_str.startswith("switch:"):
                # 换源: switch:type:keyword:page
                parts = callback_str.split(":", 3)
                if len(parts) >= 4:
                    _, search_type, keyword, page_str = parts
                    try:
                        page = int(page_str)
                        async for result in self._handle_switch_callback(event, search_type, keyword, page):
                            yield result
                    except ValueError:
                        yield event.plain_result("❌ 页码格式错误")
                else:
                    yield event.plain_result("❌ 换源回调数据格式错误")
                    
        except Exception as e:
            logger.error(f"豆瓣回调处理异常: {e}", exc_info=True)
            yield event.plain_result(f"❌ 处理失败: {e}")
            event.stop_event()  # 中止事件流转
    
    async def _handle_detail_callback(self, event: AstrMessageEvent, douban_type: str, douban_id: str):
        """处理详情回调"""
        try:
            # 直接调用现有的豆瓣链接处理逻辑
            # 构造一个豆瓣链接
            if douban_type == "book":
                douban_url = f"https://book.douban.com/subject/{douban_id}/"
            else:
                douban_url = f"https://movie.douban.com/subject/{douban_id}/"
            
            logger.info(f"处理豆瓣详情回调: {douban_type} - {douban_id}")
            
            # 调用现有的豆瓣链接处理方法
            async for result in self._handle_douban_link(event, douban_url):
                yield result
                
        except Exception as e:
            logger.error(f"处理豆瓣详情回调异常: {e}")
            yield event.plain_result(f"❌ 获取详情失败: {e}")
    
    async def _handle_page_callback(self, event: AstrMessageEvent, search_type: str, keyword: str, page: int):
        """处理翻页回调"""
        try:
            # 获取新页面的搜索结果
            capabilities = get_platform_capabilities(event, "Douban")
            message, keyboard = await self._handle_douban_search(keyword, search_type, page, capabilities)
            
            # 使用消息编辑器处理
            async for ret in MessageEditor.edit_or_send(event, message, keyboard):
                yield ret
            
        except Exception as e:
            logger.error(f"处理翻页回调异常: {e}")
            yield event.plain_result("❌ 翻页失败，请重试")
    
    async def _handle_switch_callback(self, event: AstrMessageEvent, search_type: str, keyword: str, page: int):
        """处理换源回调"""
        try:
            # 获取新类型的搜索结果
            capabilities = get_platform_capabilities(event, "Douban")
            message, keyboard = await self._handle_douban_search(keyword, search_type, page, capabilities)
            
            # 使用消息编辑器处理
            async for ret in MessageEditor.edit_or_send(event, message, keyboard):
                yield ret
            
        except Exception as e:
            logger.error(f"处理换源回调异常: {e}")
            yield event.plain_result("❌ 换源失败，请重试")

    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """处理所有消息：会话消息处理 + 豆瓣链接识别"""
        # 获取完整的消息文本
        message_text = event.message_str.strip()
        
        # 1. 优先处理会话消息（序号选择）
        session_id = event.get_session_id()
        user_id = event.get_sender_id()
        session = self.session_handler._get_session(session_id)
        
        if session:
            # 会话模式：处理用户输入的序号或导航命令
            logger.info(f"[Douban] 处理会话消息: {message_text}")
            result = await self.session_handler.handle_session_message(
                user_id, session_id, message_text
            )
            
            if result:
                # 处理返回值
                if isinstance(result, tuple):
                    # 检查是否是详情显示标记
                    if result[0] == "__SHOW_DETAIL__":
                        douban_url = result[1]
                        # 调用豆瓣链接处理方法显示详情
                        async for ret in self._handle_douban_link(event, douban_url):
                            yield ret
                    else:
                        # 普通元组（消息, 键盘）
                        message, keyboard = result
                        async for ret in MessageEditor.edit_or_send(
                            event, message, keyboard,
                            session_context=session,
                            auto_cleanup=True
                        ):
                            yield ret
                else:
                    # 字符串消息
                    async for ret in MessageEditor.edit_or_send(
                        event, result,
                        session_context=session,
                        auto_cleanup=True
                    ):
                        yield ret
            return
        
        # 2. 检查是否是豆瓣链接
        if self._is_douban_url(message_text):
            logger.info(f"识别到豆瓣链接，开始处理: {message_text}")
            async for result in self._handle_douban_link(event, message_text):
                yield result
            return
        
        # 如果不是豆瓣链接，不做任何处理（让其他插件处理）
        return
    
    async def terminate(self):
        """插件卸载时的清理工作"""
        logger.info("豆瓣评分插件正在卸载...")