"""
每日统计报告生成器

功能：
1. 汇总各数据源的统计信息
2. 生成格式化的报表文本
3. 支持不同详细程度（简报/完整报告）
4. 定时自动推送给管理员

使用示例：
    from common.daily_report import DailyReportGenerator, get_daily_report_generator
    
    generator = get_daily_report_generator(db, search_statistics, quota_analytics)
    
    # 生成报告
    report = await generator.generate_report(level="full")
    
    # 发送给管理员
    await generator.send_to_admins(admin_ids, context)
"""
import asyncio
import psutil
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


@dataclass
class DailyReportConfig:
    """每日报告配置"""
    enabled: bool = True
    send_time: str = "08:00"  # HH:MM 格式，早上推送昨日报告
    admin_ids: List[str] = field(default_factory=list)
    report_level: str = "full"  # "brief" 或 "full"


@dataclass
class DailyReportData:
    """每日报告数据结构"""
    date: str = ""
    
    # 消息统计
    today_messages: int = 0
    yesterday_messages: int = 0
    week_avg_messages: float = 0
    message_change_percent: float = 0
    platform_distribution: Dict[str, int] = field(default_factory=dict)
    
    # 用户活跃
    today_dau: int = 0
    yesterday_dau: int = 0
    dau_change_percent: float = 0
    avg_dau_7d: float = 0
    new_users_today: int = 0
    member_count: int = 0
    retention_day1: float = 0
    retention_day7: float = 0
    
    # 请求统计
    today_requests: int = 0
    yesterday_requests: int = 0
    week_requests: int = 0
    request_change_percent: float = 0
    points_issued: int = 0
    points_spent: int = 0
    checkin_today: int = 0
    
    # 热门操作
    top_actions: List[Dict[str, Any]] = field(default_factory=list)
    
    # 热门搜索
    top_searches: List[Dict[str, Any]] = field(default_factory=list)
    
    # 热门下载
    top_downloads: List[Dict[str, Any]] = field(default_factory=list)
    
    # 插件排行
    plugin_ranking: List[Dict[str, Any]] = field(default_factory=list)
    
    # 系统状态
    uptime: str = ""
    cpu_percent: float = 0
    memory_used_mb: float = 0
    memory_percent: float = 0
    disk_used_gb: float = 0
    disk_total_gb: float = 0
    disk_percent: float = 0
    plugin_count: int = 0
    rate_limiter_active_users: int = 0
    rate_limiter_total_requests: int = 0
    
    # 错误统计
    error_count_today: int = 0
    error_count_yesterday: int = 0
    error_change_percent: float = 0
    error_by_module: List[Dict[str, Any]] = field(default_factory=list)
    error_by_type: List[Dict[str, Any]] = field(default_factory=list)


