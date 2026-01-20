"""
统一输入验证模块
提供常用的输入验证功能
"""
from typing import Optional, Tuple
from datetime import datetime, timedelta
import re


class InputValidator:
    """统一的输入验证器"""
    
    @staticmethod
    def validate_date(text: str) -> Tuple[bool, str, Optional[datetime]]:
        """
        验证日期输入
        
        支持格式：
        - 相对日期：昨天、前天、大前天
        - 数字快捷方式：1(昨天)、2(前天)、3(大前天)
        - 绝对日期：2024-01-15、2024/01/15、20240115
        
        Args:
            text: 输入文本
            
        Returns:
            (是否有效, 错误消息, 日期对象)
        """
        text = text.strip()
        
        # 相对日期映射
        relative_dates = {
            '昨天': timedelta(days=1),
            '前天': timedelta(days=2),
            '大前天': timedelta(days=3),
            '今天': timedelta(days=0),
        }
        
        # 数字快捷方式映射
        numeric_shortcuts = {
            '1': '昨天',
            '2': '前天',
            '3': '大前天',
        }
        
        # 检查数字快捷方式
        if text in numeric_shortcuts:
            text = numeric_shortcuts[text]
        
        # 检查相对日期
        if text in relative_dates:
            date = datetime.now() - relative_dates[text]
            return True, "", date
        
        # 尝试解析绝对日期
        date_formats = [
            '%Y-%m-%d',      # 2024-01-15
            '%Y/%m/%d',      # 2024/01/15
            '%Y%m%d',        # 20240115
            '%m-%d',         # 01-15 (当年)
            '%m/%d',         # 01/15 (当年)
        ]
        
        for fmt in date_formats:
            try:
                date = datetime.strptime(text, fmt)
                # 如果只有月日，补充年份
                if fmt in ['%m-%d', '%m/%d']:
                    date = date.replace(year=datetime.now().year)
                return True, "", date
            except ValueError:
                continue
        
        # 所有格式都失败
        error_msg = "❌ 日期格式错误\n\n支持格式：\n  • 1(昨天)、2(前天)、3(大前天)\n  • 昨天、前天、大前天\n  • 2024-01-15\n  • 2024/01/15\n  • 01-15"
        return False, error_msg, None
    
    @staticmethod
    def validate_number(
        text: str, 
        min_val: Optional[int] = None, 
        max_val: Optional[int] = None,
        allow_float: bool = False
    ) -> Tuple[bool, str, Optional[float]]:
        """
        验证数字输入
        
        Args:
            text: 输入文本
            min_val: 最小值
            max_val: 最大值
            allow_float: 是否允许浮点数
            
        Returns:
            (是否有效, 错误消息, 数字)
        """
        text = text.strip()
        
        try:
            if allow_float:
                num = float(text)
            else:
                num = int(text)
            
            # 检查范围
            if min_val is not None and num < min_val:
                return False, f"❌ 数字不能小于 {min_val}", None
            if max_val is not None and num > max_val:
                return False, f"❌ 数字不能大于 {max_val}", None
            
            return True, "", num
            
        except ValueError:
            error_msg = "❌ 请输入有效的数字"
            if min_val is not None and max_val is not None:
                error_msg += f"（{min_val}-{max_val}）"
            return False, error_msg, None
    
    @staticmethod
    def validate_choice(
        text: str, 
        choices: list,
        case_sensitive: bool = False
    ) -> Tuple[bool, str, Optional[str]]:
        """
        验证选项输入
        
        Args:
            text: 输入文本
            choices: 有效选项列表
            case_sensitive: 是否区分大小写
            
        Returns:
            (是否有效, 错误消息, 选中的选项)
        """
        text = text.strip()
        
        # 不区分大小写
        if not case_sensitive:
            text_lower = text.lower()
            choices_lower = [str(c).lower() for c in choices]
            if text_lower in choices_lower:
                # 返回原始选项
                index = choices_lower.index(text_lower)
                return True, "", str(choices[index])
        else:
            if text in [str(c) for c in choices]:
                return True, "", text
        
        # 无效选项
        choices_str = "、".join([str(c) for c in choices])
        error_msg = f"❌ 无效选项\n\n可选项：{choices_str}"
        return False, error_msg, None
    
    @staticmethod
    def validate_email(text: str) -> Tuple[bool, str, Optional[str]]:
        """
        验证邮箱地址
        
        Args:
            text: 输入文本
            
        Returns:
            (是否有效, 错误消息, 邮箱地址)
        """
        text = text.strip()
        
        # 简单的邮箱正则
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        if re.match(email_pattern, text):
            return True, "", text
        else:
            return False, "❌ 邮箱格式错误", None
    
    @staticmethod
    def validate_url(text: str) -> Tuple[bool, str, Optional[str]]:
        """
        验证URL
        
        Args:
            text: 输入文本
            
        Returns:
            (是否有效, 错误消息, URL)
        """
        text = text.strip()
        
        # URL正则
        url_pattern = r'^https?://[^\s]+$'
        
        if re.match(url_pattern, text):
            return True, "", text
        else:
            return False, "❌ URL格式错误（需要以http://或https://开头）", None
    
    @staticmethod
    def validate_length(
        text: str, 
        min_length: Optional[int] = None, 
        max_length: Optional[int] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        验证文本长度
        
        Args:
            text: 输入文本
            min_length: 最小长度
            max_length: 最大长度
            
        Returns:
            (是否有效, 错误消息, 文本)
        """
        text = text.strip()
        length = len(text)
        
        if min_length is not None and length < min_length:
            return False, f"❌ 文本长度不能少于 {min_length} 个字符", None
        if max_length is not None and length > max_length:
            return False, f"❌ 文本长度不能超过 {max_length} 个字符", None
        
        return True, "", text
    
    @staticmethod
    def validate_pattern(
        text: str, 
        pattern: str, 
        error_message: str = "❌ 格式错误"
    ) -> Tuple[bool, str, Optional[str]]:
        """
        验证正则表达式模式
        
        Args:
            text: 输入文本
            pattern: 正则表达式
            error_message: 错误消息
            
        Returns:
            (是否有效, 错误消息, 文本)
        """
        text = text.strip()
        
        if re.match(pattern, text):
            return True, "", text
        else:
            return False, error_message, None
