"""
跨平台消息推送引擎

功能：
1. 统一消息推送 - 支持 Telegram/QQ/飞书等多平台
2. 批量推送 - 支持向多用户批量发送消息
3. 失败重试 - 自动重试失败的推送
4. 推送限流 - 避免触发平台限制
5. 推送日志 - 记录推送历史和状态
6. 推送队列 - 异步队列处理大量推送任务

使用示例：
    from common import get_message_pusher
    
    pusher = get_message_pusher()
    
    # 单条推送
    success = await pusher.send_private_message(
        user_id="telegram:123456",
        message="Hello!",
        context=context
    )
    
    # 批量推送（带重试）
    results = await pusher.batch_push(
        user_ids=["telegram:123", "qq:456"],
        message="通知内容",
        context=context,
        max_retries=3
    )
    
    # 使用推送队列（适合大量推送）
    await pusher.queue_push(
        user_id="telegram:123",
        message="排队消息",
        context=context
    )
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from enum import Enum
import traceback

# 使用标准 logging 避免依赖问题
logger = logging.getLogger(__name__)


class PushStatus(Enum):
    """推送状态枚举"""
    PENDING = "pending"      # 等待推送
    SENDING = "sending"      # 正在发送
    SUCCESS = "success"      # 发送成功
    FAILED = "failed"        # 发送失败
    RETRY = "retry"          # 等待重试
    CANCELLED = "cancelled"  # 已取消


@dataclass
class PushTask:
    """推送任务数据类"""
    task_id: str
    user_id: str
    message: str
    context: Any = None
    keyboard: Any = None
    push_type: str = "private"  # private/group/broadcast
    priority: int = 0           # 优先级（数字越大优先级越高）
    max_retries: int = 3
    retry_count: int = 0
    retry_delay: int = 5        # 重试间隔（秒）
    status: PushStatus = PushStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    sent_at: Optional[datetime] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'task_id': self.task_id,
            'user_id': self.user_id,
            'message': self.message[:100] + '...' if len(self.message) > 100 else self.message,
            'push_type': self.push_type,
            'priority': self.priority,
            'max_retries': self.max_retries,
            'retry_count': self.retry_count,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'error_message': self.error_message
        }


@dataclass
class PushResult:
    """推送结果数据类"""
    user_id: str
    success: bool
    message_id: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    duration_ms: int = 0


class PushRateLimiter:
    """推送限流器 - 避免触发平台限制"""
    
    # 各平台默认限流配置（每秒最大请求数）
    DEFAULT_LIMITS = {
        'telegram': 30,   # Telegram 限制约 30 msg/s
        'qq': 20,         # QQ 保守估计
        'lark': 50,       # 飞书限制较宽松
        'default': 10     # 默认限制
    }
    
    def __init__(self):
        self._last_send_time: Dict[str, datetime] = {}
        self._send_counts: Dict[str, int] = {}
        self._window_start: Dict[str, datetime] = {}
    
    def get_limit(self, platform: str) -> int:
        """获取平台限流值"""
        return self.DEFAULT_LIMITS.get(platform, self.DEFAULT_LIMITS['default'])
    
    async def wait_if_needed(self, platform: str):
        """如果需要，等待以满足限流要求"""
        now = datetime.now()
        limit = self.get_limit(platform)
        
        # 检查时间窗口
        window_start = self._window_start.get(platform)
        if window_start is None or (now - window_start).total_seconds() >= 1:
            # 新的时间窗口
            self._window_start[platform] = now
            self._send_counts[platform] = 0
        
        # 检查是否超过限制
        current_count = self._send_counts.get(platform, 0)
        if current_count >= limit:
            # 等待到下一个时间窗口
            wait_time = 1 - (now - self._window_start[platform]).total_seconds()
            if wait_time > 0:
                logger.debug(f"[PushRateLimiter] {platform} 达到限流，等待 {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
            self._window_start[platform] = datetime.now()
            self._send_counts[platform] = 0
        
        # 更新计数
        self._send_counts[platform] = self._send_counts.get(platform, 0) + 1


class MessagePusher:
    """
    跨平台消息推送引擎
    
    功能：
    - 统一消息推送接口
    - 批量推送支持
    - 失败自动重试
    - 推送限流
    - 推送队列
    - 推送日志
    """
    
    def __init__(self, db=None):
        """
        初始化推送引擎
        
        Args:
            db: 数据库管理器（可选，用于持久化推送日志）
        """
        self.db = db
        self._rate_limiter = PushRateLimiter()
        self._queue: asyncio.Queue = None
        self._queue_worker_task: asyncio.Task = None
        self._context = None  # 全局上下文
        self._task_counter = 0
        
        # 统计数据
        self._stats = {
            'total_sent': 0,
            'total_success': 0,
            'total_failed': 0,
            'total_retries': 0
        }
        
        # 初始化数据库表
        if self.db:
            self._init_db_tables()
    
    def _init_db_tables(self):
        """初始化推送日志表"""
        try:
            self.db.execute_write("""
                CREATE TABLE IF NOT EXISTS push_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    user_id TEXT NOT NULL,
                    push_type TEXT DEFAULT 'private',
                    message_preview TEXT,
                    status TEXT NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    created_at DATETIME NOT NULL,
                    sent_at DATETIME,
                    duration_ms INTEGER
                )
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_push_logs_user 
                ON push_logs(user_id)
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_push_logs_status 
                ON push_logs(status)
            """)
            self.db.execute_write("""
                CREATE INDEX IF NOT EXISTS idx_push_logs_created 
                ON push_logs(created_at)
            """)
            logger.debug("[MessagePusher] 推送日志表初始化完成")
        except Exception as e:
            logger.error(f"[MessagePusher] 初始化推送日志表失败: {e}")
    
    def set_context(self, context: Any):
        """设置全局上下文"""
        self._context = context
    
    def _generate_task_id(self) -> str:
        """生成任务ID"""
        self._task_counter += 1
        return f"push_{datetime.now().strftime('%Y%m%d%H%M%S')}_{self._task_counter}"
    
    def _log_push(self, task: PushTask, result: PushResult):
        """记录推送日志"""
        if not self.db:
            return
        
        try:
            self.db.execute_write("""
                INSERT INTO push_logs 
                (task_id, user_id, push_type, message_preview, status, retry_count, 
                 error_message, created_at, sent_at, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.task_id,
                task.user_id,
                task.push_type,
                task.message[:200] if task.message else None,
                'success' if result.success else 'failed',
                result.retry_count,
                result.error_message,
                task.created_at,
                datetime.now() if result.success else None,
                result.duration_ms
            ))
        except Exception as e:
            logger.error(f"[MessagePusher] 记录推送日志失败: {e}")
    
    async def send_private_message(
        self,
        user_id: str,
        message: str,
        context: Optional[Any] = None,
        keyboard: Optional[Any] = None,
        max_retries: int = 0,
        with_rate_limit: bool = True
    ) -> bool:
        """
        向指定用户发送私信
        
        Args:
            user_id: 统一用户ID (格式: platform:raw_id)
            message: 消息内容
            context: 上下文对象（用于获取平台客户端）
            keyboard: 可选的键盘
            max_retries: 最大重试次数（0表示不重试）
            with_rate_limit: 是否启用限流
            
        Returns:
            是否发送成功
        """
        ctx = context or self._context
        
        try:
            # 解析用户ID
            if ':' not in user_id:
                logger.warning(f"[MessagePusher] 无效的用户ID格式: {user_id}")
                return False
            
            platform, raw_id = user_id.split(':', 1)
            
            # 限流等待
            if with_rate_limit:
                await self._rate_limiter.wait_if_needed(platform)
            
            # 根据平台发送消息
            success = False
            retry_count = 0
            last_error = None
            
            while retry_count <= max_retries:
                try:
                    if platform == "telegram":
                        success = await self._send_telegram_message(raw_id, message, ctx, keyboard)
                    elif platform == "qq":
                        success = await self._send_qq_message(raw_id, message, ctx, keyboard)
                    elif platform == "lark":
                        success = await self._send_lark_message(raw_id, message, ctx, keyboard)
                    else:
                        logger.warning(f"[MessagePusher] 不支持的平台: {platform}")
                        return False
                    
                    if success:
                        self._stats['total_success'] += 1
                        break
                    else:
                        raise Exception("发送返回失败")
                        
                except Exception as e:
                    last_error = str(e)
                    retry_count += 1
                    self._stats['total_retries'] += 1
                    
                    if retry_count <= max_retries:
                        wait_time = min(5 * retry_count, 30)  # 指数退避，最多30秒
                        logger.warning(f"[MessagePusher] 发送失败，{wait_time}秒后重试 ({retry_count}/{max_retries}): {e}")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"[MessagePusher] 发送失败，已达最大重试次数: {e}")
                        self._stats['total_failed'] += 1
            
            self._stats['total_sent'] += 1
            return success
                
        except Exception as e:
            logger.error(f"[MessagePusher] 发送私信失败: {e}")
            self._stats['total_failed'] += 1
            return False
    
    @staticmethod
    async def _send_telegram_message(
        chat_id: str,
        message: str,
        context: Optional[Any] = None,
        keyboard: Optional[Any] = None
    ) -> bool:
        """发送 Telegram 私信"""
        try:
            client = None
            
            # 方式1: 从事件上下文获取客户端
            if context and hasattr(context, 'client'):
                # 检查是否是 Telegram 客户端
                if hasattr(context.client, 'send_message'):
                    client = context.client
            
            # 方式2: 从插件 context 获取平台管理器
            if not client and context:
                # 尝试从 context 获取 platform_manager
                platform_manager = None
                if hasattr(context, 'platform_manager'):
                    platform_manager = context.platform_manager
                elif hasattr(context, 'context') and hasattr(context.context, 'platform_manager'):
                    platform_manager = context.context.platform_manager
                
                if platform_manager and hasattr(platform_manager, 'platform_insts'):
                    for platform in platform_manager.platform_insts:
                        meta = platform.meta()
                        if meta and 'telegram' in meta.name.lower():
                            # 获取 Telegram 平台的客户端
                            if hasattr(platform, 'client'):
                                client = platform.client
                                break
                            elif hasattr(platform, 'bot'):
                                client = platform.bot
                                break
            
            if not client:
                logger.warning(f"[MessagePusher] Telegram 缺少客户端上下文, context类型: {type(context).__name__ if context else 'None'}")
                return False
            
            if not hasattr(client, 'send_message'):
                logger.warning(f"[MessagePusher] Telegram 客户端不支持发送消息")
                return False
            
            # 转换键盘格式
            reply_markup = None
            if keyboard and hasattr(keyboard, 'buttons'):
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                
                tg_keyboard_buttons = []
                for row in keyboard.buttons:
                    tg_row = [
                        InlineKeyboardButton(text=btn['text'], callback_data=btn.get('callback_data', ''))
                        if 'callback_data' in btn
                        else InlineKeyboardButton(text=btn['text'], url=btn.get('url', ''))
                        for btn in row
                    ]
                    tg_keyboard_buttons.append(tg_row)
                reply_markup = InlineKeyboardMarkup(tg_keyboard_buttons)
            
            # 发送消息
            await client.send_message(
                chat_id=int(chat_id),
                text=message,
                reply_markup=reply_markup
            )
            
            logger.debug(f"[MessagePusher] Telegram 消息发送成功: {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"[MessagePusher] Telegram 消息发送失败: {e}")
            return False
    
    @staticmethod
    async def _send_qq_message(
        user_id: str,
        message: str,
        context: Optional[Any] = None,
        keyboard: Optional[Any] = None
    ) -> bool:
        """发送 QQ 私信"""
        try:
            # QQ 平台的私信发送实现
            # 这里需要根据实际的 QQ 平台实现来调整
            logger.debug(f"[MessagePusher] QQ 私信发送 (TODO): {user_id}")
            return False  # 暂未实现
            
        except Exception as e:
            logger.error(f"[MessagePusher] QQ 消息发送失败: {e}")
            return False
    
    @staticmethod
    async def _send_lark_message(
        user_id: str,
        message: str,
        context: Optional[Any] = None,
        keyboard: Optional[Any] = None
    ) -> bool:
        """发送飞书私信"""
        try:
            client = None
            
            # 方式1: 从事件上下文获取客户端
            if context and hasattr(context, 'client'):
                # 检查是否是飞书客户端
                if hasattr(context.client, 'send_message'):
                    client = context.client
            
            # 方式2: 从插件 context 获取平台管理器
            if not client and context:
                # 尝试从 context 获取 platform_manager
                platform_manager = None
                if hasattr(context, 'platform_manager'):
                    platform_manager = context.platform_manager
                elif hasattr(context, 'context') and hasattr(context.context, 'platform_manager'):
                    platform_manager = context.context.platform_manager
                
                if platform_manager and hasattr(platform_manager, 'platform_insts'):
                    for platform in platform_manager.platform_insts:
                        meta = platform.meta()
                        if meta and ('lark' in meta.name.lower() or 'feishu' in meta.name.lower()):
                            logger.debug(f"[MessagePusher] 找到飞书平台: {meta.name}")
                            logger.debug(f"[MessagePusher] 平台对象类型: {type(platform).__name__}")
                            logger.debug(f"[MessagePusher] 平台对象方法: {[attr for attr in dir(platform) if not attr.startswith('_')]}")
                            
                            # 优先使用平台对象的 send_by_session 方法
                            if hasattr(platform, 'send_by_session'):
                                client = platform
                                logger.debug(f"[MessagePusher] 使用飞书平台对象的 send_by_session 方法")
                                break
                            # 尝试直接使用平台对象发送消息
                            elif hasattr(platform, 'send_message'):
                                client = platform
                                break
                            elif hasattr(platform, 'send_private_message'):
                                client = platform
                                break
                            # 获取飞书平台的客户端
                            elif hasattr(platform, 'client'):
                                client = platform.client
                                break
                            elif hasattr(platform, 'bot'):
                                client = platform.bot
                                break
            
            if not client:
                logger.warning(f"[MessagePusher] 飞书缺少客户端上下文, context类型: {type(context).__name__ if context else 'None'}")
                return False
            
            logger.debug(f"[MessagePusher] 飞书客户端类型: {type(client).__name__}")
            logger.debug(f"[MessagePusher] 飞书客户端所有方法: {[attr for attr in dir(client) if not attr.startswith('_')]}")
            
            # 飞书发送私信
            if hasattr(client, 'send_by_session'):
                # 使用飞书平台的 send_by_session 方法
                from astrbot.core.platform.astr_message_event import MessageSesion
                from astrbot.api.event import MessageChain
                from astrbot.api.message_components import Plain
                from astrbot.api.platform import MessageType
                
                # 创建消息会话对象
                session = MessageSesion(
                    platform_name="lark",
                    session_id=user_id,  # 使用原始的 ou_xxx 格式
                    message_type=MessageType.FRIEND_MESSAGE
                )
                
                # 创建消息链
                message_chain = MessageChain([Plain(message)])
                
                # 发送消息
                await client.send_by_session(session, message_chain)
                
            elif hasattr(client, 'send_message'):
                await client.send_message(
                    receive_id=user_id,  # 使用原始的 ou_xxx 格式
                    msg_type="text",
                    content={"text": message}
                )
            elif hasattr(client, 'send_private_message'):
                await client.send_private_message(user_id, message)
            else:
                logger.warning(f"[MessagePusher] 飞书客户端不支持发送消息")
                logger.warning(f"[MessagePusher] 客户端类型: {type(client).__name__}")
                logger.warning(f"[MessagePusher] 包含send的方法: {[attr for attr in dir(client) if 'send' in attr.lower()]}")
                logger.warning(f"[MessagePusher] 所有公开方法: {[attr for attr in dir(client) if not attr.startswith('_')]}")
                return False
            
            logger.debug(f"[MessagePusher] 飞书消息发送成功: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"[MessagePusher] 飞书消息发送失败: {e}")
            return False
    
    async def broadcast_to_admins(
        self,
        admin_list: list,
        message: str,
        context: Optional[Any] = None,
        keyboard: Optional[Any] = None,
        max_retries: int = 2
    ) -> Dict[str, bool]:
        """
        向所有管理员广播消息
        
        Args:
            admin_list: 管理员ID列表
            message: 消息内容
            context: 上下文对象
            keyboard: 可选的键盘
            max_retries: 最大重试次数
            
        Returns:
            发送结果字典 {admin_id: success}
        """
        return await self.batch_push(
            user_ids=admin_list,
            message=message,
            context=context,
            keyboard=keyboard,
            max_retries=max_retries
        )
    
    # ==================== 批量推送功能 ====================
    
    async def batch_push(
        self,
        user_ids: List[str],
        message: str,
        context: Optional[Any] = None,
        keyboard: Optional[Any] = None,
        max_retries: int = 3,
        concurrency: int = 10,
        on_progress: Callable[[int, int, int], None] = None
    ) -> Dict[str, PushResult]:
        """
        批量推送消息
        
        Args:
            user_ids: 用户ID列表
            message: 消息内容
            context: 上下文对象
            keyboard: 可选的键盘
            max_retries: 最大重试次数
            concurrency: 并发数（同时发送的消息数）
            on_progress: 进度回调函数 (sent, success, total)
            
        Returns:
            推送结果字典 {user_id: PushResult}
        """
        ctx = context or self._context
        results: Dict[str, PushResult] = {}
        total = len(user_ids)
        sent = 0
        success_count = 0
        
        # 使用信号量控制并发
        semaphore = asyncio.Semaphore(concurrency)
        
        async def push_one(user_id: str) -> PushResult:
            nonlocal sent, success_count
            
            async with semaphore:
                start_time = datetime.now()
                retry_count = 0
                success = False
                error_msg = None
                
                while retry_count <= max_retries:
                    try:
                        success = await self.send_private_message(
                            user_id=user_id,
                            message=message,
                            context=ctx,
                            keyboard=keyboard,
                            max_retries=0,  # 内部不重试，由外部控制
                            with_rate_limit=True
                        )
                        
                        if success:
                            break
                        else:
                            raise Exception("发送返回失败")
                            
                    except Exception as e:
                        error_msg = str(e)
                        retry_count += 1
                        
                        if retry_count <= max_retries:
                            wait_time = min(5 * retry_count, 30)
                            await asyncio.sleep(wait_time)
                
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                
                sent += 1
                if success:
                    success_count += 1
                
                # 进度回调
                if on_progress:
                    try:
                        on_progress(sent, success_count, total)
                    except Exception:
                        pass
                
                return PushResult(
                    user_id=user_id,
                    success=success,
                    error_message=error_msg if not success else None,
                    retry_count=retry_count,
                    duration_ms=duration_ms
                )
        
        # 并发执行
        tasks = [push_one(uid) for uid in user_ids]
        push_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for uid, result in zip(user_ids, push_results):
            if isinstance(result, Exception):
                results[uid] = PushResult(
                    user_id=uid,
                    success=False,
                    error_message=str(result)
                )
            else:
                results[uid] = result
        
        # 统计日志
        final_success = sum(1 for r in results.values() if r.success)
        logger.info(f"[MessagePusher] 批量推送完成: {final_success}/{total} 成功")
        
        return results
    
    async def batch_push_with_template(
        self,
        user_data: List[Dict[str, Any]],
        template: str,
        context: Optional[Any] = None,
        max_retries: int = 3,
        concurrency: int = 10
    ) -> Dict[str, PushResult]:
        """
        使用模板批量推送个性化消息
        
        Args:
            user_data: 用户数据列表，每项包含 user_id 和模板变量
                      例如: [{"user_id": "telegram:123", "name": "张三", "points": 100}]
            template: 消息模板，使用 {变量名} 占位
                      例如: "你好 {name}，你的积分是 {points}"
            context: 上下文对象
            max_retries: 最大重试次数
            concurrency: 并发数
            
        Returns:
            推送结果字典
        """
        ctx = context or self._context
        results: Dict[str, PushResult] = {}
        
        semaphore = asyncio.Semaphore(concurrency)
        
        async def push_one(data: Dict[str, Any]) -> PushResult:
            user_id = data.get('user_id')
            if not user_id:
                return PushResult(user_id='unknown', success=False, error_message='缺少user_id')
            
            async with semaphore:
                # 渲染模板
                try:
                    message = template.format(**{k: v for k, v in data.items() if k != 'user_id'})
                except KeyError as e:
                    return PushResult(
                        user_id=user_id,
                        success=False,
                        error_message=f"模板变量缺失: {e}"
                    )
                
                start_time = datetime.now()
                success = await self.send_private_message(
                    user_id=user_id,
                    message=message,
                    context=ctx,
                    max_retries=max_retries
                )
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                
                return PushResult(
                    user_id=user_id,
                    success=success,
                    duration_ms=duration_ms
                )
        
        tasks = [push_one(data) for data in user_data]
        push_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for data, result in zip(user_data, push_results):
            uid = data.get('user_id', 'unknown')
            if isinstance(result, Exception):
                results[uid] = PushResult(user_id=uid, success=False, error_message=str(result))
            else:
                results[uid] = result
        
        return results
    
    # ==================== 推送队列功能 ====================
    
    async def start_queue_worker(self, concurrency: int = 5):
        """
        启动推送队列工作器
        
        Args:
            concurrency: 并发处理数
        """
        if self._queue is None:
            self._queue = asyncio.Queue()
        
        if self._queue_worker_task is not None:
            logger.warning("[MessagePusher] 队列工作器已在运行")
            return
        
        self._queue_worker_task = asyncio.create_task(
            self._queue_worker(concurrency)
        )
        logger.info(f"[MessagePusher] 推送队列工作器已启动，并发数: {concurrency}")
    
    def stop_queue_worker(self):
        """停止推送队列工作器"""
        if self._queue_worker_task:
            self._queue_worker_task.cancel()
            self._queue_worker_task = None
            logger.info("[MessagePusher] 推送队列工作器已停止")
    
    async def _queue_worker(self, concurrency: int):
        """队列工作器主循环"""
        semaphore = asyncio.Semaphore(concurrency)
        
        async def process_task(task: PushTask):
            async with semaphore:
                start_time = datetime.now()
                
                task.status = PushStatus.SENDING
                success = await self.send_private_message(
                    user_id=task.user_id,
                    message=task.message,
                    context=task.context or self._context,
                    keyboard=task.keyboard,
                    max_retries=task.max_retries
                )
                
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                
                result = PushResult(
                    user_id=task.user_id,
                    success=success,
                    retry_count=task.retry_count,
                    duration_ms=duration_ms
                )
                
                task.status = PushStatus.SUCCESS if success else PushStatus.FAILED
                task.sent_at = datetime.now()
                
                # 记录日志
                self._log_push(task, result)
                
                return result
        
        while True:
            try:
                task = await self._queue.get()
                asyncio.create_task(process_task(task))
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MessagePusher] 队列处理错误: {e}")
    
    async def queue_push(
        self,
        user_id: str,
        message: str,
        context: Optional[Any] = None,
        keyboard: Optional[Any] = None,
        priority: int = 0,
        max_retries: int = 3
    ) -> str:
        """
        将推送任务加入队列
        
        Args:
            user_id: 用户ID
            message: 消息内容
            context: 上下文对象
            keyboard: 可选的键盘
            priority: 优先级（数字越大越优先）
            max_retries: 最大重试次数
            
        Returns:
            任务ID
        """
        if self._queue is None:
            self._queue = asyncio.Queue()
            # 自动启动工作器
            await self.start_queue_worker()
        
        task = PushTask(
            task_id=self._generate_task_id(),
            user_id=user_id,
            message=message,
            context=context or self._context,
            keyboard=keyboard,
            priority=priority,
            max_retries=max_retries
        )
        
        await self._queue.put(task)
        logger.debug(f"[MessagePusher] 任务已加入队列: {task.task_id}")
        
        return task.task_id
    
    async def queue_batch_push(
        self,
        user_ids: List[str],
        message: str,
        context: Optional[Any] = None,
        keyboard: Optional[Any] = None,
        priority: int = 0,
        max_retries: int = 3
    ) -> List[str]:
        """
        批量加入推送队列
        
        Args:
            user_ids: 用户ID列表
            message: 消息内容
            context: 上下文对象
            keyboard: 可选的键盘
            priority: 优先级
            max_retries: 最大重试次数
            
        Returns:
            任务ID列表
        """
        task_ids = []
        for user_id in user_ids:
            task_id = await self.queue_push(
                user_id=user_id,
                message=message,
                context=context,
                keyboard=keyboard,
                priority=priority,
                max_retries=max_retries
            )
            task_ids.append(task_id)
        
        logger.info(f"[MessagePusher] 批量加入队列: {len(task_ids)} 个任务")
        return task_ids
    
    def get_queue_size(self) -> int:
        """获取队列大小"""
        return self._queue.qsize() if self._queue else 0
    
    # ==================== 统计和日志功能 ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """获取推送统计"""
        return {
            **self._stats,
            'queue_size': self.get_queue_size(),
            'success_rate': round(
                self._stats['total_success'] / max(self._stats['total_sent'], 1) * 100, 2
            )
        }
    
    def reset_stats(self):
        """重置统计数据"""
        self._stats = {
            'total_sent': 0,
            'total_success': 0,
            'total_failed': 0,
            'total_retries': 0
        }
    
    def get_push_logs(
        self,
        user_id: str = None,
        status: str = None,
        days: int = 7,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取推送日志
        
        Args:
            user_id: 用户ID（可选）
            status: 状态过滤（success/failed）
            days: 查询天数
            limit: 返回数量
            
        Returns:
            日志列表
        """
        if not self.db:
            return []
        
        try:
            conditions = ["created_at > ?"]
            params = [datetime.now() - timedelta(days=days)]
            
            if user_id:
                conditions.append("user_id = ?")
                params.append(user_id)
            
            if status:
                conditions.append("status = ?")
                params.append(status)
            
            where_clause = " AND ".join(conditions)
            
            rows = self.db.execute(f"""
                SELECT * FROM push_logs
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ?
            """, (*params, limit))
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"[MessagePusher] 获取推送日志失败: {e}")
            return []
    
    def get_user_push_stats(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """
        获取用户推送统计
        
        Args:
            user_id: 用户ID
            days: 统计天数
            
        Returns:
            统计数据
        """
        if not self.db:
            return {'total': 0, 'success': 0, 'failed': 0}
        
        try:
            since = datetime.now() - timedelta(days=days)
            
            row = self.db.execute_one("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM push_logs
                WHERE user_id = ? AND created_at > ?
            """, (user_id, since))
            
            if row:
                return {
                    'total': row['total'] or 0,
                    'success': row['success'] or 0,
                    'failed': row['failed'] or 0,
                    'success_rate': round((row['success'] or 0) / max(row['total'] or 1, 1) * 100, 2)
                }
            
            return {'total': 0, 'success': 0, 'failed': 0, 'success_rate': 0}
            
        except Exception as e:
            logger.error(f"[MessagePusher] 获取用户推送统计失败: {e}")
            return {'total': 0, 'success': 0, 'failed': 0, 'success_rate': 0}
    
    def cleanup_old_logs(self, days: int = 30) -> int:
        """
        清理旧日志
        
        Args:
            days: 保留天数
            
        Returns:
            清理的记录数
        """
        if not self.db:
            return 0
        
        try:
            cutoff = datetime.now() - timedelta(days=days)
            self.db.execute_write("""
                DELETE FROM push_logs WHERE created_at < ?
            """, (cutoff,))
            logger.info(f"[MessagePusher] 清理 {days} 天前的推送日志")
            return 0
        except Exception as e:
            logger.error(f"[MessagePusher] 清理日志失败: {e}")
            return 0


# ==================== 全局实例 ====================

_message_pusher: Optional[MessagePusher] = None


def get_message_pusher(db=None) -> MessagePusher:
    """
    获取消息推送器实例（单例模式）
    
    Args:
        db: 数据库管理器（首次调用时可选）
    
    Returns:
        MessagePusher 实例
    """
    global _message_pusher
    
    if _message_pusher is None:
        _message_pusher = MessagePusher(db)
        logger.info("[MessagePusher] 创建全局推送器实例")
    elif db and _message_pusher.db is None:
        _message_pusher.db = db
        _message_pusher._init_db_tables()
    
    return _message_pusher


def init_message_pusher(db=None, context=None) -> MessagePusher:
    """
    初始化消息推送器（带上下文）
    
    Args:
        db: 数据库管理器
        context: AstrBot Context 对象
        
    Returns:
        MessagePusher 实例
    """
    pusher = get_message_pusher(db)
    if context:
        pusher.set_context(context)
    return pusher
