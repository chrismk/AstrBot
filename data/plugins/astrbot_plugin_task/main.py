"""
每日任务系统插件

功能：
1. 查看每日/每周/每月任务
2. 任务进度追踪
3. 奖励领取
4. 任务完成通知

命令：
- /任务 或 /task - 查看任务列表
- /任务 每日 - 查看每日任务
- /任务 每周 - 查看每周任务
- /任务 每月 - 查看每月任务
- /任务 领取 - 一键领取所有奖励
"""

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star
from astrbot.api.message_components import Plain, Image
from astrbot.api import logger

from astrbot.api.event.filter import command_group

import os

from common import (
    DatabaseManager,
    get_platform_capabilities,
    MessageEditor,
    get_unified_user_id,
    PointsManager,
    get_separator
)
from common.task_manager import (
    TaskManager,
    get_task_manager,
    TaskType,
    TaskTrigger,
    register_task_scheduler_jobs
)
from common.task_tracker import get_task_tracker


class TaskPlugin(Star):
    """每日任务系统插件"""
    
    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context
        self.task_manager = None
        self.db = None
    
    async def _ensure_initialized(self) -> bool:
        """确保初始化"""
        if self.task_manager is not None:
            return True
        
        try:
            # 获取数据库路径
            data_path = self.context.get_data_path()
            db_path = os.path.join(data_path, "quota_system.db")
            
            self.db = DatabaseManager(db_path)
            if not self.db:
                logger.error("[TaskPlugin] 数据库管理器不可用")
                return False
            
            # 初始化积分管理器
            points_manager = PointsManager(self.db)
            
            self.task_manager = get_task_manager(self.db, points_manager)
            
            # 初始化追踪器
            get_task_tracker(self.task_manager)
            
            # 注册定时任务（任务重置）
            try:
                register_task_scheduler_jobs()
            except Exception as e:
                logger.warning(f"[TaskPlugin] 定时任务注册失败: {e}")
            
            logger.info("[TaskPlugin] 初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"[TaskPlugin] 初始化失败: {e}")
            return False
    
    @filter.command_group("任务", "task")
    async def task_command(self, event: AstrMessageEvent, sub_cmd: str = ""):
        """任务命令入口"""
        if not await self._ensure_initialized():
            yield event.plain_result("❌ 任务系统暂不可用")
            return
        
        user_id = get_unified_user_id(event)
        capabilities = get_platform_capabilities(event, "Task")
        
        sub_cmd = sub_cmd.strip().lower()
        
        if sub_cmd in ("每日", "daily", "d", ""):
            async for result in self._show_tasks(event, user_id, TaskType.DAILY, capabilities):
                yield result
        elif sub_cmd in ("每周", "weekly", "w"):
            async for result in self._show_tasks(event, user_id, TaskType.WEEKLY, capabilities):
                yield result
        elif sub_cmd in ("每月", "monthly", "m"):
            async for result in self._show_tasks(event, user_id, TaskType.MONTHLY, capabilities):
                yield result
        elif sub_cmd in ("领取", "claim", "c"):
            async for result in self._claim_all(event, user_id):
                yield result
        elif sub_cmd in ("统计", "stats", "s"):
            async for result in self._show_stats(event, user_id):
                yield result
        else:
            async for result in self._show_tasks(event, user_id, TaskType.DAILY, capabilities):
                yield result
    
    async def _show_tasks(self, event: AstrMessageEvent, user_id: str, task_type: TaskType, capabilities: dict):
        """显示任务列表"""
        tasks = self.task_manager.get_user_tasks(user_id, task_type)
        
        type_names = {
            TaskType.DAILY: "每日",
            TaskType.WEEKLY: "每周",
            TaskType.MONTHLY: "每月"
        }
        type_name = type_names.get(task_type, "")
        
        # 统计
        completed = sum(1 for _, p in tasks if p.completed)
        total = len(tasks)
        claimable = sum(1 for _, p in tasks if p.is_claimable)
        claimable_points = sum(t.reward_points for t, p in tasks if p.is_claimable)
        
        message = f"📋 {type_name}任务 ({completed}/{total} 已完成)\n\n"
        
        for task, progress in tasks:
            # 状态图标
            if progress.reward_claimed:
                status = "✅"
            elif progress.completed:
                status = "🎁"  # 可领取
            else:
                status = "⬜"
            
            # 进度显示
            progress_str = f"[{progress.progress}/{progress.target}]"
            
            # 奖励显示
            reward_str = f"+{task.reward_points}积分"
            if progress.reward_claimed:
                reward_str = "✓已领取"
            elif progress.completed:
                reward_str = f"[领取 +{task.reward_points}]"
            
            message += f"{status} {task.icon} {task.name} {progress_str} {reward_str}\n"
        
        separator = get_separator()
        message += f"\n{separator}"
        
        if claimable > 0:
            message += f"\n💰 可领取: {claimable_points}积分 ({claimable}个任务)"
        
        # 获取总统计
        stats = self.task_manager.get_completion_stats(user_id)
        message += f"\n📊 累计获得: {stats.get('total_points_earned', 0)}积分"
        
        if capabilities.get('supports_buttons'):
            buttons = [
                [
                    {"text": "📅 每日", "callback_data": "task:daily"},
                    {"text": "📆 每周", "callback_data": "task:weekly"},
                    {"text": "📆 每月", "callback_data": "task:monthly"}
                ]
            ]
            
            if claimable > 0:
                buttons.append([
                    {"text": f"🎁 一键领取 (+{claimable_points})", "callback_data": "task:claim"}
                ])
            
            buttons.append([
                {"text": "📊 统计", "callback_data": "task:stats"},
                {"text": "❌ 关闭", "callback_data": "task:exit"}
            ])
            
            from astrbot.api.message_components import InlineKeyboard
            keyboard = InlineKeyboard(buttons=buttons)
            
            async for result in MessageEditor.edit_or_send(event, message, keyboard):
                yield result
        else:
            message += "\n\n💡 回复: d-每日 | w-每周 | m-每月 | c-领取"
            yield event.plain_result(message)
    
    async def _claim_all(self, event: AstrMessageEvent, user_id: str):
        """一键领取所有奖励"""
        count, total_points = self.task_manager.claim_all_rewards(user_id)
        
        if count > 0:
            yield event.plain_result(f"🎉 领取成功！\n\n获得 {total_points} 积分（{count}个任务）")
        else:
            yield event.plain_result("📭 暂无可领取的奖励\n\n完成更多任务来获取奖励吧！")
    
    async def _show_stats(self, event: AstrMessageEvent, user_id: str):
        """显示统计信息"""
        stats = self.task_manager.get_completion_stats(user_id)
        
        message = "📊 任务统计\n\n"
        
        for key, name in [('daily', '每日'), ('weekly', '每周'), ('monthly', '每月')]:
            s = stats.get(key, {})
            message += f"{name}任务: {s.get('completed', 0)}/{s.get('total', 0)} 完成"
            message += f" (+{s.get('points', 0)}积分)\n"
        
        message += f"\n💰 累计获得: {stats.get('total_points_earned', 0)}积分"
        
        # 排行榜
        leaderboard = self.task_manager.get_leaderboard(days=7, limit=5)
        if leaderboard:
            message += "\n\n🏆 本周排行榜:\n"
            for i, entry in enumerate(leaderboard, 1):
                uid = entry['user_id']
                # 脱敏显示
                display_id = uid[:8] + "..." if len(uid) > 10 else uid
                message += f"{i}. {display_id} - {entry['total_points']}积分\n"
        
        yield event.plain_result(message)
    
    @filter.command("callback")
    async def handle_callback(self, event: AstrMessageEvent, data: str = ""):
        """处理回调"""
        if not data.startswith("task:"):
            return
        
        if not await self._ensure_initialized():
            yield event.plain_result("❌ 任务系统暂不可用")
            return
        
        data = data[5:]  # 去掉 "task:" 前缀
        user_id = get_unified_user_id(event)
        capabilities = get_platform_capabilities(event, "Task")
        
        if data == "daily":
            async for result in self._show_tasks(event, user_id, TaskType.DAILY, capabilities):
                yield result
        elif data == "weekly":
            async for result in self._show_tasks(event, user_id, TaskType.WEEKLY, capabilities):
                yield result
        elif data == "monthly":
            async for result in self._show_tasks(event, user_id, TaskType.MONTHLY, capabilities):
                yield result
        elif data == "claim":
            async for result in self._claim_all(event, user_id):
                yield result
        elif data == "stats":
            async for result in self._show_stats(event, user_id):
                yield result
        elif data == "exit":
            # 删除消息
            try:
                platform_name = event.get_platform_name()
                msg_id = getattr(event.message_obj, 'message_id', None)
                if msg_id and platform_name == "telegram":
                    chat_id = event.message_obj.group_id or event.get_sender_id()
                    await event.client.delete_message(chat_id=chat_id, message_id=int(msg_id))
            except Exception as e:
                logger.debug(f"[TaskPlugin] 删除消息失败: {e}")
