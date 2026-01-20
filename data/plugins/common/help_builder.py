"""
统一帮助系统
提供标准化的帮助信息构建
"""
from typing import List, Tuple, Any, Dict, Optional
from .message_formatter import get_separator


class HelpBuilder:
    """统一的帮助信息构建器"""
    
    def __init__(self, plugin_name: str, description: str = ""):
        """
        初始化帮助构建器
        
        Args:
            plugin_name: 插件名称
            description: 插件描述
        """
        self.plugin_name = plugin_name
        self.description = description
        self.commands: List[Dict] = []
        self.examples: List[Dict] = []
        self.features: List[str] = []
        self.tips: List[str] = []
    
    def add_command(
        self, 
        cmd: str, 
        desc: str, 
        usage: str = "",
        aliases: List[str] = None
    ) -> 'HelpBuilder':
        """
        添加命令说明
        
        Args:
            cmd: 命令
            desc: 描述
            usage: 用法示例
            aliases: 命令别名列表
            
        Returns:
            self（支持链式调用）
        """
        self.commands.append({
            'cmd': cmd,
            'desc': desc,
            'usage': usage,
            'aliases': aliases or []
        })
        return self
    
    def add_example(
        self, 
        desc: str, 
        input_text: str, 
        output: str = ""
    ) -> 'HelpBuilder':
        """
        添加使用示例
        
        Args:
            desc: 示例描述
            input_text: 输入示例
            output: 输出示例
            
        Returns:
            self（支持链式调用）
        """
        self.examples.append({
            'desc': desc,
            'input': input_text,
            'output': output
        })
        return self
    
    def add_feature(self, feature: str) -> 'HelpBuilder':
        """
        添加功能特性
        
        Args:
            feature: 功能描述
            
        Returns:
            self（支持链式调用）
        """
        self.features.append(feature)
        return self
    
    def add_tip(self, tip: str) -> 'HelpBuilder':
        """
        添加使用提示
        
        Args:
            tip: 提示内容
            
        Returns:
            self（支持链式调用）
        """
        self.tips.append(tip)
        return self
    
    def build(
        self, 
        capabilities: Optional[Dict] = None,
        show_commands: bool = True,
        show_examples: bool = True,
        show_features: bool = True,
        show_tips: bool = True
    ) -> Tuple[str, Any]:
        """
        构建帮助信息
        
        Args:
            capabilities: 平台能力字典
            show_commands: 是否显示命令列表
            show_examples: 是否显示使用示例
            show_features: 是否显示功能特性
            show_tips: 是否显示使用提示
            
        Returns:
            (帮助文本, 键盘对象)
        """
        result = []
        
        # 获取平台分隔线
        platform = capabilities.get('platform_name', '') if capabilities else ''
        separator = get_separator(platform)
        
        # 标题
        result.append(separator)
        result.append(f"📖 {self.plugin_name} 使用帮助")
        result.append(f"{separator}\n")
        
        # 描述
        if self.description:
            result.append(f"{self.description}\n")
        
        # 功能特性
        if show_features and self.features:
            result.append("✨ 功能特性：")
            for feature in self.features:
                result.append(f"  • {feature}")
            result.append("")
        
        # 命令列表
        if show_commands and self.commands:
            result.append("📝 可用命令：")
            for cmd_info in self.commands:
                cmd_line = f"  • {cmd_info['cmd']}"
                if cmd_info['aliases']:
                    aliases_str = "、".join(cmd_info['aliases'])
                    cmd_line += f" (别名: {aliases_str})"
                cmd_line += f" - {cmd_info['desc']}"
                result.append(cmd_line)
                
                if cmd_info['usage']:
                    result.append(f"    用法：{cmd_info['usage']}")
            result.append("")
        
        # 使用示例
        if show_examples and self.examples:
            result.append("💡 使用示例：")
            for i, ex in enumerate(self.examples, 1):
                result.append(f"  {i}. {ex['desc']}")
                result.append(f"     输入：{ex['input']}")
                if ex['output']:
                    result.append(f"     输出：{ex['output']}")
            result.append("")
        
        # 使用提示
        if show_tips and self.tips:
            result.append("💡 使用提示：")
            for tip in self.tips:
                result.append(f"  • {tip}")
            result.append("")
        
        # 导航提示
        result.append(separator)
        if capabilities and not capabilities.get('supports_buttons', False):
            result.append("💡 0-退出")
        
        return "\n".join(result), None
    
    def build_quick_help(self) -> str:
        """
        构建快速帮助（仅命令列表）
        
        Returns:
            快速帮助文本
        """
        if not self.commands:
            return f"📖 {self.plugin_name}\n\n暂无可用命令"
        
        result = [f"📖 {self.plugin_name} 命令："]
        for cmd_info in self.commands:
            result.append(f"  • {cmd_info['cmd']} - {cmd_info['desc']}")
        
        return "\n".join(result)
    
    @staticmethod
    def create_navigation_help(platform: str = None) -> str:
        """
        创建通用导航帮助
        
        Args:
            platform: 平台名称（用于适配分隔线长度）
        
        Returns:
            导航帮助文本
        """
        separator = get_separator(platform)
        return f"""{separator}
🧭 导航说明
{separator}

会话模式导航键：
  • h - 返回首页
  • b - 返回上级
  • 0 - 退出会话
  • p - 上一页
  • n - 下一页

按钮模式：
  • 直接点击按钮即可

{separator}
💡 输入对应字母或数字即可导航"""
