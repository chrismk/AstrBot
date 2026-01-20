"""
配额管理插件响应构建器
继承通用基类，实现标准化跨平台交互
"""
import json
import sys
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List

# 添加 common 到路径
plugin_root = Path(__file__).parent.parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

from common.response_builder import BaseResponseBuilder
from common.message_formatter import get_separator

try:
    from astrbot.core.message.components import InlineKeyboard
except ImportError:
    InlineKeyboard = None


class QuotaAdminResponseBuilder(BaseResponseBuilder):
    """配额管理响应构建器 - 继承通用基类"""
    
    # 回调前缀
    CALLBACK_PREFIX = "quota_admin"
    
    # 平台名称映射
    PLATFORM_NAMES = {
        "all": "全部",
        "telegram": "Telegram",
        "qq": "QQ",
        "wechat": "微信",
        "discord": "Discord",
        "lark": "飞书",
        "unknown": "未知"
    }
    
    # 会员等级名称
    LEVEL_NAMES = {0: "免费", 1: "高级", 2: "VIP"}
    LEVEL_NAMES_FULL = {0: "免费用户", 1: "高级会员", 2: "VIP会员"}
    
    # 操作类型中文名称映射
    ACTION_NAMES = {
        # 音乐
        'music_search': '音乐搜索',
        'music_view': '音乐详情',
        'music_download': '音乐下载',
        'music_download_128': '🎵128k',
        'music_download_320': '🎵320k',
        'music_download_flac': '🎵无损',
        'music_lyric': '🎵歌词',
        # 豆瓣
        'douban_search': '豆瓣搜索',
        'douban_view': '豆瓣详情',
        # 网盘
        'pansou_search': '网盘搜索',
        'pansou_download': '网盘下载',
        # 文件处理
        'file_process': '文件处理',
        # 书籍
        'book_search': '书籍搜索',
        'book_download': '书籍下载',
    }
    
    # 插件名称中文映射
    PLUGIN_NAMES = {
        'music': '🎵音乐',
        'douban': '🎬豆瓣',
        'pansou': '📁网盘',
        'file_processor': '📄文件',
        'book': '📚书籍',
    }
    
    # 搜索类型中文映射
    SEARCH_TYPE_NAMES = {
        'keyword': '关键词',
        'id': 'ID',
        'book': '书籍',
        'movie': '电影',
        'tv': '电视剧',
    }
    
    # 平台/源中文映射
    PLATFORM_SOURCE_NAMES = {
        'default': '默认',
        'alternative': '备用',
        'cache': '缓存',
        'alt_copy': '备用复制',
    }
    
    @staticmethod
    def get_action_name(action_type: str) -> str:
        """获取操作类型的中文名称"""
        return QuotaAdminResponseBuilder.ACTION_NAMES.get(action_type, action_type)
    
    @staticmethod
    def get_plugin_name(plugin: str) -> str:
        """获取插件的中文名称"""
        return QuotaAdminResponseBuilder.PLUGIN_NAMES.get(plugin, plugin)
    
    @staticmethod
    def get_search_type_name(search_type: str) -> str:
        """获取搜索类型的中文名称"""
        return QuotaAdminResponseBuilder.SEARCH_TYPE_NAMES.get(search_type, search_type)
    
    @staticmethod
    def get_platform_source_name(name: str) -> str:
        """获取平台/源的中文名称"""
        return QuotaAdminResponseBuilder.PLATFORM_SOURCE_NAMES.get(name, name)
    
    def __init__(self, capabilities: Dict[str, bool]):
        """
        初始化响应构建器
        
        Args:
            capabilities: 平台能力字典
        """
        super().__init__(capabilities)
        self.use_json_format = self.platform_name.lower() == "lark"
    
    def _make_callback(self, action: str, **params) -> str:
        """
        生成回调数据（支持 JSON 格式用于飞书）
        
        Args:
            action: 动作名称
            **params: 额外参数
            
        Returns:
            回调数据字符串
        """
        if self.use_json_format:
            data = {"action": f"{self.CALLBACK_PREFIX}_{action}"}
            data.update(params)
            return json.dumps(data, ensure_ascii=False)
        else:
            # 传统格式: quota_admin:action:param1:param2
            parts = [self.CALLBACK_PREFIX, action]
            for key, value in params.items():
                if value is not None:
                    parts.append(str(value))
            return ":".join(parts)
    
    def _add_nav_hint(self, back_cmd: str = "b", show_back: bool = True) -> str:
        """
        添加会话模式的导航提示（标准化格式）
        
        Args:
            back_cmd: 返回指令（默认 b）
            show_back: 是否显示返回提示
            
        Returns:
            导航提示文本
        """
        separator = get_separator(self.platform_name)
        hint = f"\n{separator}\n"
        if show_back:
            hint += f"💡 {back_cmd}-返回 | 0-退出\n"
        else:
            hint += "💡 0-退出\n"
        return hint
    
    def _parse_cron_to_text(self, cron: str) -> str:
        """
        将 cron 表达式解析为人类可读的格式
        
        Args:
            cron: cron 表达式（分 时 日 月 周）
        
        Returns:
            人类可读的调度描述
        """
        try:
            parts = cron.strip().split()
            if len(parts) != 5:
                return cron  # 无法解析，返回原始表达式
            
            minute, hour, day, month, weekday = parts
            
            # 星期映射
            weekday_names = {
                '0': '周日', '7': '周日',
                '1': '周一', '2': '周二', '3': '周三',
                '4': '周四', '5': '周五', '6': '周六'
            }
            
            # 每天某时某分
            if day == '*' and month == '*' and weekday == '*':
                if hour != '*' and minute != '*':
                    return f"每天 {hour.zfill(2)}:{minute.zfill(2)}"
                elif hour != '*':
                    return f"每天 {hour}时"
            
            # 每小时
            if hour == '*' and day == '*' and month == '*' and weekday == '*':
                if minute != '*':
                    return f"每小时第{minute}分"
                return "每分钟"
            
            # 每周某天
            if day == '*' and month == '*' and weekday != '*':
                weekday_text = weekday_names.get(weekday, f'周{weekday}')
                if hour != '*' and minute != '*':
                    return f"每{weekday_text} {hour.zfill(2)}:{minute.zfill(2)}"
                return f"每{weekday_text}"
            
            # 每月某日
            if day != '*' and month == '*' and weekday == '*':
                if hour != '*' and minute != '*':
                    return f"每月{day}日 {hour.zfill(2)}:{minute.zfill(2)}"
                return f"每月{day}日"
            
            # 其他复杂情况，返回简化格式
            return cron
            
        except Exception:
            return cron
    
    def build_my_info_menu(self, user_info: Dict[str, Any], step: int = 0) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建"我的信息"菜单
        
        Args:
            user_info: 用户信息字典
            step: 当前步骤
            
        Returns:
            (消息文本, 键盘)
        """
        lines = ["📊 个人中心\n"]
        
        # 会员信息区块
        member_level = user_info.get('member_level', 'free')
        level_display = {'free': '🆓 普通用户', 'premium': '⭐ 高级会员', 'vip': '👑 VIP会员'}
        membership = user_info.get('membership', {})
        expire_date = membership.get('expire_date')
        days_remaining = membership.get('days_remaining')
        
        member_line = level_display.get(member_level, '🆓 普通用户')
        if expire_date and days_remaining is not None and member_level != 'free':
            member_line += f" · {days_remaining}天后到期"
        lines.append(member_line)
        
        # 积分和签到信息
        points = user_info.get('points', 0)
        checkin_days = user_info.get('checkin_days', 0)
        lines.append(f"💰 {points}积分 · 🔥 连签{checkin_days}天")
        
        # 今日配额使用（按插件分组显示）
        quota_usage = user_info.get('quota_usage', {})
        if quota_usage:
            lines.append("\n━━ 今日配额 ━━")
            
            # 插件中文名称
            plugin_names = {
                'music': '🎵 音乐',
                'douban': '🎬 豆瓣',
                'pansou': '📁 网盘',
                'file_processor': '📄 文件',
                'book': '📚 图书',
            }
            
            # 操作类型简称
            action_short = {
                'music_search': '搜索',
                'music_download_128': '128k',
                'music_download_320': '320k', 
                'music_download_flac': '无损',
                'music_lyric': '歌词',
                'douban_search': '搜索',
                'douban_view': '详情',
                'pansou_search': '搜索',
                'pansou_download': '下载',
                'file_process': '处理',
                'book_search': '搜索',
                'book_download': '下载',
            }
            
            # 按插件分组显示
            for plugin, actions in quota_usage.items():
                plugin_label = plugin_names.get(plugin, plugin)
                items = []
                for action, usage in actions.items():
                    used = usage.get('used', 0)
                    limit = usage.get('limit', 0)
                    name = action_short.get(action, action.split('_')[-1])
                    
                    if limit == -1:
                        items.append(f"{name}:{used}/∞")
                    elif used >= limit:
                        items.append(f"{name}:{used}/{limit}⚠️")
                    else:
                        items.append(f"{name}:{used}/{limit}")
                
                # 一行显示插件名和所有配额
                lines.append(f"{plugin_label} {' '.join(items)}")
        else:
            lines.append("\n📈 今日暂无使用记录")
        
        # 快捷提示
        lines.append("\n💡 签到可获积分，积分可兑换配额")
        
        message = "\n".join(lines)
        
        # 构建键盘
        keyboard = None
        if self.supports_buttons:
            keyboard = InlineKeyboard()
            # 第一行：核心功能
            keyboard.add_button("📅 签到", "quota_admin:checkin")
            keyboard.add_button("🎁 兑换", "quota_admin:redeem_menu")
            keyboard.add_button("📋 任务", "quota_admin:tasks")
            keyboard.add_row()
            # 第二行：详情查看
            keyboard.add_button("📊 配额", "quota_admin:quota_detail")
            keyboard.add_button("💰 流水", "quota_admin:points_history")
            keyboard.add_button("👥 邀请", "quota_admin:invite")
            keyboard.add_row()
            # 第三行：反馈和其他
            keyboard.add_button("📬 反馈", "quota_admin:feedback_menu")
            keyboard.add_button("❓ 帮助", "quota_admin:help")
            keyboard.add_button("❌ 关闭", "quota_admin:close")
        
        # 会话模式提示
        if not self.supports_buttons:
            message += f"\n{get_separator()}\n"
            message += "💡 1-签到 | 2-兑换 | 3-任务\n"
            message += "💡 4-配额 | 5-流水 | 6-邀请\n"
            message += "💡 7-反馈 | 0-退出"
        
        return message, keyboard
    
    def build_admin_menu(self, stats: Dict[str, Any], step: int = 0) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建管理员菜单
        
        Args:
            stats: 统计数据字典
            step: 当前步骤
            
        Returns:
            (消息文本, 键盘)
        """
        lines = ["🔧 管理员面板\n"]
        
        # 用户统计
        total_users = stats.get('total_users', 0)
        new_users_today = stats.get('new_users_today', 0)
        active_users = stats.get('active_users', 0)
        member_count = stats.get('member_count', 0)
        
        lines.append("👥 用户概况:")
        lines.append(f"  总用户: {total_users} | 今日新增: {new_users_today}")
        lines.append(f"  今日活跃: {active_users} | 付费会员: {member_count}")
        
        # 请求统计
        today_requests = stats.get('today_requests', 0) or 0
        yesterday_requests = stats.get('yesterday_requests', 0) or 0
        week_requests = stats.get('week_requests', 0) or 0
        
        # 计算环比变化
        if yesterday_requests > 0:
            change = ((today_requests - yesterday_requests) / yesterday_requests) * 100
            change_str = f"{'📈' if change >= 0 else '📉'}{abs(change):.0f}%"
        else:
            change_str = "—"
        
        lines.append(f"\n📊 请求统计:")
        lines.append(f"  今日: {today_requests} ({change_str})")
        lines.append(f"  昨日: {yesterday_requests} | 7日: {week_requests}")
        
        # 今日热门功能 TOP 10
        top_actions = stats.get('top_actions_today', [])
        if top_actions:
            lines.append(f"\n🔥 今日热门:")
            for item in top_actions[:10]:
                action = item.get('action_type', '')
                count = item.get('total', 0)
                action_label = self.get_action_name(action)
                lines.append(f"  • {action_label}: {count}次")
        
        # 积分流通
        checkin_today = stats.get('checkin_today', 0)
        points_issued = stats.get('points_issued', 0)
        points_spent = stats.get('points_spent', 0)
        
        lines.append(f"\n💰 今日积分:")
        lines.append(f"  签到: {checkin_today}人 | 发放: {points_issued} | 消耗: {points_spent}")
        
        message = "\n".join(lines)
        
        # 构建键盘
        keyboard = None
        if self.supports_buttons:
            keyboard = InlineKeyboard()
            keyboard.add_button("👤 用户管理", "quota_admin:admin:user")
            keyboard.add_button("📋 配额管理", "quota_admin:admin:quota_manage")
            keyboard.add_row()
            keyboard.add_button("💰 积分管理", "quota_admin:admin:points_manage")
            keyboard.add_button("📢 公告管理", "quota_admin:admin:announce")
            keyboard.add_row()
            keyboard.add_button("📊 数据统计", "quota_admin:admin:data_stats")
            keyboard.add_button("📬 反馈管理", "quota_admin:admin:feedback")
            keyboard.add_row()
            keyboard.add_button("⚡ 限流配置", "quota_admin:admin:rate_config")
            keyboard.add_button("🖥️ 系统状态", "quota_admin:admin:system")
            keyboard.add_row()
            keyboard.add_button("📰 订阅管理", "subscription:admin:stats")
            keyboard.add_button("⏰ 定时任务", "quota_admin:admin:scheduler")
            keyboard.add_row()
            keyboard.add_button("🌟 会员配置", "quota_admin:admin:member_config")
            keyboard.add_button("📺 广告管理", "quota_admin:admin:ad_manage")
            keyboard.add_row()
            keyboard.add_button("❌ 关闭", "quota_admin:close")
            
        # 添加文本提示
        if not self.supports_buttons:
            message += f"\n{get_separator()}\n"
            message += "💡 1-用户管理 | 2-配额管理 | 3-积分管理\n"
            message += "💡 4-公告管理 | 5-数据统计 | 6-反馈管理\n"
            message += "💡 7-限流配置 | 8-系统状态\n"
            message += "💡 9-订阅管理 | 10-定时任务 | 0-退出"
        
        return message, keyboard

    def build_quota_manage_menu(self, quota_stats: Dict[str, Any] = None) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建配额管理菜单（默认显示统计）"""
        lines = ["📋 配额管理\n"]
        lines.append("📈 配额使用统计\n")
        
        if not quota_stats:
            lines.append("暂无数据")
        else:
            # 功能使用排行
            if quota_stats.get('top_actions'):
                lines.append("🔥 功能使用排行 TOP 10：")
                for i, item in enumerate(quota_stats['top_actions'][:10], 1):
                    action = item.get('action_type', '未知')
                    count = item.get('total_count', 0)
                    action_label = self.get_action_name(action)
                    lines.append(f"  {i:2d}. {action_label}: {count}次")
                lines.append("")
            
            # 用户使用排行
            if quota_stats.get('top_users'):
                lines.append("👥 用户使用排行 TOP 10：")
                for i, item in enumerate(quota_stats['top_users'][:10], 1):
                    user_id = item.get('user_id', '未知')
                    username = item.get('username', '')
                    count = item.get('total_count', 0)
                    user_label = f"{username}({user_id})" if username else user_id
                    lines.append(f"  {i:2d}. {user_label}: {count}次")
                lines.append("")
            
            # 插件使用对比
            if quota_stats.get('plugin_stats'):
                lines.append("📊 插件使用对比：")
                plugin_names = {
                    'music': '🎵音乐', 'douban': '🎬豆瓣',
                    'pansou': '📁网盘', 'file_processor': '📄文件',
                    'book': '📚图书'
                }
                for item in quota_stats['plugin_stats']:
                    plugin = item.get('plugin_name', '未知')
                    count = item.get('total_count', 0)
                    plugin_label = plugin_names.get(plugin, plugin)
                    lines.append(f"  {plugin_label}: {count}次")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("⚙️ 配额规则", "quota_admin:admin:quota_rules")
            keyboard.add_button("🔙 返回", "quota_admin:admin_back")
        
        return message, keyboard

    def build_quota_usage_response(self, quota_data: list, step: int = 1) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建配额使用详情响应"""
        lines = ["📊 配额详情\n"]
        
        # 插件中文名称
        plugin_names = {
            'music': '🎵 音乐',
            'douban': '🎬 豆瓣',
            'pansou': '📁 网盘',
            'file_processor': '📄 文件',
            'book': '📚 图书',
        }
        
        # 操作类型中文名称
        action_names = {
            'music_download': '下载',
            'music_search': '搜索',
            'music_download_128': '下载128k',
            'music_download_320': '下载320k', 
            'music_download_flac': '下载无损',
            'music_lyric': '查看歌词',
            'douban_search': '搜索',
            'douban_view': '查看详情',
            'pansou_search': '搜索',
            'pansou_download': '下载',
            'file_process': '文件处理',
            'book_search': '搜索',
            'book_download': '下载',
        }
        
        if not quota_data:
            lines.append("暂无配额记录")
        else:
            # 按插件分组
            grouped = {}
            for item in quota_data:
                plugin = item['plugin_name']
                if plugin not in grouped:
                    grouped[plugin] = []
                grouped[plugin].append(item)
            
            for plugin, items in grouped.items():
                plugin_label = plugin_names.get(plugin, plugin)
                lines.append(f"{plugin_label}")
                
                for item in items:
                    action = item['action_type']
                    used = item['used']
                    limit = item['limit']
                    remaining = item['remaining']
                    
                    action_label = action_names.get(action, action.split('_')[-1])
                    
                    if limit == -1:
                        progress = f"{used}/∞"
                        status = "无限制"
                    elif used >= limit:
                        progress = f"{used}/{limit}"
                        status = "⚠️ 已用完"
                    else:
                        progress = f"{used}/{limit}"
                        status = f"剩余{remaining}"
                    
                    lines.append(f"  • {action_label}: {progress} ({status})")
                lines.append("")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons:
            keyboard = InlineKeyboard()
            keyboard.add_button("🔙 返回", "quota_admin:back")
            
        if not self.supports_buttons:
            message += f"\n{get_separator()}\n"
            message += "💡 b-返回 | 0-退出"
            
        return message, keyboard

    def build_points_transactions_response(self, transactions: list, step: int = 1) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建积分流水响应"""
        lines = ["💰 积分流水 (最近10笔)\n"]
        
        if not transactions:
            lines.append("暂无记录")
        else:
            for t in transactions:
                amount = t['amount']
                sign = "+" if amount >= 0 else ""
                desc = t['description']
                date_str = t['created_at'][:16] if isinstance(t['created_at'], str) else str(t['created_at'])[:16]
                
                lines.append(f"{date_str}")
                lines.append(f"{sign}{amount} | {desc}")
                lines.append("-" * 20)
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons:
            keyboard = InlineKeyboard()
            keyboard.add_button("🔙 返回", "quota_admin:back")
            
        if not self.supports_buttons:
            message += f"\n{get_separator()}\n"
            message += "💡 b-返回 | 0-退出"
            
        return message, keyboard

    def build_quota_boosts_response(self, boosts: list, step: int = 1) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建配额加成响应"""
        lines = ["⚡ 有效配额加成\n"]
        
        if not boosts:
            lines.append("暂无有效加成")
        else:
            for b in boosts:
                desc = b['description']
                amount = b['boost_amount']
                expire = b['expire_date']
                
                lines.append(f"📦 {desc}")
                lines.append(f"   加成: +{amount}次")
                lines.append(f"   有效期至: {expire}")
                lines.append("-" * 20)
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons:
            keyboard = InlineKeyboard()
            keyboard.add_button("🔙 返回", "quota_admin:back")
            
        if not self.supports_buttons:
            message += f"\n{get_separator()}\n"
            message += "💡 b-返回 | 0-退出"
            
        return message, keyboard
    
    def build_redeem_menu(self, packages: Dict[str, Any], balance: int, step: int = 2) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建兑换菜单"""
        lines = [f"🎁 兑换中心 (当前积分: {balance})\n"]
        
        i = 1
        pkg_ids = []
        for pid, pkg in packages.items():
            pkg_ids.append(pid)
            lines.append(f"{i}. {pkg['description']}")
            lines.append(f"   消耗: {pkg['points_cost']}积分")
            i += 1
            
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons:
            keyboard = InlineKeyboard()
            # 每行放一个兑换按钮
            i = 1
            for pid in pkg_ids:
                keyboard.add_button(f"兑换 {i}", f"quota_admin:redeem:{pid}")
                i += 1
            keyboard.add_row()
            keyboard.add_button("🔙 返回", "quota_admin:back")
            
        if not self.supports_buttons:
            message += f"\n{get_separator()}\n"
            message += "💡 回复数字兑换 | b-返回 | 0-退出"
            
        return message, keyboard

    def build_checkin_result(self, result: str) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建签到结果页面（二级菜单）"""
        message = f"📅 签到\n\n{result}"
        
        keyboard = None
        if self.supports_buttons:
            keyboard = InlineKeyboard()
            keyboard.add_button("🔙 返回", "quota_admin:back")
        
        return message, keyboard

    def build_help_page(self) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建帮助页面"""
        help_text = """❓ 使用帮助

