"""
消息格式化工具
提供统一的消息格式化功能
"""
from typing import List, Optional, Dict


# 平台分隔线配置（根据字体宽度调整）
PLATFORM_SEPARATOR_CONFIG = {
    'telegram': {
        'char': '━',
        'length': 18,      # Telegram 等宽字体，18个字符刚好
        'alt_char': '-',   # 备用字符
        'alt_length': 20
    },
    'lark': {
        'char': '━',
        'length': 12,      # 飞书比例字体，需要更短
        'alt_char': '-',
        'alt_length': 18
    },
    'qq': {
        'char': '━',
        'length': 14,      # QQ 字体较宽
        'alt_char': '-',
        'alt_length': 20
    },
    'wechat': {
        'char': '━',
        'length': 14,
        'alt_char': '-',
        'alt_length': 20
    },
    'default': {
        'char': '━',
        'length': 14,      # 默认使用较短的分隔线，兼容性更好
        'alt_char': '-',
        'alt_length': 18
    }
}


def get_separator(platform: str = None, use_alt: bool = False) -> str:
    """
    获取平台适配的分隔线
    
    Args:
        platform: 平台名称（telegram/lark/qq/wechat），不提供则使用默认
        use_alt: 是否使用备用字符（普通连字符）
        
    Returns:
        分隔线字符串
        
    Example:
        >>> get_separator('telegram')
        '━━━━━━━━━━━━━━━━━━'
        >>> get_separator('lark')
        '━━━━━━━━━━━━'
    """
    platform = (platform or 'default').lower()
    config = PLATFORM_SEPARATOR_CONFIG.get(platform, PLATFORM_SEPARATOR_CONFIG['default'])
    
    if use_alt:
        return config['alt_char'] * config['alt_length']
    return config['char'] * config['length']


def format_title_for_platform(
    text: str, 
    emoji: str = "", 
    platform: str = None,
    include_bottom: bool = True
) -> str:
    """
    格式化平台适配的标题
    
    Args:
        text: 标题文本
        emoji: 标题图标（可选）
        platform: 平台名称
        include_bottom: 是否包含底部分隔线
        
    Returns:
        格式化后的标题
        
    Example:
        >>> format_title_for_platform("签到系统", "📝", "lark")
        ━━━━━━━━━━━━
        📝 签到系统
        ━━━━━━━━━━━━
    """
    separator = get_separator(platform)
    title_text = f"{emoji} {text}" if emoji else text
    
    if include_bottom:
        return f"{separator}\n{title_text}\n{separator}"
    else:
        return f"{separator}\n{title_text}"


class PlatformFormatter:
    """
    平台感知的消息格式化器
    
    用法:
        formatter = PlatformFormatter('lark')
        msg = formatter.title("签到系统", "📝")
        msg += formatter.separator()
    """
    
    def __init__(self, platform: str = None, capabilities: Dict = None):
        """
        初始化格式化器
        
        Args:
            platform: 平台名称
            capabilities: 平台能力字典（会从中提取 platform_name）
        """
        if capabilities and 'platform_name' in capabilities:
            self.platform = capabilities['platform_name'].lower()
        else:
            self.platform = (platform or 'default').lower()
    
    def separator(self, use_alt: bool = False) -> str:
        """获取分隔线"""
        return get_separator(self.platform, use_alt)
    
    def title(self, text: str, emoji: str = "", include_bottom: bool = True) -> str:
        """格式化标题"""
        return format_title_for_platform(text, emoji, self.platform, include_bottom)
    
    def section_header(self, text: str, emoji: str = "") -> str:
        """格式化章节标题（不带分隔线）"""
        return f"{emoji} {text}" if emoji else text
    
    def divider(self) -> str:
        """获取分割线（单行）"""
        return self.separator()


def format_title(text: str, emoji: str = "", width: int = 20) -> str:
    """
    格式化标题
    
    Args:
        text: 标题文本
        emoji: 标题图标（可选）
        width: 分隔线宽度
        
    Returns:
        格式化后的标题
        
    Example:
        >>> format_title("签到系统", "📝")
        ━━━━━━━━━━━━━━━━━━
        📝 签到系统
        ━━━━━━━━━━━━━━━━━━
    """
    separator = "━" * width
    title_text = f"{emoji} {text}" if emoji else text
    return f"{separator}\n{title_text}\n{separator}"


def format_section(title: str, content: str, emoji: str = "") -> str:
    """
    格式化章节
    
    Args:
        title: 章节标题
        content: 章节内容
        emoji: 章节图标（可选）
        
    Returns:
        格式化后的章节
        
    Example:
        >>> format_section("基本信息", "用户: 张三\\n积分: 100", "📊")
        📊 基本信息
        用户: 张三
        积分: 100
    """
    section_title = f"{emoji} {title}" if emoji else title
    return f"{section_title}\n{content}"


