"""
签到插件响应构建器
继承通用基类，实现插件特定功能
"""
from typing import Optional, Tuple, List, Dict, Any
import sys
from pathlib import Path

# 添加 common 到路径
plugin_root = Path(__file__).parent.parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

from common.response_builder import BaseResponseBuilder

try:
    from astrbot.core.message.components import InlineKeyboard
except ImportError:
    InlineKeyboard = None


class CheckinResponseBuilder(BaseResponseBuilder):
    """签到插件响应构建器 - 继承通用基类"""
    
    def build_checkin_menu(self, 
                          message: str,
                          session_timeout: int = 1) -> Tuple[str, Optional[Any]]:
        """
        构建签到菜单响应
        
        Args:
            message: 基础消息文本
            session_timeout: 会话超时时间（分钟）
            
        Returns:
            (消息文本, 键盘或None)
        """
        if self.is_button_mode():
            # 按钮模式 - 使用基类方法构建
            buttons = [
                [
                    {"text": "📝 补签", "callback_data": "checkin:makeup"},
                    {"text": "📊 签到记录", "callback_data": "checkin:history"},
                    {"text": "🏆 签到排行", "callback_data": "checkin:leaderboard"}
                ],
                [{"text": "❌ 退出", "callback_data": "checkin:exit"}]
            ]
            return self.build_response(message, buttons, add_navigation=False)
        else:
            # 会话模式 - 消息已包含文本导航
            return message, None
    
    
    def build_submenu_response(self,
                              content: str,
                              step: int = 1,
                              quick_inputs: List[Dict[str, str]] = None) -> Tuple[str, Optional[Any]]:
        """
        构建子菜单响应（补签输入等）
        
        Args:
            content: 子菜单内容
            step: 当前步骤（通常 >0）
            quick_inputs: 快捷输入按钮列表
            
        Returns:
            (消息文本, 键盘或None)
        """
        if self.is_button_mode():
            # 按钮模式 - 使用基类方法
            buttons = []
            
            # 添加快捷输入按钮
            if quick_inputs:
                for i in range(0, len(quick_inputs), 3):
                    buttons.append(quick_inputs[i:i+3])
            
            # 添加导航按钮
            nav_buttons = self.build_navigation_buttons(
                show_home=True,
                show_exit=True,
                home_callback="checkin:home",
                exit_callback="checkin:exit"
            )
            buttons.append(nav_buttons)
            
            return self.build_response(content, buttons, add_navigation=False)
        else:
            # 会话模式 - 内容已包含导航提示
            return content, None
    
    def build_detail_response(self,
                             content: str,
                             step: int = 0) -> Tuple[str, Optional[Any]]:
        """
        构建详情响应（查看记录、排行等）
        
        Args:
            content: 详情内容
            step: 当前步骤（0=主菜单，>0=子菜单）
            
        Returns:
            (消息文本, 键盘或None)
        """
        if self.is_button_mode():
            # 按钮模式 - 使用基类方法
            nav_buttons = self.build_navigation_buttons(
                show_home=True,
                show_exit=True,
                home_callback="checkin:home",
                exit_callback="checkin:exit"
            )
            return self.build_response(content, [nav_buttons], add_navigation=False)
        else:
            # 会话模式 - 内容已包含导航提示
            return content, None
