"""
订阅源管理模块

提供统一的订阅源管理，支持多种订阅源类型：
1. 内部榜单 (internal) - 系统内部搜索统计榜单
2. RSS订阅 (rss) - 支持RSS/Atom/RSSHub
3. API订阅 (api) - 支持REST API（如60s新闻）
4. Webhook订阅 (webhook) - 支持外部推送

架构设计：
- SubscriptionSource: 订阅源数据模型
- SourceAdapter: 订阅源适配器基类
- SourceManager: 订阅源管理器
"""
import json
import sqlite3
import asyncio
import aiohttp
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict, fields
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class SourceType(Enum):
    """订阅源类型"""
    INTERNAL = "internal"      # 内部榜单
    RSS = "rss"                # RSS/Atom/RSSHub
    API = "api"                # REST API
    WEBHOOK = "webhook"        # Webhook推送
    CUSTOM = "custom"          # 自定义适配器


class SourceStatus(Enum):
    """订阅源状态"""
    ACTIVE = "active"          # 活跃
    INACTIVE = "inactive"      # 停用
    ERROR = "error"            # 错误
    PENDING = "pending"        # 待审核


class AccessLevel(Enum):
    """访问级别"""
    PUBLIC = 0                 # 公开（所有用户）
    REGISTERED = 1             # 注册用户
    MEMBER = 2                 # 会员用户
    VIP = 3                    # VIP用户
    ADMIN = 99                 # 管理员


class PushContentMode(Enum):
    """推送内容模式"""
    FULL = "full"              # 完整内容
    AI_SUMMARY = "ai_summary"  # AI摘要总结
    BRIEF = "brief"            # 简要提醒（标题+链接）
    TITLE_LIST = "title_list"  # 标题列表（多条合并）


# 推送内容模式显示名称
PUSH_CONTENT_MODE_NAMES = {
    'full': '📄 完整内容',
    'ai_summary': '🤖 AI摘要',
    'brief': '📌 简要提醒',
    'title_list': '📋 标题列表'
}

# 推送内容模式描述
PUSH_CONTENT_MODE_DESC = {
    'full': '推送完整的内容详情',
    'ai_summary': '使用AI生成内容摘要，适合长文章',
    'brief': '仅推送标题和链接，适合高频更新源',
    'title_list': '多条内容合并为标题列表推送'
}


@dataclass
class SubscriptionLink:
    """
    订阅链接数据模型
    
    订阅链接是API项目的入口，解析后生成多个订阅源（端点）
    例如：https://60s.7se.cn/ 是订阅链接，解析后有：
    - /           -> 每日60秒
    - /api/bing   -> 必应壁纸
    - /api/today_in_history -> 历史上的今天
    """
    id: int = 0
    name: str = ""                          # 链接名称
    display_name: str = ""                  # 显示名称
    url: str = ""                           # 链接URL
    category: str = ""                      # 分类
    description: str = ""                   # 描述
    icon: str = "🔗"                        # 图标
    
    # 状态
    status: SourceStatus = SourceStatus.ACTIVE
    source_count: int = 0                   # 解析出的订阅源数量
    
    # 元数据
    created_at: Optional[datetime] = None
    created_by: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'display_name': self.display_name,
            'url': self.url,
            'category': self.category,
            'description': self.description,
            'icon': self.icon,
            'status': self.status.value,
            'source_count': self.source_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by': self.created_by
        }


@dataclass
class SubscriptionSource:
    """
    订阅源数据模型
    
    订阅源是用户可以订阅的具体端点
    可以来自：
    1. 内部榜单（INTERNAL）
    2. 订阅链接解析（API/RSS）
    3. 手动添加
    """
    id: int = 0
    name: str = ""                          # 源代码名称（英文）
    display_name: str = ""                  # 显示名称（中文）
    source_type: SourceType = SourceType.INTERNAL
    category: str = ""                      # 分类（如：榜单、新闻、资讯）
    description: str = ""                   # 描述
    icon: str = "📰"                        # 图标
    
    # 关联的订阅链接
    link_id: int = 0                        # 所属订阅链接ID（0表示独立源）
    
    # 连接配置
    url: str = ""                           # 源URL（RSS/API地址）
    method: str = "GET"                     # HTTP方法
    headers: Dict[str, str] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    body: Dict[str, Any] = field(default_factory=dict)
    
    # 解析配置
    parser_config: Dict[str, Any] = field(default_factory=dict)
    # RSS: {}
    # API: {"data_path": "data.news", "title_field": "title", "content_field": "content"}
    
    # 更新配置
    update_interval: int = 3600             # 更新间隔（秒）
    last_update: Optional[datetime] = None
    last_content_hash: str = ""             # 上次内容哈希（用于检测更新）
    
    # 权限配置
    access_level: AccessLevel = AccessLevel.PUBLIC
    max_subscribers: int = 0                # 最大订阅数（0=无限制）
    current_subscribers: int = 0
    
    # 状态
    status: SourceStatus = SourceStatus.ACTIVE
    error_message: str = ""
    error_count: int = 0
    
    # 元数据
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: str = ""                    # 创建者（管理员ID）
    tags: List[str] = field(default_factory=list)
    
    # 推送配置
    push_template: str = ""                 # 推送消息模板
    push_format: str = "text"               # 推送格式: text/markdown/html
    push_content_mode: str = "full"         # 推送内容模式: full/ai_summary/brief/title_list
    push_max_items: int = 5                 # 每次推送最大条目数
    push_include_link: bool = True          # 是否包含链接
    push_ai_prompt: str = ""                # AI摘要自定义提示词
    
    def get_display_title(self) -> str:
        """获取显示标题"""
        return self.display_name or self.name
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['source_type'] = self.source_type.value
        data['access_level'] = self.access_level.value
        data['status'] = self.status.value
        data['last_update'] = self.last_update.isoformat() if self.last_update else None
        data['created_at'] = self.created_at.isoformat() if self.created_at else None
        data['updated_at'] = self.updated_at.isoformat() if self.updated_at else None
        data['headers'] = json.dumps(data['headers'])
        data['params'] = json.dumps(data['params'])
        data['body'] = json.dumps(data['body'])
        data['parser_config'] = json.dumps(data['parser_config'])
        data['tags'] = json.dumps(data['tags'])
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SubscriptionSource':
        """从字典创建"""
        # 类型转换
        if isinstance(data.get('source_type'), str):
            data['source_type'] = SourceType(data['source_type'])
        if isinstance(data.get('access_level'), int):
            data['access_level'] = AccessLevel(data['access_level'])
        if isinstance(data.get('status'), str):
            data['status'] = SourceStatus(data['status'])
        if isinstance(data.get('last_update'), str):
            data['last_update'] = datetime.fromisoformat(data['last_update'])
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('updated_at'), str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        if isinstance(data.get('headers'), str):
            data['headers'] = json.loads(data['headers']) if data['headers'] else {}
        if isinstance(data.get('params'), str):
            data['params'] = json.loads(data['params']) if data['params'] else {}
        if isinstance(data.get('body'), str):
            data['body'] = json.loads(data['body']) if data['body'] else {}
        if isinstance(data.get('parser_config'), str):
            data['parser_config'] = json.loads(data['parser_config']) if data['parser_config'] else {}
        if isinstance(data.get('tags'), str):
            data['tags'] = json.loads(data['tags']) if data['tags'] else []
        
        # 确保 link_id 存在（兼容旧数据）
        if 'link_id' not in data:
            data['link_id'] = 0
        
        # 过滤掉 dataclass 不支持的字段
        valid_fields = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        
        return cls(**filtered_data)


