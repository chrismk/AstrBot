"""
用户反馈管理器

功能：
1. 用户提交反馈（建议/Bug/投诉/表扬）
2. 管理员查看和回复反馈
3. 反馈状态管理
4. 反馈统计

使用示例：
    from common.feedback import FeedbackManager, get_feedback_manager
    
    # 获取实例
    feedback_mgr = get_feedback_manager(db_manager)
    
    # 用户提交反馈
    feedback_id = feedback_mgr.submit_feedback(
        user_id="telegram:123456",
        content="希望增加批量下载功能",
        feedback_type="suggestion",
        plugin_name="music"
    )
    
    # 管理员回复
    feedback_mgr.reply_feedback(
        feedback_id=feedback_id,
        admin_id="admin_001",
        reply="感谢您的建议，我们会考虑添加此功能",
        status="resolved"
    )
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from .database_manager import DatabaseManager


class FeedbackManager:
    """用户反馈管理器"""
    
    # 反馈类型
    FEEDBACK_TYPES = {
        'suggestion': '💡 建议',
        'bug': '🐛 Bug',
        'complaint': '😤 投诉',
        'praise': '👍 表扬',
        'source_request': '📰 订阅源申请'
    }
    
    # 反馈状态
    STATUS_NAMES = {
        'pending': '⏳ 待处理',
        'processing': '🔄 处理中',
        'resolved': '✅ 已解决',
        'rejected': '❌ 已拒绝',
        'approved': '✅ 已通过'
    }
    
    def __init__(self, db: DatabaseManager):
        """
        初始化反馈管理器
        
        Args:
            db: 数据库管理器实例
        """
        self.db = db
    
    # ==================== 用户操作 ====================
    
    def submit_feedback(
        self,
        user_id: str,
        content: str,
        feedback_type: str = "suggestion",
        plugin_name: str = None
    ) -> Optional[int]:
        """
        提交反馈
        
        Args:
            user_id: 用户ID（统一格式 platform:raw_id）
            content: 反馈内容
            feedback_type: 反馈类型 (suggestion/bug/complaint/praise)
            plugin_name: 相关插件名称（可选）
            
        Returns:
            反馈ID，失败返回 None
        """
        if feedback_type not in self.FEEDBACK_TYPES:
            feedback_type = "suggestion"
        
        try:
            now = datetime.now()
            
            # 在同一个连接中执行插入和获取ID
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO user_feedback 
                    (user_id, plugin_name, feedback_type, content, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """, (user_id, plugin_name, feedback_type, content, now, now))
                
                # 在同一个连接中获取刚插入的ID
                feedback_id = cursor.lastrowid
                conn.commit()
            
            logger.info(f"[Feedback] 用户 {user_id} 提交反馈 #{feedback_id}: {feedback_type}")
            return feedback_id
            
        except Exception as e:
            logger.error(f"[Feedback] 提交反馈失败: {e}")
            return None
    
    def get_user_feedbacks(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取用户的反馈列表
        
        Args:
            user_id: 用户ID
            limit: 返回数量限制
            
        Returns:
            反馈列表
        """
        try:
            rows = self.db.execute("""
                SELECT id, plugin_name, feedback_type, content, status, 
                       admin_reply, created_at, replied_at
                FROM user_feedback
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, limit))
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error(f"[Feedback] 获取用户反馈失败: {e}")
            return []
    
    def get_feedback_by_id(self, feedback_id: int) -> Optional[Dict[str, Any]]:
        """
        根据ID获取反馈详情
        
        Args:
            feedback_id: 反馈ID
            
        Returns:
            反馈详情
        """
        try:
            row = self.db.execute_one("""
                SELECT f.*, u.username
                FROM user_feedback f
                LEFT JOIN users u ON f.user_id = u.user_id
                WHERE f.id = ?
            """, (feedback_id,))
            
            return dict(row) if row else None
            
        except Exception as e:
            logger.error(f"[Feedback] 获取反馈详情失败: {e}")
            return None
    
    # ==================== 管理员操作 ====================
    
    def get_feedback_list(
        self,
        status: str = None,
        plugin_name: str = None,
        limit: int = 20,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        获取反馈列表（管理员）
        
        Args:
            status: 状态筛选（可选）
            plugin_name: 插件筛选（可选）
            limit: 返回数量
            offset: 偏移量
            
        Returns:
            {feedbacks: [...], total: int, pending_count: int}
        """
        try:
            # 构建查询条件
            conditions = []
            params = []
            
            if status:
                conditions.append("f.status = ?")
                params.append(status)
            
            if plugin_name:
                conditions.append("f.plugin_name = ?")
                params.append(plugin_name)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            # 查询列表
            query = f"""
                SELECT f.id, f.user_id, f.plugin_name, f.feedback_type, 
                       f.content, f.status, f.admin_reply, f.created_at,
                       u.username
                FROM user_feedback f
                LEFT JOIN users u ON f.user_id = u.user_id
                WHERE {where_clause}
                ORDER BY 
                    CASE f.status 
                        WHEN 'pending' THEN 0 
                        WHEN 'processing' THEN 1 
                        ELSE 2 
                    END,
                    f.created_at DESC
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])
            rows = self.db.execute(query, tuple(params))
            
            # 查询总数
            count_query = f"""
                SELECT COUNT(*) as total FROM user_feedback f WHERE {where_clause}
            """
            count_params = params[:-2]  # 去掉 limit 和 offset
            total_row = self.db.execute_one(count_query, tuple(count_params))
            total = total_row['total'] if total_row else 0
            
            # 查询待处理数量
            pending_row = self.db.execute_one(
                "SELECT COUNT(*) as cnt FROM user_feedback WHERE status = 'pending'"
            )
            pending_count = pending_row['cnt'] if pending_row else 0
            
            return {
                'feedbacks': [dict(row) for row in rows],
                'total': total,
                'pending_count': pending_count
            }
            
        except Exception as e:
            logger.error(f"[Feedback] 获取反馈列表失败: {e}")
            return {'feedbacks': [], 'total': 0, 'pending_count': 0}
    
    def reply_feedback(
        self,
        feedback_id: int,
        admin_id: str,
        reply: str,
        status: str = "resolved"
    ) -> bool:
        """
        回复反馈
        
        Args:
            feedback_id: 反馈ID
            admin_id: 管理员ID
            reply: 回复内容
            status: 新状态 (resolved/rejected/processing)
            
        Returns:
            是否成功
        """
        if status not in self.STATUS_NAMES:
            status = "resolved"
        
        try:
            now = datetime.now()
            affected = self.db.execute_write("""
                UPDATE user_feedback 
                SET admin_id = ?, admin_reply = ?, status = ?, 
                    updated_at = ?, replied_at = ?
                WHERE id = ?
            """, (admin_id, reply, status, now, now, feedback_id))
            
            if affected > 0:
                logger.info(f"[Feedback] 管理员 {admin_id} 回复反馈 #{feedback_id}: {status}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"[Feedback] 回复反馈失败: {e}")
            return False
    
    def update_status(
        self,
        feedback_id: int,
        status: str
    ) -> bool:
        """
        更新反馈状态（不带回复）
        
        Args:
            feedback_id: 反馈ID
            status: 新状态
            
        Returns:
            是否成功
        """
        if status not in self.STATUS_NAMES:
            return False
        
        try:
            now = datetime.now()
            affected = self.db.execute_write("""
                UPDATE user_feedback 
                SET status = ?, updated_at = ?
                WHERE id = ?
            """, (status, now, feedback_id))
            
            return affected > 0
            
        except Exception as e:
            logger.error(f"[Feedback] 更新状态失败: {e}")
            return False
    
    # ==================== 统计 ====================
    
    def get_feedback_stats(self) -> Dict[str, Any]:
        """
        获取反馈统计
        
        Returns:
            统计数据
        """
        try:
            # 按状态统计
            status_rows = self.db.execute("""
                SELECT status, COUNT(*) as count
                FROM user_feedback
                GROUP BY status
            """)
            status_stats = {row['status']: row['count'] for row in status_rows}
            
            # 按类型统计
            type_rows = self.db.execute("""
                SELECT feedback_type, COUNT(*) as count
                FROM user_feedback
                GROUP BY feedback_type
            """)
            type_stats = {row['feedback_type']: row['count'] for row in type_rows}
            
            # 总数
            total_row = self.db.execute_one(
                "SELECT COUNT(*) as total FROM user_feedback"
            )
            total = total_row['total'] if total_row else 0
            
            # 今日新增
            today_row = self.db.execute_one("""
                SELECT COUNT(*) as count FROM user_feedback
                WHERE date(created_at) = date('now')
            """)
            today_count = today_row['count'] if today_row else 0
            
            # 平均处理时间（已处理的）
            avg_row = self.db.execute_one("""
                SELECT AVG(
                    julianday(replied_at) - julianday(created_at)
                ) * 24 as avg_hours
                FROM user_feedback
                WHERE replied_at IS NOT NULL
            """)
            avg_hours = avg_row['avg_hours'] if avg_row and avg_row['avg_hours'] else 0
            
            return {
                'total': total,
                'today_count': today_count,
                'by_status': status_stats,
                'by_type': type_stats,
                'pending': status_stats.get('pending', 0),
                'resolved': status_stats.get('resolved', 0),
                'avg_response_hours': round(avg_hours, 1)
            }
            
        except Exception as e:
            logger.error(f"[Feedback] 获取统计失败: {e}")
            return {
                'total': 0, 'today_count': 0, 'by_status': {}, 
                'by_type': {}, 'pending': 0, 'resolved': 0,
                'avg_response_hours': 0
            }
    
    # ==================== 辅助方法 ====================
    
    def get_type_display(self, feedback_type: str) -> str:
        """获取反馈类型的显示名称"""
        return self.FEEDBACK_TYPES.get(feedback_type, feedback_type)
    
    def get_status_display(self, status: str) -> str:
        """获取状态的显示名称"""
        return self.STATUS_NAMES.get(status, status)
    
    def format_time_ago(self, dt) -> str:
        """格式化时间为"多久前"的形式"""
        if not dt:
            return ""
        
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
            except:
                return dt[:16] if len(dt) > 16 else dt
        
        now = datetime.now()
        diff = now - dt
        
        if diff.days > 30:
            return dt.strftime("%Y-%m-%d")
        elif diff.days > 0:
            return f"{diff.days}天前"
        elif diff.seconds > 3600:
            return f"{diff.seconds // 3600}小时前"
        elif diff.seconds > 60:
            return f"{diff.seconds // 60}分钟前"
        else:
            return "刚刚"


# 全局实例
_feedback_manager: Optional[FeedbackManager] = None


def get_feedback_manager(db: DatabaseManager = None) -> Optional[FeedbackManager]:
    """
    获取反馈管理器实例
    
    Args:
        db: 数据库管理器，首次调用时必须提供
        
    Returns:
        FeedbackManager 实例
    """
    global _feedback_manager
    
    if _feedback_manager is None and db is not None:
        _feedback_manager = FeedbackManager(db)
        logger.info("[Feedback] 反馈管理器初始化完成")
    
    return _feedback_manager
