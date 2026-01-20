"""
音乐搜索会话处理器
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
    logger.warning("[MusicSession] 导航模块不可用")

from .music_formatter import MusicFormatter


class MusicSessionHandler:
    """音乐搜索会话处理器"""
    
    # 会话超时时间（分钟）
    SESSION_TIMEOUT_MINUTES = 1
    
    # 可切换的平台列表
    SWITCHABLE_PLATFORMS = ["qq", "netease"]
    
    def __init__(self, session_manager, music_api):
        """
        初始化会话处理器
        
        Args:
            session_manager: 会话管理器
            music_api: 音乐API客户端
        """
        self.session_manager = session_manager
        self.music_api = music_api
        
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
            if message.lower() in ['l', 'lyric', '歌词']:
                # 返回特殊标记，让主插件处理歌词显示
                current_song_id = data.get('current_song_id', '')
                current_platform = data.get('platform', 'qq')
                if current_song_id:
                    return ("SHOW_LYRIC", current_song_id, current_platform)
                return ("❌ 无法获取歌曲信息", None)
        
        # 处理数字选择
        if message.isdigit():
            index = int(message)
            if current_step == 0:
                # 在搜索结果页，选择查看详情
                return await self._handle_select_song(session_id, session, index)
            elif current_step == 1:
                # 在详情页，选择下载音质
                return await self._handle_select_quality(session_id, session, index)
        
        return None
    
    async def _handle_prev_page(
        self,
        session_id: str,
        session: Dict[str, Any]
    ) -> Tuple[str, Any]:
        """处理上一页"""
        data = session['data']
        page = data.get('page', 1)
        
        if page <= 1:
            return ("已经是第一页了", None)
        
        new_page = page - 1
        return await self._refresh_search(session_id, session, new_page)
    
    async def _handle_next_page(
        self,
        session_id: str,
        session: Dict[str, Any]
    ) -> Tuple[str, Any]:
        """处理下一页"""
        data = session['data']
        page = data.get('page', 1)
        total = data.get('total', 0)
        page_size = data.get('page_size', 16)
        total_pages = max(1, (total + page_size - 1) // page_size)
        
        if page >= total_pages:
            return ("已经是最后一页了", None)
        
        new_page = page + 1
        return await self._refresh_search(session_id, session, new_page)
    
    async def _handle_switch_source(
        self,
        session_id: str,
        session: Dict[str, Any]
    ) -> Tuple[str, Any]:
        """处理换源"""
        data = session['data']
        current_platform = data.get('platform', 'qq')
        
        # 切换到下一个平台
        try:
            current_index = self.SWITCHABLE_PLATFORMS.index(current_platform)
            next_index = (current_index + 1) % len(self.SWITCHABLE_PLATFORMS)
            new_platform = self.SWITCHABLE_PLATFORMS[next_index]
        except ValueError:
            new_platform = 'qq'
        
        # 重新搜索
        keyword = data.get('keyword', '')
        page_size = data.get('page_size', 16)
        
        result = await self.music_api.search(
            keyword=keyword,
            platform=new_platform,
            page=1,
            limit=page_size
        )
        
        songs = result.get("songs", [])
        total = result.get("total", 0)
        
        # 更新会话数据
        data['platform'] = new_platform
        data['page'] = 1
        data['results'] = songs
        data['total'] = total
        
        return await self._show_search_results(session)
    
    async def _handle_select_song(
        self,
        session_id: str,
        session: Dict[str, Any],
        index: int
    ) -> Tuple[Any, Any]:
        """处理选择歌曲"""
        data = session['data']
        results = data.get('results', [])
        
        if index < 1 or index > len(results):
            return (f"❌ 无效的序号，请输入 1-{len(results)} 之间的数字", None)
        
        song = results[index - 1]
        song_id = str(song.get('id', ''))
        platform = data.get('platform', 'qq')
        
        if not song_id:
            return ("❌ 该歌曲无法查看详情", None)
        
        # 保存当前选择的歌曲信息
        data['current_song_id'] = song_id
        data['current_song'] = song
        self.session_manager.update_session(session_id, step=1, data=data)
        
        # 返回特殊标记，让主插件处理详情显示
        return ("SHOW_SONG_DETAIL", song_id, platform)
    
    async def _handle_select_quality(
        self,
        session_id: str,
        session: Dict[str, Any],
        index: int
    ) -> Tuple[Any, Any]:
        """处理选择音质下载"""
        data = session['data']
        available_qualities = data.get('available_qualities', ["128", "320", "flac"])
        
        if index < 1 or index > len(available_qualities):
            return (f"❌ 无效的序号，请输入 1-{len(available_qualities)} 之间的数字", None)
        
        quality = available_qualities[index - 1]
        song_id = data.get('current_song_id', '')
        platform = data.get('platform', 'qq')
        
        if not song_id:
            return ("❌ 无法获取歌曲信息", None)
        
        # 返回特殊标记，让主插件处理下载
        return ("TRIGGER_DOWNLOAD", song_id, platform, quality)
    
    async def _refresh_search(
        self,
        session_id: str,
        session: Dict[str, Any],
        page: int
    ) -> Tuple[str, Any]:
        """刷新搜索结果"""
        data = session['data']
        keyword = data.get('keyword', '')
        platform = data.get('platform', 'qq')
        page_size = data.get('page_size', 16)
        
        # 执行搜索
        result = await self.music_api.search(
            keyword=keyword,
            platform=platform,
            page=page,
            limit=page_size
        )
        
        songs = result.get("songs", [])
        total = result.get("total", 0)
        
        # 更新会话数据
        data['page'] = page
        data['results'] = songs
        data['total'] = total
        
        return await self._show_search_results(session)
    
    async def _show_search_results(self, session: Dict[str, Any]) -> Tuple[str, Any]:
        """显示搜索结果"""
        data = session['data']
        songs = data.get('results', [])
        page = data.get('page', 1)
        page_size = data.get('page_size', 16)
        total = data.get('total', 0)
        platform = data.get('platform', 'qq')
        keyword = data.get('keyword', '')
        
        # 格式化结果
        message, _ = MusicFormatter.format_search_results(
            songs=songs,
            page=page,
            page_size=page_size,
            total=total,
            platform=platform,
            keyword=keyword,
            show_hints=True,
            timeout_minutes=self.SESSION_TIMEOUT_MINUTES
        )
        
        return (message, None)
    
    async def _on_navigate_home(
        self,
        session_id: str,
        session: Dict[str, Any]
    ) -> Tuple[str, Any]:
        """返回首页回调"""
        data = session['data']
        data['page'] = 1
        self.session_manager.update_session(session_id, step=0, save_history=False)
        
        return await self._refresh_search(session_id, session, 1)
    
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
        
        return await self._refresh_search(session_id, session, page)
    
    async def _on_navigate_exit(
        self,
        session_id: str,
        session: Dict[str, Any]
    ) -> Tuple[str, Any]:
        """退出会话回调"""
        self.session_manager.end_session(session_id)
        return ("✅ 已退出音乐搜索", None)
