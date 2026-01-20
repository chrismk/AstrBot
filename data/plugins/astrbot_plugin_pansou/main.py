"""
资源搜索插件主文件
支持多平台网盘资源搜索
"""
import json
import sys
from pathlib import Path
from typing import Dict, Any

import os
from astrbot.api import logger, AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Plain
from astrbot.core.utils.callback_router import CallbackRouter, callback_handler, auto_stop_event

# 导入统一用户ID工具
try:
    from common.user_utils import get_unified_user_id
except ImportError:
    def get_unified_user_id(event):
        return event.get_sender_id()

# 导入处理器
from .handlers.pansou_api import PansouAPI
from .handlers.formatter import PansouFormatter
from .handlers.session_handler import SessionHandler
from .handlers.response_builder import PansouResponseBuilder

# 添加插件根目录到sys.path以导入通用模块
plugin_root = Path(__file__).parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

# 导入通用模块
try:
    from common.platform_capabilities import get_platform_capabilities
    from common.loading_indicator import LoadingIndicator
    from common.database_manager import DatabaseManager
    from common.quota_validator import QuotaValidator
    from common.session_manager import get_session_manager  # 引入全局获取函数
    from common.message_editor import MessageEditor
    from common.search_statistics import get_search_statistics
    from common.search_helper import SearchHelper
    COMMON_MODULES_AVAILABLE = True
except ImportError as e:
    logger.error(f"[Pansou] 导入通用模块失败: {e}")
    COMMON_MODULES_AVAILABLE = False
    raise


