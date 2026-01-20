"""
响应构建器模块
负责构建不同平台的响应（按钮、键盘等）
"""
import json
from typing import Optional, Any, List, Dict
from astrbot.api import logger

try:
    from astrbot.core.message.components import InlineKeyboard
except ImportError:
    InlineKeyboard = None
    logger.warning("[Pansou] InlineKeyboard 不可用，按钮功能将被禁用")


class PansouResponseBuilder:
    """资源搜索响应构建器"""
    
    def __init__(self, capabilities: Dict):
        """
        初始化响应构建器
        
        Args:
            capabilities: 平台能力字典
        """
        self.capabilities = capabilities
        self.supports_buttons = capabilities.get('supports_buttons', False)
        self.platform_name = capabilities.get('platform_name', 'unknown')
    
    def build_search_results(
        self,
        message: str,
        keyword: str,
        page: int,
        total_pages: int,
        results: List[Dict],
        cloud_types: Optional[str] = None
    ) -> tuple:
        """
        构建搜索结果响应
        
        Args:
            message: 格式化的消息文本
            keyword: 搜索关键词
            page: 当前页码
            total_pages: 总页数
            results: 结果列表
            cloud_types: 当前筛选的网盘类型
            
        Returns:
            (消息文本, 键盘)
        """
        logger.info(f"[Pansou] ResponseBuilder - 平台: {self.platform_name}, 支持按钮: {self.supports_buttons}")
        
        if not self.supports_buttons or InlineKeyboard is None:
            logger.info(f"[Pansou] 会话模式，不构建按钮")
            return message, None
        
        keyboard = InlineKeyboard()
        use_json_format = self.platform_name.lower() == "lark"
        
        # 如果 cloud_types 是默认的完整列表，则视为未筛选（传递 None）
        # 这样可以避免回调数据过长
        default_types = "baidu,aliyun,quark,tianyi,uc,mobile,115,pikpak,xunlei,123"
        if cloud_types == default_types:
            cloud_types = None
        
        # 构建翻页按钮
        page_buttons = []
        if page > 1:
            # 上一页按钮
            if use_json_format:
                prev_callback = json.dumps({
                    "action": "pansou_page",
                    "keyword": keyword,
                    "page": page - 1,
                    "cloud_types": cloud_types
                }, ensure_ascii=False)
            else:
                prev_callback = f"pansou:page:{keyword}:{page - 1}:{cloud_types or ''}"
            page_buttons.append({"text": "⬅️ 上页", "callback_data": prev_callback})
        
        # 只有在第三页及以上显示回首页按钮
        if page >= 3:
            if use_json_format:
                home_callback = json.dumps({
                    "action": "pansou_page",
                    "keyword": keyword,
                    "page": 1,
                    "cloud_types": cloud_types
                }, ensure_ascii=False)
            else:
                home_callback = f"pansou:page:{keyword}:1:{cloud_types or ''}"
            page_buttons.append({"text": "🏠 首页", "callback_data": home_callback})
        
        if page < total_pages:
            # 下一页按钮
            if use_json_format:
                next_callback = json.dumps({
                    "action": "pansou_page",
                    "keyword": keyword,
                    "page": page + 1,
                    "cloud_types": cloud_types
                }, ensure_ascii=False)
            else:
                next_callback = f"pansou:page:{keyword}:{page + 1}:{cloud_types or ''}"
            page_buttons.append({"text": "下页 ➡️", "callback_data": next_callback})
        
        if page_buttons:
            keyboard.buttons.append(page_buttons)
        
        # 网盘类型快捷筛选按钮
        cloud_type_buttons = []
        
        # 第一行：5个云盘类型
        first_row_types = [
            ("baidu", "百度"),
            ("aliyun", "阿里"),
            ("quark", "夸克"),
            ("tianyi", "天翼"),
            ("uc", "UC")
        ]
        
        for cloud_type, cloud_name in first_row_types:
            # 判断是否已选中
            is_selected = cloud_types == cloud_type
            button_text = f"✅ {cloud_name}" if is_selected else cloud_name
            
            # 如果已选中，点击则清除筛选；否则选中该类型
            new_cloud_types = "" if is_selected else cloud_type
            
            if use_json_format:
                callback_data = json.dumps({
                    "action": "pansou_page",
                    "keyword": keyword,
                    "page": 1,
                    "cloud_types": new_cloud_types if new_cloud_types else None
                }, ensure_ascii=False)
            else:
                callback_data = f"pansou:page:{keyword}:1:{new_cloud_types}"
            
            cloud_type_buttons.append({"text": button_text, "callback_data": callback_data})
        
        keyboard.buttons.append(cloud_type_buttons)
        
        # 第二行：5个云盘类型
        second_row_types = [
            ("115", "115"),
            ("pikpak", "PikPak"),
            ("xunlei", "迅雷"),
            ("123", "123"),
            ("magnet", "磁力")
        ]
        
        second_row_buttons = []
        for cloud_type, cloud_name in second_row_types:
            is_selected = cloud_types == cloud_type
            button_text = f"✅ {cloud_name}" if is_selected else cloud_name
            new_cloud_types = "" if is_selected else cloud_type
            
            if use_json_format:
                callback_data = json.dumps({
                    "action": "pansou_page",
                    "keyword": keyword,
                    "page": 1,
                    "cloud_types": new_cloud_types if new_cloud_types else None
                }, ensure_ascii=False)
            else:
                callback_data = f"pansou:page:{keyword}:1:{new_cloud_types}"
            
            second_row_buttons.append({"text": button_text, "callback_data": callback_data})
        
        keyboard.buttons.append(second_row_buttons)
        
        return message, keyboard
