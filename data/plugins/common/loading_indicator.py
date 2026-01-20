"""
统一加载状态提示模块
提供跨平台的加载状态指示
"""
from typing import Optional
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain


class LoadingIndicator:
    """统一的加载状态指示器，支持上下文管理器"""
    
    def __init__(self, event: AstrMessageEvent, action_type: str = 'process', custom_message: Optional[str] = None):
        """
        初始化加载指示器（用于上下文管理器模式）
        
        Args:
            event: 消息事件
            action_type: 操作类型
            custom_message: 自定义消息
        """
        self._event = event
        self._action_type = action_type
        self._custom_message = custom_message
        self._message_id: Optional[str] = None
    
    async def __aenter__(self):
        """进入上下文时显示加载提示"""
        self._message_id = await LoadingIndicator.show(self._event, self._action_type, self._custom_message)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时隐藏加载提示"""
        await LoadingIndicator.hide(self._event, self._message_id)
        return False
    
    # 加载消息模板
    MESSAGES = {
        'search': '🔍 正在搜索...',
        'fetch': '📥 正在获取数据...',
        'get_detail': '📄 正在获取详情...',
        'get_lyric': '🎵 正在获取歌词...',
        'process': '⚙️ 正在处理...',
        'generate': '✨ 正在生成...',
        'upload': '📤 正在上传...',
        'download': '📥 正在下载...',
        'save': '💾 正在保存...',
        'delete': '🗑️ 正在删除...',
        'update': '🔄 正在更新...',
        'calculate': '🧮 正在计算...',
        'ai_interpret': '🤖 正在为您解读...',
        'sending_file': '📚 文件发送中...',
    }
    
    # 支持加载提示的平台列表
    SUPPORTED_PLATFORMS = ["telegram", "lark"]
    
    @staticmethod
    async def show(
        event: AstrMessageEvent, 
        action_type: str = 'process',
        custom_message: Optional[str] = None
    ) -> Optional[str]:
        """
        显示加载提示
        
        Args:
            event: 消息事件
            action_type: 操作类型
            custom_message: 自定义消息（优先级高于预设消息）
            
        Returns:
            消息ID（用于后续删除）
        """
        message = custom_message or LoadingIndicator.MESSAGES.get(action_type, '⏳ 请稍候...')
        platform_name = (event.get_platform_name() or "").lower()
        
        # 检查平台是否支持（避免消息堆积）
        if platform_name not in LoadingIndicator.SUPPORTED_PLATFORMS:
            logger.debug(f"[LoadingIndicator] 平台 {platform_name} 不支持加载提示")
            return None
        
        try:
            # 使用统一的 send() 方法发送消息
            result = await event.send(MessageChain([Plain(message)]))
            if result and result.message_id:
                logger.debug(f"[LoadingIndicator] 加载提示已发送，消息ID: {result.message_id}")
                return result.message_id
            return None
                
        except Exception as e:
            logger.debug(f"[LoadingIndicator] 显示加载提示失败: {e}")
            return None
    
    @staticmethod
    async def hide(event: AstrMessageEvent, message_id: Optional[str]):
        """
        隐藏加载提示
        
        Args:
            event: 消息事件
            message_id: 消息ID
        """
        if not message_id:
            return
        
        try:
            # 使用统一的 delete_message 方法
            if hasattr(event, 'delete_message'):
                # Telegram 需要 int 类型的 message_id
                platform_name = (event.get_platform_name() or "").lower()
                if platform_name == "telegram":
                    await event.delete_message(int(message_id))
                else:
                    await event.delete_message(message_id)
                logger.debug(f"[LoadingIndicator] 加载提示已删除，消息ID: {message_id}")
                
        except Exception as e:
            logger.debug(f"[LoadingIndicator] 隐藏加载提示失败: {e}")
    
    @staticmethod
    async def send_typing(event: AstrMessageEvent) -> bool:
        """
        发送"正在输入"状态（仅 Telegram 支持）
        
        这是一个轻量级的加载指示，不会发送实际消息，
        适用于按钮模式下的快速操作（如翻页、换源）
        
        Args:
            event: 消息事件
            
        Returns:
            是否成功发送
        """
        platform_name = (event.get_platform_name() or "").lower()
        
        if platform_name != "telegram":
            return False
        
        try:
            # 获取 chat_id
            chat_id = getattr(event.message_obj, 'group_id', None) or event.get_sender_id()
            
            # 通过 client 发送 typing 状态
            if hasattr(event, 'client') and hasattr(event.client, 'send_chat_action'):
                await event.client.send_chat_action(chat_id=chat_id, action="typing")
                logger.debug(f"[LoadingIndicator] 已发送 typing 状态")
                return True
            
        except Exception as e:
            logger.debug(f"[LoadingIndicator] 发送 typing 状态失败: {e}")
        
        return False