@register("pansou", "资源搜索", "1.0.0", "搜索多平台网盘资源")
class PansouPlugin(Star):
    """资源搜索插件"""
    
    PAGE_SIZE = 15
    SESSION_TIMEOUT_MINUTES = 1
    
    def __init__(self, context, config: AstrBotConfig = None):
        super().__init__(context)
        self.plugin_config = config or {}
        
        # 加载插件配置
        self._load_plugin_config()
        
        # 初始化API
        self.pansou_api = PansouAPI()
        logger.info("[Pansou] API调用器初始化完成")
        
        # 初始化会话管理器（使用配置的超时时间）
        self.session_manager = get_session_manager(timeout_minutes=self.SESSION_TIMEOUT_MINUTES)
        logger.info(f"[Pansou] SessionManager初始化完成 (timeout={self.SESSION_TIMEOUT_MINUTES}min)")
        
        # 初始化限流器（使用全局实例）
        from common.rate_limiter import get_rate_limiter
        self.rate_limiter = get_rate_limiter()
        logger.info("[Pansou] RateLimiter初始化完成")
        
        # 初始化配额系统和搜索统计
        self.quota_validator = None
        self.search_stats = None
        try:
            astrbot_config = self.context.get_config()
            data_path = astrbot_config.get("data_path", "data")
            db_path = os.path.join(data_path, "quota_system.db")
            self.db = DatabaseManager(db_path)
            self.quota_validator = QuotaValidator(self.db)
            self.search_stats = get_search_statistics(self.db)
            
            # 搜索辅助器
            self.search_helper = SearchHelper(
                plugin_name='pansou',
                search_stats=self.search_stats,
                page_size=self.PAGE_SIZE
            )
            logger.info("[Pansou] 配额系统和搜索统计初始化完成")
            
            # 注册配额规则
            self._register_quota_rules()
        except Exception as e:
            logger.error(f"[Pansou] 配额系统初始化失败: {e}")
        
        # 初始化会话处理器
        self.session_handler = SessionHandler(
            session_manager=self.session_manager,
            pansou_api=self.pansou_api
        )
        logger.info("[Pansou] 会话处理器初始化完成")
        
        # 注册回调路由
        CallbackRouter.register("pansou", self.handle_callback, plugin_instance=self)
        logger.info("[Pansou] 已注册回调路由: pansou")
        
        logger.info("[Pansou] 资源搜索插件初始化完成")
    
    def _load_plugin_config(self):
        """加载插件配置"""
        defaults = {
            'page_size': 15,
            'session_timeout': 1,
            'quota_search_daily_limit': -1,
            'quota_search_points_cost': 0,
            'rate_limit_search_max': 60,
            'rate_limit_search_window': 60
        }
        for key, default in defaults.items():
            if key not in self.plugin_config:
                self.plugin_config[key] = default
        
        # 应用配置
        self.PAGE_SIZE = self.plugin_config.get('page_size', 15)
        self.SESSION_TIMEOUT_MINUTES = self.plugin_config.get('session_timeout', 1)
    
    def _register_quota_rules(self):
        """注册配额和限流规则（使用标准化配置）"""
        if not self.quota_validator:
            return
        
        try:
            from common.plugin_quota_config import sync_plugin_quota_and_rate_limit
            
            actions = [
                {'action': 'search', 'action_type': 'pansou_search', 'description': '搜索网盘资源'}
            ]
            
            quota_success, rate_limit_success = sync_plugin_quota_and_rate_limit(
                plugin_name='pansou',
                plugin_config=self.plugin_config,
                quota_validator=self.quota_validator,
                actions=actions
            )
            
            if quota_success:
                logger.info("[Pansou] 配额规则同步成功")
            if rate_limit_success:
                logger.info("[Pansou] 限流规则同步成功")
                
        except ImportError:
            # 兼容旧版
            rules = [
                {
                    'action_type': 'pansou_search',
                    'free': {'daily_limit': -1, 'points_cost': 0},
                    'premium': {'daily_limit': -1, 'points_cost': 0},
                    'vip': {'daily_limit': -1, 'points_cost': 0},
                    'description': '搜索网盘资源'
                }
            ]
            try:
                self.quota_validator.register_quota_rules(plugin_name='pansou', rules=rules, override=False)
            except Exception as e:
                logger.error(f"[Pansou] 注册配额规则失败: {e}")
    
    # ==================== 命令处理器 ====================
    
    @filter.command("搜")
    @auto_stop_event
    async def handle_search_command(self, event: AstrMessageEvent, keyword: str = ""):
        """处理资源搜索命令 - 搜索网盘资源"""
        logger.info(f"[Pansou] handle_search_command 被调用 - keyword: {keyword}")
        user_id = get_unified_user_id(event)
        
        if not keyword:
            # 使用搜索辅助器显示提示
            if COMMON_MODULES_AVAILABLE and hasattr(self, 'search_helper'):
                hint = self.search_helper.get_empty_search_hint(user_id)
                yield event.plain_result(hint)
            else:
                yield event.plain_result("💡 使用方法: /搜 关键词\n示例: /搜 宇宙")
            return
        
        async for result in self._handle_command(event, keyword):
            yield result
    
    @filter.command("start")
    async def handle_start_command(self, event: AstrMessageEvent, param: str = ""):
        """处理 Telegram /start 命令（Deep Link）"""
        if not param or not param.startswith("ps_"):
            # 不是 Pansou 的参数，不处理，让其他插件处理
            return
        
        # 处理豆瓣插件跳转过来的搜索请求
        if param.startswith("ps_"):
            try:
                import base64
                import json
                
                # 解码参数
                encoded_payload = param[3:]  # 移除 "ps_" 前缀
                decoded_bytes = base64.urlsafe_b64decode(encoded_payload)
                payload = json.loads(decoded_bytes.decode('utf-8'))
                
                douban_type = payload.get('type', '')
                douban_id = payload.get('id', '')
                
                if not douban_id:
                    yield event.plain_result("❌ 搜索参数不完整")
                    event.stop_event()
                    return
                
                # 从豆瓣 API 获取标题
                title = await self._get_douban_title_by_id(douban_type, douban_id)
                if not title:
                    yield event.plain_result("❌ 无法获取豆瓣标题，搜索失败")
                    event.stop_event()
                    return
                
                logger.info(f"[Pansou] 从豆瓣插件接收搜索请求: type={douban_type}, id={douban_id}, title={title}")
                
                # 执行搜索
                async for result in self._handle_command(event, title):
                    yield result
                event.stop_event()
                return
                    
            except Exception as e:
                logger.error(f"[Pansou] 解析豆瓣跳转参数失败: {e}")
                yield event.plain_result("❌ 搜索参数解析失败")
                event.stop_event()
                return
    
    async def _handle_command(self, event: AstrMessageEvent, message: str, create_session: bool = True, from_plugin: str = None):
        """
        处理命令
        
        Args:
            event: 消息事件
            message: 搜索关键词
            create_session: 是否创建会话（默认 True）
            from_plugin: 来源插件名称（如 "douban"），用于显示会话切换提示
        """
        try:
            # 解析命令参数
            parts = message.strip().split(maxsplit=1)
            if not parts:
                yield event.plain_result("❌ 请输入搜索关键词\n💡 用法: /搜 关键词")
                return
            
            keyword = parts[0]
            cloud_type_hint = parts[1] if len(parts) > 1 else None
            
            # 解析网盘类型提示
            cloud_types = self._parse_cloud_type_hint(cloud_type_hint)
            
            # 获取用户ID
            user_id = get_unified_user_id(event)
            
            # 限流检查
            is_allowed, error_msg = self.rate_limiter.is_allowed(user_id, 'search')
            if not is_allowed:
                yield event.plain_result(f"❌ {error_msg}")
                return
            
            # 配额检查
            if self.quota_validator:
                quota_result = await self.quota_validator.check_quota(
                    user_id=user_id,
                    action_type='pansou_search',
                    plugin_name='pansou',
                    use_points=True
                )
                if not quota_result.allowed:
                    yield event.plain_result(quota_result.message)
                    return
            
            # 获取平台能力
            capabilities = get_platform_capabilities(event, "Pansou")
            is_button_mode = capabilities.get('supports_buttons', False)
            
            # 调试日志：输出平台信息
            platform_name = event.get_platform_name()
            logger.info(f"[Pansou] 搜索请求 - 平台: {platform_name}, 按钮模式: {is_button_mode}, 关键词: {keyword}")
            
            # 如果没有指定云盘类型，默认排除 magnet 和 ed2k
            if not cloud_types:
                cloud_types = "baidu,aliyun,quark,tianyi,uc,mobile,115,pikpak,xunlei,123"
            
            # 显示加载提示
            loading_msg_id = await LoadingIndicator.show(event, 'search')
            
            # 执行搜索
            results, total = await self.pansou_api.search(
                keyword=keyword,
                cloud_types=cloud_types,
                page=1,
                page_size=self.PAGE_SIZE
            )
            
            # 隐藏加载提示
            await LoadingIndicator.hide(event, loading_msg_id)
            
            # 检查是否是异常（results 为 None 表示异常）
            if results is None:
                yield event.plain_result("⚠️ 搜索引擎异常，请稍后再试")
                return
            
            if not results:
                # 使用搜索辅助器显示无结果提示
                if COMMON_MODULES_AVAILABLE and hasattr(self, 'search_helper'):
                    hint = self.search_helper.format_no_result_hint(keyword, user_id)
                    yield event.plain_result(hint)
                else:
                    yield event.plain_result(f"😔 没有找到关于 '{keyword}' 的资源")
                # 记录搜索统计（即使没有结果）
                if self.search_stats:
                    self.search_stats.record_search(user_id, 'pansou', keyword, 0)
                return
            
            # 记录搜索统计
            if self.search_stats:
                self.search_stats.record_search(user_id, 'pansou', keyword, total)
            
            # 格式化结果
            filter_hint = "bd-百度/al-阿里/qk-夸克/ty-天翼/uc/115/pk-PikPak/xl-迅雷/123" if not is_button_mode else None
            message, _ = PansouFormatter.format_search_results(
                results, keyword, 1, self.PAGE_SIZE, total,
                show_hints=not is_button_mode,
                filter_hint=filter_hint,
                from_plugin=from_plugin  # 传递来源插件信息
            )
            
            # 构建响应
            builder = PansouResponseBuilder(capabilities)
            final_message, keyboard = builder.build_search_results(
                message=message,
                keyword=keyword,
                page=1,
                total_pages=(total + self.PAGE_SIZE - 1) // self.PAGE_SIZE,
                results=results,
                cloud_types=cloud_types
            )
            
            # 发送结果
            if keyboard:
                yield event.chain_result([Plain(final_message), keyboard])
            else:
                yield event.plain_result(final_message)
            
            # 如果是会话模式，创建会话（全局单一会话模式，自动覆盖）
            if not is_button_mode and create_session:
                session_id = event.get_session_id()
                
                self.session_manager.create_session(
                    session_id=session_id,
                    session_type='pansou_search',
                    user_id=user_id,
                    data={
                        'keyword': keyword,
                        'page': 1,
                        'results': results,
                        'total': total,
                        'cloud_types': cloud_types
                    },
                    capabilities=capabilities
                )
                logger.info(f"[Pansou] 创建会话: {session_id} (全局单一会话模式)")
            
            # 消费配额
            if self.quota_validator and quota_result:
                await self.quota_validator.consume_quota(
                    user_id=user_id,
                    action_type='pansou_search',
                    plugin_name='pansou',
                    points_cost=quota_result.points_cost
                )
                
        except Exception as e:
            logger.error(f"[Pansou] 处理命令异常: {e}")
            yield event.plain_result(f"❌ 搜索失败: {str(e)}")
    
    def _parse_cloud_type_hint(self, hint: str) -> str:
        """
        解析网盘类型提示
        
        Args:
            hint: 用户输入的提示词
            
        Returns:
            网盘类型代码（逗号分隔）
        """
        if not hint:
            return None
        
        hint_lower = hint.lower()
        
        # 网盘类型映射
        type_mapping = {
            "百度": "baidu",
            "baidu": "baidu",
            "阿里": "aliyun",
            "aliyun": "aliyun",
            "夸克": "quark",
            "quark": "quark",
            "天翼": "tianyi",
            "tianyi": "tianyi",
            "115": "115",
            "pikpak": "pikpak",
            "迅雷": "xunlei",
            "xunlei": "xunlei",
            "磁力": "magnet",
            "magnet": "magnet"
        }
        
        for key, value in type_mapping.items():
            if key in hint_lower:
                return value
        
        return None
    
    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """处理消息事件"""
        # 如果消息已被其他插件处理（如豆瓣），跳过
        if getattr(event, 'is_handled', False):
            logger.info(f"[Pansou] 跳过（已被标记处理）")
            return

        message_text = (event.message_str or "").strip()
        logger.info(f"[Pansou] on_message 被调用 - message: {message_text}, has_result: {event.get_result() is not None}")
        
        # 跳过已有结果的消息
        if event.get_result():
            logger.info(f"[Pansou] 跳过（已有结果）")
            return
        
        if not message_text:
            return
        
        # 检查是否是搜索命令（支持豆瓣插件流转过来的命令）
        if message_text.startswith('/搜 ') or message_text.startswith('搜 '):
            logger.info(f"[Pansou] 检测到搜索命令，手动处理")
            # 提取关键词
            keyword = message_text.split(maxsplit=1)[1] if len(message_text.split(maxsplit=1)) > 1 else ""
            if keyword:
                async for result in self._handle_command(event, keyword):
                    yield result
                event.stop_event()
            return
        
        # 跳过其他命令消息
        if message_text.startswith('/'):
            logger.info(f"[Pansou] 跳过（其他命令消息）")
            return
        
        # 跳过回调消息
        if message_text.startswith('callback '):
            return
        
        # 检查是否在会话中
        session_id = event.get_session_id()
        
        # 使用 match_session 进行类型检查和自动续期
        if self.session_manager.match_session(session_id, 'pansou_search'):
            # 检查是否是退出命令
            if message_text == '0':
                self.session_manager.end_session(session_id)
                yield event.plain_result("👋 已退出搜索会话")
                event.stop_event()
                return
            
            # 调用会话处理器
            result = await self.session_handler.handle_session_message(
                user_id=get_unified_user_id(event),
                session_id=session_id,
                message=message_text
            )
            
            if result:
                # 处理不同类型的返回值
                if isinstance(result, tuple) and len(result) == 2:
                    # 检查是否是特殊标记
                    if result[0] == "TRIGGER_PAGE":
                        # 翻页操作
                        new_page = result[1]
                        loading_msg_id = await LoadingIndicator.show(event, 'search')
                        try:
                            page_result = await self.session_handler.execute_page(session_id, new_page)
                            if page_result:
                                message, keyboard = page_result
                                if keyboard:
                                    yield event.chain_result([Plain(message), keyboard])
                                else:
                                    yield event.plain_result(message)
                        finally:
                            await LoadingIndicator.hide(event, loading_msg_id)
                        event.stop_event()
                        return
                    
                    if result[0] == "TRIGGER_FILTER":
                        # 筛选操作
                        cloud_type = result[1]
                        loading_msg_id = await LoadingIndicator.show(event, 'search')
                        try:
                            filter_result = await self.session_handler.execute_filter(session_id, cloud_type)
                            if filter_result:
                                message, keyboard = filter_result
                                if keyboard:
                                    yield event.chain_result([Plain(message), keyboard])
                                else:
                                    yield event.plain_result(message)
                        finally:
                            await LoadingIndicator.hide(event, loading_msg_id)
                        event.stop_event()
                        return
                    
                    # 元组返回（消息, 键盘）
                    message, keyboard = result
                    if keyboard:
                        yield event.chain_result([Plain(message), keyboard])
                    else:
                        yield event.plain_result(message)
                    event.stop_event()
                    return
                else:
                    # 字符串返回
                    yield event.plain_result(result)
                    event.stop_event()
                    return
    
    @filter.command("callback")
    @callback_handler("pansou")
    @auto_stop_event
    async def handle_callback(self, event: AstrMessageEvent, data: str = ""):
        """处理回调事件"""
        logger.info(f"[Pansou] 处理回调数据: {data}")
        
        # 处理可能的 'pansou:' 前缀
        if data.startswith("pansou:"):
            data = data[7:]  # 去掉 "pansou:" 前缀
            logger.info(f"[Pansou] 去除前缀后: {data}")
        
        try:
            # 尝试解析JSON格式（飞书）
            try:
                parsed_data = json.loads(data)
                logger.info(f"[Pansou] 解析JSON成功: {parsed_data}")
                action = parsed_data.get('action', '')
                
                if action == 'pansou_page':
                    async for result in self._handle_page_callback_json(event, parsed_data):
                        yield result
                elif action == 'pansou_douban_search':
                    # 处理豆瓣搜索回调
                    async for result in self._handle_douban_search_callback(event, parsed_data):
                        yield result
                else:
                    return
                    
            except json.JSONDecodeError:
                # 解析传统格式（Telegram）
                parts = data.split(':')
                if len(parts) < 2:
                    return
                
                action = parts[0]
                if action == 'page':
                    async for result in self._handle_page_callback(event, parts):
                        yield result
            
        except Exception as e:
            logger.error(f"[Pansou] 处理回调异常: {e}")
            yield event.plain_result("❌ 操作失败，请重试")
    
    async def _handle_page_callback(self, event: AstrMessageEvent, parts: list):
        """处理翻页回调（传统格式）"""
        try:
            # CallbackRouter已去掉pansou:前缀
            # parts格式: ['page', 'keyword', 'page_num', 'cloud_types']
            keyword = parts[1]
            page = int(parts[2])
            cloud_types = parts[3] if len(parts) > 3 and parts[3] else None
            
            # 如果没有指定云盘类型，使用默认列表（排除 magnet 和 ed2k）
            search_cloud_types = cloud_types
            if not cloud_types:
                search_cloud_types = "baidu,aliyun,quark,tianyi,uc,mobile,115,pikpak,xunlei,123"
            
            # 搜索
            results, total = await self.pansou_api.search(
                keyword=keyword,
                cloud_types=search_cloud_types,
                page=page,
                page_size=self.PAGE_SIZE
            )
            
            logger.info(f"[Pansou] 翻页搜索结果: {len(results)}条, page={page}")
            
            # 格式化结果
            capabilities = get_platform_capabilities(event, "Pansou")
            message, _ = PansouFormatter.format_search_results(
                results, keyword, page, self.PAGE_SIZE, total,
                show_hints=False
            )
            
            # 构建响应
            builder = PansouResponseBuilder(capabilities)
            final_message, keyboard = builder.build_search_results(
                message, keyword, page,
                (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE,
                results, cloud_types
            )
            
            # 编辑或发送消息
            async for result in MessageEditor.edit_or_send(event, final_message, keyboard):
                yield result
                
        except Exception as e:
            logger.error(f"[Pansou] 处理翻页回调异常: {e}")
            yield event.plain_result("❌ 翻页失败，请重试")
    
    async def _handle_page_callback_json(self, event: AstrMessageEvent, data: Dict):
        """处理翻页回调（JSON格式）"""
        try:
            keyword = data.get('keyword')
            page = data.get('page', 1)
            cloud_types = data.get('cloud_types')
            
            # 参数验证
            if not keyword:
                logger.error(f"[Pansou] 翻页回调keyword为空! 完整数据: {data}")
                logger.error(f"[Pansou] parsed_data内容: keyword={keyword}, page={page}, cloud_types={cloud_types}")
                yield event.plain_result("❌ 搜索参数丢失，请重新搜索")
                return
            
            # 如果没有指定云盘类型，使用默认列表（排除 magnet 和 ed2k）
            search_cloud_types = cloud_types
            if not cloud_types:
                search_cloud_types = "baidu,aliyun,quark,tianyi,uc,mobile,115,pikpak,xunlei,123"
            
            # 搜索
            results, total = await self.pansou_api.search(
                keyword=keyword,
                cloud_types=search_cloud_types,
                page=page,
                page_size=self.PAGE_SIZE
            )
            
            logger.info(f"[Pansou] JSON翻页搜索结果: {len(results)}条, page={page}")
            
            # 格式化结果
            capabilities = get_platform_capabilities(event, "Pansou")
            message, _ = PansouFormatter.format_search_results(
                results, keyword, page, self.PAGE_SIZE, total,
                show_hints=False
            )
            
            # 构建响应
            builder = PansouResponseBuilder(capabilities)
            final_message, keyboard = builder.build_search_results(
                message, keyword, page,
                (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE,
                results, cloud_types
            )
            
            # 编辑或发送消息
            async for result in MessageEditor.edit_or_send(event, final_message, keyboard):
                yield result
                
        except Exception as e:
            logger.error(f"[Pansou] 处理翻页回调异常: {e}")
            yield event.plain_result("❌ 翻页失败，请重试")
    
    async def _handle_douban_search_callback(self, event: AstrMessageEvent, data: Dict):
        """处理豆瓣搜索回调"""
        try:
            douban_type = data.get('type', '')
            douban_id = data.get('id', '')
            title = data.get('title', '')
            
            logger.info(f"[Pansou] 豆瓣搜索回调: type={douban_type}, id={douban_id}, title={title}")
            
            if not title:
                yield event.plain_result("❌ 缺少标题信息")
                return
            
            # 设置回调响应（飞书卡片更新）
            try:
                if hasattr(event.message_obj, 'set_callback_response'):
                    event.message_obj.set_callback_response({
                        "status": "success",
                        "toast": {
                            "type": "success",
                            "content": f"正在搜索 {title}"
                        }
                    })
            except Exception as e:
                logger.debug(f"[Pansou] 设置回调响应失败: {e}")
            
            # 执行搜索
            logger.info(f"[Pansou] 开始搜索豆瓣资源: {title}")
            async for result in self._handle_command(event, title):
                yield result
                
        except Exception as e:
            logger.error(f"[Pansou] 处理豆瓣搜索失败: {e}", exc_info=True)
            yield event.plain_result("❌ 搜索失败，请稍后重试")
    
    async def _get_douban_title_by_id(self, douban_type: str, douban_id: str) -> str:
        """
        通过豆瓣 ID 获取标题
        
        优先级：
        1. 从全局缓存获取（豆瓣插件缓存的详情）
        2. 从豆瓣移动端 API 获取（不需要 cookies）
        3. 从豆瓣网页获取（需要 cookies）
        
        Args:
            douban_type: 豆瓣类型（movie/book）
            douban_id: 豆瓣 ID
            
        Returns:
            标题，失败返回空字符串
        """
        import aiohttp
        
        # 1. 尝试从全局缓存获取
        try:
            from common.cache_manager import get_global_cache
            cache = get_global_cache()
            if cache is not None:
                cache_key = f"douban_detail_{douban_type}_{douban_id}"
                cached_data = cache.get(cache_key)
                if cached_data and isinstance(cached_data, dict):
                    title = cached_data.get('title', '')
                    if title:
                        logger.info(f"[Pansou] 从缓存获取豆瓣标题: {title}")
                        return title
        except Exception as e:
            logger.debug(f"[Pansou] 缓存获取失败: {e}")
        
        # 2. 尝试从豆瓣移动端 API 获取（通过评论接口可以获取标题）
        try:
            api_url = f"https://m.douban.com/rexxar/api/v2/{douban_type}/{douban_id}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15',
                'Referer': f'https://m.douban.com/{douban_type}/subject/{douban_id}/'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()
                        title = data.get('title', '')
                        if title:
                            logger.info(f"[Pansou] 从豆瓣API获取标题成功: {title}")
                            return title
                    else:
                        logger.debug(f"[Pansou] 豆瓣API返回: {response.status}")
        except Exception as e:
            logger.debug(f"[Pansou] 豆瓣API获取失败: {e}")
        
        # 3. 尝试从豆瓣网页获取（使用用户 cookies）
        try:
            if douban_type == "movie":
                url = f"https://movie.douban.com/subject/{douban_id}/"
            elif douban_type == "book":
                url = f"https://book.douban.com/subject/{douban_id}/"
            else:
                logger.error(f"[Pansou] 不支持的豆瓣类型: {douban_type}")
                return ""
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        logger.error(f"[Pansou] 获取豆瓣页面失败: {response.status}")
                        return ""
                    
                    html = await response.text()
                    
                    # 从 HTML 中提取标题
                    import re
                    match = re.search(r'<span property="v:itemreviewed">([^<]+)</span>', html)
                    
                    if match:
                        title = match.group(1).strip()
                        logger.info(f"[Pansou] 从豆瓣网页获取标题成功: {title}")
                        return title
                    else:
                        logger.error(f"[Pansou] 无法从 HTML 中提取标题")
                        return ""
                        
        except Exception as e:
            logger.error(f"[Pansou] 获取豆瓣标题失败: {e}")
            return ""
