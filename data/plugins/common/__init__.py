"""
知识猎人通用模块

提供统一的会员、积分、配额管理功能，以及跨平台能力检测和交互工具，支持所有插件使用。

核心模块：
- QuotaValidator: 配额验证器
- MembershipManager: 会员管理器  
- PointsManager: 积分管理器
- DatabaseManager: 数据库管理器
- PlatformCapabilities: 平台能力检测器
- MessageEditor: 消息编辑器
- BaseResponseBuilder: 响应构建器基类
- CacheManager: 缓存管理器
- SessionManager: 会话管理器 ⭐ v2.2
- LarkMessageHelper: 飞书消息辅助类 ⭐ v2.2
- NavigationHandler: 导航命令处理器 ⭐ v2.3
- PluginScheduler: 插件级定时任务调度器 ⭐ v2.4

优化模块：
- PluginErrorHandler: 统一错误处理器
- LoadingIndicator: 统一加载提示器
- InputValidator: 统一输入验证器
- Pagination: 统一分页管理器
- HelpBuilder: 统一帮助构建器
- NavigationHint: 导航提示模块

工具模块：
- platform_utils: 平台检测工具函数
- message_formatter: 消息格式化工具函数

使用示例：
    from data.plugins.common import (
        QuotaValidator, MemberLevel,
        get_platform_capabilities,
        MessageEditor,
        BaseResponseBuilder,
        CacheManager
    )
    
    # 配额系统
    validator = QuotaValidator(db_path)
    result = await validator.check_quota(user_id, "music_download_flac", "music")
    if result.allowed:
        await validator.consume_quota(user_id, "music_download_flac", "music")
    
    # 平台能力检测
    capabilities = get_platform_capabilities(event, "MyPlugin")
    
    # 消息编辑
    async for result in MessageEditor.edit_or_send(event, "消息", keyboard):
        yield result
    
    # 响应构建
    builder = BaseResponseBuilder(capabilities)
    message, keyboard = builder.build_response("Hello!")
    
    # 缓存管理
    cache = CacheManager(ttl=3600)
    cache.set("key", "value")
"""

# 配额系统
from .quota_validator import QuotaValidator, QuotaResult, MemberLevel
from .database_manager import DatabaseManager
from .points_manager import PointsManager
from .membership_manager import MembershipManager
from .rate_limiter import RateLimiter, get_rate_limiter
from .quota_reservation import QuotaReservation
from .quota_analytics import QuotaAnalytics

# 平台相关
from .platform_capabilities import (
    PlatformCapabilities,
    get_platform_capabilities,
    supports_buttons,
    is_button_mode,
    is_session_mode
)
from .message_editor import MessageEditor

# 交互相关
from .response_builder import BaseResponseBuilder, create_response_builder
from .session_manager import SessionManager, get_session_manager
from .session_step_manager import SessionStepManager
from .lark_message_helper import LarkMessageHelper
from .navigation_handler import NavigationHandler, NavigationResult
from .command_handler import auto_stop_command

# 优化模块
from .error_handler import PluginErrorHandler
from .loading_indicator import LoadingIndicator
from .input_validator import InputValidator
from .pagination import Pagination
from .help_builder import HelpBuilder
from .navigation_hint import NavigationHint, HINT_MAIN_MENU, HINT_SUB_MENU, HINT_DETAIL

