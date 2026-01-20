"""
书籍搜索会话处理器
负责处理会话模式下的用户交互
"""
from typing import Dict, Any, Optional, Tuple, List
from astrbot.api import logger

try:
    from common.navigation_handler import NavigationHandler
    from common.navigation_hint import NavigationHint
    NAVIGATION_AVAILABLE = True
except ImportError:
    NAVIGATION_AVAILABLE = False
    logger.warning("[BookSession] 导航模块不可用")


class BookSessionHandler:
    """书籍搜索会话处理器"""
    
    # 会话超时时间（分钟）
    SESSION_TIMEOUT_MINUTES = 1
    
    def __init__(self, session_manager, book_api):
        """
        初始化会话处理器
        
        Args:
            session_manager: 会话管理器
            book_api: 书籍API
        """
        self.session_manager = session_manager
        self.book_api = book_api
        
        # 初始化导航处理器
        self.nav_handler = None
        if NAVIGATION_AVAILABLE:
            self.nav_handler = NavigationHandler(self.session_manager)
            self.nav_handler.register_callbacks(
                on_home=self._on_navigate_home,
                on_back=self._on_navigate_back,
                on_exit=self._on_navigate_exit
            )
    
    async def handle_session_message(
        self,
        user_id: str,
        session_id: str,
        message: str
    ) -> Optional[Tuple[Any, Any]]:
        """
        处理会话消息
        
        Args:
            user_id: 用户ID
            session_id: 会话ID
            message: 用户消息
            
        Returns:
            (消息内容, 键盘) 或 None
        """
        # 获取会话
        session = self.session_manager.get_session(session_id)
        if not session:
            return ("❌ 会话已过期，请重新搜索", None)
        
        message = message.strip()
        data = session.get('data', {})
        current_step = session.get('step', 0)
        
        # 使用 NavigationHandler 处理导航命令
        if self.nav_handler:
            is_handled, result = await self.nav_handler.handle(session_id, message, session)
            if is_handled:
                return result
        
        # 处理分页命令
        if message.lower() in ['p', 'prev', '上页', '上一页']:
            return await self._handle_prev_page(session_id, session)
        
        if message.lower() in ['n', 'next', '下页', '下一页']:
            return await self._handle_next_page(session_id, session)
        
        # 处理换源命令
        if message.lower() in ['s', 'switch', '换源', '切换']:
            return await self._handle_switch_source(session_id, session)
        
        # 处理详情页特殊命令
        if current_step >= 1:
            if message.lower() in ['a', 'ai', '解读']:
                # 返回特殊标记，让主插件处理 AI 解读
                current_ssid = data.get('current_ssid', '')
                if current_ssid:
                    return ("TRIGGER_AI_INTERPRET", current_ssid)
                return ("❌ 无法获取书籍信息", None)
        
        # 处理数字选择
        if message.isdigit():
            index = int(message)
            if current_step == 0:
                # 在搜索结果页，选择查看详情
                return await self._handle_select_book(session_id, session, index)
            elif current_step == 1:
                # 在详情页，选择下载格式
                return await self._handle_select_format(session_id, session, index)
        
        return None
    
    async def _handle_select_format(
        self,
        session_id: str,
        session: Dict[str, Any],
        index: int
    ) -> Tuple[Any, Any]:
        """处理选择下载格式"""
        data = session.get('data', {})
        available_formats = data.get('available_formats', [])
        
        if not available_formats:
            return ("❌ 暂无可下载的文件格式", None)
        
        if index < 1 or index > len(available_formats):
            return (f"❌ 无效的序号，请输入 1-{len(available_formats)} 之间的数字", None)
        
        format_info = available_formats[index - 1]
        ssid = data.get('current_ssid', '')
        
        if not ssid:
            return ("❌ 无法获取书籍信息", None)
        
        # 返回特殊标记，让主插件处理下载
        return ("TRIGGER_DOWNLOAD", ssid, format_info['file_tag'], format_info['backend_tag'], format_info['source_type'])
    
    async def _handle_prev_page(
        self,
        session_id: str,
        session: Dict[str, Any]
    ) -> Tuple[str, Any]:
        """处理上一页"""
        data = session.get('data', {})
        page = data.get('page', 1)
        
        if page <= 1:
            return ("已经是第一页了", None)
        
        # 返回特殊标记，让主插件处理翻页
        return ("TRIGGER_PAGE", page - 1)
    
    async def _handle_next_page(
        self,
        session_id: str,
        session: Dict[str, Any]
    ) -> Tuple[str, Any]:
        """处理下一页"""
        data = session.get('data', {})
        page = data.get('page', 1)
        total = data.get('total', 0)
        page_size = data.get('page_size', 16)
        total_pages = max(1, (total + page_size - 1) // page_size)
        
        if page >= total_pages:
            return ("已经是最后一页了", None)
        
        # 返回特殊标记，让主插件处理翻页
        return ("TRIGGER_PAGE", page + 1)
    
    async def _handle_switch_source(
        self,
        session_id: str,
        session: Dict[str, Any]
    ) -> Tuple[str, Any]:
        """处理换源"""
        data = session['data']
        current_source = data.get('api_source', 'default')
        new_source = 'default' if current_source == 'alternative' else 'alternative'
        
        # 返回特殊标记，让主插件处理换源
        return ("TRIGGER_SWITCH", new_source)
    
    async def _handle_select_book(
        self,
        session_id: str,
        session: Dict[str, Any],
        index: int
    ) -> Tuple[Any, Any]:
        """处理选择书籍"""
        data = session.get('data', {})
        results = data.get('results', [])
        
        if index < 1 or index > len(results):
            return (f"❌ 无效的序号，请输入 1-{len(results)} 之间的数字", None)
        
        book = results[index - 1]
        ssid = str(book.get('id', ''))
        
        if not ssid or not (ssid.isdigit() and len(ssid) == 8):
            return ("❌ 该书籍无法查看详情", None)
        
        # 保存当前选择的 SSID
        data['current_ssid'] = ssid
        self.session_manager.update_session(session_id, step=1, data=data)
        
        # 返回特殊标记，让主插件处理详情显示
        return ("SHOW_BOOK_DETAIL", ssid)
    
    async def _on_navigate_home(
        self,
        session_id: str,
        session: Dict[str, Any]
    ) -> Tuple[str, Any]:
        """返回首页回调"""
        data = session['data']
        data['page'] = 1
        self.session_manager.update_session(session_id, step=0, save_history=False)
        
        # 返回特殊标记，让主插件处理翻页
        return ("TRIGGER_PAGE", 1)
    
    async def _on_navigate_back(
        self,
        session_id: str,
        session: Dict[str, Any]
    ) -> Tuple[str, Any]:
        """返回上级回调"""
        current_step = session.get('step', 0)
        
        if current_step <= 0:
            return ("已经在首页了", None)
        
        # 返回搜索结果页
        self.session_manager.back_to_previous_step(session_id)
        
        data = session['data']
        page = data.get('page', 1)
        
        # 返回特殊标记，让主插件处理翻页
        return ("TRIGGER_PAGE", page)
    
    async def _on_navigate_exit(
        self,
        session_id: str,
        session: Dict[str, Any]
    ) -> Tuple[str, Any]:
        """退出会话回调"""
        self.session_manager.end_session(session_id)
        return ("✅ 已退出书籍搜索", None)
