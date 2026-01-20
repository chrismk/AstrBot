"""
豆瓣URL解析模块
负责解析和验证豆瓣链接
"""
import re
from typing import Optional, Tuple
from astrbot.api import logger


class DoubanURLParser:
    """豆瓣URL解析器"""
    
    # 豆瓣链接匹配模式
    PATTERNS = [
        # 桌面版电影链接
        (r'https?://movie\.douban\.com/subject/(\d+)', 'movie'),
        # 桌面版图书链接
        (r'https?://book\.douban\.com/subject/(\d+)', 'book'),
        # 移动版电影链接
        (r'https?://m\.douban\.com/movie/subject/(\d+)', 'movie'),
        # 移动版图书链接
        (r'https?://m\.douban\.com/book/subject/(\d+)', 'book'),
        # 豆瓣App分发链接 - 电影
        (r'https?://www\.douban\.com/doubanapp/dispatch/movie/(\d+)', 'movie'),
        # 豆瓣App分发链接 - 图书
        (r'https?://www\.douban\.com/doubanapp/dispatch/book/(\d+)', 'book'),
    ]
    
    # 豆瓣链接指示符
    DOUBAN_INDICATORS = [
        # 桌面版
        'movie.douban.com',
        'book.douban.com',
        # 移动版
        'm.douban.com/movie',
        'm.douban.com/book',
        # App分发
        'doubanapp/dispatch/movie',
        'doubanapp/dispatch/book',
    ]
    
    @classmethod
    def extract_douban_info(cls, url: str) -> Optional[Tuple[str, str]]:
        """
        从豆瓣链接中提取类型和ID
        
        支持的链接格式：
        - https://movie.douban.com/subject/36208369/
        - https://movie.douban.com/subject/36208369/?icn=index-latestbook-subject
        - https://book.douban.com/subject/37375410/
        - https://book.douban.com/subject/37375410/?icn=index-latestbook-subject
        - https://m.douban.com/book/subject/37353424/?source=collection
        - https://m.douban.com/movie/subject/36455616/
        - https://www.douban.com/doubanapp/dispatch/movie/36402017
        - https://www.douban.com/doubanapp/dispatch/book/37353424
        
        Args:
            url: 豆瓣链接
            
        Returns:
            (type, id) 或 None
        """
        try:
            for pattern, douban_type in cls.PATTERNS:
                match = re.search(pattern, url)
                if match:
                    douban_id = match.group(1)
                    logger.info(f"解析豆瓣链接成功: type={douban_type}, id={douban_id}")
                    return douban_type, douban_id
            
            logger.warning(f"无法解析豆瓣链接: {url}")
            return None
            
        except Exception as e:
            logger.error(f"解析豆瓣链接失败: {e}")
            return None
    
    @classmethod
    def is_douban_url(cls, text: str) -> bool:
        """
        检查文本是否包含豆瓣链接
        
        Args:
            text: 待检查的文本
            
        Returns:
            是否包含豆瓣链接
        """
        return any(indicator in text for indicator in cls.DOUBAN_INDICATORS)
