"""
会话处理器模块
负责处理会话模式下的用户交互
"""
from typing import Dict, Optional, Tuple, Any
from astrbot.api import logger
from .pansou_api import PansouAPI
from .formatter import PansouFormatter
from .response_builder import PansouResponseBuilder


class SessionHandler:
    """会话处理器"""
    
    def __init__(self, session_manager, pansou_api: PansouAPI):
        """
        初始化会话处理器
        
        Args:
            session_manager: 会话管理器
            pansou_api: 盘搜API实例
        """
        self.session_manager = session_manager
        self.pansou_api = pansou_api
        self.SESSION_TIMEOUT_MINUTES = 1
        self.PAGE_SIZE = 15
        
        # 注册导航处理器
        try:
            from common.navigation_handler import NavigationHandler
            self.nav_handler = NavigationHandler(session_manager)
            self._register_navigation_callbacks()
        except ImportError:
            logger.warning("[Pansou] NavigationHandler 不可用，使用降级方案")
            self.nav_handler = None
    
    def _register_navigation_callbacks(self):
        """注册导航回调"""
        if not self.nav_handler:
            return
        
        # 返回首页
        async def on_home(session_id: str, session: Dict) -> Tuple[str, Any]:
            return await self._show_search_results(session)
        
        # 返回上级（同返回首页）
        async def on_back(session_id: str, session: Dict) -> Tuple[str, Any]:
            return await self._show_search_results(session)
        
        # 退出会话
        async def on_exit(session_id: str, session: Dict) -> str:
            self.session_manager.end_session(session_id)
            return "✅ 已退出资源搜索"
        
        self.nav_handler.register_callbacks(
            on_home=on_home,
            on_back=on_back,
            on_exit=on_exit
        )
    
    async def handle_session_message(
        self,
        user_id: str,
        session_id: str,
        message: str
    ) -> Optional[Tuple[str, Any]]:
        """
        处理会话消息
        
        Args:
            user_id: 用户ID
            session_id: 会话ID
            message: 用户消息
            
        Returns:
            响应消息或None
        """
        session = self.session_manager.get_session(session_id)
        if not session:
            return "❌ 会话已过期，请重新搜索"
        
        message = message.strip()
        
        # 使用导航处理器处理标准导航命令
        if self.nav_handler:
            is_handled, result = await self.nav_handler.handle(session_id, message, session)
            if is_handled:
                return result
        else:
            # 降级方案：手动处理导航命令
            if message in ['0', '退出', 'q', 'Q']:
                self.session_manager.end_session(session_id)
                return "✅ 已退出资源搜索"
            elif message.lower() in ['h', 'home', '首页']:
                return await self._show_search_results(session)
            elif message.lower() in ['b', 'back', '返回']:
                return await self._show_search_results(session)
        
        # 处理翻页命令
        if message.lower() in ['p', 'prev', '上页']:
            data = session['data']
            page = data.get('page', 1)
            if page <= 1:
                return ("❌ 已经是第一页了", None)
            return ("TRIGGER_PAGE", page - 1)
        elif message.lower() in ['n', 'next', '下页']:
            data = session['data']
            page = data.get('page', 1)
            total = data.get('total', 0)
            total_pages = (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE
            if page >= total_pages:
                return ("❌ 已经是最后一页了", None)
            return ("TRIGGER_PAGE", page + 1)
        
        # 处理云盘筛选命令（直接输入网盘关键字）
        cloud_type_map = {
            '百度': 'baidu', 'bd': 'baidu', 'baidu': 'baidu',
            '阿里': 'aliyun', 'al': 'aliyun', 'aliyun': 'aliyun',
            '夸克': 'quark', 'qk': 'quark', 'quark': 'quark',
            '天翼': 'tianyi', 'ty': 'tianyi', 'tianyi': 'tianyi',
            'uc': 'uc',
            '115': '115',
            'pikpak': 'pikpak', 'pk': 'pikpak',
            '迅雷': 'xunlei', 'xl': 'xunlei', 'xunlei': 'xunlei',
            '123': '123',
            '全部': '', 'all': '', 'qb': ''
        }
        
        cloud_type = cloud_type_map.get(message.lower())
        if cloud_type is not None:
            return ("TRIGGER_FILTER", cloud_type)
        
        # 其他输入提示
        return "❌ 请使用导航命令：p-上页 | n-下页 | h-首页 | bd-百度/al-阿里/qk-夸克/ty-天翼/uc/115/pk-PikPak/xl-迅雷/123/all-全部 | 0-退出"
    
    async def execute_page(self, session_id: str, new_page: int) -> Tuple[str, Any]:
        """执行翻页操作（供 main.py 调用）"""
        session = self.session_manager.get_session(session_id)
        if not session:
            return ("❌ 会话已过期，请重新搜索", None)
        
        data = session['data']
        keyword = data.get('keyword', '')
        cloud_types = data.get('cloud_types')
        
        # 会话模式下，如果没有指定云盘类型，则排除 magnet 和 ed2k
        search_cloud_types = cloud_types
        if not cloud_types:
            search_cloud_types = "baidu,aliyun,quark,tianyi,uc,115,pikpak,xunlei,123"
        
        # 搜索指定页
        results, total = await self.pansou_api.search(
            keyword=keyword,
            cloud_types=search_cloud_types,
            page=new_page,
            page_size=self.PAGE_SIZE
        )
        
        # 更新会话数据
        data['page'] = new_page
        data['results'] = results
        data['total'] = total
        
        return await self._show_search_results(session)
    
    async def execute_filter(self, session_id: str, cloud_type: str) -> Tuple[str, Any]:
        """执行筛选操作（供 main.py 调用）"""
        session = self.session_manager.get_session(session_id)
        if not session:
            return ("❌ 会话已过期，请重新搜索", None)
        
        data = session['data']
        keyword = data.get('keyword', '')
        
        # 更新筛选条件
        data['cloud_types'] = cloud_type if cloud_type else None
        
        # 会话模式下，如果选择"全部"（cloud_type为空），则排除 magnet 和 ed2k
        search_cloud_types = cloud_type
        if not cloud_type:
            search_cloud_types = "baidu,aliyun,quark,tianyi,uc,115,pikpak,xunlei,123"
        
        # 重新搜索第一页
        results, total = await self.pansou_api.search(
            keyword=keyword,
            cloud_types=search_cloud_types,
            page=1,
            page_size=self.PAGE_SIZE
        )
        
        # 更新会话数据
        data['page'] = 1
        data['results'] = results
        data['total'] = total
        
        return await self._show_search_results(session)
    
    async def _handle_prev_page(self, session: Dict) -> Tuple[str, Any]:
        """处理上一页"""
        data = session['data']
        page = data.get('page', 1)
        
        if page <= 1:
            return "❌ 已经是第一页了"
        
        keyword = data.get('keyword', '')
        cloud_types = data.get('cloud_types')
        
        # 会话模式下，如果没有指定云盘类型，则排除 magnet 和 ed2k
        search_cloud_types = cloud_types
        if not cloud_types:
            search_cloud_types = "baidu,aliyun,quark,tianyi,uc,115,pikpak,xunlei,123"
        
        # 搜索上一页
        results, total = await self.pansou_api.search(
            keyword=keyword,
            cloud_types=search_cloud_types,
            page=page - 1,
            page_size=self.PAGE_SIZE
        )
        
        # 更新会话数据
        data['page'] = page - 1
        data['results'] = results
        data['total'] = total
        
        return await self._show_search_results(session)
    
    async def _handle_next_page(self, session: Dict) -> Tuple[str, Any]:
        """处理下一页"""
        data = session['data']
        page = data.get('page', 1)
        total = data.get('total', 0)
        total_pages = (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE
        
        if page >= total_pages:
            return "❌ 已经是最后一页了"
        
        keyword = data.get('keyword', '')
        cloud_types = data.get('cloud_types')
        
        # 会话模式下，如果没有指定云盘类型，则排除 magnet 和 ed2k
        search_cloud_types = cloud_types
        if not cloud_types:
            search_cloud_types = "baidu,aliyun,quark,tianyi,uc,115,pikpak,xunlei,123"
        
        # 搜索下一页
        results, total = await self.pansou_api.search(
            keyword=keyword,
            cloud_types=search_cloud_types,
            page=page + 1,
            page_size=self.PAGE_SIZE
        )
        
        # 更新会话数据
        data['page'] = page + 1
        data['results'] = results
        data['total'] = total
        
        return await self._show_search_results(session)
    
    async def _apply_filter(self, session: Dict, cloud_type: str) -> Tuple[str, Any]:
        """应用云盘筛选"""
        data = session['data']
        keyword = data.get('keyword', '')
        
        # 更新筛选条件
        data['cloud_types'] = cloud_type if cloud_type else None
        
        # 会话模式下，如果选择"全部"（cloud_type为空），则排除 magnet 和 ed2k
        search_cloud_types = cloud_type
        if not cloud_type:
            search_cloud_types = "baidu,aliyun,quark,tianyi,uc,115,pikpak,xunlei,123"
        
        # 重新搜索第一页
        results, total = await self.pansou_api.search(
            keyword=keyword,
            cloud_types=search_cloud_types,
            page=1,
            page_size=self.PAGE_SIZE
        )
        
        # 更新会话数据
        data['page'] = 1
        data['results'] = results
        data['total'] = total
        
        return await self._show_search_results(session)
    
    async def _show_search_results(self, session: Dict) -> Tuple[str, Any]:
        """显示搜索结果"""
        data = session['data']
        results = data.get('results', [])
        keyword = data.get('keyword', '')
        page = data.get('page', 1)
        total = data.get('total', 0)
        cloud_types = data.get('cloud_types')
        
        # 检查是否为按钮模式
        capabilities = session.get('capabilities', {})
        is_button_mode = capabilities.get('supports_buttons', False)
        
        # 根据当前状态生成筛选提示
        filter_hint = None
        if not is_button_mode:
            # 显示云盘筛选关键字
            if cloud_types:
                # 判断是否是默认的完整列表（视为"全部"）
                default_types = "baidu,aliyun,quark,tianyi,uc,mobile,115,pikpak,xunlei,123"
                if cloud_types == default_types:
                    # 默认全部云盘
                    filter_hint = "当前:全部 | bd-百度/al-阿里/qk-夸克/ty-天翼/uc/115/pk-PikPak/xl-迅雷/123/all-全部"
                else:
                    # 单个云盘筛选
                    cloud_name_map = {
                        'baidu': '百度',
                        'aliyun': '阿里',
                        'quark': '夸克',
                        'tianyi': '天翼',
                        'uc': 'UC',
                        '115': '115',
                        'pikpak': 'PK',
                        'xunlei': '迅雷',
                        '123': '123',
                        'magnet': '磁力',
                        'ed2k': 'ED2K'
                    }
                    current_name = cloud_name_map.get(cloud_types, cloud_types)
                    filter_hint = f"当前:{current_name} | bd-百度/al-阿里/qk-夸克/ty-天翼/uc/115/pk-PikPak/xl-迅雷/123/all-全部"
            else:
                filter_hint = "bd-百度/al-阿里/qk-夸克/ty-天翼/uc/115/pk-PikPak/xl-迅雷/123"
        
        message, _ = PansouFormatter.format_search_results(
            results, keyword, page, self.PAGE_SIZE, total,
            show_pagination=True,
            timeout_minutes=self.SESSION_TIMEOUT_MINUTES,
            show_hints=not is_button_mode,
            filter_hint=filter_hint
        )
        
        # 构建响应
        builder = PansouResponseBuilder(capabilities)
        final_message, keyboard = builder.build_search_results(
            message=message,
            keyword=keyword,
            page=page,
            total_pages=(total + self.PAGE_SIZE - 1) // self.PAGE_SIZE,
            results=results,
            cloud_types=cloud_types
        )
        
        return final_message, keyboard
