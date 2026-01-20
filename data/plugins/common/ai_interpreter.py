"""
统一 AI 解读接口

提供标准化的 AI 内容解读功能，支持书籍、电影、音乐等多种内容类型。

功能：
- 统一的 AI 解读接口
- 可配置的提示词模板
- 内容类型适配
- 结果缓存

使用示例：
    from common.ai_interpreter import AIInterpreter, get_ai_interpreter
    
    # 获取全局实例
    interpreter = get_ai_interpreter(context)
    
    # 解读书籍
    result = await interpreter.interpret(
        content_type='book',
        content_info={'title': '三体', 'author': '刘慈欣', ...},
        event=event
    )
    
    # 使用自定义提示词
    result = await interpreter.interpret(
        content_type='movie',
        content_info={'title': '肖申克的救赎', ...},
        custom_prompt='请从艺术角度分析这部电影',
        event=event
    )
"""

from typing import Dict, Any, Optional
from astrbot.api import logger


# 全局实例
_global_ai_interpreter: Optional['AIInterpreter'] = None


def get_ai_interpreter(context = None) -> 'AIInterpreter':
    """
    获取全局 AI 解读器
    
    Args:
        context: AstrBot Context（首次调用时必须提供）
        
    Returns:
        AIInterpreter 实例
    """
    global _global_ai_interpreter
    if _global_ai_interpreter is None:
        if context is None:
            raise ValueError("首次调用必须提供 context")
        _global_ai_interpreter = AIInterpreter(context)
    return _global_ai_interpreter


