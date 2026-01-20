"""
书籍搜索响应构建器
负责根据平台能力构建合适的响应（按钮/文本）
"""
from typing import Dict, List, Any, Optional, Tuple
from astrbot.core.message.components import InlineKeyboard


class BookResponseBuilder:
    """书籍搜索响应构建器"""
    
    def __init__(self, capabilities: Dict[str, Any]):
        """
        初始化响应构建器
        
        Args:
            capabilities: 平台能力字典
        """
        self.capabilities = capabilities
        self.supports_buttons = capabilities.get('supports_buttons', False)
        self.platform_name = capabilities.get('platform_name', '').lower()
    
    def build_search_keyboard(
        self,
        books: List[Dict],
        keyword: str,
        page: int,
        page_size: int,
        total: int,
        api_source: str = "default"
    ) -> Optional[InlineKeyboard]:
        """
        构建搜索结果键盘
        
        Args:
            books: 书籍列表
            keyword: 搜索关键词
            page: 当前页码
            page_size: 每页数量
            total: 总数
            api_source: API源
            
        Returns:
            InlineKeyboard 或 None
        """
        if not self.supports_buttons:
            return None
        
        kb = InlineKeyboard()
        total_pages = max(1, (total + page_size - 1) // page_size)
        
        # 详情按钮（数字），每行8个
        detail_buttons = []
        for idx, book in enumerate(books, start=1):
            ssid = str(book.get("id") or "")
            
            if api_source == "alternative":
                # 备用API：尝试从link解析
                link = book.get("link", "")
                if link:
                    group_id, message_id = self._parse_telegram_link(link)
                    if group_id and message_id:
                        cb = f"book:alt_copy:{group_id}:{message_id}:{idx}"
                        detail_buttons.append({"text": str(idx), "callback_data": cb})
                        continue
            
            # 默认API：使用 SSID
            if ssid.isdigit() and len(ssid) == 8:
                cb = f"book:detail:{ssid}"
                detail_buttons.append({"text": str(idx), "callback_data": cb})
        
        # 添加详情按钮行
        if detail_buttons:
            for i in range(0, len(detail_buttons), 8):
                kb.add_row(*detail_buttons[i:i+8])
        
        # 翻页按钮
        nav_row = []
        if page > 1:
            prev_cb = self._encode_page_callback(keyword, page - 1, page_size, api_source)
            nav_row.append({"text": "⬅️ 上一页", "callback_data": prev_cb})
            
            home_cb = self._encode_page_callback(keyword, 1, page_size, api_source)
            nav_row.append({"text": "🏠 首页", "callback_data": home_cb})
        
        if page < total_pages:
            next_cb = self._encode_page_callback(keyword, page + 1, page_size, api_source)
            nav_row.append({"text": "➡️ 下一页", "callback_data": next_cb})
        
        if nav_row:
            kb.add_row(*nav_row)
        
        # 换源按钮 + 退出按钮
        action_row = []
        switch_source = "default" if api_source == "alternative" else "alternative"
        switch_text = "🔄 默认搜" if api_source == "alternative" else "🔄 换源搜"
        switch_cb = self._encode_page_callback(keyword, 1, page_size, switch_source)
        action_row.append({"text": switch_text, "callback_data": switch_cb})
        action_row.append({"text": "❌ 退出", "callback_data": "book:exit"})
        kb.add_row(*action_row)
        
        return kb if kb.buttons else None
    
    def build_detail_keyboard(
        self,
        ssid: str,
        format_buttons: List[Dict],
        bot_username: str = "zslraibot"
    ) -> Optional[InlineKeyboard]:
        """
        构建书籍详情键盘
        
        Args:
            ssid: 书籍SSID
            format_buttons: 格式按钮列表
            bot_username: 机器人用户名
            
        Returns:
            InlineKeyboard 或 None
        """
        if not self.supports_buttons:
            return None
        
        kb = InlineKeyboard()
        
        if format_buttons:
            # 添加格式按钮，每行2个
            for i in range(0, len(format_buttons), 2):
                row = format_buttons[i:i+2]
                kb.add_row(*[{"text": btn["text"], "url": btn.get("url", "")} for btn in row])
            
            # AI解读按钮
            ai_url = f"https://t.me/{bot_username}/?start=ai_interpret_{ssid}"
            kb.add_row({"text": "🤖 AI解读", "url": ai_url})
        else:
            # 无文件时
            ai_url = f"https://t.me/{bot_username}/?start=ai_interpret_{ssid}"
            kb.add_row(
                {"text": "暂无书籍文件"},
                {"text": "🤖 AI解读", "url": ai_url}
            )
        
        return kb if kb.buttons else None
    
    def build_navigation_keyboard(
        self,
        show_back: bool = True,
        show_home: bool = False,
        show_exit: bool = True
    ) -> Optional[InlineKeyboard]:
        """
        构建导航键盘
        
        Args:
            show_back: 显示返回按钮
            show_home: 显示首页按钮
            show_exit: 显示退出按钮
            
        Returns:
            InlineKeyboard 或 None
        """
        if not self.supports_buttons:
            return None
        
        kb = InlineKeyboard()
        nav_row = []
        
        if show_home:
            nav_row.append({"text": "🏠 首页", "callback_data": "book:home"})
        if show_back:
            nav_row.append({"text": "↩️ 返回", "callback_data": "book:back"})
        if show_exit:
            nav_row.append({"text": "❌ 退出", "callback_data": "book:exit"})
        
        if nav_row:
            kb.add_row(*nav_row)
        
        return kb if kb.buttons else None
    
    def _encode_page_callback(
        self,
        keyword: str,
        page: int,
        size: int,
        api_source: str
    ) -> str:
        """编码分页回调数据"""
        # 替换可能的问题字符
        safe_keyword = str(keyword).replace("|", "_").replace("=", "_").replace("&", "_")
        
        # 格式：book:page:<keyword>:<page>:<size>:<api_source>
        callback_data = f"book:page:{safe_keyword}:{page}:{size}:{api_source}"
        
        # 检查长度限制
        if len(callback_data) > 64:
            max_keyword_len = 64 - len(f"book:page::{page}:{size}:{api_source}")
            if max_keyword_len > 0:
                truncated_keyword = safe_keyword[:max_keyword_len]
                callback_data = f"book:page:{truncated_keyword}:{page}:{size}:{api_source}"
            else:
                return ""
        
        return callback_data
    
    def _parse_telegram_link(self, link: str) -> Tuple[str, str]:
        """解析 Telegram 链接"""
        group_id = ""
        message_id = ""
        
        try:
            if "/c/" in link:
                # 格式1：https://t.me/c/2011682900/668274
                parts = link.split("/c/")[1].split("/")
                if len(parts) >= 2:
                    group_id = f"-100{parts[0]}"
                    message_id = parts[1]
            elif "t.me/" in link and "/c/" not in link:
                # 格式2：https://t.me/WaiKan2023/50282
                parts = link.split("t.me/")[1].split("/")
                if len(parts) >= 2:
                    group_id = f"@{parts[0]}"
                    message_id = parts[1]
        except Exception:
            pass
        
        return group_id, message_id
