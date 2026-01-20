"""
豆瓣插件响应构建器
继承通用基类，实现插件特定功能
"""
from typing import Optional, Tuple, List, Dict, Any
import json
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


class DoubanResponseBuilder(BaseResponseBuilder):
    """豆瓣插件响应构建器 - 继承通用基类"""
    
    def build_search_results(self,
                            message: str,
                            search_type: str,
                            keyword: str,
                            page: int,
                            total_pages: int,
                            results: List[Dict]) -> Tuple[str, Optional[Any]]:
        """
        构建搜索结果响应
        
        Args:
            message: 格式化的消息文本
            search_type: 搜索类型
            keyword: 搜索关键词
            page: 当前页码
            total_pages: 总页数
            results: 搜索结果列表
            
        Returns:
            (消息文本, 键盘)
        """
        keyboard = self.build_search_result_keyboard(
            results=results,
            search_type=search_type,
            keyword=keyword,
            page=page,
            page_size=15,
            total_count=total_pages * 15  # 近似总数
        )
        return message, keyboard
    
    def build_search_result_keyboard(self,
                                     results: List[Dict],
                                     search_type: str,
                                     keyword: str,
                                     page: int = 1,
                                     page_size: int = 15,
                                     total_count: int = 0) -> Optional[Any]:
        """
        构建搜索结果键盘
        
        Args:
            results: 当前页搜索结果列表
            search_type: 搜索类型
            keyword: 搜索关键词
            page: 当前页码
            page_size: 每页显示数量
            total_count: 总条数
            
        Returns:
            InlineKeyboard 或 None
        """
        if not self.is_button_mode():
            return None
        
        keyboard = InlineKeyboard()
        use_json_format = self.platform_name == "lark"  # 飞书使用JSON格式
        
        # 数字按钮（显示详情）
        number_buttons = []
        for idx, item in enumerate(results, 1):
            item_id = item.get("id", "")
            if item_id:
                if use_json_format:
                    # JSON格式回调（飞书）
                    callback_data = json.dumps({
                        "action": "douban_detail",
                        "type": search_type,
                        "id": item_id
                    }, ensure_ascii=False)
                else:
                    # 传统格式回调（Telegram等）
                    callback_data = f"douban:detail:{search_type}:{item_id}"
                
                # 为飞书平台设置按钮配置
                button_config = {"text": str(idx), "callback_data": callback_data}
                if use_json_format:  # 飞书平台
                    button_config["button_size"] = "tiny"
                    button_config["button_type"] = "default"
                number_buttons.append(button_config)
        
        # 添加数字按钮行（每行8个）
        for i in range(0, len(number_buttons), 8):
            row_buttons = number_buttons[i:i+8]
            keyboard.buttons.append(row_buttons)
        
        # 分页按钮
        page_buttons = []
        if page > 1:
            if use_json_format:
                prev_callback = json.dumps({
                    "action": "douban_page",
                    "search_type": search_type,
                    "keyword": keyword,
                    "page": page - 1
                }, ensure_ascii=False)
            else:
                prev_callback = f"douban:page:{search_type}:{keyword}:{page-1}"
            page_buttons.append({"text": "⬅️ 上页", "callback_data": prev_callback})
        
        # 回首页 (只在第3页及以上显示)
        if page >= 3:
            if use_json_format:
                home_callback = json.dumps({
                    "action": "douban_page",
                    "search_type": search_type,
                    "keyword": keyword,
                    "page": 1
                }, ensure_ascii=False)
            else:
                home_callback = f"douban:page:{search_type}:{keyword}:1"
            page_buttons.append({"text": "🏠 首页", "callback_data": home_callback})
        
        # 判断是否有下一页
        has_next_page = False
        if total_count > 0:
            total_pages = (total_count + page_size - 1) // page_size
            has_next_page = page < total_pages
        else:
            has_next_page = len(results) >= 15
        
        if has_next_page:
            if use_json_format:
                next_callback = json.dumps({
                    "action": "douban_page",
                    "search_type": search_type,
                    "keyword": keyword,
                    "page": page + 1
                }, ensure_ascii=False)
            else:
                next_callback = f"douban:page:{search_type}:{keyword}:{page+1}"
            page_buttons.append({"text": "➡️ 下页", "callback_data": next_callback})
        
        if page_buttons:
            keyboard.buttons.append(page_buttons)
        
        # 换源按钮 + 退出按钮
        action_buttons = []
        if search_type == "book":
            if use_json_format:
                switch_callback = json.dumps({
                    "action": "douban_switch",
                    "search_type": "movie",
                    "keyword": keyword,
                    "page": 1
                }, ensure_ascii=False)
            else:
                switch_callback = f"douban:switch:movie:{keyword}:1"
            action_buttons.append({"text": "🎬 搜电影", "callback_data": switch_callback})
        else:
            if use_json_format:
                switch_callback = json.dumps({
                    "action": "douban_switch",
                    "search_type": "book",
                    "keyword": keyword,
                    "page": 1
                }, ensure_ascii=False)
            else:
                switch_callback = f"douban:switch:book:{keyword}:1"
            action_buttons.append({"text": "📚 搜书籍", "callback_data": switch_callback})
        
        # 添加退出按钮
        exit_button = self.build_exit_button("douban", use_json_format)
        action_buttons.append(exit_button)
        
        keyboard.buttons.append(action_buttons)
        
        return keyboard
    
    def build_action_keyboard(self,
                             douban_type: str,
                             douban_id: str,
                             title: Optional[str],
                             bot_username: str = "zslraibot") -> Optional[Any]:
        """
        创建操作按钮
        
        Args:
            douban_type: 豆瓣类型
            douban_id: 豆瓣ID
            title: 标题
            bot_username: 机器人用户名
            
        Returns:
            InlineKeyboard 或 None
        """
        if not self.supports_buttons or InlineKeyboard is None:
            return None
        
        keyboard = InlineKeyboard()
        use_json_format = self.platform_name.lower() == "lark"
        
        # 搜索资源按钮 - 根据类型区分：书籍用 book 插件，影视用 pansou 插件
        import base64
        
        if douban_type == "book":
            # 书籍：跳转到 book 插件搜索电子书
            if use_json_format:
                search_callback = json.dumps({
                    "action": "book_douban_search",
                    "id": douban_id,
                    "title": title or "未知"
                }, ensure_ascii=False)
                keyboard.add_button("📚 搜索书籍", callback_data=search_callback)
            else:
                # Telegram: 使用 bks_ 前缀跳转到 book 插件
                payload = {"id": douban_id}
                json_str = json.dumps(payload, ensure_ascii=False)
                encoded_payload = base64.urlsafe_b64encode(json_str.encode('utf-8')).decode('ascii')
                search_url = f"https://t.me/{bot_username}/?start=bks_{encoded_payload}"
                keyboard.add_button("📚 搜索书籍", url=search_url)
        else:
            # 影视：跳转到 pansou 插件搜索网盘资源
            if use_json_format:
                search_callback = json.dumps({
                    "action": "pansou_douban_search",
                    "type": douban_type,
                    "id": douban_id,
                    "title": title or "未知"
                }, ensure_ascii=False)
                keyboard.add_button("🔍 搜索资源", callback_data=search_callback)
            else:
                # Telegram: 使用 ps_ 前缀跳转到 pansou 插件
                payload = {"type": douban_type, "id": douban_id}
                json_str = json.dumps(payload, ensure_ascii=False)
                encoded_payload = base64.urlsafe_b64encode(json_str.encode('utf-8')).decode('ascii')
                search_url = f"https://t.me/{bot_username}/?start=ps_{encoded_payload}"
                keyboard.add_button("🔍 搜索资源", url=search_url)
        
        # AI解读按钮
        if use_json_format:
            ai_interpret_callback = json.dumps({
                "action": "douban_ai_interpret",
                "type": douban_type,
                "id": douban_id
            }, ensure_ascii=False)
            keyboard.add_button("🤖 AI解读", callback_data=ai_interpret_callback)
        else:
            # AI 解读需要 type 和 id
            ai_payload = {"type": douban_type, "id": douban_id}
            ai_json_str = json.dumps(ai_payload, ensure_ascii=False)
            ai_encoded_payload = base64.urlsafe_b64encode(ai_json_str.encode('utf-8')).decode('ascii')
            ai_interpret_url = f"https://t.me/{bot_username}/?start=dbai_{ai_encoded_payload}"
            keyboard.add_button("🤖 AI解读", url=ai_interpret_url)
        
        # 查看详情按钮
        detail_url = ""
        if douban_type == "movie":
            detail_url = f"https://movie.douban.com/subject/{douban_id}/"
        elif douban_type == "book":
            detail_url = f"https://book.douban.com/subject/{douban_id}/"
        
        if detail_url:
            keyboard.add_button("📖 查看详情", url=detail_url)
        
        return keyboard
    
    def build_empty_search_keyboard(self,
                                   search_type: str,
                                   keyword: str) -> Optional[Any]:
        """
        创建空搜索结果键盘（仅换源按钮）
        
        Args:
            search_type: 搜索类型
            keyword: 搜索关键词
            
        Returns:
            InlineKeyboard 或 None
        """
        if not self.supports_buttons or InlineKeyboard is None:
            return None
        
        keyboard = InlineKeyboard()
        use_json_format = self.platform_name.lower() == "lark"
        
        # 添加换源按钮
        if search_type == "book":
            if use_json_format:
                switch_callback = json.dumps({
                    "action": "douban_switch",
                    "search_type": "movie",
                    "keyword": keyword,
                    "page": 1
                }, ensure_ascii=False)
            else:
                switch_callback = f"douban:switch:movie:{keyword}:1"
            keyboard.add_button("🎬 搜电影", callback_data=switch_callback)
        else:
            if use_json_format:
                switch_callback = json.dumps({
                    "action": "douban_switch",
                    "search_type": "book",
                    "keyword": keyword,
                    "page": 1
                }, ensure_ascii=False)
            else:
                switch_callback = f"douban:switch:book:{keyword}:1"
            keyboard.add_button("📚 搜书籍", callback_data=switch_callback)
        
        return keyboard
