"""
飞书Token管理器
负责tenant_access_token的获取、缓存和刷新
"""
import asyncio
import time
import aiohttp
from typing import Optional, Dict, Any
from dataclasses import dataclass
from astrbot import logger


@dataclass
class TokenInfo:
    """Token信息"""
    access_token: str
    expires_at: float  # 过期时间戳
    
    @property
    def is_expired(self) -> bool:
        """检查token是否过期（提前5分钟刷新）"""
        return time.time() >= (self.expires_at - 300)


class LarkTokenManager:
    """飞书Token管理器"""
    
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._token_cache: Optional[TokenInfo] = None
        self._lock = asyncio.Lock()
        
    async def get_tenant_access_token(self) -> Optional[str]:
        """获取tenant_access_token（带缓存和自动刷新）"""
        async with self._lock:
            # 检查缓存的token是否有效
            if self._token_cache and not self._token_cache.is_expired:
                logger.debug("[lark-token] 使用缓存的token")
                return self._token_cache.access_token
            
            # 获取新token
            logger.debug("[lark-token] 获取新的tenant_access_token")
            token_info = await self._fetch_new_token()
            
            if token_info:
                self._token_cache = token_info
                logger.debug(f"[lark-token] 新token获取成功，过期时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(token_info.expires_at))}")
                return token_info.access_token
            else:
                logger.error("[lark-token] 获取token失败")
                return None
    
    async def _fetch_new_token(self) -> Optional[TokenInfo]:
        """从飞书API获取新的token"""
        try:
            url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            data = {
                "app_id": self.app_id,
                "app_secret": self.app_secret
            }
            
            logger.debug(f"[lark-token] 请求token，app_id: {self.app_id[:8]}...")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        logger.error(f"[lark-token] HTTP请求失败: {response.status}")
                        return None
                    
                    result = await response.json()
                    
                    if result.get("code") != 0:
                        logger.error(f"[lark-token] API返回错误: {result.get('code')} - {result.get('msg')}")
                        return None
                    
                    access_token = result.get("tenant_access_token")
                    expire_seconds = result.get("expire", 7200)  # 默认2小时
                    
                    if not access_token:
                        logger.error("[lark-token] 响应中缺少access_token")
                        return None
                    
                    expires_at = time.time() + expire_seconds
                    
                    return TokenInfo(
                        access_token=access_token,
                        expires_at=expires_at
                    )
                    
        except asyncio.TimeoutError:
            logger.error("[lark-token] 请求超时")
            return None
        except Exception as e:
            logger.error(f"[lark-token] 获取token异常: {e}")
            return None
    
    def invalidate_cache(self):
        """使缓存失效（用于错误恢复）"""
        logger.debug("[lark-token] 清除token缓存")
        self._token_cache = None


# 全局token管理器实例缓存
_token_managers: Dict[str, LarkTokenManager] = {}


def get_token_manager(app_id: str, app_secret: str) -> LarkTokenManager:
    """获取token管理器实例（单例模式）"""
    key = f"{app_id}:{app_secret}"
    
    if key not in _token_managers:
        _token_managers[key] = LarkTokenManager(app_id, app_secret)
        logger.debug(f"[lark-token] 创建新的token管理器: {app_id[:8]}...")
    
    return _token_managers[key]



