"""
推送内容格式化器

根据订阅源的推送配置，生成不同格式的推送内容：
1. full - 完整内容
2. ai_summary - AI摘要（整合系统LLM）
3. brief - 简要提醒（标题+链接）
4. title_list - 标题列表

使用示例：
    from common.push_formatter import PushFormatter, init_push_formatter
    
    # 初始化（需要传入 context 以使用 AI 功能）
    formatter = init_push_formatter(context)
    
    # 格式化推送内容
    content = await formatter.format_push_content(
        source=source,
        items=content_items
    )
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from .message_formatter import get_separator

try:
    from astrbot.api import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# 导入 AI 解读器
try:
    from .ai_interpreter import get_ai_interpreter, AIInterpreter
except ImportError:
    get_ai_interpreter = None
    AIInterpreter = None


@dataclass
class FormattedPushContent:
    """格式化后的推送内容"""
    title: str = ""                 # 推送标题
    body: str = ""                  # 推送正文
    items: List[Dict] = None        # 原始条目（用于去重）
    mode: str = "full"              # 使用的模式
    item_count: int = 0             # 条目数量
    
    def __post_init__(self):
        if self.items is None:
            self.items = []
    
    # 用于反馈的元数据
    source_id: int = 0
    content_hash: str = ""
    
    def to_message(self) -> str:
        """转换为消息文本"""
        if self.title and self.body:
            return f"{self.title}\n\n{self.body}"
        return self.body or self.title
    
    def to_message_with_feedback(self) -> str:
        """转换为带反馈提示的消息文本"""
        msg = self.to_message()
        if self.source_id:
            msg += f"\n\n💬 回复 👍/👎 反馈本次推送"
        return msg
    
    def get_feedback_buttons(self) -> list:
        """
        获取反馈按钮（用于支持按钮的平台）
        
        Returns:
            按钮列表 [[{text, callback_data}]]
        """
        if not self.source_id:
            return []
        
        return [[
            {"text": "👍 有用", "callback_data": f"subscription:feedback:{self.source_id}:useful:{self.content_hash[:16] if self.content_hash else ''}"},
            {"text": "👎 无用", "callback_data": f"subscription:feedback:{self.source_id}:useless:{self.content_hash[:16] if self.content_hash else ''}"}
        ]]


class PushFormatter:
    """推送内容格式化器"""
    
    # 默认AI摘要提示词
    DEFAULT_AI_PROMPT = """请对以下订阅内容进行简洁的摘要总结。

要求：
1. 提取核心要点，字数控制在200字以内
2. 使用简洁的语言，避免冗余
3. 保留关键信息和数据
4. 适合快速阅读
5. 不要使用表格、Markdown格式

内容：
{content}

