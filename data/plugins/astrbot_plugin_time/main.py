"""
时间查询插件
用户输入 /time 指令返回当前时间
"""

import asyncio
from datetime import datetime
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# 导入统一用户ID工具
try:
    import sys
    from pathlib import Path
    plugin_root = Path(__file__).parent.parent
    if str(plugin_root) not in sys.path:
        sys.path.insert(0, str(plugin_root))
    from common.user_utils import get_unified_user_id
except ImportError:
    def get_unified_user_id(event):
        return event.get_sender_id()


@register("astrbot_plugin_time", "AstrBot", "时间查询插件，输入 /time 指令返回当前时间", "1.0.0", "")
class TimePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        logger.info("[astrbot_plugin_time] 时间插件已加载")

    @filter.command("time")
    async def time_command(self, event: AstrMessageEvent):
        """处理 /time 指令"""
        try:
            # 获取当前时间
            now = datetime.now()
            
            # 格式化时间字符串
            time_str = now.strftime("%Y年%m月%d日 %H:%M:%S")
            weekday = now.strftime("%A")
            weekday_cn = {
                "Monday": "星期一",
                "Tuesday": "星期二", 
                "Wednesday": "星期三",
                "Thursday": "星期四",
                "Friday": "星期五",
                "Saturday": "星期六",
                "Sunday": "星期日"
            }.get(weekday, weekday)
            
            # 构建回复消息
            message = f"🕐 当前时间：{time_str}\n📅 今天是：{weekday_cn}"
            
            # 发送消息
            yield event.plain_result(message)
            
            logger.info(f"[astrbot_plugin_time] 用户 {get_unified_user_id(event)} 查询时间")
            
        except Exception as e:
            logger.error(f"[astrbot_plugin_time] 处理时间指令时出错: {e}")
            yield event.plain_result("❌ 获取时间失败，请稍后重试")
