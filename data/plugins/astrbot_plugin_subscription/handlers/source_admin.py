"""
订阅源管理界面（管理员功能）

功能：
1. 查看所有订阅源
2. 添加订阅源（预置/自定义）
3. 编辑订阅源配置
4. 启用/禁用订阅源
5. 删除订阅源
6. 测试订阅源
"""
from typing import Dict, Any, Optional, List, Tuple

try:
    from astrbot.api import logger
    from astrbot.api.event import AstrMessageEvent
    from astrbot.core.message.components import Plain, InlineKeyboard
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

try:
    from common import (
        MessageEditor,
        get_platform_capabilities,
        get_unified_user_id
    )
    from common.subscription_source import (
        SourceManager,
        SubscriptionLink,
        SubscriptionSource,
        SourceType,
        SourceStatus,
        AccessLevel,
        APIAdapter,
        URLParser
    )
except ImportError:
    logger.warning("[SourceAdmin] 通用模块不可用")


class SourceAdminHandler:
    """订阅源管理处理器"""
    
    # 源类型显示名称
    SOURCE_TYPE_NAMES = {
        'internal': '📊 内部榜单',
        'rss': '📰 RSS订阅',
        'api': '🔌 API接口',
        'webhook': '🔔 Webhook',
        'custom': '⚙️ 自定义'
    }
    
    # 访问级别显示名称
    ACCESS_LEVEL_NAMES = {
        0: '🌐 公开',
        1: '👤 注册用户',
        2: '⭐ 会员',
        3: '💎 VIP',
        99: '🔒 管理员'
    }
    
    # 状态显示名称
    STATUS_NAMES = {
        'active': '✅ 活跃',
        'inactive': '⏸️ 停用',
        'error': '❌ 错误',
        'pending': '⏳ 待审核'
    }
    
    def __init__(self, source_manager: SourceManager):
        self.source_manager = source_manager
        # 临时存储解析结果
        self._last_parse_result = None
        self._last_parse_url = None
        self._last_parse_domain = None
    
    # ==================== 列表页面 ====================
    
    def build_source_list(self, capabilities: Dict[str, Any], page: int = 1, category: str = None, 
                          link_id: int = None, status_filter: str = None) -> Tuple[str, Any]:
        """
        构建订阅源列表
        
        Args:
            capabilities: 平台能力
            page: 页码
            category: 分类筛选
            link_id: 订阅链接ID筛选
            status_filter: 状态筛选 (active/inactive/error)
        """
        # 按 link_id 筛选
        if link_id:
            all_sources = self.source_manager.get_link_sources(link_id)
            link = self.source_manager.get_link(link_id)
            title = f"📰 {link.display_name or link.name} 的订阅源" if link else "📰 订阅源列表"
        else:
            all_sources = self.source_manager.get_all_sources()
            title = "📰 订阅源管理"
        
        # 按分类分组
        categories = {}
        for source in all_sources:
            cat = source.category or "其他"
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(source)
        
        # 状态统计
        status_counts = {'active': 0, 'inactive': 0, 'error': 0}
        for source in all_sources:
            status_counts[source.status.value] = status_counts.get(source.status.value, 0) + 1
        
        # 按分类筛选
        sources = all_sources
        if category:
            sources = [s for s in sources if (s.category or "其他") == category]
        
        # 按状态筛选
        if status_filter:
            sources = [s for s in sources if s.status.value == status_filter]
        
        page_size = 5
        total_pages = max(1, (len(sources) + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_sources = sources[start_idx:end_idx]
        
        # 统计信息
        active_count = status_counts.get('active', 0)
        error_count = status_counts.get('error', 0)
        
        # 分类统计
        cat_stats = " | ".join([f"{k}:{len(v)}" for k, v in categories.items()])
        
        message = f"""{title}

📊 统计: {len(all_sources)}个 | ✅{active_count} | 🔴{error_count}
"""
        if categories:
            message += f"📂 分类: {cat_stats}\n"
        
        # 显示当前筛选条件
        filters = []
        if category:
            filters.append(f"分类:{category}")
        if status_filter:
            status_names = {'active': '活跃', 'inactive': '停用', 'error': '错误'}
            filters.append(f"状态:{status_names.get(status_filter, status_filter)}")
        if filters:
            message += f"🔍 筛选: {', '.join(filters)}\n"
        
        message += "\n"
        
        if not page_sources:
            message += "暂无订阅源\n\n💡 点击下方按钮添加订阅源"
        else:
            for i, source in enumerate(page_sources, start=start_idx + 1):
                status_icon = '✅' if source.status == SourceStatus.ACTIVE else ('🔴' if source.status == SourceStatus.ERROR else '⏸️')
                level_icon = self.ACCESS_LEVEL_NAMES.get(source.access_level.value, '🌐')[:2]
                display_title = source.get_display_title()
                
                # 获取健康度
                stats = self.source_manager.get_source_stats(source.id)
                health_icon = self.source_manager.get_health_icon(stats.get('health_score', 100)) if stats else '🟢'
                
                message += f"{i}. {source.icon} {display_title} {health_icon}\n"
                message += f"   {status_icon} {level_icon} 订阅:{source.current_subscribers}"
                if stats and stats.get('total_count', 0) > 0:
                    message += f" | 成功率:{stats['success_rate']}%"
                message += "\n"
        
        message += f"\n📄 第 {page}/{total_pages} 页"
        
        if capabilities.get('supports_buttons'):
            buttons = []
            
            # 源操作按钮（包含快捷状态切换）
            for source in page_sources:
                display_title = source.get_display_title()
                row = []
                # 详情按钮
                row.append({
                    "text": f"📝 {display_title[:6]}",
                    "callback_data": f"subscription:admin:source:{source.id}"
                })
                # 快捷状态切换按钮
                if source.status == SourceStatus.ACTIVE:
                    row.append({
                        "text": "⏸️停用",
                        "callback_data": f"subscription:admin:quick_disable:{source.id}"
                    })
                else:
                    row.append({
                        "text": "✅启用",
                        "callback_data": f"subscription:admin:quick_enable:{source.id}"
                    })
                buttons.append(row)
            
            # 状态筛选按钮
            status_row = []
            if status_filter:
                status_row.append({"text": "📊 全部", "callback_data": "subscription:admin:list:1"})
            if status_filter != 'active':
                status_row.append({"text": f"✅ 活跃({status_counts.get('active', 0)})", "callback_data": "subscription:admin:list:1::active"})
            if status_filter != 'error' and error_count > 0:
                status_row.append({"text": f"🔴 错误({error_count})", "callback_data": "subscription:admin:list:1::error"})
            if status_row:
                buttons.append(status_row)
            
            # 分类筛选按钮
            cat_row = []
            if category:
                cat_row.append({
                    "text": "📂 全部分类",
                    "callback_data": "subscription:admin:list:1"
                })
            for cat in list(categories.keys())[:3]:
                if cat != category:
                    cat_row.append({
                        "text": f"📂 {cat[:4]}",
                        "callback_data": f"subscription:admin:list:1:{cat}"
                    })
            if cat_row:
                buttons.append(cat_row)
            
            # 翻页按钮
            nav_row = []
            if page > 1:
                nav_row.append({"text": "⬅️", "callback_data": f"subscription:admin:list:{page-1}:{category or ''}:{status_filter or ''}"})
            if page < total_pages:
                nav_row.append({"text": "➡️", "callback_data": f"subscription:admin:list:{page+1}:{category or ''}:{status_filter or ''}"})
            if nav_row:
                buttons.append(nav_row)
            
            # 功能按钮
            func_row = [
                {"text": "🔍 搜索", "callback_data": "subscription:admin:search"},
                {"text": "📦 批量操作", "callback_data": "subscription:admin:batch"}
            ]
            buttons.append(func_row)
            
            # 切换到订阅链接视图
            if not link_id:
                buttons.append([
                    {"text": "🔗 订阅链接", "callback_data": "subscription:admin:links:1"}
                ])
            else:
                buttons.append([
                    {"text": "🔙 返回链接详情", "callback_data": f"subscription:admin:link:{link_id}"}
                ])
            
            buttons.append([
                {"text": "🔙 返回统计", "callback_data": "subscription:admin:stats"},
                {"text": "❌ 关闭", "callback_data": "subscription:exit"}
            ])
            
            keyboard = InlineKeyboard(buttons=buttons)
            return message, keyboard
        else:
            message += "\n\n操作: a-添加预置 | c-自定义 | 数字-查看详情 | b-返回"
            return message, None
    
    # ==================== 预置源列表 ====================
    
    def build_preset_list(self, capabilities: Dict[str, Any]) -> Tuple[str, Any]:
        """构建预置源列表"""
        presets = self.source_manager.list_preset_sources()
        
        message = """➕ 添加预置订阅源

选择要添加的预置源:

"""
        
        for i, preset in enumerate(presets, 1):
            message += f"{i}. 📰 {preset['name']}\n"
            message += f"   🔗 {preset['url'][:40]}...\n"
        
        if capabilities.get('supports_buttons'):
            buttons = []
            
            for preset in presets:
                buttons.append([{
                    "text": f"➕ {preset['name']}",
                    "callback_data": f"subscription:admin:create_preset:{preset['name']}"
                }])
            
            buttons.append([
                {"text": "🔙 返回列表", "callback_data": "subscription:admin:list:1"},
                {"text": "❌ 关闭", "callback_data": "subscription:exit"}
            ])
            
            keyboard = InlineKeyboard(buttons=buttons)
            return message, keyboard
        else:
            message += "\n输入序号添加 | b-返回"
            return message, None
    
    # ==================== 订阅统计 ====================
    
    def build_stats_page(self, capabilities: Dict[str, Any], subscription_manager=None) -> Tuple[str, Any]:
        """构建订阅统计页面"""
        # 获取订阅源统计
        all_sources = self.source_manager.get_all_sources()
        all_links = self.source_manager.get_all_links()
        
        active_sources = sum(1 for s in all_sources if s.status == SourceStatus.ACTIVE)
        total_subscribers = sum(s.current_subscribers for s in all_sources)
        
        # 按分类统计
        category_stats = {}
        for source in all_sources:
            cat = source.category or "其他"
            if cat not in category_stats:
                category_stats[cat] = {'count': 0, 'subscribers': 0}
            category_stats[cat]['count'] += 1
            category_stats[cat]['subscribers'] += source.current_subscribers
        
        # 热门订阅源 TOP 5
        top_sources = sorted(all_sources, key=lambda s: s.current_subscribers, reverse=True)[:5]
        
        message = f"""📊 订阅系统统计

🔗 订阅链接: {len(all_links)} 个
📰 订阅源: {len(all_sources)} 个 ({active_sources} 活跃)
👥 总订阅人次: {total_subscribers}

📂 分类统计:
"""
        for cat, stats in sorted(category_stats.items(), key=lambda x: x[1]['subscribers'], reverse=True):
            message += f"  • {cat}: {stats['count']}源 / {stats['subscribers']}订阅\n"
        
        if top_sources:
            message += f"\n🔥 热门订阅源 TOP5:\n"
            for i, source in enumerate(top_sources, 1):
                display_title = source.get_display_title()
                message += f"  {i}. {source.icon} {display_title[:12]} ({source.current_subscribers}人)\n"
        
        # 获取用户订阅统计
        if subscription_manager:
            try:
                total_subscriptions = subscription_manager.count_all_subscriptions()
                active_users = subscription_manager.count_active_users()
                message += f"\n👤 用户统计:\n"
                message += f"  • 总订阅数: {total_subscriptions}\n"
                message += f"  • 活跃用户: {active_users}\n"
            except Exception:
                pass
        
        if capabilities.get('supports_buttons'):
            buttons = [
                [
                    {"text": "🔗 订阅链接", "callback_data": "subscription:admin:links:1"},
                    {"text": "📰 订阅源", "callback_data": "subscription:admin:list:1"}
                ],
                [
                    {"text": "📈 运营数据", "callback_data": "subscription:admin:analytics"}
                ],
                [
                    {"text": "📝 订阅配置", "callback_data": "quota_admin:admin:sub_config"}
                ],
                [
                    {"text": "🔙 返回管理", "callback_data": "quota_admin:admin_back"},
                    {"text": "❌ 关闭", "callback_data": "subscription:exit"}
                ]
            ]
            keyboard = InlineKeyboard(buttons=buttons)
            return message, keyboard
        else:
            message += "\n\n1-订阅链接 | 2-订阅源 | 3-运营数据 | 4-订阅配置 | b-返回"
            return message, None
    
    # ==================== 运营数据分析 ====================
    
    def build_analytics_page(self, capabilities: Dict[str, Any], subscription_manager=None) -> Tuple[str, Any]:
        """构建运营数据分析页面"""
        if not subscription_manager:
            return "❌ 订阅管理器不可用", None
        
        # 获取订阅趋势
        trend = subscription_manager.get_subscription_trend(7)
        
        # 获取用户活跃度
        activity = subscription_manager.get_user_activity_stats()
        
        # 获取源健康度排行
        health_ranking = subscription_manager.get_source_health_ranking(5)
        
        message = """📈 运营数据分析

━━━━━━ 订阅趋势（近7天）━━━━━━
"""
        # 趋势图（简易文本版）
        for day in trend['daily']:
            bar_new = '▓' * min(day['new'], 10)
            bar_lost = '░' * min(day['lost'], 10)
            net_icon = '📈' if day['net'] > 0 else ('📉' if day['net'] < 0 else '➖')
            message += f"{day['date']} +{day['new']}{bar_new} -{day['lost']}{bar_lost} {net_icon}\n"
        
        net_icon = '📈' if trend['net_growth'] > 0 else ('📉' if trend['net_growth'] < 0 else '➖')
        message += f"\n汇总: 新增 {trend['total_new']} | 流失 {trend['total_lost']} | 净增 {trend['net_growth']} {net_icon}\n"
        
        message += f"""
━━━━━━ 用户活跃度 ━━━━━━
👥 总用户: {activity['total_users']}
🟢 活跃用户: {activity['active_users']}（7天内）
💬 反馈率: {activity['feedback_rate']}%
📊 人均订阅: {activity['avg_subscriptions']}

活跃度分布:
  🔥 高活跃(5+订阅): {activity['activity_distribution']['high']}人
  ⚡ 中活跃(2-4订阅): {activity['activity_distribution']['medium']}人
  💤 低活跃(1订阅): {activity['activity_distribution']['low']}人
"""
        
        if health_ranking:
            message += "\n━━━━━━ 源健康度TOP5 ━━━━━━\n"
            for i, src in enumerate(health_ranking, 1):
                health_icon = '🟢' if src['health_score'] >= 80 else ('🟡' if src['health_score'] >= 60 else '🔴')
                # 获取源名称
                source_name = "未知源"
                if self.source_manager:
                    source = self.source_manager.get_source(src['source_id'])
                    if source:
                        source_name = source.get_display_title()[:10]
                message += f"{i}. {source_name} {health_icon} {src['health_score']}分\n"
                message += f"   成功率{src['success_rate']}% | 满意度{src['satisfaction']}% | {src['subscribers']}人\n"
        
        if capabilities.get('supports_buttons'):
            buttons = [
                [
                    {"text": "🔄 刷新", "callback_data": "subscription:admin:analytics"},
                    {"text": "📊 统计", "callback_data": "subscription:admin:stats"}
                ],
                [
                    {"text": "🔙 返回", "callback_data": "subscription:admin:stats"},
                    {"text": "❌ 关闭", "callback_data": "subscription:exit"}
                ]
            ]
            keyboard = InlineKeyboard(buttons=buttons)
            return message, keyboard
        else:
            message += "\n\nr-刷新 | b-返回"
            return message, None
    
    # ==================== 订阅链接管理 ====================
    
    def build_link_list(self, capabilities: Dict[str, Any], page: int = 1) -> Tuple[str, Any]:
        """构建订阅链接列表"""
        links = self.source_manager.get_all_links()
        
        page_size = 5
        total_pages = max(1, (len(links) + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_links = links[start_idx:end_idx]
        
        # 统计
        total_sources = sum(link.source_count for link in links)
        
        message = f"""🔗 订阅链接管理

📊 统计: {len(links)} 个链接 | {total_sources} 个订阅源

"""
        
        if not page_links:
            message += "暂无订阅链接\n\n💡 点击下方按钮添加订阅链接"
        else:
            for i, link in enumerate(page_links, start=start_idx + 1):
                status_icon = '✅' if link.status == SourceStatus.ACTIVE else '⏸️'
                display_name = link.display_name or link.name
                message += f"{i}. {link.icon} {display_name}\n"
                message += f"   {status_icon} {link.source_count} 个订阅源\n"
        
        message += f"\n📄 第 {page}/{total_pages} 页"
        
        if capabilities.get('supports_buttons'):
            buttons = []
            
            # 链接操作按钮
            for link in page_links[:4]:
                display_name = link.display_name or link.name
                buttons.append([{
                    "text": f"📝 {display_name[:10]}",
                    "callback_data": f"subscription:admin:link:{link.id}"
                }])
            
            # 添加按钮
            buttons.append([
                {"text": "🔗 添加订阅链接", "callback_data": "subscription:admin:add_link"}
            ])
            
            # 切换到订阅源视图
            buttons.append([
                {"text": "📰 查看所有订阅源", "callback_data": "subscription:admin:list:1"}
            ])
            
            # 翻页
            nav_row = []
            if page > 1:
                nav_row.append({"text": "⬅️", "callback_data": f"subscription:admin:links:{page-1}"})
            if page < total_pages:
                nav_row.append({"text": "➡️", "callback_data": f"subscription:admin:links:{page+1}"})
            if nav_row:
                buttons.append(nav_row)
            
            buttons.append([
                {"text": "🔙 返回统计", "callback_data": "subscription:admin:stats"},
                {"text": "❌ 关闭", "callback_data": "subscription:exit"}
            ])
            
            keyboard = InlineKeyboard(buttons=buttons)
            return message, keyboard
        else:
            message += "\n\n操作: a-添加链接 | s-查看订阅源 | 数字-查看详情 | b-返回"
            return message, None
    
    def build_link_detail(self, link_id: int, capabilities: Dict[str, Any]) -> Tuple[str, Any]:
        """构建订阅链接详情"""
        link = self.source_manager.get_link(link_id)
        if not link:
            return "❌ 订阅链接不存在", None
        
        sources = self.source_manager.get_link_sources(link_id)
        status_name = self.STATUS_NAMES.get(link.status.value, '未知')
        
        message = f"""🔗 订阅链接详情

{link.icon} {link.display_name or link.name}

🔗 URL: {link.url}
📂 分类: {link.category or '未分类'}
📝 描述: {link.description or '无'}

{status_name} 状态
📰 订阅源数量: {len(sources)}

📅 创建时间: {link.created_at.strftime('%Y-%m-%d %H:%M') if link.created_at else '未知'}
"""
        
        if sources:
            message += "\n📋 包含的订阅源:\n"
            for i, source in enumerate(sources[:5], 1):
                message += f"  {i}. {source.icon} {source.get_display_title()}\n"
            if len(sources) > 5:
                message += f"  ... 还有 {len(sources) - 5} 个\n"
        
        if capabilities.get('supports_buttons'):
            buttons = []
            
            # 状态切换
            if link.status == SourceStatus.ACTIVE:
                buttons.append([
                    {"text": "⏸️ 停用链接", "callback_data": f"subscription:admin:disable_link:{link_id}"}
                ])
            else:
                buttons.append([
                    {"text": "✅ 启用链接", "callback_data": f"subscription:admin:enable_link:{link_id}"}
                ])
            
            # 查看订阅源
            if sources:
                buttons.append([
                    {"text": f"📰 查看订阅源 ({len(sources)})", "callback_data": f"subscription:admin:link_sources:{link_id}"}
                ])
            
            # 重新解析
            buttons.append([
                {"text": "🔄 重新解析", "callback_data": f"subscription:admin:reparse_link:{link_id}"}
            ])
            
            # 删除
            buttons.append([
                {"text": "🗑️ 删除链接", "callback_data": f"subscription:admin:delete_link:{link_id}"}
            ])
            
            buttons.append([
                {"text": "🔙 返回列表", "callback_data": "subscription:admin:links:1"},
                {"text": "❌ 关闭", "callback_data": "subscription:exit"}
            ])
            
            keyboard = InlineKeyboard(buttons=buttons)
            return message, keyboard
        else:
            message += "\n\n操作: e-启用/停用 | s-查看订阅源 | r-重新解析 | d-删除 | b-返回"
            return message, None
    
    def build_smart_add_menu(self, capabilities: Dict[str, Any]) -> Tuple[str, Any]:
        """构建智能解析菜单（添加订阅链接）"""
        # 从插件配置文件动态加载
        import importlib
        try:
            from .. import sources_config
            importlib.reload(sources_config)
            known_projects = sources_config.KNOWN_PROJECTS
        except ImportError:
            known_projects = {}
        
        message = """🔗 添加订阅链接

📌 支持的方式:
1. 选择已知API项目（推荐）
2. 直接输入URL自动解析

📋 已知API项目:
"""
        
        for i, (domain, project) in enumerate(known_projects.items(), 1):
            endpoint_count = len(project['endpoints'])
            message += f"{i}. {project['name']} ({endpoint_count}个端点)\n"
            message += f"   🔗 {domain}\n"
        
        message += """
💡 提示: 
- 选择已知项目可自动解析所有端点
- 直接发送URL也可自动检测
- 支持RSS/Atom和JSON API"""
        
        if capabilities.get('supports_buttons'):
            buttons = []
            
            # 已知项目按钮（每行2个）
            items = list(known_projects.items())
            for i in range(0, len(items), 2):
                row = []
                for domain, project in items[i:i+2]:
                    row.append({
                        "text": f"📦 {project['name']}",
                        "callback_data": f"subscription:admin:parse_known:{domain}"
                    })
                buttons.append(row)
            
            buttons.append([
                {"text": "🔙 返回链接列表", "callback_data": "subscription:admin:links:1"},
                {"text": "❌ 关闭", "callback_data": "subscription:exit"}
            ])
            
            keyboard = InlineKeyboard(buttons=buttons)
            return message, keyboard
        else:
            message += "\n\n直接输入URL | 输入序号选择项目 | b-返回"
            return message, None
    
    def build_parse_result(self, parse_result: Dict[str, Any], capabilities: Dict[str, Any], page: int = 1) -> Tuple[str, Any]:
        """构建解析结果页面（支持翻页）
        
        Args:
            parse_result: 解析结果
            capabilities: 平台能力
            page: 当前页码（从1开始）
        """
        if not parse_result['success']:
            message = f"❌ 解析失败\n\n{parse_result['message']}"
            if capabilities.get('supports_buttons'):
                buttons = [[
                    {"text": "🔙 返回", "callback_data": "subscription:admin:smart_add"},
                    {"text": "❌ 关闭", "callback_data": "subscription:exit"}
                ]]
                keyboard = InlineKeyboard(buttons=buttons)
                return message, keyboard
            return message, None
        
        sources = parse_result['sources']
        total = len(sources)
        
        # 检查哪些源已经添加过（通过URL匹配）
        existing_urls = set()
        if self.source_manager:
            for source in sources:
                url = source.get('url', '')
                if url and self.source_manager.get_source_by_url(url):
                    existing_urls.add(url)
        
        # 统计已添加和未添加数量
        added_count = len(existing_urls)
        not_added_count = total - added_count
        
        # 分页参数
        page_size = 6  # 每页显示6个端点
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))  # 确保页码有效
        
        start_idx = (page - 1) * page_size
        end_idx = min(start_idx + page_size, total)
        page_sources = sources[start_idx:end_idx]
        
        message = f"""✅ 解析成功！

📦 项目: {parse_result['project_name']}
📊 类型: {parse_result['type'].upper()}
📝 {parse_result['message']}

🔍 发现 {total} 个订阅源 (第 {page}/{total_pages} 页)
   ✅ 已添加: {added_count} | ⏳ 未添加: {not_added_count}

"""
        
        for i, source in enumerate(page_sources, start_idx + 1):
            url = source.get('url', '')
            is_added = url in existing_urls
            status_icon = "✅" if is_added else "⏳"
            message += f"{i}. {status_icon} {source['icon']} {source['display_name']}\n"
            desc = source.get('description', '')
            if len(desc) > 30:
                message += f"   {desc[:30]}...\n"
            elif desc:
                message += f"   {desc}\n"
        
        if capabilities.get('supports_buttons'):
            buttons = []
            
            # 全部添加按钮（只显示未添加数量）
            if not_added_count > 0:
                buttons.append([{
                    "text": f"✅ 添加全部未添加 ({not_added_count}个)",
                    "callback_data": "subscription:admin:add_all_parsed"
                }])
            else:
                buttons.append([{
                    "text": "✅ 全部已添加",
                    "callback_data": "subscription:admin:noop"
                }])
            
            # 当前页的端点按钮（每行2个）
            for i in range(0, len(page_sources), 2):
                row = []
                for j in range(2):
                    if i + j < len(page_sources):
                        source = page_sources[i + j]
                        global_idx = start_idx + i + j
                        display_name = source['display_name']
                        if len(display_name) > 10:
                            display_name = display_name[:10] + ".."
                        
                        url = source.get('url', '')
                        is_added = url in existing_urls
                        if is_added:
                            # 已添加的显示不同样式
                            row.append({
                                "text": f"✅ {display_name}",
                                "callback_data": f"subscription:admin:add_parsed:{global_idx}"
                            })
                        else:
                            row.append({
                                "text": f"➕ {display_name}",
                                "callback_data": f"subscription:admin:add_parsed:{global_idx}"
                            })
                if row:
                    buttons.append(row)
            
            # 翻页按钮（标准化格式）
            nav_row = []
            if page > 1:
                nav_row.append({"text": "⬅️ 上页", "callback_data": f"subscription:admin:parsed_page:{page-1}"})
            # 第三页及以上显示首页按钮
            if page >= 3:
                nav_row.append({"text": "🏠 首页", "callback_data": "subscription:admin:parsed_page:1"})
            if page < total_pages:
                nav_row.append({"text": "下页 ➡️", "callback_data": f"subscription:admin:parsed_page:{page+1}"})
            if nav_row:
                buttons.append(nav_row)
            
            buttons.append([
                {"text": "🔙 返回", "callback_data": "subscription:admin:smart_add"},
                {"text": "❌ 关闭", "callback_data": "subscription:exit"}
            ])
            
            keyboard = InlineKeyboard(buttons=buttons)
            return message, keyboard
        else:
            # 会话模式提示
            nav_hints = []
            if page > 1:
                nav_hints.append("p-上页")
            if page < total_pages:
                nav_hints.append("n-下页")
            nav_hints.extend(["a-全部添加", "序号-单独添加", "b-返回"])
            message += f"\n\n操作: {' | '.join(nav_hints)}"
            return message, None
    
    # ==================== 源详情 ====================
    
    def build_source_detail(self, source_id: int, capabilities: Dict[str, Any]) -> Tuple[str, Any]:
        """构建订阅源详情（包含运营数据）"""
        source = self.source_manager.get_source(source_id)
        if not source:
            return "❌ 订阅源不存在", None
        
        type_name = self.SOURCE_TYPE_NAMES.get(source.source_type.value, '未知')
        status_name = self.STATUS_NAMES.get(source.status.value, '未知')
        level_name = self.ACCESS_LEVEL_NAMES.get(source.access_level.value, '未知')
        
        # 获取运营统计数据
        stats = self.source_manager.get_source_stats(source_id)
        health_icon = self.source_manager.get_health_icon(stats.get('health_score', 100)) if stats else '🟢'
        
        message = f"""📰 订阅源详情

📌 名称: {source.name}
{source.icon} 类型: {type_name}
📝 描述: {source.description or '无'}

🔗 URL: {source.url[:50] + '...' if len(source.url) > 50 else source.url or '无'}
⏱️ 更新间隔: {source.update_interval // 60} 分钟

{status_name} 状态
{level_name} 访问级别
👥 订阅数: {source.current_subscribers}/{source.max_subscribers or '∞'}
"""
        
        # 运营数据部分
        if stats and stats.get('total_count', 0) > 0:
            message += f"""
━━ 运营数据 ━━
{health_icon} 健康度: {stats['health_score']}分
✅ 成功率: {stats['success_rate']}% ({stats['success_count']}/{stats['total_count']})
⏱️ 平均耗时: {stats['avg_fetch_time']}s
"""
            if stats.get('last_error_at'):
                message += f"🔴 最近错误: {stats['last_error_at'][:16]}\n"
                if stats.get('error_message'):
                    error_msg = stats['error_message'][:50] + '...' if len(stats.get('error_message', '')) > 50 else stats.get('error_message', '')
                    message += f"   {error_msg}\n"
        else:
            message += f"""
━━ 运营数据 ━━
{health_icon} 健康度: {stats.get('health_score', 100)}分
📊 暂无拉取记录
"""
        
        message += f"""
━━ 时间信息 ━━
📅 创建: {source.created_at.strftime('%Y-%m-%d %H:%M') if source.created_at else '未知'}
🔄 更新: {source.last_update.strftime('%Y-%m-%d %H:%M') if source.last_update else '从未'}
"""
        
        if source.error_message and not (stats and stats.get('last_error_at')):
            message += f"\n⚠️ 错误: {source.error_message}"
        
        if capabilities.get('supports_buttons'):
            buttons = []
            
            # 状态切换
            if source.status == SourceStatus.ACTIVE:
                buttons.append([
                    {"text": "⏸️ 停用", "callback_data": f"subscription:admin:disable:{source_id}"},
                    {"text": "🧪 测试", "callback_data": f"subscription:admin:test:{source_id}"}
                ])
            else:
                buttons.append([
                    {"text": "✅ 启用", "callback_data": f"subscription:admin:enable:{source_id}"},
                    {"text": "🧪 测试", "callback_data": f"subscription:admin:test:{source_id}"}
                ])
            
            # 编辑和删除
            buttons.append([
                {"text": "✏️ 编辑", "callback_data": f"subscription:admin:edit:{source_id}"},
                {"text": "🗑️ 删除", "callback_data": f"subscription:admin:delete:{source_id}"}
            ])
            
            # 访问级别
            buttons.append([
                {"text": "🔐 修改权限", "callback_data": f"subscription:admin:access:{source_id}"}
            ])
            
            buttons.append([
                {"text": "🔙 返回列表", "callback_data": "subscription:admin:list:1"},
                {"text": "❌ 关闭", "callback_data": "subscription:exit"}
            ])
            
            keyboard = InlineKeyboard(buttons=buttons)
            return message, keyboard
        else:
            message += "\n\n操作: e-编辑 | d-删除 | t-测试 | b-返回"
            return message, None
    
    # ==================== 批量操作 ====================
    
    def build_batch_operation_menu(self, capabilities: Dict[str, Any]) -> Tuple[str, Any]:
        """构建批量操作菜单"""
        all_sources = self.source_manager.get_all_sources()
        
        # 统计各状态数量
        status_counts = {'active': 0, 'inactive': 0, 'error': 0}
        for source in all_sources:
            status_counts[source.status.value] = status_counts.get(source.status.value, 0) + 1
        
        # 统计各分类数量
        category_counts = {}
        for source in all_sources:
            cat = source.category or "其他"
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        message = f"""📦 批量操作

📊 当前状态:
✅ 活跃: {status_counts.get('active', 0)} 个
⏸️ 停用: {status_counts.get('inactive', 0)} 个
🔴 错误: {status_counts.get('error', 0)} 个

📂 分类统计:
"""
        for cat, count in sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            message += f"• {cat}: {count} 个\n"
        
        message += "\n💡 选择要执行的批量操作"
        
        if capabilities.get('supports_buttons'):
            buttons = []
            
            # 按状态批量操作
            if status_counts.get('inactive', 0) > 0:
                buttons.append([{
                    "text": f"✅ 启用所有停用 ({status_counts.get('inactive', 0)})",
                    "callback_data": "subscription:admin:batch_enable:inactive"
                }])
            
            if status_counts.get('error', 0) > 0:
                buttons.append([{
                    "text": f"🔄 重试错误源 ({status_counts.get('error', 0)})",
                    "callback_data": "subscription:admin:batch_enable:error"
                }])
            
            if status_counts.get('active', 0) > 0:
                buttons.append([{
                    "text": f"⏸️ 停用所有活跃 ({status_counts.get('active', 0)})",
                    "callback_data": "subscription:admin:batch_disable:active"
                }])
            
            # 按分类批量操作
            if len(category_counts) > 1:
                buttons.append([{
                    "text": "📂 按分类批量操作...",
                    "callback_data": "subscription:admin:batch_by_category"
                }])
            
            buttons.append([
                {"text": "🔙 返回列表", "callback_data": "subscription:admin:list:1"},
                {"text": "❌ 关闭", "callback_data": "subscription:exit"}
            ])
            
            keyboard = InlineKeyboard(buttons=buttons)
            return message, keyboard
        else:
            message += "\n\n1-启用所有停用 | 2-停用所有活跃 | b-返回"
            return message, None
    
    def build_batch_by_category_menu(self, capabilities: Dict[str, Any]) -> Tuple[str, Any]:
        """构建按分类批量操作菜单"""
        all_sources = self.source_manager.get_all_sources()
        
        # 统计各分类
        category_stats = {}
        for source in all_sources:
            cat = source.category or "其他"
            if cat not in category_stats:
                category_stats[cat] = {'total': 0, 'active': 0}
            category_stats[cat]['total'] += 1
            if source.status == SourceStatus.ACTIVE:
                category_stats[cat]['active'] += 1
        
        message = """📂 按分类批量操作

选择分类后可批量启用/停用该分类下所有源

"""
        for cat, stats in sorted(category_stats.items(), key=lambda x: x[1]['total'], reverse=True):
            message += f"• {cat}: {stats['active']}/{stats['total']} 活跃\n"
        
        if capabilities.get('supports_buttons'):
            buttons = []
            
            # 每个分类一行
            for cat, stats in sorted(category_stats.items(), key=lambda x: x[1]['total'], reverse=True)[:6]:
                row = []
                if stats['active'] < stats['total']:
                    row.append({
                        "text": f"✅ {cat[:5]}",
                        "callback_data": f"subscription:admin:batch_cat_enable:{cat}"
                    })
                if stats['active'] > 0:
                    row.append({
                        "text": f"⏸️ {cat[:5]}",
                        "callback_data": f"subscription:admin:batch_cat_disable:{cat}"
                    })
                if row:
                    buttons.append(row)
            
            buttons.append([
                {"text": "🔙 返回批量操作", "callback_data": "subscription:admin:batch"},
                {"text": "❌ 关闭", "callback_data": "subscription:exit"}
            ])
            
            keyboard = InlineKeyboard(buttons=buttons)
            return message, keyboard
        else:
            message += "\n\nb-返回"
            return message, None
    
    # ==================== 搜索功能 ====================
    
    def build_search_menu(self, capabilities: Dict[str, Any], keyword: str = None, 
                          results: List = None) -> Tuple[str, Any]:
        """构建搜索菜单/结果"""
        if results is not None:
            # 显示搜索结果
            if not results:
                message = f"""🔍 搜索结果

关键词: {keyword}

未找到匹配的订阅源"""
            else:
                message = f"""🔍 搜索结果

关键词: {keyword}
找到 {len(results)} 个匹配:

"""
                for i, source in enumerate(results[:10], 1):
                    status_icon = '✅' if source.status == SourceStatus.ACTIVE else ('🔴' if source.status == SourceStatus.ERROR else '⏸️')
                    message += f"{i}. {source.icon} {source.get_display_title()} {status_icon}\n"
            
            if capabilities.get('supports_buttons'):
                buttons = []
                
                # 搜索结果按钮
                for source in results[:8]:
                    display_title = source.get_display_title()
                    buttons.append([{
                        "text": f"📝 {display_title[:12]}",
                        "callback_data": f"subscription:admin:source:{source.id}"
                    }])
                
                buttons.append([
                    {"text": "🔍 重新搜索", "callback_data": "subscription:admin:search"},
                    {"text": "🔙 返回列表", "callback_data": "subscription:admin:list:1"}
                ])
                
                keyboard = InlineKeyboard(buttons=buttons)
                return message, keyboard
            else:
                message += "\n\n输入序号查看详情 | s-重新搜索 | b-返回"
                return message, None
        else:
            # 显示搜索输入页
            # 获取状态统计
            all_sources = self.source_manager.get_all_sources()
            status_counts = {'active': 0, 'inactive': 0, 'error': 0}
            for source in all_sources:
                status_counts[source.status.value] = status_counts.get(source.status.value, 0) + 1
            
            message = f"""🔍 订阅源搜索

📊 当前共 {len(all_sources)} 个订阅源

💡 请发送关键词进行搜索
或点击下方按钮快速筛选"""
            
            if capabilities.get('supports_buttons'):
                buttons = []
                
                # 状态快捷筛选
                status_row = []
                if status_counts.get('active', 0) > 0:
                    status_row.append({
                        "text": f"✅ 活跃({status_counts.get('active', 0)})",
                        "callback_data": "subscription:admin:list:1::active"
                    })
                if status_counts.get('inactive', 0) > 0:
                    status_row.append({
                        "text": f"⏸️ 停用({status_counts.get('inactive', 0)})",
                        "callback_data": "subscription:admin:list:1::inactive"
                    })
                if status_counts.get('error', 0) > 0:
                    status_row.append({
                        "text": f"🔴 错误({status_counts.get('error', 0)})",
                        "callback_data": "subscription:admin:list:1::error"
                    })
                if status_row:
                    buttons.append(status_row)
                
                # 分类快捷筛选
                categories = self.source_manager.get_all_categories()
                if categories:
                    cat_row = []
                    for cat in categories[:4]:
                        cat_row.append({
                            "text": f"📂 {cat[:5]}",
                            "callback_data": f"subscription:admin:list:1:{cat}"
                        })
                    if cat_row:
                        buttons.append(cat_row)
                
                buttons.append([
                    {"text": "🔙 返回列表", "callback_data": "subscription:admin:list:1"},
                    {"text": "❌ 关闭", "callback_data": "subscription:exit"}
                ])
                
                keyboard = InlineKeyboard(buttons=buttons)
                return message, keyboard
            else:
                message += "\n\n输入关键词搜索 | b-返回"
                return message, None
    
    # ==================== 访问级别设置 ====================
    
    def build_access_level_menu(self, source_id: int, capabilities: Dict[str, Any]) -> Tuple[str, Any]:
        """构建访问级别设置菜单"""
        source = self.source_manager.get_source(source_id)
        if not source:
            return "❌ 订阅源不存在", None
        
        current_level = self.ACCESS_LEVEL_NAMES.get(source.access_level.value, '未知')
        
        message = f"""🔐 设置访问级别

订阅源: {source.name}
当前级别: {current_level}

选择新的访问级别:
"""
        
        if capabilities.get('supports_buttons'):
            buttons = []
            
            for level in AccessLevel:
                level_name = self.ACCESS_LEVEL_NAMES.get(level.value, str(level.value))
                is_current = "✓ " if level == source.access_level else ""
                buttons.append([{
                    "text": f"{is_current}{level_name}",
                    "callback_data": f"subscription:admin:set_access:{source_id}:{level.value}"
                }])
            
            buttons.append([
                {"text": "🔙 返回详情", "callback_data": f"subscription:admin:source:{source_id}"},
                {"text": "❌ 关闭", "callback_data": "subscription:exit"}
            ])
            
            keyboard = InlineKeyboard(buttons=buttons)
            return message, keyboard
        else:
            for level in AccessLevel:
                level_name = self.ACCESS_LEVEL_NAMES.get(level.value, str(level.value))
                message += f"\n{level.value}. {level_name}"
            message += "\n\n输入数字选择 | b-返回"
            return message, None
    
    # ==================== 删除确认 ====================
    
    def build_delete_confirm(self, source_id: int, capabilities: Dict[str, Any]) -> Tuple[str, Any]:
        """构建删除确认"""
        source = self.source_manager.get_source(source_id)
        if not source:
            return "❌ 订阅源不存在", None
        
        message = f"""⚠️ 确认删除订阅源?

📰 名称: {source.name}
👥 当前订阅数: {source.current_subscribers}

⚠️ 此操作不可恢复！
删除后，所有订阅此源的用户将失去订阅。"""
        
        if capabilities.get('supports_buttons'):
            buttons = [
                [
                    {"text": "✅ 确认删除", "callback_data": f"subscription:admin:confirm_delete:{source_id}"},
                    {"text": "❌ 取消", "callback_data": f"subscription:admin:source:{source_id}"}
                ]
            ]
            keyboard = InlineKeyboard(buttons=buttons)
            return message, keyboard
        else:
            message += "\n\n输入 yes 确认删除 | b-取消"
            return message, None
    
    # ==================== 操作处理 ====================
    
    async def handle_callback(self, event: AstrMessageEvent, action: str, params: List[str], capabilities: Dict[str, Any], subscription_manager=None):
        """处理管理员回调"""
        
        # ==================== 订阅统计 ====================
        
        if action == "stats":
            # 订阅统计页面
            message, keyboard = self.build_stats_page(capabilities, subscription_manager)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
            return
        
        if action == "analytics":
            # 运营数据分析页面
            message, keyboard = self.build_analytics_page(capabilities, subscription_manager)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
            return
        
        # ==================== 订阅链接管理 ====================
        
        if action == "links":
            # 订阅链接列表
            page = int(params[0]) if params else 1
            message, keyboard = self.build_link_list(capabilities, page)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "link":
            # 订阅链接详情
            link_id = int(params[0]) if params else 0
            message, keyboard = self.build_link_detail(link_id, capabilities)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "add_link":
            # 添加订阅链接
            message, keyboard = self.build_smart_add_menu(capabilities)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "enable_link":
            # 启用订阅链接
            link_id = int(params[0]) if params else 0
            link = self.source_manager.get_link(link_id)
            if link:
                link.status = SourceStatus.ACTIVE
                self.source_manager.update_link(link)
                # 同时启用所有订阅源
                for source in self.source_manager.get_link_sources(link_id):
                    source.status = SourceStatus.ACTIVE
                    self.source_manager.update_source(source)
            message, keyboard = self.build_link_detail(link_id, capabilities)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "disable_link":
            # 停用订阅链接
            link_id = int(params[0]) if params else 0
            link = self.source_manager.get_link(link_id)
            if link:
                link.status = SourceStatus.INACTIVE
                self.source_manager.update_link(link)
                # 同时停用所有订阅源
                for source in self.source_manager.get_link_sources(link_id):
                    source.status = SourceStatus.INACTIVE
                    self.source_manager.update_source(source)
            message, keyboard = self.build_link_detail(link_id, capabilities)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "delete_link":
            # 删除订阅链接
            link_id = int(params[0]) if params else 0
            self.source_manager.delete_link(link_id)
            message = "✅ 订阅链接已删除"
            if capabilities.get('supports_buttons'):
                buttons = [[
                    {"text": "🔙 返回列表", "callback_data": "subscription:admin:links:1"}
                ]]
                keyboard = InlineKeyboard(buttons=buttons)
            else:
                keyboard = None
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "link_sources":
            # 查看订阅链接下的订阅源
            link_id = int(params[0]) if params else 0
            message, keyboard = self.build_source_list(capabilities, 1, None, link_id)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        # ==================== 订阅源管理 ====================
        
        elif action == "list":
            page = int(params[0]) if params else 1
            category = params[1] if len(params) > 1 and params[1] else None
            status_filter = params[2] if len(params) > 2 and params[2] else None
            message, keyboard = self.build_source_list(capabilities, page, category, status_filter=status_filter)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        # ==================== 快捷状态切换 ====================
        
        elif action == "quick_enable":
            source_id = int(params[0]) if params else 0
            source = self.source_manager.get_source(source_id)
            if source:
                source.status = SourceStatus.ACTIVE
                self.source_manager.update_source(source)
            # 返回列表
            message, keyboard = self.build_source_list(capabilities, 1)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "quick_disable":
            source_id = int(params[0]) if params else 0
            source = self.source_manager.get_source(source_id)
            if source:
                source.status = SourceStatus.INACTIVE
                self.source_manager.update_source(source)
            # 返回列表
            message, keyboard = self.build_source_list(capabilities, 1)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        # ==================== 批量操作 ====================
        
        elif action == "batch":
            message, keyboard = self.build_batch_operation_menu(capabilities)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "batch_by_category":
            message, keyboard = self.build_batch_by_category_menu(capabilities)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "batch_enable":
            # 批量启用指定状态的源
            status_filter = params[0] if params else "inactive"
            all_sources = self.source_manager.get_all_sources()
            source_ids = [s.id for s in all_sources if s.status.value == status_filter]
            count = self.source_manager.batch_update_status(source_ids, SourceStatus.ACTIVE)
            message = f"✅ 已启用 {count} 个订阅源"
            if capabilities.get('supports_buttons'):
                buttons = [[
                    {"text": "🔙 返回批量操作", "callback_data": "subscription:admin:batch"},
                    {"text": "📊 查看列表", "callback_data": "subscription:admin:list:1"}
                ]]
                keyboard = InlineKeyboard(buttons=buttons)
            else:
                keyboard = None
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "batch_disable":
            # 批量停用指定状态的源
            status_filter = params[0] if params else "active"
            all_sources = self.source_manager.get_all_sources()
            source_ids = [s.id for s in all_sources if s.status.value == status_filter]
            count = self.source_manager.batch_update_status(source_ids, SourceStatus.INACTIVE)
            message = f"⏸️ 已停用 {count} 个订阅源"
            if capabilities.get('supports_buttons'):
                buttons = [[
                    {"text": "🔙 返回批量操作", "callback_data": "subscription:admin:batch"},
                    {"text": "📊 查看列表", "callback_data": "subscription:admin:list:1"}
                ]]
                keyboard = InlineKeyboard(buttons=buttons)
            else:
                keyboard = None
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "batch_cat_enable":
            # 按分类批量启用
            category = params[0] if params else ""
            all_sources = self.source_manager.get_all_sources()
            source_ids = [s.id for s in all_sources if (s.category or "其他") == category and s.status != SourceStatus.ACTIVE]
            count = self.source_manager.batch_update_status(source_ids, SourceStatus.ACTIVE)
            message = f"✅ 已启用 {category} 分类下 {count} 个订阅源"
            if capabilities.get('supports_buttons'):
                buttons = [[
                    {"text": "🔙 返回分类操作", "callback_data": "subscription:admin:batch_by_category"},
                    {"text": "📊 查看列表", "callback_data": "subscription:admin:list:1"}
                ]]
                keyboard = InlineKeyboard(buttons=buttons)
            else:
                keyboard = None
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "batch_cat_disable":
            # 按分类批量停用
            category = params[0] if params else ""
            all_sources = self.source_manager.get_all_sources()
            source_ids = [s.id for s in all_sources if (s.category or "其他") == category and s.status == SourceStatus.ACTIVE]
            count = self.source_manager.batch_update_status(source_ids, SourceStatus.INACTIVE)
            message = f"⏸️ 已停用 {category} 分类下 {count} 个订阅源"
            if capabilities.get('supports_buttons'):
                buttons = [[
                    {"text": "🔙 返回分类操作", "callback_data": "subscription:admin:batch_by_category"},
                    {"text": "📊 查看列表", "callback_data": "subscription:admin:list:1"}
                ]]
                keyboard = InlineKeyboard(buttons=buttons)
            else:
                keyboard = None
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        # ==================== 搜索功能 ====================
        
        elif action == "search":
            message, keyboard = self.build_search_menu(capabilities)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "do_search":
            # 执行搜索（从会话中获取关键词）
            keyword = params[0] if params else ""
            results = self.source_manager.search_sources(keyword=keyword) if keyword else []
            message, keyboard = self.build_search_menu(capabilities, keyword=keyword, results=results)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "add_preset":
            message, keyboard = self.build_preset_list(capabilities)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "smart_add":
            message, keyboard = self.build_smart_add_menu(capabilities)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "parse_known":
            # 解析已知项目并创建订阅链接
            domain = params[0] if params else ""
            url = f"https://{domain}/"
            parse_result = await URLParser.parse_url(url)
            
            # 保存解析结果到临时存储
            self._last_parse_result = parse_result
            self._last_parse_url = url
            self._last_parse_domain = domain
            
            message, keyboard = self.build_parse_result(parse_result, capabilities, page=1)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "parsed_page":
            # 解析结果翻页
            page = int(params[0]) if params else 1
            
            if not hasattr(self, '_last_parse_result') or not self._last_parse_result:
                yield event.plain_result("❌ 解析结果已过期，请重新解析")
                return
            
            message, keyboard = self.build_parse_result(self._last_parse_result, capabilities, page=page)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "noop":
            # 空操作（如全部已添加时点击按钮）
            return
        
        elif action == "add_all_parsed":
            # 添加订阅链接和所有未添加的订阅源
            if not hasattr(self, '_last_parse_result') or not self._last_parse_result:
                yield event.plain_result("❌ 没有待添加的订阅源")
                return
            
            user_id = get_unified_user_id(event)
            parse_result = self._last_parse_result
            sources = parse_result.get('sources', [])
            
            # 过滤掉已添加的源
            sources_to_add = []
            for source_data in sources:
                url = source_data.get('url', '')
                if url and not self.source_manager.get_source_by_url(url):
                    sources_to_add.append(source_data)
            
            if not sources_to_add:
                yield event.plain_result("✅ 所有订阅源都已添加过了")
                return
            
            # 1. 检查是否已有订阅链接
            existing_link = self.source_manager.get_link_by_url(getattr(self, '_last_parse_url', ''))
            if existing_link:
                link_id = existing_link.id
            else:
                # 创建新的订阅链接
                link = SubscriptionLink(
                    name=getattr(self, '_last_parse_domain', 'unknown'),
                    display_name=parse_result.get('project_name', ''),
                    url=getattr(self, '_last_parse_url', ''),
                    category=sources_to_add[0].get('category', '其他') if sources_to_add else '其他',
                    description=f"包含 {len(sources)} 个订阅源",
                    icon='🔗',
                    source_count=len(sources),
                    created_by=user_id
                )
                link_id = self.source_manager.create_link(link)
            
            # 2. 创建未添加的订阅源
            added_count = 0
            for source_data in sources_to_add:
                try:
                    source = SubscriptionSource(
                        name=source_data['name'],
                        display_name=source_data['display_name'],
                        source_type=SourceType.API,
                        category=source_data.get('category', '其他'),
                        description=source_data.get('description', ''),
                        icon=source_data.get('icon', '📰'),
                        link_id=link_id,
                        url=source_data['url'],
                        parser_config=source_data.get('parser_config', {}),
                        created_by=user_id
                    )
                    self.source_manager.create_source(source)
                    added_count += 1
                except Exception as e:
                    logger.error(f"[SourceAdmin] 添加订阅源失败: {e}")
            
            # 清理临时数据
            self._last_parse_result = None
            self._last_parse_url = None
            self._last_parse_domain = None
            
            message = f"✅ 订阅链接添加成功！\n\n🔗 {parse_result.get('project_name', '')}\n📰 已添加 {added_count} 个订阅源"
            
            if capabilities.get('supports_buttons'):
                buttons = [[
                    {"text": "🔗 查看链接列表", "callback_data": "subscription:admin:links:1"},
                    {"text": "📰 查看订阅源", "callback_data": "subscription:admin:list:1"}
                ], [
                    {"text": "❌ 关闭", "callback_data": "subscription:exit"}
                ]]
                keyboard = InlineKeyboard(buttons=buttons)
            else:
                keyboard = None
            
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "add_parsed":
            # 添加单个解析的订阅源
            index = int(params[0]) if params else 0
            
            if not hasattr(self, '_last_parse_result') or not self._last_parse_result:
                yield event.plain_result("❌ 没有待添加的订阅源")
                return
            
            sources = self._last_parse_result.get('sources', [])
            if index >= len(sources):
                yield event.plain_result("❌ 无效的索引")
                return
            
            user_id = get_unified_user_id(event)
            source_data = sources[index]
            
            try:
                source = SubscriptionSource(
                    name=source_data['name'],
                    display_name=source_data['display_name'],
                    source_type=SourceType.API,
                    category=source_data.get('category', '其他'),
                    description=source_data.get('description', ''),
                    icon=source_data.get('icon', '📰'),
                    url=source_data['url'],
                    parser_config=source_data.get('parser_config', {}),
                    created_by=user_id
                )
                source_id = self.source_manager.create_source(source)
                message = f"✅ 订阅源添加成功！\n\n{source_data['icon']} {source_data['display_name']}\n🆔 ID: {source_id}"
            except Exception as e:
                message = f"❌ 添加失败: {e}"
            
            if capabilities.get('supports_buttons'):
                buttons = [[
                    {"text": "📋 查看列表", "callback_data": "subscription:admin:list:1"},
                    {"text": "🔙 返回解析", "callback_data": "subscription:admin:smart_add"}
                ]]
                keyboard = InlineKeyboard(buttons=buttons)
            else:
                keyboard = None
            
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "create_preset":
            preset_name = params[0] if params else ""
            user_id = get_unified_user_id(event)
            
            source_id = self.source_manager.create_preset_source(preset_name, user_id)
            if source_id:
                message = f"✅ 订阅源创建成功！\n\n📰 {preset_name}\n🆔 ID: {source_id}"
            else:
                message = f"❌ 创建失败，预置源 {preset_name} 不存在"
            
            if capabilities.get('supports_buttons'):
                buttons = [[
                    {"text": "📋 查看列表", "callback_data": "subscription:admin:list:1"},
                    {"text": "❌ 关闭", "callback_data": "subscription:exit"}
                ]]
                keyboard = InlineKeyboard(buttons=buttons)
            else:
                keyboard = None
            
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "source":
            source_id = int(params[0]) if params else 0
            message, keyboard = self.build_source_detail(source_id, capabilities)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "enable":
            source_id = int(params[0]) if params else 0
            source = self.source_manager.get_source(source_id)
            if source:
                source.status = SourceStatus.ACTIVE
                self.source_manager.update_source(source)
                message = f"✅ 订阅源 {source.name} 已启用"
            else:
                message = "❌ 订阅源不存在"
            
            # 返回详情页
            detail_msg, keyboard = self.build_source_detail(source_id, capabilities)
            async for result in MessageEditor.edit_or_send(event, detail_msg, keyboard):
                yield result
        
        elif action == "disable":
            source_id = int(params[0]) if params else 0
            source = self.source_manager.get_source(source_id)
            if source:
                source.status = SourceStatus.INACTIVE
                self.source_manager.update_source(source)
            
            detail_msg, keyboard = self.build_source_detail(source_id, capabilities)
            async for result in MessageEditor.edit_or_send(event, detail_msg, keyboard):
                yield result
        
        elif action == "access":
            source_id = int(params[0]) if params else 0
            message, keyboard = self.build_access_level_menu(source_id, capabilities)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "set_access":
            source_id = int(params[0]) if params else 0
            level = int(params[1]) if len(params) > 1 else 0
            
            source = self.source_manager.get_source(source_id)
            if source:
                source.access_level = AccessLevel(level)
                self.source_manager.update_source(source)
            
            detail_msg, keyboard = self.build_source_detail(source_id, capabilities)
            async for result in MessageEditor.edit_or_send(event, detail_msg, keyboard):
                yield result
        
        elif action == "delete":
            source_id = int(params[0]) if params else 0
            message, keyboard = self.build_delete_confirm(source_id, capabilities)
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "confirm_delete":
            source_id = int(params[0]) if params else 0
            source = self.source_manager.get_source(source_id)
            source_name = source.name if source else "未知"
            
            if self.source_manager.delete_source(source_id):
                message = f"✅ 订阅源 {source_name} 已删除"
            else:
                message = "❌ 删除失败"
            
            if capabilities.get('supports_buttons'):
                buttons = [[
                    {"text": "📋 返回列表", "callback_data": "subscription:admin:list:1"},
                    {"text": "❌ 关闭", "callback_data": "subscription:exit"}
                ]]
                keyboard = InlineKeyboard(buttons=buttons)
            else:
                keyboard = None
            
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "test":
            source_id = int(params[0]) if params else 0
            source = self.source_manager.get_source(source_id)
            
            if not source:
                yield event.plain_result("❌ 订阅源不存在")
                return
            
            # 验证源
            valid, msg = await self.source_manager.validate_source(source)
            
            if valid:
                # 尝试获取内容
                result = await self.source_manager.fetch_source_content(source_id)
                # fetch_source_content 返回 (List[SourceContent], str) 元组
                if isinstance(result, tuple):
                    contents, content_hash = result
                else:
                    contents = result
                
                if contents:
                    first_content = contents[0]
                    title = first_content.title if hasattr(first_content, 'title') else str(first_content)
                    preview = title[:50] + "..." if len(title) > 50 else title
                    message = f"✅ 测试成功！\n\n获取到 {len(contents)} 条内容\n预览: {preview}"
                else:
                    message = f"⚠️ 连接成功但未获取到内容\n{msg}"
            else:
                message = f"❌ 测试失败\n{msg}"
            
            if capabilities.get('supports_buttons'):
                buttons = [[
                    {"text": "🔙 返回详情", "callback_data": f"subscription:admin:source:{source_id}"},
                    {"text": "❌ 关闭", "callback_data": "subscription:exit"}
                ]]
                keyboard = InlineKeyboard(buttons=buttons)
            else:
                keyboard = None
            
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        elif action == "add_custom":
            message = """➕ 添加自定义订阅源

请按以下格式发送配置:

```
名称: 源名称
类型: rss/api
URL: https://example.com/feed
描述: 源描述（可选）
```

支持的类型:
• rss - RSS/Atom订阅
• api - REST API接口

💡 提示: 也可以直接发送RSS链接快速添加"""
            
            if capabilities.get('supports_buttons'):
                buttons = [[
                    {"text": "🔙 返回列表", "callback_data": "subscription:admin:list:1"},
                    {"text": "❌ 关闭", "callback_data": "subscription:exit"}
                ]]
                keyboard = InlineKeyboard(buttons=buttons)
            else:
                keyboard = None
            
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        
        else:
            yield event.plain_result(f"❌ 未知操作: {action}")
