"""
订阅插件响应构建器
支持按钮模式和会话模式的跨平台响应构建
"""
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

plugin_root = Path(__file__).parent.parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))
from common.message_formatter import get_separator

try:
    from astrbot.api import logger
    from astrbot.core.message.components import Plain
    from astrbot.core.message.message_event_result import MessageEventResult
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

try:
    from common import BaseResponseBuilder
except ImportError:
    BaseResponseBuilder = object
    logger.warning("[SubscriptionResponseBuilder] BaseResponseBuilder 不可用")


class SubscriptionResponseBuilder(BaseResponseBuilder):
    """订阅插件响应构建器"""
    
    # 插件名称映射
    PLUGIN_NAMES = {
        'music': '🎵 音乐',
        'book': '📚 书籍',
        'douban': '🎬 豆瓣',
        'pansou': '☁️ 云盘'
    }
    
    # 订阅类型映射
    SUBSCRIPTION_TYPES = {
        'ranking': '📊 热搜榜',
        'keyword': '🔍 关键词',
        'new_entry': '🆕 新上榜',
        'rising': '📈 飙升榜'
    }
    
    def __init__(self, capabilities: Dict[str, Any]):
        """
        初始化响应构建器
        
        Args:
            capabilities: 平台能力字典
        """
        if BaseResponseBuilder != object:
            super().__init__(capabilities)
        self.capabilities = capabilities
        self.supports_buttons = capabilities.get('supports_buttons', False)
    
    def build_main_menu(self, user_subscriptions: List = None, available_sources: List = None, 
                        max_subscriptions: int = 3, user_level: str = "免费用户",
                        hot_sources: List = None) -> Tuple[str, Any]:
        """
        构建主菜单（统一使用订阅源）
        
        Args:
            user_subscriptions: 用户当前订阅列表
            available_sources: 可用订阅源列表
            max_subscriptions: 最大订阅数（-1表示无限）
            user_level: 用户等级名称
            hot_sources: 热门订阅源列表（用于快捷订阅）
            
        Returns:
            (消息文本, 键盘)
        """
        sub_count = len(user_subscriptions) if user_subscriptions else 0
        source_count = len(available_sources) if available_sources else 0
        
        # 显示订阅配额
        if max_subscriptions == -1:
            quota_str = f"{sub_count}/∞"
        else:
            quota_str = f"{sub_count}/{max_subscriptions}"
        
        message = f"""📬 订阅中心

👤 {user_level} | 📊 {quota_str}
"""
        
        # 显示热门推荐（最多3个）
        if hot_sources and self.supports_buttons:
            message += "\n🔥 热门推荐:\n"
            for source in hot_sources[:3]:
                display_title = source.get_display_title() if hasattr(source, 'get_display_title') else source.display_name or source.name
                icon = source.icon if hasattr(source, 'icon') else '📰'
                message += f"  {icon} {display_title}\n"
        
        if self.supports_buttons:
            buttons = []
            
            # 热门订阅源快捷按钮（一键订阅）
            if hot_sources:
                hot_row = []
                for source in hot_sources[:3]:
                    display_title = source.get_display_title() if hasattr(source, 'get_display_title') else source.display_name or source.name
                    icon = source.icon if hasattr(source, 'icon') else '📰'
                    hot_row.append({
                        "text": f"{icon} {display_title[:6]}",
                        "callback_data": f"subscription:quick_sub:{source.id}"
                    })
                if hot_row:
                    buttons.append(hot_row)
            
            # 浏览订阅源
            buttons.append([
                {"text": "📰 浏览全部订阅源", "callback_data": "subscription:browse_sources:1"}
            ])
            
            # 管理功能
            if sub_count > 0:
                buttons.append([
                    {"text": f"📋 我的订阅({sub_count})", "callback_data": "subscription:list"},
                    {"text": "⚙️ 设置", "callback_data": "subscription:settings"}
                ])
            else:
                buttons.append([
                    {"text": "⚙️ 推送设置", "callback_data": "subscription:settings"}
                ])
            
            # 快捷功能
            buttons.append([
                {"text": "🔥 查看热门", "callback_data": "subscription:view_hot"},
                {"text": "📝 申请订阅源", "callback_data": "subscription:request"}
            ])
            
            buttons.append([
                {"text": "❓ 使用帮助", "callback_data": "subscription:help"},
                {"text": "❌ 退出", "callback_data": "subscription:exit"}
            ])
            
            keyboard = self._create_keyboard(buttons)
            return message, keyboard
        else:
            message += """

1. 浏览订阅源 - 查看可订阅的内容源
2. 我的订阅 - 查看和管理现有订阅
3. 推送设置 - 时间和频率设置
4. 查看热门 - 实时热搜榜单
5. 使用帮助 - 订阅功能说明

💡 输入数字选择功能 | 0-退出"""
            return message, None
    
    def build_source_browse(self, sources: List, page: int = 1, category: str = None) -> Tuple[str, Any]:
        """
        构建订阅源浏览页面
        
        Args:
            sources: 订阅源列表
            page: 当前页码
            category: 筛选分类
        """
        # 空列表处理
        if not sources:
            message = """📰 可订阅内容源

暂无可用的订阅源

💡 管理员可通过 /管理 → 订阅源管理 添加订阅源"""
            
            if self.supports_buttons:
                buttons = [[
                    {"text": "🏠 返回首页", "callback_data": "subscription:home"},
                    {"text": "❌ 退出", "callback_data": "subscription:exit"}
                ]]
                keyboard = self._create_keyboard(buttons)
                return message, keyboard
            else:
                message += "\n\n💡 h-返回首页 | 0-退出"
                return message, None
        
        # 按分类分组
        categories = {}
        for source in sources:
            cat = source.category or "其他"
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(source)
        
        # 分页
        page_size = 6
        total_pages = max(1, (len(sources) + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_sources = sources[start_idx:end_idx]
        
        message = f"""📰 可订阅内容源 ({len(sources)} 个)

"""
        # 显示分类统计
        cat_stats = " | ".join([f"{k}:{len(v)}" for k, v in categories.items()])
        message += f"📂 分类: {cat_stats}\n\n"
        
        # 访问等级标识
        ACCESS_LEVEL_ICONS = {
            0: '',       # PUBLIC - 无标识
            1: '👤',     # REGISTERED
            2: '⭐',     # MEMBER
            3: '💎',     # VIP
        }
        
        # 显示当前页的订阅源
        for i, source in enumerate(page_sources, start=start_idx + 1):
            display_title = source.get_display_title()
            access_icon = ACCESS_LEVEL_ICONS.get(source.access_level.value, '')
            message += f"{i}. {source.icon} {display_title} {access_icon}\n"
            if source.description:
                desc = source.description[:25] + "..." if len(source.description) > 25 else source.description
                message += f"   {desc}\n"
        
        message += f"\n📄 第 {page}/{total_pages} 页"
        
        if self.supports_buttons:
            buttons = []
            
            # 订阅源按钮（每行2个）
            for i in range(0, len(page_sources), 2):
                row = []
                for source in page_sources[i:i+2]:
                    display_title = source.get_display_title()
                    row.append({
                        "text": f"{source.icon} {display_title[:8]}",
                        "callback_data": f"subscription:source_detail:{source.id}"
                    })
                if row:
                    buttons.append(row)
            
            # 分类筛选（始终显示，方便扩展）
            cat_row = []
            # 如果当前有筛选，显示"全部"按钮
            if category:
                cat_row.append({
                    "text": "📂 全部",
                    "callback_data": "subscription:browse_sources:1"
                })
            # 显示各分类
            for cat in list(categories.keys())[:4]:
                if cat != category:  # 不显示当前选中的分类
                    cat_row.append({
                        "text": f"📂 {cat}",
                        "callback_data": f"subscription:browse_sources:1:{cat}"
                    })
            if cat_row:
                buttons.append(cat_row)
            
            # 翻页
            nav_row = []
            if page > 1:
                nav_row.append({"text": "⬅️ 上一页", "callback_data": f"subscription:browse_sources:{page-1}"})
            if page < total_pages:
                nav_row.append({"text": "➡️ 下一页", "callback_data": f"subscription:browse_sources:{page+1}"})
            if nav_row:
                buttons.append(nav_row)
            
            buttons.append([
                {"text": "🏠 返回首页", "callback_data": "subscription:home"},
                {"text": "❌ 退出", "callback_data": "subscription:exit"}
            ])
            
            keyboard = self._create_keyboard(buttons)
            return message, keyboard
        else:
            message += "\n\n💡 输入序号查看详情 | h-返回首页 | 0-退出"
            return message, None
    
    def build_source_detail(self, source, is_subscribed: bool = False) -> Tuple[str, Any]:
        """
        构建订阅源详情页面
        """
        display_title = source.get_display_title()
        
        message = f"""{source.icon} {display_title}

📝 {source.description or '暂无描述'}

📂 分类: {source.category or '未分类'}
⏰ 更新间隔: {source.update_interval // 60} 分钟
👥 订阅人数: {source.current_subscribers}
"""
        
        if is_subscribed:
            message += "\n✅ 已订阅"
        
        if self.supports_buttons:
            buttons = []
            
            if is_subscribed:
                buttons.append([
                    {"text": "❌ 取消订阅", "callback_data": f"subscription:unsubscribe:{source.id}"}
                ])
            else:
                # P1优化：提供常用时间快捷订阅按钮，减少操作步骤
                buttons.append([
                    {"text": "🌅 08:00订阅", "callback_data": f"subscription:sub_time:{source.id}:08:00"},
                    {"text": "🌙 19:00订阅", "callback_data": f"subscription:sub_time:{source.id}:19:00"}
                ])
                buttons.append([
                    {"text": "🌃 21:00订阅", "callback_data": f"subscription:sub_time:{source.id}:21:00"},
                    {"text": "⚙️ 更多时间", "callback_data": f"subscription:subscribe:{source.id}"}
                ])
            
            buttons.append([
                {"text": "🔙 返回列表", "callback_data": "subscription:browse_sources:1"},
                {"text": "🏠 返回首页", "callback_data": "subscription:home"}
            ])
            
            keyboard = self._create_keyboard(buttons)
            return message, keyboard
        else:
            if is_subscribed:
                message += "\n\n💡 u-取消订阅 | b-返回列表 | h-返回首页"
            else:
                message += "\n\n💡 s-订阅 | b-返回列表 | h-返回首页"
            return message, None
    
    def build_plugin_select(self, subscription_type: str) -> Tuple[str, Any]:
        """
        构建插件选择菜单
        
        Args:
            subscription_type: 订阅类型
            
        Returns:
            (消息文本, 键盘)
        """
        type_name = self.SUBSCRIPTION_TYPES.get(subscription_type, subscription_type)
        
        message = f"""📬 {type_name}

请选择要订阅的平台:"""
        
        if self.supports_buttons:
            buttons = [
                [
                    {"text": "🎵 音乐", "callback_data": f"subscription:plugin:{subscription_type}:music"},
                    {"text": "📚 书籍", "callback_data": f"subscription:plugin:{subscription_type}:book"}
                ],
                [
                    {"text": "🎬 豆瓣", "callback_data": f"subscription:plugin:{subscription_type}:douban"},
                    {"text": "☁️ 云盘", "callback_data": f"subscription:plugin:{subscription_type}:pansou"}
                ],
                [
                    {"text": "⬅️ 返回", "callback_data": "subscription:back"},
                    {"text": "❌ 退出", "callback_data": "subscription:exit"}
                ]
            ]
            keyboard = self._create_keyboard(buttons)
            return message, keyboard
        else:
            message += """

1. 🎵 音乐
2. 📚 书籍
3. 🎬 豆瓣
4. ☁️ 云盘

💡 输入数字选择 | b-返回 | 0-退出"""
            return message, None
    
    def build_push_mode_select(self, source_id: int = None) -> Tuple[str, Any]:
        """
        构建推送模式选择
        
        Args:
            source_id: 订阅源ID（可选）
            
        Returns:
            (消息文本, 键盘)
        """
        message = """⚙️ 选择推送模式

请选择您希望的推送方式:

📅 **每日定时** - 每天固定时间推送
🕐 **多时段推送** - 每天多个时间点推送
⚡ **有更新立即推送** - 内容更新后立即推送
📰 **每周摘要** - 周日汇总一周内容"""
        
        callback_prefix = f"subscription:push_mode:{source_id}" if source_id else "subscription:push_mode:0"
        
        if self.supports_buttons:
            buttons = [
                [
                    {"text": "📅 每日定时", "callback_data": f"{callback_prefix}:daily"},
                    {"text": "🕐 多时段", "callback_data": f"{callback_prefix}:multi_time"}
                ],
                [
                    {"text": "⚡ 立即推送", "callback_data": f"{callback_prefix}:realtime"},
                    {"text": "📰 每周摘要", "callback_data": f"{callback_prefix}:weekly_digest"}
                ],
                [
                    {"text": "⬅️ 返回", "callback_data": "subscription:home"},
                    {"text": "❌ 退出", "callback_data": "subscription:exit"}
                ]
            ]
            keyboard = self._create_keyboard(buttons)
            return message, keyboard
        else:
            message += """

1. 📅 每日定时
2. 🕐 多时段推送
3. ⚡ 有更新立即推送
4. 📰 每周摘要

💡 输入数字选择 | b-返回 | 0-退出"""
            return message, None
    
    def build_time_select(self, subscription_type: str, plugin_name: str, push_mode: str = "daily") -> Tuple[str, Any]:
        """
        构建推送时间选择
        
        Args:
            subscription_type: 订阅类型
            plugin_name: 插件名称
            push_mode: 推送模式
            
        Returns:
            (消息文本, 键盘)
        """
        type_name = self.SUBSCRIPTION_TYPES.get(subscription_type, subscription_type)
        plugin_display = self.PLUGIN_NAMES.get(plugin_name, plugin_name)
        
        # 根据推送模式显示不同的界面
        if push_mode == "realtime":
            message = f"""⚡ 实时推送设置

订阅类型: {type_name}
订阅平台: {plugin_display}

实时推送模式下，内容更新后将立即推送给您。
系统每15分钟检查一次更新。"""
            
            if self.supports_buttons:
                buttons = [
                    [{"text": "✅ 确认开启实时推送", "callback_data": f"subscription:confirm:{subscription_type}:{plugin_name}:realtime:00:00"}],
                    [
                        {"text": "⬅️ 返回", "callback_data": f"subscription:add:{subscription_type}"},
                        {"text": "❌ 退出", "callback_data": "subscription:exit"}
                    ]
                ]
                keyboard = self._create_keyboard(buttons)
                return message, keyboard
            else:
                message += "\n\n💡 输入 y 确认 | b-返回 | 0-退出"
                return message, None
        
        elif push_mode == "weekly_digest":
            message = f"""📰 每周摘要设置

订阅类型: {type_name}
订阅平台: {plugin_display}

每周摘要模式下，系统将在周日汇总一周内容推送给您。
请选择推送时间:"""
            
            if self.supports_buttons:
                buttons = [
                    [
                        {"text": "🌅 10:00", "callback_data": f"subscription:confirm:{subscription_type}:{plugin_name}:weekly_digest:10:00"},
                        {"text": "🌆 18:00", "callback_data": f"subscription:confirm:{subscription_type}:{plugin_name}:weekly_digest:18:00"}
                    ],
                    [
                        {"text": "🌙 19:00", "callback_data": f"subscription:confirm:{subscription_type}:{plugin_name}:weekly_digest:19:00"},
                        {"text": "🌃 21:00", "callback_data": f"subscription:confirm:{subscription_type}:{plugin_name}:weekly_digest:21:00"}
                    ],
                    [
                        {"text": "⬅️ 返回", "callback_data": f"subscription:add:{subscription_type}"},
                        {"text": "❌ 退出", "callback_data": "subscription:exit"}
                    ]
                ]
                keyboard = self._create_keyboard(buttons)
                return message, keyboard
            else:
                message += """

1. 🌅 10:00
2. 🌆 18:00
3. 🌙 19:00
4. 🌃 21:00

💡 输入数字选择 | b-返回 | 0-退出"""
                return message, None
        
        elif push_mode == "multi_time":
            message = f"""🕐 多时段推送设置

订阅类型: {type_name}
订阅平台: {plugin_display}

请选择推送时段组合:"""
            
            if self.supports_buttons:
                buttons = [
                    [{"text": "🌅🌙 早晚 (08:00, 20:00)", "callback_data": f"subscription:confirm:{subscription_type}:{plugin_name}:multi_time:08:00,20:00"}],
                    [{"text": "🌅🌞🌙 三时段 (08:00, 12:00, 20:00)", "callback_data": f"subscription:confirm:{subscription_type}:{plugin_name}:multi_time:08:00,12:00,20:00"}],
                    [{"text": "🌞🌃 午晚 (12:00, 21:00)", "callback_data": f"subscription:confirm:{subscription_type}:{plugin_name}:multi_time:12:00,21:00"}],
                    [
                        {"text": "⬅️ 返回", "callback_data": f"subscription:add:{subscription_type}"},
                        {"text": "❌ 退出", "callback_data": "subscription:exit"}
                    ]
                ]
                keyboard = self._create_keyboard(buttons)
                return message, keyboard
            else:
                message += """

1. 🌅🌙 早晚 (08:00, 20:00)
2. 🌅🌞🌙 三时段 (08:00, 12:00, 20:00)
3. 🌞🌃 午晚 (12:00, 21:00)

💡 输入数字选择 | b-返回 | 0-退出"""
                return message, None
        
        # 默认：每日定时
        message = f"""⏰ 设置推送时间

订阅类型: {type_name}
订阅平台: {plugin_display}

请选择推送时间:"""
        
        if self.supports_buttons:
            buttons = [
                [
                    {"text": "🌅 08:00", "callback_data": f"subscription:time:{subscription_type}:{plugin_name}:08:00"},
                    {"text": "🌞 12:00", "callback_data": f"subscription:time:{subscription_type}:{plugin_name}:12:00"}
                ],
                [
                    {"text": "🌆 18:00", "callback_data": f"subscription:time:{subscription_type}:{plugin_name}:18:00"},
                    {"text": "🌙 19:00", "callback_data": f"subscription:time:{subscription_type}:{plugin_name}:19:00"}
                ],
                [
                    {"text": "🌃 21:00", "callback_data": f"subscription:time:{subscription_type}:{plugin_name}:21:00"},
                    {"text": "⌨️ 自定义", "callback_data": f"subscription:time_custom:{subscription_type}:{plugin_name}"}
                ],
                [
                    {"text": "⬅️ 返回", "callback_data": f"subscription:add:{subscription_type}"},
                    {"text": "❌ 退出", "callback_data": "subscription:exit"}
                ]
            ]
            keyboard = self._create_keyboard(buttons)
            return message, keyboard
        else:
            message += """

1. 🌅 08:00
2. 🌞 12:00
3. 🌆 18:00
4. 🌙 19:00
5. 🌃 21:00
6. ⌨️ 自定义时间

💡 输入数字选择或直接输入时间(如 19:30) | b-返回 | 0-退出"""
            return message, None
    
    def build_keyword_input(self, plugin_name: str) -> Tuple[str, Any]:
        """
        构建关键词输入提示
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            (消息文本, 键盘)
        """
        plugin_display = self.PLUGIN_NAMES.get(plugin_name, plugin_name)
        
        message = f"""🔍 订阅关键词

订阅平台: {plugin_display}

请输入要订阅的关键词:
(当该关键词进入热搜榜时会通知您)"""
        
        if self.supports_buttons:
            buttons = [
                [
                    {"text": "⬅️ 返回", "callback_data": "subscription:add:keyword"},
                    {"text": "❌ 退出", "callback_data": "subscription:exit"}
                ]
            ]
            keyboard = self._create_keyboard(buttons)
            return message, keyboard
        else:
            message += "\n\n💡 直接输入关键词 | b-返回 | 0-退出"
            return message, None
    
    def build_subscription_list(self, subscriptions: List, page: int = 1, page_size: int = 5) -> Tuple[str, Any]:
        """
        构建订阅列表
        
        Args:
            subscriptions: 订阅列表
            page: 当前页码
            page_size: 每页数量
            
        Returns:
            (消息文本, 键盘)
        """
        if not subscriptions:
            message = "📭 暂无订阅\n\n快去添加订阅吧！"
            
            if self.supports_buttons:
                buttons = [
                    [
                        {"text": "➕ 添加订阅", "callback_data": "subscription:home"},
                        {"text": "❌ 退出", "callback_data": "subscription:exit"}
                    ]
                ]
                keyboard = self._create_keyboard(buttons)
                return message, keyboard
            else:
                message += "\n\n💡 h-首页 | 0-退出"
                return message, None
        
        total = len(subscriptions)
        total_pages = (total + page_size - 1) // page_size
        start = (page - 1) * page_size
        end = min(start + page_size, total)
        page_subs = subscriptions[start:end]
        
        separator = get_separator()
        lines = [f"📬 我的订阅 ({page}/{total_pages})", separator]
        
        for i, sub in enumerate(page_subs, start + 1):
            status = "✅" if sub.enabled else "⏸️"
            type_name = self.SUBSCRIPTION_TYPES.get(sub.subscription_type.value, sub.subscription_type.value)
            
            # 根据订阅类型显示不同的信息
            if sub.subscription_type.value == 'source':
                # 源订阅：显示源的信息
                try:
                    from common import get_source_manager
                    source_manager = get_source_manager()
                    if source_manager:
                        source = source_manager.get_source(int(sub.target))
                        if source:
                            display_name = source.get_display_title() if hasattr(source, 'get_display_title') else source.display_name
                            icon = source.icon if hasattr(source, 'icon') else '📰'
                            lines.append(f"{i}. {status} {icon} {display_name}")
                            # 显示分类和推送时间
                            category = source.category if hasattr(source, 'category') else '资讯'
                            lines.append(f"   📂 {category} | ⏰ {sub.push_time}")
                        else:
                            lines.append(f"{i}. {status} 📰 订阅源 #{sub.target}")
                            lines.append(f"   {type_name} | {sub.push_time}")
                    else:
                        lines.append(f"{i}. {status} 📰 订阅源 #{sub.target}")
                        lines.append(f"   {type_name} | {sub.push_time}")
                except Exception as e:
                    logger.debug(f"[SubscriptionResponseBuilder] 获取源信息失败: {e}")
                    lines.append(f"{i}. {status} 📰 订阅源 #{sub.target}")
                    lines.append(f"   {type_name} | {sub.push_time}")
            else:
                # 其他订阅类型：显示插件名称
                plugin_name = self.PLUGIN_NAMES.get(sub.plugin_name, sub.plugin_name)
                target_display = ""
                if sub.subscription_type.value == 'keyword':
                    target_display = f"「{sub.target}」"
                lines.append(f"{i}. {status} {plugin_name} {target_display}")
                lines.append(f"   {type_name} | {sub.push_time}")
        
        message = "\n".join(lines)
        
        if self.supports_buttons:
            buttons = []
            
            # 订阅操作按钮
            row = []
            for i, sub in enumerate(page_subs, start + 1):
                row.append({"text": f"#{i}", "callback_data": f"subscription:detail:{sub.id}"})
                if len(row) >= 5:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)
            
            # 分页按钮
            nav_row = []
            if page > 1:
                nav_row.append({"text": "⬅️ 上一页", "callback_data": f"subscription:list:{page-1}"})
            if page < total_pages:
                nav_row.append({"text": "➡️ 下一页", "callback_data": f"subscription:list:{page+1}"})
            if nav_row:
                buttons.append(nav_row)
            
            # 导航按钮
            buttons.append([
                {"text": "🏠 首页", "callback_data": "subscription:home"},
                {"text": "❌ 退出", "callback_data": "subscription:exit"}
            ])
            
            keyboard = self._create_keyboard(buttons)
            return message, keyboard
        else:
            message += f"\n\n💡 输入序号查看详情 | p/n-翻页 | h-首页 | 0-退出"
            return message, None
    
    def build_subscription_detail(self, sub) -> Tuple[str, Any]:
        """
        构建订阅详情
        
        Args:
            sub: 订阅对象
            
        Returns:
            (消息文本, 键盘)
        """
        status = "✅ 已启用" if sub.enabled else "⏸️ 已暂停"
        
        separator = get_separator()
        lines = [
            f"📬 订阅详情 #{sub.id}",
            separator,
        ]
        
        # 根据订阅类型显示不同的信息
        if sub.subscription_type.value == 'source':
            # 源订阅：显示源的详细信息
            try:
                from common import get_source_manager
                source_manager = get_source_manager()
                if source_manager:
                    source = source_manager.get_source(int(sub.target))
                    if source:
                        display_name = source.get_display_title() if hasattr(source, 'get_display_title') else source.display_name
                        icon = source.icon if hasattr(source, 'icon') else '📰'
                        lines.append(f"{icon} {display_name}")
                        
                        # 显示源的详细信息
                        if hasattr(source, 'category') and source.category:
                            lines.append(f"📂 分类: {source.category}")
                        if hasattr(source, 'description') and source.description:
                            lines.append(f"📝 {source.description}")
                        if hasattr(source, 'current_subscribers'):
                            lines.append(f"👥 {source.current_subscribers} 人订阅")
                    else:
                        lines.append(f"📰 订阅源 #{sub.target}")
                else:
                    lines.append(f"📰 订阅源 #{sub.target}")
            except Exception as e:
                logger.debug(f"[SubscriptionResponseBuilder] 获取源信息失败: {e}")
                lines.append(f"📰 订阅源 #{sub.target}")
        else:
            # 其他订阅类型：显示插件名称
            plugin_name = self.PLUGIN_NAMES.get(sub.plugin_name, sub.plugin_name)
            type_name = self.SUBSCRIPTION_TYPES.get(sub.subscription_type.value, sub.subscription_type.value)
            lines.append(f"📱 {plugin_name}")
            lines.append(f"📋 {type_name}")
            if sub.subscription_type.value == 'keyword':
                lines.append(f"� 关键词: 「{sub.target}」")
            else:
                lines.append(f"🎯 目标: {sub.target}")
        
        # 推送设置
        lines.append("")
        
        # 显示推送模式
        push_mode_names = {
            'daily': '📅 每日定时',
            'weekly': '📆 每周定时',
            'realtime': '⚡ 有更新立即推送',
            'multi_time': '🕐 多时段推送',
            'weekly_digest': '📰 每周摘要',
            'custom': '⚙️ 自定义'
        }
        push_mode = sub.push_frequency.value if hasattr(sub.push_frequency, 'value') else str(sub.push_frequency)
        mode_display = push_mode_names.get(push_mode, push_mode)
        lines.append(f"📡 推送模式: {mode_display}")
        
        # 根据推送模式显示时间
        if push_mode == 'realtime':
            lines.append("⏰ 有更新时立即推送")
        elif push_mode == 'weekly_digest':
            lines.append(f"⏰ 每周日 {sub.push_time} 推送摘要")
        elif push_mode == 'multi_time':
            times = sub.push_time.split(',') if sub.push_time else []
            lines.append(f"⏰ 每日 {', '.join(times)} 推送")
        else:
            lines.append(f"⏰ 推送时间: {sub.push_time}")
        
        lines.append(f"📊 状态: {status}")
        
        if sub.last_push_at:
            lines.append(f"📤 上次推送: {sub.last_push_at.strftime('%m-%d %H:%M')}")
        if sub.next_push_at:
            lines.append(f"⏳ 下次推送: {sub.next_push_at.strftime('%m-%d %H:%M')}")
        
        message = "\n".join(lines)
        
        if self.supports_buttons:
            buttons = []
            
            # 状态切换按钮
            if sub.enabled:
                buttons.append([{"text": "⏸️ 暂停订阅", "callback_data": f"subscription:disable:{sub.id}"}])
            else:
                buttons.append([{"text": "▶️ 启用订阅", "callback_data": f"subscription:enable:{sub.id}"}])
            
            buttons.append([
                {"text": "⏰ 修改时间", "callback_data": f"subscription:edit_time:{sub.id}"},
                {"text": "🗑️ 取消订阅", "callback_data": f"subscription:delete:{sub.id}"}
            ])
            
            buttons.append([
                {"text": "⬅️ 返回列表", "callback_data": "subscription:list"},
                {"text": "❌ 退出", "callback_data": "subscription:exit"}
            ])
            
            keyboard = self._create_keyboard(buttons)
            return message, keyboard
        else:
            message += "\n\n操作选项:"
            message += "\n1. 暂停/启用订阅"
            message += "\n2. 修改推送时间"
            message += "\n3. 取消订阅"
            message += "\n\n💡 输入数字选择 | b-返回 | 0-退出"
            return message, None
    
    def build_confirm_delete(self, sub) -> Tuple[str, Any]:
        """构建删除确认"""
        plugin_name = self.PLUGIN_NAMES.get(sub.plugin_name, sub.plugin_name)
        
        message = f"""⚠️ 确认取消订阅?

平台: {plugin_name}
目标: {sub.target}

此操作不可恢复！"""
        
        if self.supports_buttons:
            buttons = [
                [
                    {"text": "✅ 确认取消", "callback_data": f"subscription:confirm_delete:{sub.id}"},
                    {"text": "❌ 取消", "callback_data": f"subscription:detail:{sub.id}"}
                ]
            ]
            keyboard = self._create_keyboard(buttons)
            return message, keyboard
        else:
            message += "\n\n输入 y 确认取消，其他任意键返回"
            return message, None
    
    def build_success_message(self, action: str, details: str = "") -> Tuple[str, Any]:
        """构建成功消息"""
        messages = {
            'subscribe': f"✅ 订阅成功！\n\n{details}",
            'unsubscribe': "✅ 已取消订阅",
            'enable': "✅ 订阅已启用",
            'disable': "✅ 订阅已暂停",
            'update_time': f"✅ 推送时间已更新\n\n{details}"
        }
        
        message = messages.get(action, f"✅ 操作成功\n\n{details}")
        
        if self.supports_buttons:
            buttons = [
                [
                    {"text": "📋 我的订阅", "callback_data": "subscription:list"},
                    {"text": "🏠 首页", "callback_data": "subscription:home"}
                ]
            ]
            keyboard = self._create_keyboard(buttons)
            return message, keyboard
        else:
            message += "\n\n💡 h-首页 | 0-退出"
            return message, None
    
    # ==================== 热门订阅源 ====================
    
    def build_hot_sources_page(self, sources: List, user_subscribed_ids: set = None, page: int = 1) -> Tuple[str, Any]:
        """构建热门订阅源页面
        
        Args:
            sources: 热门订阅源列表
            user_subscribed_ids: 用户已订阅的源ID集合
            page: 当前页码
        """
        if user_subscribed_ids is None:
            user_subscribed_ids = set()
        
        if not sources:
            message = """🔥 热门订阅源

暂无热门订阅源数据。

💡 订阅源的热度根据订阅人数计算。"""
            
            if self.supports_buttons:
                buttons = [
                    [{"text": "📰 浏览全部订阅源", "callback_data": "subscription:browse_sources:1"}],
                    [
                        {"text": "🏠 返回首页", "callback_data": "subscription:home"},
                        {"text": "❌ 退出", "callback_data": "subscription:exit"}
                    ]
                ]
                keyboard = self._create_keyboard(buttons)
                return message, keyboard
            else:
                message += "\n\n💡 1-浏览全部 | h-首页 | 0-退出"
                return message, None
        
        # 分页
        page_size = 8
        total_pages = max(1, (len(sources) + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_sources = sources[start_idx:end_idx]
        
        message = f"""🔥 热门订阅源 TOP {len(sources)}

按订阅人数排序，发现更多优质内容！

"""
        
        # 排名图标
        RANK_ICONS = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
        
        for i, source in enumerate(page_sources):
            global_rank = start_idx + i
            rank_icon = RANK_ICONS[global_rank] if global_rank < len(RANK_ICONS) else f"{global_rank + 1}."
            
            # 检查是否已订阅
            is_subscribed = source.id in user_subscribed_ids
            sub_icon = "✅" if is_subscribed else ""
            
            display_title = source.get_display_title()
            subscriber_count = getattr(source, 'current_subscribers', 0)
            
            message += f"{rank_icon} {source.icon} {display_title} {sub_icon}\n"
            message += f"   👥 {subscriber_count} 人订阅"
            if source.category:
                message += f" | 📂 {source.category}"
            message += "\n"
        
        if total_pages > 1:
            message += f"\n📄 第 {page}/{total_pages} 页"
        
        if self.supports_buttons:
            buttons = []
            
            # 热门源按钮（每行2个）
            for i in range(0, len(page_sources), 2):
                row = []
                for j in range(2):
                    if i + j < len(page_sources):
                        source = page_sources[i + j]
                        display_title = source.get_display_title()
                        is_subscribed = source.id in user_subscribed_ids
                        
                        if is_subscribed:
                            row.append({
                                "text": f"✅ {display_title[:8]}",
                                "callback_data": f"subscription:source_detail:{source.id}"
                            })
                        else:
                            row.append({
                                "text": f"➕ {display_title[:8]}",
                                "callback_data": f"subscription:quick_sub:{source.id}"
                            })
                if row:
                    buttons.append(row)
            
            # 翻页
            nav_row = []
            if page > 1:
                nav_row.append({"text": "⬅️ 上一页", "callback_data": f"subscription:view_hot:{page-1}"})
            if page < total_pages:
                nav_row.append({"text": "➡️ 下一页", "callback_data": f"subscription:view_hot:{page+1}"})
            if nav_row:
                buttons.append(nav_row)
            
            buttons.append([
                {"text": "📰 浏览全部", "callback_data": "subscription:browse_sources:1"},
                {"text": "🏠 返回首页", "callback_data": "subscription:home"}
            ])
            
            keyboard = self._create_keyboard(buttons)
            return message, keyboard
        else:
            # 会话模式
            nav_hints = []
            if page > 1:
                nav_hints.append("p-上页")
            if page < total_pages:
                nav_hints.append("n-下页")
            nav_hints.extend(["序号-订阅", "a-全部", "h-首页", "0-退出"])
            message += f"\n\n操作: {' | '.join(nav_hints)}"
            return message, None
    
    # ==================== 订阅源申请 ====================
    
    def build_source_request_page(self) -> Tuple[str, Any]:
        """构建订阅源申请页面"""
        message = """📰 申请添加订阅源

您可以向我们申请添加新的订阅源！

📝 **申请说明**:
• 请提供订阅源的RSS链接或网站地址
• 简要说明订阅源的内容类型
• 管理员审核通过后会添加到系统中

💡 **支持的类型**:
• RSS/Atom 订阅源
• 热门网站榜单
• API 数据接口

请按以下格式发送申请:"""
        
        if self.supports_buttons:
            buttons = [
                [{"text": "📝 开始申请", "callback_data": "subscription:request:start"}],
                [{"text": "📋 我的申请", "callback_data": "subscription:request:my"}],
                [
                    {"text": "🔙 返回", "callback_data": "subscription:home"},
                    {"text": "❌ 退出", "callback_data": "subscription:exit"}
                ]
            ]
            keyboard = self._create_keyboard(buttons)
            return message, keyboard
        else:
            message += """

格式: 链接 + 说明
例如: https://example.com/feed 科技新闻RSS

💡 1-开始申请 | 2-我的申请 | b-返回 | 0-退出"""
            return message, None
    
    def build_source_request_form(self) -> Tuple[str, Any]:
        """构建订阅源申请表单"""
        message = """📝 提交订阅源申请

请按以下格式发送:

```
链接: https://example.com/feed
名称: 订阅源名称
说明: 简要描述订阅源内容
```

或者直接发送RSS链接，系统会自动解析。

💡 提示: 发送 b 返回，发送 0 退出"""
        
        if self.supports_buttons:
            buttons = [
                [
                    {"text": "🔙 返回", "callback_data": "subscription:request"},
                    {"text": "❌ 退出", "callback_data": "subscription:exit"}
                ]
            ]
            keyboard = self._create_keyboard(buttons)
            return message, keyboard
        else:
            return message, None
    
    def build_source_request_confirm(self, url: str, name: str = None, description: str = None) -> Tuple[str, Any]:
        """构建订阅源申请确认页面"""
        message = f"""📋 确认提交申请

🔗 链接: {url}
📛 名称: {name or '待解析'}
📝 说明: {description or '无'}

确认提交此订阅源申请吗？"""
        
        # URL编码处理
        import urllib.parse
        encoded_url = urllib.parse.quote(url, safe='')
        
        if self.supports_buttons:
            buttons = [
                [{"text": "✅ 确认提交", "callback_data": f"subscription:request:submit:{encoded_url}"}],
                [
                    {"text": "✏️ 重新填写", "callback_data": "subscription:request:start"},
                    {"text": "❌ 取消", "callback_data": "subscription:request"}
                ]
            ]
            keyboard = self._create_keyboard(buttons)
            return message, keyboard
        else:
            message += "\n\n💡 输入 y 确认 | n 重新填写 | b 返回"
            return message, None
    
    def build_source_request_success(self, request_id: int) -> Tuple[str, Any]:
        """构建申请成功页面"""
        message = f"""✅ 申请提交成功！

📋 申请编号: #{request_id}

管理员会尽快审核您的申请，审核结果会通过系统通知您。

感谢您的贡献！"""
        
        if self.supports_buttons:
            buttons = [
                [{"text": "📋 查看我的申请", "callback_data": "subscription:request:my"}],
                [
                    {"text": "🏠 返回首页", "callback_data": "subscription:home"},
                    {"text": "❌ 退出", "callback_data": "subscription:exit"}
                ]
            ]
            keyboard = self._create_keyboard(buttons)
            return message, keyboard
        else:
            message += "\n\n💡 1-查看我的申请 | h-首页 | 0-退出"
            return message, None
    
    def build_my_source_requests(self, requests: List[Dict], page: int = 1) -> Tuple[str, Any]:
        """构建我的申请列表"""
        if not requests:
            message = """📋 我的订阅源申请

暂无申请记录。

💡 您可以申请添加新的订阅源！"""
            
            if self.supports_buttons:
                buttons = [
                    [{"text": "📝 申请新订阅源", "callback_data": "subscription:request:start"}],
                    [
                        {"text": "🔙 返回", "callback_data": "subscription:home"},
                        {"text": "❌ 退出", "callback_data": "subscription:exit"}
                    ]
                ]
                keyboard = self._create_keyboard(buttons)
                return message, keyboard
            else:
                message += "\n\n💡 1-申请新订阅源 | b-返回 | 0-退出"
                return message, None
        
        # 状态映射
        status_names = {
            'pending': '⏳ 待审核',
            'processing': '🔄 审核中',
            'approved': '✅ 已通过',
            'rejected': '❌ 已拒绝',
            'resolved': '✅ 已添加'
        }
        
        message = "📋 我的订阅源申请\n\n"
        
        for req in requests:
            status = status_names.get(req.get('status', 'pending'), '⏳ 待审核')
            content = req.get('content', '')[:30]
            created = req.get('created_at', '')[:10] if req.get('created_at') else ''
            message += f"#{req['id']} {status}\n"
            message += f"   {content}...\n"
            message += f"   📅 {created}\n"
            if req.get('admin_reply'):
                message += f"   💬 {req['admin_reply'][:20]}...\n"
            message += "\n"
        
        if self.supports_buttons:
            buttons = [
                [{"text": "📝 申请新订阅源", "callback_data": "subscription:request:start"}],
                [
                    {"text": "🔙 返回", "callback_data": "subscription:home"},
                    {"text": "❌ 退出", "callback_data": "subscription:exit"}
                ]
            ]
            keyboard = self._create_keyboard(buttons)
            return message, keyboard
        else:
            message += "\n💡 1-申请新订阅源 | b-返回 | 0-退出"
            return message, None
    
    def _create_keyboard(self, buttons: List[List[Dict]]):
        """创建键盘"""
        try:
            from astrbot.core.message.components import InlineKeyboard
            return InlineKeyboard(buttons=buttons)
        except ImportError:
            return None
