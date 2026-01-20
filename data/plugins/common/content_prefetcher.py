"""
内容预抓取调度器

解决问题：
- 用户推送时间集中（如都设置8点）
- 不能在推送时刻并发抓取几百个源（IP封禁风险）
- 需要高效、稳定、智能的内容获取策略

解决方案：
1. 内容预抓取：提前分散抓取，推送时直接使用缓存
2. 智能调度：根据源更新频率动态调整抓取间隔
3. 并发控制：限制同时抓取数量，避免IP封禁
4. 错峰抓取：将抓取任务分散到全天各时段
5. 优先级队列：热门源、即将推送的源优先抓取

架构：
┌─────────────────────────────────────────────────────────┐
│                    ContentPrefetcher                     │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │ 调度引擎    │  │ 抓取队列    │  │ 内容缓存        │  │
│  │ Scheduler   │→ │ FetchQueue  │→ │ ContentCache    │  │
│  └─────────────┘  └─────────────┘  └─────────────────┘  │
│         ↓                                    ↑          │
│  ┌─────────────┐  ┌─────────────┐            │          │
│  │ 频率分析    │  │ 并发控制    │────────────┘          │
│  │ FreqAnalyzer│  │ RateLimiter │                       │
│  └─────────────┘  └─────────────┘                       │
└─────────────────────────────────────────────────────────┘

使用示例：
    from common.content_prefetcher import get_prefetcher, init_prefetcher
    
    # 初始化
    prefetcher = init_prefetcher(source_manager, cache_manager)
    
    # 启动后台调度
    await prefetcher.start()
    
    # 推送时获取缓存内容（不触发抓取）
    content = await prefetcher.get_cached_content(source_id)
    
    # 如果缓存过期，可选择等待抓取或使用旧数据
    content = await prefetcher.get_content(source_id, max_age=3600)
"""

import asyncio
import time
import random
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
import heapq

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# 导入订阅相关枚举
try:
    from .subscription_manager import SubscriptionType
    from .subscription_source import SourceStatus
except ImportError:
    SubscriptionType = None
    SourceStatus = None


class FetchPriority(Enum):
    """抓取优先级"""
    URGENT = 0      # 紧急：即将推送（30分钟内）
    HIGH = 1        # 高：1小时内推送
    NORMAL = 2      # 普通：常规调度
    LOW = 3         # 低：不活跃源
    IDLE = 4        # 空闲：填充时段


@dataclass
class FetchTask:
    """抓取任务"""
    source_id: int
    priority: FetchPriority
    scheduled_time: float           # 计划抓取时间
    next_push_time: float = 0       # 下次推送时间
    last_fetch_time: float = 0      # 上次抓取时间
    retry_count: int = 0            # 重试次数
    
    def __lt__(self, other):
        # 优先级队列排序：优先级 > 计划时间
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        return self.scheduled_time < other.scheduled_time


@dataclass
class SourceFetchStats:
    """源抓取统计"""
    source_id: int
    total_fetches: int = 0          # 总抓取次数
    success_count: int = 0          # 成功次数
    fail_count: int = 0             # 失败次数
    consecutive_fails: int = 0      # 连续失败次数（用于健康监控）
    avg_fetch_time: float = 0       # 平均抓取耗时
    avg_content_count: float = 0    # 平均内容数
    update_frequency: float = 0     # 更新频率（小时）
    last_update_time: float = 0     # 最后更新时间
    last_content_hash: str = ""     # 最后内容哈希（用于检测更新）
    disabled_at: float = 0          # 自动停用时间（0表示未停用）


@dataclass 
class CachedContent:
    """缓存的内容"""
    source_id: int
    items: List[Dict]               # 内容条目
    fetch_time: float               # 抓取时间
    content_hash: str               # 内容哈希
    is_updated: bool = False        # 是否有新内容