# 工具模块
from .cache_manager import CacheManager, get_global_cache
from .search_statistics import SearchStatistics, get_search_statistics
from .feedback import FeedbackManager, get_feedback_manager
from .message_pusher import (
    MessagePusher, 
    get_message_pusher, 
    init_message_pusher,
    PushTask,
    PushResult,
    PushStatus,
    PushRateLimiter
)
from .user_utils import get_unified_user_id, parse_unified_user_id
from .exit_handler import ExitHandler, handle_exit
from .ai_interpreter import AIInterpreter, get_ai_interpreter
from .search_helper import SearchHelper, create_search_helper
from .scheduler import (
    PluginScheduler, 
    get_scheduler, 
    scheduled_task, 
    register_decorated_tasks,
    ScheduledTask,
    TaskStatus
)
from .daily_report import (
    DailyReportGenerator,
    DailyReportConfig,
    DailyReportData,
    get_daily_report_generator,
    init_daily_report
)
from .subscription_manager import (
    SubscriptionManager,
    get_subscription_manager,
    SubscriptionType,
    PushFrequency,
    PUSH_FREQUENCY_NAMES,
    Subscription
)
from .subscription_source import (
    SourceManager,
    get_source_manager,
    init_source_manager,
    SubscriptionLink,
    SubscriptionSource,
    SourceContent,
    SourceType,
    SourceStatus,
    AccessLevel,
    PushContentMode,
    PUSH_CONTENT_MODE_NAMES,
    PUSH_CONTENT_MODE_DESC,
    SourceAdapter,
    InternalAdapter,
    RSSAdapter,
    APIAdapter,
    WebhookAdapter,
    URLParser
)
from .push_formatter import (
    PushFormatter,
    FormattedPushContent,
    get_push_formatter,
    init_push_formatter
)
from .content_prefetcher import (
    ContentPrefetcher,
    get_prefetcher,
    init_prefetcher,
    mark_prefetcher_index_dirty,  # P0优化：标记索引需要重建
    FetchPriority,
    CachedContent
)
from .push_scheduler import (
    PushScheduler,
    get_push_scheduler,
    init_push_scheduler
)
from .subscription_privileges import (
    SubscriptionPrivilegeManager,
    get_subscription_privilege_manager,
    init_subscription_privileges,
    SUBSCRIPTION_PRIVILEGES,
    SUBSCRIPTION_BOOST_PACKAGES,
    SUBSCRIPTION_POINTS_REWARDS
)

# 任务系统
from .task_manager import (
    TaskManager,
    get_task_manager,
    TaskType,
    TaskTrigger,
    TaskDefinition,
    UserTaskProgress,
    register_task_scheduler_jobs
)
from .task_tracker import (
    TaskTracker,
    get_task_tracker,
    track_task
)

# 错误追踪
from .error_tracker import (
    ErrorTracker,
    get_error_tracker,
    track_error
)

# 邀请系统
from .invite_manager import (
    InviteManager,
    get_invite_manager,
    InviteReward
)

from . import platform_utils
from . import message_formatter
from .message_formatter import (
    get_separator,
    format_title_for_platform,
    PlatformFormatter,
    PLATFORM_SEPARATOR_CONFIG
)


def extract_user_info(event) -> dict:
    """
    从 event 对象提取用户信息
    
    Args:
        event: AstrMessageEvent 对象
        
    Returns:
        dict: {user_id, username, platform, platform_user_id}
        其中 user_id 是统一格式: platform:raw_id
    """
    # 使用统一的用户ID格式
    user_id = get_unified_user_id(event)
    
    # 获取用户昵称 - 使用 AstrMessageEvent 的标准方法
    username = event.get_sender_name() if hasattr(event, 'get_sender_name') else None
    
    # 获取平台信息 - 使用 AstrMessageEvent 的标准方法
    platform = 'unknown'
    platform_user_id = user_id
    
    if hasattr(event, 'get_platform_name'):
        platform_name = event.get_platform_name()
        if platform_name:
            # 标准化平台名称
            platform_map = {
                'aiocqhttp': 'qq',
                'nakuru': 'qq',
                'telegram': 'telegram',
                'discord': 'discord',
                'slack': 'slack',
                'lark': 'lark',
                'feishu': 'lark',
                'wechat': 'wechat',
                'gewechat': 'wechat',
                'dingtalk': 'dingtalk',
            }
            platform = platform_map.get(platform_name.lower(), platform_name.lower())
    
    # 从 user_id 推断平台（如果还是 unknown）
    if platform == 'unknown' and user_id:
        if user_id.startswith('user_telegram_'):
            platform = 'telegram'
            platform_user_id = user_id.replace('user_telegram_', '')
        elif user_id.startswith('user_qq_'):
            platform = 'qq'
            platform_user_id = user_id.replace('user_qq_', '')
        elif user_id.startswith('user_wechat_'):
            platform = 'wechat'
            platform_user_id = user_id.replace('user_wechat_', '')
        elif user_id.startswith('user_lark_') or user_id.startswith('ou_'):
            platform = 'lark'
            platform_user_id = user_id
        elif user_id.startswith('user_discord_'):
            platform = 'discord'
            platform_user_id = user_id.replace('user_discord_', '')
    
    # 飞书 open_id 格式特殊处理
    if user_id and user_id.startswith('ou_'):
        platform = 'lark'
        platform_user_id = user_id
    
    return {
        'user_id': user_id,
        'username': username,
        'platform': platform,
        'platform_user_id': platform_user_id
    }

