"""
智能推送调度器

整合内容预抓取，实现高效稳定的推送系统。

核心策略：
1. 预抓取分离：内容抓取与推送完全分离
2. 错峰推送：同一时段的推送分散到前后几分钟
3. 批量推送：相同内容合并推送，减少重复抓取
4. 智能重试：推送失败智能重试，避免集中重试

时间线示例（用户都设置8点推送）：
┌────────────────────────────────────────────────────────┐
│ 6:00-7:00  预抓取阶段：分散抓取所有8点要推送的源        │
│ 7:30-7:55  紧急补抓：检查缓存，补抓过期内容            │
│ 8:00-8:10  错峰推送：将推送分散到这10分钟内执行        │
│ 8:10-8:30  重试阶段：处理推送失败的任务                │
└────────────────────────────────────────────────────────┘

使用示例：
    from common.push_scheduler import get_push_scheduler, init_push_scheduler
    
    # 初始化
    scheduler = init_push_scheduler(
        prefetcher=prefetcher,
        subscription_manager=subscription_manager,
        push_handler=push_handler
    )
    
    # 启动
    await scheduler.start()
"""

import asyncio
import time
import random
from typing import Dict, List, Any, Optional, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import heapq

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


@dataclass
class PushTask:
    """推送任务"""
    subscription_id: int            # 订阅ID
    user_id: str                    # 用户ID
    source_id: int                  # 源ID
    scheduled_time: float           # 计划推送时间
    priority: int = 0               # 优先级（0最高）
    retry_count: int = 0            # 重试次数
    created_at: float = field(default_factory=time.time)
    
    def __lt__(self, other):
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.scheduled_time < other.scheduled_time


@dataclass
class PushBatch:
    """推送批次（相同源的推送合并）"""
    source_id: int
    tasks: List[PushTask] = field(default_factory=list)
    content: Any = None             # 缓存的内容
    

