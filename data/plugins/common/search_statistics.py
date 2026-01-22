"""
搜索统计管理器

负责：
1. 记录搜索行为
2. 记录下载行为
3. 生成统计报表和排行榜
4. 用户搜索历史（最近搜索、搜索建议）

使用示例：
    from common.search_statistics import get_search_statistics
    
    stats = get_search_statistics(db_manager)
    
    # 记录搜索
    stats.record_search(user_id, 'music', '周杰伦')
    
    # 获取用户最近搜索
    recent = stats.get_user_recent_searches(user_id, 'music', limit=5)
    
    # 获取热门搜索
    hot = stats.get_popular_searches('music', days=7, limit=10)
    
    # 获取搜索建议
    suggestions = stats.get_search_suggestions(user_id, 'music', prefix='周')
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from .database_manager import DatabaseManager
from .message_formatter import get_separator


class SearchStatistics:
    """搜索统计管理器"""
    
    def __init__(self, db: DatabaseManager):
        """
        初始化搜索统计管理器
        
        Args:
            db: 数据库管理器实例
        """
        self.db = db
    
    def record_search(
        self,
        user_id: str,
        plugin_name: str,
        keyword: str,
        result_count: int = 0,
        search_type: str = "keyword",
        platform: str = None
    ) -> bool:
        """
        记录搜索行为
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称 (book, music, pansou)
            keyword: 搜索关键词
            result_count: 搜索结果数量
            search_type: 搜索类型 (keyword, link, id)
            platform: 平台 (qq, netease, etc.)
            
        Returns:
            是否成功
        """
        try:
            self.db.execute_write("""
                INSERT INTO search_statistics 
                (user_id, plugin_name, search_type, keyword, platform, result_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, plugin_name, search_type, keyword, platform, result_count, datetime.now()))
            
            # 追踪任务进度
            try:
                from .task_tracker import get_task_tracker
                tracker = get_task_tracker()
                tracker.track_search(user_id, plugin_name=plugin_name)
            except Exception as e:
                logger.debug(f"[SearchStats] 任务追踪失败: {e}")
            
            return True
        except Exception as e:
            logger.error(f"[SearchStats] 记录搜索失败: {e}")
            return False
    
    def record_download(
        self,
        user_id: str,
        plugin_name: str,
        item_id: str,
        item_name: str = None,
        item_type: str = None,
        platform: str = None,
        quality: str = None,
        file_size: int = 0,
        source: str = None
    ) -> bool:
        """
        记录下载行为
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称
            item_id: 项目ID (歌曲ID, 书籍ID等)
            item_name: 项目名称
            item_type: 项目类型 (song, book, file)
            platform: 平台
            quality: 品质 (128, 320, flac, epub, pdf等)
            file_size: 文件大小
            source: 来源
            
        Returns:
            是否成功
        """
        try:
            self.db.execute_write("""
                INSERT INTO download_statistics 
                (user_id, plugin_name, item_id, item_name, item_type, platform, quality, file_size, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, plugin_name, item_id, item_name, item_type, platform, quality, file_size, source, datetime.now()))
            return True
        except Exception as e:
            logger.error(f"[SearchStats] 记录下载失败: {e}")
            return False
    
    def get_popular_searches(
        self,
        plugin_name: str = None,
        days: int = 7,
        limit: int = 10,
        start_days_ago: int = 0
    ) -> List[Dict[str, Any]]:
        """
        获取热门搜索
        
        Args:
            plugin_name: 插件名称，None表示所有插件
            days: 统计天数
            limit: 返回数量
            start_days_ago: 从几天前开始统计（0=今天，1=昨天）
            
        Returns:
            热门搜索列表
        """
        # 计算时间范围
        # start_days_ago=1, days=1 表示统计昨天一整天（昨天 00:00 到 今天 00:00）
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = today - timedelta(days=start_days_ago - 1) if start_days_ago > 0 else today + timedelta(days=1)
        since = end_date - timedelta(days=days)
        
        if plugin_name:
            rows = self.db.execute("""
                SELECT keyword, COUNT(*) as search_count, COUNT(DISTINCT user_id) as unique_users
                FROM search_statistics
                WHERE plugin_name = ? AND created_at >= ? AND created_at < ? AND keyword IS NOT NULL AND keyword != ''
                GROUP BY keyword
                ORDER BY search_count DESC
                LIMIT ?
            """, (plugin_name, since, end_date, limit))
        else:
            rows = self.db.execute("""
                SELECT plugin_name, keyword, COUNT(*) as search_count, COUNT(DISTINCT user_id) as unique_users
                FROM search_statistics
                WHERE created_at >= ? AND created_at < ? AND keyword IS NOT NULL AND keyword != ''
                GROUP BY plugin_name, keyword
                ORDER BY search_count DESC
                LIMIT ?
            """, (since, end_date, limit))
        
        return [dict(row) for row in rows]
    
    def get_popular_downloads(
        self,
        plugin_name: str = None,
        days: int = 7,
        limit: int = 10,
        start_days_ago: int = 0
    ) -> List[Dict[str, Any]]:
        """
        获取热门下载
        
        Args:
            plugin_name: 插件名称
            days: 统计天数
            limit: 返回数量
            start_days_ago: 从几天前开始统计（0=今天，1=昨天）
            
        Returns:
            热门下载列表
        """
        # 计算时间范围
        # start_days_ago=1, days=1 表示统计昨天一整天（昨天 00:00 到 今天 00:00）
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = today - timedelta(days=start_days_ago - 1) if start_days_ago > 0 else today + timedelta(days=1)
        since = end_date - timedelta(days=days)
        
        if plugin_name:
            rows = self.db.execute("""
                SELECT item_id, item_name, platform, COUNT(*) as download_count, COUNT(DISTINCT user_id) as unique_users
                FROM download_statistics
                WHERE plugin_name = ? AND created_at >= ? AND created_at < ?
                GROUP BY item_id, item_name, platform
                ORDER BY download_count DESC
                LIMIT ?
            """, (plugin_name, since, end_date, limit))
        else:
            rows = self.db.execute("""
                SELECT plugin_name, item_id, item_name, platform, COUNT(*) as download_count, COUNT(DISTINCT user_id) as unique_users
                FROM download_statistics
                WHERE created_at >= ? AND created_at < ?
                GROUP BY plugin_name, item_id, item_name, platform
                ORDER BY download_count DESC
                LIMIT ?
            """, (since, end_date, limit))
        
        return [dict(row) for row in rows]
    
    def get_user_stats(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """
        获取用户统计
        
        Args:
            user_id: 用户ID
            days: 统计天数
            
        Returns:
            用户统计信息
        """
        since = datetime.now() - timedelta(days=days)
        
        # 搜索统计
        search_row = self.db.execute_one("""
            SELECT COUNT(*) as total_searches, COUNT(DISTINCT keyword) as unique_keywords
            FROM search_statistics
            WHERE user_id = ? AND created_at > ?
        """, (user_id, since))
        
        # 下载统计
        download_row = self.db.execute_one("""
            SELECT COUNT(*) as total_downloads, SUM(file_size) as total_size
            FROM download_statistics
            WHERE user_id = ? AND created_at > ?
        """, (user_id, since))
        
        # 按插件统计
        plugin_rows = self.db.execute("""
            SELECT plugin_name, COUNT(*) as count
            FROM search_statistics
            WHERE user_id = ? AND created_at > ?
            GROUP BY plugin_name
        """, (user_id, since))
        
        return {
            'total_searches': search_row['total_searches'] if search_row else 0,
            'unique_keywords': search_row['unique_keywords'] if search_row else 0,
            'total_downloads': download_row['total_downloads'] if download_row else 0,
            'total_download_size': download_row['total_size'] or 0 if download_row else 0,
            'by_plugin': {row['plugin_name']: row['count'] for row in plugin_rows}
        }
    
    def get_plugin_stats(self, plugin_name: str, days: int = 7) -> Dict[str, Any]:
        """
        获取插件统计
        
        Args:
            plugin_name: 插件名称
            days: 统计天数
            
        Returns:
            插件统计信息
        """
        since = datetime.now() - timedelta(days=days)
        
        # 搜索统计
        search_row = self.db.execute_one("""
            SELECT COUNT(*) as total_searches, COUNT(DISTINCT user_id) as unique_users, COUNT(DISTINCT keyword) as unique_keywords
            FROM search_statistics
            WHERE plugin_name = ? AND created_at > ?
        """, (plugin_name, since))
        
        # 下载统计
        download_row = self.db.execute_one("""
            SELECT COUNT(*) as total_downloads, COUNT(DISTINCT user_id) as download_users
            FROM download_statistics
            WHERE plugin_name = ? AND created_at > ?
        """, (plugin_name, since))
        
        return {
            'plugin_name': plugin_name,
            'days': days,
            'total_searches': search_row['total_searches'] if search_row else 0,
            'unique_users': search_row['unique_users'] if search_row else 0,
            'unique_keywords': search_row['unique_keywords'] if search_row else 0,
            'total_downloads': download_row['total_downloads'] if download_row else 0,
            'download_users': download_row['download_users'] if download_row else 0
        }
    
    def format_popular_searches(self, plugin_name: str = None, days: int = 7, limit: int = 10) -> str:
        """
        格式化热门搜索排行榜
        
        Args:
            plugin_name: 插件名称
            days: 统计天数
            limit: 返回数量
            
        Returns:
            格式化的排行榜文本
        """
        popular = self.get_popular_searches(plugin_name, days, limit)
        
        if not popular:
            return "📊 暂无搜索记录"
        
        plugin_names = {
            'book': '📚 书籍',
            'music': '🎵 音乐',
            'pansou': '☁️ 云盘'
        }
        
        title = plugin_names.get(plugin_name, '🔍 综合') if plugin_name else '🔍 综合'
        separator = get_separator()
        lines = [f"{title}热门搜索 (近{days}天)", separator]
        
        for i, item in enumerate(popular, 1):
            keyword = item['keyword']
            count = item['search_count']
            users = item['unique_users']
            if len(keyword) > 15:
                keyword = keyword[:13] + "..."
            lines.append(f"{i}. {keyword} ({count}次/{users}人)")
        
        return "\n".join(lines)
    
    def format_popular_downloads(self, plugin_name: str = None, days: int = 7, limit: int = 10) -> str:
        """
        格式化热门下载排行榜
        
        Args:
            plugin_name: 插件名称
            days: 统计天数
            limit: 返回数量
            
        Returns:
            格式化的排行榜文本
        """
        popular = self.get_popular_downloads(plugin_name, days, limit)
        
        if not popular:
            return "📊 暂无下载记录"
        
        plugin_names = {
            'book': '📚 书籍',
            'music': '🎵 音乐',
            'pansou': '☁️ 云盘'
        }
        
        title = plugin_names.get(plugin_name, '⬇️ 综合') if plugin_name else '⬇️ 综合'
        separator = get_separator()
        lines = [f"{title}热门下载 (近{days}天)", separator]
        
        for i, item in enumerate(popular, 1):
            name = item.get('item_name') or item.get('item_id', '未知')
            count = item['download_count']
            users = item['unique_users']
            if len(name) > 15:
                name = name[:13] + "..."
            lines.append(f"{i}. {name} ({count}次/{users}人)")
        
        return "\n".join(lines)
    
    # ==================== 用户搜索历史功能 ====================
    
    def get_user_recent_searches(
        self,
        user_id: str,
        plugin_name: str = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        获取用户最近搜索
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称（可选，不指定则返回所有插件）
            limit: 返回数量限制
            
        Returns:
            搜索记录列表 [{"keyword": "...", "plugin_name": "...", "created_at": "...", "result_count": ...}, ...]
        """
        try:
            if plugin_name:
                rows = self.db.execute("""
                    SELECT keyword, plugin_name, created_at, result_count
                    FROM search_statistics
                    WHERE user_id = ? AND plugin_name = ? AND keyword IS NOT NULL AND keyword != ''
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (user_id, plugin_name, limit))
            else:
                rows = self.db.execute("""
                    SELECT keyword, plugin_name, created_at, result_count
                    FROM search_statistics
                    WHERE user_id = ? AND keyword IS NOT NULL AND keyword != ''
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (user_id, limit))
            
            # 去重（同一关键词只保留最近一次）
            seen = set()
            results = []
            for row in rows:
                key = (row['keyword'], row['plugin_name'])
                if key not in seen:
                    seen.add(key)
                    results.append(dict(row))
                    if len(results) >= limit:
                        break
            
            return results
            
        except Exception as e:
            logger.error(f"[SearchStats] 获取用户最近搜索失败: {e}")
            return []
    
    def get_search_suggestions(
        self,
        user_id: str,
        plugin_name: str,
        prefix: str = "",
        limit: int = 5
    ) -> List[str]:
        """
        获取搜索建议（基于用户历史和热门搜索）
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称
            prefix: 搜索前缀（用于模糊匹配）
            limit: 返回数量限制
            
        Returns:
            建议关键词列表
        """
        suggestions = []
        
        try:
            # 1. 优先从用户历史中匹配
            if prefix:
                rows = self.db.execute("""
                    SELECT DISTINCT keyword FROM search_statistics
                    WHERE user_id = ? AND plugin_name = ? AND keyword LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (user_id, plugin_name, f"{prefix}%", limit))
            else:
                rows = self.db.execute("""
                    SELECT DISTINCT keyword FROM search_statistics
                    WHERE user_id = ? AND plugin_name = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (user_id, plugin_name, limit))
            
            user_keywords = [row['keyword'] for row in rows if row['keyword']]
            suggestions.extend(user_keywords)
            
            # 2. 补充热门搜索
            remaining = limit - len(suggestions)
            if remaining > 0:
                since = datetime.now() - timedelta(days=7)
                
                if prefix:
                    placeholders = ','.join(['?'] * len(suggestions)) if suggestions else "''"
                    rows = self.db.execute(f"""
                        SELECT keyword, COUNT(*) as cnt
                        FROM search_statistics
                        WHERE plugin_name = ? AND created_at > ? AND keyword LIKE ?
                        AND keyword NOT IN ({placeholders})
                        GROUP BY keyword
                        ORDER BY cnt DESC
                        LIMIT ?
                    """, (plugin_name, since, f"{prefix}%", *suggestions, remaining))
                else:
                    placeholders = ','.join(['?'] * len(suggestions)) if suggestions else "''"
                    rows = self.db.execute(f"""
                        SELECT keyword, COUNT(*) as cnt
                        FROM search_statistics
                        WHERE plugin_name = ? AND created_at > ?
                        AND keyword NOT IN ({placeholders})
                        GROUP BY keyword
                        ORDER BY cnt DESC
                        LIMIT ?
                    """, (plugin_name, since, *suggestions, remaining))
                
                hot_keywords = [row['keyword'] for row in rows if row['keyword']]
                suggestions.extend(hot_keywords)
            
            return suggestions[:limit]
            
        except Exception as e:
            logger.error(f"[SearchStats] 获取搜索建议失败: {e}")
            return []
    
    def format_recent_searches_hint(
        self,
        user_id: str,
        plugin_name: str,
        limit: int = 3,
        prefix: str = "📜 最近搜索: "
    ) -> str:
        """
        格式化最近搜索提示（用于显示在帮助信息中）
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称
            limit: 显示数量
            prefix: 前缀文本
            
        Returns:
            格式化的提示文本，如果没有历史则返回空字符串
        """
        recent = self.get_user_recent_searches(user_id, plugin_name, limit)
        if not recent:
            return ""
        
        keywords = [item["keyword"] for item in recent]
        return f"{prefix}{' | '.join(keywords)}"
    
    def format_hot_searches_hint(
        self,
        plugin_name: str,
        limit: int = 5,
        prefix: str = "🔥 热门搜索: "
    ) -> str:
        """
        格式化热门搜索提示
        
        Args:
            plugin_name: 插件名称
            limit: 显示数量
            prefix: 前缀文本
            
        Returns:
            格式化的提示文本
        """
        hot = self.get_popular_searches(plugin_name, days=7, limit=limit)
        if not hot:
            return ""
        
        keywords = [item["keyword"] for item in hot]
        return f"{prefix}{' | '.join(keywords)}"
    
    def delete_user_history(self, user_id: str, plugin_name: str = None) -> bool:
        """
        删除用户搜索历史
        
        Args:
            user_id: 用户ID
            plugin_name: 插件名称（可选，不指定则删除所有）
            
        Returns:
            是否删除成功
        """
        try:
            if plugin_name:
                self.db.execute_write("""
                    DELETE FROM search_statistics
                    WHERE user_id = ? AND plugin_name = ?
                """, (user_id, plugin_name))
            else:
                self.db.execute_write("""
                    DELETE FROM search_statistics
                    WHERE user_id = ?
                """, (user_id,))
            
            logger.info(f"[SearchStats] 删除用户历史: user={user_id}, plugin={plugin_name}")
            return True
            
        except Exception as e:
            logger.error(f"[SearchStats] 删除用户历史失败: {e}")
            return False
    
    def cleanup_old_data(self, days: int = 90) -> int:
        """
        清理旧数据
        
        Args:
            days: 保留天数
            
        Returns:
            清理的记录数
        """
        try:
            cutoff_time = datetime.now() - timedelta(days=days)
            
            # 清理搜索统计
            self.db.execute_write("""
                DELETE FROM search_statistics
                WHERE created_at < ?
            """, (cutoff_time,))
            
            # 清理下载统计
            self.db.execute_write("""
                DELETE FROM download_statistics
                WHERE created_at < ?
            """, (cutoff_time,))
            
            logger.info(f"[SearchStats] 清理 {days} 天前的旧数据完成")
            return 0  # SQLite 不返回删除行数
            
        except Exception as e:
            logger.error(f"[SearchStats] 清理旧数据失败: {e}")
            return 0
    
    # ==================== 运营统计增强 ====================
    
    def get_daily_active_users(
        self,
        plugin_name: str = None,
        target_date: datetime = None
    ) -> int:
        """
        获取日活跃用户数 (DAU)
        
        Args:
            plugin_name: 插件名称（可选，不指定则统计所有插件）
            target_date: 目标日期（默认今天）
            
        Returns:
            活跃用户数
        """
        try:
            if target_date is None:
                target_date = datetime.now()
            
            date_str = target_date.strftime("%Y-%m-%d")
            
            if plugin_name:
                row = self.db.execute_one("""
                    SELECT COUNT(DISTINCT user_id) as dau
                    FROM search_statistics
                    WHERE plugin_name = ? AND date(created_at) = ?
                """, (plugin_name, date_str))
            else:
                row = self.db.execute_one("""
                    SELECT COUNT(DISTINCT user_id) as dau
                    FROM search_statistics
                    WHERE date(created_at) = ?
                """, (date_str,))
            
            return row['dau'] if row else 0
            
        except Exception as e:
            logger.error(f"[SearchStats] 获取DAU失败: {e}")
            return 0
    
    def get_plugin_usage_ranking(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        获取插件使用排行
        
        Args:
            days: 统计天数
            
        Returns:
            插件排行列表 [{plugin_name, search_count, download_count, unique_users}, ...]
        """
        try:
            since = datetime.now() - timedelta(days=days)
            
            # 搜索统计
            search_rows = self.db.execute("""
                SELECT plugin_name, 
                       COUNT(*) as search_count,
                       COUNT(DISTINCT user_id) as search_users
                FROM search_statistics
                WHERE created_at > ?
                GROUP BY plugin_name
            """, (since,))
            search_stats = {row['plugin_name']: dict(row) for row in search_rows}
            
            # 下载统计
            download_rows = self.db.execute("""
                SELECT plugin_name,
                       COUNT(*) as download_count,
                       COUNT(DISTINCT user_id) as download_users
                FROM download_statistics
                WHERE created_at > ?
                GROUP BY plugin_name
            """, (since,))
            download_stats = {row['plugin_name']: dict(row) for row in download_rows}
            
            # 合并统计
            all_plugins = set(search_stats.keys()) | set(download_stats.keys())
            result = []
            
            for plugin in all_plugins:
                s = search_stats.get(plugin, {})
                d = download_stats.get(plugin, {})
                
                result.append({
                    'plugin_name': plugin,
                    'search_count': s.get('search_count', 0),
                    'download_count': d.get('download_count', 0),
                    'unique_users': max(s.get('search_users', 0), d.get('download_users', 0)),
                    'total_actions': s.get('search_count', 0) + d.get('download_count', 0)
                })
            
            # 按总操作数排序
            result.sort(key=lambda x: x['total_actions'], reverse=True)
            return result
            
        except Exception as e:
            logger.error(f"[SearchStats] 获取插件排行失败: {e}")
            return []
    
    def get_user_retention_rate(self, days: int = 7) -> Dict[str, Any]:
        """
        获取用户留存率
        
        计算逻辑：
        - 次日留存：第1天活跃且第2天也活跃的用户比例
        - N日留存：第1天活跃且第N天也活跃的用户比例
        
        Args:
            days: 统计周期（计算1日、7日、30日留存）
            
        Returns:
            {
                'day1_retention': float,  # 次日留存率
                'day7_retention': float,  # 7日留存率
                'day30_retention': float, # 30日留存率
                'base_date': str,         # 基准日期
                'base_users': int         # 基准日用户数
            }
        """
        try:
            # 基准日期（N天前）
            base_date = datetime.now() - timedelta(days=days)
            base_date_str = base_date.strftime("%Y-%m-%d")
            
            # 基准日活跃用户
            base_row = self.db.execute_one("""
                SELECT COUNT(DISTINCT user_id) as cnt
                FROM search_statistics
                WHERE date(created_at) = ?
            """, (base_date_str,))
            base_users = base_row['cnt'] if base_row else 0
            
            if base_users == 0:
                return {
                    'day1_retention': 0,
                    'day7_retention': 0,
                    'day30_retention': 0,
                    'base_date': base_date_str,
                    'base_users': 0
                }
            
            # 计算各日留存
            retention_days = [1, 7, 30]
            retention_rates = {}
            
            for rd in retention_days:
                target_date = base_date + timedelta(days=rd)
                target_date_str = target_date.strftime("%Y-%m-%d")
                
                # 基准日活跃且目标日也活跃的用户数
                retained_row = self.db.execute_one("""
                    SELECT COUNT(DISTINCT s1.user_id) as cnt
                    FROM search_statistics s1
                    WHERE date(s1.created_at) = ?
                    AND s1.user_id IN (
                        SELECT DISTINCT user_id FROM search_statistics
                        WHERE date(created_at) = ?
                    )
                """, (target_date_str, base_date_str))
                
                retained_users = retained_row['cnt'] if retained_row else 0
                retention_rates[f'day{rd}_retention'] = round(retained_users / base_users * 100, 1)
            
            return {
                **retention_rates,
                'base_date': base_date_str,
                'base_users': base_users
            }
            
        except Exception as e:
            logger.error(f"[SearchStats] 获取留存率失败: {e}")
            return {
                'day1_retention': 0,
                'day7_retention': 0,
                'day30_retention': 0,
                'base_date': '',
                'base_users': 0
            }
    
    def get_active_users_trend(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        获取活跃用户趋势
        
        Args:
            days: 统计天数
            
        Returns:
            [{date, dau, searches, downloads}, ...]
        """
        try:
            since = datetime.now() - timedelta(days=days)
            
            rows = self.db.execute("""
                SELECT date(created_at) as date,
                       COUNT(DISTINCT user_id) as dau,
                       COUNT(*) as searches
                FROM search_statistics
                WHERE created_at > ?
                GROUP BY date(created_at)
                ORDER BY date
            """, (since,))
            
            # 补充下载数据
            download_rows = self.db.execute("""
                SELECT date(created_at) as date,
                       COUNT(*) as downloads
                FROM download_statistics
                WHERE created_at > ?
                GROUP BY date(created_at)
            """, (since,))
            download_map = {row['date']: row['downloads'] for row in download_rows}
            
            result = []
            for row in rows:
                result.append({
                    'date': row['date'],
                    'dau': row['dau'],
                    'searches': row['searches'],
                    'downloads': download_map.get(row['date'], 0)
                })
            
            return result
            
        except Exception as e:
            logger.error(f"[SearchStats] 获取活跃趋势失败: {e}")
            return []
    
    def get_dashboard_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        获取综合仪表盘数据
        
        Args:
            days: 统计天数
            
        Returns:
            综合统计数据
        """
        try:
            today = datetime.now()
            yesterday = today - timedelta(days=1)
            
            # 今日DAU
            today_dau = self.get_daily_active_users(target_date=today)
            yesterday_dau = self.get_daily_active_users(target_date=yesterday)
            
            # DAU环比
            if yesterday_dau > 0:
                dau_change = round((today_dau - yesterday_dau) / yesterday_dau * 100, 1)
            else:
                dau_change = 0
            
            # 7日均值DAU
            week_dau_total = 0
            for i in range(7):
                d = today - timedelta(days=i)
                week_dau_total += self.get_daily_active_users(target_date=d)
            avg_dau = round(week_dau_total / 7, 1)
            
            # 插件排行
            plugin_ranking = self.get_plugin_usage_ranking(days)
            
            # 留存率
            retention = self.get_user_retention_rate(days)
            
            # 活跃趋势
            trend = self.get_active_users_trend(days)
            
            return {
                'today_dau': today_dau,
                'yesterday_dau': yesterday_dau,
                'dau_change': dau_change,
                'avg_dau_7d': avg_dau,
                'plugin_ranking': plugin_ranking,
                'retention': retention,
                'trend': trend
            }
            
        except Exception as e:
            logger.error(f"[SearchStats] 获取仪表盘数据失败: {e}")
            return {
                'today_dau': 0,
                'yesterday_dau': 0,
                'dau_change': 0,
                'avg_dau_7d': 0,
                'plugin_ranking': [],
                'retention': {},
                'trend': []
            }
    
    # ==================== 榜单增强功能 ====================
    
    def get_ranking_with_changes(
        self,
        plugin_name: str = None,
        current_days: int = 1,
        compare_days: int = 1,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        获取带排名变化的热搜榜单
        
        Args:
            plugin_name: 插件名称（可选）
            current_days: 当前周期天数（默认1天，即今日榜单）
            compare_days: 对比周期天数（默认1天，即昨日榜单）
            limit: 返回数量
            
        Returns:
            榜单列表，每项包含：
            - keyword: 关键词
            - search_count: 搜索次数
            - unique_users: 独立用户数
            - rank: 当前排名
            - prev_rank: 上期排名（None表示新上榜）
            - rank_change: 排名变化（正数上升，负数下降，0不变，None新上榜）
            - is_new: 是否新上榜
            - heat_change: 热度变化百分比
        """
        now = datetime.now()
        
        # 当前周期
        current_start = now - timedelta(days=current_days)
        
        # 对比周期
        compare_end = current_start
        compare_start = compare_end - timedelta(days=compare_days)
        
        # 获取当前周期榜单
        current_ranking = self._get_period_ranking(plugin_name, current_start, now, limit * 2)
        
        # 获取对比周期榜单
        prev_ranking = self._get_period_ranking(plugin_name, compare_start, compare_end, limit * 2)
        
        # 构建对比周期的排名映射
        prev_rank_map = {}
        prev_count_map = {}
        for i, item in enumerate(prev_ranking, 1):
            key = item['keyword']
            prev_rank_map[key] = i
            prev_count_map[key] = item['search_count']
        
        # 计算排名变化
        result = []
        for i, item in enumerate(current_ranking[:limit], 1):
            keyword = item['keyword']
            current_count = item['search_count']
            
            prev_rank = prev_rank_map.get(keyword)
            prev_count = prev_count_map.get(keyword, 0)
            
            # 计算排名变化
            if prev_rank is None:
                rank_change = None
                is_new = True
            else:
                rank_change = prev_rank - i  # 正数表示上升
                is_new = False
            
            # 计算热度变化百分比
            if prev_count > 0:
                heat_change = round((current_count - prev_count) / prev_count * 100, 1)
            else:
                heat_change = 100.0 if current_count > 0 else 0
            
            result.append({
                'keyword': keyword,
                'search_count': current_count,
                'unique_users': item['unique_users'],
                'rank': i,
                'prev_rank': prev_rank,
                'rank_change': rank_change,
                'is_new': is_new,
                'heat_change': heat_change,
                'plugin_name': item.get('plugin_name', plugin_name)
            })
        
        return result
    
    def _get_period_ranking(
        self,
        plugin_name: str,
        start_time: datetime,
        end_time: datetime,
        limit: int
    ) -> List[Dict[str, Any]]:
        """获取指定时间段的排名"""
        try:
            if plugin_name:
                rows = self.db.execute("""
                    SELECT keyword, COUNT(*) as search_count, COUNT(DISTINCT user_id) as unique_users
                    FROM search_statistics
                    WHERE plugin_name = ? AND created_at >= ? AND created_at < ?
                    AND keyword IS NOT NULL AND keyword != ''
                    GROUP BY keyword
                    ORDER BY search_count DESC
                    LIMIT ?
                """, (plugin_name, start_time, end_time, limit))
            else:
                rows = self.db.execute("""
                    SELECT keyword, plugin_name, COUNT(*) as search_count, COUNT(DISTINCT user_id) as unique_users
                    FROM search_statistics
                    WHERE created_at >= ? AND created_at < ?
                    AND keyword IS NOT NULL AND keyword != ''
                    GROUP BY keyword
                    ORDER BY search_count DESC
                    LIMIT ?
                """, (start_time, end_time, limit))
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"[SearchStats] 获取周期排名失败: {e}")
            return []
    
    def get_rising_searches(
        self,
        plugin_name: str = None,
        current_hours: int = 24,
        compare_hours: int = 24,
        limit: int = 10,
        min_searches: int = 3
    ) -> List[Dict[str, Any]]:
        """
        获取飙升榜（热度上升最快的关键词）
        
        Args:
            plugin_name: 插件名称（可选）
            current_hours: 当前周期小时数
            compare_hours: 对比周期小时数
            limit: 返回数量
            min_searches: 最小搜索次数（过滤噪音）
            
        Returns:
            飙升榜列表，按热度增长率排序
        """
        now = datetime.now()
        
        # 当前周期
        current_start = now - timedelta(hours=current_hours)
        
        # 对比周期
        compare_end = current_start
        compare_start = compare_end - timedelta(hours=compare_hours)
        
        try:
            # 获取当前周期数据
            if plugin_name:
                current_rows = self.db.execute("""
                    SELECT keyword, COUNT(*) as search_count
                    FROM search_statistics
                    WHERE plugin_name = ? AND created_at >= ? AND created_at < ?
                    AND keyword IS NOT NULL AND keyword != ''
                    GROUP BY keyword
                    HAVING search_count >= ?
                """, (plugin_name, current_start, now, min_searches))
            else:
                current_rows = self.db.execute("""
                    SELECT keyword, COUNT(*) as search_count
                    FROM search_statistics
                    WHERE created_at >= ? AND created_at < ?
                    AND keyword IS NOT NULL AND keyword != ''
                    GROUP BY keyword
                    HAVING search_count >= ?
                """, (current_start, now, min_searches))
            
            current_map = {row['keyword']: row['search_count'] for row in current_rows}
            
            # 获取对比周期数据
            if plugin_name:
                prev_rows = self.db.execute("""
                    SELECT keyword, COUNT(*) as search_count
                    FROM search_statistics
                    WHERE plugin_name = ? AND created_at >= ? AND created_at < ?
                    AND keyword IS NOT NULL AND keyword != ''
                    GROUP BY keyword
                """, (plugin_name, compare_start, compare_end))
            else:
                prev_rows = self.db.execute("""
                    SELECT keyword, COUNT(*) as search_count
                    FROM search_statistics
                    WHERE created_at >= ? AND created_at < ?
                    AND keyword IS NOT NULL AND keyword != ''
                    GROUP BY keyword
                """, (compare_start, compare_end))
            
            prev_map = {row['keyword']: row['search_count'] for row in prev_rows}
            
            # 计算增长率
            rising = []
            for keyword, current_count in current_map.items():
                prev_count = prev_map.get(keyword, 0)
                
                # 计算增长率
                if prev_count > 0:
                    growth_rate = (current_count - prev_count) / prev_count * 100
                else:
                    # 新词，给予较高的增长率但不是无限大
                    growth_rate = min(current_count * 50, 500)  # 最高500%
                
                # 只保留正增长的
                if growth_rate > 0:
                    rising.append({
                        'keyword': keyword,
                        'search_count': current_count,
                        'prev_count': prev_count,
                        'growth_rate': round(growth_rate, 1),
                        'is_new': prev_count == 0
                    })
            
            # 按增长率排序
            rising.sort(key=lambda x: x['growth_rate'], reverse=True)
            
            return rising[:limit]
            
        except Exception as e:
            logger.error(f"[SearchStats] 获取飙升榜失败: {e}")
            return []
    
    def get_new_entries(
        self,
        plugin_name: str = None,
        hours: int = 24,
        limit: int = 10,
        min_searches: int = 2
    ) -> List[Dict[str, Any]]:
        """
        获取新上榜关键词（首次出现在热搜中的词）
        
        Args:
            plugin_name: 插件名称（可选）
            hours: 检测时间范围（小时）
            limit: 返回数量
            min_searches: 最小搜索次数
            
        Returns:
            新上榜列表
        """
        now = datetime.now()
        recent_start = now - timedelta(hours=hours)
        history_start = now - timedelta(days=30)  # 对比30天历史
        
        try:
            # 获取最近时段的热词
            if plugin_name:
                recent_rows = self.db.execute("""
                    SELECT keyword, COUNT(*) as search_count, COUNT(DISTINCT user_id) as unique_users,
                           MIN(created_at) as first_seen
                    FROM search_statistics
                    WHERE plugin_name = ? AND created_at >= ?
                    AND keyword IS NOT NULL AND keyword != ''
                    GROUP BY keyword
                    HAVING search_count >= ?
                    ORDER BY search_count DESC
                """, (plugin_name, recent_start, min_searches))
            else:
                recent_rows = self.db.execute("""
                    SELECT keyword, COUNT(*) as search_count, COUNT(DISTINCT user_id) as unique_users,
                           MIN(created_at) as first_seen
                    FROM search_statistics
                    WHERE created_at >= ?
                    AND keyword IS NOT NULL AND keyword != ''
                    GROUP BY keyword
                    HAVING search_count >= ?
                    ORDER BY search_count DESC
                """, (recent_start, min_searches))
            
            # 获取历史热词（排除最近时段）
            if plugin_name:
                history_rows = self.db.execute("""
                    SELECT DISTINCT keyword
                    FROM search_statistics
                    WHERE plugin_name = ? AND created_at >= ? AND created_at < ?
                    AND keyword IS NOT NULL AND keyword != ''
                """, (plugin_name, history_start, recent_start))
            else:
                history_rows = self.db.execute("""
                    SELECT DISTINCT keyword
                    FROM search_statistics
                    WHERE created_at >= ? AND created_at < ?
                    AND keyword IS NOT NULL AND keyword != ''
                """, (history_start, recent_start))
            
            history_keywords = {row['keyword'] for row in history_rows}
            
            # 筛选新上榜的词
            new_entries = []
            for row in recent_rows:
                if row['keyword'] not in history_keywords:
                    new_entries.append({
                        'keyword': row['keyword'],
                        'search_count': row['search_count'],
                        'unique_users': row['unique_users'],
                        'first_seen': row['first_seen']
                    })
            
            return new_entries[:limit]
            
        except Exception as e:
            logger.error(f"[SearchStats] 获取新上榜失败: {e}")
            return []
    
    def format_ranking_with_changes(
        self,
        plugin_name: str = None,
        current_days: int = 1,
        compare_days: int = 1,
        limit: int = 10
    ) -> str:
        """
        格式化带排名变化的热搜榜单
        
        Args:
            plugin_name: 插件名称
            current_days: 当前周期天数
            compare_days: 对比周期天数
            limit: 返回数量
            
        Returns:
            格式化的榜单文本
        """
        ranking = self.get_ranking_with_changes(plugin_name, current_days, compare_days, limit)
        
        if not ranking:
            return "📊 暂无搜索记录"
        
        plugin_names = {
            'book': '📚 书籍',
            'music': '🎵 音乐',
            'pansou': '☁️ 云盘',
            'douban': '🎬 豆瓣'
        }
        
        title = plugin_names.get(plugin_name, '🔍 综合') if plugin_name else '🔍 综合'
        period = "今日" if current_days == 1 else f"近{current_days}天"
        separator = get_separator()
        lines = [f"{title}热搜榜 ({period})", separator]
        
        for item in ranking:
            keyword = item['keyword']
            count = item['search_count']
            rank = item['rank']
            rank_change = item['rank_change']
            is_new = item['is_new']
            
            # 截断过长的关键词
            if len(keyword) > 12:
                keyword = keyword[:10] + ".."
            
            # 排名变化标记
            if is_new:
                change_mark = "🆕"
            elif rank_change is None:
                change_mark = ""
            elif rank_change > 0:
                change_mark = f"🔺{rank_change}"
            elif rank_change < 0:
                change_mark = f"🔻{abs(rank_change)}"
            else:
                change_mark = "➡️"
            
            # 热度标记（前3名）
            if rank == 1:
                rank_mark = "🥇"
            elif rank == 2:
                rank_mark = "🥈"
            elif rank == 3:
                rank_mark = "🥉"
            else:
                rank_mark = f"{rank}."
            
            lines.append(f"{rank_mark} {keyword} ({count}次) {change_mark}")
        
        return "\n".join(lines)
    
    def format_rising_searches(
        self,
        plugin_name: str = None,
        current_hours: int = 24,
        compare_hours: int = 24,
        limit: int = 10
    ) -> str:
        """
        格式化飙升榜
        
        Args:
            plugin_name: 插件名称
            current_hours: 当前周期小时数
            compare_hours: 对比周期小时数
            limit: 返回数量
            
        Returns:
            格式化的飙升榜文本
        """
        rising = self.get_rising_searches(plugin_name, current_hours, compare_hours, limit)
        
        if not rising:
            return "📈 暂无飙升数据"
        
        plugin_names = {
            'book': '📚 书籍',
            'music': '🎵 音乐',
            'pansou': '☁️ 云盘',
            'douban': '🎬 豆瓣'
        }
        
        title = plugin_names.get(plugin_name, '📈 综合') if plugin_name else '📈 综合'
        separator = get_separator()
        lines = [f"{title}飙升榜", separator]
        
        for i, item in enumerate(rising, 1):
            keyword = item['keyword']
            count = item['search_count']
            growth = item['growth_rate']
            is_new = item['is_new']
            
            # 截断过长的关键词
            if len(keyword) > 12:
                keyword = keyword[:10] + ".."
            
            # 增长标记
            if is_new:
                growth_mark = "🆕新词"
            else:
                growth_mark = f"↑{growth}%"
            
            lines.append(f"{i}. {keyword} ({count}次) {growth_mark}")
        
        return "\n".join(lines)
    
    def format_new_entries(
        self,
        plugin_name: str = None,
        hours: int = 24,
        limit: int = 10
    ) -> str:
        """
        格式化新上榜列表
        
        Args:
            plugin_name: 插件名称
            hours: 检测时间范围
            limit: 返回数量
            
        Returns:
            格式化的新上榜文本
        """
        new_entries = self.get_new_entries(plugin_name, hours, limit)
        
        if not new_entries:
            return "🆕 暂无新上榜"
        
        plugin_names = {
            'book': '📚 书籍',
            'music': '🎵 音乐',
            'pansou': '☁️ 云盘',
            'douban': '🎬 豆瓣'
        }
        
        title = plugin_names.get(plugin_name, '🆕 综合') if plugin_name else '🆕 综合'
        period = "今日" if hours <= 24 else f"近{hours}小时"
        separator = get_separator()
        lines = [f"{title}新上榜 ({period})", separator]
        
        for i, item in enumerate(new_entries, 1):
            keyword = item['keyword']
            count = item['search_count']
            users = item['unique_users']
            
            # 截断过长的关键词
            if len(keyword) > 12:
                keyword = keyword[:10] + ".."
            
            lines.append(f"{i}. {keyword} ({count}次/{users}人) 🆕")
        
        return "\n".join(lines)
    
    def get_comprehensive_ranking(
        self,
        plugin_name: str = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        获取综合榜单数据（包含热搜、飙升、新上榜）
        
        Args:
            plugin_name: 插件名称
            limit: 每个榜单的返回数量
            
        Returns:
            {
                'hot': [...],      # 热搜榜（带排名变化）
                'rising': [...],   # 飙升榜
                'new': [...],      # 新上榜
                'updated_at': datetime
            }
        """
        return {
            'hot': self.get_ranking_with_changes(plugin_name, current_days=1, compare_days=1, limit=limit),
            'rising': self.get_rising_searches(plugin_name, current_hours=24, compare_hours=24, limit=limit),
            'new': self.get_new_entries(plugin_name, hours=24, limit=limit),
            'updated_at': datetime.now()
        }
    
    def format_comprehensive_ranking(
        self,
        plugin_name: str = None,
        hot_limit: int = 10,
        rising_limit: int = 5,
        new_limit: int = 5
    ) -> str:
        """
        格式化综合榜单
        
        Args:
            plugin_name: 插件名称
            hot_limit: 热搜榜数量
            rising_limit: 飙升榜数量
            new_limit: 新上榜数量
            
        Returns:
            格式化的综合榜单文本
        """
        lines = []
        
        # 热搜榜
        hot_text = self.format_ranking_with_changes(plugin_name, limit=hot_limit)
        lines.append(hot_text)
        
        # 飙升榜
        rising = self.get_rising_searches(plugin_name, limit=rising_limit)
        separator = get_separator()
        if rising:
            lines.append("")
            lines.append("📈 飙升榜")
            lines.append(separator)
            for i, item in enumerate(rising, 1):
                keyword = item['keyword'][:10] + ".." if len(item['keyword']) > 12 else item['keyword']
                growth = item['growth_rate']
                mark = "🆕" if item['is_new'] else f"↑{growth}%"
                lines.append(f"{i}. {keyword} {mark}")
        
        # 新上榜
        new_entries = self.get_new_entries(plugin_name, limit=new_limit)
        if new_entries:
            lines.append("")
            lines.append("🆕 新上榜")
            lines.append(separator)
            for i, item in enumerate(new_entries, 1):
                keyword = item['keyword'][:10] + ".." if len(item['keyword']) > 12 else item['keyword']
                lines.append(f"{i}. {keyword} ({item['search_count']}次)")
        
        return "\n".join(lines)


# 全局实例
_search_statistics: Optional[SearchStatistics] = None


def get_search_statistics(db: DatabaseManager = None) -> Optional[SearchStatistics]:
    """
    获取搜索统计管理器实例
    
    Args:
        db: 数据库管理器，首次调用时必须提供
        
    Returns:
        SearchStatistics 实例
    """
    global _search_statistics
    
    if _search_statistics is None and db is not None:
        _search_statistics = SearchStatistics(db)
        logger.info("[SearchStats] 搜索统计管理器初始化完成")
    
    return _search_statistics
