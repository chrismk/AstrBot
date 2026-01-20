"""
搜索辅助模块

提供统一的搜索命令增强功能：
- 无关键词时显示最近搜索和热门搜索
- 搜索成功后自动记录历史
- 格式化搜索提示

使用示例：
    from common.search_helper import SearchHelper
    
    # 在插件初始化时创建
    self.search_helper = SearchHelper(
        plugin_name='music',
        search_stats=self.search_stats,
        page_size=self.PAGE_SIZE
    )
    
    # 在搜索命令中使用
    @filter.command("歌")
    async def handle_search(self, event, keyword: str = ""):
        # 无关键词时显示提示
        if not keyword:
            hint = self.search_helper.get_empty_search_hint(user_id, event)
            yield event.plain_result(hint)
            return
        
        # 执行搜索...
        results = await self.do_search(keyword)
        
        # 记录搜索历史
        self.search_helper.record_search(user_id, keyword, len(results))
"""

from typing import Optional, List, Dict, Any
from astrbot.api import logger


class SearchHelper:
    """搜索辅助类 - 统一的搜索历史集成"""
    
    # 插件显示名称映射
    PLUGIN_NAMES = {
        'music': '🎵 音乐',
        'book': '📚 书籍',
        'douban': '🎬 豆瓣',
        'pansou': '☁️ 资源'
    }
    
    # 插件命令映射
    PLUGIN_COMMANDS = {
        'music': '/歌',
        'book': '/书',
        'douban': '/豆',
        'pansou': '/搜'
    }
    
    def __init__(
        self,
        plugin_name: str,
        search_stats = None,
        page_size: int = 15,
        recent_limit: int = 3,
        hot_limit: int = 5
    ):
        """
        初始化搜索辅助类
        
        Args:
            plugin_name: 插件名称（music/book/douban/pansou）
            search_stats: SearchStatistics 实例
            page_size: 每页结果数
            recent_limit: 最近搜索显示数量
            hot_limit: 热门搜索显示数量
        """
        self.plugin_name = plugin_name
        self.search_stats = search_stats
        self.page_size = page_size
        self.recent_limit = recent_limit
        self.hot_limit = hot_limit
        
        self.display_name = self.PLUGIN_NAMES.get(plugin_name, plugin_name)
        self.command = self.PLUGIN_COMMANDS.get(plugin_name, f'/{plugin_name}')
    
    def get_empty_search_hint(
        self,
        user_id: str,
        show_usage: bool = True,
        show_recent: bool = True,
        show_hot: bool = True
    ) -> str:
        """
        获取空搜索提示（无关键词时显示）
        
        Args:
            user_id: 用户ID
            show_usage: 是否显示使用方法
            show_recent: 是否显示最近搜索
            show_hot: 是否显示热门搜索
            
        Returns:
            格式化的提示文本
        """
        lines = []
        
        # 使用方法
        if show_usage:
            lines.append(f"💡 使用方法: {self.command} 关键词")
            lines.append(f"示例: {self.command} {self._get_example_keyword()}")
        
        # 最近搜索
        if show_recent and self.search_stats:
            recent_hint = self.search_stats.format_recent_searches_hint(
                user_id, self.plugin_name, self.recent_limit
            )
            if recent_hint:
                if lines:
                    lines.append("")
                lines.append(recent_hint)
        
        # 热门搜索
        if show_hot and self.search_stats:
            hot_hint = self.search_stats.format_hot_searches_hint(
                self.plugin_name, self.hot_limit
            )
            if hot_hint:
                if lines and not lines[-1].startswith("🔥"):
                    lines.append("")
                lines.append(hot_hint)
        
        return "\n".join(lines) if lines else f"💡 使用方法: {self.command} 关键词"
    
    def _get_example_keyword(self) -> str:
        """获取示例关键词"""
        examples = {
            'music': '周杰伦 晴天',
            'book': '三体',
            'douban': '肖申克的救赎',
            'pansou': '阿凡达'
        }
        return examples.get(self.plugin_name, '关键词')
    
    def record_search(
        self,
        user_id: str,
        keyword: str,
        result_count: int = 0,
        search_type: str = "keyword",
        platform: str = None
    ) -> bool:
        """
        记录搜索历史
        
        Args:
            user_id: 用户ID
            keyword: 搜索关键词
            result_count: 结果数量
            search_type: 搜索类型
            platform: 平台
            
        Returns:
            是否成功
        """
        if not self.search_stats:
            return False
        
        return self.search_stats.record_search(
            user_id=user_id,
            plugin_name=self.plugin_name,
            keyword=keyword,
            result_count=result_count,
            search_type=search_type,
            platform=platform
        )
    
    def get_suggestions(self, user_id: str, prefix: str = "", limit: int = 5) -> List[str]:
        """
        获取搜索建议
        
        Args:
            user_id: 用户ID
            prefix: 搜索前缀
            limit: 返回数量
            
        Returns:
            建议关键词列表
        """
        if not self.search_stats:
            return []
        
        return self.search_stats.get_search_suggestions(
            user_id, self.plugin_name, prefix, limit
        )
    
    def format_no_result_hint(self, keyword: str, user_id: str = None) -> str:
        """
        格式化无结果提示
        
        Args:
            keyword: 搜索关键词
            user_id: 用户ID（用于显示搜索建议）
            
        Returns:
            格式化的提示文本
        """
        lines = [f"😔 没有找到关于「{keyword}」的结果"]
        
        # 显示搜索建议
        if user_id and self.search_stats:
            suggestions = self.get_suggestions(user_id, limit=3)
            if suggestions:
                # 过滤掉当前关键词
                suggestions = [s for s in suggestions if s != keyword][:3]
                if suggestions:
                    lines.append("")
                    lines.append(f"💡 试试搜索: {' | '.join(suggestions)}")
        
        return "\n".join(lines)


def create_search_helper(
    plugin_name: str,
    db_manager = None,
    search_stats = None,
    **kwargs
) -> SearchHelper:
    """
    创建搜索辅助类（便捷函数）
    
    Args:
        plugin_name: 插件名称
        db_manager: 数据库管理器（如果没有 search_stats）
        search_stats: SearchStatistics 实例（优先使用）
        **kwargs: 其他参数传递给 SearchHelper
        
    Returns:
        SearchHelper 实例
    """
    if search_stats is None and db_manager is not None:
        from .search_statistics import get_search_statistics
        search_stats = get_search_statistics(db_manager)
    
    return SearchHelper(
        plugin_name=plugin_name,
        search_stats=search_stats,
        **kwargs
    )
