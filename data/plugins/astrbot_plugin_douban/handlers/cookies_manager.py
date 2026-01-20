"""
Cookies 管理模块
负责存储和管理豆瓣 cookies
"""
import sqlite3
import os
from typing import Optional
from astrbot.api import logger


class CookiesManager:
    """Cookies 管理器"""
    
    def __init__(self, db_path: str = "data/plugin_data/douban/cookies.db"):
        """
        初始化 Cookies 管理器
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._init_db()
        logger.info(f"[CookiesManager] 初始化完成: {db_path}")
    
    def _init_db(self):
        """初始化数据库"""
        # 确保目录存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建 cookies 表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cookies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                dbcl2 TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_cookie(self, user_id: str, dbcl2: str) -> bool:
        """
        保存用户的 cookies
        
        Args:
            user_id: 用户ID
            dbcl2: dbcl2 cookie 值
            
        Returns:
            是否保存成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 使用 REPLACE 实现插入或更新
            cursor.execute('''
                REPLACE INTO cookies (user_id, dbcl2, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (user_id, dbcl2))
            
            conn.commit()
            conn.close()
            
            logger.info(f"[CookiesManager] 保存 cookies 成功: user_id={user_id}")
            return True
            
        except Exception as e:
            logger.error(f"[CookiesManager] 保存 cookies 失败: {e}")
            return False
    
    def get_cookie(self, user_id: str) -> Optional[str]:
        """
        获取用户的 cookies
        
        Args:
            user_id: 用户ID
            
        Returns:
            dbcl2 cookie 值，如果不存在返回 None
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT dbcl2 FROM cookies WHERE user_id = ?
            ''', (user_id,))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                logger.debug(f"[CookiesManager] 获取 cookies 成功: user_id={user_id}")
                return result[0]
            else:
                logger.debug(f"[CookiesManager] 未找到 cookies: user_id={user_id}")
                return None
                
        except Exception as e:
            logger.error(f"[CookiesManager] 获取 cookies 失败: {e}")
            return None
    
    def delete_cookie(self, user_id: str) -> bool:
        """
        删除用户的 cookies
        
        Args:
            user_id: 用户ID
            
        Returns:
            是否删除成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM cookies WHERE user_id = ?
            ''', (user_id,))
            
            conn.commit()
            affected_rows = cursor.rowcount
            conn.close()
            
            if affected_rows > 0:
                logger.info(f"[CookiesManager] 删除 cookies 成功: user_id={user_id}")
                return True
            else:
                logger.warning(f"[CookiesManager] 未找到要删除的 cookies: user_id={user_id}")
                return False
                
        except Exception as e:
            logger.error(f"[CookiesManager] 删除 cookies 失败: {e}")
            return False
