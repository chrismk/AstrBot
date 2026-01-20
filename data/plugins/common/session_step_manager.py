"""
会话步骤管理器 - 标准化 step 定义和验证

提供统一的会话步骤管理，避免硬编码 step 值，提供类型安全和集中管理。

使用示例:
    from common.session_step_manager import SessionStepManager
    from enum import IntEnum
    
    class MyStepManager(SessionStepManager):
        class Step(IntEnum):
            MAIN_MENU = 0
            VIEW_ONLY = 1
            INPUT_REQUIRED = 2
        
        def __init__(self):
            super().__init__({
                self.Step.MAIN_MENU: "主菜单",
                self.Step.VIEW_ONLY: "查看页面",
                self.Step.INPUT_REQUIRED: "输入页面"
            })
"""
from typing import Dict, Optional


class SessionStepManager:
    """会话步骤管理器基类 - 标准化 step 定义和验证"""
    
    def __init__(self, step_definitions: Dict[int, str]):
        """
        初始化步骤管理器
        
        Args:
            step_definitions: step 定义字典，如 {0: "主菜单", 1: "查看页", 2: "输入页"}
        """
        self.step_definitions = step_definitions
        self._validate_definitions()
    
    def _validate_definitions(self):
        """验证 step 定义的完整性"""
        if not self.step_definitions:
            raise ValueError("step_definitions 不能为空")
        
        if 0 not in self.step_definitions:
            raise ValueError("必须定义 step=0 (主菜单)")
        
        # 检查连续性
        max_step = max(self.step_definitions.keys())
        for i in range(max_step + 1):
            if i not in self.step_definitions:
                raise ValueError(f"step 定义不连续，缺少 step={i}")
    
    def get_step_name(self, step: int) -> str:
        """
        获取步骤名称
        
        Args:
            step: 步骤值
            
        Returns:
            步骤名称，如果未定义则返回 "未知步骤(N)"
        """
        return self.step_definitions.get(step, f"未知步骤({step})")
    
    def is_main_menu(self, step: int) -> bool:
        """
        判断是否为主菜单
        
        Args:
            step: 步骤值
            
        Returns:
            True 表示是主菜单（step=0）
        """
        return step == 0
    
    def is_readonly_step(self, step: int) -> bool:
        """
        判断是否为只读步骤（子类可重写）
        
        Args:
            step: 步骤值
            
        Returns:
            True 表示是只读步骤，不接受用户输入
        """
        return False
    
    def is_input_step(self, step: int) -> bool:
        """
        判断是否为输入步骤（子类可重写）
        
        Args:
            step: 步骤值
            
        Returns:
            True 表示是输入步骤，需要接受用户输入
        """
        return step > 1
    
    def validate_step_transition(self, from_step: int, to_step: int) -> bool:
        """
        验证步骤转换是否合法
        
        Args:
            from_step: 当前步骤
            to_step: 目标步骤
            
        Returns:
            True 表示转换合法
        """
        # 基础规则：可以返回主菜单，可以前进/后退一步
        if to_step == 0:  # 返回主菜单
            return True
        if abs(to_step - from_step) <= 1:  # 相邻步骤
            return True
        return False
    
    def get_all_steps(self) -> Dict[int, str]:
        """
        获取所有步骤定义
        
        Returns:
            步骤定义字典
        """
        return self.step_definitions.copy()
    
    def get_max_step(self) -> int:
        """
        获取最大步骤值
        
        Returns:
            最大步骤值
        """
        return max(self.step_definitions.keys())
