"""
统一订阅系统插件

功能：
1. /订阅 - 订阅管理主菜单
2. 榜单订阅 - 订阅热搜榜单推送
3. 关键词订阅 - 订阅特定关键词
4. 推送时间设置 - 自定义推送时间
5. 订阅管理 - 查看、修改、取消订阅

支持跨平台交互（按钮模式/会话模式）
"""
import os
from pathlib import Path
from typing import Optional, Dict, Any, List

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from astrbot.core.message.components import Plain
from astrbot.core import CallbackRouter, callback_handler, auto_stop_event

# 导入通用模块
import sys
plugin_root = Path(__file__).parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

try:
    from common import (
        DatabaseManager,
        get_platform_capabilities,
        MessageEditor,
        get_session_manager,
        auto_stop_command,
        get_unified_user_id,
        get_search_statistics,
        get_message_pusher,
        init_message_pusher,
        get_scheduler,
        init_subscription_privileges,
        get_subscription_privilege_manager,
        # 预抓取和推送调度
        init_prefetcher,
        get_prefetcher,
        init_push_scheduler,
        get_push_scheduler,
        # 推送格式化
        init_push_formatter,
        get_push_formatter
    )
    from common.subscription_manager import (
        SubscriptionManager,
        get_subscription_manager,
        SubscriptionType,
        PushFrequency,
        Subscription
    )
    from common.subscription_source import (
        SourceManager,
        get_source_manager,
        init_source_manager,
        SubscriptionSource,
        SourceContent,
        SourceType,
        SourceStatus,
        AccessLevel,
        InternalAdapter,
        PUSH_CONTENT_MODE_NAMES
    )
    from common.quota_validator import QuotaValidator, get_quota_validator
    SYSTEM_AVAILABLE = True
except ImportError as e:
    SYSTEM_AVAILABLE = False
    logger.error(f"[Subscription] 通用模块不可用: {e}")
    def get_unified_user_id(event):
        return event.get_sender_id()

from .handlers import SubscriptionResponseBuilder, SubscriptionSessionHandler, SourceAdminHandler


