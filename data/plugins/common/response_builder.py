"""
通用响应构建器基类 - 跨平台交互设计
支持按钮模式和会话模式的自动适配
"""
from typing import List, Tuple, Optional, Dict, Any
from .message_formatter import get_separator

try:
    from astrbot.core.message.components import InlineKeyboard
except ImportError:
    InlineKeyboard = None


class BaseResponseBuilder:
    """
    通用响应构建器基类
    
    提供跨平台响应构建的基础功能，插件可以继承此类并扩展自定义方法
    """
    
    def __init__(self, platform_capabilities: dict):
        """
        初始化响应构建器
        
        Args:
            platform_capabilities: 平台能力字典
        """
        self.capabilities = platform_capabilities
        self.supports_buttons = platform_capabilities.get('supports_buttons', False)
        self.supports_inline_keyboard = platform_capabilities.get('supports_inline_keyboard', False)
        self.supports_edit_message = platform_capabilities.get('supports_edit_message', False)
        self.platform_name = platform_capabilities.get('platform_name', 'unknown')
        self.max_button_per_row = platform_capabilities.get('max_button_per_row', 3)
        self.max_message_length = platform_capabilities.get('max_message_length', 2000)
    
    def is_button_mode(self) -> bool:
        """判断是否是按钮模式"""
        return self.supports_buttons
    
    def is_session_mode(self) -> bool:
        """判断是否是会话模式"""
        return not self.supports_buttons
    
    def create_keyboard(self, buttons: List[List[Dict[str, str]]]) -> Optional[Any]:
        """
        创建键盘
        
        Args:
            buttons: 按钮列表，格式：[[{"text": "按钮1", "callback_data": "data1"}, ...], ...]
            
        Returns:
            InlineKeyboard 对象或 None
        """
        if not self.supports_buttons or InlineKeyboard is None:
            return None
        
        keyboard = InlineKeyboard()
        keyboard.buttons = buttons
        return keyboard
    
    def build_navigation_buttons(self, 
                                 show_home: bool = True,
                                 show_back: bool = False,
                                 show_exit: bool = True,
                                 home_callback: str = "home",
                                 back_callback: str = "back",
                                 exit_callback: str = "exit") -> List[Dict[str, str]]:
        """
        构建导航按钮行
        
        Args:
            show_home: 是否显示返回首页按钮
            show_back: 是否显示返回上一级按钮
            show_exit: 是否显示退出按钮
            home_callback: 返回首页的回调数据
            back_callback: 返回上一级的回调数据
            exit_callback: 退出的回调数据
            
        Returns:
            按钮列表
        """
        buttons = []
        
        if show_home:
            buttons.append({"text": "🏠 返回首页", "callback_data": home_callback})
        
        if show_back:
            buttons.append({"text": "◀️ 返回", "callback_data": back_callback})
        
        if show_exit:
            buttons.append({"text": "❌ 退出", "callback_data": exit_callback})
        
        return buttons
    
    def build_exit_button(self, 
                         plugin_prefix: str,
                         use_json: bool = False) -> Dict[str, str]:
        """
        构建标准退出按钮
        
        Args:
            plugin_prefix: 插件前缀（如 "douban", "book", "music"）
            use_json: 是否使用 JSON 格式（飞书平台）
            
        Returns:
            按钮配置字典
        """
        import json
        
        if use_json:
            callback_data = json.dumps({
                "action": f"{plugin_prefix}_exit",
                "delete_message": True
            }, ensure_ascii=False)
        else:
            callback_data = f"{plugin_prefix}:exit"
        
        return {"text": "❌ 退出", "callback_data": callback_data}
    
    def add_exit_button_row(self, 
                           buttons: List[List[Dict[str, str]]],
                           plugin_prefix: str,
                           use_json: bool = False) -> List[List[Dict[str, str]]]:
        """
        向按钮列表添加退出按钮行
        
        Args:
            buttons: 现有按钮列表
            plugin_prefix: 插件前缀
            use_json: 是否使用 JSON 格式
            
        Returns:
            添加了退出按钮的按钮列表
        """
        exit_button = self.build_exit_button(plugin_prefix, use_json)
        buttons.append([exit_button])
        return buttons
    
    def build_pagination_buttons(self,
                                 current_page: int,
                                 total_pages: int,
                                 callback_prefix: str) -> List[Dict[str, str]]:
        """
        构建分页按钮
        
        Args:
            current_page: 当前页码（从1开始）
            total_pages: 总页数
            callback_prefix: 回调前缀（如 "page:"）
            
        Returns:
            按钮列表
        """
        buttons = []
        
        # 上一页按钮
        if current_page > 1:
            buttons.append({
                "text": "◀️ 上一页",
                "callback_data": f"{callback_prefix}{current_page - 1}"
            })
        
        # 页码显示
        buttons.append({
            "text": f"📄 {current_page}/{total_pages}",
            "callback_data": f"{callback_prefix}current"
        })
        
        # 下一页按钮
        if current_page < total_pages:
            buttons.append({
                "text": "下一页 ▶️",
                "callback_data": f"{callback_prefix}{current_page + 1}"
            })
        
        return buttons
    
    def build_response(self,
                      message: str,
                      buttons: List[List[Dict[str, str]]] = None,
                      add_navigation: bool = True,
                      navigation_callback_prefix: str = "") -> Tuple[str, Optional[Any]]:
        """
        构建通用响应
        
        Args:
            message: 消息文本
            buttons: 自定义按钮列表（可选）
            add_navigation: 是否添加导航按钮
            navigation_callback_prefix: 导航回调前缀
            
        Returns:
            (消息文本, 键盘或None)
        """
        if self.supports_buttons and InlineKeyboard is not None:
            # 按钮模式
            keyboard = InlineKeyboard()
            
            # 添加自定义按钮
            if buttons:
                keyboard.buttons.extend(buttons)
            
            # 添加导航按钮
            if add_navigation:
                nav_buttons = self.build_navigation_buttons(
                    home_callback=f"{navigation_callback_prefix}home",
                    exit_callback=f"{navigation_callback_prefix}exit"
                )
                keyboard.buttons.append(nav_buttons)
            
            return message, keyboard
        else:
            # 会话模式 - 消息应该已经包含文本导航
            return message, None
    
    def format_session_navigation(self, 
                                  step: int = 0,
                                  options: List[str] = None,
                                  show_home: bool = True,
                                  show_exit: bool = True) -> str:
        """
        格式化会话模式的文本导航提示
        
        Args:
            step: 当前步骤（0=主菜单）
            options: 选项列表（用于主菜单）
            show_home: 是否显示返回首页提示
            show_exit: 是否显示退出提示
            
        Returns:
            导航提示文本
        """
        separator = get_separator(self.platform_name)
        nav_text = f"\n{separator}\n"
        
        if step == 0 and options:
            # 主菜单 - 显示数字选项
            nav_text += "💡 回复对应数字选择功能\n"
            for i, option in enumerate(options, 1):
                nav_text += f"   {i}️⃣ {option}\n"
        else:
            # 子菜单 - 显示导航提示
            nav_parts = []
            if show_home:
                nav_parts.append("0️⃣ 返回首页")
            if show_exit:
                nav_parts.append("输入 退出 结束")
            
            if nav_parts:
                nav_text += "💡 " + " | ".join(nav_parts)
        
        return nav_text
    
    def truncate_message(self, message: str, max_length: int = None) -> str:
        """
        截断消息文本
        
        Args:
            message: 原始消息
            max_length: 最大长度（默认使用平台限制）
            
        Returns:
            截断后的消息
        """
        if max_length is None:
            max_length = self.max_message_length
        
        if len(message) <= max_length:
            return message
        
        return message[:max_length - 3] + "..."


# 便捷函数
def create_response_builder(platform_capabilities: dict) -> BaseResponseBuilder:
    """
    创建响应构建器实例（便捷函数）
    
    Args:
        platform_capabilities: 平台能力字典
        
    Returns:
        BaseResponseBuilder 实例
        
    Example:
        ```python
        from common.response_builder import create_response_builder
        from common.platform_capabilities import get_platform_capabilities
        
        capabilities = get_platform_capabilities(event, "MyPlugin")
        builder = create_response_builder(capabilities)
        message, keyboard = builder.build_response("Hello!", buttons=[[...]])
        ```
    """
    return BaseResponseBuilder(platform_capabilities)