@dataclass
class SourceContent:
    """订阅源内容"""
    source_id: int
    title: str
    content: str
    url: str = ""
    published_at: Optional[datetime] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""
    
    def format_message(self, template: str = "") -> str:
        """格式化推送消息"""
        if not template:
            template = "{icon} {title}\n\n{content}"
        
        return template.format(
            title=self.title,
            content=self.content,
            url=self.url,
            published_at=self.published_at.strftime("%Y-%m-%d %H:%M") if self.published_at else "",
            **self.extra
        )


class SourceAdapter(ABC):
    """订阅源适配器基类"""
    
    @abstractmethod
    async def fetch(self, source: SubscriptionSource) -> List[SourceContent]:
        """获取订阅源内容"""
        pass
    
    @abstractmethod
    async def validate(self, source: SubscriptionSource) -> tuple[bool, str]:
        """验证订阅源配置"""
        pass
    
    def get_content_hash(self, contents: List[SourceContent]) -> str:
        """计算内容哈希"""
        import hashlib
        content_str = "|".join([c.title + c.content for c in contents])
        return hashlib.md5(content_str.encode()).hexdigest()


class InternalAdapter(SourceAdapter):
    """内部榜单适配器"""
    
    def __init__(self, search_stats=None):
        self.search_stats = search_stats
    
    async def fetch(self, source: SubscriptionSource) -> List[SourceContent]:
        """获取内部榜单内容"""
        if not self.search_stats:
            return []
        
        contents = []
        config = source.parser_config
        ranking_type = config.get('ranking_type', 'hot')
        plugin_name = config.get('plugin_name', '')
        limit = config.get('limit', 10)
        
        if ranking_type == 'hot':
            # 热搜榜单
            ranking = self.search_stats.get_popular_searches(
                plugin_name=plugin_name,
                limit=limit
            )
            for i, item in enumerate(ranking, 1):
                contents.append(SourceContent(
                    source_id=source.id,
                    title=f"#{i} {item.get('keyword', '')}",
                    content=f"搜索次数: {item.get('search_count', 0)}",
                    extra={'rank': i, 'count': item.get('search_count', 0)}
                ))
        
        elif ranking_type == 'rising':
            # 飙升榜
            rising = self.search_stats.get_rising_searches(
                plugin_name=plugin_name,
                limit=limit
            )
            for item in rising:
                contents.append(SourceContent(
                    source_id=source.id,
                    title=f"📈 {item['keyword']}",
                    content=f"增长: +{item.get('growth', 0)}%",
                    extra=item
                ))
        
        elif ranking_type == 'new_entry':
            # 新上榜
            new_entries = self.search_stats.get_new_entries(
                plugin_name=plugin_name,
                hours=24,
                limit=limit
            )
            for item in new_entries:
                contents.append(SourceContent(
                    source_id=source.id,
                    title=f"🆕 {item['keyword']}",
                    content=f"首次上榜",
                    extra=item
                ))
        
        return contents
    
    async def validate(self, source: SubscriptionSource) -> tuple[bool, str]:
        """验证内部榜单配置"""
        config = source.parser_config
        if not config.get('ranking_type'):
            return False, "缺少 ranking_type 配置"
        return True, "配置有效"


class RSSAdapter(SourceAdapter):
    """RSS/Atom适配器"""
    
    async def fetch(self, source: SubscriptionSource) -> List[SourceContent]:
        """获取RSS内容"""
        try:
            import feedparser
        except ImportError:
            logger.warning("[RSSAdapter] feedparser 未安装，无法解析RSS")
            return []
        
        contents = []
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    source.url,
                    headers=source.headers,
                    params=source.params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status != 200:
                        logger.error(f"[RSSAdapter] 获取RSS失败: {response.status}")
                        return []
                    
                    text = await response.text()
                    feed = feedparser.parse(text)
                    
                    limit = source.parser_config.get('limit', 10)
                    for entry in feed.entries[:limit]:
                        published = None
                        if hasattr(entry, 'published_parsed') and entry.published_parsed:
                            published = datetime(*entry.published_parsed[:6])
                        
                        contents.append(SourceContent(
                            source_id=source.id,
                            title=entry.get('title', ''),
                            content=entry.get('summary', entry.get('description', '')),
                            url=entry.get('link', ''),
                            published_at=published
                        ))
        
        except Exception as e:
            logger.error(f"[RSSAdapter] 获取RSS失败: {e}")
        
        return contents
    
    async def validate(self, source: SubscriptionSource) -> tuple[bool, str]:
        """验证RSS配置"""
        if not source.url:
            return False, "缺少RSS URL"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    source.url,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        return False, f"无法访问RSS: HTTP {response.status}"
                    return True, "RSS源有效"
        except Exception as e:
            return False, f"验证失败: {e}"