class PushScheduler:
    """智能推送调度器
    
    P1优化：
    1. 分层并发控制：全局限制 + 按源限制
    2. 批量推送优化：相同源的订阅共享内容
    3. 用户去重：同一用户不重复推送
    """
    
    # 配置
    SPREAD_WINDOW = 600             # 错峰窗口：10分钟
    MAX_CONCURRENT_PUSH = 20        # P1优化：全局最大并发推送数（10→20）
    MAX_CONCURRENT_PER_SOURCE = 5   # P1优化：每个源最大并发数
    PUSH_DELAY_MIN = 0.3            # P1优化：推送间隔最小延迟（0.5→0.3）
    PUSH_DELAY_MAX = 1.5            # P1优化：推送间隔最大延迟（2.0→1.5）
    MAX_RETRY = 3                   # 最大重试次数
    RETRY_DELAYS = [60, 300, 900]   # 重试延迟：1分钟、5分钟、15分钟
    
    def __init__(
        self,
        prefetcher=None,
        subscription_manager=None,
        push_handler: Callable = None
    ):
        """
        初始化推送调度器
        
        Args:
            prefetcher: 内容预抓取器
            subscription_manager: 订阅管理器
            push_handler: 推送处理函数 async def handler(user_id, source_id, content)
        """
        self.prefetcher = prefetcher
        self.subscription_manager = subscription_manager
        self.push_handler = push_handler
        
        # 任务队列
        self._task_queue: List[PushTask] = []
        self._task_set: Set[Tuple[int, str]] = set()  # (subscription_id, user_id)
        
        # 运行状态
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        
        # P1优化：分层并发控制
        self._global_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_PUSH)
        self._source_semaphores: Dict[int, asyncio.Semaphore] = {}  # 按源的信号量
        self._push_semaphore = self._global_semaphore  # 兼容旧代码
        
        # 统计
        self._stats = {
            'total_pushed': 0,
            'success_count': 0,
            'fail_count': 0,
            'retry_count': 0,
            'cache_hits': 0,      # P1优化：缓存命中统计
            'batch_count': 0      # P1优化：批量推送统计
        }
        
        logger.info("[PushScheduler] 推送调度器初始化完成")
    
    def _get_source_semaphore(self, source_id: int) -> asyncio.Semaphore:
        """
        P1优化：获取源级别的信号量
        
        每个源有独立的并发限制，避免单一源占用所有并发资源
        """
        if source_id not in self._source_semaphores:
            self._source_semaphores[source_id] = asyncio.Semaphore(self.MAX_CONCURRENT_PER_SOURCE)
        return self._source_semaphores[source_id]
    
    async def start(self):
        """启动调度器"""
        if self._running:
            return
        
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        
        logger.info("[PushScheduler] 推送调度器已启动")
    
    async def stop(self):
        """停止调度器"""
        self._running = False
        
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        
        logger.info("[PushScheduler] 推送调度器已停止")
    
    async def _scheduler_loop(self):
        """调度主循环
        
        优化后的调度策略：
        1. 每分钟查询数据库获取待推送订阅（基于 next_push_at）
        2. 直接处理到期订阅，无需维护内存队列
        3. 支持实时响应推送时间修改
        """
        logger.info("[PushScheduler] 调度循环启动")
        
        while self._running:
            try:
                # 直接从数据库查询待推送订阅
                await self._process_due_subscriptions()
                
                # 同时处理内存队列中的任务（兼容旧逻辑）
                await self._process_due_tasks()
                
                # 休眠30秒
                await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[PushScheduler] 调度循环异常: {e}")
                await asyncio.sleep(60)
        
        logger.info("[PushScheduler] 调度循环结束")
    
    async def _process_due_subscriptions(self):
        """处理到期订阅（基于数据库查询）"""
        if not self.subscription_manager:
            return
        
        try:
            # 查询未来1分钟内需要推送的订阅
            due_subs = self.subscription_manager.get_due_subscriptions(within_minutes=1)
            
            if not due_subs:
                return
            
            logger.info(f"[PushScheduler] 发现 {len(due_subs)} 个待推送订阅")
            
            # 按 source_id 分组（相同源的订阅共享内容）
            source_groups: Dict[int, List] = defaultdict(list)
            for sub in due_subs:
                # 使用 source_id 或生成虚拟ID
                source_id = sub.source_id if sub.source_id else hash(f"{sub.plugin_name}:{sub.target}") % 1000000
                source_groups[source_id].append(sub)
            
            # 处理每个源组
            for source_id, subs in source_groups.items():
                asyncio.create_task(self._process_subscription_group(source_id, subs))
                
        except Exception as e:
            logger.error(f"[PushScheduler] 处理待推送订阅失败: {e}")
    
    async def _process_subscription_group(self, source_id: int, subscriptions: List):
        """
        处理一组订阅（相同源）
        
        P1优化：
        1. 一次抓取，多次推送（缓存共享）
        2. 按用户去重，避免同一用户收到重复内容
        3. 分层并发控制（全局 + 源级别）
        4. 并发推送给不同用户
        """
        # 获取缓存内容（仅对真实订阅源有效）
        content = None
        is_real_source = source_id < 100000
        
        if is_real_source and self.prefetcher:
            cached = await self.prefetcher.get_content(
                source_id, 
                max_age=3600,
                wait_for_fetch=True
            )
            if cached:
                content = cached.items
                self._stats['cache_hits'] += 1
        
        # P1优化：按用户去重（同一用户可能有多个相同源的订阅）
        user_subscriptions: Dict[str, List] = defaultdict(list)
        for sub in subscriptions:
            user_subscriptions[sub.user_id].append(sub)
        
        # P1优化：记录批量推送
        self._stats['batch_count'] += 1
        
        # P1优化：获取源级别信号量
        source_semaphore = self._get_source_semaphore(source_id)
        
        # P1优化：并发推送给不同用户
        async def push_to_user(user_id: str, user_subs: List):
            """推送给单个用户"""
            # 使用分层信号量：全局 + 源级别
            async with self._global_semaphore:
                async with source_semaphore:
                    # 只推送一次（取第一个订阅）
                    sub = user_subs[0]
                    try:
                        if self.push_handler:
                            success = await self.push_handler(
                                user_id=user_id,
                                source_id=source_id,
                                subscription_id=sub.id,
                                content=content
                            )
                            
                            if success:
                                self._stats['success_count'] += 1
                                # 标记所有该用户的相关订阅为已推送
                                for s in user_subs:
                                    if self.subscription_manager:
                                        try:
                                            self.subscription_manager.mark_pushed(s.id, success=True)
                                        except:
                                            pass
                                logger.debug(f"[PushScheduler] 推送成功: user={user_id}, source={source_id}")
                            else:
                                self._stats['fail_count'] += 1
                        
                        self._stats['total_pushed'] += 1
                        
                    except Exception as e:
                        self._stats['fail_count'] += 1
                        logger.error(f"[PushScheduler] 推送失败: user={user_id}, error={e}")
                        # 确保更新下次推送时间，避免重复尝试
                        if self.subscription_manager:
                            for s in user_subs:
                                try:
                                    self.subscription_manager.mark_pushed(s.id, success=False, error_message=str(e))
                                except:
                                    pass
                    
                    # 添加随机延迟
                    await asyncio.sleep(random.uniform(self.PUSH_DELAY_MIN, self.PUSH_DELAY_MAX))
        
        # 并发执行所有用户的推送
        tasks = [push_to_user(user_id, subs) for user_id, subs in user_subscriptions.items()]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _schedule_hour_tasks(self, hour: int):
        """生成指定小时的推送任务"""
        if not self.subscription_manager:
            return
        
        try:
            # 获取该小时需要推送的订阅
            subscriptions = await self._get_subscriptions_for_hour(hour)
            
            if not subscriptions:
                return
            
            logger.info(f"[PushScheduler] 为 {hour}:00 生成 {len(subscriptions)} 个推送任务")
            
            # 计算错峰时间
            base_time = datetime.now().replace(minute=0, second=0, microsecond=0)
            if base_time.hour != hour:
                # 如果当前不是目标小时，调整到目标小时
                if hour > base_time.hour:
                    base_time = base_time.replace(hour=hour)
                else:
                    base_time = base_time + timedelta(days=1)
                    base_time = base_time.replace(hour=hour)
            
            base_timestamp = base_time.timestamp()
            
            # 按源分组，相同源的推送时间接近
            source_groups: Dict[int, List] = defaultdict(list)
            for sub in subscriptions:
                source_groups[sub.source_id].append(sub)
            
            # 为每个源组分配错峰时间
            num_groups = len(source_groups)
            time_slot = self.SPREAD_WINDOW / max(num_groups, 1)
            
            for i, (source_id, subs) in enumerate(source_groups.items()):
                # 该源组的基准时间
                group_base_time = base_timestamp + (i * time_slot)
                
                for j, sub in enumerate(subs):
                    # 组内再错峰
                    offset = random.uniform(0, time_slot * 0.8)
                    scheduled_time = group_base_time + offset
                    
                    task = PushTask(
                        subscription_id=sub.id,
                        user_id=sub.user_id,
                        source_id=source_id,
                        scheduled_time=scheduled_time,
                        priority=0
                    )
                    
                    self._add_task(task)
            
            # 提前触发预抓取
            if self.prefetcher:
                for source_id in source_groups.keys():
                    await self.prefetcher.trigger_fetch(source_id)
            
        except Exception as e:
            logger.error(f"[PushScheduler] 生成推送任务失败: {e}")
    
    async def _get_subscriptions_for_hour(self, hour: int) -> List:
        """获取指定小时需要推送的订阅"""
        try:
            # 这里需要根据实际的订阅管理器接口调整
            all_subs = self.subscription_manager.get_all_active_subscriptions()
            
            result = []
            for sub in all_subs:
                push_hours = self._parse_push_hours(sub)
                if hour in push_hours:
                    result.append(sub)
            
            return result
            
        except Exception as e:
            logger.error(f"[PushScheduler] 获取订阅失败: {e}")
            return []
    
    def _parse_push_hours(self, subscription) -> List[int]:
        """解析订阅的推送小时"""
        hours = []
        
        try:
            push_time = getattr(subscription, 'push_time', None)
            if push_time:
                for t in str(push_time).split(','):
                    t = t.strip()
                    if ':' in t:
                        hour = int(t.split(':')[0])
                        if 0 <= hour <= 23:
                            hours.append(hour)
        except Exception:
            pass
        
        return hours if hours else [8]
    
    def _add_task(self, task: PushTask):
        """添加任务"""
        key = (task.subscription_id, task.user_id)
        if key in self._task_set:
            return
        
        heapq.heappush(self._task_queue, task)
        self._task_set.add(key)
    
    async def schedule_subscription(self, subscription_id: int):
        """
        通知调度器某订阅的推送时间已更新
        
        由于调度器现在基于数据库 next_push_at 字段查询，
        只需确保数据库已更新即可，调度器会自动检测到。
        
        此方法保留用于：
        1. 记录日志
        2. 未来可能的立即推送需求
        
        Args:
            subscription_id: 订阅ID
        """
        if not self.subscription_manager:
            return
        
        try:
            sub = self.subscription_manager.get_subscription(subscription_id)
            if not sub:
                return
            
            next_push = sub.next_push_at
            if next_push:
                logger.info(f"[PushScheduler] 订阅 {subscription_id} 下次推送时间: {next_push.strftime('%Y-%m-%d %H:%M')}")
            else:
                logger.warning(f"[PushScheduler] 订阅 {subscription_id} 未设置下次推送时间")
                
        except Exception as e:
            logger.error(f"[PushScheduler] 检查订阅失败: {e}")
    
    async def _process_due_tasks(self):
        """处理内存队列中的到期任务（兼容旧逻辑）"""
        now = time.time()
        
        # 收集到期任务，按源分组
        due_batches: Dict[int, PushBatch] = {}
        
        while self._task_queue and self._task_queue[0].scheduled_time <= now:
            task = heapq.heappop(self._task_queue)
            key = (task.subscription_id, task.user_id)
            self._task_set.discard(key)
            
            source_id = task.source_id
            if source_id not in due_batches:
                due_batches[source_id] = PushBatch(source_id=source_id)
            due_batches[source_id].tasks.append(task)
        
        # 批量处理
        for source_id, batch in due_batches.items():
            asyncio.create_task(self._process_batch(batch))
    
    async def _process_batch(self, batch: PushBatch):
        """处理推送批次"""
        source_id = batch.source_id
        
        # 获取缓存内容（仅对真实订阅源有效）
        content = None
        
        # 检查是否是真实的订阅源ID（小于100000的通常是真实ID）
        # 大于100000的是通过 hash(plugin_name:target) 生成的虚拟ID
        is_real_source = source_id < 100000
        
        if is_real_source and self.prefetcher:
            cached = await self.prefetcher.get_content(
                source_id, 
                max_age=3600,  # 1小时内的缓存
                wait_for_fetch=True
            )
            if cached:
                content = cached.items
        
        # 逐个推送（即使没有预抓取内容，也让 push_handler 自己获取）
        for task in batch.tasks:
            async with self._push_semaphore:
                await self._execute_push(task, content)
                
                # 添加随机延迟
                await asyncio.sleep(
                    random.uniform(self.PUSH_DELAY_MIN, self.PUSH_DELAY_MAX)
                )
    
    async def _execute_push(self, task: PushTask, content: Any):
        """执行单个推送"""
        self._stats['total_pushed'] += 1
        
        try:
            if self.push_handler:
                success = await self.push_handler(
                    user_id=task.user_id,
                    source_id=task.source_id,
                    subscription_id=task.subscription_id,
                    content=content
                )
                
                if success:
                    self._stats['success_count'] += 1
                    logger.debug(f"[PushScheduler] 推送成功: user={task.user_id}, source={task.source_id}")
                else:
                    raise Exception("推送返回失败")
            else:
                logger.warning("[PushScheduler] 未设置推送处理器")
                
        except Exception as e:
            self._stats['fail_count'] += 1
            logger.error(f"[PushScheduler] 推送失败: {e}")
            
            # 重试
            if task.retry_count < self.MAX_RETRY:
                task.retry_count += 1
                task.scheduled_time = time.time() + self.RETRY_DELAYS[min(task.retry_count - 1, 2)]
                task.priority = 2  # 降低优先级
                self._add_task(task)
                self._stats['retry_count'] += 1
    
    # ==================== 公开接口 ====================
    
    async def trigger_push(
        self, 
        subscription_id: int,
        user_id: str,
        source_id: int,
        delay: int = 0
    ):
        """
        触发立即推送
        
        Args:
            subscription_id: 订阅ID
            user_id: 用户ID
            source_id: 源ID
            delay: 延迟秒数
        """
        task = PushTask(
            subscription_id=subscription_id,
            user_id=user_id,
            source_id=source_id,
            scheduled_time=time.time() + delay,
            priority=0
        )
        self._add_task(task)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            'queue_size': len(self._task_queue),
            'success_rate': self._stats['success_count'] / max(self._stats['total_pushed'], 1)
        }
    
    def get_queue_status(self) -> List[Dict]:
        """获取队列状态"""
        now = time.time()
        result = []
        
        for task in sorted(self._task_queue)[:20]:
            result.append({
                'subscription_id': task.subscription_id,
                'user_id': task.user_id,
                'source_id': task.source_id,
                'scheduled_in': round(task.scheduled_time - now, 1),
                'retry_count': task.retry_count
            })
        
        return result


# 全局实例
_push_scheduler: Optional[PushScheduler] = None


def get_push_scheduler() -> Optional[PushScheduler]:
    """获取推送调度器实例"""
    return _push_scheduler


def init_push_scheduler(
    prefetcher=None,
    subscription_manager=None,
    push_handler: Callable = None
) -> PushScheduler:
    """
    初始化推送调度器
    
    Args:
        prefetcher: 内容预抓取器
        subscription_manager: 订阅管理器
        push_handler: 推送处理函数
        
    Returns:
        PushScheduler 实例
    """
    global _push_scheduler
    _push_scheduler = PushScheduler(
        prefetcher=prefetcher,
        subscription_manager=subscription_manager,
        push_handler=push_handler
    )
    return _push_scheduler