📅 签到 - 每日签到获取积分
🎁 兑换 - 用积分兑换配额加成
📢 公告 - 查看系统公告

📊 配额 - 查看今日配额使用详情
💰 流水 - 查看积分收支记录
⚡ 加成 - 查看有效的配额加成

━━ 配额说明 ━━
• 每日配额在0点重置
• 会员享有更高配额
• 签到积分可兑换额外配额"""
        
        keyboard = None
        if self.supports_buttons:
            keyboard = InlineKeyboard()
            keyboard.add_button("🔙 返回", "quota_admin:back")
        
        return help_text, keyboard

    def build_user_list(
        self, 
        users: list, 
        page: int, 
        total_pages: int, 
        total_count: int,
        current_platform: str = "all",
        platforms: list = None
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建用户列表（标准化分页交互）
        
        Args:
            users: 用户列表
            page: 当前页码（从1开始）
            total_pages: 总页数
            total_count: 总用户数
            current_platform: 当前筛选的平台
            platforms: 可用平台列表
        """
        current_platform_name = self.PLATFORM_NAMES.get(current_platform, current_platform)
        lines = [f"👤 用户管理 [{current_platform_name}] ({total_count}人)\n"]
        
        if not users:
            lines.append("暂无用户数据")
        else:
            for i, user in enumerate(users, 1):
                username = user.get('username') or '无昵称'
                platform = user.get('platform', 'unknown')
                platform_name = self.PLATFORM_NAMES.get(platform, platform)
                level = user.get('level', 0)
                level_name = self.LEVEL_NAMES.get(level, "免费")
                points = user.get('balance', 0)
                last_active = user.get('last_active_at', '')
                if last_active:
                    last_active = str(last_active)[:10]
                
                lines.append(f"{i}. {username}")
                lines.append(f"   📱 {platform_name} | 👑 {level_name} | 💰 {points}")
                if last_active:
                    lines.append(f"   🕐 {last_active}")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            
            # 用户选择按钮（每行5个，与其他插件一致）
            row_buttons = []
            for i, user in enumerate(users[:10], 1):
                uid = user.get('user_id', '')
                callback = f"quota_admin:user_detail:{uid}"
                row_buttons.append({"text": str(i), "callback_data": callback})
                if len(row_buttons) == 5:
                    keyboard.buttons.append(row_buttons)
                    row_buttons = []
            if row_buttons:
                keyboard.buttons.append(row_buttons)
            
            # 翻页按钮（标准化格式）
            page_buttons = []
            if page > 1:
                callback = self._make_callback("user_page", page=page-1, platform=current_platform)
                page_buttons.append({"text": "⬅️ 上页", "callback_data": callback})
            
            # 页码显示（第三页及以上显示首页按钮）
            if page >= 3:
                callback = self._make_callback("user_page", page=1, platform=current_platform)
                page_buttons.append({"text": "🏠 首页", "callback_data": callback})
            
            if page < total_pages:
                callback = self._make_callback("user_page", page=page+1, platform=current_platform)
                page_buttons.append({"text": "下页 ➡️", "callback_data": callback})
            
            if page_buttons:
                keyboard.buttons.append(page_buttons)
            
            # 功能按钮行
            func_buttons = [
                {"text": "🔍 搜索", "callback_data": self._make_callback("user_search")},
                {"text": "🔄 平台", "callback_data": self._make_callback("user_platform")},
                {"text": "🚫 黑名单", "callback_data": "quota_admin:admin:blacklist"}
            ]
            keyboard.buttons.append(func_buttons)
            
            # 返回按钮
            keyboard.buttons.append([
                {"text": "🔙 返回", "callback_data": self._make_callback("admin_back")}
            ])
            
            # 添加页码提示到消息
            message += f"\n\n📄 第 {page}/{total_pages} 页"
        else:
            # 会话模式导航
            message += f"\n{get_separator()}\n"
            message += "💡 序号-查看详情 | p/n-翻页\n"
            message += "💡 输入平台名筛选 | b-返回 | 0-退出"
        
        return message, keyboard

    def build_platform_selector(self, platforms: list, current: str) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建平台选择器（标准化格式）"""
        lines = ["🔄 选择平台\n"]
        lines.append(f"当前: {self.PLATFORM_NAMES.get(current, current)}\n")
        
        for i, p in enumerate(platforms, 1):
            name = self.PLATFORM_NAMES.get(p, p)
            marker = "✅" if p == current else "  "
            lines.append(f"{i}. {marker} {name}")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            
            # 平台按钮（每行3个）
            row_buttons = []
            for p in platforms:
                name = self.PLATFORM_NAMES.get(p, p)
                # 当前选中的平台加上标记
                text = f"✅ {name}" if p == current else name
                callback = self._make_callback("user_filter", platform=p)
                row_buttons.append({"text": text, "callback_data": callback})
                if len(row_buttons) == 3:
                    keyboard.buttons.append(row_buttons)
                    row_buttons = []
            if row_buttons:
                keyboard.buttons.append(row_buttons)
            
            # 返回按钮
            keyboard.buttons.append([
                {"text": "🔙 返回用户列表", "callback_data": self._make_callback("user_page", page=1, platform="all")}
            ])
        else:
            message += f"\n{get_separator()}\n"
            message += "💡 输入平台名或序号筛选 | b-返回 | 0-退出"
        
        return message, keyboard

    def build_user_detail(self, user_info: Dict[str, Any]) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建用户详情页（标准化格式）"""
        user_id = user_info.get('user_id', '未知')
        username = user_info.get('username') or '无昵称'
        platform = user_info.get('platform', 'unknown')
        platform_name = self.PLATFORM_NAMES.get(platform, platform)
        
        lines = ["👤 用户详情\n"]
        lines.append(f"🆔 ID: {user_id}")
        lines.append(f"📛 昵称: {username}")
        lines.append(f"📱 平台: {platform_name}")
        
        # 会员信息
        membership = user_info.get('membership', {})
        level = membership.get('level', 0) if isinstance(membership.get('level'), int) else 0
        lines.append(f"\n👑 会员等级: {self.LEVEL_NAMES_FULL.get(level, '免费用户')}")
        if membership.get('expire_date'):
            lines.append(f"📅 到期时间: {membership['expire_date']}")
        if membership.get('days_remaining') is not None:
            lines.append(f"⏳ 剩余天数: {membership['days_remaining']}天")
        
        # 积分信息
        points = user_info.get('points', {})
        lines.append(f"\n💰 积分余额: {points.get('balance', 0)}")
        lines.append(f"📈 累计获得: {points.get('total_earned', 0)}")
        lines.append(f"📉 累计消费: {points.get('total_spent', 0)}")
        
        # 活跃信息
        created_at = user_info.get('created_at', '')
        last_active = user_info.get('last_active_at', '')
        if created_at:
            lines.append(f"\n📆 注册时间: {str(created_at)[:10]}")
        if last_active:
            lines.append(f"🕐 最后活跃: {str(last_active)[:10]}")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            
            # 操作按钮
            action_buttons = [
                {"text": "💰 充值积分", "callback_data": self._make_callback("points_add", user_id=user_id)},
                {"text": "👑 升级会员", "callback_data": self._make_callback("member_up", user_id=user_id)}
            ]
            keyboard.buttons.append(action_buttons)
            
            # 导航按钮
            nav_buttons = [
                {"text": "🔙 返回列表", "callback_data": self._make_callback("user_page", page=1, platform="all")},
                {"text": "❌ 退出", "callback_data": self._make_callback("back")}
            ]
            keyboard.buttons.append(nav_buttons)
        else:
            message += f"\n{get_separator()}\n"
            message += "💡 p 积分 原因-充值 | m 等级 天数-升级\n"
            message += "💡 b-返回列表 | 0-退出"
        
        return message, keyboard
    
    def build_search_prompt(self) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建搜索提示页面"""
        message = "🔍 搜索用户\n\n"
        message += "请输入搜索关键词：\n"
        message += "• 用户ID（完整或部分）\n"
        message += "• 用户昵称\n"
        message += "• 平台用户ID\n"
        message += "\n示例: bet、ou_6f68、123456"
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.buttons.append([
                {"text": "🔙 返回", "callback_data": self._make_callback("admin_back")},
                {"text": "❌ 取消", "callback_data": self._make_callback("back")}
            ])
        else:
            message += f"\n{get_separator()}\n"
            message += "💡 直接输入关键词搜索 | 0-退出"
        
        return message, keyboard
    
    def build_search_results(
        self, 
        keyword: str, 
        users: List[Dict], 
        total_count: int
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建搜索结果页面
        
        Args:
            keyword: 搜索关键词
            users: 匹配的用户列表
            total_count: 匹配总数
            
        Returns:
            (消息文本, 键盘)
        """
        if not users:
            message = f"🔍 搜索结果: \"{keyword}\"\n\n"
            message += "❌ 未找到匹配的用户\n"
            message += "\n请尝试其他关键词"
            
            keyboard = None
            if self.supports_buttons and InlineKeyboard is not None:
                keyboard = InlineKeyboard()
                keyboard.buttons.append([
                    {"text": "🔍 重新搜索", "callback_data": self._make_callback("user_search")},
                    {"text": "🔙 返回", "callback_data": self._make_callback("admin_back")}
                ])
            else:
                message += f"\n{get_separator()}\n"
                message += "💡 输入关键词继续搜索 | b-返回 | 0-退出"
            
            return message, keyboard
        
        lines = [f"🔍 搜索结果: \"{keyword}\" ({total_count}人)\n"]
        
        for i, user in enumerate(users[:10], 1):
            username = user.get('username') or '无昵称'
            platform = user.get('platform', 'unknown')
            platform_name = self.PLATFORM_NAMES.get(platform, platform)
            level = user.get('level', 0)
            level_name = self.LEVEL_NAMES.get(level, "免费")
            
            lines.append(f"{i}. {username}")
            lines.append(f"   📱 {platform_name} | 👑 {level_name}")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            
            # 用户选择按钮（每行5个）
            row_buttons = []
            for i, user in enumerate(users[:10], 1):
                user_id = user.get('user_id', '')
                callback = self._make_callback("user_detail", user_id=user_id)
                row_buttons.append({"text": str(i), "callback_data": callback})
                if len(row_buttons) == 5:
                    keyboard.buttons.append(row_buttons)
                    row_buttons = []
            if row_buttons:
                keyboard.buttons.append(row_buttons)
            
            # 功能按钮
            keyboard.buttons.append([
                {"text": "🔍 重新搜索", "callback_data": self._make_callback("user_search")},
                {"text": "🔙 返回", "callback_data": self._make_callback("admin_back")}
            ])
            
            if total_count > 10:
                message += f"\n\n⚠️ 显示前10个结果，共{total_count}个匹配"
        else:
            message += f"\n{get_separator()}\n"
            message += "💡 序号-查看详情 | 输入关键词继续搜索\n"
            message += "💡 b-返回 | 0-退出"
        
        return message, keyboard
    
    def build_stats_detail(self, stats: Dict[str, Any]) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建详细统计页面
        
        Args:
            stats: 统计数据
            
        Returns:
            (消息文本, 键盘)
        """
        lines = ["📊 配额使用统计（最近7天）\n"]
        
        if stats.get('top_actions'):
            lines.append("🔥 热门操作 TOP 5：")
            for i, act in enumerate(stats['top_actions'][:5], 1):
                lines.append(f"  {i}. {act['action_type']}: {act['total_count']}次")
            lines.append("")
        
        if stats.get('member_stats'):
            lines.append("👥 会员等级统计：")
            level_names = {0: "免费", 1: "高级", 2: "VIP"}
            for member in stats['member_stats']:
                level_name = level_names.get(member['level'], "未知")
                lines.append(f"  {level_name}: {member['active_users']}人, {member['total_usage']}次")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.buttons.append([
                {"text": "🔙 返回", "callback_data": self._make_callback("admin_back")}
            ])
        else:
            message += f"\n{get_separator()}\n"
            message += "💡 b-返回 | 0-退出"
        
        return message, keyboard
    
    def build_rate_limit_status(self, stats: Dict[str, Any]) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建限流状态页面
        
        Args:
            stats: 限流统计数据
            
        Returns:
            (消息文本, 键盘)
        """
        lines = ["⚡ 速率限制状态\n"]
        
        lines.append(f"👥 当前活跃用户: {stats.get('total_users', 0)}人")
        lines.append(f"📊 总请求数: {stats.get('total_requests', 0)}次")
        lines.append(f"📊 平均请求/用户: {stats.get('avg_requests_per_user', 0):.2f}次")
        
        lines.append("\n💡 限流配置（推广期）：")
        lines.append("  • 所有操作: 60次/分钟")
        
        lines.append("\n🎯 会员倍率：")
        lines.append("  • 免费: 1倍")
        lines.append("  • 高级: 2倍")
        lines.append("  • VIP: 5倍")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.buttons.append([
                {"text": "🔙 返回", "callback_data": self._make_callback("admin_back")}
            ])
        else:
            message += f"\n{get_separator()}\n"
            message += "💡 b-返回 | 0-退出"
        
        return message, keyboard
    
    def build_quota_rules_list(
        self, 
        rules: List[Dict[str, Any]], 
        plugins: List[str],
        current_plugin: str = "all"
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建配额规则列表页面
        
        Args:
            rules: 配额规则列表
            plugins: 插件列表
            current_plugin: 当前筛选的插件
            
        Returns:
            (消息文本, 键盘)
        """
        plugin_display = "全部" if current_plugin == "all" else current_plugin
        lines = [f"📋 配额规则 [{plugin_display}]\n"]
        
        if not rules:
            lines.append("暂无配额规则")
        else:
            # 按插件分组显示
            current_p = None
            for rule in rules:
                plugin = rule.get('plugin_name', 'unknown')
                if plugin != current_p:
                    current_p = plugin
                    lines.append(f"\n🔌 {plugin}")
                
                action = rule.get('action_type', '')
                desc = rule.get('description', action)
                
                # 各等级限制
                free_limit = rule.get('free_limit', -1)
                premium_limit = rule.get('premium_limit', -1)
                vip_limit = rule.get('vip_limit', -1)
                
                free_str = "无限" if free_limit == -1 else str(free_limit)
                premium_str = "无限" if premium_limit == -1 else str(premium_limit)
                vip_str = "无限" if vip_limit == -1 else str(vip_limit)
                
                lines.append(f"  • {desc}")
                lines.append(f"    免费:{free_str} | 高级:{premium_str} | VIP:{vip_str}")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            
            # 编辑配额入口
            keyboard.add_button("✏️ 编辑配额", "quota_admin:admin:edit_quota")
            keyboard.add_row()
            
            # 插件筛选按钮（每行3个）
            row_buttons = []
            all_btn = {"text": "✅ 全部" if current_plugin == "all" else "全部", 
                      "callback_data": self._make_callback("quota_filter", plugin="all")}
            row_buttons.append(all_btn)
            
            for p in plugins[:5]:  # 最多显示5个插件
                text = f"✅ {p}" if p == current_plugin else p
                callback = self._make_callback("quota_filter", plugin=p)
                row_buttons.append({"text": text, "callback_data": callback})
                if len(row_buttons) == 3:
                    keyboard.buttons.append(row_buttons)
                    row_buttons = []
            if row_buttons:
                keyboard.buttons.append(row_buttons)
            
            # 返回按钮（返回配额管理菜单）
            keyboard.buttons.append([
                {"text": "🔙 返回", "callback_data": "quota_admin:admin:quota_manage"}
            ])
        else:
            message += f"\n{get_separator()}\n"
            message += "💡 输入插件名筛选 | b-返回 | 0-退出"
        
        return message, keyboard
    
    def build_points_stats(self, stats: Dict[str, Any]) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建积分统计页面
        
        Args:
            stats: 积分统计数据
            
        Returns:
            (消息文本, 键盘)
        """
        lines = ["💰 积分统计\n"]
        
        # 总体统计
        lines.append("📊 总体数据：")
        lines.append(f"  • 用户总数: {stats.get('total_users', 0)}人")
        lines.append(f"  • 有积分用户: {stats.get('users_with_points', 0)}人")
        lines.append(f"  • 系统总积分: {stats.get('total_balance', 0)}")
        lines.append(f"  • 平均余额: {stats.get('avg_balance', 0):.1f}")
        
        # 积分流动
        lines.append("\n📈 积分流动（近7天）：")
        lines.append(f"  • 总发放: +{stats.get('total_earned_7d', 0)}")
        lines.append(f"  • 总消耗: -{stats.get('total_spent_7d', 0)}")
        lines.append(f"  • 净流入: {stats.get('net_flow_7d', 0)}")
        
        # 积分来源分布
        if stats.get('source_distribution'):
            lines.append("\n🏷️ 来源分布（近7天）：")
            for source in stats['source_distribution'][:5]:
                lines.append(f"  • {source['source']}: +{source['amount']}")
        
        # 高积分用户
        if stats.get('top_users'):
            lines.append("\n👑 积分排行 TOP 5：")
            for i, user in enumerate(stats['top_users'][:5], 1):
                username = user.get('username') or '无昵称'
                balance = user.get('balance', 0)
                lines.append(f"  {i}. {username}: {balance}")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.buttons.append([
                {"text": "🔙 返回积分管理", "callback_data": "quota_admin:admin:points_manage"}
            ])
        else:
            message += f"\n{get_separator()}\n"
            message += "💡 b-返回 | 0-退出"
        
        return message, keyboard
    
    def build_search_stats(self, stats: Dict[str, Any]) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建搜索统计页面
        
        Args:
            stats: 搜索统计数据
            
        Returns:
            (消息文本, 键盘)
        """
        lines = ["🔎 搜索统计\n"]
        
        # 总体统计
        lines.append("📊 总体数据（近7天）：")
        lines.append(f"  • 总搜索次数: {stats.get('total_searches', 0)}")
        lines.append(f"  • 搜索用户数: {stats.get('unique_users', 0)}")
        lines.append(f"  • 平均结果数: {stats.get('avg_results', 0):.1f}")
        
        # 按插件+类型+平台统计（细分）
        if stats.get('by_detail'):
            lines.append("\n🔌 分类统计：")
            for item in stats['by_detail'][:15]:  # 最多显示15条
                plugin = item.get('plugin', '?')
                stype = item.get('type') or ''
                platform = item.get('platform') or ''
                count = item.get('count', 0)
                
                # 构建显示标签（使用中文映射）
                plugin_label = self.get_plugin_name(plugin)
                label = plugin_label
                if stype:
                    stype_label = self.get_search_type_name(stype)
                    label += f"/{stype_label}"
                if platform:
                    platform_label = self.get_platform_source_name(platform)
                    label += f"({platform_label})"
                lines.append(f"  • {label}: {count}次")
        
        # 热门搜索
        if stats.get('hot_keywords'):
            lines.append("\n🔥 热门搜索 TOP 10：")
            for i, item in enumerate(stats['hot_keywords'][:10], 1):
                keyword = item.get('keyword', '')
                plugin = item.get('plugin', '')
                count = item.get('count', 0)
                plugin_label = self.get_plugin_name(plugin)
                lines.append(f"  {i}. {keyword} [{plugin_label}] ({count}次)")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.buttons.append([
                {"text": "🔙 返回", "callback_data": "quota_admin:admin:data_stats"}
            ])
        else:
            message += f"\n{get_separator()}\n"
            message += "💡 b-返回 | 0-退出"
        
        return message, keyboard
    
    def build_download_stats(self, stats: Dict[str, Any]) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建下载统计页面
        
        Args:
            stats: 下载统计数据
            
        Returns:
            (消息文本, 键盘)
        """
        lines = ["📥 下载统计\n"]
        
        # 总体统计
        lines.append("📊 总体数据（近7天）：")
        lines.append(f"  • 总下载次数: {stats.get('total_downloads', 0)}")
        lines.append(f"  • 下载用户数: {stats.get('unique_users', 0)}")
        
        # 按插件+平台/源统计（细分）
        if stats.get('by_detail'):
            lines.append("\n🔌 分类统计：")
            for item in stats['by_detail'][:15]:  # 最多显示15条
                plugin = item.get('plugin', '?')
                platform = item.get('platform') or ''
                source = item.get('source') or ''
                count = item.get('count', 0)
                
                # 构建显示标签（使用中文映射）
                plugin_label = self.get_plugin_name(plugin)
                label = plugin_label
                if platform:
                    platform_label = self.get_platform_source_name(platform)
                    label += f"({platform_label})"
                if source:
                    source_label = self.get_platform_source_name(source)
                    label += f"[{source_label}]"
                lines.append(f"  • {label}: {count}次")
        
        # 热门下载
        if stats.get('hot_items'):
            lines.append("\n🔥 热门下载 TOP 10：")
            for i, item in enumerate(stats['hot_items'][:10], 1):
                name = item.get('name') or item.get('item_id', '未知')
                plugin = item.get('plugin', '')
                count = item.get('count', 0)
                # 截断过长的名称
                if len(name) > 20:
                    name = name[:18] + '..'
                plugin_label = self.get_plugin_name(plugin)
                lines.append(f"  {i}. {name} [{plugin_label}] ({count}次)")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.buttons.append([
                {"text": "🔙 返回", "callback_data": "quota_admin:admin:data_stats"}
            ])
        else:
            message += f"\n{get_separator()}\n"
            message += "💡 b-返回 | 0-退出"
        
        return message, keyboard
    
    # ==================== 配额规则编辑 ====================
    
    def build_edit_quota_menu(self, plugins: List[str]) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建配额编辑插件选择菜单"""
        lines = ["✏️ 编辑配额规则\n"]
        lines.append("选择要编辑的插件：")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            # 每行3个按钮
            row_buttons = []
            for plugin in plugins:
                row_buttons.append({"text": f"📦 {plugin}", "callback_data": f"quota_admin:edit_plugin:{plugin}"})
                if len(row_buttons) == 3:
                    keyboard.buttons.append(row_buttons)
                    row_buttons = []
            if row_buttons:
                keyboard.buttons.append(row_buttons)
            keyboard.buttons.append([
                {"text": "🔙 返回", "callback_data": "quota_admin:admin:quota_rules"}
            ])
        
        return message, keyboard
    
    def build_edit_quota_rules(self, plugin: str, rules: List[Dict]) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建插件配额规则编辑页面"""
        lines = [f"✏️ 编辑 {plugin} 配额规则\n"]
        
        for rule in rules:
            action = rule.get('action_type', '')
            desc = rule.get('description', action)
            lines.append(f"📌 {desc} ({action})")
            
            for level in ['free', 'premium', 'vip']:
                limit = rule.get(f'{level}_daily_limit', -1)
                cost = rule.get(f'{level}_points_cost', 0)
                limit_str = "无限" if limit == -1 else f"{limit}/天"
                lines.append(f"  • {level}: {limit_str}, {cost}积分")
            lines.append("")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            # 每行3个按钮
            row_buttons = []
            for rule in rules:
                action = rule.get('action_type', '')
                desc = rule.get('description', action)
                row_buttons.append({"text": f"✏️ {desc}", "callback_data": f"quota_admin:edit_rule:{plugin}:{action}"})
                if len(row_buttons) == 3:
                    keyboard.buttons.append(row_buttons)
                    row_buttons = []
            if row_buttons:
                keyboard.buttons.append(row_buttons)
            keyboard.buttons.append([
                {"text": "🔙 返回", "callback_data": "quota_admin:admin:edit_quota"}
            ])
        
        return message, keyboard
    
    def build_edit_rule_form(self, plugin: str, action: str, rule: Dict) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建单条规则编辑表单"""
        desc = rule.get('description', action)
        lines = [f"✏️ 编辑规则: {desc}\n"]
        lines.append(f"插件: {plugin}")
        lines.append(f"操作: {action}\n")
        lines.append("当前设置：")
        
        for level in ['free', 'premium', 'vip']:
            limit = rule.get(f'{level}_daily_limit', -1)
            cost = rule.get(f'{level}_points_cost', 0)
            limit_str = "无限" if limit == -1 else str(limit)
            lines.append(f"  • {level}: 限制={limit_str}, 积分={cost}")
        
        lines.append("\n点击下方按钮修改：")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            # 快捷设置按钮
            keyboard.add_button("🔓 全部无限", f"quota_admin:set_rule:{plugin}:{action}:unlimited")
            keyboard.add_button("🔒 恢复限制", f"quota_admin:set_rule:{plugin}:{action}:limited")
            keyboard.add_row()
            # 分级别编辑 - 3个一行
            keyboard.add_button("Free", f"quota_admin:edit_level:{plugin}:{action}:free")
            keyboard.add_button("Premium", f"quota_admin:edit_level:{plugin}:{action}:premium")
            keyboard.add_button("VIP", f"quota_admin:edit_level:{plugin}:{action}:vip")
            keyboard.add_row()
            keyboard.buttons.append([
                {"text": "🔙 返回", "callback_data": f"quota_admin:edit_plugin:{plugin}"}
            ])
        
        return message, keyboard
    
    # ==================== 黑名单管理 ====================
    
    def build_blacklist_menu(self, blacklist: List[Dict], page: int = 1, page_size: int = 10) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建黑名单管理页面"""
        lines = ["🚫 黑名单管理\n"]
        
        total = len(blacklist)
        if total == 0:
            lines.append("当前没有被封禁的用户")
        else:
            start = (page - 1) * page_size
            end = min(start + page_size, total)
            page_items = blacklist[start:end]
            
            lines.append(f"共 {total} 个用户被封禁：\n")
            for i, item in enumerate(page_items, start=start+1):
                user_id = item.get('user_id', '')
                reason = item.get('reason', '未知')
                banned_at = item.get('banned_at', '')[:10] if item.get('banned_at') else ''
                lines.append(f"{i}. {user_id[:20]}")
                lines.append(f"   原因: {reason}")
                lines.append(f"   时间: {banned_at}")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("➕ 添加黑名单", "quota_admin:blacklist:add")
            keyboard.add_row()
            
            # 显示解封按钮（每行2个）
            if total > 0:
                start = (page - 1) * page_size
                end = min(start + 6, min(start + page_size, total))  # 最多6个
                page_items = blacklist[start:end]
                row_buttons = []
                for item in page_items:
                    user_id = item.get('user_id', '')
                    short_id = user_id[:12] + '..' if len(user_id) > 12 else user_id
                    row_buttons.append({"text": f"🔓 {short_id}", "callback_data": f"quota_admin:blacklist:remove:{user_id}"})
                    if len(row_buttons) == 2:
                        keyboard.buttons.append(row_buttons)
                        row_buttons = []
                if row_buttons:
                    keyboard.buttons.append(row_buttons)
            
            # 翻页
            total_pages = (total + page_size - 1) // page_size if total > 0 else 1
            if total_pages > 1:
                nav = []
                if page > 1:
                    nav.append({"text": "⬅️ 上页", "callback_data": f"quota_admin:blacklist:page:{page-1}"})
                if page < total_pages:
                    nav.append({"text": "下页 ➡️", "callback_data": f"quota_admin:blacklist:page:{page+1}"})
                if nav:
                    keyboard.buttons.append(nav)
            
            keyboard.buttons.append([
                {"text": "🔙 返回用户管理", "callback_data": "quota_admin:admin:user"}
            ])
        
        return message, keyboard
    
    # ==================== 积分操作 ====================
    
    def build_points_op_menu(self, stats: Dict[str, Any] = None) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建积分管理菜单（含统计数据）"""
        lines = ["💰 积分管理\n"]
        
        # 显示积分统计
        if stats:
            lines.append("📊 总体数据：")
            lines.append(f"  • 用户总数: {stats.get('total_users', 0)}人")
            lines.append(f"  • 有积分用户: {stats.get('users_with_points', 0)}人")
            lines.append(f"  • 系统总积分: {stats.get('total_balance', 0)}")
            lines.append(f"  • 平均余额: {stats.get('avg_balance', 0):.1f}")
            
            lines.append("\n📈 积分流动（近7天）：")
            lines.append(f"  • 总发放: +{stats.get('total_earned_7d', 0)}")
            lines.append(f"  • 总消耗: -{stats.get('total_spent_7d', 0)}")
            lines.append(f"  • 净流入: {stats.get('net_flow_7d', 0)}")
            
            if stats.get('top_users'):
                lines.append("\n👑 积分排行 TOP 5：")
                for i, user in enumerate(stats['top_users'][:5], 1):
                    username = user.get('username') or '无昵称'
                    balance = user.get('balance', 0)
                    lines.append(f"  {i}. {username}: {balance}")
        
        lines.append("\n选择操作：")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("💳 用户充值", "quota_admin:points:add_single")
            keyboard.add_button("💳 批量充值", "quota_admin:points:add_batch")
            keyboard.add_row()
            keyboard.add_button("➖ 扣除积分", "quota_admin:points:deduct")
            keyboard.add_button("🔙 返回", self._make_callback("admin_back"))
        
        return message, keyboard
    
    def build_points_input_prompt(self, op_type: str, user_id: str = None) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建积分输入提示"""
        if op_type == "add_single":
            lines = ["💳 用户充值\n"]
            lines.append("请输入: 用户ID 积分数量")
            lines.append("示例: user123 100")
        elif op_type == "add_batch":
            lines = ["💳 批量充值\n"]
            lines.append("请输入充值积分数量：")
            lines.append("示例: 50")
            lines.append("\n⚠️ 将给所有用户充值")
        elif op_type == "deduct":
            lines = ["➖ 扣除积分\n"]
            lines.append("请输入: 用户ID 积分数量")
            lines.append("示例: user123 50")
        else:
            lines = ["请输入操作参数"]
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.buttons.append([
                {"text": "❌ 取消", "callback_data": "quota_admin:admin:points_op"}
            ])
        
        return message, keyboard
    
    # ==================== 公告管理 ====================
    
    def build_announce_menu(self, announcements: List[Dict] = None) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建公告管理菜单"""
        lines = ["📢 公告管理\n"]
        
        if announcements:
            lines.append("最近公告：")
            for i, ann in enumerate(announcements[:5], 1):
                content = ann.get('content', '')[:30]
                created = ann.get('created_at', '')[:10] if ann.get('created_at') else ''
                lines.append(f"{i}. {content}... ({created})")
        else:
            lines.append("暂无公告记录")
        
        lines.append("\n选择操作：")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("📝 发送新公告", "quota_admin:announce:new")
            keyboard.add_button("🔙 返回", self._make_callback("admin_back"))
        
        return message, keyboard
    
    def build_announce_input_prompt(self) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建公告输入提示"""
        lines = ["📝 发送新公告\n"]
        lines.append("请输入公告内容：")
        lines.append("（支持多行，发送后将通知所有用户）")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.buttons.append([
                {"text": "❌ 取消", "callback_data": "quota_admin:admin:announce"}
            ])
        
        return message, keyboard
    
    def build_announcements_list(self, announcements: List[Dict], is_admin: bool = False) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建公告列表（用户端）"""
        lines = ["📢 系统公告\n"]
        
        if not announcements:
            lines.append("暂无公告")
        else:
            for ann in announcements:
                content = ann.get('content', '')
                created_at = ann.get('created_at', '')
                # 格式化时间
                if isinstance(created_at, str) and len(created_at) >= 10:
                    date_str = created_at[:10]
                else:
                    date_str = str(created_at)[:10] if created_at else ''
                
                lines.append(f"━━ {date_str} ━━")
                # 限制内容长度
                if len(content) > 100:
                    content = content[:100] + "..."
                lines.append(content)
                lines.append("")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("🔙 返回", "quota_admin:back")
        
        return message, keyboard
    
    # ==================== 数据统计子菜单 ====================
    
    def build_data_stats_menu(self, usage_stats: Dict[str, Any] = None) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建数据统计子菜单（含使用统计）"""
        lines = ["📊 数据统计\n"]
        
        # 显示使用统计
        if usage_stats:
            if usage_stats.get('top_actions'):
                lines.append("🔥 热门操作 TOP 5：")
                for i, act in enumerate(usage_stats['top_actions'][:5], 1):
                    action_type = act['action_type']
                    action_label = self.get_action_name(action_type)
                    lines.append(f"  {i}. {action_label}: {act['total_count']}次")
                lines.append("")
            
            if usage_stats.get('member_stats'):
                lines.append("👥 会员等级统计：")
                level_names = {0: "免费", 1: "高级", 2: "VIP"}
                for member in usage_stats['member_stats']:
                    level_name = level_names.get(member['level'], "未知")
                    lines.append(f"  {level_name}: {member['active_users']}人, {member['total_usage']}次")
        
        lines.append("\n查看详细统计：")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("👥 活跃用户", "quota_admin:admin:active_stats")
            keyboard.add_button("📈 插件排行", "quota_admin:admin:plugin_ranking")
            keyboard.add_row()
            keyboard.add_button("🔎 搜索统计", "quota_admin:admin:search_stats")
            keyboard.add_button("📥 下载统计", "quota_admin:admin:download_stats")
            keyboard.add_row()
            keyboard.buttons.append([
                {"text": "🔙 返回", "callback_data": self._make_callback("admin_back")}
            ])
        
        return message, keyboard
    
    def build_quota_stats_menu(self, quota_stats: Dict[str, Any] = None) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建配额使用统计菜单"""
        lines = ["📊 配额使用统计\n"]
        
        if not quota_stats:
            lines.append("暂无数据")
        else:
            # 功能使用排行
            if quota_stats.get('top_actions'):
                lines.append("🔥 功能使用排行 TOP 10：")
                for i, item in enumerate(quota_stats['top_actions'][:10], 1):
                    action = item.get('action_type', '未知')
                    count = item.get('total_count', 0)
                    # 获取中文名称
                    action_names = {
                        'music_search': '🎵搜索', 'music_download_128': '🎵128k',
                        'music_download_320': '🎵320k', 'music_download_flac': '🎵无损',
                        'music_lyric': '🎵歌词', 'douban_search': '🎬搜索',
                        'douban_view': '🎬详情', 'pansou_search': '📁搜索',
                        'pansou_download': '📁下载', 'file_process': '📄处理',
                    }
                    action_label = action_names.get(action, action)
                    lines.append(f"  {i:2d}. {action_label}: {count}次")
                lines.append("")
            
            # 用户使用排行
            if quota_stats.get('top_users'):
                lines.append("👥 用户使用排行 TOP 10：")
                for i, item in enumerate(quota_stats['top_users'][:10], 1):
                    user_id = item.get('user_id', '未知')
                    username = item.get('username', '')
                    count = item.get('total_count', 0)
                    user_label = f"{username}({user_id})" if username else user_id
                    lines.append(f"  {i:2d}. {user_label}: {count}次")
                lines.append("")
            
            # 插件使用对比
            if quota_stats.get('plugin_stats'):
                lines.append("🔌 插件使用对比：")
                plugin_names = {
                    'music': '🎵音乐', 'douban': '🎬豆瓣',
                    'pansou': '📁网盘', 'file_processor': '📄文件',
                    'book': '📚图书'
                }
                for item in quota_stats['plugin_stats']:
                    plugin = item.get('plugin_name', '未知')
                    count = item.get('total_count', 0)
                    plugin_label = plugin_names.get(plugin, plugin)
                    lines.append(f"  {plugin_label}: {count}次")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("🔙 返回", "quota_admin:back")
        
        return message, keyboard
    
    # ==================== 用户详情 ====================
    
    def build_user_detail(self, user_info: Dict[str, Any], membership: Dict[str, Any], 
                          points: Dict[str, Any], quota_usage: Dict[str, Any]) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建用户详情页面"""
        user_id = user_info.get('user_id', '未知')
        username = user_info.get('username', '无昵称')
        platform = user_info.get('platform', '未知')
        
        lines = [f"👤 用户详情\n"]
        lines.append(f"🆔 ID: {user_id}")
        lines.append(f"📛 昵称: {username}")
        lines.append(f"📱 平台: {self.PLATFORM_NAMES.get(platform, platform)}")
        
        # 会员信息
        lines.append("\n👑 会员状态：")
        level_name = membership.get('level_name', '免费用户')
        expire_date = membership.get('expire_date', '无')
        days_remaining = membership.get('days_remaining')
        lines.append(f"  • 等级: {level_name}")
        if expire_date and expire_date != '无':
            lines.append(f"  • 到期: {expire_date}")
            if days_remaining is not None:
                lines.append(f"  • 剩余: {days_remaining}天")
        
        # 积分信息
        lines.append("\n💰 积分信息：")
        balance = points.get('balance', 0) if points else 0
        lines.append(f"  • 余额: {balance}")
        
        # 配额使用
        if quota_usage:
            lines.append("\n📊 今日使用：")
            for action, count in list(quota_usage.items())[:5]:
                lines.append(f"  • {action}: {count}次")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            # 会员操作
            keyboard.add_button("👑 调整会员", f"quota_admin:member_edit:{user_id}")
            keyboard.add_button("💰 充值积分", f"quota_admin:points_add:{user_id}")
            keyboard.add_row()
            keyboard.add_button("🚫 加入黑名单", f"quota_admin:blacklist:add:{user_id}")
            keyboard.add_button("🔙 返回", "quota_admin:admin:user")
        
        return message, keyboard
    
    def build_member_edit_menu(self, user_id: str, current_level: int, expire_date: str = None) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建会员编辑菜单"""
        level_names = {0: "免费用户", 1: "高级会员", 2: "VIP会员"}
        
        lines = ["👑 调整会员等级\n"]
        lines.append(f"用户: {user_id}")
        lines.append(f"当前等级: {level_names.get(current_level, '未知')}")
        if expire_date:
            lines.append(f"到期时间: {expire_date}")
        lines.append("\n选择新等级：")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            # 等级按钮
            for level, name in level_names.items():
                marker = "✅ " if level == current_level else ""
                keyboard.add_button(f"{marker}{name}", f"quota_admin:set_member:{user_id}:{level}")
            keyboard.add_row()
            # 时长选择
            keyboard.add_button("1个月", f"quota_admin:member_duration:{user_id}:1")
            keyboard.add_button("3个月", f"quota_admin:member_duration:{user_id}:3")
            keyboard.add_button("12个月", f"quota_admin:member_duration:{user_id}:12")
            keyboard.add_row()
            keyboard.buttons.append([
                {"text": "🔙 返回", "callback_data": f"quota_admin:user_detail:{user_id}"}
            ])
        
        return message, keyboard
    
    # ==================== 限流配置 ====================
    
    def build_rate_limit_config(self, config: Dict[str, Any]) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建限流配置页面"""
        lines = ["⚡ 限流配置\n"]
        
        # 当前配置
        default_limits = config.get('default_limits', {})
        lines.append("📋 当前配置：")
        for category, (max_req, window) in default_limits.items():
            lines.append(f"  • {category}: {max_req}次/{window}秒")
        
        # 会员倍率
        lines.append("\n👥 会员倍率：")
        multipliers = config.get('multipliers', {})
        level_names = {0: "免费", 1: "高级", 2: "VIP"}
        for level, mult in multipliers.items():
            lines.append(f"  • {level_names.get(int(level), level)}: {mult}x")
        
        lines.append("\n选择要修改的配置：")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("🔧 搜索限制", "quota_admin:rate_edit:search")
            keyboard.add_button("🔧 下载限制", "quota_admin:rate_edit:download")
            keyboard.add_row()
            keyboard.add_button("🔧 AI限制", "quota_admin:rate_edit:ai")
            keyboard.add_button("🔧 默认限制", "quota_admin:rate_edit:default")
            keyboard.add_row()
            keyboard.buttons.append([
                {"text": "🔙 返回", "callback_data": self._make_callback("admin_back")}
            ])
        
        return message, keyboard
    
    def build_rate_edit_form(self, category: str, current_limit: int, current_window: int) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建限流编辑表单"""
        lines = [f"🔧 编辑 {category} 限流\n"]
        lines.append(f"当前: {current_limit}次/{current_window}秒")
        lines.append("\n选择新的限制：")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            # 预设选项
            presets = [(30, 60), (60, 60), (120, 60), (60, 30)]
            for max_req, window in presets:
                marker = "✅ " if max_req == current_limit and window == current_window else ""
                keyboard.add_button(f"{marker}{max_req}次/{window}秒", f"quota_admin:rate_set:{category}:{max_req}:{window}")
            keyboard.add_row()
            keyboard.buttons.append([
                {"text": "🔙 返回", "callback_data": "quota_admin:admin:rate_config"}
            ])
        
        return message, keyboard
    
    # ==================== 系统状态 ====================
    
    def build_system_status(self, status: Dict[str, Any]) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建系统状态页面"""
        lines = ["🖥️ 系统状态\n"]
        
        # 服务器运行状态
        server = status.get('server', {})
        uptime = server.get('uptime', '未知')
        cpu_percent = server.get('cpu_percent', 0)
        memory_percent = server.get('memory_percent', 0)
        memory_used = server.get('memory_used_mb', 0)
        
        disk_used = server.get('disk_used_gb', 0)
        disk_total = server.get('disk_total_gb', 0)
        disk_percent = server.get('disk_percent', 0)
        
        lines.append("🔧 服务器：")
        lines.append(f"  • 运行时间: {uptime}")
        lines.append(f"  • CPU使用: {cpu_percent:.1f}%")
        lines.append(f"  • 内存使用: {memory_used:.0f}MB ({memory_percent:.1f}%)")
        lines.append(f"  • 磁盘空间: {disk_used:.1f}/{disk_total:.1f}GB ({disk_percent:.1f}%)")
        
        # 插件状态
        plugins = status.get('plugins', [])
        lines.append(f"\n📦 已加载插件: {len(plugins)}个")
        for p in plugins[:8]:
            name = p.get('name', '未知')
            enabled = "✅" if p.get('enabled', True) else "❌"
            lines.append(f"  {enabled} {name}")
        if len(plugins) > 8:
            lines.append(f"  ... 还有 {len(plugins) - 8} 个")
        
        # 数据库状态
        db_status = status.get('database', {})
        lines.append(f"\n💾 数据库：")
        lines.append(f"  • 用户数: {db_status.get('user_count', 0)}")
        lines.append(f"  • 配额记录: {db_status.get('quota_count', 0)}")
        lines.append(f"  • 积分交易: {db_status.get('transaction_count', 0)}")
        
        # 限流状态
        rate_status = status.get('rate_limiter', {})
        lines.append(f"\n⚡ 限流器：")
        lines.append(f"  • 活跃用户: {rate_status.get('total_users', 0)}")
        lines.append(f"  • 总请求数: {rate_status.get('total_requests', 0)}")
        
        # 未读公告
        unread = status.get('unread_announcements', 0)
        if unread > 0:
            lines.append(f"\n📢 待推送公告: {unread}条")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("🔄 刷新", "quota_admin:admin:system")
            keyboard.add_button("🔙 返回", self._make_callback("admin_back"))
        
        return message, keyboard
    
    # ==================== 用户反馈 ====================
    
    def build_feedback_type_menu(self) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建反馈类型选择菜单（用户端）"""
        lines = ["📬 意见反馈\n"]
        lines.append("请选择反馈类型：\n")
        lines.append("💡 建议 - 功能建议或改进意见")
        lines.append("🐛 Bug - 发现的问题或错误")
        lines.append("😤 投诉 - 服务不满意")
        lines.append("👍 表扬 - 好评和鼓励")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("💡 建议", "quota_admin:feedback:type:suggestion")
            keyboard.add_button("🐛 Bug", "quota_admin:feedback:type:bug")
            keyboard.add_row()
            keyboard.add_button("😤 投诉", "quota_admin:feedback:type:complaint")
            keyboard.add_button("👍 表扬", "quota_admin:feedback:type:praise")
            keyboard.add_row()
            keyboard.add_button("📋 我的反馈", "quota_admin:my_feedbacks")
            keyboard.add_button("🔙 返回", "quota_admin:back")
        else:
            message += f"\n{get_separator()}\n"
            message += "💡 1-建议 | 2-Bug | 3-投诉 | 4-表扬\n"
            message += "💡 5-我的反馈 | b-返回 | 0-退出"
        
        return message, keyboard
    
    def build_feedback_input_prompt(self, feedback_type: str) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建反馈内容输入提示"""
        type_names = {
            'suggestion': '💡 建议',
            'bug': '🐛 Bug报告',
            'complaint': '😤 投诉',
            'praise': '👍 表扬'
        }
        type_name = type_names.get(feedback_type, '反馈')
        
        lines = [f"📬 提交{type_name}\n"]
        lines.append("请输入您的反馈内容：")
        lines.append("（直接发送文字即可）")
        lines.append("")
        lines.append("💡 提示：5分钟后会话自动结束")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("❌ 取消", "quota_admin:feedback_menu")
        else:
            message += f"\n{get_separator()}\n"
            message += "💡 直接输入内容 | 0-取消"
        
        return message, keyboard
    
    def build_feedback_success(self, feedback_id: int, feedback_type: str) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建反馈提交成功页面"""
        type_names = {
            'suggestion': '💡 建议',
            'bug': '🐛 Bug',
            'complaint': '😤 投诉',
            'praise': '👍 表扬'
        }
        type_name = type_names.get(feedback_type, '反馈')
        
        lines = ["✅ 反馈提交成功！\n"]
        lines.append(f"反馈编号: #{feedback_id}")
        lines.append(f"类型: {type_name}")
        lines.append("状态: ⏳ 待处理")
        lines.append("\n我们会尽快处理您的反馈，")
        lines.append("处理结果将通过消息通知您。")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("📋 我的反馈", "quota_admin:my_feedbacks")
            keyboard.add_button("🔙 返回", "quota_admin:back")
        
        return message, keyboard
    
    def build_my_feedbacks(self, feedbacks: List[Dict], user_id: str) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建用户反馈列表"""
        lines = ["📋 我的反馈\n"]
        
        if not feedbacks:
            lines.append("暂无反馈记录")
        else:
            type_names = {
                'suggestion': '💡', 'bug': '🐛',
                'complaint': '😤', 'praise': '👍'
            }
            status_names = {
                'pending': '⏳', 'processing': '🔄',
                'resolved': '✅', 'rejected': '❌'
            }
            
            for fb in feedbacks[:10]:
                fb_id = fb.get('id', 0)
                fb_type = type_names.get(fb.get('feedback_type', ''), '📝')
                status = status_names.get(fb.get('status', ''), '⏳')
                content = fb.get('content', '')[:30]
                if len(fb.get('content', '')) > 30:
                    content += '...'
                created = fb.get('created_at', '')
                if isinstance(created, str) and len(created) > 10:
                    created = created[:10]
                
                lines.append(f"━━ #{fb_id} {fb_type} {status} ━━")
                lines.append(f"{content}")
                if fb.get('admin_reply'):
                    reply = fb['admin_reply'][:20]
                    if len(fb['admin_reply']) > 20:
                        reply += '...'
                    lines.append(f"💬 回复: {reply}")
                lines.append(f"📅 {created}")
                lines.append("")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("📬 提交新反馈", "quota_admin:feedback_menu")
            keyboard.add_button("🔙 返回", "quota_admin:back")
        
        return message, keyboard
    
    # ==================== 管理员反馈管理 ====================
    
    def build_admin_feedback_list(
        self, 
        feedbacks: List[Dict], 
        pending_count: int,
        total: int,
        current_status: str = None,
        page: int = 1,
        page_size: int = 10
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建管理员反馈列表"""
        status_filter = current_status or "all"
        status_display = {
            'all': '全部',
            'pending': '待处理',
            'processing': '处理中',
            'resolved': '已解决',
            'rejected': '已拒绝'
        }
        
        lines = [f"📬 反馈管理 [{status_display.get(status_filter, '全部')}]"]
        if pending_count > 0:
            lines[0] += f" ({pending_count}条待处理)"
        lines.append("")
        
        if not feedbacks:
            lines.append("暂无反馈记录")
        else:
            type_names = {
                'suggestion': '💡建议', 'bug': '🐛Bug',
                'complaint': '😤投诉', 'praise': '👍表扬'
            }
            status_icons = {
                'pending': '⏳', 'processing': '🔄',
                'resolved': '✅', 'rejected': '❌'
            }
            
            for i, fb in enumerate(feedbacks, 1):
                fb_id = fb.get('id', 0)
                fb_type = type_names.get(fb.get('feedback_type', ''), '📝')
                status = status_icons.get(fb.get('status', ''), '⏳')
                username = fb.get('username') or '匿名'
                content = fb.get('content', '')[:25]
                if len(fb.get('content', '')) > 25:
                    content += '...'
                created = fb.get('created_at', '')
                if isinstance(created, str) and len(created) > 16:
                    created = created[5:16]  # 显示 MM-DD HH:MM
                
                lines.append(f"{i}. #{fb_id} {fb_type} {status}")
                lines.append(f"   👤 {username}")
                lines.append(f"   {content}")
                lines.append(f"   📅 {created}")
                lines.append("")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            
            # 反馈选择按钮（每行5个）
            row_buttons = []
            for i, fb in enumerate(feedbacks[:10], 1):
                fb_id = fb.get('id', 0)
                callback = f"quota_admin:feedback:detail:{fb_id}"
                row_buttons.append({"text": str(i), "callback_data": callback})
                if len(row_buttons) == 5:
                    keyboard.buttons.append(row_buttons)
                    row_buttons = []
            if row_buttons:
                keyboard.buttons.append(row_buttons)
            
            # 状态筛选按钮
            filter_buttons = []
            for s, name in [('pending', '⏳待处理'), ('resolved', '✅已处理'), ('all', '📋全部')]:
                marker = "✓" if s == status_filter else ""
                callback = f"quota_admin:feedback:filter:{s}"
                filter_buttons.append({"text": f"{marker}{name}", "callback_data": callback})
            keyboard.buttons.append(filter_buttons)
            
            # 翻页
            total_pages = (total + page_size - 1) // page_size if total > 0 else 1
            if total_pages > 1:
                nav = []
                if page > 1:
                    nav.append({"text": "⬅️ 上页", "callback_data": f"quota_admin:feedback:page:{page-1}:{status_filter}"})
                nav.append({"text": f"{page}/{total_pages}", "callback_data": "quota_admin:noop"})
                if page < total_pages:
                    nav.append({"text": "下页 ➡️", "callback_data": f"quota_admin:feedback:page:{page+1}:{status_filter}"})
                keyboard.buttons.append(nav)
            
            # 返回按钮
            keyboard.buttons.append([
                {"text": "🔙 返回", "callback_data": self._make_callback("admin_back")}
            ])
        else:
            message += f"\n{get_separator()}\n"
            message += "💡 序号-查看详情 | p/n-翻页\n"
            message += "💡 b-返回 | 0-退出"
        
        return message, keyboard
    
    def build_feedback_detail(self, feedback: Dict, is_admin: bool = True) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建反馈详情页面"""
        fb_id = feedback.get('id', 0)
        user_id = feedback.get('user_id', '未知')
        username = feedback.get('username') or '匿名'
        fb_type = feedback.get('feedback_type', 'suggestion')
        content = feedback.get('content', '')
        status = feedback.get('status', 'pending')
        plugin = feedback.get('plugin_name', '')
        created = feedback.get('created_at', '')
        admin_reply = feedback.get('admin_reply', '')
        replied_at = feedback.get('replied_at', '')
        
        type_names = {
            'suggestion': '💡 建议', 'bug': '🐛 Bug',
            'complaint': '😤 投诉', 'praise': '👍 表扬'
        }
        status_names = {
            'pending': '⏳ 待处理', 'processing': '🔄 处理中',
            'resolved': '✅ 已解决', 'rejected': '❌ 已拒绝'
        }
        
        lines = [f"📬 反馈详情 #{fb_id}\n"]
        lines.append(f"👤 用户: {username}")
        lines.append(f"🆔 ID: {user_id}")
        if isinstance(created, str) and len(created) > 16:
            created = created[:16]
        lines.append(f"📅 时间: {created}")
        lines.append(f"🏷️ 类型: {type_names.get(fb_type, fb_type)}")
        if plugin:
            lines.append(f"📦 插件: {plugin}")
        
        lines.append("\n━━ 反馈内容 ━━")
        lines.append(content)
        
        lines.append(f"\n━━ 状态: {status_names.get(status, status)} ━━")
        
        if admin_reply:
            lines.append("\n💬 管理员回复:")
            lines.append(admin_reply)
            if replied_at:
                if isinstance(replied_at, str) and len(replied_at) > 16:
                    replied_at = replied_at[:16]
                lines.append(f"📅 回复时间: {replied_at}")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            
            if is_admin:
                # 管理员操作按钮
                if status == 'pending' or status == 'processing':
                    keyboard.add_button("✅ 已解决", f"quota_admin:feedback:resolve:{fb_id}")
                    keyboard.add_button("❌ 拒绝", f"quota_admin:feedback:reject:{fb_id}")
                    keyboard.add_row()
                keyboard.add_button("💬 回复", f"quota_admin:feedback:reply:{fb_id}")
                keyboard.add_row()
                keyboard.add_button("🔙 返回列表", "quota_admin:admin:feedback")
            else:
                keyboard.add_button("🔙 返回", "quota_admin:my_feedbacks")
        
        return message, keyboard
    
    def build_feedback_reply_prompt(self, feedback_id: int) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建反馈回复输入提示"""
        lines = [f"💬 回复反馈 #{feedback_id}\n"]
        lines.append("请输入回复内容：")
        lines.append("（回复后将通知用户）")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("❌ 取消", f"quota_admin:feedback:detail:{feedback_id}")
        
        return message, keyboard
    
    def build_feedback_stats(self, stats: Dict) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建反馈统计页面"""
        lines = ["📊 反馈统计\n"]
        
        lines.append(f"📝 总反馈数: {stats.get('total', 0)}")
        lines.append(f"📅 今日新增: {stats.get('today_count', 0)}")
        lines.append(f"⏱️ 平均响应: {stats.get('avg_response_hours', 0)}小时")
        
        lines.append("\n📋 状态分布:")
        lines.append(f"  ⏳ 待处理: {stats.get('pending', 0)}")
        lines.append(f"  ✅ 已解决: {stats.get('resolved', 0)}")
        
        by_type = stats.get('by_type', {})
        if by_type:
            lines.append("\n🏷️ 类型分布:")
            type_names = {'suggestion': '建议', 'bug': 'Bug', 'complaint': '投诉', 'praise': '表扬'}
            for t, count in by_type.items():
                lines.append(f"  {type_names.get(t, t)}: {count}")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("📋 查看列表", "quota_admin:admin:feedback")
            keyboard.add_button("🔙 返回", self._make_callback("admin_back"))
        
        return message, keyboard
    
    # ==================== 活跃用户统计 ====================
    
    def build_active_users_stats(self, stats: Dict[str, Any]) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建活跃用户统计页面"""
        lines = ["👥 活跃用户统计\n"]
        
        # DAU
        today_dau = stats.get('today_dau', 0)
        yesterday_dau = stats.get('yesterday_dau', 0)
        dau_change = stats.get('dau_change', 0)
        avg_dau = stats.get('avg_dau_7d', 0)
        
        change_icon = "📈" if dau_change >= 0 else "📉"
        change_str = f"{change_icon} {abs(dau_change):.1f}%"
        
        lines.append("📊 日活跃用户 (DAU)：")
        lines.append(f"  • 今日: {today_dau}人")
        lines.append(f"  • 昨日: {yesterday_dau}人 ({change_str})")
        lines.append(f"  • 7日均值: {avg_dau}人")
        
        # 留存率
        retention = stats.get('retention', {})
        if retention:
            lines.append("\n📈 用户留存率：")
            lines.append(f"  • 次日留存: {retention.get('day1_retention', 0)}%")
            lines.append(f"  • 7日留存: {retention.get('day7_retention', 0)}%")
            lines.append(f"  • 30日留存: {retention.get('day30_retention', 0)}%")
            if retention.get('base_date'):
                lines.append(f"  (基准日: {retention['base_date']})")
        
        # 插件排行
        plugin_ranking = stats.get('plugin_ranking', [])
        if plugin_ranking:
            lines.append("\n🔥 插件使用排行：")
            for i, p in enumerate(plugin_ranking[:5], 1):
                plugin = p.get('plugin_name', '未知')
                plugin_label = self.PLUGIN_NAMES.get(plugin, plugin)
                total = p.get('total_actions', 0)
                users = p.get('unique_users', 0)
                lines.append(f"  {i}. {plugin_label}: {total}次 ({users}人)")
        
        # 趋势
        trend = stats.get('trend', [])
        if trend and len(trend) >= 3:
            lines.append("\n📅 近期趋势：")
            for item in trend[-3:]:
                date = item.get('date', '')
                if isinstance(date, str) and len(date) > 5:
                    date = date[5:]  # MM-DD
                dau = item.get('dau', 0)
                lines.append(f"  {date}: {dau}人")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("🔄 刷新", "quota_admin:admin:active_stats")
            keyboard.add_button("🔙 返回", "quota_admin:admin:data_stats")
        
        return message, keyboard
    
    # ==================== 任务系统页面 ====================
    
    def build_tasks_page(
        self, 
        tasks: List[tuple],
        task_type: str = "daily",
        claimable_count: int = 0,
        claimable_points: int = 0,
        step: int = 1
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建任务列表页面
        
        Args:
            tasks: [(TaskDefinition, UserTaskProgress), ...]
            task_type: 任务类型 (daily/weekly/monthly/onetime)
            claimable_count: 可领取任务数
            claimable_points: 可领取积分
            step: 当前步骤
        """
        type_names = {
            "daily": "每日",
            "weekly": "每周", 
            "monthly": "每月",
            "onetime": "新手"
        }
        type_name = type_names.get(task_type, "")
        
        completed = sum(1 for _, p in tasks if p.completed)
        total = len(tasks)
        
        lines = [f"📋 {type_name}任务 ({completed}/{total})\n"]
        
        for task, progress in tasks:
            # 状态图标
            if progress.reward_claimed:
                status = "✅"
            elif progress.completed:
                status = "🎁"  # 可领取
            else:
                status = "⬜"
            
            # 进度显示
            progress_str = f"[{progress.progress}/{progress.target}]"
            
            # 奖励显示
            if progress.reward_claimed:
                reward_str = "已领取"
            elif progress.completed:
                reward_str = f"待领取 +{task.reward_points}"
            else:
                reward_str = f"+{task.reward_points}"
            
            lines.append(f"{status} {task.icon} {task.name} {progress_str} {reward_str}")
        
        if claimable_count > 0:
            lines.append(f"\n💰 可领取: {claimable_points}积分 ({claimable_count}个)")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            # 任务类型切换
            keyboard.add_button("📅 每日", "quota_admin:tasks:daily")
            keyboard.add_button("📆 每周", "quota_admin:tasks:weekly")
            keyboard.add_button("📆 每月", "quota_admin:tasks:monthly")
            keyboard.add_row()
            keyboard.add_button("🎯 新手", "quota_admin:tasks:onetime")
            if claimable_count > 0:
                keyboard.add_button(f"🎁 领取 (+{claimable_points})", "quota_admin:tasks:claim")
            keyboard.add_row()
            keyboard.add_button("🔙 返回", "quota_admin:back")
            keyboard.add_button("❌ 关闭", "quota_admin:close")
        else:
            message += self._add_nav_hint()
        
        return message, keyboard
    
    # ==================== 邀请系统页面 ====================
    
    def build_invite_page(
        self,
        invite_code: str,
        invite_link: str = None,
        stats: Dict[str, Any] = None,
        invitees: List[Dict] = None,
        inviter: str = None,
        step: int = 1
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建邀请页面
        
        Args:
            invite_code: 邀请码
            invite_link: 邀请链接（Telegram）
            stats: 邀请统计
            invitees: 邀请的用户列表
            inviter: 邀请人ID
            step: 当前步骤
        """
        stats = stats or {}
        
        lines = ["👥 邀请好友\n"]
        
        # 邀请统计
        total = stats.get('successful_invites', 0)
        rewards = stats.get('total_rewards', 0)
        lines.append(f"📊 已邀请: {total}人 | 获得: {rewards}积分")
        
        # 邀请码/链接
        lines.append("\n━━ 我的邀请码 ━━")
        lines.append(f"📎 {invite_code}")
        
        if invite_link:
            lines.append(f"\n🔗 邀请链接:")
            lines.append(invite_link)
        
        # 奖励说明
        lines.append("\n━━ 邀请奖励 ━━")
        lines.append("• 邀请人获得: 50积分")
        lines.append("• 被邀请人获得: 30积分")
        
        # 我的邀请人
        if inviter:
            lines.append(f"\n👤 我的邀请人: {inviter[:10]}...")
        
        # 邀请记录
        if invitees:
            lines.append("\n━━ 邀请记录 ━━")
            for inv in invitees[:5]:
                invitee_id = inv.get('invitee_id', '')[:8] + "..."
                reward = inv.get('inviter_reward', 0)
                lines.append(f"• {invitee_id} +{reward}积分")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            # 复制邀请码按钮（部分平台支持）
            if invite_link:
                keyboard.add_button("📤 分享链接", url=invite_link)
            keyboard.add_row()
            keyboard.add_button("📋 邀请任务", "quota_admin:tasks:onetime")
            keyboard.add_button("🏆 邀请榜", "quota_admin:invite:rank")
            keyboard.add_row()
            keyboard.add_button("🔙 返回", "quota_admin:back")
            keyboard.add_button("❌ 关闭", "quota_admin:close")
        else:
            message += f"\n{get_separator()}\n"
            message += "💡 发送邀请码给好友，好友使用 /绑定邀请 {邀请码} 绑定\n"
            message += self._add_nav_hint()
        
        return message, keyboard
    
    def build_invite_rank_page(
        self,
        leaderboard: List[Dict],
        my_rank: int = 0,
        step: int = 2
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建邀请排行榜页面"""
        lines = ["🏆 邀请排行榜\n"]
        
        if leaderboard:
            for i, entry in enumerate(leaderboard, 1):
                user_id = entry.get('user_id', '')
                display_id = user_id[:8] + "..." if len(user_id) > 10 else user_id
                invites = entry.get('successful_invites', 0)
                rewards = entry.get('total_rewards', 0)
                
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
                lines.append(f"{medal} {display_id} - {invites}人 ({rewards}积分)")
        else:
            lines.append("暂无邀请记录")
        
        if my_rank > 0:
            lines.append(f"\n📍 我的排名: 第{my_rank}名")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("🔙 返回邀请", "quota_admin:invite")
            keyboard.add_button("❌ 关闭", "quota_admin:close")
        
        return message, keyboard
    
    # ==================== 定时任务页面 ====================
    
    def build_scheduler_menu(
        self,
        tasks: List[Dict[str, Any]],
        recent_logs: List[Dict[str, Any]] = None
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建定时任务管理页面
        
        Args:
            tasks: 任务列表
            recent_logs: 最近的执行日志
        """
        lines = ["⏰ 定时任务管理\n"]
        
        # 统计信息
        total_tasks = len(tasks)
        enabled_tasks = sum(1 for t in tasks if t.get('enabled', False))
        running_tasks = sum(1 for t in tasks if t.get('status') == 'running')
        
        lines.append(f"📊 任务统计: 共 {total_tasks} 个任务")
        lines.append(f"  • 启用: {enabled_tasks} | 运行中: {running_tasks}")
        
        if tasks:
            lines.append("\n━━ 任务列表 ━━")
            
            # 按插件分组显示
            plugins = {}
            for task in tasks:
                plugin = task.get('plugin_name', 'unknown')
                if plugin not in plugins:
                    plugins[plugin] = []
                plugins[plugin].append(task)
            
            for plugin, plugin_tasks in plugins.items():
                lines.append(f"\n📦 {plugin}:")
                for task in plugin_tasks:
                    task_id = task.get('task_id', '')
                    desc = task.get('description', task_id)
                    enabled = task.get('enabled', False)
                    status = task.get('status', 'pending')
                    cron = task.get('cron')
                    interval_seconds = task.get('interval_seconds')
                    
                    # 状态图标
                    if not enabled:
                        status_icon = "⏸️"  # 禁用
                    elif status == 'running':
                        status_icon = "🔄"  # 运行中
                    elif status == 'success':
                        status_icon = "✅"  # 成功
                    elif status == 'failed':
                        status_icon = "❌"  # 失败
                    else:
                        status_icon = "⏳"  # 等待
                    
                    # 调度时间描述
                    schedule_desc = ""
                    if cron:
                        # 解析 cron 表达式为人类可读格式
                        schedule_desc = self._parse_cron_to_text(cron)
                    elif interval_seconds:
                        if interval_seconds < 60:
                            schedule_desc = f"每{interval_seconds}秒"
                        elif interval_seconds < 3600:
                            schedule_desc = f"每{interval_seconds // 60}分钟"
                        else:
                            schedule_desc = f"每{interval_seconds // 3600}小时"
                    
                    lines.append(f"  {status_icon} {desc}")
                    
                    # 定时时间
                    if schedule_desc:
                        lines.append(f"     ⏱️ {schedule_desc}")
                    
                    # 下次执行时间
                    next_run = task.get('next_run')
                    if next_run:
                        try:
                            from datetime import datetime
                            if isinstance(next_run, str):
                                next_dt = datetime.fromisoformat(next_run.replace('Z', '+00:00'))
                                next_str = next_dt.strftime("%m-%d %H:%M")
                            else:
                                next_str = str(next_run)[:16]
                            lines.append(f"     📅 下次: {next_str}")
                        except:
                            pass
                    
                    # 执行统计
                    run_count = task.get('run_count', 0)
                    success_count = task.get('success_count', 0)
                    fail_count = task.get('fail_count', 0)
                    if run_count > 0:
                        lines.append(f"     📊 执行: {run_count}次 (成功{success_count}/失败{fail_count})")
        else:
            lines.append("\n暂无定时任务")
        
        # 最近执行日志
        if recent_logs:
            lines.append("\n━━ 最近执行 ━━")
            for log in recent_logs[:5]:
                task_id = log.get('task_id', '')
                status = log.get('status', '')
                started_at = log.get('started_at', '')
                duration_ms = log.get('duration_ms', 0)
                
                status_icon = "✅" if status == 'success' else "❌"
                
                # 格式化时间
                try:
                    from datetime import datetime
                    if isinstance(started_at, str):
                        start_dt = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                        time_str = start_dt.strftime("%m-%d %H:%M")
                    else:
                        time_str = str(started_at)[:16]
                except:
                    time_str = str(started_at)[:16]
                
                # 简化任务ID显示
                short_id = task_id.split(':')[-1] if ':' in task_id else task_id
                lines.append(f"  {status_icon} {short_id} | {time_str} | {duration_ms}ms")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("📊 每日报告", "quota_admin:scheduler:daily_report")
            keyboard.add_button("🔄 刷新", "quota_admin:admin:scheduler")
            keyboard.add_row()
            keyboard.add_button("🔙 返回", "quota_admin:admin_back")
        
        return message, keyboard
    
    # ==================== 每日报告配置页面 ====================
    
    def build_daily_report_config(
        self,
        config: Dict[str, Any],
        next_run: str = None
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建每日报告配置页面
        
        Args:
            config: 当前配置 {
                'enabled': bool,
                'send_time': str,  # "HH:MM"
                'report_level': str,  # "brief" 或 "full"
                'admin_ids': list
            }
            next_run: 下次执行时间
        """
        enabled = config.get('enabled', True)
        send_time = config.get('send_time', '21:00')
        report_level = config.get('report_level', 'full')
        admin_ids = config.get('admin_ids', [])
        
        level_names = {'brief': '简报', 'full': '完整报告'}
        level_name = level_names.get(report_level, report_level)
        
        lines = ["📊 每日统计报告\n"]
        
        # 状态
        status_icon = "✅" if enabled else "❌"
        lines.append(f"状态: {status_icon} {'已启用' if enabled else '已禁用'}")
        lines.append(f"发送时间: ⏰ {send_time}")
        lines.append(f"报告级别: 📝 {level_name}")
        lines.append(f"接收人数: 👤 {len(admin_ids)}人")
        
        if next_run:
            lines.append(f"\n下次发送: {next_run}")
        
        lines.append("\n━━ 报告内容 ━━")
        lines.append("• 用户活跃统计 (DAU/留存率)")
        lines.append("• 请求/积分统计")
        lines.append("• 热门操作/搜索/下载 TOP5")
        lines.append("• 插件使用排行")
        lines.append("• 系统状态信息")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            # 开启/关闭
            if enabled:
                keyboard.add_button("❌ 关闭报告", "quota_admin:scheduler:daily_report:toggle:0")
            else:
                keyboard.add_button("✅ 开启报告", "quota_admin:scheduler:daily_report:toggle:1")
            keyboard.add_row()
            # 时间设置
            keyboard.add_button("⏰ 设置时间", "quota_admin:scheduler:daily_report:time")
            # 报告级别
            keyboard.add_button("📝 切换级别", "quota_admin:scheduler:daily_report:level")
            keyboard.add_row()
            # 预览和立即发送
            keyboard.add_button("👁️ 预览报告", "quota_admin:scheduler:daily_report:preview")
            keyboard.add_button("📤 立即发送", "quota_admin:scheduler:daily_report:send")
            keyboard.add_row()
            keyboard.add_button("🔙 返回", "quota_admin:admin:scheduler")
        
        return message, keyboard
    
    def build_daily_report_time_select(
        self,
        current_time: str = "08:00"
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建每日报告时间选择页面
        
        Args:
            current_time: 当前设置的时间
        """
        lines = ["⏰ 设置发送时间\n"]
        lines.append(f"当前: {current_time}")
        lines.append("💡 报告内容为昨日的完整统计")
        lines.append("\n选择新的发送时间：")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            # 常用时间选项（优先显示早上时段）
            times = ["07:00", "08:00", "09:00", "12:00", "18:00", "21:00"]
            for i, t in enumerate(times):
                marker = "✅" if t == current_time else ""
                keyboard.add_button(f"{marker}{t}", f"quota_admin:scheduler:daily_report:set_time:{t}")
                if (i + 1) % 3 == 0:
                    keyboard.add_row()
            keyboard.add_row()
            keyboard.add_button("🔙 返回", "quota_admin:scheduler:daily_report")
        
        return message, keyboard
    
    def build_daily_report_level_select(
        self,
        current_level: str = "full"
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建每日报告级别选择页面
        
        Args:
            current_level: 当前设置的级别
        """
        lines = ["📝 选择报告级别\n"]
        lines.append(f"当前: {'简报' if current_level == 'brief' else '完整报告'}")
        lines.append("\n━━ 简报 (brief) ━━")
        lines.append("• 仅包含核心指标")
        lines.append("• DAU、请求数、积分流通")
        lines.append("• 热门操作 TOP3")
        lines.append("\n━━ 完整报告 (full) ━━")
        lines.append("• 包含所有统计数据")
        lines.append("• 用户活跃、留存率")
        lines.append("• 热门操作/搜索/下载 TOP5")
        lines.append("• 插件排行、系统状态")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            brief_marker = "✅" if current_level == 'brief' else ""
            full_marker = "✅" if current_level == 'full' else ""
            keyboard.add_button(f"{brief_marker}📋 简报", "quota_admin:scheduler:daily_report:set_level:brief")
            keyboard.add_button(f"{full_marker}📑 完整报告", "quota_admin:scheduler:daily_report:set_level:full")
            keyboard.add_row()
            keyboard.add_button("🔙 返回", "quota_admin:scheduler:daily_report")
        
        return message, keyboard
    
    def build_daily_report_preview(
        self,
        report: str
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建每日报告预览页面
        
        Args:
            report: 报告内容
        """
        lines = ["👁️ 报告预览\n"]
        lines.append(report)
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("📤 立即发送", "quota_admin:scheduler:daily_report:send")
            keyboard.add_button("🔙 返回", "quota_admin:scheduler:daily_report")
        
        return message, keyboard
    
    def build_daily_report_send_result(
        self,
        results: Dict[str, bool]
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建每日报告发送结果页面
        
        Args:
            results: 发送结果 {user_id: success}
        """
        success_count = sum(1 for v in results.values() if v)
        total_count = len(results)
        
        if total_count == 0:
            lines = ["⚠️ 没有配置接收人"]
            lines.append("\n请先在插件配置中设置管理员ID")
        elif success_count == total_count:
            lines = [f"✅ 发送成功"]
            lines.append(f"\n已发送给 {total_count} 位管理员")
        else:
            lines = [f"⚠️ 部分发送失败"]
            lines.append(f"\n成功: {success_count}/{total_count}")
            # 显示失败的
            failed = [uid for uid, ok in results.items() if not ok]
            if failed:
                lines.append(f"\n失败: {', '.join(failed[:3])}")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("🔙 返回", "quota_admin:scheduler:daily_report")
        
        return message, keyboard
    
    # ==================== 订阅配置页面 ====================
    
    def build_subscription_config_menu(
        self,
        configs: Dict[int, Dict[str, Any]]
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建订阅配置管理页面
        
        Args:
            configs: 各等级配置 {level: config}
        """
        lines = ["📝 订阅配置\n"]
        
        # 订阅源访问等级名称
        access_names = {0: '公开', 1: '注册', 2: '会员', 3: 'VIP'}
        
        lines.append("━━ 订阅数量上限 ━━")
        for level in [0, 1, 2]:  # FREE, PREMIUM, VIP
            config = configs.get(level, {})
            level_name = config.get('level_name', ['免费用户', '高级会员', 'VIP会员'][level])
            max_subs = config.get('max_subscriptions', 3)
            max_str = '无限' if max_subs == -1 else f'{max_subs}个'
            
            icon = ['👤', '💎', '👑'][level]
            lines.append(f"{icon} {level_name}: {max_str}")
        
        lines.append("\n━━ 订阅源访问权限 ━━")
        for level in [0, 1, 2]:
            config = configs.get(level, {})
            level_name = config.get('level_name', ['免费用户', '高级会员', 'VIP会员'][level])
            access_levels = config.get('source_access', [0])
            access_str = '+'.join([access_names.get(a, '未知') for a in access_levels])
            
            icon = ['👤', '💎', '👑'][level]
            lines.append(f"{icon} {level_name}: {access_str}源")
        
        lines.append("\n💡 点击下方按钮编辑各等级配置")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("👤 免费用户", "quota_admin:sub_config:edit:0")
            keyboard.add_button("💎 高级会员", "quota_admin:sub_config:edit:1")
            keyboard.add_row()
            keyboard.add_button("👑 VIP会员", "quota_admin:sub_config:edit:2")
            keyboard.add_button("🔙 返回", "subscription:admin:stats")
        
        return message, keyboard
    
    def build_subscription_config_edit(
        self,
        level: int,
        config: Dict[str, Any]
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建订阅配置编辑页面
        
        Args:
            level: 会员等级 (0=FREE, 1=PREMIUM, 2=VIP)
            config: 当前配置
        """
        level_names = ['免费用户', '高级会员', 'VIP会员']
        level_icons = ['👤', '💎', '👑']
        access_names = {0: '公开', 1: '注册', 2: '会员', 3: 'VIP'}
        
        level_name = level_names[level] if level < 3 else '未知'
        level_icon = level_icons[level] if level < 3 else '❓'
        
        max_subs = config.get('max_subscriptions', 3)
        max_str = '无限' if max_subs == -1 else str(max_subs)
        access_levels = config.get('source_access', [0])
        access_str = '+'.join([access_names.get(a, '未知') for a in access_levels])
        
        lines = [f"✈️ 编辑 {level_icon} {level_name} 订阅配置\n"]
        
        lines.append(f"📊 订阅数量上限: {max_str}")
        lines.append(f"🔗 订阅源访问: {access_str}源")
        
        lines.append("\n━━ 设置订阅数量 ━━")
        lines.append("点击下方按钮快速设置")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            # 订阅数量快捷设置
            keyboard.add_button("3个", f"quota_admin:sub_config:set_limit:{level}:3")
            keyboard.add_button("5个", f"quota_admin:sub_config:set_limit:{level}:5")
            keyboard.add_button("10个", f"quota_admin:sub_config:set_limit:{level}:10")
            keyboard.add_row()
            keyboard.add_button("20个", f"quota_admin:sub_config:set_limit:{level}:20")
            keyboard.add_button("50个", f"quota_admin:sub_config:set_limit:{level}:50")
            keyboard.add_button("无限", f"quota_admin:sub_config:set_limit:{level}:-1")
            keyboard.add_row()
            # 访问权限设置
            keyboard.add_button("🔓 仅公开源", f"quota_admin:sub_config:set_access:{level}:0")
            keyboard.add_button("🔐 含会员源", f"quota_admin:sub_config:set_access:{level}:0,1,2")
            keyboard.add_row()
            keyboard.add_button("🔑 全部源", f"quota_admin:sub_config:set_access:{level}:0,1,2,3")
            keyboard.add_button("🔙 返回订阅配置", "quota_admin:admin:sub_config")
        
        return message, keyboard
    
    # ==================== 会员配置页面 ====================
    
    def build_member_config_menu(
        self,
        configs: Dict[int, Dict[str, Any]]
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建会员权益配置页面
        
        Args:
            configs: 各等级配置 {level: config}
        """
        lines = ["🌟 会员权益配置\n"]
        
        for level in [0, 1, 2]:  # FREE, PREMIUM, VIP
            config = configs.get(level, {})
            level_name = config.get('level_name', ['免费用户', '高级会员', 'VIP会员'][level])
            icon = ['👤', '💎', '👑'][level]
            
            ad_enabled = config.get('ad_enabled', True)
            custom_time = config.get('custom_push_time', False)
            priority_push = config.get('priority_push', False)
            history_days = config.get('history_days', 7)
            history_str = '永久' if history_days == -1 else f'{history_days}天'
            
            lines.append(f"{icon} {level_name}")
            lines.append(f"  • 广告: {'显示' if ad_enabled else '关闭'}")
            lines.append(f"  • 自定义推送时间: {'✅' if custom_time else '❌'}")
            lines.append(f"  • 优先推送: {'✅' if priority_push else '❌'}")
            lines.append(f"  • 历史保留: {history_str}")
            lines.append("")
        
        lines.append("💡 点击下方按钮编辑各等级权益")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("👤 免费用户", "quota_admin:member_config:edit:0")
            keyboard.add_button("💎 高级会员", "quota_admin:member_config:edit:1")
            keyboard.add_row()
            keyboard.add_button("👑 VIP会员", "quota_admin:member_config:edit:2")
            keyboard.add_button("🔙 返回", "quota_admin:admin_back")
        
        return message, keyboard
    
    def build_member_config_edit(
        self,
        level: int,
        config: Dict[str, Any]
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建会员权益编辑页面
        
        Args:
            level: 会员等级 (0=FREE, 1=PREMIUM, 2=VIP)
            config: 当前配置
        """
        level_names = ['免费用户', '高级会员', 'VIP会员']
        level_icons = ['👤', '💎', '👑']
        
        level_name = level_names[level] if level < 3 else '未知'
        level_icon = level_icons[level] if level < 3 else '❓'
        
        ad_enabled = config.get('ad_enabled', True)
        custom_time = config.get('custom_push_time', False)
        priority_push = config.get('priority_push', False)
        history_days = config.get('history_days', 7)
        
        lines = [f"✈️ 编辑 {level_icon} {level_name} 权益\n"]
        
        lines.append(f"📺 广告显示: {'开启' if ad_enabled else '关闭'}")
        lines.append(f"⏰ 自定义推送时间: {'✅支持' if custom_time else '❌不支持'}")
        lines.append(f"🚀 优先推送: {'✅开启' if priority_push else '❌关闭'}")
        lines.append(f"📅 历史保留: {'永久' if history_days == -1 else f'{history_days}天'}")
        
        lines.append("\n━━ 快速设置 ━━")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            # 广告开关
            if ad_enabled:
                keyboard.add_button("📺 关闭广告", f"quota_admin:member_config:set_ad:{level}:0")
            else:
                keyboard.add_button("📺 开启广告", f"quota_admin:member_config:set_ad:{level}:1")
            # 自定义时间
            if custom_time:
                keyboard.add_button("⏰ 禁用自定义时间", f"quota_admin:member_config:set_custom_time:{level}:0")
            else:
                keyboard.add_button("⏰ 启用自定义时间", f"quota_admin:member_config:set_custom_time:{level}:1")
            keyboard.add_row()
            # 优先推送
            if priority_push:
                keyboard.add_button("🚀 关闭优先推送", f"quota_admin:member_config:set_priority:{level}:0")
            else:
                keyboard.add_button("🚀 开启优先推送", f"quota_admin:member_config:set_priority:{level}:1")
            keyboard.add_row()
            # 历史保留
            keyboard.add_button("7天", f"quota_admin:member_config:set_history:{level}:7")
            keyboard.add_button("30天", f"quota_admin:member_config:set_history:{level}:30")
            keyboard.add_button("90天", f"quota_admin:member_config:set_history:{level}:90")
            keyboard.add_button("永久", f"quota_admin:member_config:set_history:{level}:-1")
            keyboard.add_row()
            keyboard.add_button("🔙 返回会员配置", "quota_admin:admin:member_config")
        
        return message, keyboard
    
    # ==================== 广告管理页面 ====================
    
    def build_ad_manage_menu(
        self,
        ads: List[Dict[str, Any]],
        stats: Dict[str, Any]
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建广告管理页面
        
        Args:
            ads: 广告列表
            stats: 广告统计
        """
        lines = ["📺 广告管理\n"]
        
        # 统计信息
        lines.append(f"📊 统计: {stats.get('total', 0)}条广告 | {stats.get('enabled', 0)}启用 | {stats.get('disabled', 0)}暂停")
        lines.append(f"👁️ 总展示: {stats.get('total_shows', 0)}次\n")
        
        lines.append("━━ 广告列表 ━━")
        
        if not ads:
            lines.append("暂无广告")
        else:
            for ad in ads[:10]:  # 最多显示10条
                ad_id = ad.get('id', 0)
                content = ad.get('content', '')[:30]
                is_enabled = ad.get('is_enabled', 0)
                weight = ad.get('weight', 1)
                show_count = ad.get('show_count', 0)
                
                status_icon = '✅' if is_enabled else '⏸️'
                lines.append(f"{status_icon} #{ad_id} | 权重{weight} | {show_count}次")
                lines.append(f"   {content}{'...' if len(ad.get('content', '')) > 30 else ''}")
        
        lines.append("\n💡 点击广告ID查看详情")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            
            # 广告列表按钮（每行2个）
            row_ads = []
            for ad in ads[:8]:  # 最多8个按钮
                ad_id = ad.get('id', 0)
                is_enabled = ad.get('is_enabled', 0)
                status_icon = '✅' if is_enabled else '⏸️'
                row_ads.append({
                    "text": f"{status_icon}#{ad_id}",
                    "callback": f"quota_admin:ad:detail:{ad_id}"
                })
            
            # 每行2个按钮
            for i in range(0, len(row_ads), 2):
                if i + 1 < len(row_ads):
                    keyboard.add_button(row_ads[i]["text"], row_ads[i]["callback"])
                    keyboard.add_button(row_ads[i+1]["text"], row_ads[i+1]["callback"])
                else:
                    keyboard.add_button(row_ads[i]["text"], row_ads[i]["callback"])
                keyboard.add_row()
            
            keyboard.add_button("➕ 添加广告", "quota_admin:ad:add")
            keyboard.add_row()
            keyboard.add_button("🔙 返回管理", "quota_admin:admin_back")
            keyboard.add_button("❌ 关闭", "quota_admin:close")
        
        return message, keyboard
    
    def build_ad_detail(
        self,
        ad: Dict[str, Any]
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建广告详情页面
        
        Args:
            ad: 广告信息
        """
        import json
        
        ad_id = ad.get('id', 0)
        content = ad.get('content', '')
        is_enabled = ad.get('is_enabled', 0)
        weight = ad.get('weight', 1)
        show_count = ad.get('show_count', 0)
        target_levels = ad.get('target_levels', '[0,1,2]')
        created_at = ad.get('created_at', '')
        
        # 解析目标等级
        try:
            levels = json.loads(target_levels) if isinstance(target_levels, str) else target_levels
            level_names = {0: '免费', 1: '高级', 2: 'VIP'}
            target_str = '+'.join([level_names.get(l, '?') for l in levels])
        except:
            target_str = '全部'
        
        status_text = '✅ 启用中' if is_enabled else '⏸️ 已暂停'
        
        lines = [f"📺 广告详情 #{ad_id}\n"]
        lines.append(f"状态: {status_text}")
        lines.append(f"权重: {weight}")
        lines.append(f"目标用户: {target_str}")
        lines.append(f"展示次数: {show_count}")
        lines.append(f"创建时间: {created_at[:10] if created_at else '未知'}")
        lines.append(f"\n━━ 广告内容 ━━")
        lines.append(content)
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            
            # 状态切换
            if is_enabled:
                keyboard.add_button("⏸️ 暂停", f"quota_admin:ad:toggle:{ad_id}")
            else:
                keyboard.add_button("✅ 启用", f"quota_admin:ad:toggle:{ad_id}")
            keyboard.add_button("✏️ 编辑", f"quota_admin:ad:edit:{ad_id}")
            keyboard.add_row()
            
            # 权重调整
            keyboard.add_button("权重1", f"quota_admin:ad:weight:{ad_id}:1")
            keyboard.add_button("权重5", f"quota_admin:ad:weight:{ad_id}:5")
            keyboard.add_button("权重10", f"quota_admin:ad:weight:{ad_id}:10")
            keyboard.add_row()
            
            keyboard.add_button("🗑️ 删除", f"quota_admin:ad:delete:{ad_id}")
            keyboard.add_button("🔙 返回列表", "quota_admin:admin:ad_manage")
        
        return message, keyboard
    
    def build_ad_add_prompt(self) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建添加广告提示页面"""
        lines = ["➕ 添加新广告\n"]
        lines.append("请输入广告内容：")
        lines.append("")
        lines.append("💡 支持 emoji 和换行")
        lines.append("💡 建议长度不超过100字")
        lines.append("")
        lines.append("示例：")
        lines.append("💎 升级会员，享受更多权益 | 发送 /会员")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("❌ 取消", "quota_admin:admin:ad_manage")
        
        return message, keyboard
    
    def build_ad_edit_prompt(
        self,
        ad: Dict[str, Any]
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """构建编辑广告提示页面"""
        ad_id = ad.get('id', 0)
        content = ad.get('content', '')
        
        lines = [f"✏️ 编辑广告 #{ad_id}\n"]
        lines.append("当前内容：")
        lines.append(f"{content}")
        lines.append("")
        lines.append("请输入新的广告内容：")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("❌ 取消", f"quota_admin:ad:detail:{ad_id}")
        
        return message, keyboard
    
    # ==================== 会员介绍页面 ====================
    
    def build_membership_intro(
        self,
        user_info: Dict[str, Any] = None
    ) -> Tuple[str, Optional[InlineKeyboard]]:
        """
        构建会员介绍页面
        
        Args:
            user_info: 用户信息（可选，用于显示当前等级）
        """
        lines = ["🌟 会员中心\n"]
        
        # 显示用户当前等级
        if user_info:
            current_level = user_info.get('member_level', 0)
            # 确保 current_level 是整数
            if hasattr(current_level, 'value'):
                current_level = current_level.value
            try:
                current_level = int(current_level)
            except (TypeError, ValueError):
                current_level = 0
            
            level_name = user_info.get('level_name', '免费用户')
            expire_date = user_info.get('expire_date')
            
            level_icons = ['👤', '💎', '👑']
            icon = level_icons[current_level] if current_level < 3 else '❓'
            
            lines.append(f"当前等级: {icon} {level_name}")
            if expire_date and current_level > 0:
                lines.append(f"到期时间: {expire_date[:10] if isinstance(expire_date, str) else str(expire_date)[:10]}")
            lines.append("")
        
        lines.append("━━ 会员等级对比 ━━\n")
        
        # 免费用户
        lines.append("👤 免费用户")
        lines.append("• 订阅数量: 3个")
        lines.append("• 订阅源: 公开源")
        lines.append("• 推送时间: 固定时间")
        lines.append("• 广告: 显示")
        lines.append("")
        
        # 高级会员
        lines.append("💎 高级会员")
        lines.append("• 订阅数量: 20个")
        lines.append("• 订阅源: 公开+会员源")
        lines.append("• 推送时间: 自定义")
        lines.append("• 广告: 无")
        lines.append("• 限流倍率: 2倍")
        lines.append("")
        
        # VIP会员
        lines.append("👑 VIP会员")
        lines.append("• 订阅数量: 无限")
        lines.append("• 订阅源: 全部+VIP专属")
        lines.append("• 推送时间: 自定义")
        lines.append("• 广告: 无")
        lines.append("• 优先推送: ✅")
        lines.append("• 限流倍率: 5倍")
        lines.append("• 历史记录: 永久")
        lines.append("")
        
        lines.append("━━ 开通方式 ━━\n")
        lines.append("🎁 积分兑换: 通过签到/任务赚取积分兑换")
        lines.append("💳 赞助开通: 联系管理员赞助开通")
        lines.append("")
        lines.append("💡 发送 /签到 每日领取积分")
        lines.append("💡 发送 /我 查看个人中心")
        
        message = "\n".join(lines)
        
        keyboard = None
        if self.supports_buttons and InlineKeyboard is not None:
            keyboard = InlineKeyboard()
            keyboard.add_button("⭐ 签到领积分", "quota_admin:checkin")
            keyboard.add_button("👤 个人中心", "quota_admin:home")
            keyboard.add_row()
            keyboard.add_button("❌ 关闭", "quota_admin:close")
        
        return message, keyboard