class AIInterpreter:
    """统一 AI 解读器"""
    
    # 内容类型配置
    CONTENT_TYPES = {
        'book': {
            'name': '书籍',
            'icon': '📚',
            'expert_role': '资深读书博主和文学评论家',
            'aspects': ['内容概述', '适合读者', '核心收获', '推荐理由']
        },
        'movie': {
            'name': '电影',
            'icon': '🎬',
            'expert_role': '资深影评人和电影爱好者',
            'aspects': ['剧情亮点', '适合观众', '观影收获', '推荐理由']
        },
        'music': {
            'name': '音乐',
            'icon': '🎵',
            'expert_role': '音乐评论人和乐评人',
            'aspects': ['风格特点', '情感表达', '适合场景', '推荐理由']
        },
        'tv': {
            'name': '电视剧',
            'icon': '📺',
            'expert_role': '剧评人和影视爱好者',
            'aspects': ['剧情亮点', '角色塑造', '适合观众', '推荐理由']
        },
        'game': {
            'name': '游戏',
            'icon': '🎮',
            'expert_role': '游戏评测师和玩家',
            'aspects': ['玩法特点', '游戏体验', '适合玩家', '推荐理由']
        },
        'subscription': {
            'name': '订阅内容',
            'icon': '📰',
            'expert_role': '内容摘要助手',
            'aspects': ['核心要点', '关键信息', '重要数据']
        }
    }
    
    # 默认提示词模板
    DEFAULT_PROMPT_TEMPLATE = """请作为一位{expert_role}，用生动有趣的语言为用户解读这部作品。

作品信息：
{content_info}

要求：
1. 字数控制在 {max_length} 字以内
2. 不要使用表格、Markdown格式或特殊符号
3. 分段清晰，每段用空行分隔
4. 语言简洁明了，贴近生活，避免学术化表达
5. 从以下角度分析：{aspects}

请直接开始解读，不要重复标题。"""

    # 默认系统提示词
    DEFAULT_SYSTEM_PROMPT = "你是一位专业的{content_type}评论家。请用简洁、口语化的方式进行解读，避免使用表格、列表符号等格式。重点突出作品特色和推荐价值，语言要生动有趣。"
    
    def __init__(self, context):
        """
        初始化 AI 解读器
        
        Args:
            context: AstrBot Context
        """
        self.context = context
        logger.info("[AIInterpreter] AI 解读器初始化完成")
    
    async def interpret(
        self,
        content_type: str,
        content_info: Dict[str, Any],
        event = None,
        custom_prompt: str = None,
        system_prompt: str = None,
        max_length: int = 300,
        session_id: str = None
    ) -> Optional[str]:
        """
        AI 解读内容
        
        Args:
            content_type: 内容类型（book/movie/music/tv/game）
            content_info: 内容信息字典
            event: 消息事件（用于获取 provider）
            custom_prompt: 自定义提示词（可选）
            system_prompt: 自定义系统提示词（可选）
            max_length: 最大字数限制
            session_id: 会话ID（可选，用于 LLM 上下文）
            
        Returns:
            AI 解读结果文本，失败返回 None
        """
        try:
            # 1. 获取内容类型配置
            type_config = self.CONTENT_TYPES.get(content_type, {
                'name': content_type,
                'icon': '📝',
                'expert_role': '内容评论家',
                'aspects': ['内容概述', '特点分析', '推荐理由']
            })
            
            # 2. 格式化内容信息
            formatted_info = self._format_content_info(content_type, content_info)
            
            # 3. 构建提示词
            if custom_prompt:
                # 使用自定义提示词
                prompt = f"{custom_prompt}\n\n作品信息：\n{formatted_info}\n\n请基于以上信息进行解读，字数控制在{max_length}字以内。"
            else:
                # 使用默认模板
                prompt = self.DEFAULT_PROMPT_TEMPLATE.format(
                    expert_role=type_config['expert_role'],
                    content_info=formatted_info,
                    max_length=max_length,
                    aspects='、'.join(type_config['aspects'])
                )
            
            # 4. 构建系统提示词
            if system_prompt is None:
                system_prompt = self.DEFAULT_SYSTEM_PROMPT.format(
                    content_type=type_config['name']
                )
            
            # 5. 获取 LLM Provider
            provider = await self._get_provider(event)
            if not provider:
                logger.warning("[AIInterpreter] 未找到可用的 LLM Provider")
                return None
            
            # 6. 生成会话ID
            if session_id is None:
                title = content_info.get('title', 'unknown')
                user_id = event.get_sender_id() if event else 'system'
                session_id = f"ai_interpret_{content_type}_{title}_{user_id}"
            
            # 7. 调用 LLM
            response = await provider.text_chat(
                prompt=prompt,
                session_id=session_id,
                system_prompt=system_prompt
            )
            
            # 8. 提取结果
            if response:
                if hasattr(response, 'completion_text'):
                    return response.completion_text
                elif hasattr(response, 'result_chain') and response.result_chain:
                    text = "".join(
                        c.text for c in response.result_chain.chain 
                        if hasattr(c, 'text')
                    )
                    return text.strip() if text else None
            
            return None
            
        except Exception as e:
            logger.error(f"[AIInterpreter] AI 解读失败: {e}", exc_info=True)
            return None
    
    async def _get_provider(self, event = None):
        """
        获取 LLM Provider
        
        Args:
            event: 消息事件
            
        Returns:
            Provider 实例或 None
        """
        try:
            # 方式1: 通过 event 获取
            if event:
                # 尝试新版 API
                if hasattr(self.context, 'get_using_provider'):
                    provider = self.context.get_using_provider(umo=event.unified_msg_origin)
                    if provider:
                        return provider
                
                # 尝试旧版 API
                if hasattr(self.context, 'provider_manager'):
                    from astrbot.core.provider.entities import ProviderType
                    provider = self.context.provider_manager.get_using_provider(
                        ProviderType.CHAT_COMPLETION, 
                        event.get_session_id()
                    )
                    if provider:
                        return provider
            
            # 方式2: 获取默认 provider
            if hasattr(self.context, 'provider_manager'):
                from astrbot.core.provider.entities import ProviderType
                providers = self.context.provider_manager.get_providers_by_type(
                    ProviderType.CHAT_COMPLETION
                )
                if providers:
                    return providers[0]
            
            return None
            
        except Exception as e:
            logger.error(f"[AIInterpreter] 获取 Provider 失败: {e}")
            return None
    
    def _format_content_info(self, content_type: str, content_info: Dict[str, Any]) -> str:
        """
        格式化内容信息为文本
        
        Args:
            content_type: 内容类型
            content_info: 内容信息字典
            
        Returns:
            格式化的文本
        """
        lines = []
        
        # 通用字段映射
        field_names = {
            'title': '标题',
            'author': '作者',
            'director': '导演',
            'artist': '艺术家',
            'singer': '歌手',
            'actors': '主演',
            'cast': '演员',
            'genre': '类型',
            'genres': '类型',
            'year': '年份',
            'release_date': '发行日期',
            'rating': '评分',
            'score': '评分',
            'votes': '评价人数',
            'summary': '简介',
            'description': '描述',
            'intro': '简介',
            'publisher': '出版社',
            'isbn': 'ISBN',
            'pages': '页数',
            'duration': '时长',
            'country': '国家/地区',
            'language': '语言',
            'tags': '标签',
            'album': '专辑',
            'lyrics': '歌词摘要'
        }
        
        # 按优先级排序的字段
        priority_fields = ['title', 'author', 'director', 'singer', 'artist', 
                          'actors', 'cast', 'genre', 'genres', 'year', 
                          'rating', 'score', 'summary', 'description', 'intro']
        
        # 先处理优先字段
        for field in priority_fields:
            if field in content_info and content_info[field]:
                value = content_info[field]
                name = field_names.get(field, field)
                
                # 处理列表类型
                if isinstance(value, list):
                    value = '、'.join(str(v) for v in value[:5])  # 最多5个
                
                # 处理长文本
                if isinstance(value, str) and len(value) > 200:
                    value = value[:200] + '...'
                
                lines.append(f"{name}：{value}")
        
        # 处理其他字段
        for field, value in content_info.items():
            if field not in priority_fields and value:
                name = field_names.get(field, field)
                
                if isinstance(value, list):
                    value = '、'.join(str(v) for v in value[:5])
                
                if isinstance(value, str) and len(value) > 200:
                    value = value[:200] + '...'
                
                lines.append(f"{name}：{value}")
        
        return '\n'.join(lines)
    
    def format_result(
        self,
        content_type: str,
        title: str,
        interpretation: str,
        icon: str = None
    ) -> str:
        """
        格式化 AI 解读结果
        
        Args:
            content_type: 内容类型
            title: 作品标题
            interpretation: AI 解读文本
            icon: 自定义图标（可选）
            
        Returns:
            格式化的结果文本
        """
        type_config = self.CONTENT_TYPES.get(content_type, {'icon': '📝', 'name': content_type})
        
        if icon is None:
            icon = type_config['icon']
        
        return f"🤖 {icon} 《{title}》AI解读\n\n{interpretation}"
    
    @staticmethod
    def build_book_info(book_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        从书籍数据构建标准内容信息
        
        Args:
            book_data: 原始书籍数据
            
        Returns:
            标准化的内容信息字典
        """
        return {
            'title': book_data.get('title') or book_data.get('name', ''),
            'author': book_data.get('author') or book_data.get('authors', ''),
            'publisher': book_data.get('publisher', ''),
            'year': book_data.get('year') or book_data.get('pub_date', ''),
            'rating': book_data.get('rating') or book_data.get('score', ''),
            'summary': book_data.get('summary') or book_data.get('intro') or book_data.get('description', ''),
            'tags': book_data.get('tags', []),
            'isbn': book_data.get('isbn', ''),
            'pages': book_data.get('pages', '')
        }
    
    @staticmethod
    def build_movie_info(movie_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        从电影数据构建标准内容信息
        
        Args:
            movie_data: 原始电影数据
            
        Returns:
            标准化的内容信息字典
        """
        return {
            'title': movie_data.get('title') or movie_data.get('name', ''),
            'director': movie_data.get('director') or movie_data.get('directors', ''),
            'actors': movie_data.get('actors') or movie_data.get('cast', ''),
            'genre': movie_data.get('genre') or movie_data.get('genres', ''),
            'year': movie_data.get('year') or movie_data.get('release_date', ''),
            'country': movie_data.get('country') or movie_data.get('countries', ''),
            'rating': movie_data.get('rating') or movie_data.get('score', ''),
            'summary': movie_data.get('summary') or movie_data.get('intro') or movie_data.get('description', ''),
            'duration': movie_data.get('duration', ''),
            'tags': movie_data.get('tags', [])
        }
    
    @staticmethod
    def build_music_info(music_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        从音乐数据构建标准内容信息
        
        Args:
            music_data: 原始音乐数据
            
        Returns:
            标准化的内容信息字典
        """
        return {
            'title': music_data.get('title') or music_data.get('name', ''),
            'singer': music_data.get('singer') or music_data.get('artist') or music_data.get('artists', ''),
            'album': music_data.get('album', ''),
            'year': music_data.get('year') or music_data.get('release_date', ''),
            'genre': music_data.get('genre', ''),
            'duration': music_data.get('duration', ''),
            'lyrics': music_data.get('lyrics', '')[:200] if music_data.get('lyrics') else ''
        }