请直接输出摘要，不要有开头语。"""

    # AI摘要系统提示词
    AI_SYSTEM_PROMPT = "你是一位专业的内容摘要助手。请用简洁、口语化的方式总结内容要点，避免使用表格、列表符号等格式。"
    
    def __init__(self, context=None):
        """
        初始化格式化器
        
        Args:
            context: AstrBot Context（用于AI摘要）
        """
        self.context = context
        self._ai_interpreter = None
    
    @property
    def ai_interpreter(self):
        """获取 AI 解读器（延迟初始化）"""
        if self._ai_interpreter is None and self.context and get_ai_interpreter:
            try:
                self._ai_interpreter = get_ai_interpreter(self.context)
            except Exception as e:
                logger.warning(f"[PushFormatter] 初始化 AI 解读器失败: {e}")
        return self._ai_interpreter
    
    async def format_push_content(
        self,
        source,
        items: List[Dict],
        override_mode: str = None
    ) -> FormattedPushContent:
        """
        格式化推送内容
        
        Args:
            source: 订阅源对象
            items: 内容条目列表，每个条目包含 title, content, url, published_at 等
            override_mode: 覆盖推送模式（可选）
            
        Returns:
            FormattedPushContent 对象
        """
        if not items:
            return FormattedPushContent(
                title="📭 暂无新内容",
                body="",
                mode="empty"
            )
        
        # 获取推送配置
        mode = override_mode or getattr(source, 'push_content_mode', 'full') or 'full'
        max_items = getattr(source, 'push_max_items', 5) or 5
        include_link = getattr(source, 'push_include_link', True)
        ai_prompt = getattr(source, 'push_ai_prompt', '') or self.DEFAULT_AI_PROMPT
        
        # 限制条目数
        items = items[:max_items]
        
        # 获取源信息
        source_icon = getattr(source, 'icon', '📰')
        source_title = source.get_display_title() if hasattr(source, 'get_display_title') else getattr(source, 'display_name', '')
        
        # 根据模式格式化
        if mode == 'full':
            return await self._format_full(source_icon, source_title, items, include_link)
        elif mode == 'ai_summary':
            return await self._format_ai_summary(source_icon, source_title, items, include_link, ai_prompt)
        elif mode == 'brief':
            return await self._format_brief(source_icon, source_title, items, include_link)
        elif mode == 'title_list':
            return await self._format_title_list(source_icon, source_title, items, include_link)
        else:
            # 默认使用完整模式
            return await self._format_full(source_icon, source_title, items, include_link)
    
    async def _format_full(
        self, 
        source_icon: str, 
        source_title: str, 
        items: List[Dict],
        include_link: bool
    ) -> FormattedPushContent:
        """完整内容模式"""
        title = f"{source_icon} {source_title}"
        
        body_parts = []
        for i, item in enumerate(items, 1):
            item_title = item.get('title') or '无标题'
            item_content = item.get('content') or item.get('description') or ''
            item_url = item.get('url', item.get('link', ''))
            
            # 如果标题、内容、URL都为空，跳过该条目
            if item_title == '无标题' and not item_content.strip() and not item_url:
                continue
            
            # 限制内容长度（对于新闻列表类内容，放宽限制）
            max_content_length = 2000  # 增加到 2000 字符
            if len(item_content) > max_content_length:
                item_content = item_content[:max_content_length] + "..."
            
            # 构建条目内容
            if item_content.strip():
                part = f"📌 {item_title}\n\n{item_content}"
            else:
                part = f"📌 {item_title}"
            
            if include_link and item_url:
                part += f"\n\n🔗 {item_url}"
            
            body_parts.append(part)
        
        separator = get_separator()
        body = f"\n\n{separator}\n\n".join(body_parts)
        
        # 如果所有条目都被过滤，返回空内容提示
        if not body_parts:
            return FormattedPushContent(
                title=title,
                body="📭 暂无有效内容",
                items=items,
                mode='empty',
                item_count=0
            )
        
        return FormattedPushContent(
            title=title,
            body=body,
            items=items,
            mode='full',
            item_count=len(body_parts)
        )
    
    async def _format_ai_summary(
        self, 
        source_icon: str, 
        source_title: str, 
        items: List[Dict],
        include_link: bool,
        ai_prompt: str
    ) -> FormattedPushContent:
        """AI摘要模式"""
        title = f"{source_icon} {source_title} · AI摘要"
        
        # 合并所有内容
        all_content = []
        for item in items:
            item_title = item.get('title', '')
            item_content = item.get('content', item.get('description', ''))
            all_content.append(f"【{item_title}】\n{item_content}")
        
        combined_content = "\n\n".join(all_content)
        
        # 调用AI生成摘要
        summary = await self._generate_ai_summary(combined_content, ai_prompt)
        
        body = f"🤖 AI摘要:\n\n{summary}"
        
        # 添加原文链接
        if include_link:
            links = []
            for item in items[:3]:  # 最多3个链接
                item_title = item.get('title', '查看原文')[:20]
                item_url = item.get('url', item.get('link', ''))
                if item_url:
                    links.append(f"• {item_title}: {item_url}")
            
            if links:
                body += "\n\n📎 原文链接:\n" + "\n".join(links)
        
        return FormattedPushContent(
            title=title,
            body=body,
            items=items,
            mode='ai_summary',
            item_count=len(items)
        )
    
    async def _format_brief(
        self, 
        source_icon: str, 
        source_title: str, 
        items: List[Dict],
        include_link: bool
    ) -> FormattedPushContent:
        """简要提醒模式"""
        title = f"{source_icon} {source_title} 有新内容"
        
        body_parts = []
        for item in items:
            item_title = item.get('title') or '无标题'
            item_url = item.get('url', item.get('link', ''))
            
            # 如果标题和URL都为空，跳过该条目
            if not item_title.strip() and not item_url:
                continue
            
            if include_link and item_url:
                body_parts.append(f"📌 {item_title}\n   🔗 {item_url}")
            else:
                body_parts.append(f"📌 {item_title}")
        
        body = "\n\n".join(body_parts)
        
        # 如果所有条目都被过滤，返回空内容提示
        if not body_parts:
            return FormattedPushContent(
                title=title,
                body="📭 暂无有效内容",
                items=items,
                mode='empty',
                item_count=0
            )
        
        return FormattedPushContent(
            title=title,
            body=body,
            items=items,
            mode='brief',
            item_count=len(body_parts)
        )
    
    async def _format_title_list(
        self, 
        source_icon: str, 
        source_title: str, 
        items: List[Dict],
        include_link: bool
    ) -> FormattedPushContent:
        """标题列表模式"""
        title = f"{source_icon} {source_title} · {len(items)}条更新"
        
        body_parts = []
        index = 1
        for item in items:
            item_title = item.get('title') or '无标题'
            item_url = item.get('url', item.get('link', ''))
            
            # 如果标题为空或仅为"无标题"且无URL，跳过该条目
            if item_title == '无标题' and not item_url:
                continue
            
            if include_link and item_url:
                body_parts.append(f"{index}. {item_title}\n   {item_url}")
            else:
                body_parts.append(f"{index}. {item_title}")
            index += 1
        
        body = "\n".join(body_parts)
        
        # 如果所有条目都被过滤，返回空内容提示
        if not body_parts:
            return FormattedPushContent(
                title=title,
                body="📭 暂无有效内容",
                items=items,
                mode='empty',
                item_count=0
            )
        
        return FormattedPushContent(
            title=title,
            body=body,
            items=items,
            mode='title_list',
            item_count=len(body_parts)
        )
    
    async def _generate_ai_summary(self, content: str, prompt_template: str) -> str:
        """
        生成AI摘要（使用系统 AIInterpreter）
        
        Args:
            content: 原始内容
            prompt_template: 提示词模板
            
        Returns:
            AI生成的摘要
        """
        # 优先使用 AIInterpreter
        if self.ai_interpreter:
            try:
                # 使用自定义提示词调用 AI
                result = await self.ai_interpreter.interpret(
                    content_type='subscription',  # 订阅内容类型
                    content_info={'content': content[:3000]},  # 限制长度
                    custom_prompt=prompt_template.format(content=content[:3000]),
                    system_prompt=self.AI_SYSTEM_PROMPT,
                    max_length=200
                )
                
                if result:
                    return result.strip()
                    
            except Exception as e:
                logger.error(f"[PushFormatter] AI摘要生成失败: {e}")
        else:
            logger.debug("[PushFormatter] AI解读器不可用，使用简单摘要")
        
        # 降级：使用简单摘要
        return self._simple_summary(content)
    
    async def generate_summary_with_provider(self, content: str, provider) -> str:
        """
        使用指定的 Provider 生成摘要（备用方法）
        
        Args:
            content: 原始内容
            provider: LLM Provider
            
        Returns:
            AI生成的摘要
        """
        if not provider:
            return self._simple_summary(content)
        
        try:
            prompt = self.DEFAULT_AI_PROMPT.format(content=content[:3000])
            
            response = await provider.text_chat(
                prompt=prompt,
                session_id=f"push_summary_{hash(content[:100])}",
                system_prompt=self.AI_SYSTEM_PROMPT
            )
            
            if response:
                if hasattr(response, 'completion_text') and response.completion_text:
                    return response.completion_text.strip()
                elif hasattr(response, 'result_chain') and response.result_chain:
                    text = "".join(
                        c.text for c in response.result_chain.chain 
                        if hasattr(c, 'text')
                    )
                    return text.strip() if text else self._simple_summary(content)
            
            return self._simple_summary(content)
            
        except Exception as e:
            logger.error(f"[PushFormatter] Provider AI摘要生成失败: {e}")
            return self._simple_summary(content)
    
    def _simple_summary(self, content: str, max_length: int = 300) -> str:
        """简单摘要（截取前N个字符）"""
        # 移除多余空白
        content = ' '.join(content.split())
        
        if len(content) <= max_length:
            return content
        
        # 尝试在句子边界截断
        truncated = content[:max_length]
        
        # 查找最后一个句号、问号或感叹号
        for sep in ['。', '！', '？', '.', '!', '?']:
            last_pos = truncated.rfind(sep)
            if last_pos > max_length // 2:
                return truncated[:last_pos + 1]
        
        return truncated + "..."


# 全局实例
_push_formatter: Optional[PushFormatter] = None


def get_push_formatter(context=None) -> PushFormatter:
    """
    获取推送格式化器实例
    
    Args:
        context: AstrBot Context（首次调用时需要提供以启用AI功能）
        
    Returns:
        PushFormatter 实例
    """
    global _push_formatter
    if _push_formatter is None:
        _push_formatter = PushFormatter(context)
    elif context and _push_formatter.context is None:
        _push_formatter.context = context
    return _push_formatter


def init_push_formatter(context=None) -> PushFormatter:
    """
    初始化推送格式化器
    
    Args:
        context: AstrBot Context（用于AI摘要功能）
        
    Returns:
        PushFormatter 实例
    """
    global _push_formatter
    _push_formatter = PushFormatter(context)
    logger.info("[PushFormatter] 推送格式化器初始化完成")
    return _push_formatter
