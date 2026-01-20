"""
统一分页系统
提供标准化的分页管理和导航
"""
from typing import List, Any, Optional, Tuple


class Pagination:
    """统一的分页管理器"""
    
    def __init__(
        self, 
        items: List[Any], 
        page: int = 1, 
        per_page: int = 10
    ):
        """
        初始化分页器
        
        Args:
            items: 所有项目列表
            page: 当前页码（从1开始）
            per_page: 每页项目数
        """
        self.items = items
        self.page = max(1, page)  # 确保页码至少为1
        self.per_page = max(1, per_page)  # 确保每页至少1项
        self.total = len(items)
        self.total_pages = max(1, (self.total + per_page - 1) // per_page)
        
        # 确保当前页不超过总页数
        if self.page > self.total_pages:
            self.page = self.total_pages
    
    def get_page_items(self) -> List[Any]:
        """
        获取当前页的项目
        
        Returns:
            当前页的项目列表
        """
        start = (self.page - 1) * self.per_page
        end = start + self.per_page
        return self.items[start:end]
    
    def has_prev(self) -> bool:
        """是否有上一页"""
        return self.page > 1
    
    def has_next(self) -> bool:
        """是否有下一页"""
        return self.page < self.total_pages
    
    def prev_page(self) -> int:
        """获取上一页页码"""
        return max(1, self.page - 1)
    
    def next_page(self) -> int:
        """获取下一页页码"""
        return min(self.total_pages, self.page + 1)
    
    def get_page_info(self) -> str:
        """
        获取分页信息文本
        
        Returns:
            分页信息（如：第 1/5 页，共 48 项）
        """
        return f"📄 第 {self.page}/{self.total_pages} 页，共 {self.total} 项"
    
    def get_navigation_hint(
        self, 
        show_home: bool = True,
        show_exit: bool = True
    ) -> str:
        """
        获取分页导航提示
        
        Args:
            show_home: 是否显示首页选项
            show_exit: 是否显示退出选项
            
        Returns:
            导航提示文本
        """
        hints = []
        
        # 分页导航
        if self.has_prev():
            hints.append("p-上页")
        if self.has_next():
            hints.append("n-下页")
        
        # 通用导航
        if show_home:
            hints.append("h-首页")
        if show_exit:
            hints.append("0-退出")
        
        return f"💡 {' | '.join(hints)}"
    
    def get_full_navigation(
        self,
        show_home: bool = True,
        show_exit: bool = True
    ) -> str:
        """
        获取完整的导航信息（分页信息 + 导航提示）
        
        Args:
            show_home: 是否显示首页选项
            show_exit: 是否显示退出选项
            
        Returns:
            完整导航文本
        """
        return f"{self.get_page_info()}\n{self.get_navigation_hint(show_home, show_exit)}"
    
    def format_items(
        self, 
        formatter: callable,
        start_index: Optional[int] = None
    ) -> str:
        """
        格式化当前页的项目
        
        Args:
            formatter: 格式化函数，接收 (index, item) 返回字符串
            start_index: 起始索引（如果为None则从1开始）
            
        Returns:
            格式化后的项目列表文本
        """
        items = self.get_page_items()
        if start_index is None:
            start_index = (self.page - 1) * self.per_page + 1
        
        result = []
        for i, item in enumerate(items):
            index = start_index + i
            result.append(formatter(index, item))
        
        return "\n".join(result)
    
    @staticmethod
    def create_from_query(
        all_items: List[Any],
        page_param: str,
        per_page: int = 10
    ) -> Tuple[bool, str, Optional['Pagination']]:
        """
        从页码参数创建分页器（带验证）
        
        Args:
            all_items: 所有项目
            page_param: 页码参数（字符串）
            per_page: 每页项目数
            
        Returns:
            (是否成功, 错误消息, 分页器对象)
        """
        try:
            page = int(page_param)
            if page < 1:
                return False, "❌ 页码必须大于0", None
            
            pagination = Pagination(all_items, page, per_page)
            
            if page > pagination.total_pages:
                return False, f"❌ 页码超出范围（共 {pagination.total_pages} 页）", None
            
            return True, "", pagination
            
        except ValueError:
            return False, "❌ 页码格式错误", None
    
    def to_dict(self) -> dict:
        """
        转换为字典（用于序列化）
        
        Returns:
            包含分页信息的字典
        """
        return {
            'page': self.page,
            'per_page': self.per_page,
            'total': self.total,
            'total_pages': self.total_pages,
            'has_prev': self.has_prev(),
            'has_next': self.has_next(),
            'prev_page': self.prev_page() if self.has_prev() else None,
            'next_page': self.next_page() if self.has_next() else None,
        }
