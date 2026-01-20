"""
缓存管理器
提供简单的内存缓存功能，支持 TTL（过期时间）
"""
import time
from typing import Any, Optional, Dict
from threading import Lock


class CacheManager:
    """
    简单的内存缓存管理器
    
    支持：
    - TTL（过期时间）
    - 自动清理过期缓存
    - 线程安全
    """
    
    def __init__(self, default_ttl: int = 3600):
        """
        初始化缓存管理器
        
        Args:
            default_ttl: 默认过期时间（秒），0 表示永不过期
        """
        self.default_ttl = default_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        设置缓存
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None 使用默认值，0 表示永不过期
        """
        if ttl is None:
            ttl = self.default_ttl
        
        expire_time = time.time() + ttl if ttl > 0 else 0
        
        with self._lock:
            self._cache[key] = {
                'value': value,
                'expire_time': expire_time
            }
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取缓存
        
        Args:
            key: 缓存键
            default: 默认值（缓存不存在或已过期时返回）
            
        Returns:
            缓存值或默认值
        """
        with self._lock:
            if key not in self._cache:
                return default
            
            cache_item = self._cache[key]
            expire_time = cache_item['expire_time']
            
            # 检查是否过期
            if expire_time > 0 and time.time() > expire_time:
                # 过期，删除并返回默认值
                del self._cache[key]
                return default
            
            return cache_item['value']
    
    def delete(self, key: str) -> bool:
        """
        删除缓存
        
        Args:
            key: 缓存键
            
        Returns:
            是否删除成功
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def exists(self, key: str) -> bool:
        """
        检查缓存是否存在（且未过期）
        
        Args:
            key: 缓存键
            
        Returns:
            是否存在
        """
        return self.get(key) is not None
    
    def clear(self) -> None:
        """清空所有缓存"""
        with self._lock:
            self._cache.clear()
    
    def clear_expired(self) -> int:
        """
        清理过期缓存
        
        Returns:
            清理的缓存数量
        """
        current_time = time.time()
        expired_keys = []
        
        with self._lock:
            for key, cache_item in self._cache.items():
                expire_time = cache_item['expire_time']
                if expire_time > 0 and current_time > expire_time:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._cache[key]
        
        return len(expired_keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            total_count = len(self._cache)
            expired_count = 0
            current_time = time.time()
            
            for cache_item in self._cache.values():
                expire_time = cache_item['expire_time']
                if expire_time > 0 and current_time > expire_time:
                    expired_count += 1
            
            return {
                'total': total_count,
                'active': total_count - expired_count,
                'expired': expired_count
            }
    
    def get_or_set(self, key: str, factory_func: callable, ttl: Optional[int] = None) -> Any:
        """
        获取缓存，如果不存在则通过工厂函数创建并缓存
        
        Args:
            key: 缓存键
            factory_func: 工厂函数，用于创建缓存值
            ttl: 过期时间（秒）
            
        Returns:
            缓存值
            
        Example:
            ```python
            cache = CacheManager()
            
            def expensive_operation():
                # 耗时操作
                return "result"
            
            # 第一次调用会执行 expensive_operation
            # 之后会直接返回缓存值
            result = cache.get_or_set("my_key", expensive_operation, ttl=60)
            ```
        """
        value = self.get(key)
        if value is None:
            value = factory_func()
            self.set(key, value, ttl)
        return value
    
    def update_ttl(self, key: str, ttl: int) -> bool:
        """
        更新缓存的过期时间
        
        Args:
            key: 缓存键
            ttl: 新的过期时间（秒）
            
        Returns:
            是否更新成功
        """
        with self._lock:
            if key not in self._cache:
                return False
            
            expire_time = time.time() + ttl if ttl > 0 else 0
            self._cache[key]['expire_time'] = expire_time
            return True
    
    def keys(self) -> list:
        """
        获取所有缓存键（包括已过期的）
        
        Returns:
            缓存键列表
        """
        with self._lock:
            return list(self._cache.keys())
    
    def __len__(self) -> int:
        """获取缓存数量"""
        with self._lock:
            return len(self._cache)
    
    def __contains__(self, key: str) -> bool:
        """支持 in 操作符"""
        return self.exists(key)


# 全局缓存实例（可选）
_global_cache = None


def get_global_cache(default_ttl: int = 3600) -> CacheManager:
    """
    获取全局缓存实例（单例模式）
    
    Args:
        default_ttl: 默认过期时间（秒）
        
    Returns:
        全局缓存管理器实例
        
    Example:
        ```python
        from common.cache_manager import get_global_cache
        
        cache = get_global_cache()
        cache.set("my_key", "my_value", ttl=60)
        ```
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = CacheManager(default_ttl)
    return _global_cache