def format_list(items: List[str], numbered: bool = False, emoji: str = "•") -> str:
    """
    格式化列表
    
    Args:
        items: 列表项
        numbered: 是否使用数字编号
        emoji: 列表项图标（仅非编号模式）
        
    Returns:
        格式化后的列表
        
    Example:
        >>> format_list(["项目1", "项目2", "项目3"], numbered=True)
        1. 项目1
        2. 项目2
        3. 项目3
    """
    if not items:
        return ""
    
    result = []
    for i, item in enumerate(items, 1):
        if numbered:
            result.append(f"{i}. {item}")
        else:
            result.append(f"{emoji} {item}")
    
    return "\n".join(result)


def format_key_value(key: str, value: str, separator: str = ": ", emoji: str = "") -> str:
    """
    格式化键值对
    
    Args:
        key: 键
        value: 值
        separator: 分隔符
        emoji: 图标（可选）
        
    Returns:
        格式化后的键值对
        
    Example:
        >>> format_key_value("用户名", "张三", emoji="👤")
        👤 用户名: 张三
    """
    prefix = f"{emoji} " if emoji else ""
    return f"{prefix}{key}{separator}{value}"


def format_navigation(step: int, total: int, show_progress: bool = True) -> str:
    """
    格式化导航提示
    
    Args:
        step: 当前步骤（从1开始）
        total: 总步骤数
        show_progress: 是否显示进度条
        
    Returns:
        格式化后的导航提示
        
    Example:
        >>> format_navigation(2, 5)
        ━━━━━━━━━━━━━━━━━━
        📍 步骤 2/5
        ▓▓▓▓░░░░░░ 40%
    """
    result = "━━━━━━━━━━━━━━━━━━\n"
    result += f"📍 步骤 {step}/{total}\n"
    
    if show_progress:
        progress = int((step / total) * 10)
        bar = "▓" * progress + "░" * (10 - progress)
        percentage = int((step / total) * 100)
        result += f"{bar} {percentage}%"
    
    return result


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """
    截断文本
    
    Args:
        text: 原始文本
        max_length: 最大长度
        suffix: 截断后缀
        
    Returns:
        截断后的文本
        
    Example:
        >>> truncate_text("这是一段很长的文本内容", 10)
        这是一段很长的...
    """
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def format_table(headers: List[str], rows: List[List[str]], align: str = "left") -> str:
    """
    格式化表格（简单文本表格）
    
    Args:
        headers: 表头
        rows: 数据行
        align: 对齐方式（left/center/right）
        
    Returns:
        格式化后的表格
        
    Example:
        >>> format_table(["姓名", "积分"], [["张三", "100"], ["李四", "200"]])
        姓名    积分
        ────────────
        张三    100
        李四    200
    """
    if not headers or not rows:
        return ""
    
    # 计算每列的最大宽度
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))
    
    # 格式化表头
    header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    separator = "─" * len(header_line)
    
    # 格式化数据行
    data_lines = []
    for row in rows:
        line = "  ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
        data_lines.append(line)
    
    return f"{header_line}\n{separator}\n" + "\n".join(data_lines)


def format_box(content: str, width: int = 30, style: str = "single") -> str:
    """
    格式化文本框
    
    Args:
        content: 内容
        width: 宽度
        style: 边框样式（single/double/round）
        
    Returns:
        格式化后的文本框
        
    Example:
        >>> format_box("重要提示", style="double")
        ╔══════════════════════════════╗
        ║ 重要提示                     ║
        ╚══════════════════════════════╝
    """
    styles = {
        "single": {"tl": "┌", "tr": "┐", "bl": "└", "br": "┘", "h": "─", "v": "│"},
        "double": {"tl": "╔", "tr": "╗", "bl": "╚", "br": "╝", "h": "═", "v": "║"},
        "round": {"tl": "╭", "tr": "╮", "bl": "╰", "br": "╯", "h": "─", "v": "│"}
    }
    
    s = styles.get(style, styles["single"])
    
    # 分割内容为多行
    lines = content.split("\n")
    
    # 构建文本框
    top = s["tl"] + s["h"] * (width - 2) + s["tr"]
    bottom = s["bl"] + s["h"] * (width - 2) + s["br"]
    
    content_lines = []
    for line in lines:
        # 截断或填充到指定宽度
        if len(line) > width - 4:
            line = line[:width - 7] + "..."
        padded_line = line.ljust(width - 4)
        content_lines.append(f"{s['v']} {padded_line} {s['v']}")
    
    return f"{top}\n" + "\n".join(content_lines) + f"\n{bottom}"


def format_percentage(value: float, total: float, decimals: int = 1) -> str:
    """
    格式化百分比
    
    Args:
        value: 当前值
        total: 总值
        decimals: 小数位数
        
    Returns:
        格式化后的百分比
        
    Example:
        >>> format_percentage(75, 100)
        75.0%
    """
    if total == 0:
        return "0%"
    
    percentage = (value / total) * 100
    return f"{percentage:.{decimals}f}%"


def format_number(number: int, separator: str = ",") -> str:
    """
    格式化数字（添加千位分隔符）
    
    Args:
        number: 数字
        separator: 分隔符
        
    Returns:
        格式化后的数字
        
    Example:
        >>> format_number(1234567)
        1,234,567
    """
    return f"{number:,}".replace(",", separator)