class ContentPrefetcher:
    """内容预抓取调度器"""
    
    # 配置常量
    DEFAULT_FETCH_INTERVAL = 1800       # 默认抓取间隔：30分钟
    MIN_FETCH_INTERVAL = 300            # 最小抓取间隔：5分钟
    MAX_FETCH_INTERVAL = 7200           # 最大抓取间隔：2小时
    
    MAX_CONCURRENT_FETCHES = 3          # 最大并发抓取数
    FETCH_DELAY_MIN = 2                 # 抓取间隔最小延迟（秒）
    FETCH_DELAY_MAX = 5                 # 抓取间隔最大延迟（秒）
    
    PRE_FETCH_WINDOW = 3600             # 预抓取窗口：推送前1小时
    URGENT_WINDOW = 1800                # 紧急窗口：推送前30分钟
    
    CACHE_TTL = 7200                    # 缓存有效期：2小时
    MAX_RETRY = 3                       # 最大重试次数
    
    def __init__(
        self, 
        source_manager=None,
        cache_manager=None,
        subscription_manager=None
    ):
        """
        初始化预抓取调度器
        
        Args:
            source_manager: 订阅源管理器
            cache_manager: 缓存管理器
            subscription_manager: 订阅管理器（用于获取推送时间）
        """
        self.source_manager = source_manager
        self.cache_manager = cache_manager
        self.subscription_manager = subscription_manager
        
        # 任务队列（优先级队列）
        self._task_queue: List[FetchTask] = []
        self._task_set: Set[int] = set()  # 已在队列中的源ID
        
        # 内容缓存
        self._content_cache: Dict[int, CachedContent] = {}
        
        # 源统计信息
        self._source_stats: Dict[int, SourceFetchStats] = {}
        
        # 运行状态
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._fetch_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_FETCHES)
        
        # 推送时间索引：{hour: [source_ids]}
        self._push_time_index: Dict[int, List[int]] = defaultdict(list)
        
        # P0优化：索引重建控制
        self._last_index_build_time: float = 0
        self._index_dirty: bool = True  # 标记索引是否需要重建
        self._INDEX_REBUILD_INTERVAL = 3600  # 索引重建间隔：1小时
        
        # P0优化：正在抓取的源ID集合（防止重复抓取）
        self._fetching_sources: Set[int] = set()
        
        logger.info("[Prefetcher] 内容预抓取调度器初始化完成")
    
    async def start(self):
        """启动调度器"""
        if self._running:
            return
        
        self._running = True
        
        # 构建推送时间索引
        await self._build_push_time_index()
        
        # 初始化任务队列
        await self._initialize_task_queue()
        
        # 启动调度循环
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        
        logger.info("[Prefetcher] 调度器已启动")
    
    async def stop(self):
        """停止调度器"""
        self._running = False
        
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        
        logger.info("[Prefetcher] 调度器已停止")
    
    async def _build_push_time_index(self):
        """构建推送时间索引"""
        if not self.subscription_manager:
            return
        
        self._push_time_index.clear()
        
        try:
            # 获取所有活跃订阅
            # 这里需要根据实际的订阅管理器接口调整
            subscriptions = self.subscription_manager.get_all_active_subscriptions()
            
            for sub in subscriptions:
                # 从订阅中获取源ID
                source_id = None
                try:
                    if hasattr(sub, 'subscription_type') and sub.subscription_type:
                        type_value = sub.subscription_type.value if hasattr(sub.subscription_type, 'value') else str(sub.subscription_type)
                        if type_value == 'source' and sub.target:
                            # 订阅源类型，target 是源ID
                            try:
                                source_id = int(sub.target)
                            except (ValueError, TypeError):
                                continue
                    
                    if not source_id and hasattr(sub, 'config') and sub.config:
                        # 从配置中获取源ID
                        source_id = sub.config.get('source_id')
                except Exception:
                    continue
                
                if not source_id:
                    continue
                
                push_times = self._parse_push_times(sub)
                
                for hour in push_times:
                    if source_id not in self._push_time_index[hour]:
                        self._push_time_index[hour].append(source_id)
            
            logger.info(f"[Prefetcher] 推送时间索引构建完成，覆盖 {len(self._push_time_index)} 个时段")
            
        except Exception as e:
            logger.error(f"[Prefetcher] 构建推送时间索引失败: {e}")
    
    def _parse_push_times(self, subscription) -> List[int]:
        """解析订阅的推送时间（返回小时列表）"""
        hours = []
        
        try:
            push_time = getattr(subscription, 'push_time', None)
            if push_time:
                # 格式: "08:00" 或 "08:00,12:00,18:00"
                for t in str(push_time).split(','):
                    t = t.strip()
                    if ':' in t:
                        hour = int(t.split(':')[0])
                        if 0 <= hour <= 23:
                            hours.append(hour)
        except Exception:
            pass
        
        return hours if hours else [8]  # 默认8点
    
    async def _initialize_task_queue(self):
        """初始化任务队列"""
        if not self.source_manager:
            return
        
        try:
            # 获取所有活跃源
            if SourceStatus:
                sources = self.source_manager.get_all_sources(status=SourceStatus.ACTIVE)
            else:
                sources = self.source_manager.get_all_sources()
            
            now = time.time()
            current_hour = datetime.now().hour
            
            for source in sources:
                # 计算优先级和调度时间
                priority, scheduled_time = self._calculate_schedule(
                    source.id, 
                    current_hour,
                    now
                )
                
                task = FetchTask(
                    source_id=source.id,
                    priority=priority,
                    scheduled_time=scheduled_time
                )
                
                self._add_task(task)
            
            logger.info(f"[Prefetcher] 任务队列初始化完成，共 {len(self._task_queue)} 个任务")
            
        except Exception as e:
            logger.error(f"[Prefetcher] 初始化任务队列失败: {e}")
    
    def _calculate_schedule(
        self, 
        source_id: int, 
        current_hour: int,
        now: float
    ) -> Tuple[FetchPriority, float]:
        """
        计算源的抓取优先级和调度时间
        
        策略：
        1. 即将推送（30分钟内）→ URGENT，立即抓取
        2. 1小时内推送 → HIGH，尽快抓取
        3. 有订阅用户 → NORMAL，按更新频率调度
        4. 无订阅用户 → LOW，低优先级
        """
        # 查找该源最近的推送时间
        next_push_hours = []
        for hour, source_ids in self._push_time_index.items():
            if source_id in source_ids:
                next_push_hours.append(hour)
        
        if not next_push_hours:
            # 无推送计划，低优先级
            return FetchPriority.LOW, now + random.uniform(1800, 3600)
        
        # 计算距离最近推送的时间
        min_delta = float('inf')
        for hour in next_push_hours:
            delta = (hour - current_hour) % 24
            if delta == 0:
                delta = 24  # 如果是当前小时，算作24小时后
            min_delta = min(min_delta, delta)
        
        minutes_to_push = min_delta * 60
        
        if minutes_to_push <= 30:
            # 30分钟内推送，紧急
            return FetchPriority.URGENT, now
        elif minutes_to_push <= 60:
            # 1小时内推送，高优先级
            return FetchPriority.HIGH, now + random.uniform(0, 300)
        elif minutes_to_push <= 120:
            # 2小时内推送，正常优先级，提前抓取
            return FetchPriority.NORMAL, now + random.uniform(300, 900)
        else:
            # 较远的推送，根据更新频率调度
            stats = self._source_stats.get(source_id)
            if stats and stats.update_frequency > 0:
                # 根据历史更新频率调度
                interval = min(stats.update_frequency * 3600, self.MAX_FETCH_INTERVAL)
            else:
                interval = self.DEFAULT_FETCH_INTERVAL
            
            return FetchPriority.NORMAL, now + random.uniform(interval * 0.8, interval * 1.2)
    
    def _add_task(self, task: FetchTask):
        """添加任务到队列"""
        if task.source_id in self._task_set:
            return
        
        heapq.heappush(self._task_queue, task)
        self._task_set.add(task.source_id)
    
    def _pop_task(self) -> Optional[FetchTask]:
        """从队列取出任务"""
        if not self._task_queue:
            return None
        
        task = heapq.heappop(self._task_queue)
        self._task_set.discard(task.source_id)
        return task
    
    async def _scheduler_loop(self):
        """调度主循环
        
        P0优化：
        1. 索引重建改为按时间间隔+脏标记触发，而非每分钟检查
        2. 增加抓取去重检查
        """
        logger.info("[Prefetcher] 调度循环启动")
        
        while self._running:
            try:
                now = time.time()
                
                # P0优化：智能索引重建（仅在需要时重建）
                should_rebuild_index = (
                    self._index_dirty or 
                    (now - self._last_index_build_time) >= self._INDEX_REBUILD_INTERVAL
                )
                if should_rebuild_index:
                    await self._build_push_time_index()
                    self._last_index_build_time = now
                    self._index_dirty = False
                
                # 检查是否有到期任务
                while self._task_queue and self._task_queue[0].scheduled_time <= now:
                    task = self._pop_task()
                    if task:
                        # P0优化：跳过正在抓取的源
                        if task.source_id in self._fetching_sources:
                            logger.debug(f"[Prefetcher] 源 {task.source_id} 正在抓取中，跳过")
                            continue
                        
                        # 异步执行抓取
                        asyncio.create_task(self._execute_fetch(task))
                        
                        # 添加随机延迟，避免并发过高
                        await asyncio.sleep(
                            random.uniform(self.FETCH_DELAY_MIN, self.FETCH_DELAY_MAX)
                        )
                
                # 休眠一段时间（从10秒改为30秒，减少空转）
                await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[Prefetcher] 调度循环异常: {e}")
                await asyncio.sleep(30)
        
        logger.info("[Prefetcher] 调度循环结束")
    
    async def _execute_fetch(self, task: FetchTask):
        """执行抓取任务
        
        P0优化：添加抓取去重机制，防止同一源被并发抓取
        """
        source_id = task.source_id
        
        # P0优化：标记正在抓取
        if source_id in self._fetching_sources:
            logger.debug(f"[Prefetcher] 源 {source_id} 已在抓取中，跳过")
            return
        
        self._fetching_sources.add(source_id)
        
        try:
            async with self._fetch_semaphore:
                start_time = time.time()
                
                try:
                    logger.debug(f"[Prefetcher] 开始抓取源 {source_id}")
                    
                    # 获取源信息
                    source = self.source_manager.get_source(source_id)
                    if not source:
                        logger.warning(f"[Prefetcher] 源 {source_id} 不存在")
                        return
                    
                    # 执行抓取
                    items = await self._fetch_source_content(source)
                    
                    # 计算内容哈希
                    content_hash = self._calculate_content_hash(items)
                    
                    # 检查是否有更新
                    old_cache = self._content_cache.get(source_id)
                    is_updated = (
                        old_cache is None or 
                        old_cache.content_hash != content_hash
                    )
                    
                    # 更新缓存
                    self._content_cache[source_id] = CachedContent(
                        source_id=source_id,
                        items=items,
                        fetch_time=time.time(),
                        content_hash=content_hash,
                        is_updated=is_updated
                    )
                    
                    # 更新统计
                    self._update_stats(source_id, True, time.time() - start_time, len(items), is_updated)
                    
                    logger.debug(f"[Prefetcher] 源 {source_id} 抓取完成，{len(items)} 条内容")
                    
                except Exception as e:
                    logger.error(f"[Prefetcher] 抓取源 {source_id} 失败: {e}")
                    self._update_stats(source_id, False, time.time() - start_time, 0, False)
                    
                    # 重试逻辑
                    if task.retry_count < self.MAX_RETRY:
                        task.retry_count += 1
                        task.scheduled_time = time.time() + (60 * task.retry_count)  # 递增延迟
                        self._add_task(task)
                
                finally:
                    # 重新调度下次抓取
                    if task.retry_count == 0:  # 非重试任务才重新调度
                        self._schedule_next_fetch(source_id)
        finally:
            # P0优化：确保移除抓取标记
            self._fetching_sources.discard(source_id)
    
    async def _fetch_source_content(self, source) -> List:
        """抓取源内容"""
        try:
            # 直接调用源管理器
            if self.source_manager:
                result = await self.source_manager.fetch_source_content(source.id)
                # fetch_source_content 返回 (List[SourceContent], str) 元组
                if isinstance(result, tuple):
                    contents, _ = result
                    return contents if contents else []
                # 兼容旧版本直接返回列表
                elif isinstance(result, list):
                    return result
                elif result and hasattr(result, 'items'):
                    return result.items
            
            return []
            
        except Exception as e:
            logger.error(f"[Prefetcher] 抓取内容失败: {e}")
            raise
    
    def _calculate_content_hash(self, items: List) -> str:
        """计算内容哈希"""
        import hashlib
        
        # 使用标题和URL生成哈希
        hash_parts = []
        for item in items[:20]:  # 只取前20条
            if isinstance(item, dict):
                title = item.get('title', '')
                url = item.get('url', '')
            elif hasattr(item, 'title'):
                title = getattr(item, 'title', '')
                url = getattr(item, 'url', '') or getattr(item, 'link', '')
            else:
                title = str(item)
                url = ''
            hash_parts.append(f"{title}:{url}")
        
        content_str = "|".join(hash_parts)
        return hashlib.md5(content_str.encode()).hexdigest()[:16]
    
    # 源健康监控配置
    CONSECUTIVE_FAIL_THRESHOLD = 5      # 连续失败阈值，超过则自动停用
    AUTO_DISABLE_ENABLED = True         # 是否启用自动停用
    
    def _update_stats(
        self, 
        source_id: int, 
        success: bool, 
        fetch_time: float,
        content_count: int,
        has_update: bool
    ):
        """更新源统计"""
        stats = self._source_stats.get(source_id)
        if not stats:
            stats = SourceFetchStats(source_id=source_id)
            self._source_stats[source_id] = stats
        
        stats.total_fetches += 1
        
        if success:
            stats.success_count += 1
            stats.consecutive_fails = 0  # 重置连续失败计数
            
            # 更新平均抓取时间
            stats.avg_fetch_time = (
                stats.avg_fetch_time * 0.8 + fetch_time * 0.2
            )
            
            # 更新平均内容数
            stats.avg_content_count = (
                stats.avg_content_count * 0.8 + content_count * 0.2
            )
            
            # 更新频率分析
            if has_update and stats.last_update_time > 0:
                hours_since_update = (time.time() - stats.last_update_time) / 3600
                if hours_since_update > 0:
                    stats.update_frequency = (
                        stats.update_frequency * 0.7 + hours_since_update * 0.3
                    ) if stats.update_frequency > 0 else hours_since_update
            
            if has_update:
                stats.last_update_time = time.time()
        else:
            stats.fail_count += 1
            stats.consecutive_fails = getattr(stats, 'consecutive_fails', 0) + 1
            
            # 源健康监控：连续失败超过阈值，自动停用
            if self.AUTO_DISABLE_ENABLED and stats.consecutive_fails >= self.CONSECUTIVE_FAIL_THRESHOLD:
                self._auto_disable_source(source_id, stats.consecutive_fails)
    
    def _schedule_next_fetch(self, source_id: int):
        """调度下次抓取"""
        # 检查是否已被自动停用
        stats = self._source_stats.get(source_id)
        if stats and stats.disabled_at > 0:
            logger.debug(f"[Prefetcher] 源 {source_id} 已停用，跳过调度")
            return
        
        now = time.time()
        current_hour = datetime.now().hour
        
        priority, scheduled_time = self._calculate_schedule(
            source_id, 
            current_hour,
            now
        )
        
        task = FetchTask(
            source_id=source_id,
            priority=priority,
            scheduled_time=scheduled_time
        )
        
        self._add_task(task)
    
    def _auto_disable_source(self, source_id: int, fail_count: int):
        """
        自动停用连续失败的源
        
        Args:
            source_id: 源ID
            fail_count: 连续失败次数
        """
        try:
            logger.warning(f"[Prefetcher] 源 {source_id} 连续失败 {fail_count} 次，自动停用")
            
            # 更新统计
            stats = self._source_stats.get(source_id)
            if stats:
                stats.disabled_at = time.time()
            
            # 更新数据库中的源状态
            if self.source_manager and SourceStatus:
                source = self.source_manager.get_source(source_id)
                if source:
                    source.status = SourceStatus.ERROR
                    source.error_message = f"连续抓取失败 {fail_count} 次，已自动停用"
                    source.error_count = fail_count
                    self.source_manager.update_source(source)
                    logger.info(f"[Prefetcher] 源 {source_id} 已标记为错误状态")
            
            # 从任务队列中移除该源的任务
            self._task_queue = [t for t in self._task_queue if t.source_id != source_id]
            heapq.heapify(self._task_queue)
            
        except Exception as e:
            logger.error(f"[Prefetcher] 自动停用源 {source_id} 失败: {e}")
    
    def reactivate_source(self, source_id: int) -> bool:
        """
        重新激活被停用的源（管理员手动操作）
        
        Args:
            source_id: 源ID
            
        Returns:
            是否成功
        """
        try:
            stats = self._source_stats.get(source_id)
            if stats:
                stats.consecutive_fails = 0
                stats.disabled_at = 0
            
            # 更新数据库
            if self.source_manager and SourceStatus:
                source = self.source_manager.get_source(source_id)
                if source:
                    source.status = SourceStatus.ACTIVE
                    source.error_message = ""
                    source.error_count = 0
                    self.source_manager.update_source(source)
            
            # 重新加入调度
            self._schedule_next_fetch(source_id)
            
            logger.info(f"[Prefetcher] 源 {source_id} 已重新激活")
            return True
            
        except Exception as e:
            logger.error(f"[Prefetcher] 重新激活源 {source_id} 失败: {e}")
            return False
    
    # ==================== 公开接口 ====================
    
    async def get_cached_content(self, source_id: int) -> Optional[CachedContent]:
        """
        获取缓存的内容（不触发抓取）
        
        Args:
            source_id: 源ID
            
        Returns:
            CachedContent 或 None
        """
        return self._content_cache.get(source_id)
    
    def _get_adaptive_ttl(self, source_id: int) -> int:
        """
        P1优化：根据源的更新频率计算自适应TTL
        
        策略：
        - 高频更新源（<1小时）：TTL = 更新频率 * 0.5
        - 中频更新源（1-6小时）：TTL = 更新频率 * 0.7
        - 低频更新源（>6小时）：TTL = 更新频率 * 0.8
        - 未知频率：使用默认TTL
        
        Args:
            source_id: 源ID
            
        Returns:
            自适应TTL（秒）
        """
        stats = self._source_stats.get(source_id)
        if not stats or stats.update_frequency <= 0:
            return self.CACHE_TTL  # 默认2小时
        
        freq_hours = stats.update_frequency
        
        if freq_hours < 1:
            # 高频更新：TTL = 频率的50%
            ttl = int(freq_hours * 3600 * 0.5)
        elif freq_hours <= 6:
            # 中频更新：TTL = 频率的70%
            ttl = int(freq_hours * 3600 * 0.7)
        else:
            # 低频更新：TTL = 频率的80%
            ttl = int(freq_hours * 3600 * 0.8)
        
        # 确保在合理范围内
        return max(self.MIN_FETCH_INTERVAL, min(ttl, self.MAX_FETCH_INTERVAL))
    
    async def get_content(
        self, 
        source_id: int, 
        max_age: int = None,
        wait_for_fetch: bool = False,
        use_adaptive_ttl: bool = True
    ) -> Optional[CachedContent]:
        """
        获取内容（可选等待抓取）
        
        P1优化：支持自适应TTL
        
        Args:
            source_id: 源ID
            max_age: 最大缓存年龄（秒），None表示使用自适应TTL
            wait_for_fetch: 缓存过期时是否等待抓取
            use_adaptive_ttl: 是否使用自适应TTL（当max_age为None时生效）
            
        Returns:
            CachedContent 或 None
        """
        cached = self._content_cache.get(source_id)
        
        # P1优化：使用自适应TTL
        effective_max_age = max_age
        if effective_max_age is None and use_adaptive_ttl:
            effective_max_age = self._get_adaptive_ttl(source_id)
        
        # 检查缓存是否有效
        if cached:
            age = time.time() - cached.fetch_time
            if effective_max_age is None or age <= effective_max_age:
                return cached
        
        # 缓存过期或不存在
        if wait_for_fetch:
            # 触发立即抓取
            await self.trigger_fetch(source_id, priority=FetchPriority.URGENT)
            
            # 等待抓取完成（最多30秒）
            for _ in range(30):
                await asyncio.sleep(1)
                cached = self._content_cache.get(source_id)
                if cached and time.time() - cached.fetch_time < 60:
                    return cached
        
        # 返回旧缓存（如果有）
        return cached
    
    async def trigger_fetch(
        self, 
        source_id: int, 
        priority: FetchPriority = FetchPriority.HIGH
    ):
        """
        触发立即抓取
        
        Args:
            source_id: 源ID
            priority: 优先级
        """
        # 如果已在队列中，先移除
        if source_id in self._task_set:
            self._task_queue = [t for t in self._task_queue if t.source_id != source_id]
            heapq.heapify(self._task_queue)
            self._task_set.discard(source_id)
        
        # 添加高优先级任务
        task = FetchTask(
            source_id=source_id,
            priority=priority,
            scheduled_time=time.time()
        )
        self._add_task(task)
    
    async def get_batch_content(
        self, 
        source_ids: List[int],
        max_age: int = 3600
    ) -> Dict[int, CachedContent]:
        """
        批量获取内容
        
        Args:
            source_ids: 源ID列表
            max_age: 最大缓存年龄
            
        Returns:
            {source_id: CachedContent}
        """
        result = {}
        now = time.time()
        
        for source_id in source_ids:
            cached = self._content_cache.get(source_id)
            if cached and (now - cached.fetch_time) <= max_age:
                result[source_id] = cached
        
        return result
    
    def get_stats(self, source_id: int = None) -> Dict[str, Any]:
        """
        获取统计信息
        
        Args:
            source_id: 源ID，None表示获取全局统计
            
        Returns:
            统计信息字典
        """
        if source_id:
            stats = self._source_stats.get(source_id)
            if stats:
                return {
                    'source_id': source_id,
                    'total_fetches': stats.total_fetches,
                    'success_rate': stats.success_count / max(stats.total_fetches, 1),
                    'avg_fetch_time': round(stats.avg_fetch_time, 2),
                    'avg_content_count': round(stats.avg_content_count, 1),
                    'update_frequency_hours': round(stats.update_frequency, 1)
                }
            return {}
        
        # 全局统计
        total_sources = len(self._source_stats)
        total_fetches = sum(s.total_fetches for s in self._source_stats.values())
        total_success = sum(s.success_count for s in self._source_stats.values())
        
        return {
            'total_sources': total_sources,
            'total_fetches': total_fetches,
            'success_rate': total_success / max(total_fetches, 1),
            'queue_size': len(self._task_queue),
            'cache_size': len(self._content_cache),
            'push_time_coverage': len(self._push_time_index)
        }
    
    def get_queue_status(self) -> List[Dict]:
        """获取队列状态"""
        now = time.time()
        result = []
        
        for task in sorted(self._task_queue)[:20]:  # 只返回前20个
            result.append({
                'source_id': task.source_id,
                'priority': task.priority.name,
                'scheduled_in': round(task.scheduled_time - now, 1),
                'retry_count': task.retry_count
            })
        
        return result
    
    def mark_index_dirty(self):
        """
        标记索引需要重建
        
        当订阅发生变更时调用此方法，触发下次循环重建索引
        """
        self._index_dirty = True
        logger.debug("[Prefetcher] 索引已标记为需要重建")
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """
        获取性能摘要（用于监控）
        
        Returns:
            性能指标字典
        """
        stats = self.get_stats()
        return {
            **stats,
            'index_dirty': self._index_dirty,
            'last_index_build': self._last_index_build_time,
            'fetching_count': len(self._fetching_sources),
            'adaptive_ttl_enabled': True
        }


# 全局实例
_prefetcher: Optional[ContentPrefetcher] = None


def get_prefetcher() -> Optional[ContentPrefetcher]:
    """获取预抓取调度器实例"""
    return _prefetcher


def mark_prefetcher_index_dirty():
    """标记预抓取器索引需要重建（供外部调用）"""
    if _prefetcher:
        _prefetcher.mark_index_dirty()


def init_prefetcher(
    source_manager=None,
    cache_manager=None,
    subscription_manager=None
) -> ContentPrefetcher:
    """
    初始化预抓取调度器
    
    Args:
        source_manager: 订阅源管理器
        cache_manager: 缓存管理器
        subscription_manager: 订阅管理器
        
    Returns:
        ContentPrefetcher 实例
    """
    global _prefetcher
    _prefetcher = ContentPrefetcher(
        source_manager=source_manager,
        cache_manager=cache_manager,
        subscription_manager=subscription_manager
    )
    return _prefetcher
