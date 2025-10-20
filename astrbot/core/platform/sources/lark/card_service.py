"""
飞书卡片服务
负责卡片的更新操作
"""
import json
import asyncio
import aiohttp
from typing import Optional, Dict, Any
from astrbot.api.message_components import InlineKeyboard
from astrbot import logger
from .token_manager import get_token_manager


class LarkCardService:
    """飞书卡片服务"""
    
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.token_manager = get_token_manager(app_id, app_secret)
    
    async def update_card(self, token: str, text: str, keyboard: Optional[InlineKeyboard] = None) -> bool:
        """更新卡片内容"""
        try:
            if not token:
                logger.warning("[lark-card] 缺少卡片更新token")
                return False
            
            logger.debug(f"[lark-card] 开始更新卡片，token: {token[:20]}...")
            
            # 获取访问令牌
            access_token = await self.token_manager.get_tenant_access_token()
            if not access_token:
                logger.error("[lark-card] 获取访问令牌失败")
                return False
            
            # 构建卡片内容
            card_content = self._build_card_content(text, keyboard)
            
            # 调用更新API
            success = await self._call_update_api(token, access_token, card_content)
            
            if success:
                logger.debug("[lark-card] 卡片更新成功")
            else:
                logger.warning("[lark-card] 卡片更新失败")
                # 清除token缓存，下次重新获取
                self.token_manager.invalidate_cache()
            
            return success
            
        except Exception as e:
            logger.error(f"[lark-card] 更新卡片异常: {e}")
            return False
    
    def _build_card_content(self, text: str, keyboard: Optional[InlineKeyboard] = None) -> Dict[str, Any]:
        """构建卡片内容 - 使用与原始消息发送相同的格式（非schema 2.0）"""
        card_elements = []
        
        # 添加文本内容
        if text:
            card_elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": text
                }
            })
        
        # 添加按钮 - 使用与lark_event.py相同的action格式
        if keyboard and keyboard.buttons:
            for row in keyboard.buttons:
                button_elements = []
                for button in row:
                    button_element = self._create_button_element(button)
                    if button_element:
                        button_elements.append(button_element)
                
                # 将按钮放在 action 容器中（与原始格式一致）
                if button_elements:
                    card_elements.append({
                        "tag": "action",
                        "actions": button_elements
                    })
        
        # 确保卡片至少有一些内容
        if not card_elements:
            card_elements.append({
                "tag": "div",
                "text": {"tag": "plain_text", "content": " "}  # 空内容占位符
            })
        
        # 使用与原始消息发送相同的格式（无schema版本）
        return {
            "config": {
                "wide_screen_mode": True,
                "update_multi": True
            },
            "elements": card_elements
        }
    
    def _create_button_element(self, button: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建按钮元素 - 使用与lark_event.py完全相同的格式"""
        try:
            if button.get("url"):
                button_type = button.get("button_type", "default")
                button_element = {
                    "tag": "button",
                    "text": {
                        "tag": "plain_text",
                        "content": button["text"]
                    },
                    "type": button_type,
                    "url": button["url"]
                }
                # 添加按钮大小（如果指定）
                if "button_size" in button:
                    button_element["size"] = button["button_size"]
                # 添加按钮宽度（如果指定）
                if "button_width" in button:
                    button_element["width"] = button["button_width"]
                return button_element
            elif button.get("callback_data"):
                button_type = button.get("button_type", "primary")
                button_element = {
                    "tag": "button",
                    "text": {
                        "tag": "plain_text",
                        "content": button["text"]
                    },
                    "type": button_type,
                    "value": {
                        "action": "callback",
                        "data": button["callback_data"]
                    }
                }
                # 添加按钮大小（如果指定）
                if "button_size" in button:
                    button_element["size"] = button["button_size"]
                # 添加按钮宽度（如果指定）
                if "button_width" in button:
                    button_element["width"] = button["button_width"]
                return button_element
            else:
                logger.warning(f"[lark-card] 无效的按钮配置: {button}")
                return None
                
        except Exception as e:
            logger.error(f"[lark-card] 创建按钮元素失败: {e}")
            return None
    
    async def _call_update_api(self, card_token: str, access_token: str, card_content: Dict[str, Any]) -> bool:
        """调用卡片更新API"""
        try:
            url = "https://open.feishu.cn/open-apis/interactive/v1/card/update"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=utf-8"
            }
            data = {
                "token": card_token,
                "card": card_content
            }
            
            logger.debug(f"[lark-card] 发送更新请求到: {url}")
            logger.debug(f"[lark-card] 卡片内容: {json.dumps(card_content, ensure_ascii=False, indent=2)}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, 
                    headers=headers, 
                    json=data,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    response_text = await response.text()
                    logger.debug(f"[lark-card] API响应状态: {response.status}")
                    logger.debug(f"[lark-card] API响应内容: {response_text}")
                    
                    if response.status == 200:
                        result = await response.json()
                        if result.get("code") == 0:
                            return True
                        else:
                            logger.error(f"[lark-card] API返回错误: {result.get('code')} - {result.get('msg')}")
                            return False
                    else:
                        logger.error(f"[lark-card] HTTP请求失败: {response.status}, 响应: {response_text}")
                        return False
                        
        except asyncio.TimeoutError:
            logger.error("[lark-card] 更新请求超时")
            return False
        except Exception as e:
            logger.error(f"[lark-card] 调用更新API异常: {e}")
            return False


# 全局卡片服务实例缓存
_card_services: Dict[str, LarkCardService] = {}


def get_card_service(app_id: str, app_secret: str) -> LarkCardService:
    """获取卡片服务实例（单例模式）"""
    key = f"{app_id}:{app_secret}"
    
    if key not in _card_services:
        _card_services[key] = LarkCardService(app_id, app_secret)
        logger.debug(f"[lark-card] 创建新的卡片服务: {app_id[:8]}...")
    
    return _card_services[key]
