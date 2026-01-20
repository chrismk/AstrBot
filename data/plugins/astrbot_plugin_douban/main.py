"""AstrBot 豆瓣评分图片显示插件 - 标准化版本"""

import os
from pathlib import Path
from typing import Optional

from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Plain, Image
from astrbot.core.utils.callback_router import CallbackRouter, callback_handler, auto_stop_event

# 导入通用模块
import sys
plugin_root = Path(__file__).parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

from common import (
    DatabaseManager,
    QuotaValidator,
    get_platform_capabilities,
    MessageEditor,
    CacheManager,
    get_session_manager,  # 使用全局会话管理器
    LarkMessageHelper,
    LoadingIndicator,
    auto_stop_command,
    get_search_statistics,
    get_separator
)
from common.user_utils import get_unified_user_id
from common.search_helper import SearchHelper

# 导入插件特定的处理器
from .handlers import (
    DoubanResponseBuilder,
    SessionHandler,
    DoubanAPI,
    DoubanURLParser,
    DoubanFormatter
)


@register("douban-rating", "Chrismk", "豆瓣评分图片显示插件 - 标准化跨平台交互", "2.0.0")
class DoubanPlugin(Star):
    """豆瓣评分插件主类 - 标准化版本"""
    
    # 默认常量（会被配置覆盖）
    PAGE_SIZE = 15  # 每页显示的搜索结果数量
    
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.config = config  # 插件配置
        
        # 读取插件配置
        self.plugin_config = self._load_plugin_config()
        logger.info(f"[Douban] 插件配置加载完成: AI解读={'启用' if self.plugin_config['enable_ai_interpretation'] else '禁用'}")
        
        # 应用配置到类属性
        self.PAGE_SIZE = self.plugin_config.get('page_size', 15)
        
        # 初始化API调用器（传入超时配置）
        api_timeout = self.plugin_config.get('api_timeout', 15)
        self.douban_api = DoubanAPI(timeout=api_timeout)
        logger.info(f"[Douban] API调用器初始化完成 (timeout={api_timeout}s)")
        
        # 初始化SessionManager（使用配置的超时时间）
        session_timeout = self.plugin_config.get('session_timeout', 1)
        self.session_manager = get_session_manager(timeout_minutes=session_timeout)
        logger.info(f"[Douban] SessionManager初始化完成 (timeout={session_timeout}min)")
        
        # 注册回调路由
        CallbackRouter.register("douban", self.handle_callback, plugin_instance=self)
        logger.info("[Douban] 已注册回调路由: douban")
        
        # 初始化缓存管理器（使用配置的缓存时间）
        cache_ttl = self.plugin_config.get('cache_ttl', 600)
        self.cache = CacheManager(default_ttl=cache_ttl)
        logger.info(f"[Douban] 缓存管理器初始化完成 (TTL={cache_ttl}s)")
        
        # 初始化配额系统
        self.quota_validator = None
        self.search_stats = None
        self.search_helper = None
        try:
            config = self.context.get_config()
            data_path = config.get("data_path", "data")
            db_path = os.path.join(data_path, "quota_system.db")
            self.db = DatabaseManager(db_path)
            self.quota_validator = QuotaValidator(self.db)
            self.search_stats = get_search_statistics(self.db)
            # 搜索辅助器
            self.search_helper = SearchHelper(
                plugin_name='douban',
                search_stats=self.search_stats,
                page_size=self.PAGE_SIZE
            )
            logger.info("[Douban] 配额系统和搜索统计初始化完成")
            
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
    
    def _load_plugin_config(self):
        """加载插件配置"""
        try:
            # 直接使用传入的 AstrBotConfig，它已经包含了用户的配置
            # 设置默认配置（作为备用）
            default_config = {
                # 基础设置
                'page_size': 15,
                'session_timeout': 1,
                'cache_ttl': 600,
                'api_timeout': 15,
                # AI解读设置
                'ai_prompt': "请基于以下豆瓣信息，用简洁的语言为用户推荐这本书/电影。重点关注：1) 作品的核心价值和亮点 2) 适合的读者/观众群体 3) 个人推荐理由。请控制在200字以内，语言要生动有趣。",
                'enable_ai_interpretation': True,
                'ai_max_length': 200,
                # 配额设置
                'quota_view_daily_limit': -1,
                'quota_view_points_cost': 0,
                'quota_search_daily_limit': -1,
                'quota_search_points_cost': 0,
                # 限流设置
                'rate_limit_view_max': 60,
                'rate_limit_view_window': 60,
                'rate_limit_search_max': 60,
                'rate_limit_search_window': 60,
                'rate_limit_ai_max': 60,
                'rate_limit_ai_window': 60
            }
            
            # 合并配置（用户配置优先，缺失的使用默认值）
            config = {}
            for key, default_value in default_config.items():
                config[key] = self.config.get(key, default_value)
            
            return config
            
        except Exception as e:
            logger.warning(f"[Douban] 加载插件配置失败，使用默认配置: {e}")
            return {
                'page_size': 15,
                'session_timeout': 1,
                'cache_ttl': 600,
                'api_timeout': 15,
                'ai_prompt': "请基于以下豆瓣信息，用简洁的语言为用户推荐这本书/电影。重点关注：1) 作品的核心价值和亮点 2) 适合的读者/观众群体 3) 个人推荐理由。请控制在200字以内，语言要生动有趣。",
                'enable_ai_interpretation': True,
                'ai_max_length': 200,
                'quota_view_daily_limit': -1,
                'quota_view_points_cost': 0,
                'quota_search_daily_limit': -1,
                'quota_search_points_cost': 0,
                'rate_limit_view_max': 60,
                'rate_limit_view_window': 60,
                'rate_limit_search_max': 60,
                'rate_limit_search_window': 60,
                'rate_limit_ai_max': 60,
                'rate_limit_ai_window': 60
            }
    
    def _register_quota_rules(self):
        """注册插件的配额和限流规则（使用标准化配置）"""
        try:
            from common.plugin_quota_config import sync_plugin_quota_and_rate_limit
            
            # 定义插件的配额操作
            actions = [
                {'action': 'view', 'action_type': 'douban_view', 'description': '查看豆瓣详情'},
                {'action': 'search', 'action_type': 'douban_search', 'description': '搜索豆瓣'},
                {'action': 'ai', 'action_type': 'douban_ai', 'description': 'AI解读'}
            ]
            
            # 使用标准化方式同步配额和限流配置
            quota_success, rate_limit_success = sync_plugin_quota_and_rate_limit(
                plugin_name='douban',
                plugin_config=self.plugin_config,
                quota_validator=self.quota_validator,
                actions=actions
            )
            
            if quota_success:
                logger.info("[Douban] 配额规则同步成功（从插件配置）")
            else:
                logger.warning("[Douban] 配额规则同步失败")
            
            if rate_limit_success:
                logger.info("[Douban] 限流规则同步成功（从插件配置）")
            else:
                logger.warning("[Douban] 限流规则同步失败")
                
        except ImportError:
            logger.warning("[Douban] 无法导入 plugin_quota_config，使用旧版配额注册")
            self._register_quota_rules_legacy()
    
    def _register_quota_rules_legacy(self):
        """旧版配额注册（兼容）"""
        view_daily_limit = self.plugin_config.get('quota_view_daily_limit', -1)
        view_points_cost = self.plugin_config.get('quota_view_points_cost', 0)
        search_daily_limit = self.plugin_config.get('quota_search_daily_limit', -1)
        search_points_cost = self.plugin_config.get('quota_search_points_cost', 0)
        
        rules = [
            {
                'action_type': 'douban_view',
                'free': {'daily_limit': view_daily_limit, 'points_cost': view_points_cost},
                'premium': {'daily_limit': view_daily_limit, 'points_cost': view_points_cost},
                'vip': {'daily_limit': -1, 'points_cost': 0},
                'description': '查看豆瓣评分详情'
            },
            {
                'action_type': 'douban_search',
                'free': {'daily_limit': search_daily_limit, 'points_cost': search_points_cost},
                'premium': {'daily_limit': search_daily_limit, 'points_cost': search_points_cost},
                'vip': {'daily_limit': -1, 'points_cost': 0},
                'description': '搜索豆瓣'
            }
        ]
        
        self.quota_validator.register_quota_rules(
            plugin_name='douban',
            rules=rules,
            override=True
        )
    
    # ==================== 命令处理器 ====================
    
    @filter.command("豆")
    @auto_stop_command
    async def handle_search_command(self, event: AstrMessageEvent, keyword: str = ""):
        """处理豆瓣搜索命令 - 搜索豆瓣信息"""
        user_id = get_unified_user_id(event)
        
        if not keyword:
            # 使用搜索辅助器显示提示
            if self.search_helper:
                hint = self.search_helper.get_empty_search_hint(user_id)
                yield event.plain_result(hint + "\n\n🔐 设置 cookies: /豆 dbcl2=\"xxx\"")
            else:
                yield event.plain_result("💡 使用方法:\n/豆 关键词 - 搜索豆瓣\n/豆 dbcl2=\"xxx\" - 设置cookies\n示例: /豆 中国的妇女与财产")
            return
        session_id = event.get_session_id()
        
        # 检查是否是设置 cookies 的命令
        if keyword.strip().startswith('dbcl2='):
            import re
            # 提取 dbcl2 的值（支持带引号和不带引号）
            match = re.search(r'dbcl2=["\'"]?([^"\'"\s]+)["\'"]?', keyword)
            if match:
                dbcl2_value = match.group(1)
                success = self.douban_api.cookies_manager.save_cookie(user_id, dbcl2_value)
                if success:
                    yield event.plain_result(f"✅ Cookies 设置成功！\n用户ID: {user_id}\n现在搜索豆瓣时将自动使用您的 cookies。")
                else:
                    yield event.plain_result("❌ Cookies 设置失败，请稍后重试。")
            else:
                yield event.plain_result("❌ Cookies 格式错误\n正确格式: /豆 dbcl2=\"224902776:h5H3iJrC5HE\"")
            return
        
        # 显示加载提示
        loading_msg_id = await LoadingIndicator.show(event, 'search')
        
        quota_result = None
        try:
            # 检查配额
            if self.quota_validator:
                quota_result = await self.quota_validator.check_quota(
                    user_id=user_id,
                    action_type='douban_search',
                    plugin_name='douban',
                    use_points=True
                )
                if not quota_result.allowed:
                    yield event.plain_result(quota_result.message)
                    return
            
            # 获取平台能力
            capabilities = get_platform_capabilities(event, "Douban")
            
            # 执行搜索（传递 user_id 以使用该用户的 cookies）
            results, total = await self.douban_api.search_douban(keyword, "book", 1, user_id=user_id)
            
            # 记录搜索统计
            if self.search_stats and results:
                self.search_stats.record_search(
                    user_id=user_id,
                    plugin_name='douban',
                    keyword=keyword,
                    result_count=total,
                    search_type='keyword'
                )
            
            if not results:
                # 检查用户是否设置了 cookies
                has_cookies = self.douban_api.cookies_manager.get_cookie(user_id) is not None
                
                if has_cookies:
                    # 已设置 cookies 但仍然失败（可能过期）
                    yield event.plain_result(
                        f"😔 没有找到关于 '{keyword}' 的结果\n\n"
                        f"💡 提示：豆瓣触发了反爬虫限制。\n"
                        f"您的 cookies 可能已过期，请重新设置：\n"
                        f"/豆 dbcl2=\"您的新cookies值\""
                    )
                else:
                    # 未设置 cookies，提示用户设置
                    yield event.plain_result(
                        f"😔 没有找到关于 '{keyword}' 的结果\n\n"
                        f"💡 提示：豆瓣触发了反爬虫限制。\n"
                        f"请设置您的豆瓣 cookies 以提高搜索成功率：\n"
                        f"/豆 dbcl2=\"您的cookies值\"\n\n"
                        f"获取方法：\n"
                        f"1. 浏览器访问 book.douban.com 并登录\n"
                        f"2. 按F12打开开发者工具\n"
                        f"3. Application → Cookies → 复制 dbcl2 的值"
                    )
                return
            
            # 格式化结果
            is_button_mode = capabilities.get('supports_buttons', False)
            switch_hint = "s-搜电影" if not is_button_mode else None  # 会话模式显示切换提示
            message, _ = DoubanFormatter.format_search_results(
                results, "book", 1, self.PAGE_SIZE, total,
                show_hints=not is_button_mode,  # 按钮模式不显示导航文本
                switch_hint=switch_hint
            )
            
            # 构建响应
            builder = DoubanResponseBuilder(capabilities)
            final_message, keyboard = builder.build_search_results(
                message=message,
                search_type="book",
                keyword=keyword,
                page=1,
                total_pages=(total + self.PAGE_SIZE - 1) // self.PAGE_SIZE,
                results=results
            )
            
            # 创建会话（会话模式）- 只使用 SessionManager
            if not capabilities['supports_buttons']:
                self.session_manager.create_session(
                    session_id=session_id,
                    session_type="douban_search",
                    user_id=user_id,
                    step=0,  # 搜索结果列表是主菜单（0级）
                    capabilities=capabilities,
                    data={
                        'keyword': keyword,
                        'search_type': 'book',
                        'page': 1,
                        'results': results,
                        'total': total
                    }
                )
            
            # 发送响应
            async for result in MessageEditor.edit_or_send(event, final_message, keyboard):
                yield result
            
            # 消费配额
            if self.quota_validator and quota_result:
                await self.quota_validator.consume_quota(
                    user_id=user_id,
                    action_type='douban_search',
                    plugin_name='douban',
                    points_cost=quota_result.points_cost
                )
                
        except Exception as e:
            logger.error(f"搜索豆瓣失败: {e}", exc_info=True)
            yield event.plain_result("❌ 搜索失败，请稍后重试")
        finally:
            await LoadingIndicator.hide(event, loading_msg_id)
    
    @filter.command("start")
    async def handle_start_command(self, event: AstrMessageEvent, param: str = ""):
        """处理 /start 命令，支持AI解读回调"""
        # 只处理豆瓣相关的 /start 参数
        if not param or not param.startswith("dbai_"):
            # 不是豆瓣的参数，不处理，让其他插件处理
            return
        
        # 检查是否是豆瓣AI解读回调
        if param.startswith("dbai_"):
            try:
                import base64
                import json
                
                # 解码参数
                encoded_payload = param[5:]  # 移除 "dbai_" 前缀
                decoded_bytes = base64.urlsafe_b64decode(encoded_payload)
                payload = json.loads(decoded_bytes.decode('utf-8'))
                
                douban_type = payload.get('type', '')
                douban_id = payload.get('id', '')
                
                if not douban_id:
                    yield event.plain_result("❌ 参数不完整")
                    event.stop_event()
                    return
                
                # 处理AI解读请求
                async for result in self._handle_douban_ai_interpret(event, douban_type, douban_id):
                    yield result
                event.stop_event()
                return
            except Exception as e:
                logger.error(f"解析豆瓣AI解读回调参数失败: {e}")
                yield event.plain_result("❌ 参数解析失败")
                event.stop_event()
                return
    
    async def _handle_douban_ai_interpret(self, event: AstrMessageEvent, douban_type: str, douban_id: str):
        """处理豆瓣AI解读请求 - 使用统一 AI 解读接口"""
        user_id = get_unified_user_id(event)
        
        # 检查AI解读功能是否启用
        if not self.plugin_config.get('enable_ai_interpretation', True):
            yield event.plain_result("❌ AI解读功能已被管理员禁用")
            return
        
        # 显示加载提示
        loading_msg_id = await LoadingIndicator.show(event, 'ai_interpret')
        
        try:
            # 获取豆瓣详细信息
            douban_info = await self.douban_api.get_douban_detail_info(douban_type, douban_id, user_id=user_id)
            
            if not douban_info:
                yield event.plain_result("❌ 获取豆瓣信息失败")
                return
            
            title = douban_info.get('title', '未知作品')
            max_length = self.plugin_config.get('ai_max_length', 200)
            custom_prompt = self.plugin_config.get('ai_prompt', '').strip()
            
            from common.ai_interpreter import get_ai_interpreter, AIInterpreter
            
            # 根据类型构建内容信息
            content_type = 'movie' if douban_type == 'movie' else 'book'
            if content_type == 'movie':
                content_info = AIInterpreter.build_movie_info(douban_info)
            else:
                content_info = AIInterpreter.build_book_info(douban_info)
            
            # 获取 AI 解读器
            interpreter = get_ai_interpreter(self.context)
            
            # 调用统一解读接口
            result = await interpreter.interpret(
                content_type=content_type,
                content_info=content_info,
                event=event,
                custom_prompt=custom_prompt if custom_prompt else None,
                max_length=max_length
            )
            
            if result:
                formatted = interpreter.format_result(content_type, title, result)
                yield event.plain_result(formatted)
            else:
                yield event.plain_result("❌ AI解读失败")
            
        except Exception as e:
            logger.error(f"处理豆瓣AI解读请求失败: {e}", exc_info=True)
            yield event.plain_result("❌ 处理AI解读请求失败，请稍后重试")
        finally:
            await LoadingIndicator.hide(event, loading_msg_id)
    
    # ==================== 回调处理器 ====================
    
    @filter.command("callback")
    @callback_handler("douban")
    @auto_stop_event
    async def handle_callback(self, event: AstrMessageEvent, data: str = ""):
        """处理回调按钮 - 处理用户点击的按钮操作"""
        try:
            # 从消息中提取回调数据并去掉前缀
            raw = event.message_str.strip()
            parts = raw.split(" ", 1)
            if len(parts) < 2:
                return
            callback_data = parts[1].strip()
            
            # 去掉 "douban:" 前缀
            if callback_data.startswith("douban:"):
                callback_data = callback_data[7:]  # 去掉 "douban:"
            
            logger.info(f"[Douban] 处理回调: {callback_data}")
            
            # 解析回调数据
            parts = callback_data.split(":")
            action = parts[0] if parts else ""
            
            # 详情回调: detail:movie:123456
            if action == "detail" and len(parts) >= 3:
                douban_type = parts[1]
                douban_id = parts[2]
                async for result in self._handle_detail_callback(event, douban_type, douban_id):
                    yield result
            
            # 翻页回调: page:book:关键词:2
            elif action == "page" and len(parts) >= 4:
                search_type = parts[1]
                keyword = parts[2]
                page = int(parts[3])
                async for result in self._handle_page_callback(event, search_type, keyword, page):
                    yield result
            
            # 换源回调: switch:movie:关键词:1
            elif action == "switch" and len(parts) >= 4:
                search_type = parts[1]
                keyword = parts[2]
                page = int(parts[3])
                async for result in self._handle_switch_callback(event, search_type, keyword, page):
                    yield result
            
            # 退出回调: exit
            elif action == "exit":
                async for result in self._handle_exit_callback(event):
                    yield result
            
            else:
                logger.warning(f"[Douban] 未知的回调动作: {action}")
                yield event.plain_result("❌ 未知的操作")
                
        except Exception as e:
            logger.error(f"[Douban] 处理回调失败: {e}", exc_info=True)
            # 不暴露详细错误信息给用户
            yield event.plain_result("❌ 处理失败，请稍后重试")
    
    async def _handle_detail_callback(self, event: AstrMessageEvent, douban_type: str, douban_id: str):
        """处理详情回调"""
        try:
            # 构建豆瓣链接并调用链接处理逻辑
            douban_url = f"https://{douban_type}.douban.com/subject/{douban_id}/"
            async for result in self._handle_douban_link(event, douban_url):
                yield result
        except Exception as e:
            logger.error(f"处理豆瓣详情回调异常: {e}", exc_info=True)
            yield event.plain_result("❌ 获取详情失败，请稍后重试")
    
    async def _handle_page_callback(self, event: AstrMessageEvent, search_type: str, keyword: str, page: int):
        """处理翻页回调"""
        try:
            user_id = get_unified_user_id(event)
            # 获取新页面的搜索结果
            results, total = await self.douban_api.search_douban(keyword, search_type, page, user_id=user_id)
            
            capabilities = get_platform_capabilities(event, "Douban")
            is_button_mode = capabilities.get('supports_buttons', False)
            
            # 根据当前类型生成切换提示
            switch_hint = None
            if not is_button_mode:
                switch_hint = "s-搜电影" if search_type == "book" else "s-搜图书"
            
            message, _ = DoubanFormatter.format_search_results(
                results, search_type, page, self.PAGE_SIZE, total,
                show_hints=not is_button_mode,  # 按钮模式不显示导航文本
                switch_hint=switch_hint
            )
            
            builder = DoubanResponseBuilder(capabilities)
            final_message, keyboard = builder.build_search_results(
                message, search_type, keyword, page, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE, results
            )
            
            async for result in MessageEditor.edit_or_send(event, final_message, keyboard):
                yield result
        except Exception as e:
            logger.error(f"处理翻页回调异常: {e}")
            yield event.plain_result("❌ 翻页失败，请重试")
    
    async def _handle_switch_callback(self, event: AstrMessageEvent, search_type: str, keyword: str, page: int):
        """处理换源回调"""
        try:
            user_id = get_unified_user_id(event)
            # search_type 已经是目标类型，直接使用
            results, total = await self.douban_api.search_douban(keyword, search_type, 1, user_id=user_id)
            
            capabilities = get_platform_capabilities(event, "Douban")
            is_button_mode = capabilities.get('supports_buttons', False)
            
            # 根据当前类型生成切换提示
            switch_hint = None
            if not is_button_mode:
                switch_hint = "s-搜电影" if search_type == "book" else "s-搜图书"
            
            message, _ = DoubanFormatter.format_search_results(
                results, search_type, 1, self.PAGE_SIZE, total,
                show_hints=not is_button_mode,  # 按钮模式不显示导航文本
                switch_hint=switch_hint
            )
            
            builder = DoubanResponseBuilder(capabilities)
            final_message, keyboard = builder.build_search_results(
                message, search_type, keyword, 1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE, results
            )
            
            async for result in MessageEditor.edit_or_send(event, final_message, keyboard):
                yield result
        except Exception as e:
            logger.error(f"处理换源回调异常: {e}")
            yield event.plain_result("❌ 换源失败，请重试")
    
    async def _handle_exit_callback(self, event: AstrMessageEvent):
        """处理退出回调 - 使用统一退出处理器"""
        from common.exit_handler import handle_exit
        async for result in handle_exit(event, self.session_manager, plugin_name="Douban"):
            yield result
    
    # ==================== 豆瓣链接处理 ====================
    
    async def _handle_douban_link(self, event: AstrMessageEvent, message_text: str):
        """处理豆瓣链接"""
        logger.info(f"检测到豆瓣链接: {message_text}")
        
        # 解析豆瓣链接
        douban_info = DoubanURLParser.extract_douban_info(message_text)
        if not douban_info:
            yield event.plain_result("❌ 无法识别的豆瓣链接格式")
            return
        
        douban_type, douban_id = douban_info
        user_id = get_unified_user_id(event)
        
        # 检查配额
        if self.quota_validator:
            quota_result = await self.quota_validator.check_quota(
                user_id=user_id,
                action_type='douban_view',
                plugin_name='douban',
                use_points=True
            )
            if not quota_result.allowed:
                yield event.plain_result(quota_result.message)
                return
        
        # 显示加载提示
        loading_msg_id = await LoadingIndicator.show(event, 'process')
        
        try:
            # 获取豆瓣图片
            image_data = await self.douban_api.get_douban_image(douban_type, douban_id)
            
            if image_data:
                # 获取评论
                comment_data = await self.douban_api.get_douban_comments(douban_type, douban_id)
                comments_text = DoubanFormatter.format_comments(comment_data) if comment_data else ""
                
                # 缓存详情信息（供其他插件使用，如 pansou 搜索资源）
                try:
                    from common.cache_manager import get_global_cache
                    cache = get_global_cache()
                    if cache is not None:
                        # 尝试从评论数据中获取标题，或者单独请求
                        title = ''
                        rating = ''
                        
                        # 评论 API 返回的数据中可能包含 subject 信息
                        if comment_data:
                            subject = comment_data.get('subject', {})
                            title = subject.get('title', '') or comment_data.get('title', '')
                            rating = subject.get('rating', {}).get('value', '') or comment_data.get('rating', {}).get('value', '')
                        
                        # 如果没有标题，尝试单独获取
                        if not title:
                            title = await self.douban_api.get_douban_title(douban_type, douban_id) or ''
                        
                        if title:
                            cache_key = f"douban_detail_{douban_type}_{douban_id}"
                            cache_data = {
                                'type': douban_type,
                                'id': douban_id,
                                'title': title,
                                'rating': rating,
                            }
                            cache.set(cache_key, cache_data, ttl=3600)  # 缓存1小时
                            logger.info(f"[Douban] 缓存详情: {cache_key} -> {title}")
                except Exception as e:
                    logger.debug(f"[Douban] 缓存详情失败: {e}")
                
                # 检查是否在会话中
                session_id = event.get_session_id()
                session = self.session_manager.get_session(session_id)
                in_session = session is not None
                
                # 获取平台能力
                capabilities = get_platform_capabilities(event, "Douban")
                platform_name = capabilities.get('platform_name', '').lower()
                is_button_mode = capabilities.get('supports_buttons', False)
                
                # 如果在会话中且是会话模式（非按钮模式），添加导航提示
                if in_session and comments_text and not is_button_mode:
                    from common.navigation_hint import NavigationHint
                    separator = get_separator(platform_name)
                    comments_text += f"\n\n{separator}"
                    
                    # 添加特殊操作提示（对应按钮模式的操作按钮）
                    comments_text += "\n💡 特殊操作："
                    comments_text += "\n  • r-搜索资源"
                    comments_text += "\n  • a-AI解读"
                    comments_text += "\n  • d-查看详情"
                    
                    # 根据会话的 step 自动生成标准导航提示
                    current_step = session.get('step', 0)
                    if NavigationHint:
                        hint = NavigationHint.get_hint(level=current_step)
                    else:
                        # 降级方案
                        hint = "💡 b-返回 | 0-退出" if current_step >= 1 else "💡 0-退出"
                    comments_text += f"\n{hint}"
                    
                    # 添加超时提示
                    timeout_minutes = self.session_handler.SESSION_TIMEOUT_MINUTES
                    comments_text += f"\n⏱️ 请在 {timeout_minutes} 分钟内输入选择"
                
                # 发送图片和评论
                logger.info(f"发送图片消息，图片大小: {len(image_data)} bytes")
                image_component = Image.fromBytes(image_data)
                
                # 构建操作按钮
                builder = DoubanResponseBuilder(capabilities)
                bot_username = event.get_self_id() or "zslraibot"
                keyboard = builder.build_action_keyboard(douban_type, douban_id, None, bot_username)
                
                # 根据平台发送不同格式
                if platform_name == "lark":
                    # 飞书：图片在上，文字在下（飞书适配器已处理顺序）
                    if comments_text:
                        if keyboard:
                            yield event.chain_result([image_component, Plain(comments_text), keyboard])
                        else:
                            yield event.chain_result([image_component, Plain(comments_text)])
                    else:
                        if keyboard:
                            yield event.chain_result([image_component, keyboard])
                        else:
                            yield event.chain_result([image_component])
                else:
                    # Telegram等：使用caption，图片和键盘一起发送
                    if comments_text:
                        image_component.caption = comments_text
                    if keyboard:
                        yield event.chain_result([image_component, keyboard])
                    else:
                        yield event.chain_result([image_component])
                
                # 消费配额
                if self.quota_validator:
                    await self.quota_validator.consume_quota(
                        user_id=user_id,
                        action_type='douban_view',
                        plugin_name='douban',
                        points_cost=quota_result.points_cost if hasattr(quota_result, 'points_cost') else 0
                    )
            else:
                yield event.plain_result("❌ 获取豆瓣图片失败")
                
        except Exception as e:
            logger.error(f"处理豆瓣链接异常: {e}", exc_info=True)
            yield event.plain_result("❌ 处理豆瓣链接失败，请稍后重试")
        finally:
            await LoadingIndicator.hide(event, loading_msg_id)
    
    # ==================== 消息监听 ====================
    
    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """处理所有消息：会话消息处理 + 豆瓣链接识别"""
        # 1. 如果事件已经有结果，不处理（避免重复处理）
        if event.get_result():
            logger.debug("[Douban] on_message: 跳过 - 事件已有结果")
            return
        
        message_text = (event.message_str or "").strip()
        if not message_text:
            return
        
        # 2. 跳过命令消息（以 / 开头），这些由命令处理器处理
        if message_text.startswith('/'):
            logger.debug(f"[Douban] on_message: 跳过 - 是命令: {message_text}")
            return
        
        # 3. 跳过回调消息（某些平台可能不以 / 开头）
        if message_text.startswith('callback '):
            logger.debug(f"[Douban] on_message: 跳过 - 是回调: {message_text}")
            return
        
        session_id = event.get_session_id()
        
        # 4. 优先处理会话消息
        # 使用 match_session 进行类型检查和自动续期
        if self.session_manager.match_session(session_id, 'douban_search'):
            session = self.session_manager.get_session(session_id)
            
            # 特殊处理：如果会话刚创建且消息是命令关键词，跳过
            # 这是为了处理某些平台（如飞书）在命令处理后会将命令消息再次传递的情况
            session_data = session.get('data', {})
            results = session_data.get('results', [])
            
            # 如果会话刚创建（有搜索结果）且消息包含命令关键词，则跳过
            # 例如：消息是 "豆 宇宙" 或 "豆宇宙"，说明是命令的重复传递
            if results and (message_text.startswith('豆 ') or message_text.startswith('豆')):
                logger.debug(f"[Douban] on_message: 跳过 - 会话刚创建且是命令关键词 - message={message_text}")
                return
            
            # 有会话，处理会话消息
            logger.debug(f"[Douban] on_message: 检测到会话 - session_id={session_id}, message={message_text}")
            user_id = get_unified_user_id(event)
            result = await self.session_handler.handle_session_message(user_id, session_id, message_text)
            if result:
                # 处理不同类型的返回值
                if isinstance(result, tuple):
                    if len(result) == 2 and result[0] == "__SHOW_DETAIL__":
                        # 特殊标记：显示详情
                        douban_url = result[1]
                        async for r in self._handle_douban_link(event, douban_url):
                            yield r
                    elif len(result) == 3 and result[0] == "TRIGGER_AI_INTERPRET":
                        # 特殊标记：触发 AI 解读
                        search_type = result[1]
                        douban_id = result[2]
                        logger.info(f"[Douban] 触发AI解读 - type={search_type}, id={douban_id}")
                        async for r in self._handle_douban_ai_interpret(event, search_type, douban_id):
                            yield r
                    elif len(result) == 2 and result[0] == "TRIGGER_PANSOU_SEARCH":
                        # 特殊标记：触发 Pansou 搜索
                        title = result[1]
                        # 结束豆瓣会话，让 Pansou 接管（互斥会话模式）
                        self.session_manager.end_session(session_id)
                        logger.info(f"[Douban] 结束会话，触发Pansou搜索 - 标题: {title}")
                        
                        # 尝试直接调用 Pansou 插件
                        pansou_plugin = None
                        # 使用 context.get_all_stars() 获取所有插件元数据
                        for star_md in self.context.get_all_stars():
                            if star_md.star_cls and star_md.star_cls.__class__.__name__ == "PansouPlugin":
                                pansou_plugin = star_md.star_cls
                                break
                        
                        if pansou_plugin and hasattr(pansou_plugin, "_handle_command"):
                            logger.info("[Douban] 显式调用 Pansou 插件执行搜索（创建 Pansou 会话）")
                            
                            # 关键：在 yield 之前停止事件传播，并清空消息内容防止后续插件处理
                            event.stop_event()
                            event.message_str = ""  # 清空消息，让后续插件（如Pansou）看到空消息而跳过
                            event.is_handled = True # 设置自定义标记
                            
                            # 调用 Pansou 搜索，创建 Pansou 会话（互斥会话模式）
                            async for r in pansou_plugin._handle_command(event, title, create_session=True, from_plugin="douban"):
                                yield r
                            return
                        
                        # 降级方案：修改消息内容，希望后续插件处理（如果执行顺序允许）
                        event.message_str = f"/搜 {title}"
                        logger.info(f"[Douban] 未找到 Pansou 插件或无法直接调用，尝试修改消息流转: {event.message_str}")
                        return
                    else:
                        # 普通元组：(消息, 键盘)
                        message, keyboard = result
                        async for r in MessageEditor.edit_or_send(event, message, keyboard):
                            yield r
                elif isinstance(result, str):
                    # 纯字符串消息
                    yield event.plain_result(result)
                event.stop_event()
                return
        
        # 5. 没有会话，不处理任何消息
        # 注意：不要在这里检测会话命令并提示超时，因为：
        # 1. 用户可能在使用其他插件的会话（如签到插件）
        # 2. 数字输入可能是其他插件的序号选择
        # 3. 只有在确认用户之前有豆瓣会话的情况下才应该提示超时
        logger.debug(f"[Douban] on_message: 没有会话，跳过处理 - message={message_text}")
        
        # 检查是否为豆瓣链接
        if DoubanURLParser.is_douban_url(message_text):
            logger.debug(f"[Douban] on_message: 检测到豆瓣链接 - {message_text}")
            async for result in self._handle_douban_link(event, message_text):
                yield result
            event.stop_event()
            return
    
    async def terminate(self):
        """插件卸载时的清理工作"""
        logger.info("豆瓣评分插件正在卸载...")
        # 清理会话
        if hasattr(self, 'session_manager'):
            # SessionManager 会自动清理过期会话
            pass
        logger.info("豆瓣评分插件已卸载")