class DailyReportGenerator:
    """每日统计报告生成器"""
    
    # 操作类型中文名称
    ACTION_NAMES = {
        'music_search': '🎵音乐搜索',
        'music_download_128': '🎵128k下载',
        'music_download_320': '🎵320k下载',
        'music_download_flac': '🎵无损下载',
        'music_lyric': '🎵歌词查看',
        'douban_search': '🎨豆瓣搜索',
        'douban_view': '🎨豆瓣详情',
        'pansou_search': '📁网盘搜索',
        'pansou_download': '📁网盘下载',
        'file_process': '📄文件处理',
        'book_search': '📚图书搜索',
        'book_download': '📚图书下载',
    }
    
    # 插件中文名称
    PLUGIN_NAMES = {
        'music': '🎵音乐',
        'douban': '🎨豆瓣',
        'pansou': '📁网盘',
        'book': '📚图书',
        'file_processor': '📄文件',
    }
    
    # 平台名称
    PLATFORM_NAMES = {
        'telegram': '📱Telegram',
        'qq': '🐧QQ',
        'lark': '🟦飞书',
        'wechat': '💬微信',
        'discord': '🎮Discord',
    }
    
    def __init__(
        self,
        db=None,
        search_statistics=None,
        quota_analytics=None,
        session_handler=None,
        context=None
    ):
        """
        初始化报告生成器
        
        Args:
            db: DatabaseManager 实例
            search_statistics: SearchStatistics 实例
            quota_analytics: QuotaAnalytics 实例
            session_handler: SessionHandler 实例（用于获取系统状态）
            context: AstrBot Context 实例
        """
        self.db = db
        self.search_statistics = search_statistics
        self.quota_analytics = quota_analytics
        self.session_handler = session_handler
        self.context = context
        
        # 配置
        self.config = DailyReportConfig()
        
        # 启动时间（用于计算运行时长）
        self._start_time = datetime.now()
    
    def update_config(self, config: Dict[str, Any]):
        """更新配置"""
        if 'enabled' in config:
            self.config.enabled = config['enabled']
        if 'send_time' in config:
            self.config.send_time = config['send_time']
        if 'admin_ids' in config:
            self.config.admin_ids = config['admin_ids']
        if 'report_level' in config:
            self.config.report_level = config['report_level']
    
    def get_config(self) -> Dict[str, Any]:
        """获取当前配置"""
        return {
            'enabled': self.config.enabled,
            'send_time': self.config.send_time,
            'admin_ids': self.config.admin_ids,
            'report_level': self.config.report_level
        }
    
    async def collect_data(self) -> DailyReportData:
        """
        采集昨日完整一天的统计数据
        
        Returns:
            DailyReportData 数据对象
        """
        data = DailyReportData()
        # 统计昨天的数据
        yesterday = datetime.now() - timedelta(days=1)
        data.date = yesterday.strftime("%Y-%m-%d")
        
        try:
            # 1. 采集搜索统计数据
            await self._collect_search_stats(data)
            
            # 2. 采集配额统计数据
            await self._collect_quota_stats(data)
            
            # 3. 采集系统状态
            await self._collect_system_stats(data)
            
            # 4. 采集数据库统计
            await self._collect_db_stats(data)
            
            # 5. 采集错误统计
            await self._collect_error_stats(data)
            
        except Exception as e:
            logger.error(f"[DailyReport] 采集数据失败: {e}", exc_info=True)
        
        return data
    
    async def _collect_search_stats(self, data: DailyReportData):
        """采集昨日搜索统计数据"""
        if not self.search_statistics:
            return
        
        try:
            # 获取仪表盘数据（含昨日的 DAU 等）
            dashboard = self.search_statistics.get_dashboard_stats(days=7)
            
            # DAU 数据
            # get_dashboard_stats 返回的 today_dau 是“今天的 DAU”，yesterday_dau 是“昨天的 DAU”
            # 我们的报告是“昨日报告”，所以要统计的是昨天的 DAU
            data.today_dau = dashboard.get('yesterday_dau', 0)  # 昨日 DAU
            
            # 计算昨日与前日的环比（需要重新计算）
            # dashboard 的 dau_change 是“今天 vs 昨天”，我们需要“昨天 vs 前天”
            day_before = datetime.now() - timedelta(days=2)
            day_before_dau = self.search_statistics.get_daily_active_users(target_date=day_before)
            data.yesterday_dau = day_before_dau
            
            if day_before_dau > 0:
                data.dau_change_percent = round((data.today_dau - day_before_dau) / day_before_dau * 100, 1)
            else:
                data.dau_change_percent = 0
            
            data.avg_dau_7d = dashboard.get('avg_dau_7d', 0)
            
            # 留存率
            retention = dashboard.get('retention', {})
            data.retention_day1 = retention.get('day1_retention', 0)
            data.retention_day7 = retention.get('day7_retention', 0)
            
            # 插件排行
            data.plugin_ranking = dashboard.get('plugin_ranking', [])
            
            # 热门搜索 - 昨日数据（start_days_ago=1 代表从昨天开始）
            data.top_searches = self.search_statistics.get_popular_searches(days=1, limit=5, start_days_ago=1)
            
            # 热门下载 - 昨日数据
            data.top_downloads = self.search_statistics.get_popular_downloads(days=1, limit=5, start_days_ago=1)
            
        except Exception as e:
            logger.error(f"[DailyReport] 采集搜索统计失败: {e}")
    
    async def _collect_quota_stats(self, data: DailyReportData):
        """采集昨日配额统计数据"""
        if not self.quota_analytics:
            return
        
        try:
            # 获取昨日使用统计 (start_days_ago=1 代表从昨天开始)
            usage_stats = await self.quota_analytics.get_usage_stats(days=1, start_days_ago=1)
            
            # 热门操作 - 昨日
            data.top_actions = usage_stats.get('top_actions', [])[:5]
            
            # 请求统计 - 昨日（从 daily_stats 中汇总）
            daily_stats = usage_stats.get('daily_stats', [])
            data.today_requests = sum(d.get('total_usage', 0) for d in daily_stats)
            
            # 获取 7 日统计
            week_stats = await self.quota_analytics.get_usage_stats(days=7)
            week_daily = week_stats.get('daily_stats', [])
            data.week_requests = sum(d.get('total_usage', 0) for d in week_daily)
            
        except Exception as e:
            logger.error(f"[DailyReport] 采集配额统计失败: {e}")
    
    async def _collect_system_stats(self, data: DailyReportData):
        """采集系统状态"""
        try:
            # 运行时长
            uptime = datetime.now() - self._start_time
            days = uptime.days
            hours = uptime.seconds // 3600
            data.uptime = f"{days}天{hours}小时" if days > 0 else f"{hours}小时"
            
            # CPU 和内存
            data.cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            data.memory_used_mb = memory.used / (1024 * 1024)
            data.memory_percent = memory.percent
            
            # 磁盘（兼容 Windows 和 Linux）
            import os
            if os.name == 'nt':  # Windows
                # 获取当前工作目录所在的盘符
                current_drive = os.path.splitdrive(os.getcwd())[0] + '\\'
                disk = psutil.disk_usage(current_drive)
            else:  # Linux/macOS
                disk = psutil.disk_usage('/')
            data.disk_used_gb = disk.used / (1024 ** 3)
            data.disk_total_gb = disk.total / (1024 ** 3)
            data.disk_percent = disk.percent
            
            # 插件数量
            if self.context:
                try:
                    # 使用 context.get_all_stars() 获取所有已激活的插件
                    all_stars = self.context.get_all_stars()
                    # 只统计已激活的插件
                    data.plugin_count = len([s for s in all_stars if getattr(s, 'activated', True)])
                except Exception:
                    pass
            
            # 限流器统计
            try:
                from common.rate_limiter import get_rate_limiter
                rate_limiter = get_rate_limiter()
                rl_stats = rate_limiter.get_stats()
                data.rate_limiter_active_users = rl_stats.get('total_users', 0)
                data.rate_limiter_total_requests = rl_stats.get('total_requests', 0)
            except Exception:
                pass
                
        except Exception as e:
            logger.error(f"[DailyReport] 采集系统状态失败: {e}")
    
    async def _collect_db_stats(self, data: DailyReportData):
        """采集昨日数据库统计"""
        if not self.db:
            return
        
        try:
            # 昨日新增用户
            result = self.db.execute_one("""
                SELECT COUNT(*) as count FROM users
                WHERE date(created_at) = date('now', '-1 day')
            """)
            data.new_users_today = result['count'] if result else 0
            
            # 付费会员数（截止昨日）
            result = self.db.execute_one("""
                SELECT COUNT(*) as count FROM memberships
                WHERE level > 0 AND (expire_date IS NULL OR expire_date > datetime('now', '-1 day'))
            """)
            data.member_count = result['count'] if result else 0
            
            # 昨日签到人数
            result = self.db.execute_one("""
                SELECT COUNT(DISTINCT user_id) as count FROM points_transactions
                WHERE source = 'checkin' AND date(created_at) = date('now', '-1 day')
            """)
            data.checkin_today = result['count'] if result else 0
            
            # 昨日积分流通
            result = self.db.execute_one("""
                SELECT 
                    COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as issued,
                    COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as spent
                FROM points_transactions
                WHERE date(created_at) = date('now', '-1 day')
            """)
            if result:
                data.points_issued = result['issued']
                data.points_spent = result['spent']
                
        except Exception as e:
            logger.error(f"[DailyReport] 采集数据库统计失败: {e}")
    
    async def _collect_error_stats(self, data: DailyReportData):
        """采集昨日错误统计"""
        try:
            from .error_tracker import get_error_tracker
            tracker = get_error_tracker()
            if not tracker:
                return
            
            stats = tracker.get_error_stats(days=7)
            if not stats:
                return
            
            data.error_count_today = stats.get('yesterday_errors', 0)
            data.error_change_percent = stats.get('change_percent', 0)
            data.error_by_module = stats.get('by_module', [])[:5]
            data.error_by_type = stats.get('by_type', [])[:5]
            
        except Exception as e:
            logger.error(f"[DailyReport] 采集错误统计失败: {e}")
    
    def format_report(self, data: DailyReportData, level: str = "full") -> str:
        """
        格式化报告
        
        Args:
            data: 报告数据
            level: 报告级别 ("brief" 或 "full")
            
        Returns:
            格式化的报告文本
        """
        if level == "brief":
            return self._format_brief_report(data)
        else:
            return self._format_full_report(data)
    
    def _format_brief_report(self, data: DailyReportData) -> str:
        """格式化简报"""
        lines = [
            f"📊 昨日简报 | {data.date}",
            "━" * 20,
            f"👥 DAU: {data.today_dau}人 ({self._format_change(data.dau_change_percent)})",
            f"📊 请求: {data.today_requests}次",
            f"💰 积分: +{data.points_issued}/-{data.points_spent}",
        ]
        
        # 热门操作 TOP3
        if data.top_actions:
            lines.append("🔥 热门:")
            for i, action in enumerate(data.top_actions[:3], 1):
                action_type = action.get('action_type', '')
                count = action.get('total_count', 0)
                name = self.ACTION_NAMES.get(action_type, action_type)
                lines.append(f"  {i}. {name}: {count}次")
        
        lines.append("━" * 20)
        return "\n".join(lines)
    
    def _format_full_report(self, data: DailyReportData) -> str:
        """格式化完整报告"""
        lines = [
            "📊 AstrBot 昨日统计报告",
            "━" * 22,
            f"📅 统计日期：{data.date}",
        ]
        
        # 用户活跃
        lines.extend([
            "",
            "👥 用户活跃",
            f"├ 昨日DAU: {data.today_dau}人 ({self._format_change(data.dau_change_percent)})",
            f"├ 7日均值: {data.avg_dau_7d:.0f}人",
            f"├ 新增用户: {data.new_users_today}人",
            f"├ 付费会员: {data.member_count}人",
            f"└ 留存率: 次日{data.retention_day1}% | 7日{data.retention_day7}%",
        ])
        
        # 请求统计
        lines.extend([
            "",
            "📊 请求统计",
            f"├ 昨日请求: {data.today_requests}次",
            f"├ 7日累计: {data.week_requests}次",
            f"├ 签到人数: {data.checkin_today}人",
            f"└ 积分流通: 发放 {data.points_issued} | 消耗 {data.points_spent}",
        ])
        
        # 热门操作 TOP5
        if data.top_actions:
            lines.extend(["", "🔥 热门操作 TOP5"])
            for i, action in enumerate(data.top_actions[:5], 1):
                action_type = action.get('action_type', '')
                count = action.get('total_count', 0)
                name = self.ACTION_NAMES.get(action_type, action_type)
                lines.append(f"{i}. {name}: {count}次")
        
        # 热门搜索 TOP5
        if data.top_searches:
            lines.extend(["", "🔍 热门搜索 TOP5"])
            for i, item in enumerate(data.top_searches[:5], 1):
                keyword = item.get('keyword', '')
                count = item.get('search_count', 0)
                users = item.get('unique_users', 0)
                if len(keyword) > 12:
                    keyword = keyword[:10] + "..."
                lines.append(f"{i}. {keyword} ({count}次/{users}人)")
        
        # 热门下载 TOP5
        if data.top_downloads:
            lines.extend(["", "⬇️ 热门下载 TOP5"])
            for i, item in enumerate(data.top_downloads[:5], 1):
                name = item.get('item_name') or item.get('item_id', '未知')
                count = item.get('download_count', 0)
                users = item.get('unique_users', 0)
                if len(name) > 12:
                    name = name[:10] + "..."
                lines.append(f"{i}. {name} ({count}次/{users}人)")
        
        # 插件排行
        if data.plugin_ranking:
            lines.extend(["", "🔌 插件使用排行"])
            for i, p in enumerate(data.plugin_ranking[:5], 1):
                plugin = p.get('plugin_name', '未知')
                total = p.get('total_actions', 0)
                users = p.get('unique_users', 0)
                name = self.PLUGIN_NAMES.get(plugin, plugin)
                lines.append(f"{i}. {name}: {total}次 ({users}人)")
        
        # 系统状态
        lines.extend([
            "",
            "⚙️ 系统状态",
            f"├ 运行时长: {data.uptime}",
            f"├ CPU: {data.cpu_percent:.1f}% | 内存: {data.memory_used_mb:.0f}MB ({data.memory_percent:.1f}%)",
            f"├ 磁盘: {data.disk_used_gb:.1f}/{data.disk_total_gb:.1f}GB ({data.disk_percent:.0f}%)",
            f"├ 插件: {data.plugin_count}个运行中",
            f"└ 限流器: {data.rate_limiter_active_users}活跃/{data.rate_limiter_total_requests}请求",
        ])
        
        # 错误统计
        if data.error_count_today > 0 or data.error_by_module:
            lines.extend([
                "",
                "🔴 错误统计",
                f"├ 昨日错误: {data.error_count_today}次 ({self._format_change(data.error_change_percent)})",
            ])
            if data.error_by_module:
                modules = ", ".join([f"{e['module']}:{e['count']}" for e in data.error_by_module[:3]])
                lines.append(f"└ 模块分布: {modules}")
        
        lines.append("━" * 22)
        return "\n".join(lines)
    
    def _format_change(self, percent: float) -> str:
        """格式化变化百分比"""
        if percent > 0:
            return f"📈+{percent:.1f}%"
        elif percent < 0:
            return f"📉{percent:.1f}%"
        else:
            return "→0%"
    
    async def generate_report(self, level: str = None) -> str:
        """
        生成报告
        
        Args:
            level: 报告级别，默认使用配置中的级别
            
        Returns:
            格式化的报告文本
        """
        if level is None:
            level = self.config.report_level
        
        data = await self.collect_data()
        return self.format_report(data, level)
    
    async def send_to_admins(
        self,
        admin_ids: List[str] = None,
        context=None,
        report: str = None
    ) -> Dict[str, bool]:
        """
        发送报告给管理员
        
        Args:
            admin_ids: 管理员ID列表，默认使用配置中的列表
            context: AstrBot Context
            report: 预生成的报告，默认自动生成
            
        Returns:
            发送结果 {user_id: success}
        """
        if admin_ids is None:
            admin_ids = self.config.admin_ids
        
        if context is None:
            context = self.context
        
        if not admin_ids:
            logger.warning("[DailyReport] 没有配置管理员ID，跳过发送")
            return {}
        
        if report is None:
            report = await self.generate_report()
        
        results = {}
        
        try:
            from common.message_pusher import get_message_pusher
            pusher = get_message_pusher()
            
            for admin_id in admin_ids:
                try:
                    success = await pusher.send_private_message(
                        user_id=admin_id,
                        message=report,
                        context=context
                    )
                    results[admin_id] = success
                    if success:
                        logger.info(f"[DailyReport] 已发送报告给管理员: {admin_id}")
                    else:
                        logger.warning(f"[DailyReport] 发送报告给管理员失败: {admin_id}")
                except Exception as e:
                    logger.error(f"[DailyReport] 发送报告给 {admin_id} 失败: {e}")
                    results[admin_id] = False
                    
        except Exception as e:
            logger.error(f"[DailyReport] 获取消息推送器失败: {e}")
        
        return results
    
    async def scheduled_send(self, context=None):
        """
        定时发送任务（由调度器调用）
        
        Args:
            context: AstrBot Context
        """
        if not self.config.enabled:
            logger.debug("[DailyReport] 每日报告已禁用，跳过发送")
            return
        
        logger.info("[DailyReport] 开始执行每日报告定时任务")
        
        try:
            report = await self.generate_report()
            results = await self.send_to_admins(context=context, report=report)
            
            success_count = sum(1 for v in results.values() if v)
            total_count = len(results)
            logger.info(f"[DailyReport] 每日报告发送完成: {success_count}/{total_count} 成功")
            
        except Exception as e:
            logger.error(f"[DailyReport] 每日报告定时任务失败: {e}", exc_info=True)