class APIAdapter(SourceAdapter):
    """REST API适配器（支持60s等）"""
    
    # 动态配置加载器
    _external_presets = None
    
    @classmethod
    def load_external_presets(cls):
        """从插件配置文件加载预置配置"""
        if cls._external_presets is not None:
            return cls._external_presets
        
        try:
            # 尝试导入插件配置
            import sys
            import importlib
            
            # 尝试多种导入路径
            config_module = None
            for module_name in [
                'astrbot_plugin_subscription.sources_config',
                'data.plugins.astrbot_plugin_subscription.sources_config'
            ]:
                try:
                    if module_name in sys.modules:
                        # 重新加载以获取最新配置
                        config_module = importlib.reload(sys.modules[module_name])
                    else:
                        config_module = importlib.import_module(module_name)
                    break
                except ImportError:
                    continue
            
            if config_module and hasattr(config_module, 'PRESETS'):
                cls._external_presets = config_module.PRESETS
                logger.info(f"[APIAdapter] 加载外部预置配置: {len(cls._external_presets)} 个")
            else:
                cls._external_presets = {}
        except Exception as e:
            logger.debug(f"[APIAdapter] 加载外部配置失败: {e}")
            cls._external_presets = {}
        
        return cls._external_presets
    
    @classmethod
    def reload_presets(cls):
        """重新加载预置配置（插件重载时调用）"""
        cls._external_presets = None
        return cls.load_external_presets()
    
    # 内置预置API模板（作为后备）
    PRESETS = {
        '60s': {
            'url': 'https://60s.viki.moe/',
            'parser_config': {
                'data_path': 'data',
                'title_field': None,
                'content_field': None,
                'is_list': True
            },
            'push_template': '📰 每日60秒读懂世界\n\n{content}'
        },
        'bing_wallpaper': {
            'url': 'https://bing.biturl.top/',
            'parser_config': {
                'data_path': None,
                'title_field': 'copyright',
                'content_field': 'url'
            },
            'push_template': '🖼️ 必应每日壁纸\n\n{title}\n{content}'
        }
    }
    
    async def fetch(self, source: SubscriptionSource) -> List[SourceContent]:
        """获取API内容"""
        contents = []
        
        try:
            async with aiohttp.ClientSession() as session:
                if source.method.upper() == 'GET':
                    async with session.get(
                        source.url,
                        headers=source.headers,
                        params=source.params,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        data = await response.json()
                elif source.method.upper() == 'POST':
                    async with session.post(
                        source.url,
                        headers=source.headers,
                        json=source.body,
                        timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        data = await response.json()
                else:
                    return []
                
                # 解析数据
                contents = self._parse_response(source, data)
        
        except Exception as e:
            logger.error(f"[APIAdapter] 获取API数据失败: {e}")
        
        return contents
    
    def _parse_response(self, source: SubscriptionSource, data: Any) -> List[SourceContent]:
        """解析API响应
        
        支持两种解析方式：
        1. 自定义解析函数（优先）：在 sources_config.py 中定义，通过 parser 字段指定
        2. 通用解析逻辑（后备）：基于 parser_config 配置自动解析
        """
        contents = []
        config = source.parser_config or {}
        
        # 尝试使用自定义解析函数
        custom_result = self._try_custom_parser(source, data)
        if custom_result is not None:
            return custom_result
        
        # 后备：通用解析逻辑
        return self._default_parse(source, data, config)
    
    def _try_custom_parser(self, source: SubscriptionSource, data: Any) -> Optional[List[SourceContent]]:
        """尝试使用自定义解析函数"""
        try:
            import sys
            import importlib
            
            # 重新加载配置模块以获取最新的解析函数
            config_module = None
            for module_name in [
                'astrbot_plugin_subscription.sources_config',
                'data.plugins.astrbot_plugin_subscription.sources_config'
            ]:
                try:
                    if module_name in sys.modules:
                        config_module = importlib.reload(sys.modules[module_name])
                    else:
                        config_module = importlib.import_module(module_name)
                    break
                except ImportError:
                    continue
            
            if not config_module:
                return None
            
            # 查找匹配的预置配置
            presets = getattr(config_module, 'PRESETS', {})
            parser_name = None
            
            # 通过 URL 或名称匹配预置
            for preset_name, preset_config in presets.items():
                if preset_config.get('url') == source.url or preset_config.get('name') == source.name:
                    parser_name = preset_config.get('parser')
                    break
            
            # 也检查 source.parser_config 中是否指定了 parser
            if not parser_name and source.parser_config:
                parser_name = source.parser_config.get('parser')
            
            if not parser_name:
                return None
            
            # 获取解析函数
            parser_func = getattr(config_module, parser_name, None)
            if not parser_func or not callable(parser_func):
                logger.warning(f"[APIAdapter] 解析函数 {parser_name} 不存在")
                return None
            
            # 调用解析函数
            result = parser_func(data)
            
            if isinstance(result, dict):
                # 单条结果
                contents = [SourceContent(
                    source_id=source.id,
                    title=result.get('title') or source.display_name or source.name,
                    content=result.get('content', ''),
                    url=result.get('url', ''),
                    extra=result.get('extra', {})
                )]
                logger.debug(f"[APIAdapter] 使用自定义解析函数 {parser_name} 成功")
                return contents
            elif isinstance(result, list):
                # 多条结果
                contents = []
                for item in result:
                    if isinstance(item, dict):
                        item_title = item.get('title') or ''
                        item_content = item.get('content') or ''
                        item_url = item.get('url') or ''
                        
                        # 跳过完全空的条目
                        if not item_title.strip() and not item_content.strip() and not item_url.strip():
                            continue
                        
                        contents.append(SourceContent(
                            source_id=source.id,
                            title=item_title,
                            content=item_content,
                            url=item_url,
                            extra=item.get('extra', {})
                        ))
                
                # 如果所有条目都被过滤，返回空内容提示
                if not contents:
                    contents.append(SourceContent(
                        source_id=source.id,
                        title=source.display_name or source.name,
                        content='📭 暂无有效内容',
                        extra={'empty': True}
                    ))
                return contents
            
        except Exception as e:
            logger.debug(f"[APIAdapter] 自定义解析失败: {e}")
        
        return None
    
    def _default_parse(self, source: SubscriptionSource, data: Any, config: dict) -> List[SourceContent]:
        """默认解析逻辑"""
        contents = []
        
        # 获取数据路径
        data_path = config.get('data_path')
        if data_path:
            for key in data_path.split('.'):
                if isinstance(data, dict):
                    data = data.get(key, {})
                else:
                    break
        
        # 智能检测：如果没有配置 data_path，尝试自动检测常见格式
        if not data_path and isinstance(data, dict):
            if 'news' in data and isinstance(data['news'], list):
                data = data['news']
            elif 'data' in data and isinstance(data['data'], list):
                data = data['data']
            elif 'items' in data and isinstance(data['items'], list):
                data = data['items']
            elif 'list' in data and isinstance(data['list'], list):
                data = data['list']
        
        # 判断是否为列表
        is_list = config.get('is_list', isinstance(data, list))
        
        if is_list and isinstance(data, list):
            # 兜底：空列表
            if not data:
                contents.append(SourceContent(
                    source_id=source.id,
                    title=source.display_name or source.name,
                    content='📭 暂无数据，请稍后再试',
                    extra={'empty': True}
                ))
                return contents
            
            if isinstance(data[0], str):
                # 字符串列表 - 过滤空内容
                valid_items = [item for item in data[:15] if item and str(item).strip()]
                if not valid_items:
                    contents.append(SourceContent(
                        source_id=source.id,
                        title=source.display_name or source.name,
                        content='📭 暂无有效内容',
                        extra={'empty': True}
                    ))
                    return contents
                
                content_text = "\n".join([f"{i}. {item}" for i, item in enumerate(valid_items, 1)])
                contents.append(SourceContent(
                    source_id=source.id,
                    title=source.display_name or source.name,
                    content=content_text,
                    extra={'items': valid_items}
                ))
            else:
                # 对象列表
                title_field = config.get('title_field', 'title')
                content_field = config.get('content_field', 'content')
                url_field = config.get('url_field', 'url')
                
                for item in data[:config.get('limit', 10)]:
                    if isinstance(item, dict):
                        # 使用 or 模式处理空字符串
                        item_title = (item.get(title_field) if title_field else '') or ''
                        item_content = (item.get(content_field) if content_field else '') or ''
                        item_url = (item.get(url_field) if url_field else '') or ''
                        
                        # 跳过完全空的条目
                        if not item_title.strip() and not item_content.strip() and not item_url.strip():
                            continue
                        
                        contents.append(SourceContent(
                            source_id=source.id,
                            title=item_title,
                            content=item_content,
                            url=item_url,
                            extra=item
                        ))
                
                # 如果所有条目都被过滤，返回空内容提示
                if not contents:
                    contents.append(SourceContent(
                        source_id=source.id,
                        title=source.display_name or source.name,
                        content='📭 暂无有效内容',
                        extra={'empty': True}
                    ))
                    
        elif isinstance(data, dict):
            title_field = config.get('title_field', 'title')
            content_field = config.get('content_field', 'content')
            
            item_title = (data.get(title_field) if title_field else '') or (source.display_name or source.name)
            item_content = (data.get(content_field) if content_field else '') or ''
            
            # 如果内容为空，尝试使用整个数据对象
            if not item_content.strip():
                item_content = str(data) if data else '📭 暂无内容'
            
            contents.append(SourceContent(
                source_id=source.id,
                title=item_title,
                content=item_content,
                extra=data
            ))
        else:
            # 兜底：无法解析的数据格式
            contents.append(SourceContent(
                source_id=source.id,
                title=source.display_name or source.name,
                content='📭 无法解析数据格式',
                extra={'raw': str(data)[:500]}
            ))
        
        return contents
    
    async def validate(self, source: SubscriptionSource) -> tuple[bool, str]:
        """验证API配置"""
        if not source.url:
            return False, "缺少API URL"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    source.url,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status != 200:
                        return False, f"API返回错误: HTTP {response.status}"
                    
                    # 尝试解析JSON
                    try:
                        await response.json()
                        return True, "API源有效"
                    except:
                        return False, "API返回非JSON格式"
        except Exception as e:
            return False, f"验证失败: {e}"
    
    @classmethod
    def get_preset(cls, preset_name: str) -> Optional[Dict[str, Any]]:
        """获取预置API配置"""
        import importlib
        try:
            import astrbot_plugin_subscription.sources_config as sources_config
            importlib.reload(sources_config)
            config_preset = sources_config.get_preset(preset_name)
            if config_preset:
                return config_preset
        except ImportError:
            pass
        return cls.PRESETS.get(preset_name)
    
    @classmethod
    def list_presets(cls) -> List[str]:
        """列出所有预置API"""
        import importlib
        presets = list(cls.PRESETS.keys())
        try:
            import astrbot_plugin_subscription.sources_config as sources_config
            importlib.reload(sources_config)
            presets = list(set(sources_config.list_presets() + presets))
        except ImportError:
            pass
        return presets


class URLParser:
    """
    智能URL解析器
    
    自动检测URL类型并解析可用端点，支持：
    1. 单个API端点
    2. API项目主页（自动发现端点）
    3. RSS/Atom订阅源
    4. 常见API项目模板
    
    已知项目配置存放在 subscription_sources_config.py 中
    """
    
    @classmethod
    async def parse_url(cls, url: str) -> Dict[str, Any]:
        """
        解析URL，返回可添加的订阅源列表
        
        Returns:
            {
                'success': bool,
                'type': 'api' | 'rss' | 'unknown',
                'project_name': str,
                'sources': [
                    {
                        'name': str,
                        'display_name': str,
                        'url': str,
                        'icon': str,
                        'description': str,
                        'category': str,
                        'parser_config': dict
                    }
                ],
                'message': str
            }
        """
        from urllib.parse import urlparse
        import importlib
        
        # 动态导入配置，支持热重载
        try:
            import astrbot_plugin_subscription.sources_config as sources_config
            importlib.reload(sources_config)  # 强制重载
            KNOWN_PROJECTS = sources_config.KNOWN_PROJECTS
        except ImportError:
            KNOWN_PROJECTS = {}
        
        result = {
            'success': False,
            'type': 'unknown',
            'project_name': '',
            'sources': [],
            'message': ''
        }
        
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # 1. 检查是否为已知项目
            for known_domain, project in KNOWN_PROJECTS.items():
                if known_domain in domain:
                    result['success'] = True
                    result['type'] = 'api'
                    result['project_name'] = project['name']
                    
                    base_url = f"{parsed.scheme}://{parsed.netloc}"
                    
                    for endpoint in project['endpoints']:
                        source_url = base_url + endpoint['path']
                        # 优先使用端点自己的分类，否则使用项目分类
                        endpoint_category = endpoint.get('category', project['category'])
                        result['sources'].append({
                            'name': f"{known_domain.replace('.', '_')}_{endpoint['name']}",
                            'display_name': endpoint['display_name'],
                            'url': source_url,
                            'icon': endpoint['icon'],
                            'description': endpoint['description'],
                            'category': endpoint_category,
                            'parser_config': cls._guess_parser_config(source_url)
                        })
                    
                    result['message'] = f"检测到已知项目: {project['name']}，共 {len(result['sources'])} 个可用端点"
                    return result
            
            # 2. 尝试自动检测
            detected = await cls._auto_detect(url)
            if detected:
                result.update(detected)
                return result
            
            # 3. 作为单个API端点处理
            result['success'] = True
            result['type'] = 'api'
            result['project_name'] = domain
            result['sources'].append({
                'name': domain.replace('.', '_'),
                'display_name': f'{domain} API',
                'url': url,
                'icon': '🔌',
                'description': f'来自 {domain} 的API',
                'category': '其他',
                'parser_config': cls._guess_parser_config(url)
            })
            result['message'] = f"已添加为单个API端点"
            
        except Exception as e:
            result['message'] = f"解析失败: {e}"
        
        return result
    
    @classmethod
    async def _auto_detect(cls, url: str) -> Optional[Dict[str, Any]]:
        """自动检测URL类型"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    content_type = response.headers.get('content-type', '')
                    
                    # 检测RSS/Atom
                    if 'xml' in content_type or 'rss' in content_type or 'atom' in content_type:
                        return {
                            'success': True,
                            'type': 'rss',
                            'project_name': 'RSS订阅',
                            'sources': [{
                                'name': urlparse(url).netloc.replace('.', '_'),
                                'display_name': 'RSS订阅',
                                'url': url,
                                'icon': '📰',
                                'description': 'RSS订阅源',
                                'category': 'RSS',
                                'parser_config': {}
                            }],
                            'message': '检测到RSS订阅源'
                        }
                    
                    # 检测JSON API
                    if 'json' in content_type:
                        data = await response.json()
                        parser_config = cls._analyze_json_structure(data)
                        
                        return {
                            'success': True,
                            'type': 'api',
                            'project_name': urlparse(url).netloc,
                            'sources': [{
                                'name': urlparse(url).netloc.replace('.', '_'),
                                'display_name': f'{urlparse(url).netloc} API',
                                'url': url,
                                'icon': '🔌',
                                'description': '自动检测的API',
                                'category': 'API',
                                'parser_config': parser_config
                            }],
                            'message': f'检测到JSON API，已自动分析数据结构'
                        }
        except:
            pass
        
        return None
    
    @classmethod
    def _guess_parser_config(cls, url: str) -> Dict[str, Any]:
        """根据URL猜测解析配置"""
        url_lower = url.lower()
        
        # 60s类API
        if '60s' in url_lower:
            return {
                'data_path': 'data',
                'is_list': True
            }
        
        # 热搜类API
        if 'hot' in url_lower or 'trending' in url_lower:
            return {
                'data_path': 'data',
                'title_field': 'title',
                'content_field': 'hot',
                'url_field': 'url'
            }
        
        # 壁纸类API
        if 'bing' in url_lower or 'wallpaper' in url_lower:
            return {
                'title_field': 'copyright',
                'content_field': 'url'
            }
        
        # 默认配置
        return {
            'data_path': 'data',
            'title_field': 'title',
            'content_field': 'content'
        }
    
    @classmethod
    def _analyze_json_structure(cls, data: Any) -> Dict[str, Any]:
        """分析JSON结构，自动生成解析配置"""
        config = {}
        
        # 如果是字典，查找常见的数据字段
        if isinstance(data, dict):
            # 查找数据路径
            for key in ['data', 'result', 'items', 'list', 'news', 'content']:
                if key in data:
                    config['data_path'] = key
                    data = data[key]
                    break
        
        # 如果是列表
        if isinstance(data, list):
            config['is_list'] = True
            if data and isinstance(data[0], dict):
                # 分析第一个元素的字段
                sample = data[0]
                for key in ['title', 'name', 'headline']:
                    if key in sample:
                        config['title_field'] = key
                        break
                for key in ['content', 'description', 'summary', 'text']:
                    if key in sample:
                        config['content_field'] = key
                        break
                for key in ['url', 'link', 'href']:
                    if key in sample:
                        config['url_field'] = key
                        break
            elif data and isinstance(data[0], str):
                # 纯字符串列表（如60s新闻）
                config['is_list'] = True
        
        return config


class WebhookAdapter(SourceAdapter):
    """Webhook适配器（被动接收推送）"""
    
    async def fetch(self, source: SubscriptionSource) -> List[SourceContent]:
        """Webhook不主动获取，返回空"""
        return []
    
    async def validate(self, source: SubscriptionSource) -> tuple[bool, str]:
        """验证Webhook配置"""
        # Webhook只需要配置接收端点
        return True, "Webhook配置有效"
    
    def parse_webhook_data(self, source: SubscriptionSource, data: Dict[str, Any]) -> Optional[SourceContent]:
        """解析Webhook推送数据"""
        config = source.parser_config
        
        title_field = config.get('title_field', 'title')
        content_field = config.get('content_field', 'content')
        
        return SourceContent(
            source_id=source.id,
            title=data.get(title_field, ''),
            content=data.get(content_field, ''),
            extra=data
        )


class SourceManager:
    """订阅源管理器"""
    
    _instance = None
    
    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        self.adapters: Dict[SourceType, SourceAdapter] = {}
        self._sources_cache: Dict[int, SubscriptionSource] = {}
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = 300  # 缓存5分钟
        
        # P1优化：内容缓存（避免同一源被多用户订阅时重复抓取）
        self._content_cache: Dict[int, Dict] = {}  # {source_id: {'content': [...], 'fetched_at': datetime, 'hash': str}}
        self._content_cache_ttl = 300  # 内容缓存5分钟
        
        # 注册默认适配器
        self.register_adapter(SourceType.INTERNAL, InternalAdapter())
        self.register_adapter(SourceType.RSS, RSSAdapter())
        self.register_adapter(SourceType.API, APIAdapter())
        self.register_adapter(SourceType.WEBHOOK, WebhookAdapter())
        
        # 初始化数据库
        if db_manager:
            self._init_database()
    
    @classmethod
    def get_instance(cls, db_manager=None) -> 'SourceManager':
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls(db_manager)
        return cls._instance
    
    def register_adapter(self, source_type: SourceType, adapter: SourceAdapter):
        """注册订阅源适配器"""
        self.adapters[source_type] = adapter
        logger.info(f"[SourceManager] 注册适配器: {source_type.value}")
    
    def get_adapter(self, source_type: SourceType) -> Optional[SourceAdapter]:
        """获取适配器"""
        return self.adapters.get(source_type)
    
    def _init_database(self):
        """初始化数据库表"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 订阅链接表（API项目入口）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subscription_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    display_name TEXT DEFAULT '',
                    url TEXT NOT NULL,
                    category TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    icon TEXT DEFAULT '🔗',
                    status TEXT DEFAULT 'active',
                    source_count INTEGER DEFAULT 0,
                    created_at TEXT,
                    created_by TEXT DEFAULT ''
                )
            ''')
            
            # 订阅源表（用户可订阅的端点）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subscription_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    display_name TEXT DEFAULT '',
                    source_type TEXT NOT NULL,
                    category TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    icon TEXT DEFAULT '📰',
                    link_id INTEGER DEFAULT 0,
                    url TEXT DEFAULT '',
                    method TEXT DEFAULT 'GET',
                    headers TEXT DEFAULT '{}',
                    params TEXT DEFAULT '{}',
                    body TEXT DEFAULT '{}',
                    parser_config TEXT DEFAULT '{}',
                    update_interval INTEGER DEFAULT 3600,
                    last_update TEXT,
                    last_content_hash TEXT DEFAULT '',
                    access_level INTEGER DEFAULT 0,
                    max_subscribers INTEGER DEFAULT 0,
                    current_subscribers INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'active',
                    error_message TEXT DEFAULT '',
                    error_count INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT,
                    created_by TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    push_template TEXT DEFAULT '',
                    push_format TEXT DEFAULT 'text'
                )
            ''')
            
            # 迁移：添加新字段（如果不存在）
            migration_columns = [
                ('display_name', 'TEXT DEFAULT ""'),
                ('category', 'TEXT DEFAULT ""'),
                ('link_id', 'INTEGER DEFAULT 0'),
                ('push_content_mode', 'TEXT DEFAULT "full"'),
                ('push_max_items', 'INTEGER DEFAULT 5'),
                ('push_include_link', 'INTEGER DEFAULT 1'),
                ('push_ai_prompt', 'TEXT DEFAULT ""'),
                # 运营统计字段
                ('success_count', 'INTEGER DEFAULT 0'),
                ('fail_count', 'INTEGER DEFAULT 0'),
                ('total_fetch_time', 'REAL DEFAULT 0'),
                ('last_error_at', 'TEXT DEFAULT ""'),
            ]
            for col_name, col_type in migration_columns:
                try:
                    cursor.execute(f'ALTER TABLE subscription_sources ADD COLUMN {col_name} {col_type}')
                except:
                    pass
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sources_type ON subscription_sources(source_type)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sources_status ON subscription_sources(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sources_access ON subscription_sources(access_level)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sources_link ON subscription_sources(link_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_links_status ON subscription_links(status)')
            
            conn.commit()
            logger.info("[SourceManager] 数据库表初始化完成")
    
    # ==================== 订阅链接CRUD ====================
    
    def create_link(self, link: SubscriptionLink) -> int:
        """创建订阅链接"""
        link.created_at = datetime.now()
        
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO subscription_links 
                (name, display_name, url, category, description, icon, status, source_count, created_at, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                link.name, link.display_name, link.url, link.category,
                link.description, link.icon, link.status.value,
                link.source_count, link.created_at, link.created_by
            ))
            conn.commit()
            link_id = cursor.lastrowid
            logger.info(f"[SourceManager] 创建订阅链接: {link.name} (ID: {link_id})")
            return link_id
    
    def get_link(self, link_id: int) -> Optional[SubscriptionLink]:
        """获取订阅链接"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM subscription_links WHERE id = ?', (link_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_link(dict(row))
        return None
    
    def get_link_by_url(self, url: str) -> Optional[SubscriptionLink]:
        """根据URL获取订阅链接"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM subscription_links WHERE url = ?', (url,))
            row = cursor.fetchone()
            if row:
                return self._row_to_link(dict(row))
        return None
    
    def get_all_links(self) -> List[SubscriptionLink]:
        """获取所有订阅链接"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM subscription_links ORDER BY created_at DESC')
            rows = cursor.fetchall()
            return [self._row_to_link(dict(row)) for row in rows]
    
    def update_link(self, link: SubscriptionLink) -> bool:
        """更新订阅链接"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE subscription_links SET
                    name = ?, display_name = ?, url = ?, category = ?,
                    description = ?, icon = ?, status = ?, source_count = ?
                WHERE id = ?
            ''', (
                link.name, link.display_name, link.url, link.category,
                link.description, link.icon, link.status.value,
                link.source_count, link.id
            ))
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_link(self, link_id: int) -> bool:
        """删除订阅链接及其所有订阅源"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            # 先删除关联的订阅源
            cursor.execute('DELETE FROM subscription_sources WHERE link_id = ?', (link_id,))
            # 再删除链接
            cursor.execute('DELETE FROM subscription_links WHERE id = ?', (link_id,))
            conn.commit()
            logger.info(f"[SourceManager] 删除订阅链接: {link_id}")
            return cursor.rowcount > 0
    
    def get_link_sources(self, link_id: int) -> List[SubscriptionSource]:
        """获取订阅链接下的所有订阅源"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM subscription_sources WHERE link_id = ?', (link_id,))
            rows = cursor.fetchall()
            
            sources = []
            columns = [desc[0] for desc in cursor.description]
            for row in rows:
                data = dict(zip(columns, row))
                sources.append(SubscriptionSource.from_dict(data))
            return sources
    
    def _row_to_link(self, row: Dict) -> SubscriptionLink:
        """将数据库行转换为订阅链接对象"""
        return SubscriptionLink(
            id=row['id'],
            name=row['name'],
            display_name=row.get('display_name', ''),
            url=row['url'],
            category=row.get('category', ''),
            description=row.get('description', ''),
            icon=row.get('icon', '🔗'),
            status=SourceStatus(row.get('status', 'active')),
            source_count=row.get('source_count', 0),
            created_at=datetime.fromisoformat(row['created_at']) if row.get('created_at') else None,
            created_by=row.get('created_by', '')
        )
    
    # ==================== 订阅源CRUD ====================
    
    def create_source(self, source: SubscriptionSource) -> int:
        """创建订阅源"""
        source.created_at = datetime.now()
        source.updated_at = datetime.now()
        
        data = source.to_dict()
        del data['id']
        
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['?' for _ in data])
            
            cursor.execute(f'''
                INSERT INTO subscription_sources ({columns})
                VALUES ({placeholders})
            ''', list(data.values()))
            
            conn.commit()
            source_id = cursor.lastrowid
            
            # 清除缓存
            self._invalidate_cache()
            
            logger.info(f"[SourceManager] 创建订阅源: {source.name} (ID={source_id})")
            return source_id
    
    def get_source(self, source_id: int) -> Optional[SubscriptionSource]:
        """获取订阅源"""
        # 检查缓存
        if self._is_cache_valid() and source_id in self._sources_cache:
            return self._sources_cache[source_id]
        
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM subscription_sources WHERE id = ?', (source_id,))
            row = cursor.fetchone()
            
            if row:
                columns = [desc[0] for desc in cursor.description]
                data = dict(zip(columns, row))
                return SubscriptionSource.from_dict(data)
        
        return None
    
    def get_source_by_name(self, name: str) -> Optional[SubscriptionSource]:
        """根据名称获取订阅源"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM subscription_sources WHERE name = ?', (name,))
            row = cursor.fetchone()
            
            if row:
                columns = [desc[0] for desc in cursor.description]
                data = dict(zip(columns, row))
                return SubscriptionSource.from_dict(data)
        
        return None
    
    def get_source_by_url(self, url: str) -> Optional[SubscriptionSource]:
        """根据URL获取订阅源"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM subscription_sources WHERE url = ?', (url,))
            row = cursor.fetchone()
            
            if row:
                columns = [desc[0] for desc in cursor.description]
                data = dict(zip(columns, row))
                return SubscriptionSource.from_dict(data)
        
        return None
    
    def get_all_sources(self, 
                        source_type: Optional[SourceType] = None,
                        status: Optional[SourceStatus] = None,
                        access_level: Optional[AccessLevel] = None) -> List[SubscriptionSource]:
        """获取所有订阅源"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            query = 'SELECT * FROM subscription_sources WHERE 1=1'
            params = []
            
            if source_type:
                query += ' AND source_type = ?'
                params.append(source_type.value)
            
            if status:
                query += ' AND status = ?'
                params.append(status.value)
            
            if access_level is not None:
                query += ' AND access_level <= ?'
                params.append(access_level.value)
            
            query += ' ORDER BY id'
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            sources = []
            columns = [desc[0] for desc in cursor.description]
            for row in rows:
                data = dict(zip(columns, row))
                sources.append(SubscriptionSource.from_dict(data))
            
            return sources
    
    def get_available_sources(self, user_level: int = 0) -> List[SubscriptionSource]:
        """获取用户可用的订阅源"""
        return self.get_all_sources(
            status=SourceStatus.ACTIVE,
            access_level=AccessLevel(min(user_level, 99))
        )
    
    def update_source(self, source: SubscriptionSource) -> bool:
        """更新订阅源"""
        source.updated_at = datetime.now()
        data = source.to_dict()
        source_id = data.pop('id')
        
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            set_clause = ', '.join([f'{k} = ?' for k in data.keys()])
            
            cursor.execute(f'''
                UPDATE subscription_sources
                SET {set_clause}
                WHERE id = ?
            ''', list(data.values()) + [source_id])
            
            conn.commit()
            self._invalidate_cache()
            
            return cursor.rowcount > 0
    
    def delete_source(self, source_id: int) -> bool:
        """删除订阅源"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM subscription_sources WHERE id = ?', (source_id,))
            conn.commit()
            self._invalidate_cache()
            
            return cursor.rowcount > 0
    
    def get_popular_sources(self, limit: int = 10, user_level: int = 0) -> List[SubscriptionSource]:
        """获取热门订阅源（按订阅人数排序）"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM subscription_sources 
                WHERE status = ? AND access_level <= ?
                ORDER BY current_subscribers DESC, id ASC
                LIMIT ?
            ''', (SourceStatus.ACTIVE.value, user_level, limit))
            
            rows = cursor.fetchall()
            sources = []
            columns = [desc[0] for desc in cursor.description]
            for row in rows:
                data = dict(zip(columns, row))
                sources.append(SubscriptionSource.from_dict(data))
            
            return sources
    
    def get_sources_by_category(self, category: str, user_level: int = 0) -> List[SubscriptionSource]:
        """按分类获取订阅源"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM subscription_sources 
                WHERE status = ? AND access_level <= ? AND category = ?
                ORDER BY current_subscribers DESC, id ASC
            ''', (SourceStatus.ACTIVE.value, user_level, category))
            
            rows = cursor.fetchall()
            sources = []
            columns = [desc[0] for desc in cursor.description]
            for row in rows:
                data = dict(zip(columns, row))
                sources.append(SubscriptionSource.from_dict(data))
            
            return sources
    
    def get_all_categories(self) -> List[str]:
        """获取所有分类"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT category FROM subscription_sources 
                WHERE status = ? AND category != ''
                ORDER BY category
            ''', (SourceStatus.ACTIVE.value,))
            
            return [row[0] for row in cursor.fetchall()]
    
    def increment_subscriber_count(self, source_id: int) -> bool:
        """增加订阅人数"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE subscription_sources 
                SET current_subscribers = current_subscribers + 1
                WHERE id = ?
            ''', (source_id,))
            conn.commit()
            self._invalidate_cache()
            return cursor.rowcount > 0
    
    def decrement_subscriber_count(self, source_id: int) -> bool:
        """减少订阅人数"""
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE subscription_sources 
                SET current_subscribers = MAX(0, current_subscribers - 1)
                WHERE id = ?
            ''', (source_id,))
            conn.commit()
            self._invalidate_cache()
            return cursor.rowcount > 0
    
    def record_fetch_result(self, source_id: int, success: bool, fetch_time: float, error_msg: str = "") -> bool:
        """
        记录抓取结果统计
        
        Args:
            source_id: 订阅源ID
            success: 是否成功
            fetch_time: 抓取耗时（秒）
            error_msg: 错误信息（失败时）
        """
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            if success:
                cursor.execute('''
                    UPDATE subscription_sources 
                    SET success_count = success_count + 1,
                        total_fetch_time = total_fetch_time + ?,
                        last_update = ?,
                        error_count = 0,
                        error_message = ''
                    WHERE id = ?
                ''', (fetch_time, datetime.now().isoformat(), source_id))
            else:
                cursor.execute('''
                    UPDATE subscription_sources 
                    SET fail_count = fail_count + 1,
                        total_fetch_time = total_fetch_time + ?,
                        error_count = error_count + 1,
                        error_message = ?,
                        last_error_at = ?
                    WHERE id = ?
                ''', (fetch_time, error_msg, datetime.now().isoformat(), source_id))
            conn.commit()
            self._invalidate_cache()
            return cursor.rowcount > 0
    
    def get_source_stats(self, source_id: int) -> Dict[str, Any]:
        """
        获取订阅源运营统计数据
        
        Returns:
            {
                'success_count': int,
                'fail_count': int,
                'total_count': int,
                'success_rate': float,  # 百分比
                'avg_fetch_time': float,  # 秒
                'last_error_at': str,
                'error_message': str,
                'health_score': int  # 0-100健康度评分
            }
        """
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT success_count, fail_count, total_fetch_time, 
                       last_error_at, error_message, error_count,
                       last_update, status
                FROM subscription_sources WHERE id = ?
            ''', (source_id,))
            row = cursor.fetchone()
            
            if not row:
                return {}
            
            success_count = row[0] or 0
            fail_count = row[1] or 0
            total_fetch_time = row[2] or 0
            last_error_at = row[3] or ""
            error_message = row[4] or ""
            error_count = row[5] or 0
            last_update = row[6] or ""
            status = row[7] or "active"
            
            total_count = success_count + fail_count
            success_rate = (success_count / total_count * 100) if total_count > 0 else 100
            avg_fetch_time = (total_fetch_time / total_count) if total_count > 0 else 0
            
            # 计算健康度评分
            health_score = self._calculate_health_score(
                success_rate, error_count, last_update, status
            )
            
            return {
                'success_count': success_count,
                'fail_count': fail_count,
                'total_count': total_count,
                'success_rate': round(success_rate, 1),
                'avg_fetch_time': round(avg_fetch_time, 2),
                'last_error_at': last_error_at,
                'error_message': error_message,
                'health_score': health_score
            }
    
    def _calculate_health_score(self, success_rate: float, error_count: int, 
                                 last_update: str, status: str) -> int:
        """
        计算健康度评分 (0-100)
        
        评分规则：
        - 成功率占50分
        - 连续错误扣分：每次-10分
        - 更新活跃度占30分
        - 状态占20分
        """
        score = 0
        
        # 成功率 (50分)
        score += int(success_rate * 0.5)
        
        # 连续错误扣分
        score -= min(error_count * 10, 30)
        
        # 更新活跃度 (30分)
        if last_update:
            try:
                last_dt = datetime.fromisoformat(last_update)
                hours_ago = (datetime.now() - last_dt).total_seconds() / 3600
                if hours_ago <= 1:
                    score += 30
                elif hours_ago <= 6:
                    score += 25
                elif hours_ago <= 24:
                    score += 20
                elif hours_ago <= 72:
                    score += 10
                # 超过72小时不加分
            except:
                pass
        
        # 状态 (20分)
        if status == 'active':
            score += 20
        elif status == 'inactive':
            score += 10
        # error状态不加分
        
        return max(0, min(100, score))
    
    def get_health_icon(self, health_score: int) -> str:
        """根据健康度返回图标"""
        if health_score >= 80:
            return '🟢'
        elif health_score >= 60:
            return '🟡'
        else:
            return '🔴'
    
    def batch_update_status(self, source_ids: List[int], status: SourceStatus) -> int:
        """
        批量更新订阅源状态
        
        Returns:
            更新的数量
        """
        if not source_ids:
            return 0
        
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join(['?' for _ in source_ids])
            cursor.execute(f'''
                UPDATE subscription_sources 
                SET status = ?, updated_at = ?
                WHERE id IN ({placeholders})
            ''', [status.value, datetime.now().isoformat()] + source_ids)
            conn.commit()
            self._invalidate_cache()
            return cursor.rowcount
    
    def batch_delete_sources(self, source_ids: List[int]) -> int:
        """
        批量删除订阅源
        
        Returns:
            删除的数量
        """
        if not source_ids:
            return 0
        
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join(['?' for _ in source_ids])
            cursor.execute(f'''
                DELETE FROM subscription_sources 
                WHERE id IN ({placeholders})
            ''', source_ids)
            conn.commit()
            self._invalidate_cache()
            return cursor.rowcount
    
    def search_sources(self, keyword: str = None, status: SourceStatus = None,
                       category: str = None, user_level: int = 99) -> List[SubscriptionSource]:
        """
        搜索订阅源
        
        Args:
            keyword: 名称关键词
            status: 状态筛选
            category: 分类筛选
            user_level: 用户等级（用于权限筛选）
        """
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            query = 'SELECT * FROM subscription_sources WHERE access_level <= ?'
            params = [user_level]
            
            if keyword:
                query += ' AND (name LIKE ? OR display_name LIKE ? OR description LIKE ?)'
                like_pattern = f'%{keyword}%'
                params.extend([like_pattern, like_pattern, like_pattern])
            
            if status:
                query += ' AND status = ?'
                params.append(status.value)
            
            if category:
                query += ' AND category = ?'
                params.append(category)
            
            query += ' ORDER BY current_subscribers DESC, id ASC'
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            sources = []
            columns = [desc[0] for desc in cursor.description]
            for row in rows:
                data = dict(zip(columns, row))
                sources.append(SubscriptionSource.from_dict(data))
            
            return sources
    
    def get_recommended_sources(self, user_level: int = 0, user_categories: List[str] = None,
                                 limit: int = 5) -> List[SubscriptionSource]:
        """
        获取推荐订阅源（优化算法）
        
        推荐算法考虑：
        1. 健康度（成功率、更新活跃度）
        2. 订阅人数
        3. 用户偏好分类
        
        Args:
            user_level: 用户等级
            user_categories: 用户已订阅的分类列表（用于个性化推荐）
            limit: 返回数量
        """
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            
            # 获取所有活跃的可用订阅源
            cursor.execute('''
                SELECT *, 
                    (success_count * 1.0 / NULLIF(success_count + fail_count, 0)) as success_rate,
                    (CASE 
                        WHEN last_update IS NOT NULL AND last_update != '' 
                        THEN (julianday('now') - julianday(last_update)) 
                        ELSE 999 
                    END) as days_since_update
                FROM subscription_sources 
                WHERE status = ? AND access_level <= ?
                ORDER BY 
                    -- 健康度权重：成功率越高越好
                    (success_count * 1.0 / NULLIF(success_count + fail_count, 0)) DESC,
                    -- 活跃度权重：最近更新的优先
                    days_since_update ASC,
                    -- 人气权重
                    current_subscribers DESC
                LIMIT ?
            ''', (SourceStatus.ACTIVE.value, user_level, limit * 3))  # 多取一些用于筛选
            
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            
            all_sources = []
            for row in rows:
                data = dict(zip(columns, row))
                all_sources.append(SubscriptionSource.from_dict(data))
            
            # 如果有用户偏好分类，优先推荐相关分类
            if user_categories:
                preferred = [s for s in all_sources if s.category in user_categories]
                others = [s for s in all_sources if s.category not in user_categories]
                # 偏好分类占比60%，其他40%
                preferred_count = int(limit * 0.6)
                result = preferred[:preferred_count] + others[:limit - len(preferred[:preferred_count])]
            else:
                result = all_sources[:limit]
            
            return result
    
    # ==================== 订阅源操作 ====================
    
    async def fetch_source_content(self, source_id: int) -> List[SourceContent]:
        """获取订阅源内容"""
        source = self.get_source(source_id)
        if not source:
            return []
        
        adapter = self.get_adapter(source.source_type)
        if not adapter:
            logger.error(f"[SourceManager] 未找到适配器: {source.source_type}")
            return []
        
        try:
            contents = await adapter.fetch(source)
            
            # 更新最后获取时间
            source.last_update = datetime.now()
            if contents:
                source.last_content_hash = adapter.get_content_hash(contents)
            source.error_count = 0
            source.error_message = ""
            self.update_source(source)
            
            return contents
        
        except Exception as e:
            logger.error(f"[SourceManager] 获取订阅源内容失败: {e}")
            source.error_count += 1
            source.error_message = str(e)
            if source.error_count >= 5:
                source.status = SourceStatus.ERROR
            self.update_source(source)
            return []
    
    async def validate_source(self, source: SubscriptionSource) -> tuple[bool, str]:
        """验证订阅源"""
        adapter = self.get_adapter(source.source_type)
        if not adapter:
            return False, f"未找到适配器: {source.source_type}"
        
        return await adapter.validate(source)
    
    def check_content_updated(self, source_id: int, contents: List[SourceContent]) -> bool:
        """检查内容是否有更新"""
        source = self.get_source(source_id)
        if not source:
            return False
        
        adapter = self.get_adapter(source.source_type)
        if not adapter:
            return False
        
        new_hash = adapter.get_content_hash(contents)
        return new_hash != source.last_content_hash
    
    # ==================== 预置源管理 ====================
    
    def create_preset_source(self, preset_name: str, created_by: str = "") -> Optional[int]:
        """从预置创建订阅源"""
        preset = APIAdapter.get_preset(preset_name)
        if not preset:
            return None
        
        source = SubscriptionSource(
            name=preset_name,
            source_type=SourceType.API,
            url=preset['url'],
            parser_config=preset['parser_config'],
            push_template=preset.get('push_template', ''),
            created_by=created_by,
            description=f"预置订阅源: {preset_name}"
        )
        
        return self.create_source(source)
    
    def list_preset_sources(self) -> List[Dict[str, Any]]:
        """列出所有预置订阅源"""
        presets = []
        for name in APIAdapter.list_presets():
            preset = APIAdapter.get_preset(name)
            presets.append({
                'name': name,
                'url': preset['url'],
                'description': preset.get('push_template', '')[:50]
            })
        return presets
    
    # ==================== 缓存管理 ====================
    
    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        if not self._cache_time:
            return False
        return (datetime.now() - self._cache_time).total_seconds() < self._cache_ttl
    
    def _invalidate_cache(self):
        """使缓存失效"""
        self._sources_cache.clear()
        self._cache_time = None
    
    # ==================== P1: 内容缓存 ====================
    
    async def fetch_source_content(self, source_id: int, force_refresh: bool = False) -> tuple[List[SourceContent], str]:
        """
        获取订阅源内容（带缓存）
        
        Args:
            source_id: 订阅源ID
            force_refresh: 是否强制刷新
            
        Returns:
            (内容列表, 内容哈希)
        """
        now = datetime.now()
        
        # 检查缓存
        if not force_refresh and source_id in self._content_cache:
            cache_entry = self._content_cache[source_id]
            cache_age = (now - cache_entry['fetched_at']).total_seconds()
            if cache_age < self._content_cache_ttl:
                logger.debug(f"[SourceManager] 使用缓存内容: source_id={source_id}, age={cache_age:.0f}s")
                return cache_entry['content'], cache_entry['hash']
        
        # 获取订阅源
        source = self.get_source(source_id)
        if not source:
            return [], ""
        
        # 获取适配器
        adapter = self.get_adapter(source.source_type)
        if not adapter:
            logger.warning(f"[SourceManager] 订阅源 {source.name} 没有可用的适配器")
            return [], ""
        
        try:
            # 抓取内容
            contents = await adapter.fetch(source)
            
            # 计算内容哈希
            content_hash = adapter.get_content_hash(contents) if contents else ""
            
            # 更新缓存
            self._content_cache[source_id] = {
                'content': contents,
                'fetched_at': now,
                'hash': content_hash
            }
            
            # 更新源的最后更新时间
            source.last_update = now
            if content_hash and content_hash != source.last_content_hash:
                source.last_content_hash = content_hash
                self.update_source(source)
            
            logger.debug(f"[SourceManager] 抓取内容成功: source_id={source_id}, count={len(contents)}")
            return contents, content_hash
            
        except Exception as e:
            logger.error(f"[SourceManager] 抓取内容失败: source_id={source_id}, error={e}")
            # 更新错误状态
            source.error_count += 1
            source.error_message = str(e)
            if source.error_count >= 3:
                source.status = SourceStatus.ERROR
            self.update_source(source)
            return [], ""
    
    def get_cached_content(self, source_id: int) -> Optional[tuple[List[SourceContent], str]]:
        """
        获取缓存的内容（不触发抓取）
        
        Args:
            source_id: 订阅源ID
            
        Returns:
            (内容列表, 内容哈希) 或 None
        """
        if source_id in self._content_cache:
            cache_entry = self._content_cache[source_id]
            cache_age = (datetime.now() - cache_entry['fetched_at']).total_seconds()
            if cache_age < self._content_cache_ttl:
                return cache_entry['content'], cache_entry['hash']
        return None
    
    def invalidate_content_cache(self, source_id: int = None):
        """
        使内容缓存失效
        
        Args:
            source_id: 指定源ID，None表示清除所有
        """
        if source_id is None:
            self._content_cache.clear()
            logger.debug("[SourceManager] 清除所有内容缓存")
        elif source_id in self._content_cache:
            del self._content_cache[source_id]
            logger.debug(f"[SourceManager] 清除内容缓存: source_id={source_id}")
    
    def cleanup_content_cache(self):
        """清理过期的内容缓存"""
        now = datetime.now()
        expired = []
        for source_id, cache_entry in self._content_cache.items():
            cache_age = (now - cache_entry['fetched_at']).total_seconds()
            if cache_age >= self._content_cache_ttl:
                expired.append(source_id)
        
        for source_id in expired:
            del self._content_cache[source_id]
        
        if expired:
            logger.debug(f"[SourceManager] 清理过期缓存: {len(expired)} 个")
    
    def get_content_cache_stats(self) -> Dict:
        """获取内容缓存统计"""
        now = datetime.now()
        stats = {
            'total': len(self._content_cache),
            'valid': 0,
            'expired': 0
        }
        for cache_entry in self._content_cache.values():
            cache_age = (now - cache_entry['fetched_at']).total_seconds()
            if cache_age < self._content_cache_ttl:
                stats['valid'] += 1
            else:
                stats['expired'] += 1
        return stats


# 全局实例获取函数
_source_manager: Optional[SourceManager] = None

def get_source_manager(db_manager=None) -> SourceManager:
    """获取订阅源管理器实例"""
    global _source_manager
    if _source_manager is None:
        _source_manager = SourceManager(db_manager)
    return _source_manager

def init_source_manager(db_manager) -> SourceManager:
    """初始化订阅源管理器"""
    global _source_manager
    _source_manager = SourceManager(db_manager)
    return _source_manager
