"""
统一导航提示模块
提供标准化的会话导航提示
"""
from typing import Optional


class NavigationHint:
    """统一的导航提示生成器"""
    
    # 导航层级定义
    LEVEL_MAIN = 0      # 主菜单
    LEVEL_SUB = 1       # 一级子菜单
    LEVEL_DETAIL = 2    # 二级子菜单/详情页
    
    @staticmethod
    def get_hint(
        level: int = 0,
        show_home: bool = None,
        show_back: bool = None,
        show_exit: bool = True,
        show_prev: bool = False,
        show_next: bool = False,
        custom_hints: list = None
    ) -> str:
        """
        获取导航提示
        
        Args:
            level: 导航层级
                0 = 主菜单（只显示退出）
                1 = 一级子菜单（显示返回+退出）
                2+ = 二级子菜单（显示首页+返回+退出）
            show_home: 是否显示首页（None=自动判断）
            show_back: 是否显示返回（None=自动判断）
            show_exit: 是否显示退出
            show_prev: 是否显示上一页
            show_next: 是否显示下一页
            custom_hints: 自定义提示列表（优先级最高）
            
        Returns:
            导航提示文本
        """
        if custom_hints:
            # 自定义提示
            return f"💡 {' | '.join(custom_hints)}"
        
        hints = []
        
        # 分页导航（优先显示）
        if show_prev:
            hints.append("p-上页")
        if show_next:
            hints.append("n-下页")
        
        # 自动判断是否显示首页和返回
        if show_home is None:
            show_home = level >= 2  # 二级及以上显示首页
        if show_back is None:
            show_back = level >= 1  # 一级及以上显示返回
        
        # 通用导航
        if show_home:
            hints.append("h-首页")
        if show_back:
            hints.append("b-返回")
        if show_exit:
            hints.append("0-退出")
        
        if not hints:
            return ""
        
        return f"💡 {' | '.join(hints)}"
    
    @staticmethod
    def get_main_menu_hint() -> str:
        """获取主菜单导航提示（0级）"""
        return NavigationHint.get_hint(level=NavigationHint.LEVEL_MAIN)
    
    @staticmethod
    def get_sub_menu_hint() -> str:
        """获取一级子菜单导航提示（1级）"""
        return NavigationHint.get_hint(level=NavigationHint.LEVEL_SUB)
    
    @staticmethod
    def get_detail_hint() -> str:
        """获取二级子菜单/详情页导航提示（2级）"""
        return NavigationHint.get_hint(level=NavigationHint.LEVEL_DETAIL)
    
    @staticmethod
    def get_pagination_hint(
        has_prev: bool = False,
        has_next: bool = False,
        current_page: int = 1,
        total_pages: int = 1,
        show_home: bool = False,
        show_back: bool = False,
        show_exit: bool = True,
        show_switch: bool = False
    ) -> str:
        """
        获取智能分页导航提示
        
        根据分页状态智能显示导航选项：
        - 只有一页：不显示翻页，只显示 h-首页 | 0-退出
        - 第一页：显示 n-下页 | h-首页 | 0-退出
        - 中间页：显示 p-上页 | n-下页 | h-首页 | 0-退出
        - 最后一页：显示 p-上页 | h-首页 | 0-退出
        
        Args:
            has_prev: 是否有上一页
            has_next: 是否有下一页
            current_page: 当前页码（用于判断）
            total_pages: 总页数（用于判断）
            show_home: 是否显示首页
            show_back: 是否显示返回
            show_exit: 是否显示退出
            
        Returns:
            分页导航提示
        """
        hints = []
        
        # 智能判断是否显示翻页
        # 如果只有一页，不显示翻页选项
        if total_pages > 1:
            if has_prev:
                hints.append("p-上页")
            if has_next:
                hints.append("n-下页")
        
        # 通用导航
        if show_home:
            hints.append("h-首页")
        if show_back:
            hints.append("b-返回")
        if show_exit:
            hints.append("0-退出")
        
        if not hints:
            return ""
        
        return f"💡 {' | '.join(hints)}"
    
    @staticmethod
    def get_detail_pagination_hint(
        has_prev: bool = False,
        has_next: bool = False,
        current_page: int = 1,
        total_pages: int = 1
    ) -> str:
        """
        获取详情页分页导航提示（带返回上级）
        
        适用场景：在详情页中浏览多页数据
        
        Args:
            has_prev: 是否有上一页
            has_next: 是否有下一页
            current_page: 当前页码
            total_pages: 总页数
            
        Returns:
            详情页分页导航提示
        """
        return NavigationHint.get_pagination_hint(
            has_prev=has_prev,
            has_next=has_next,
            current_page=current_page,
            total_pages=total_pages,
            show_home=True,
            show_back=True,  # 详情页显示返回
            show_exit=True
        )
    
    @staticmethod
    def format_with_timeout(hint: str, timeout_minutes: int = 1) -> str:
        """
        添加超时提示
        
        Args:
            hint: 导航提示
            timeout_minutes: 超时分钟数
            
        Returns:
            带超时的完整提示
        """
        if not hint:
            return f"⏱️ 请在 {timeout_minutes} 分钟内输入"
        return f"{hint}\n⏱️ 请在 {timeout_minutes} 分钟内输入"
    
    @staticmethod
    def format_with_instruction(hint: str, instruction: str = "请输入数字选择功能") -> str:
        """
        添加操作说明
        
        Args:
            hint: 导航提示
            instruction: 操作说明
            
        Returns:
            带说明的完整提示
        """
        if not hint:
            return f"💡 {instruction}"
        return f"{instruction}\n{hint}"
    
    @staticmethod
    def build_full_hint(
        level: int = 0,
        instruction: Optional[str] = None,
        timeout_minutes: Optional[int] = None,
        show_home: bool = None,
        show_back: bool = None,
        show_exit: bool = True,
        show_prev: bool = False,
        show_next: bool = False
    ) -> str:
        """
        构建完整的导航提示（包含说明和超时）
        
        Args:
            level: 导航层级
            instruction: 操作说明
            timeout_minutes: 超时分钟数
            其他参数同 get_hint
            
        Returns:
            完整的导航提示文本
        """
        hint = NavigationHint.get_hint(
            level=level,
            show_home=show_home,
            show_back=show_back,
            show_exit=show_exit,
            show_prev=show_prev,
            show_next=show_next
        )
        
        result = []
        if instruction:
            result.append(f"💡 {instruction}")
        if hint:
            result.append(hint)
        if timeout_minutes:
            result.append(f"⏱️ 请在 {timeout_minutes} 分钟内输入")
        
        return "\n".join(result)


    @staticmethod
    def from_pagination(
        pagination,
        show_home: bool = True,
        show_back: bool = False,
        show_exit: bool = True
    ) -> str:
        """
        从 Pagination 对象生成导航提示
        
        Args:
            pagination: Pagination 对象
            show_home: 是否显示首页
            show_back: 是否显示返回
            show_exit: 是否显示退出
            
        Returns:
            分页导航提示
        """
        return NavigationHint.get_pagination_hint(
            has_prev=pagination.has_prev(),
            has_next=pagination.has_next(),
            current_page=pagination.page,
            total_pages=pagination.total_pages,
            show_home=show_home,
            show_back=show_back,
            show_exit=show_exit
        )


# 便捷常量
HINT_MAIN_MENU = NavigationHint.get_main_menu_hint()      # "💡 0-退出"
HINT_SUB_MENU = NavigationHint.get_sub_menu_hint()        # "💡 b-返回 | 0-退出"
HINT_DETAIL = NavigationHint.get_detail_hint()            # "💡 h-首页 | b-返回 | 0-退出"