__all__ = [
    # 配额系统
    'DatabaseManager',
    'PointsManager',
    'MembershipManager',
    'QuotaValidator',
    'MemberLevel',
    'QuotaResult',
    'RateLimiter',
    'get_rate_limiter',
    'QuotaReservation',
    'QuotaAnalytics',
    
    # 平台相关
    'PlatformCapabilities',
    'get_platform_capabilities',
    'supports_buttons',
    'is_button_mode',
    'is_session_mode',
    'MessageEditor',
    
    # 交互相关
    'BaseResponseBuilder',
    'create_response_builder',
    'SessionManager',
    'get_session_manager',
    'SessionStepManager',
    'LarkMessageHelper',
    'NavigationHandler',
    'NavigationResult',
    'auto_stop_command',
    
    # 优化模块
    'PluginErrorHandler',
    'LoadingIndicator',
    'InputValidator',
    'Pagination',
    'HelpBuilder',
    'NavigationHint',
    'HINT_MAIN_MENU',
    'HINT_SUB_MENU',
    'HINT_DETAIL',
    
    # 工具模块
    'CacheManager',
    'get_global_cache',
    'SearchStatistics',
    'get_search_statistics',
    'FeedbackManager',
    'get_feedback_manager',
    'MessagePusher',
    'get_message_pusher',
    'init_message_pusher',
    'PushTask',
    'PushResult',
    'PushStatus',
    'PushRateLimiter',
    'get_unified_user_id',
    'parse_unified_user_id',
    'ExitHandler',
    'handle_exit',
    'AIInterpreter',
    'get_ai_interpreter',
    'SearchHelper',
    'create_search_helper',
    'PluginScheduler',
    'get_scheduler',
    'scheduled_task',
    'register_decorated_tasks',
    'ScheduledTask',
    'TaskStatus',
    'DailyReportGenerator',
    'DailyReportConfig',
    'DailyReportData',
    'get_daily_report_generator',
    'init_daily_report',
    'SubscriptionManager',
    'get_subscription_manager',
    'SubscriptionType',
    'PushFrequency',
    'PUSH_FREQUENCY_NAMES',
    'Subscription',
    'SourceManager',
    'get_source_manager',
    'init_source_manager',
    'SubscriptionSource',
    'SourceContent',
    'SourceType',
    'SourceStatus',
    'AccessLevel',
    'PushContentMode',
    'PUSH_CONTENT_MODE_NAMES',
    'PUSH_CONTENT_MODE_DESC',
    'SourceAdapter',
    'InternalAdapter',
    'RSSAdapter',
    'APIAdapter',
    'WebhookAdapter',
    'PushFormatter',
    'FormattedPushContent',
    'get_push_formatter',
    'init_push_formatter',
    'ContentPrefetcher',
    'get_prefetcher',
    'init_prefetcher',
    'mark_prefetcher_index_dirty',
    'FetchPriority',
    'CachedContent',
    'PushScheduler',
    'get_push_scheduler',
    'init_push_scheduler',
    'platform_utils',
    'message_formatter',
    'extract_user_info',
    # 错误追踪
    'ErrorTracker',
    'get_error_tracker',
    'track_error',
    # 消息格式化
    'get_separator',
    'format_title_for_platform',
    'PlatformFormatter',
    'PLATFORM_SEPARATOR_CONFIG',
]

__version__ = '1.0.0'