# 单例实例
_daily_report_generator: Optional[DailyReportGenerator] = None


def get_daily_report_generator(
    db=None,
    search_statistics=None,
    quota_analytics=None,
    session_handler=None,
    context=None
) -> DailyReportGenerator:
    """
    获取每日报告生成器单例
    
    Args:
        db: DatabaseManager 实例
        search_statistics: SearchStatistics 实例
        quota_analytics: QuotaAnalytics 实例
        session_handler: SessionHandler 实例
        context: AstrBot Context 实例
        
    Returns:
        DailyReportGenerator 实例
    """
    global _daily_report_generator
    
    if _daily_report_generator is None:
        _daily_report_generator = DailyReportGenerator(
            db=db,
            search_statistics=search_statistics,
            quota_analytics=quota_analytics,
            session_handler=session_handler,
            context=context
        )
    elif db is not None:
        # 更新依赖
        _daily_report_generator.db = db
        _daily_report_generator.search_statistics = search_statistics
        _daily_report_generator.quota_analytics = quota_analytics
        _daily_report_generator.session_handler = session_handler
        _daily_report_generator.context = context
    
    return _daily_report_generator


def init_daily_report(
    db=None,
    search_statistics=None,
    quota_analytics=None,
    session_handler=None,
    context=None,
    config: Dict[str, Any] = None
) -> DailyReportGenerator:
    """
    初始化每日报告生成器
    
    Args:
        db: DatabaseManager 实例
        search_statistics: SearchStatistics 实例
        quota_analytics: QuotaAnalytics 实例
        session_handler: SessionHandler 实例
        context: AstrBot Context 实例
        config: 配置字典
        
    Returns:
        DailyReportGenerator 实例
    """
    generator = get_daily_report_generator(
        db=db,
        search_statistics=search_statistics,
        quota_analytics=quota_analytics,
        session_handler=session_handler,
        context=context
    )
    
    if config:
        generator.update_config(config)
    
    return generator
