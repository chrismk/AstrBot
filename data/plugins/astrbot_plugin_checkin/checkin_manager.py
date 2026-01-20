"""
签到管理器
处理签到逻辑、奖励计算、数据存储等
使用统一的 quota_system.db 数据库
"""
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
import random
from astrbot.api import logger


class CheckinManager:
    """签到管理器 - 使用统一数据库"""
    
    def __init__(self, db_manager, points_manager, config: Dict[str, Any]):
        """
        初始化签到管理器
        
        Args:
            db_manager: 统一的 DatabaseManager 实例（quota_system.db）
            points_manager: 积分管理器
            config: 签到配置
        """
        self.db = db_manager
        self.points_manager = points_manager
        self.config = config
        self._init_tables()
    
    def _init_tables(self):
        """初始化签到相关表（在统一数据库中）"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # 签到记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS checkin_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    checkin_date DATE NOT NULL,
                    points_earned INTEGER NOT NULL,
                    is_lucky BOOLEAN DEFAULT 0,
                    is_makeup BOOLEAN DEFAULT 0,
                    streak_days INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, checkin_date)
                )
            """)
            
            # 用户签到统计表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS checkin_stats (
                    user_id TEXT PRIMARY KEY,
                    total_days INTEGER DEFAULT 0,
                    current_streak INTEGER DEFAULT 0,
                    max_streak INTEGER DEFAULT 0,
                    last_checkin_date DATE,
                    total_points INTEGER DEFAULT 0,
                    lucky_count INTEGER DEFAULT 0,
                    makeup_count INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_checkin_user_date 
                ON checkin_records(user_id, checkin_date DESC)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_checkin_date 
                ON checkin_records(checkin_date DESC)
            """)
            
            conn.commit()
            
        logger.info("[CheckinManager] 签到表初始化完成（统一数据库）")
    
    async def daily_checkin(self, user_id: str) -> str:
        """每日签到"""
        today = date.today()
        
        # 检查今天是否已签到
        if self._is_checked_in_today(user_id, today):
            return "❌ 您今天已经签到过了\n\n💡 明天再来吧！"
        
        # 获取用户统计信息
        stats = self._get_user_stats(user_id)
        
        # 计算连续签到天数
        current_streak = self._calculate_streak(user_id, stats)
        
        # 计算奖励
        reward_info = self._calculate_reward(current_streak)
        
        # 保存签到记录
        self._save_checkin_record(
            user_id=user_id,
            checkin_date=today,
            points_earned=reward_info['total_points'],
            is_lucky=reward_info['is_lucky'],
            streak_days=current_streak
        )
        
        # 更新统计信息
        self._update_stats(user_id, current_streak, reward_info)
        
        # 发放积分
        await self.points_manager.recharge(
            user_id=user_id,
            amount=reward_info['total_points'],
            description=f"签到奖励（第{current_streak}天）"
        )
        
        # 追踪任务进度
        try:
            from common.task_tracker import get_task_tracker
            tracker = get_task_tracker()
            tracker.track_checkin(user_id)
        except Exception as e:
            logger.debug(f"[CheckinManager] 任务追踪失败: {e}")
        
        # 检查是否全勤
        perfect_bonus = self._check_perfect_month(user_id, today)
        if perfect_bonus > 0:
            await self.points_manager.recharge(
                user_id=user_id,
                amount=perfect_bonus,
                description="本月全勤奖励"
            )
        
        # 生成签到结果
        return await self._format_checkin_result(user_id, reward_info, current_streak, perfect_bonus)
    
    def _is_checked_in_today(self, user_id: str, today: date) -> bool:
        """检查今天是否已签到"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COUNT(*) as count FROM checkin_records
                WHERE user_id = ? AND checkin_date = ?
            """, (user_id, today))
            
            result = cursor.fetchone()
            
            return result['count'] > 0
    
    def _get_user_stats(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户统计信息"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM checkin_stats WHERE user_id = ?
            """, (user_id,))
            
            result = cursor.fetchone()
            
            if result:
                return dict(result)
            return None
    
    def _calculate_streak(self, user_id: str, stats: Optional[Dict[str, Any]]) -> int:
        """计算连续签到天数"""
        if not stats or not stats.get('last_checkin_date'):
            return 1
        
        last_date = datetime.strptime(stats['last_checkin_date'], '%Y-%m-%d').date()
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        # 如果昨天签到了，连续天数+1
        if last_date == yesterday:
            return stats['current_streak'] + 1
        # 如果今天签到了（补签情况），保持连续天数
        elif last_date == today:
            return stats['current_streak']
        # 否则重新开始
        else:
            return 1
    
    def _calculate_reward(self, streak_days: int) -> Dict[str, Any]:
        """计算签到奖励"""
        rewards_config = self.config.get('rewards', {})
        
        # 基础奖励
        base_points = rewards_config.get('base_points', 10)
        
        # 随机奖励
        random_min = rewards_config.get('random_points_min', 1)
        random_max = rewards_config.get('random_points_max', 20)
        random_points = random.randint(random_min, random_max)
        
        # 连续签到奖励倍数
        streak_bonus_config = rewards_config.get('streak_bonus', {})
        streak_multiplier = 1.0
        
        for days, multiplier in sorted(streak_bonus_config.items(), reverse=True):
            if streak_days >= int(days):
                streak_multiplier = multiplier
                break
        
        # 幸运签到
        lucky_chance = rewards_config.get('lucky_chance', 0.1)
        is_lucky = random.random() < lucky_chance
        
        lucky_multiplier = 1.0
        if is_lucky:
            lucky_multiplier = rewards_config.get('lucky_multiplier', 2.0)
        
        # 计算总奖励
        total_points = int((base_points + random_points) * streak_multiplier * lucky_multiplier)
        
        return {
            'base_points': base_points,
            'random_points': random_points,
            'streak_multiplier': streak_multiplier,
            'is_lucky': is_lucky,
            'lucky_multiplier': lucky_multiplier,
            'total_points': total_points
        }
    
    def _save_checkin_record(self, user_id: str, checkin_date: date, points_earned: int, 
                            is_lucky: bool, streak_days: int, is_makeup: bool = False):
        """保存签到记录"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO checkin_records 
                (user_id, checkin_date, points_earned, is_lucky, is_makeup, streak_days)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, checkin_date, points_earned, is_lucky, is_makeup, streak_days))
            
            conn.commit()
    
    def _update_stats(self, user_id: str, current_streak: int, reward_info: Dict[str, Any]):
        """更新用户统计信息"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            stats = self._get_user_stats(user_id)
            
            if stats:
                # 更新现有记录
                total_days = stats['total_days'] + 1
                max_streak = max(stats['max_streak'], current_streak)
                total_points = stats['total_points'] + reward_info['total_points']
                lucky_count = stats['lucky_count'] + (1 if reward_info['is_lucky'] else 0)
                
                cursor.execute("""
                    UPDATE checkin_stats
                    SET total_days = ?,
                        current_streak = ?,
                        max_streak = ?,
                        last_checkin_date = ?,
                        total_points = ?,
                        lucky_count = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (total_days, current_streak, max_streak, date.today(), 
                      total_points, lucky_count, user_id))
            else:
                # 创建新记录
                cursor.execute("""
                    INSERT INTO checkin_stats
                    (user_id, total_days, current_streak, max_streak, last_checkin_date, 
                     total_points, lucky_count)
                    VALUES (?, 1, ?, ?, ?, ?, ?)
                """, (user_id, current_streak, current_streak, date.today(), 
                      reward_info['total_points'], 1 if reward_info['is_lucky'] else 0))
            
            conn.commit()
    
    def _check_perfect_month(self, user_id: str, today: date) -> int:
        """检查是否本月全勤"""
        # 获取本月第一天和最后一天
        first_day = today.replace(day=1)
        
        # 如果不是月末，返回0
        next_month = today.replace(day=28) + timedelta(days=4)
        last_day = next_month - timedelta(days=next_month.day)
        
        if today != last_day:
            return 0
        
        # 检查本月每天是否都签到了
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COUNT(DISTINCT checkin_date) as count
                FROM checkin_records
                WHERE user_id = ? 
                AND checkin_date >= ? 
                AND checkin_date <= ?
            """, (user_id, first_day, last_day))
            
            result = cursor.fetchone()
        
        # 计算本月应有的天数
        days_in_month = (last_day - first_day).days + 1
        
        if result['count'] == days_in_month:
            return self.config.get('rewards', {}).get('perfect_month_bonus', 200)
        
        return 0
    
    async def _format_checkin_result(self, user_id: str, reward_info: Dict[str, Any], streak_days: int, 
                               perfect_bonus: int = 0) -> str:
        """格式化签到结果"""
        result = "✅ 签到成功！\n\n"
        
        # 幸运签到特效
        if reward_info['is_lucky']:
            result += "🎉 恭喜！触发幸运签到！\n\n"
        
        result += f"📅 签到日期：{date.today()}\n"
        result += f"🔥 连续签到：{streak_days}天\n\n"
        
        result += "💰 本次奖励：\n"
        result += f"  • 基础奖励：{reward_info['base_points']}积分\n"
        result += f"  • 随机奖励：{reward_info['random_points']}积分\n"
        
        if reward_info['streak_multiplier'] > 1.0:
            result += f"  • 连续奖励：x{reward_info['streak_multiplier']}\n"
        
        if reward_info['is_lucky']:
            result += f"  • 幸运加成：x{reward_info['lucky_multiplier']}\n"
        
        result += f"\n💎 获得积分：{reward_info['total_points']}\n"
        
        if perfect_bonus > 0:
            result += f"\n🎊 本月全勤奖励：{perfect_bonus}积分\n"
        
        # 获取当前积分余额
        try:
            account = await self.points_manager.get_account_info(user_id)
            current_balance = account.get('balance', 0) if account else 0
            result += f"\n💳 当前积分：{current_balance}\n"
        except Exception as e:
            logger.debug(f"[签到] 获取积分余额失败: {e}")
        
        # 连续签到提示
        if streak_days in [2, 6, 14, 29]:
            next_milestone = {2: 3, 6: 7, 14: 15, 29: 30}[streak_days]
            result += f"\n💡 再签到1天即可获得{next_milestone}天连续奖励！"
        
        return result
    
    async def makeup_checkin(self, user_id: str, date_str: str) -> str:
        """补签功能"""
        makeup_config = self.config.get('makeup', {})
        
        # 检查是否启用补签
        if not makeup_config.get('enabled', True):
            return "❌ 补签功能未启用"
        
        # 解析日期
        target_date = self._parse_date(date_str)
        if not target_date:
            return "❌ 日期格式错误\n\n💡 支持格式：1(昨天)、2(前天)、3(大前天)、昨天、前天、大前天、2024-01-15"
        
        today = date.today()
        
        # 检查日期是否在允许范围内
        max_days = makeup_config.get('max_days', 7)
        earliest_date = today - timedelta(days=max_days)
        
        if target_date > today:
            return "❌ 不能补签未来的日期"
        
        if target_date < earliest_date:
            return f"❌ 只能补签最近{max_days}天的记录"
        
        if target_date == today:
            return "❌ 今天请直接使用 /签 命令签到"
        
        # 检查是否已经签到
        if self._is_checked_in_today(user_id, target_date):
            return f"❌ {target_date} 已经签到过了"
        
        # 检查积分是否足够
        makeup_cost = makeup_config.get('cost', 50)
        account = await self.points_manager.get_account_info(user_id)
        
        if not account or account.get('balance', 0) < makeup_cost:
            return f"❌ 积分不足\n\n需要：{makeup_cost}积分\n当前：{account.get('balance', 0) if account else 0}积分"
        
        # 扣除积分（使用负数充值）
        success = await self.points_manager.recharge(
            user_id=user_id,
            amount=-makeup_cost,  # 负数表示扣除
            description=f"补签消耗 {target_date}"
        )
        
        if not success:
            return "❌ 积分扣除失败"
        
        # 计算补签奖励（基础奖励，无额外加成）
        base_points = self.config.get('rewards', {}).get('base_points', 10)
        
        # 保存补签记录
        self._save_checkin_record(
            user_id=user_id,
            checkin_date=target_date,
            points_earned=base_points,
            is_lucky=False,
            streak_days=1,
            is_makeup=True
        )
        
        # 发放基础积分
        await self.points_manager.recharge(
            user_id=user_id,
            amount=base_points,
            description=f"补签奖励 {target_date}"
        )
        
        # 更新补签统计
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE checkin_stats
                SET makeup_count = makeup_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (user_id,))
            conn.commit()
        
        result = f"✅ 补签成功！\n\n"
        result += f"📅 补签日期：{target_date}\n"
        result += f"💰 消耗积分：{makeup_cost}\n"
        result += f"💎 获得积分：{base_points}\n\n"
        result += "💡 补签不影响连续签到天数"
        
        return result
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """解析日期字符串"""
        today = date.today()
        
        # 数字快捷方式映射
        numeric_shortcuts = {
            '1': '昨天',
            '2': '前天',
            '3': '大前天',
        }
        
        # 检查数字快捷方式
        if date_str in numeric_shortcuts:
            date_str = numeric_shortcuts[date_str]
        
        # 处理中文日期
        if date_str == "昨天":
            return today - timedelta(days=1)
        elif date_str == "前天":
            return today - timedelta(days=2)
        elif date_str == "大前天":
            return today - timedelta(days=3)
        
        # 处理标准日期格式
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
        
        # 处理其他格式
        try:
            return datetime.strptime(date_str, '%Y/%m/%d').date()
        except ValueError:
            pass
        
        return None
    
    async def get_checkin_history(self, user_id: str) -> str:
        """获取签到历史"""
        stats = self._get_user_stats(user_id)
        
        if not stats:
            return "📊 签到记录\n\n暂无签到记录\n\n💡 使用 /签 开始签到"
        
        # 获取最近7天的签到记录
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT checkin_date, points_earned, is_lucky, is_makeup, streak_days
                FROM checkin_records
                WHERE user_id = ?
                ORDER BY checkin_date DESC
                LIMIT 7
            """, (user_id,))
            
            records = cursor.fetchall()
        
        result = "📊 签到记录\n\n"
        result += f"👤 用户统计：\n"
        result += f"  • 累计签到：{stats['total_days']}天\n"
        result += f"  • 连续签到：{stats['current_streak']}天\n"
        result += f"  • 最长连续：{stats['max_streak']}天\n"
        result += f"  • 累计积分：{stats['total_points']}\n"
        result += f"  • 幸运次数：{stats['lucky_count']}次\n"
        result += f"  • 补签次数：{stats['makeup_count']}次\n\n"
        
        if records:
            result += "📅 最近7天：\n"
            for record in records:
                date_str = record['checkin_date']
                points = record['points_earned']
                is_lucky = record['is_lucky']
                is_makeup = record['is_makeup']
                streak = record['streak_days']
                
                status = ""
                if is_lucky:
                    status = "🎉"
                if is_makeup:
                    status += "🔧"
                
                result += f"  • {date_str} {status}\n"
                result += f"    积分: {points} | 连续: {streak}天\n"
        
        return result
    
    async def get_leaderboard(self) -> str:
        """获取签到排行榜"""
        top_count = self.config.get('leaderboard', {}).get('top_count', 10)
        
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # 连续签到排行
            cursor.execute("""
                SELECT cs.user_id, cs.current_streak, cs.total_days, cs.total_points,
                       u.username
                FROM checkin_stats cs
                LEFT JOIN users u ON cs.user_id = u.user_id
                WHERE cs.current_streak > 0
                ORDER BY cs.current_streak DESC, cs.total_days DESC
                LIMIT ?
            """, (top_count,))
            
            streak_records = cursor.fetchall()
            
            # 累计签到排行
            cursor.execute("""
                SELECT cs.user_id, cs.total_days, cs.current_streak, cs.total_points,
                       u.username
                FROM checkin_stats cs
                LEFT JOIN users u ON cs.user_id = u.user_id
                ORDER BY cs.total_days DESC, cs.total_points DESC
                LIMIT ?
            """, (top_count,))
            
            total_records = cursor.fetchall()
        
        result = "🏆 签到排行榜\n\n"
        
        # 连续签到排行
        result += "🔥 连续签到榜：\n"
        if streak_records:
            for i, record in enumerate(streak_records, 1):
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
                display_name = self._get_display_name(record)
                result += f"{medal} {display_name} - {record['current_streak']}天\n"
        else:
            result += "暂无数据\n"
        
        result += "\n📊 累计签到榜：\n"
        if total_records:
            for i, record in enumerate(total_records, 1):
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
                display_name = self._get_display_name(record)
                result += f"{medal} {display_name} - {record['total_days']}天\n"
        else:
            result += "暂无数据\n"
        
        return result
    
    def _get_display_name(self, record) -> str:
        """获取用户显示名称（优先用户名，否则截断ID）"""
        username = record['username'] if 'username' in record.keys() else None
        if username:
            # 用户名过长则截断
            if len(username) > 12:
                return username[:10] + "..."
            return username
        # 无用户名则显示截断的 user_id
        user_id = record['user_id']
        return user_id[:8] + "..."