@register("subscription", "AstrBot Team", "统一订阅系统 - 支持跨平台交互", "1.0.0")
class SubscriptionPlugin(Star):
    """统一订阅系统插件"""
    
    # 支持的插件列表
    SUPPORTED_PLUGINS = ['music', 'book', 'douban', 'pansou']
    
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context, config)
        self.context = context
        self.plugin_config = config or {}
        
        # 加载配置
        self._load_plugin_config()
        
        # 初始化系统
        self.db = None
        self.subscription_manager = None
        self.source_manager = None
        self.source_admin_handler = None
        self.search_stats = None
        self.message_pusher = None
        self.scheduler = None
        self.session_manager = None
        self.session_handler = None
        self.quota_validator = None
        self.privilege_manager = None
        # 新增：预抓取和推送调度
        self.prefetcher = None
        self.push_scheduler = None
        self.push_formatter = None
        self.system_available = SYSTEM_AVAILABLE
        
        if self.system_available:
            try:
                # 获取数据路径
                astrbot_config = self.context.get_config()
                data_path = astrbot_config.get("data_path", "data")
                db_path = os.path.join(data_path, "quota_system.db")
                
                # 初始化数据库
                self.db = DatabaseManager(db_path)
                
                # 初始化订阅管理器
                self.subscription_manager = get_subscription_manager(self.db)
                
                # 初始化订阅源管理器
                self.source_manager = init_source_manager(self.db)
                
                # 设置内部适配器的搜索统计
                self.search_stats = get_search_statistics(self.db)
                internal_adapter = InternalAdapter(self.search_stats)
                self.source_manager.register_adapter(SourceType.INTERNAL, internal_adapter)
                
                # 初始化消息推送器
                self.message_pusher = init_message_pusher(self.db, context)
                
                # 初始化调度器
                self.scheduler = get_scheduler(self.db)
                self.scheduler.set_context(context)
                
                # 初始化配额验证器和权益管理器
                self.quota_validator = get_quota_validator(self.db)
                self.privilege_manager = init_subscription_privileges(self.quota_validator)
                
                # 初始化会话管理器
                session_timeout = self.plugin_config.get('session_timeout', 2)
                self.session_manager = get_session_manager(timeout_minutes=session_timeout)
                
                # 注册回调路由
                CallbackRouter.register("subscription", self.handle_callback, plugin_instance=self)
                logger.info("[Subscription] 已注册回调路由: subscription")
                
                # 初始化会话处理器
                self.session_handler = SubscriptionSessionHandler(
                    plugin=self,
                    subscription_manager=self.subscription_manager,
                    session_manager=self.session_manager
                )
                
                # 初始化订阅源管理处理器
                self.source_admin_handler = SourceAdminHandler(self.source_manager)
                
                # 初始化推送格式化器（整合AI摘要功能）
                self.push_formatter = init_push_formatter(context)
                
                # 初始化内容预抓取器
                self.prefetcher = init_prefetcher(
                    source_manager=self.source_manager,
                    cache_manager=None,  # 使用内置缓存
                    subscription_manager=self.subscription_manager
                )
                
                # 初始化智能推送调度器
                self.push_scheduler = init_push_scheduler(
                    prefetcher=self.prefetcher,
                    subscription_manager=self.subscription_manager,
                    push_handler=self._smart_push_handler
                )
                
                # 注册定时推送任务
                self._register_push_tasks()
                
                # 重新加载API适配器配置（支持热更新）
                try:
                    from common.subscription_source import APIAdapter
                    APIAdapter.reload_presets()
                except Exception as e:
                    logger.debug(f"[Subscription] 重载API配置失败: {e}")
                
                # 初始化默认订阅源
                self._init_default_sources()
                
                # 启动预抓取和推送调度（异步）
                import asyncio
                asyncio.create_task(self._start_smart_scheduler())
                
                logger.info("[Subscription] 订阅系统插件初始化完成（含智能调度）")
                
            except Exception as e:
                logger.error(f"[Subscription] 初始化失败: {e}", exc_info=True)
                self.system_available = False
        else:
            logger.warning("[Subscription] 订阅系统不可用")
    
    def _load_plugin_config(self):
        """加载插件配置"""
        defaults = {
            'session_timeout': 2,           # 会话超时（分钟）
            'max_subscriptions_per_user': 20,  # 每用户最大订阅数
            'default_push_time': '19:00',   # 默认推送时间
            'push_check_interval': 60,      # 推送检查间隔（秒）
            'push_batch_size': 50,          # 批量推送大小
            'push_concurrency': 10,         # 推送并发数
            # 智能调度配置
            'prefetch_enabled': True,       # 启用预抓取
            'prefetch_max_concurrent': 3,   # 预抓取最大并发
            'prefetch_interval_min': 300,   # 预抓取最小间隔（秒）
            'push_spread_window': 600,      # 错峰推送窗口（秒）
        }
        for key, default in defaults.items():
            if key not in self.plugin_config:
                self.plugin_config[key] = default
    
    def _register_push_tasks(self):
        """注册定时推送任务"""
        if not self.scheduler:
            return
        
        # 每分钟检查到期订阅
        self.scheduler.register_task(
            task_id="subscription:check_due",
            plugin_name="subscription",
            interval_seconds=self.plugin_config.get('push_check_interval', 60),
            handler=self._process_due_subscriptions,
            description="检查到期订阅并推送"
        )
        
        # 每分钟处理重试队列
        self.scheduler.register_task(
            task_id="subscription:process_retries",
            plugin_name="subscription",
            interval_seconds=60,
            handler=self._process_retry_queue,
            description="处理推送重试队列"
        )
        
        # 每天凌晨清理旧日志
        self.scheduler.register_task(
            task_id="subscription:cleanup",
            plugin_name="subscription",
            cron="0 3 * * *",
            handler=self._cleanup_old_logs,
            description="清理旧推送日志"
        )
        
        logger.info("[Subscription] 定时任务注册完成")
    
    # 插件中文名称映射
    PLUGIN_DISPLAY_NAMES = {
        'music': '音乐',
        'book': '书籍',
        'douban': '豆瓣',
        'pansou': '资源'
    }
    
    def _init_default_sources(self):
        """初始化默认订阅源"""
        if not self.source_manager:
            return
        
        # 检查是否已有订阅源
        existing_sources = self.source_manager.get_all_sources()
        if existing_sources:
            # 检查是否需要更新（如果第一个源没有 display_name，则需要重建）
            first_source = existing_sources[0]
            if first_source.display_name:
                logger.info(f"[Subscription] 已有 {len(existing_sources)} 个订阅源")
                return
            else:
                # 删除旧数据，重新创建
                logger.info("[Subscription] 检测到旧订阅源数据，正在更新...")
                for source in existing_sources:
                    self.source_manager.delete_source(source.id)
        
        # 创建内部榜单订阅源
        for plugin_name in self.SUPPORTED_PLUGINS:
            display_name = self.PLUGIN_DISPLAY_NAMES.get(plugin_name, plugin_name)
            
            # 热搜榜单
            hot_source = SubscriptionSource(
                name=f"{plugin_name}_hot",
                display_name=f"{display_name}热搜榜",
                source_type=SourceType.INTERNAL,
                category="榜单",
                description=f"每日{display_name}热门搜索排行",
                icon="🔥",
                parser_config={
                    'ranking_type': 'hot',
                    'plugin_name': plugin_name,
                    'limit': 10
                },
                access_level=AccessLevel.PUBLIC,
                update_interval=3600
            )
            self.source_manager.create_source(hot_source)
            
            # 飙升榜
            rising_source = SubscriptionSource(
                name=f"{plugin_name}_rising",
                display_name=f"{display_name}飙升榜",
                source_type=SourceType.INTERNAL,
                category="榜单",
                description=f"{display_name}热度飙升内容",
                icon="📈",
                parser_config={
                    'ranking_type': 'rising',
                    'plugin_name': plugin_name,
                    'limit': 10
                },
                access_level=AccessLevel.PUBLIC,
                update_interval=3600
            )
            self.source_manager.create_source(rising_source)
            
            # 新上榜
            new_source = SubscriptionSource(
                name=f"{plugin_name}_new",
                display_name=f"{display_name}新上榜",
                source_type=SourceType.INTERNAL,
                category="榜单",
                description=f"新进入{display_name}榜单的内容",
                icon="🆕",
                parser_config={
                    'ranking_type': 'new_entry',
                    'plugin_name': plugin_name,
                    'limit': 10
                },
                access_level=AccessLevel.PUBLIC,
                update_interval=3600
            )
            self.source_manager.create_source(new_source)
        
        logger.info(f"[Subscription] 初始化了 {len(self.SUPPORTED_PLUGINS) * 3} 个内部订阅源")
    
    async def _process_due_subscriptions(self, context):
        """处理到期订阅"""
        if not self.subscription_manager:
            return
        
        try:
            # 获取到期订阅
            due_subs = self.subscription_manager.get_due_subscriptions(buffer_minutes=1)
            
            if not due_subs:
                return
            
            logger.info(f"[Subscription] 处理 {len(due_subs)} 个到期订阅")
            
            # 按用户优先级排序（VIP优先）
            if self.privilege_manager:
                due_subs.sort(
                    key=lambda s: self.privilege_manager.get_push_priority(s.user_id),
                    reverse=True
                )
            
            # P1优化：并发控制
            import asyncio
            semaphore = asyncio.Semaphore(self.plugin_config.get('push_concurrency', 10))
            
            async def process_single_sub(sub):
                async with semaphore:
                    await self._push_single_subscription(sub, context)
            
            # 并发处理所有订阅
            await asyncio.gather(*[process_single_sub(sub) for sub in due_subs], return_exceptions=True)
                    
        except Exception as e:
            logger.error(f"[Subscription] 处理到期订阅失败: {e}")
    
    async def _push_single_subscription(self, sub, context):
        """处理单个订阅的推送"""
        try:
            # 生成推送内容
            content, content_hash = await self._generate_push_content_with_hash(sub)
            
            if not content:
                # 无内容，跳过但更新下次推送时间
                self.subscription_manager.mark_pushed(sub.id, success=True)
                return
            
            # P0优化：内容去重检查
            source_id = int(sub.target) if sub.subscription_type == SubscriptionType.SOURCE else 0
            if content_hash and source_id:
                if self.subscription_manager.is_content_pushed(sub.user_id, source_id, content_hash):
                    logger.debug(f"[Subscription] 内容已推送过，跳过: sub={sub.id}, hash={content_hash[:8]}")
                    self.subscription_manager.mark_pushed(sub.id, success=True)
                    return
            
            # 根据会员等级添加广告
            if self.privilege_manager:
                content = self.privilege_manager.format_ad_message(content, sub.user_id)
            
            # 发送推送
            success = await self.message_pusher.send_private_message(
                user_id=sub.user_id,
                message=content,
                context=context,
                max_retries=1  # 首次只重试1次，失败后进入重试队列
            )
            
            if success:
                # 标记已推送
                self.subscription_manager.mark_pushed(sub.id, success=True)
                # P0优化：记录内容哈希，防止重复推送
                if content_hash and source_id:
                    self.subscription_manager.mark_content_pushed(sub.user_id, source_id, content_hash)
            else:
                # P0优化：推送失败，加入重试队列
                self.subscription_manager.add_to_retry_queue(
                    subscription_id=sub.id,
                    user_id=sub.user_id,
                    content=content,
                    error="首次推送失败"
                )
                self.subscription_manager.mark_pushed(sub.id, success=False, error_message="已加入重试队列")
                
        except Exception as e:
            logger.error(f"[Subscription] 处理订阅 {sub.id} 失败: {e}")
            self.subscription_manager.mark_pushed(sub.id, success=False, error_message=str(e))
    
    async def _process_retry_queue(self, context):
        """处理推送重试队列"""
        if not self.subscription_manager or not self.message_pusher:
            return
        
        try:
            # 获取待重试的推送
            pending_retries = self.subscription_manager.get_pending_retries(limit=50)
            
            if not pending_retries:
                return
            
            logger.info(f"[Subscription] 处理 {len(pending_retries)} 个待重试推送")
            
            for retry in pending_retries:
                try:
                    # 发送推送
                    success = await self.message_pusher.send_private_message(
                        user_id=retry['user_id'],
                        message=retry['content'],
                        context=context,
                        max_retries=1
                    )
                    
                    # 更新重试状态
                    self.subscription_manager.update_retry_status(
                        retry_id=retry['id'],
                        success=success,
                        error="重试发送失败" if not success else None
                    )
                    
                except Exception as e:
                    logger.error(f"[Subscription] 重试推送 {retry['id']} 失败: {e}")
                    self.subscription_manager.update_retry_status(
                        retry_id=retry['id'],
                        success=False,
                        error=str(e)
                    )
                    
        except Exception as e:
            logger.error(f"[Subscription] 处理重试队列失败: {e}")
    
    async def _generate_push_content(self, sub: Subscription) -> Optional[str]:
        """生成推送内容"""
        content, _ = await self._generate_push_content_with_hash(sub)
        return content
    
    async def _generate_push_content_with_hash(self, sub: Subscription) -> tuple[Optional[str], Optional[str]]:
        """
        生成推送内容及其哈希值
        
        Returns:
            (内容, 内容哈希) - 用于去重
        """
        import hashlib
        
        try:
            content = None
            if sub.subscription_type == SubscriptionType.RANKING:
                content = await self._generate_ranking_content(sub)
            elif sub.subscription_type == SubscriptionType.KEYWORD:
                content = await self._generate_keyword_content(sub)
            elif sub.subscription_type == SubscriptionType.NEW_ENTRY:
                content = await self._generate_new_entry_content(sub)
            elif sub.subscription_type == SubscriptionType.RISING:
                content = await self._generate_rising_content(sub)
            elif sub.subscription_type == SubscriptionType.SOURCE:
                content = await self._generate_source_content(sub)
            
            # 计算内容哈希
            content_hash = None
            if content:
                content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            
            return content, content_hash
            
        except Exception as e:
            logger.error(f"[Subscription] 生成推送内容失败: {e}")
            return None, None
    
    async def _generate_ranking_content(self, sub: Subscription) -> Optional[str]:
        """生成榜单推送内容"""
        if not self.search_stats:
            return None
        
        # 获取带排名变化的榜单
        content = self.search_stats.format_ranking_with_changes(
            plugin_name=sub.plugin_name,
            current_days=1,
            compare_days=1,
            limit=10
        )
        
        return f"📬 您订阅的榜单更新了\n\n{content}"
    
    async def _generate_keyword_content(self, sub: Subscription) -> Optional[str]:
        """生成关键词推送内容"""
        if not self.search_stats:
            return None
        
        # 检查关键词是否在榜单中
        ranking = self.search_stats.get_ranking_with_changes(
            plugin_name=sub.plugin_name,
            current_days=1,
            limit=50
        )
        
        keyword = sub.target
        for item in ranking:
            if item['keyword'] == keyword:
                rank = item['rank']
                change = item['rank_change']
                is_new = item['is_new']
                
                if is_new:
                    return f"🔔 关键词提醒\n\n您关注的「{keyword}」新上榜了！\n当前排名: 第{rank}名 🆕"
                elif change and change > 0:
                    return f"🔔 关键词提醒\n\n您关注的「{keyword}」排名上升了！\n当前排名: 第{rank}名 (↑{change})"
                elif sub.config.get('notify_on_ranking', False):
                    return f"🔔 关键词提醒\n\n您关注的「{keyword}」在榜单中\n当前排名: 第{rank}名"
        
        return None  # 关键词不在榜单中，不推送
    
    async def _generate_new_entry_content(self, sub: Subscription) -> Optional[str]:
        """生成新上榜推送内容"""
        if not self.search_stats:
            return None
        
        min_searches = sub.config.get('min_searches', 3)
        new_entries = self.search_stats.get_new_entries(
            plugin_name=sub.plugin_name,
            hours=24,
            limit=10,
            min_searches=min_searches
        )
        
        if not new_entries:
            return None
        
        content = self.search_stats.format_new_entries(
            plugin_name=sub.plugin_name,
            hours=24,
            limit=10
        )
        
        return f"📬 新上榜提醒\n\n{content}"
    
    async def _generate_rising_content(self, sub: Subscription) -> Optional[str]:
        """生成飙升榜推送内容"""
        if not self.search_stats:
            return None
        
        min_growth = sub.config.get('min_growth_rate', 50.0)
        rising = self.search_stats.get_rising_searches(
            plugin_name=sub.plugin_name,
            current_hours=24,
            compare_hours=24,
            limit=10
        )
        
        # 过滤低增长率的
        rising = [r for r in rising if r['growth_rate'] >= min_growth]
        
        if not rising:
            return None
        
        content = self.search_stats.format_rising_searches(
            plugin_name=sub.plugin_name,
            limit=10
        )
        
        return f"📬 飙升榜提醒\n\n{content}"
    
    async def _generate_source_content(self, sub: Subscription) -> Optional[str]:
        """生成订阅源推送内容"""
        if not self.source_manager:
            return None
        
        # 获取订阅源ID（从 target 或 config 获取）
        source_id = None
        if sub.target and sub.target.isdigit():
            source_id = int(sub.target)
        elif sub.config:
            source_id = sub.config.get('source_id')
        
        if not source_id:
            return None
        
        source = self.source_manager.get_source(source_id)
        if not source or source.status != SourceStatus.ACTIVE:
            return None
        
        try:
            contents = None
            
            # 优先使用预抓取的缓存内容
            if self.prefetcher:
                cached = await self.prefetcher.get_content(
                    source_id, 
                    max_age=3600,  # 1小时内的缓存
                    wait_for_fetch=False  # 不等待抓取
                )
                if cached and cached.items:
                    contents = cached.items
            
            # 降级：直接抓取
            if not contents:
                result, _ = await self.source_manager.fetch_source_content(source_id)
                contents = result
            
            if not contents:
                return None
            
            # 使用推送格式化器（支持多种推送模式）
            if self.push_formatter:
                # 将内容转换为字典列表
                items = []
                for item in contents:
                    if hasattr(item, '__dict__'):
                        items.append({
                            'title': getattr(item, 'title', ''),
                            'content': getattr(item, 'content', ''),
                            'url': getattr(item, 'url', ''),
                            'published_at': getattr(item, 'published_at', None)
                        })
                    elif isinstance(item, dict):
                        items.append(item)
                
                formatted = await self.push_formatter.format_push_content(
                    source=source,
                    items=items
                )
                # 设置反馈所需的元数据
                formatted.source_id = source.id if source else 0
                import hashlib
                formatted.content_hash = hashlib.md5(formatted.to_message().encode('utf-8')).hexdigest()
                return formatted.to_message_with_feedback()
            
            # 降级：使用旧的格式化逻辑
            display_title = source.get_display_title()
            
            if source.push_template:
                # 使用自定义模板
                message = source.push_template
                content = contents[0]
                if hasattr(content, 'title'):
                    message = message.replace('{title}', content.title)
                    message = message.replace('{content}', content.content)
                    message = message.replace('{url}', content.url)
                else:
                    message = message.replace('{title}', content.get('title', ''))
                    message = message.replace('{content}', content.get('content', ''))
                    message = message.replace('{url}', content.get('url', ''))
            else:
                # 默认格式
                content = contents[0]
                message = f"📬 {source.icon} {display_title}\n\n"
                title = content.title if hasattr(content, 'title') else content.get('title', '')
                body = content.content if hasattr(content, 'content') else content.get('content', '')
                url = content.url if hasattr(content, 'url') else content.get('url', '')
                
                if title:
                    message += f"📰 {title}\n\n"
                message += body
                if url:
                    message += f"\n\n🔗 {url}"
            
            return message
            
        except Exception as e:
            logger.error(f"[Subscription] 获取订阅源 {source.name} 内容失败: {e}")
            return None
    
    async def _cleanup_old_logs(self, context):
        """清理旧日志和历史记录"""
        if self.subscription_manager:
            self.subscription_manager.cleanup_old_logs(days=30)
            # P0优化：清理内容推送历史（保留7天用于去重）
            self.subscription_manager.cleanup_old_content_history(days=7)
            # P0优化：清理旧的重试记录
            self.subscription_manager.cleanup_old_retries(days=7)
        # P1优化：清理过期的内容缓存
        if self.source_manager:
            self.source_manager.cleanup_content_cache()
        if self.message_pusher:
            self.message_pusher.cleanup_old_logs(days=30)
    
    # ==================== 智能调度系统 ====================
    
    async def _start_smart_scheduler(self):
        """启动智能调度系统"""
        try:
            # 启动预抓取器
            if self.prefetcher:
                await self.prefetcher.start()
                logger.info("[Subscription] 内容预抓取器已启动")
            
            # 启动推送调度器
            if self.push_scheduler:
                await self.push_scheduler.start()
                logger.info("[Subscription] 智能推送调度器已启动")
                
        except Exception as e:
            logger.error(f"[Subscription] 启动智能调度失败: {e}")
    
    async def _smart_push_handler(
        self, 
        user_id: str, 
        source_id: int, 
        subscription_id: int,
        content: list
    ) -> bool:
        """
        智能推送处理器（由 PushScheduler 调用）
        
        统一处理两种订阅类型：
        1. 订阅源订阅（source_id < 100000）：使用预抓取内容
        2. 普通订阅（source_id >= 100000）：实时获取内容
        
        Args:
            user_id: 用户ID
            source_id: 订阅源ID（可能是虚拟ID）
            subscription_id: 订阅ID
            content: 预抓取的内容列表（可能为None）
            
        Returns:
            是否推送成功
        """
        try:
            # 获取订阅信息
            subscription = self.subscription_manager.get_subscription(subscription_id)
            if not subscription:
                logger.warning(f"[Subscription] 订阅 {subscription_id} 不存在")
                return False
            
            # 判断是否是订阅源订阅
            is_source_subscription = subscription.source_id and subscription.source_id > 0
            
            # 获取订阅源（仅订阅源订阅有效）
            source = None
            if is_source_subscription:
                source = self.source_manager.get_source(subscription.source_id)
                if not source:
                    logger.warning(f"[Subscription] 订阅源 {subscription.source_id} 不存在")
                    # 更新下次推送时间，避免重复查询（订阅源可能被删除）
                    self.subscription_manager.mark_pushed(subscription_id, success=False, error_message="订阅源不存在")
                    return False
            
            # 如果没有预抓取内容，尝试获取
            if not content:
                if is_source_subscription and self.source_manager:
                    # 订阅源订阅：从订阅源获取内容
                    result = await self.source_manager.fetch_source_content(subscription.source_id)
                    if isinstance(result, tuple):
                        content, _ = result
                    else:
                        content = result
                else:
                    # 普通订阅：根据插件类型获取内容
                    content = await self._fetch_subscription_content(subscription)
                
                if not content:
                    logger.debug(f"[Subscription] 订阅 {subscription_id} 无新内容")
                    # 更新下次推送时间，避免重复查询
                    self.subscription_manager.mark_pushed(subscription_id, success=True)
                    return True  # 无内容视为成功
            
            # 使用推送格式化器格式化内容
            if self.push_formatter and content and source:
                # 将内容转换为字典列表
                items = []
                for item in content:
                    if hasattr(item, '__dict__'):
                        items.append({
                            'title': getattr(item, 'title', ''),
                            'content': getattr(item, 'content', ''),
                            'url': getattr(item, 'url', ''),
                            'published_at': getattr(item, 'published_at', None)
                        })
                    elif isinstance(item, dict):
                        items.append(item)
                
                # 格式化推送内容
                formatted = await self.push_formatter.format_push_content(
                    source=source,
                    items=items
                )
                # 设置反馈所需的元数据
                formatted.source_id = source.id if source else 0
                import hashlib
                formatted.content_hash = hashlib.md5(formatted.to_message().encode('utf-8')).hexdigest()
                message = formatted.to_message_with_feedback()
            elif content:
                # 降级：使用简单格式（支持 source 为 None）
                message = self._format_simple_content(source, content)
            else:
                # 无内容
                message = ""
            
            if not message:
                # 更新下次推送时间，避免重复查询
                self.subscription_manager.mark_pushed(subscription_id, success=True)
                return True  # 无内容，视为成功
            
            # 内容去重检查
            import hashlib
            content_hash = hashlib.md5(message.encode('utf-8')).hexdigest()
            
            if self.subscription_manager.is_content_pushed(user_id, source_id, content_hash):
                logger.debug(f"[Subscription] 内容已推送过，跳过: user={user_id}, source={source_id}")
                # 更新下次推送时间，避免重复查询
                self.subscription_manager.mark_pushed(subscription_id, success=True)
                return True
            
            # 根据会员等级添加广告
            if self.privilege_manager:
                message = self.privilege_manager.format_ad_message(message, user_id)
            
            # 发送推送
            success = await self.message_pusher.send_private_message(
                user_id=user_id,
                message=message,
                context=self.context,
                max_retries=1
            )
            
            if success:
                # 记录已推送
                self.subscription_manager.mark_content_pushed(user_id, source_id, content_hash)
                # 更新订阅状态
                self.subscription_manager.mark_pushed(subscription_id, success=True)
                logger.debug(f"[Subscription] 智能推送成功: user={user_id}, source={source_id}")
            else:
                # 推送失败也要更新下次推送时间，避免重复尝试
                self.subscription_manager.mark_pushed(subscription_id, success=False, error_message="推送失败")
                logger.warning(f"[Subscription] 推送失败: user={user_id}, source={source_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"[Subscription] 智能推送失败: {e}")
            # 异常时也要更新下次推送时间，避免重复尝试
            try:
                self.subscription_manager.mark_pushed(subscription_id, success=False, error_message=str(e))
            except:
                pass
            return False
    
    async def _fetch_subscription_content(self, subscription) -> list:
        """
        根据订阅类型获取内容
        
        Args:
            subscription: 订阅对象
            
        Returns:
            内容列表
        """
        try:
            plugin_name = subscription.plugin_name
            target = subscription.target
            sub_type = subscription.subscription_type
            
            logger.info(f"[Subscription] 获取订阅内容: plugin={plugin_name}, target={target}, type={sub_type}")
            
            # 根据插件类型获取内容
            if plugin_name == "douban":
                # 豆瓣榜单
                return await self._fetch_douban_content(target)
            elif plugin_name == "music":
                # 音乐榜单
                return await self._fetch_music_content(target)
            elif plugin_name == "book":
                # 书籍榜单
                return await self._fetch_book_content(target)
            elif plugin_name == "pansou":
                # 资源搜索（关键词订阅）
                return await self._fetch_pansou_content(target)
            else:
                logger.warning(f"[Subscription] 未知的插件类型: {plugin_name}")
                return []
                
        except Exception as e:
            logger.error(f"[Subscription] 获取订阅内容失败: {e}")
            return []
    
    async def _fetch_douban_content(self, target: str) -> list:
        """获取豆瓣内容"""
        # TODO: 调用豆瓣插件获取榜单内容
        return []
    
    async def _fetch_music_content(self, target: str) -> list:
        """获取音乐内容"""
        # TODO: 调用音乐插件获取榜单内容
        return []
    
    async def _fetch_book_content(self, target: str) -> list:
        """获取书籍内容"""
        # TODO: 调用书籍插件获取榜单内容
        return []
    
    async def _fetch_pansou_content(self, target: str) -> list:
        """获取资源搜索内容"""
        # TODO: 调用资源搜索插件获取内容
        return []
    
    def _format_simple_content(self, source, content: list) -> str:
        """简单格式化内容（降级方案）"""
        if not content:
            return ""
        
        if source:
            display_title = source.get_display_title()
            message = f"📬 {source.icon} {display_title}\n\n"
        else:
            message = "📬 订阅更新\n\n"
        
        for i, item in enumerate(content[:5], 1):
            if hasattr(item, 'title'):
                title = item.title
            elif isinstance(item, dict):
                title = item.get('title', '')
            else:
                title = str(item)
            
            if title:
                message += f"{i}. {title}\n"
        
        return message.strip()
    
    async def get_prefetch_stats(self) -> dict:
        """获取预抓取统计信息"""
        stats = {
            'prefetcher': None,
            'push_scheduler': None
        }
        
        if self.prefetcher:
            stats['prefetcher'] = self.prefetcher.get_stats()
        
        if self.push_scheduler:
            stats['push_scheduler'] = self.push_scheduler.get_stats()
        
        return stats
    
    # ==================== 命令处理 ====================
    
    @filter.command("订")
    @auto_stop_command
    async def subscription_cmd(self, event: AstrMessageEvent):
        """订阅管理命令"""
        if not self.system_available:
            yield event.plain_result("❌ 订阅系统不可用")
            return
        
        user_id = get_unified_user_id(event)
        
        # 获取平台能力
        capabilities = get_platform_capabilities(event, "Subscription")
        
        # 获取用户订阅
        subscriptions = self.subscription_manager.get_user_subscriptions(user_id)
        
        # 获取用户权益信息
        max_subscriptions = 3
        user_level = "免费用户"
        user_access_level = 0
        if self.privilege_manager:
            max_subscriptions = self.privilege_manager.get_max_subscriptions(user_id)
            privileges = self.privilege_manager.get_user_privileges(user_id)
            # 根据权益获取用户等级名称
            if privileges.get('priority_push'):
                user_level = "超级会员"
                user_access_level = 3
            elif not privileges.get('ad_enabled'):
                user_level = "高级会员"
                user_access_level = 2
            else:
                user_level = "免费用户"
                user_access_level = 0
        
        # 获取可用订阅源（根据用户等级）
        available_sources = []
        hot_sources = []
        if self.source_manager:
            available_sources = self.source_manager.get_available_sources(user_access_level)
            # 获取热门订阅源（按订阅人数排序，取前3个）
            hot_sources = sorted(
                [s for s in available_sources if s.current_subscribers > 0],
                key=lambda s: s.current_subscribers,
                reverse=True
            )[:3]
            # 如果没有热门，取前3个可用的
            if not hot_sources and available_sources:
                hot_sources = available_sources[:3]
        
        # 构建并发送主菜单（不创建会话）
        builder = SubscriptionResponseBuilder(capabilities)
        message, keyboard = builder.build_main_menu(
            subscriptions, available_sources, 
            max_subscriptions=max_subscriptions,
            user_level=user_level,
            hot_sources=hot_sources
        )
        
        # 如果支持按钮，直接发送（按钮模式不需要会话）
        if capabilities.get('supports_buttons'):
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        else:
            # 会话模式：创建会话后发送
            session_id = event.get_session_id()
            self.session_manager.create_session(
                session_id=session_id,
                session_type='subscription_menu',
                user_id=user_id,
                capabilities=capabilities
            )
            self.session_manager.update_session(session_id, step=self.session_handler.Step.MAIN_MENU)
            
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
    
    @filter.command("callback")
    @callback_handler("subscription")
    @auto_stop_event
    async def handle_callback(self, event: AstrMessageEvent, data: str = ""):
        """处理回调"""
        # 检查是否是订阅回调（callback_handler 已经过滤了前缀）
        if not data:
            return
        
        if not self.system_available:
            yield event.plain_result("❌ 订阅系统不可用")
            return
        
        # 确保有会话（按钮模式可能没有会话）
        session_id = event.get_session_id()
        session = self.session_manager.get_session(session_id)
        
        if not session:
            # 创建临时会话处理回调
            user_id = get_unified_user_id(event)
            capabilities = get_platform_capabilities(event, "Subscription")
            
            self.session_manager.create_session(
                session_id=session_id,
                session_type='subscription_menu',
                user_id=user_id,
                capabilities=capabilities
            )
        
        # 去掉前缀（callback_handler 只做过滤，不去前缀）
        if data.startswith("subscription:"):
            data = data[len("subscription:"):]
        
        # 解析回调数据
        parts = data.split(":")
        action = parts[0] if parts else ""
        
        # 管理员功能路由
        if action == "admin" and self.source_admin_handler:
            admin_action = parts[1] if len(parts) > 1 else ""
            admin_params = parts[2:] if len(parts) > 2 else []
            
            # 获取平台能力
            session = self.session_manager.get_session(session_id)
            capabilities = session.get('capabilities') if session else get_platform_capabilities(event, "Subscription")
            
            async for result in self.source_admin_handler.handle_callback(
                event, admin_action, admin_params, capabilities,
                subscription_manager=self.subscription_manager
            ):
                yield result
            return
        
        # 用户反馈处理
        if action == "feedback":
            async for result in self._handle_feedback_callback(event, parts[1:]):
                yield result
            return
        
        # 普通用户功能
        async for result in self.session_handler.handle_callback(event, data):
            yield result
    
    async def _handle_feedback_callback(self, event: AstrMessageEvent, params: list):
        """
        处理用户反馈回调
        
        格式: subscription:feedback:{source_id}:{type}:{content_hash}
        """
        try:
            if len(params) < 2:
                yield event.plain_result("❌ 反馈参数错误")
                return
            
            source_id = int(params[0])
            feedback_type = params[1]  # useful/useless
            content_hash = params[2] if len(params) > 2 else None
            
            user_id = get_unified_user_id(event)
            
            # 提交反馈
            success = self.subscription_manager.submit_feedback(
                user_id=user_id,
                source_id=source_id,
                feedback_type=feedback_type,
                content_hash=content_hash
            )
            
            if success:
                if feedback_type == 'useful':
                    yield event.plain_result("👍 感谢反馈！我们会推送更多类似内容")
                else:
                    yield event.plain_result("👎 收到反馈！我们会优化推送内容")
                    
                    # 检查是否需要降低推送频率
                    if self.subscription_manager.should_reduce_push_frequency(user_id, source_id):
                        yield event.plain_result("💡 检测到您对此源多次负面反馈，建议调整推送频率或取消订阅")
            else:
                yield event.plain_result("❌ 反馈提交失败，请稍后重试")
                
        except Exception as e:
            logger.error(f"[Subscription] 处理反馈失败: {e}")
            yield event.plain_result("❌ 反馈处理失败")
    
    def _normalize_emoji(self, text: str) -> str:
        """
        标准化 emoji，移除变体选择器和肤色修饰符
        
        不同平台发送的 emoji 可能包含：
        - 变体选择器 (U+FE0F) - 文本/emoji 样式切换
        - 肤色修饰符 (U+1F3FB - U+1F3FF)
        - 零宽度连接符 (U+200D)
        """
        import unicodedata
        
        # 移除变体选择器 (VS15/VS16)
        text = text.replace('\ufe0e', '').replace('\ufe0f', '')
        
        # 移除肤色修饰符 (Fitzpatrick skin type modifiers)
        skin_tones = ['\U0001F3FB', '\U0001F3FC', '\U0001F3FD', '\U0001F3FE', '\U0001F3FF']
        for tone in skin_tones:
            text = text.replace(tone, '')
        
        # 移除零宽度字符
        text = text.replace('\u200d', '').replace('\u200b', '').replace('\u200c', '')
        
        return text
    
    def _contains_emoji(self, text: str, emoji_base: str) -> bool:
        """
        检查文本是否包含指定的 emoji（忽略变体）
        
        Args:
            text: 原始文本
            emoji_base: 基础 emoji 字符
            
        Returns:
            是否包含
        """
        normalized_text = self._normalize_emoji(text)
        normalized_emoji = self._normalize_emoji(emoji_base)
        return normalized_emoji in normalized_text
    
    async def _handle_text_feedback(self, event: AstrMessageEvent, message_str: str):
        """
        处理文本反馈（用户回复 👍 或 👎）
        
        Args:
            event: 消息事件
            message_str: 消息文本
            
        Returns:
            反馈结果（如果处理了反馈），否则返回 None
        """
        # 只匹配纯反馈消息
        message_stripped = message_str.strip()
        
        # 调试：打印原始消息的 Unicode 编码
        if message_stripped and len(message_stripped) <= 10:
            hex_repr = ' '.join(f'U+{ord(c):04X}' for c in message_stripped)
            logger.debug(f"[Subscription] 反馈检测: 原始消息='{message_stripped}' Unicode=[{hex_repr}]")
        
        # 标准化消息文本，便于匹配
        normalized_msg = self._normalize_emoji(message_stripped)
        
        # 支持的反馈模式（基础 emoji + 文字）
        # 👍 的 Unicode: U+1F44D
        # 👎 的 Unicode: U+1F44E
        positive_emoji = ['👍', '\U0001F44D']  # 两种表示方式
        negative_emoji = ['👎', '\U0001F44E']
        positive_text = ['有用', '赞', '喜欢', '+1', 'good', 'nice', '棒', '顶']
        negative_text = ['无用', '不要', '不喜欢', '-1', 'bad', '差', '踩']
        
        feedback_type = None
        
        # 检查 emoji 反馈（优先级最高）
        for emoji in positive_emoji:
            if self._contains_emoji(message_stripped, emoji):
                feedback_type = 'useful'
                break
        
        if not feedback_type:
            for emoji in negative_emoji:
                if self._contains_emoji(message_stripped, emoji):
                    feedback_type = 'useless'
                    break
        
        # 检查文字反馈（消息长度限制更严格）
        if not feedback_type and len(message_stripped) <= 10:
            if any(p in normalized_msg for p in positive_text):
                feedback_type = 'useful'
            elif any(p in normalized_msg for p in negative_text):
                feedback_type = 'useless'
        
        if not feedback_type:
            return None
        
        # 获取用户ID
        user_id = get_unified_user_id(event)
        
        # 获取用户最近的推送记录
        recent_push = self.subscription_manager.get_user_recent_push(
            user_id=user_id,
            max_age_minutes=30  # 30分钟内的推送可以反馈
        )
        
        if not recent_push:
            # 没有最近的推送，不处理该消息
            logger.info(f"[Subscription] 文本反馈: 无最近30分钟内的推送记录 - user={user_id}, feedback_type={feedback_type}")
            # 返回提示，而不是静默忽略（让用户知道为什么反馈无效）
            return event.plain_result(f"⚠️ 无法匹配到最近的推送\n\n可能原因：\n• 推送已超过30分钟\n• 该消息不是订阅推送\n\n💡 请在推送消息后30分钟内回复反馈")
        
        source_id = recent_push['source_id']
        content_hash = recent_push['content_hash']
        
        # 提交反馈
        success = self.subscription_manager.submit_feedback(
            user_id=user_id,
            source_id=source_id,
            feedback_type=feedback_type,
            content_hash=content_hash
        )
        
        if success:
            logger.info(f"[Subscription] 文本反馈成功: user={user_id}, source={source_id}, type={feedback_type}")
            if feedback_type == 'useful':
                return event.plain_result("👍 感谢反馈！我们会推送更多类似内容")
            else:
                # 检查是否需要降低推送频率
                if self.subscription_manager.should_reduce_push_frequency(user_id, source_id):
                    return event.plain_result("👎 收到反馈！\n\n💡 检测到您对此源多次负面反馈，建议调整推送频率或取消订阅")
                return event.plain_result("👎 收到反馈！我们会优化推送内容")
        else:
            logger.warning(f"[Subscription] 文本反馈失败: user={user_id}, source={source_id}")
            return event.plain_result("❌ 反馈提交失败，请稍后重试")
    
    @filter.platform_adapter_type(filter.PlatformAdapterType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        """处理会话消息"""
        if not self.system_available:
            return
        
        # 如果事件已经有结果，不处理
        if event.get_result():
            logger.debug(f"[Subscription] on_message: 跳过 - has_result=True")
            return
        
        # 如果是命令（包括回调命令），不处理
        message_str = event.message_str or ""
        if message_str.startswith("/"):
            logger.debug(f"[Subscription] on_message: 跳过 - 是命令: {message_str}")
            return
        
        # 特别跳过回调消息（某些平台可能不以 / 开头）
        if message_str.startswith("callback "):
            logger.debug(f"[Subscription] on_message: 跳过 - 是回调: {message_str}")
            return
        
        # 检测文本反馈（👍/👎）
        feedback_result = await self._handle_text_feedback(event, message_str)
        if feedback_result:
            yield feedback_result
            event.stop_event()
            return
        
        session_id = event.get_session_id()
        
        # P1优化：检测会话超时并提示用户
        # 先不自动清理，检查是否存在过期会话
        session = self.session_manager.get_session(session_id, renew=False, auto_cleanup=False)
        if session and session.get('type') == 'subscription_menu':
            # 检查是否过期
            from datetime import datetime
            if datetime.now() > session.get('expires_at', datetime.now()):
                # 会话已超时，清理并提示用户
                self.session_manager.end_session(session_id)
                logger.info(f"[Subscription] 会话超时 - session_id={session_id}")
                yield event.plain_result("⏰ 订阅会话已超时\n\n💡 请重新发送 /订 进入订阅管理")
                event.stop_event()
                return
        
        # 正常获取会话（自动续期）
        session = self.session_manager.get_session(session_id)
        
        if not session or session.get('type') != 'subscription_menu':
            logger.debug(f"[Subscription] on_message: 没有会话或类型不匹配 - session_id={session_id}, message={message_str}")
            return
        
        logger.debug(f"[Subscription] on_message: 处理会话输入 - message={message_str}")
        
        # 处理会话输入
        has_result = False
        async for result in self.session_handler.handle_session_input(event, session):
            has_result = True
            yield result
        
        # 如果有结果，停止事件传播，防止流转到 LLM
        if has_result:
            event.stop_event()
