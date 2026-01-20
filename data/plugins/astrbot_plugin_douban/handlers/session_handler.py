"""
豆瓣插件会话处理器
处理会话模式下的用户输入（序号选择）
"""
from typing import Dict, Optional, Tuple, Any
from astrbot.api import logger

# 导入通用模块
try:
    from common.navigation_handler import NavigationHandler
    from common.navigation_hint import NavigationHint
except ImportError:
    NavigationHandler = None
    NavigationHint = None
    logger.warning("[SessionHandler] 导航模块不可用")


class SessionHandler:
    """会话处理器 - 管理会话模式下的用户交互（标准化版本）"""
    
    # 会话超时时间（分钟），默认值，会被插件配置覆盖
    SESSION_TIMEOUT_MINUTES = 1
    
    def __init__(self, plugin, session_manager, douban_api=None):
        """
        初始化会话处理器
        
        Args:
            plugin: 豆瓣插件实例
            session_manager: SessionManager实例（必需）
            douban_api: DoubanAPI实例（可选）
        """
        self.plugin = plugin
        self.session_manager = session_manager
        self.douban_api = douban_api
        
        # 从插件配置中获取超时时间
        if hasattr(plugin, 'plugin_config'):
            self.SESSION_TIMEOUT_MINUTES = plugin.plugin_config.get('session_timeout', 1)
        
        # 使用通用导航处理器
        if NavigationHandler:
            self.nav_handler = NavigationHandler(self.session_manager)
            # 注册导航回调
            self.nav_handler.register_callbacks(
                on_home=self._on_navigate_home,
                on_back=self._on_navigate_back,
                on_exit=self._on_navigate_exit
            )
            logger.debug("[Douban] 使用通用 NavigationHandler")
        else:
            self.nav_handler = None
            logger.warning("[Douban] NavigationHandler 不可用，使用本地导航处理")
        
        logger.info("[Douban] SessionHandler 初始化完成")
    
    async def handle_session_message(
        self, 
        user_id: str, 
        session_id: str, 
        message: str
    ) -> Optional[Tuple[str, Any]]:
        """
        处理会话消息（用户输入的序号或导航命令）
        
        Args:
            user_id: 用户ID
            session_id: 会话ID
            message: 用户消息
            
        Returns:
            (消息文本, 键盘对象) 或 消息文本 或 None
        """
        # 使用 SessionManager 获取会话
        session = self.session_manager.get_session(session_id)
        if not session:
            return "❌ 会话已过期，请重新开始"
        
        message = message.strip()
        
        # 使用 NavigationHandler 处理导航命令
        if self.nav_handler:
            is_handled, result = await self.nav_handler.handle(session_id, message, session)
            if is_handled:
                return result
        else:
            # 降级方案：手动处理导航命令
            if message in ['0', '退出', 'q', 'Q']:
                self.session_manager.end_session(session_id)
                return "✅ 已退出豆瓣搜索"
            elif message.lower() in ['h', 'home', '首页']:
                return await self._show_search_results(session)
            elif message.lower() in ['b', 'back', '返回']:
                return await self._show_search_results(session)
        
        # 处理翻页命令
        if message.lower() in ['p', 'prev', '上页']:
            return await self._handle_prev_page(session)
        elif message.lower() in ['n', 'next', '下页']:
            return await self._handle_next_page(session)
        
        # 处理切换类型命令
        if message.lower() in ['s', 'switch', '切换']:
            return await self._handle_switch_type(session)
        
        # 处理详情页特殊操作命令
        current_step = session.get('step', 0)
        if current_step >= 1:  # 在详情页（step >= 1）
            if message.lower() in ['r', 'resource', '资源']:
                # 触发 Pansou 搜索
                data = session['data']
                title = data.get('current_detail_title', '')
                
                if title:
                    # 返回特殊标记，让主插件识别并触发 Pansou
                    return ("TRIGGER_PANSOU_SEARCH", title)
                else:
                    return "❌ 无法获取标题信息，请先查看详情"
            elif message.lower() in ['a', 'ai', '解读']:
                # 触发 AI 解读
                data = session['data']
                search_type = data.get('search_type', 'book')
                current_detail_id = data.get('current_detail_id')
                
                if current_detail_id:
                    # 返回特殊标记，让主插件识别并触发 AI 解读
                    return ("TRIGGER_AI_INTERPRET", search_type, current_detail_id)
                else:
                    return "❌ 无法获取详情信息，请先查看详情"
            elif message.lower() in ['d', 'detail', '详情']:
                # 返回豆瓣详情链接
                data = session['data']
                search_type = data.get('search_type', 'book')
                # 从当前详情中获取ID（需要在进入详情时保存）
                current_detail_id = data.get('current_detail_id')
                if current_detail_id:
                    if search_type == 'book':
                        detail_url = f"https://book.douban.com/subject/{current_detail_id}/"
                    else:
                        detail_url = f"https://movie.douban.com/subject/{current_detail_id}/"
                    return f"📖 豆瓣详情页：{detail_url}"
                else:
                    return "❌ 无法获取详情链接"
        
        # 尝试解析为序号
        try:
            index = int(message)
            data = session['data']
            results = data.get('results', [])
            
            # 相对序号逻辑：用户输入 1-15
            if 1 <= index <= len(results):
                list_index = index - 1
                selected = results[list_index]
                subject_id = selected.get('id')
                title = selected.get('title', '未知标题')
                
                # 保存当前详情信息到会话
                session['data']['current_detail_id'] = subject_id
                session['data']['current_detail_title'] = title
                
                # 获取并显示详情
                search_type = data.get('search_type', 'book')
                if search_type == "book":
                    douban_url = f"https://book.douban.com/subject/{subject_id}/"
                    data['current_detail_id'] = subject_id
                    data['current_detail_title'] = selected.get('title', '')
                    
                    # 更新步骤为1（进入详情页，一级子菜单）
                    self.session_manager.update_session(session_id, step=1)
                    
                    # 返回特殊标记，让调用方处理详情显示
                    return ("__SHOW_DETAIL__", douban_url)
                else:
                    return "❌ 无法获取详情"
            else:
                return f"❌ 请输入 {start_index}-{end_index} 之间的序号"
                
        except ValueError:
            # 不是数字，提示正确的命令
            data = session['data']
            page = data.get('page', 1)
            PAGE_SIZE = 15
            results = data.get('results', [])
            start_index = (page - 1) * PAGE_SIZE + 1
            end_index = start_index + len(results) - 1
            
            hint = NavigationHint.get_main_menu_hint() if NavigationHint else "💡 0-退出"
            return f"❌ 请输入序号 ({start_index}-{end_index}) 或导航命令 ({hint})"
    
    # ==================== 导航回调 ====================
    
    async def _on_navigate_home(self, session_id: str, session: Dict[str, Any]):
        """返回首页回调"""
        # 在搜索结果列表中，"首页"表示返回第1页
        data = session.get('data', {})
        current_page = data.get('page', 1)
        
        if current_page == 1:
            return "❌ 已经在第一页了"
        
        # 重置页码为1
        data['page'] = 1
        
        # 重新搜索第1页
        keyword = data.get('keyword', '')
        search_type = data.get('search_type', 'book')
        
        if self.douban_api:
            results, total = await self.douban_api.search_douban(keyword, search_type, 1, user_id=session_id)
            data['results'] = results
            data['total'] = total
        
        # 重置步骤为0（主菜单）
        self.session_manager.update_session(session_id, step=0, save_history=False)
        return await self._show_search_results(session)
    
    async def _on_navigate_back(self, session_id: str, session: Dict[str, Any]):
        """返回上级回调"""
        # 使用 SessionManager 的步骤历史返回上级
        previous_step = self.session_manager.back_to_previous_step(session_id)
        if previous_step is not None:
            logger.debug(f"[Douban] 返回上级 - step={previous_step}")
        return await self._show_search_results(session)
    
    async def _on_navigate_exit(self, session_id: str, session: Dict[str, Any]):
        """退出会话回调"""
        return "✅ 已退出豆瓣搜索"
    
    # ==================== 翻页处理 ====================
    
    async def _handle_prev_page(self, session: Dict) -> Tuple[str, Any]:
        """处理上一页"""
        session_id = session.get('id', '')
        data = session['data']
        current_page = data.get('page', 1)
        
        if current_page <= 1:
            return "❌ 已经是第一页了"
        
        # 更新页码
        new_page = current_page - 1
        data['page'] = new_page
        
        # 重新搜索
        keyword = data.get('keyword', '')
        search_type = data.get('search_type', 'book')
        
        # 调用插件的搜索方法
        results, total = await self.douban_api.search_douban(keyword, search_type, new_page, user_id=session_id)
        data['results'] = results
        data['total'] = total
        
        return await self._show_search_results(session)
    
    async def _handle_next_page(self, session: Dict) -> Tuple[str, Any]:
        """处理下一页"""
        session_id = session.get('id', '')
        data = session['data']
        current_page = data.get('page', 1)
        total = data.get('total', 0)
        PAGE_SIZE = 15
        total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
        
        if current_page >= total_pages:
            return "❌ 已经是最后一页了"
        
        # 更新页码
        new_page = current_page + 1
        data['page'] = new_page
        
        # 重新搜索
        keyword = data.get('keyword', '')
        search_type = data.get('search_type', 'book')
        
        # 调用插件的搜索方法
        results, total = await self.douban_api.search_douban(keyword, search_type, new_page, user_id=session_id)
        data['results'] = results
        data['total'] = total
        
        return await self._show_search_results(session)
    
    async def _handle_switch_type(self, session: Dict) -> Tuple[str, Any]:
        """处理切换搜索类型"""
        session_id = session.get('id', '')
        data = session['data']
        current_type = data.get('search_type', 'book')
        keyword = data.get('keyword', '')
        
        # 切换类型
        new_type = 'movie' if current_type == 'book' else 'book'
        type_name = '电影' if new_type == 'movie' else '图书'
        
        # 重新搜索
        results, total = await self.douban_api.search_douban(keyword, new_type, 1, user_id=session_id)
        
        # 更新会话数据
        data['search_type'] = new_type
        data['page'] = 1
        data['results'] = results
        data['total'] = total
        
        return await self._show_search_results(session)
    
    # ==================== 搜索结果显示 ====================
    
    async def _show_search_results(self, session: Dict) -> Tuple[str, Any]:
        """重新显示搜索结果"""
        data = session['data']
        
        from .response_builder import DoubanResponseBuilder
        from .formatter import DoubanFormatter
        
        builder = DoubanResponseBuilder(session['capabilities'])
        
        # 格式化搜索结果
        PAGE_SIZE = 15  # 每页显示数量
        results = data.get('results', [])
        search_type = data.get('search_type', 'book')
        page = data.get('page', 1)
        total = data.get('total', 0)
        keyword = data.get('keyword', '')
        
        # 检查是否为按钮模式
        capabilities = session.get('capabilities', {})
        is_button_mode = capabilities.get('supports_buttons', False)
        
        # 根据当前搜索类型生成切换提示
        switch_hint = None
        if not is_button_mode:  # 只在会话模式下显示切换提示
            if search_type == 'book':
                switch_hint = "s-搜电影"
            else:
                switch_hint = "s-搜图书"
        
        message, _ = DoubanFormatter.format_search_results(
            results, search_type, page, PAGE_SIZE, total,
            show_pagination=True,
            timeout_minutes=self.SESSION_TIMEOUT_MINUTES,
            show_hints=not is_button_mode,  # 按钮模式不显示导航文本
            switch_hint=switch_hint  # 传入切换提示
        )
        
        # 构建响应
        return builder.build_search_results(
            message=message,
            search_type=search_type,
            keyword=keyword,
            page=page,
            total_pages=(total + PAGE_SIZE - 1) // PAGE_SIZE,
            results=results
        )
