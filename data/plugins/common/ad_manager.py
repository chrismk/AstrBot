"""
广告管理模块

功能：
1. 多广告配置管理
2. 随机展示广告
3. 启用/暂停广告
4. 按会员等级过滤广告显示

使用示例：
    from common.ad_manager import get_ad_manager
    
    ad_manager = get_ad_manager(db)
    
    # 添加广告
    ad_manager.add_ad(content="💎 升级会员，享受更多权益")
    
    # 获取随机广告
    ad = ad_manager.get_random_ad()
"""

import random
from datetime import datetime
from typing import Dict, Any, Optional, List

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class AdManager:
    """广告管理器"""
    
    def __init__(self, db_manager=None):
        self.db = db_manager
        self._ads_cache: List[Dict] = []
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = 60  # 缓存1分钟
        
        if self.db:
            self._init_database()
    
    def set_db_manager(self, db_manager):
        """设置数据库管理器"""
        self.db = db_manager
        if self.db:
            self._init_database()
    
    def _init_database(self):
        """初始化数据库表"""
        try:
            self.db.execute_write('''
                CREATE TABLE IF NOT EXISTS ads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    is_enabled INTEGER DEFAULT 1,
                    weight INTEGER DEFAULT 1,
                    start_time TEXT,
                    end_time TEXT,
                    target_levels TEXT DEFAULT '[0,1,2]',
                    click_count INTEGER DEFAULT 0,
                    show_count INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                )
            ''')
            
            # 检查是否有默认广告，没有则添加
            count = self.db.execute_one('SELECT COUNT(*) as cnt FROM ads')
            if count and count['cnt'] == 0:
                self._add_default_ads()
            
            logger.debug("[AdManager] 数据库表初始化完成")
        except Exception as e:
            logger.error(f"[AdManager] 初始化数据库失败: {e}")
    
    def _add_default_ads(self):
        """添加默认广告"""
        default_ads = [
            {
                'content': '💎 升级会员，去除广告 | 发送 /会员 了解详情',
                'weight': 10
            },
            {
                'content': '⭐ 签到领积分，兑换会员特权 | 发送 /签到',
                'weight': 5
            },
            {
                'content': '📰 订阅您感兴趣的内容 | 发送 /订阅 管理订阅',
                'weight': 5
            }
        ]
        
        for ad in default_ads:
            self.add_ad(
                content=ad['content'],
                weight=ad.get('weight', 1),
                is_enabled=True
            )
        
        logger.info("[AdManager] 已添加默认广告")
    
    def _clear_cache(self):
        """清除缓存"""
        self._ads_cache = []
        self._cache_time = None
    
    def _get_enabled_ads(self) -> List[Dict]:
        """获取启用的广告列表（带缓存）"""
        # 检查缓存
        if self._cache_time and (datetime.now() - self._cache_time).total_seconds() < self._cache_ttl:
            return self._ads_cache
        
        if not self.db:
            return []
        
        try:
            now = datetime.now().isoformat()
            rows = self.db.execute('''
                SELECT * FROM ads 
                WHERE is_enabled = 1
                AND (start_time IS NULL OR start_time <= ?)
                AND (end_time IS NULL OR end_time >= ?)
                ORDER BY weight DESC
            ''', (now, now))
            
            self._ads_cache = [dict(row) for row in rows]
            self._cache_time = datetime.now()
            return self._ads_cache
        except Exception as e:
            logger.error(f"[AdManager] 获取广告列表失败: {e}")
            return []
    
    def get_all_ads(self, include_disabled: bool = True) -> List[Dict]:
        """获取所有广告"""
        if not self.db:
            return []
        
        try:
            if include_disabled:
                rows = self.db.execute('SELECT * FROM ads ORDER BY id DESC')
            else:
                rows = self.db.execute('SELECT * FROM ads WHERE is_enabled = 1 ORDER BY id DESC')
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"[AdManager] 获取广告列表失败: {e}")
            return []
    
    def get_ad(self, ad_id: int) -> Optional[Dict]:
        """获取单条广告"""
        if not self.db:
            return None
        
        try:
            row = self.db.execute_one('SELECT * FROM ads WHERE id = ?', (ad_id,))
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"[AdManager] 获取广告失败: {e}")
            return None
    
    def add_ad(
        self,
        content: str,
        weight: int = 1,
        is_enabled: bool = True,
        start_time: str = None,
        end_time: str = None,
        target_levels: List[int] = None
    ) -> Optional[int]:
        """
        添加广告
        
        Args:
            content: 广告内容
            weight: 权重（越大显示概率越高）
            is_enabled: 是否启用
            start_time: 开始时间（ISO格式）
            end_time: 结束时间（ISO格式）
            target_levels: 目标会员等级列表 [0,1,2]
            
        Returns:
            广告ID
        """
        if not self.db:
            return None
        
        try:
            import json
            now = datetime.now().isoformat()
            target_json = json.dumps(target_levels or [0, 1, 2])
            
            self.db.execute_write('''
                INSERT INTO ads (content, weight, is_enabled, start_time, end_time, target_levels, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (content, weight, 1 if is_enabled else 0, start_time, end_time, target_json, now, now))
            
            # 获取新插入的ID
            row = self.db.execute_one('SELECT last_insert_rowid() as id')
            ad_id = row['id'] if row else None
            
            self._clear_cache()
            logger.info(f"[AdManager] 添加广告成功: id={ad_id}")
            return ad_id
        except Exception as e:
            logger.error(f"[AdManager] 添加广告失败: {e}")
            return None
    
    def update_ad(
        self,
        ad_id: int,
        content: str = None,
        weight: int = None,
        is_enabled: bool = None,
        start_time: str = None,
        end_time: str = None,
        target_levels: List[int] = None
    ) -> bool:
        """更新广告"""
        if not self.db:
            return False
        
        try:
            import json
            
            # 获取现有广告
            ad = self.get_ad(ad_id)
            if not ad:
                return False
            
            # 更新字段
            updates = []
            params = []
            
            if content is not None:
                updates.append('content = ?')
                params.append(content)
            if weight is not None:
                updates.append('weight = ?')
                params.append(weight)
            if is_enabled is not None:
                updates.append('is_enabled = ?')
                params.append(1 if is_enabled else 0)
            if start_time is not None:
                updates.append('start_time = ?')
                params.append(start_time if start_time else None)
            if end_time is not None:
                updates.append('end_time = ?')
                params.append(end_time if end_time else None)
            if target_levels is not None:
                updates.append('target_levels = ?')
                params.append(json.dumps(target_levels))
            
            updates.append('updated_at = ?')
            params.append(datetime.now().isoformat())
            params.append(ad_id)
            
            self.db.execute_write(f'''
                UPDATE ads SET {', '.join(updates)} WHERE id = ?
            ''', params)
            
            self._clear_cache()
            logger.info(f"[AdManager] 更新广告成功: id={ad_id}")
            return True
        except Exception as e:
            logger.error(f"[AdManager] 更新广告失败: {e}")
            return False
    
    def delete_ad(self, ad_id: int) -> bool:
        """删除广告"""
        if not self.db:
            return False
        
        try:
            self.db.execute_write('DELETE FROM ads WHERE id = ?', (ad_id,))
            self._clear_cache()
            logger.info(f"[AdManager] 删除广告成功: id={ad_id}")
            return True
        except Exception as e:
            logger.error(f"[AdManager] 删除广告失败: {e}")
            return False
    
    def toggle_ad(self, ad_id: int) -> Optional[bool]:
        """
        切换广告启用状态
        
        Returns:
            新的启用状态，失败返回None
        """
        ad = self.get_ad(ad_id)
        if not ad:
            return None
        
        new_state = not ad['is_enabled']
        if self.update_ad(ad_id, is_enabled=new_state):
            return new_state
        return None
    
    def get_random_ad(self, user_level: int = 0) -> Optional[str]:
        """
        获取随机广告（按权重）
        
        Args:
            user_level: 用户会员等级（用于过滤定向广告）
            
        Returns:
            广告内容文本
        """
        import json
        
        ads = self._get_enabled_ads()
        if not ads:
            return None
        
        # 过滤目标等级
        filtered_ads = []
        for ad in ads:
            try:
                target_levels = json.loads(ad.get('target_levels', '[0,1,2]'))
                if user_level in target_levels:
                    filtered_ads.append(ad)
            except:
                filtered_ads.append(ad)
        
        if not filtered_ads:
            return None
        
        # 按权重随机选择
        total_weight = sum(ad.get('weight', 1) for ad in filtered_ads)
        if total_weight <= 0:
            return random.choice(filtered_ads)['content']
        
        r = random.uniform(0, total_weight)
        cumulative = 0
        for ad in filtered_ads:
            cumulative += ad.get('weight', 1)
            if r <= cumulative:
                # 更新展示次数
                self._increment_show_count(ad['id'])
                return ad['content']
        
        return filtered_ads[-1]['content']
    
    def _increment_show_count(self, ad_id: int):
        """增加展示次数"""
        if not self.db:
            return
        
        try:
            self.db.execute_write(
                'UPDATE ads SET show_count = show_count + 1 WHERE id = ?',
                (ad_id,)
            )
        except Exception as e:
            logger.debug(f"[AdManager] 更新展示次数失败: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取广告统计"""
        if not self.db:
            return {'total': 0, 'enabled': 0, 'disabled': 0, 'total_shows': 0}
        
        try:
            total = self.db.execute_one('SELECT COUNT(*) as cnt FROM ads')
            enabled = self.db.execute_one('SELECT COUNT(*) as cnt FROM ads WHERE is_enabled = 1')
            shows = self.db.execute_one('SELECT SUM(show_count) as total FROM ads')
            
            return {
                'total': total['cnt'] if total else 0,
                'enabled': enabled['cnt'] if enabled else 0,
                'disabled': (total['cnt'] if total else 0) - (enabled['cnt'] if enabled else 0),
                'total_shows': shows['total'] if shows and shows['total'] else 0
            }
        except Exception as e:
            logger.error(f"[AdManager] 获取统计失败: {e}")
            return {'total': 0, 'enabled': 0, 'disabled': 0, 'total_shows': 0}


# 单例
_ad_manager: Optional[AdManager] = None


def get_ad_manager(db_manager=None) -> AdManager:
    """获取广告管理器单例"""
    global _ad_manager
    if _ad_manager is None:
        _ad_manager = AdManager(db_manager)
    elif db_manager and not _ad_manager.db:
        _ad_manager.set_db_manager(db_manager)
    return _ad_manager


def init_ad_manager(db_manager) -> AdManager:
    """初始化广告管理器"""
    global _ad_manager
    _ad_manager = AdManager(db_manager)
    logger.info("[AdManager] 广告管理器初始化完成")
    return _ad_manager
