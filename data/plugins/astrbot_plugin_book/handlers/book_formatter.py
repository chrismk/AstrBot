"""
书籍搜索结果格式化器
"""
from typing import Dict, List, Tuple, Any, Optional
import sys
from pathlib import Path
plugin_root = Path(__file__).parent.parent.parent
if str(plugin_root) not in sys.path:
    sys.path.insert(0, str(plugin_root))
from common.message_formatter import get_separator


def _bytes_to_human(size_bytes: int) -> str:
    """将字节数转换为人类可读格式"""
    try:
        size = float(size_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024.0:
                if unit == "B":
                    return f"{int(size)}B"
                return f"{size:.2f}{unit}"
            size /= 1024.0
        return f"{size:.2f}PB"
    except Exception:
        return str(size_bytes)


def _build_duxiu_cover_url(eight_digits: str) -> str:
    """构建读秀封面URL"""
    try:
        chars = list(eight_digits)
        parts = []
        for idx, ch in enumerate(chars):
            seg = "6" + ch
            if idx == 1:
                seg += "5F"
            if idx == 4:
                seg += "5F"
            parts.append(seg)
        modified = "".join(parts)
        return (
            "https://unicover.duxiu.com/coverNew/CoverNew.dll?iid="
            + modified
            + "9C97569E9F8FA791A495A29D91A29B566131688929249994130"
        )
    except Exception:
        return ""


class BookFormatter:
    """书籍搜索结果格式化器"""
    
    @staticmethod
    def format_search_results(
        books: List[Dict],
        page: int,
        page_size: int,
        total: int,
        api_source: str = "default",
        show_hints: bool = True,
        timeout_minutes: int = 1
    ) -> Tuple[str, List[Dict]]:
        """
        格式化搜索结果列表
        
        Args:
            books: 书籍列表
            page: 当前页码
            page_size: 每页数量
            total: 总数
            api_source: API源
            show_hints: 是否显示导航提示（会话模式）
            timeout_minutes: 会话超时时间
            
        Returns:
            (格式化文本, 书籍列表)
        """
        if not books:
            return "未找到任何结果，请尝试换源搜索", []
        
        lines = []
        total_pages = max(1, (total + page_size - 1) // page_size)
        source_text = "备用源" if api_source == "alternative" else "默认源"
        
        # 结果列表
        for idx, book in enumerate(books, start=1):
            ssid = str(book.get("id") or "")
            title = str(book.get("title") or "")
            author = str(book.get("author") or "").strip()
            ext = str(book.get("extension") or "").lower()
            fs = int(book.get("filesize") or 0)
            size_h = _bytes_to_human(fs)
            
            # 构建显示行
            if api_source == "alternative":
                if author:
                    line = f"{idx}.【{ssid}】{title} - {author} {size_h}"
                else:
                    line = f"{idx}.【{ssid}】{title} {size_h}"
            else:
                if author:
                    line = f"{idx}.【{ssid}】{title} - {author}.{ext} {size_h}"
                else:
                    line = f"{idx}.【{ssid}】{title}.{ext} {size_h}"
            
            lines.append(line)
            
        lines.append("")
        separator = get_separator()
        lines.append(separator)
        lines.append(f"📚 书籍搜索结果 (第{page}/{total_pages}页，共{total}条) [{source_text}]")
        
        # 导航提示（仅会话模式）
        if show_hints:
            lines.append("💡 请输入序号查看详情")
            
            nav_parts = []
            if page > 1:
                nav_parts.append("p-上页")
            if page < total_pages:
                nav_parts.append("n-下页")
            if page >= 3:
                nav_parts.append("h-首页")
            # 显示具体的换源目标
            if api_source == "alternative":
                nav_parts.append("s-默认源")
            else:
                nav_parts.append("s-备用源")
            nav_parts.append("0-退出")
            
            lines.append(f"💡 {' | '.join(nav_parts)}")
            lines.append(f"⏱️ 请在 {timeout_minutes} 分钟内输入")
        
        return "\n".join(lines), books
    
    @staticmethod
    def format_book_detail(book: Dict, ssid: str) -> str:
        """
        格式化书籍详情
        
        Args:
            book: 书籍信息
            ssid: 书籍SSID
            
        Returns:
            格式化文本
        """
        lines = []
        
        title = str(book.get("title") or "")
        author = str(book.get("author") or "")
        publisher = str(book.get("publisher") or "")
        year = str(book.get("year") or "")
        pages = str(book.get("pages") or "")
        isbn = str(book.get("isbn") or "")
        
        if title:
            lines.append(f"书名:{title}")
        if author:
            lines.append(f"作者:{author}")
        if publisher:
            lines.append(f"出版:{publisher}")
        if year:
            lines.append(f"年份:{year}")
        if pages:
            lines.append(f"页数:{pages}")
        if isbn:
            lines.append(f"ISBN:{isbn}")
        if ssid:
            lines.append(f"SSID:{ssid}")
        
        return "\n".join(lines)
    
    @staticmethod
    def format_book_info_for_ai(book: Dict, ssid: str) -> str:
        """
        格式化书籍信息用于 AI 解读
        
        Args:
            book: 书籍信息
            ssid: 书籍SSID
            
        Returns:
            格式化文本
        """
        lines = []
        
        title = str(book.get("title", "")).strip()
        author = str(book.get("author", "")).strip()
        publisher = str(book.get("publisher", "")).strip()
        year = str(book.get("year", "")).strip()
        pages = str(book.get("pages", "")).strip()
        isbn = str(book.get("isbn", "")).strip()
        
        if title:
            lines.append(f"📖 书名：{title}")
        if author:
            lines.append(f"✍️ 作者：{author}")
        if publisher:
            lines.append(f"🏢 出版社：{publisher}")
        if year:
            lines.append(f"📅 出版年份：{year}")
        if pages:
            lines.append(f"📄 页数：{pages}")
        if isbn:
            lines.append(f"🔢 ISBN：{isbn}")
        if ssid:
            lines.append(f"🆔 SSID：{ssid}")
        
        return "\n".join(lines) if lines else "书籍信息不完整"
    
    @staticmethod
    def format_file_formats(formats: List[Dict], ssid: str, bot_username: str = "zslraibot") -> List[Dict]:
        """
        格式化文件格式列表（用于生成按钮）
        
        Args:
            formats: 格式列表
            ssid: 书籍SSID
            bot_username: 机器人用户名
            
        Returns:
            按钮数据列表
        """
        buttons = []
        
        for item in formats:
            ext_raw = str(item.get("extension") or "")
            if not ext_raw:
                continue
            
            ext_up = ext_raw.upper()
            ext_low = ext_raw.lower()
            fs = int(item.get("file_size") or 0)
            tag_val = str(item.get("tag") or "").strip()
            source = str(item.get("source") or "")
            
            file_tag = f"{fs}{ext_low}"
            backend_tag = tag_val if tag_val else file_tag
            
            # 根据数据来源生成不同的深度链接格式
            if source == "backup_search" and tag_val:
                encoded_tag = tag_val.replace(".", "d").replace("-", "m")
                deep_link_param = f"gb_{ssid}_{file_tag}_{encoded_tag}"
            else:
                deep_link_param = f"bk_{ssid}_{file_tag}_{backend_tag}"
            
            deep_link = f"https://t.me/{bot_username}/?start={deep_link_param}"
            
            buttons.append({
                "text": f"{ext_up}/{_bytes_to_human(fs)}",
                "url": deep_link,
                "file_tag": file_tag,
                "backend_tag": backend_tag
            })
        
        return buttons
    
    @staticmethod
    def format_file_formats_for_session(formats: List[Dict]) -> Tuple[str, List[Dict]]:
        """
        格式化文件格式列表（用于会话模式显示）
        
        Args:
            formats: 格式列表
            
        Returns:
            (格式化文本, 格式数据列表)
        """
        if not formats:
            return "", []
        
        lines = ["📥 可下载格式："]
        format_list = []
        
        for i, item in enumerate(formats, 1):
            ext_raw = str(item.get("extension") or "")
            if not ext_raw:
                continue
            
            ext_up = ext_raw.upper()
            ext_low = ext_raw.lower()
            fs = int(item.get("file_size") or 0)
            tag_val = str(item.get("tag") or "").strip()
            source = str(item.get("source") or "")
            
            file_tag = f"{fs}{ext_low}"
            backend_tag = tag_val if tag_val else file_tag
            source_type = "backup" if source == "backup_search" else "default"
            
            size_str = _bytes_to_human(fs)
            lines.append(f"  {i}. {ext_up} ({size_str})")
            
            format_list.append({
                "file_tag": file_tag,
                "backend_tag": backend_tag,
                "source_type": source_type,
                "display": f"{ext_up}/{size_str}"
            })
        
        return "\n".join(lines), format_list
    
    @staticmethod
    def get_cover_url(ssid: str) -> str:
        """获取书籍封面URL"""
        return _build_duxiu_cover_url(ssid)
    
    @staticmethod
    def bytes_to_human(size_bytes: int) -> str:
        """将字节数转换为人类可读格式"""
        return _bytes_to_human(size_bytes)
