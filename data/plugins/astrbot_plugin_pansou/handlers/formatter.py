"""
资源搜索结果格式化模块
负责格式化各种搜索结果
"""
import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime as dt
from astrbot.api import logger

plugin_root = Path(__file__).parent.parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))
from common.message_formatter import get_separator


class PansouFormatter:
    """资源搜索结果格式化器"""
    
    @staticmethod
    def format_search_results(
        results: list,
        keyword: str,
        page: int,
        page_size: int,
        total: int,
        show_pagination: bool = True,
        timeout_minutes: int = 1,
        show_hints: bool = True,
        filter_hint: str = None,
        from_plugin: str = None
    ) -> Tuple[str, list]:
        """
        格式化搜索结果
        
        Args:
            results: 搜索结果列表
            keyword: 搜索关键词
            page: 当前页码
            page_size: 每页显示数量
            total: 总结果数
            show_pagination: 是否显示分页导航
            timeout_minutes: 会话超时时间（分钟）
            show_hints: 是否显示导航提示文本（按钮模式下为False）
            filter_hint: 筛选提示文字（如 "f-筛选网盘"），None则不显示
            from_plugin: 来源插件名称（如 "douban"），用于显示会话切换提示
            
        Returns:
            (格式化的消息文本, 结果列表)
        """
        if not results:
            return f"😔 没有找到关于 '{keyword}' 的资源", []
        
        # 导入API类（避免循环依赖，在函数开始处导入）
        from .pansou_api import PansouAPI
        
        # 计算分页信息
        # start_index = (page - 1) * page_size + 1
        start_index = 1  # 相对序号（每页重置）
        total_pages = (total + page_size - 1) // page_size
        
        lines = []
        
        # 如果是从其他插件跳转过来，显示会话切换提示
        if from_plugin:
            plugin_name_map = {
                'douban': '豆瓣',
                'yunpan': '云盘'
            }
            plugin_display_name = plugin_name_map.get(from_plugin, from_plugin)
            lines.append(f"🔄 已从{plugin_display_name}切换到资源搜索会话")
            lines.append("")
        
        # 格式化每个结果
        for idx, item in enumerate(results, start=start_index):
            cloud_type = item.get('cloud_type', 'unknown')
            url = item.get('url', '')
            password = item.get('password', '')
            note = item.get('note', '')
            title = item.get('title', '')
            work_title = item.get('work_title', '')
            source = item.get('source', '')
            datetime = item.get('datetime', '')
            
            # 获取网盘名称和图标
            cloud_name = PansouAPI.get_cloud_type_name(cloud_type)
            cloud_emoji = PansouAPI.get_cloud_type_emoji(cloud_type)
            
            # 格式化时间
            formatted_time = ""
            if datetime:
                try:
                    # 处理纳秒精度的时间字符串（Python只支持微秒）
                    # 例如: 2025-11-24T15:24:26.243141716+08:00 -> 2025-11-24T15:24:26.243141+08:00
                    # 匹配并截断纳秒到微秒（保留6位小数）
                    datetime_str = re.sub(r'(\.\d{6})\d+', r'\1', datetime)
                    # 替换Z为+00:00
                    datetime_str = datetime_str.replace('Z', '+00:00')
                    
                    # 解析ISO格式时间
                    dt_obj = dt.fromisoformat(datetime_str)
                    # 检查是否是有效时间（排除 0001-01-01 等无效时间）
                    if dt_obj.year > 1900:
                        # 格式化为更友好的格式
                        formatted_time = dt_obj.strftime("%Y-%m-%d %H:%M")
                    else:
                        # 无效时间，记录日志
                        logger.debug(f"[Pansou] 无效时间数据: {datetime} (year={dt_obj.year})")
                except Exception as e:
                    # 解析失败，记录原始数据
                    logger.warning(f"[Pansou] 时间解析失败: {datetime} - 错误: {e}")
            
            # 标题行（网盘名 + 时间）
            title_line = f"{idx}. {cloud_emoji} {cloud_name}"
            if formatted_time:
                title_line += f" ({formatted_time})"
            lines.append(title_line)
            
            # 资源标题
            display_title = note or work_title or title or "未知资源"
            lines.append(f"   {display_title}")
            
            # 链接信息（完整显示）
            if url:
                lines.append(f"   🔗 {url}")
            
            # 提取码
            # 如果链接中已经包含了密码参数（如 pwd=xxxx 或 password=xxxx），则不重复显示提取码
            should_show_password = True
            if password and url:
                if f"pwd={password}" in url or f"password={password}" in url:
                    should_show_password = False
            
            if password and should_show_password:
                lines.append(f"   🔑 {password}")
            
            lines.append("")
        
        # 添加分页信息（在列表末尾）
        separator = get_separator()
        lines.append(separator)
        lines.append(f"🔍 '{keyword}' 搜索结果 (第{page}/{total_pages}页，共{total}条)")
        
        # 添加导航提示（仅会话模式，按钮模式不显示）
        if show_hints:
            lines.append("💡 请输入序号查看详情")
            
            nav_parts = []
            if page > 1:
                nav_parts.append("p-上页")
            if page < total_pages:
                nav_parts.append("n-下页")
            if page >= 3:
                nav_parts.append("h-首页")
            nav_parts.append("0-退出")
            
            lines.append(f"💡 {' | '.join(nav_parts)}")
            if filter_hint:
                lines.append(f"💡 {filter_hint}")
            lines.append(f"⏱️ 请在 {timeout_minutes} 分钟内输入")
        
        return "\n".join(lines), results
