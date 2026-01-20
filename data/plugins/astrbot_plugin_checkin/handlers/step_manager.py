"""
签到插件步骤管理器

定义签到插件的会话步骤常量和验证逻辑。

步骤定义:
- Step.MAIN_MENU (0): 主菜单，显示签到功能选项
- Step.VIEW_ONLY (1): 查看页面（记录/排行榜），只读不接受输入
- Step.INPUT_REQUIRED (2): 补签输入页面，需要用户输入日期
"""
from enum import IntEnum
import sys
from pathlib import Path

# 添加 common 到路径
plugin_root = Path(__file__).parent.parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))

from common.session_step_manager import SessionStepManager


class CheckinStepManager(SessionStepManager):
    """签到插件步骤管理器"""
    
    class Step(IntEnum):
        """步骤常量定义"""
        MAIN_MENU = 0       # 主菜单
        VIEW_ONLY = 1       # 查看页面（记录/排行榜，只读）
        INPUT_REQUIRED = 2  # 补签输入页面
    
    def __init__(self):
        """初始化签到插件步骤管理器"""
        super().__init__({
            self.Step.MAIN_MENU: "主菜单",
            self.Step.VIEW_ONLY: "查看页面（只读）",
            self.Step.INPUT_REQUIRED: "补签输入页面"
        })
    
    def is_readonly_step(self, step: int) -> bool:
        """
        判断是否为只读步骤
        
        Args:
            step: 步骤值
            
        Returns:
            True 表示是只读步骤（记录/排行榜页面）
        """
        return step == self.Step.VIEW_ONLY
    
    def is_input_step(self, step: int) -> bool:
        """
        判断是否为输入步骤
        
        Args:
            step: 步骤值
            
        Returns:
            True 表示是输入步骤（补签页面）
        """
        return step == self.Step.INPUT_REQUIRED
