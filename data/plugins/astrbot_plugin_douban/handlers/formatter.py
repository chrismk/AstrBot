"""
豆瓣数据格式化模块
负责格式化各种豆瓣数据
"""
from typing import List, Dict, Tuple
from astrbot.api import logger
import sys
from pathlib import Path
plugin_root = Path(__file__).parent.parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))
from common.message_formatter import get_separator


class DoubanFormatter:
    """豆瓣数据格式化器"""
    
    @staticmethod
    def format_search_results(
        results: list, 
        search_type: str, 
        page: int, 
        page_size: int, 
        total: int,
        show_pagination: bool = True,
        timeout_minutes: int = 1,
        show_hints: bool = True,
        switch_hint: str = None
    ) -> Tuple[str, list]:
        """
        格式化搜索结果
        
        Args:
            results: 搜索结果列表
            search_type: 搜索类型 (book/movie)
            page: 当前页码
            page_size: 每页显示数量
            total: 总结果数
            show_pagination: 是否显示分页导航
            timeout_minutes: 会话超时时间（分钟）
            show_hints: 是否显示导航提示文本（按钮模式下为False）
            switch_hint: 切换按钮的提示文字（如 "s-搜电影"），None则不显示
            
        Returns:
            (格式化的消息文本, 结果列表)
        """
        if not results:
            return "😔 没有找到相关结果", []
        
        # 计算分页信息
        # start_index = (page - 1) * page_size + 1  # 绝对序号
        start_index = 1  # 相对序号（每页重置，匹配按钮 1-15）
        end_index = min((page - 1) * page_size + len(results), total)
        total_pages = (total + page_size - 1) // page_size
        
        # 类型标题（保存，稍后添加到末尾）
        type_name = "📚 图书" if search_type == "book" else "🎬 电影"
        page_info = f"{type_name}搜索结果 (第{page}/{total_pages}页，共{total}条)"
        
        lines = []
        
        # 格式化每个结果
        for idx, item in enumerate(results, start=start_index):
            title = item.get('title', '未知标题')
            rating = item.get('rating', 0)
            rating_count = item.get('rating_count', 0)
            year = item.get('year', '')
            douban_id = item.get('id', '')
            
            # 类型特定信息 - 单行显示
            if search_type == 'movie':
                # 电影格式: 序号.标题 (年份) /导演 /演员
                info_parts = [title]
                
                # 添加年份
                #if year:
                    #info_parts[0] = f"{title} ({year})"
                
                # 添加导演
                directors = item.get('directors', [])
                if directors:
                    info_parts.append(' / '.join(directors[:2]))
                
                # 添加演员
                actors = item.get('actors', [])
                if actors:
                    info_parts.append(' / '.join(actors[:3]))
                
                lines.append(f"{idx}.{' /'.join(info_parts)}")
            
            elif search_type == 'book':
                # 书籍格式: 序号.标题 - 作者 - 出版社 - 价格
                info_parts = [title]
                
                # 添加作者
                authors = item.get('author', [])
                if authors:
                    info_parts.append('（' + '）（'.join(authors[:2]) + '）')
                
                # 添加出版社
                publisher = item.get('publisher', '')
                if publisher:
                    info_parts.append(publisher)
                
                # 添加价格（如果有）
                price = item.get('price', '')
                if price:
                    info_parts.append(price)
                
                lines.append(f"{idx}.{' - '.join(info_parts)}")
            
            # 评分显示（第二行，使用└符号）
            if rating > 0:
                # 根据评分计算星星数量
                star_count = int(rating / 2)
                stars = '⭐' * star_count
                rating_text = f"└ {rating:.1f}分{stars} ({rating_count}人评价)"
                lines.append(rating_text)
            
            lines.append("")
        
        # 添加分页信息（在列表末尾）
        separator = get_separator()
        lines.append(separator)
        lines.append(page_info)
        
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
            if switch_hint:
                nav_parts.append(switch_hint)
            nav_parts.append("0-退出")
            
            lines.append(f"💡 {' | '.join(nav_parts)}")
            lines.append(f"⏱️ 请在 {timeout_minutes} 分钟内输入")
        
        return "\n".join(lines), results
    
    @staticmethod
    def format_comments(comment_data: dict) -> str:
        """
        格式化评论数据
        
        Args:
            comment_data: 评论数据字典
            
        Returns:
            格式化的评论文本
        """
        try:
            if not comment_data:
                return "暂无评论"
            
            interests = comment_data.get('interests', [])
            if not interests:
                return "暂无评论"
            
            lines = ["📝 热门短评：", ""]
            
            for idx, interest in enumerate(interests[:5], 1):
                try:
                    # 用户信息
                    user = interest.get('user', {})
                    user_name = user.get('name', '匿名用户')
                    
                    # 评分
                    rating = interest.get('rating', {})
                    rating_value = rating.get('value', 0) if rating else 0
                    
                    if rating_value > 0:
                        stars = '⭐' * rating_value
                        rating_text = stars
                    else:
                        rating_text = "未评分"
                    
                    # 评论内容
                    comment = interest.get('comment', '').strip()
                    if not comment:
                        continue
                    
                    # 点赞数
                    vote_count = interest.get('vote_count', 0)
                    
                    # 格式化输出 - 紧凑格式
                    vote_text = f" 👍 {vote_count}" if vote_count > 0 else ""
                    lines.append(f"👤 {user_name} {rating_text}{vote_text}")
                    
                    # 处理长评论
                    if len(comment) > 100:
                        comment = comment[:100] + "..."
                    
                    lines.append(f"{comment}")
                    lines.append("")
                    
                except Exception as e:
                    logger.warning(f"格式化单条评论失败: {e}")
                    continue
            
            if len(lines) <= 2:
                return "暂无有效评论"
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"格式化评论失败: {e}")
            return "评论格式化失败"
    
    @staticmethod
    def format_douban_info_for_ai(douban_info: dict, douban_type: str, douban_id: str) -> str:
        """
        格式化豆瓣信息用于AI解读
        
        Args:
            douban_info: 豆瓣详细信息
            douban_type: 类型 (movie/book)
            douban_id: 豆瓣ID
            
        Returns:
            格式化的文本
        """
        info_lines = []
        
        # 基本信息
        title = douban_info.get('title', '')
        if title:
            info_lines.append(f"标题: {title}")
        
        # 评分信息
        rating = douban_info.get('rating', {})
        if rating:
            if isinstance(rating, dict):
                rating_value = rating.get('value', 0)
                rating_count = rating.get('count', 0)
                if rating_value > 0:
                    info_lines.append(f"评分: {rating_value}/10 ({rating_count}人评价)")
            elif isinstance(rating, (int, float, str)):
                try:
                    rating_value = float(rating)
                    if rating_value > 0:
                        info_lines.append(f"评分: {rating_value}/10")
                except (ValueError, TypeError):
                    pass
        
        # 类型特定信息
        if douban_type == 'movie':
            # 导演
            directors = douban_info.get('directors', [])
            if directors:
                # 兼容字符串列表和字典列表两种格式
                if isinstance(directors[0], dict):
                    directors_names = [d.get('name', '') for d in directors]
                else:
                    directors_names = [str(d) for d in directors]
                info_lines.append(f"导演: {', '.join(directors_names)}")
            
            # 演员
            actors = douban_info.get('actors', [])
            if actors:
                # 兼容字符串列表和字典列表两种格式
                if isinstance(actors[0], dict):
                    actors_names = [a.get('name', '') for a in actors[:5]]
                else:
                    actors_names = [str(a) for a in actors[:5]]
                info_lines.append(f"主演: {', '.join(actors_names)}")
            
            # 类型
            genres = douban_info.get('genres', [])
            if genres:
                info_lines.append(f"类型: {', '.join(genres)}")
            
            # 年份
            year = douban_info.get('year', '')
            if year:
                info_lines.append(f"年份: {year}")
            
            # 片长
            duration = douban_info.get('duration', '')
            if duration:
                info_lines.append(f"片长: {duration}")
        
        elif douban_type == 'book':
            # 作者
            authors = douban_info.get('author', []) or douban_info.get('authors', [])
            if authors:
                if isinstance(authors, str):
                    authors = [authors]
                info_lines.append(f"作者: {', '.join(authors)}")
            
            # 出版社
            publisher = douban_info.get('publisher', '')
            if publisher:
                info_lines.append(f"出版社: {publisher}")
            
            # 出版年份
            pubdate = douban_info.get('pubdate', '')
            if pubdate:
                info_lines.append(f"出版时间: {pubdate}")
            
            # ISBN
            isbn = douban_info.get('isbn13', '') or douban_info.get('isbn10', '') or douban_info.get('isbn', '')
            if isbn:
                info_lines.append(f"ISBN: {isbn}")
        
        # 简介
        intro = douban_info.get('intro', '') or douban_info.get('summary', '')
        if intro:
            # 限制简介长度
            if len(intro) > 500:
                intro = intro[:500] + "..."
            info_lines.append(f"\n简介:\n{intro}")
        
        return "\n".join(info_lines) if info_lines else "信息不完整"
