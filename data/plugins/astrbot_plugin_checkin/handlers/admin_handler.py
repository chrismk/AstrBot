"""
管理员处理器
处理签到系统的管理功能，可集成到配额管理插件的 /管理 命令中
"""
from typing import List, Dict, Any
from astrbot.api import logger


class AdminHandler:
    """管理员处理器"""
    
    def __init__(self, checkin_manager, points_manager, admins: List[str], config: Dict[str, Any]):
        self.checkin_manager = checkin_manager
        self.points_manager = points_manager
        self.admins = admins
        self.config = config
    
    def _is_admin(self, user_id: str) -> bool:
        """检查是否为管理员"""
        return user_id in self.admins
    
    async def get_checkin_stats(self) -> str:
        """获取签到统计"""
        try:
            conn = self.checkin_manager._get_connection()
            cursor = conn.cursor()
            
            # 总签到人数
            cursor.execute("SELECT COUNT(DISTINCT user_id) as count FROM checkin_stats")
            total_users = cursor.fetchone()['count']
            
            # 今日签到人数
            from datetime import date
            today = date.today()
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) as count 
                FROM checkin_records 
                WHERE checkin_date = ?
            """, (today,))
            today_count = cursor.fetchone()['count']
            
            # 总签到次数
            cursor.execute("SELECT SUM(total_days) as total FROM checkin_stats")
            total_checkins = cursor.fetchone()['total'] or 0
            
            # 总发放积分
            cursor.execute("SELECT SUM(total_points) as total FROM checkin_stats")
            total_points = cursor.fetchone()['total'] or 0
            
            # 最长连续签到
            cursor.execute("SELECT MAX(max_streak) as max FROM checkin_stats")
            max_streak = cursor.fetchone()['max'] or 0
            
            # 幸运签到次数
            cursor.execute("SELECT SUM(lucky_count) as total FROM checkin_stats")
            lucky_total = cursor.fetchone()['total'] or 0
            
            # 补签次数
            cursor.execute("SELECT SUM(makeup_count) as total FROM checkin_stats")
            makeup_total = cursor.fetchone()['total'] or 0
            
            conn.close()
            
            result = "📊 签到系统统计\n\n"
            result += f"👥 签到用户：{total_users}人\n"
            result += f"📅 今日签到：{today_count}人\n"
            result += f"✅ 总签到次数：{total_checkins}次\n"
            result += f"💰 总发放积分：{total_points}\n"
            result += f"🔥 最长连续：{max_streak}天\n"
            result += f"🎉 幸运签到：{lucky_total}次\n"
            result += f"🔧 补签次数：{makeup_total}次\n"
            
            return result
            
        except Exception as e:
            logger.error(f"[AdminHandler] 获取签到统计失败: {e}", exc_info=True)
            return f"❌ 获取统计失败: {e}"
    
    async def update_base_reward(self, admin_id: str, new_value: int) -> str:
        """更新基础奖励"""
        if not self._is_admin(admin_id):
            return "❌ 权限不足"
        
        if new_value <= 0:
            return "❌ 基础奖励必须大于0"
        
        try:
            # 更新配置（注意：这里只是内存中的配置，需要持久化到文件）
            self.config['rewards']['base_points'] = new_value
            
            result = f"✅ 基础奖励已更新\n\n"
            result += f"新值：{new_value}积分\n\n"
            result += "💡 注意：需要重启插件才能永久生效"
            
            logger.info(f"[AdminHandler] 管理员 {admin_id} 更新基础奖励为 {new_value}")
            return result
            
        except Exception as e:
            logger.error(f"[AdminHandler] 更新基础奖励失败: {e}", exc_info=True)
            return f"❌ 更新失败: {e}"
    
    async def update_random_reward(self, admin_id: str, min_value: int, max_value: int) -> str:
        """更新随机奖励范围"""
        if not self._is_admin(admin_id):
            return "❌ 权限不足"
        
        if min_value <= 0 or max_value <= 0:
            return "❌ 奖励值必须大于0"
        
        if min_value > max_value:
            return "❌ 最小值不能大于最大值"
        
        try:
            self.config['rewards']['random_points_min'] = min_value
            self.config['rewards']['random_points_max'] = max_value
            
            result = f"✅ 随机奖励已更新\n\n"
            result += f"范围：{min_value}-{max_value}积分\n\n"
            result += "💡 注意：需要重启插件才能永久生效"
            
            logger.info(f"[AdminHandler] 管理员 {admin_id} 更新随机奖励为 {min_value}-{max_value}")
            return result
            
        except Exception as e:
            logger.error(f"[AdminHandler] 更新随机奖励失败: {e}", exc_info=True)
            return f"❌ 更新失败: {e}"
    
    async def update_makeup_cost(self, admin_id: str, new_cost: int) -> str:
        """更新补签消耗"""
        if not self._is_admin(admin_id):
            return "❌ 权限不足"
        
        if new_cost < 0:
            return "❌ 补签消耗不能为负数"
        
        try:
            self.config['makeup']['cost'] = new_cost
            
            result = f"✅ 补签消耗已更新\n\n"
            result += f"新值：{new_cost}积分\n\n"
            result += "💡 注意：需要重启插件才能永久生效"
            
            logger.info(f"[AdminHandler] 管理员 {admin_id} 更新补签消耗为 {new_cost}")
            return result
            
        except Exception as e:
            logger.error(f"[AdminHandler] 更新补签消耗失败: {e}", exc_info=True)
            return f"❌ 更新失败: {e}"
    
    async def reset_user_checkin(self, admin_id: str, target_user_id: str) -> str:
        """重置用户签到"""
        if not self._is_admin(admin_id):
            return "❌ 权限不足"
        
        try:
            conn = self.checkin_manager._get_connection()
            cursor = conn.cursor()
            
            # 删除签到记录
            cursor.execute("DELETE FROM checkin_records WHERE user_id = ?", (target_user_id,))
            
            # 删除统计信息
            cursor.execute("DELETE FROM checkin_stats WHERE user_id = ?", (target_user_id,))
            
            conn.commit()
            conn.close()
            
            result = f"✅ 用户签到已重置\n\n"
            result += f"用户ID：{target_user_id}\n"
            result += "所有签到记录和统计信息已清除"
            
            logger.info(f"[AdminHandler] 管理员 {admin_id} 重置用户 {target_user_id} 的签到")
            return result
            
        except Exception as e:
            logger.error(f"[AdminHandler] 重置用户签到失败: {e}", exc_info=True)
            return f"❌ 重置失败: {e}"
