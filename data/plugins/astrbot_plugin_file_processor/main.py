from __future__ import annotations

import asyncio
import hashlib
import os
from typing import List, Optional
from sys import maxsize

from astrbot.api.event import AstrMessageEvent, MessageEventResult, filter
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.message.components import File, Image, Plain
from astrbot.api.event import MessageChain

# 导入统一用户ID工具
try:
    import sys
    from pathlib import Path
    plugin_root = Path(__file__).parent.parent
    if str(plugin_root) not in sys.path:
        sys.path.insert(0, str(plugin_root))
    from common.user_utils import get_unified_user_id
except ImportError:
    def get_unified_user_id(event):
        return event.get_sender_id()


@register(
    "astrbot_plugin_file_processor",
    "AstrBot",
    "接收文件/图片后回显详情（名称、后缀、大小、来源）",
    "1.0.0",
    "",
)
class FileProcessorPlugin(Star):
    """文件处理演示插件

    - 触发方式：任意消息中包含 File 或 Image 组件时
    - 行为：不下载，仅回显可得的元信息：名称、后缀、大小（若本地路径存在）、路径或 URL
    """

    def __init__(self, context: Context):
        super().__init__(context)
        logger.info("插件已加载")

    @filter.event_message_type(filter.EventMessageType.ALL, priority=maxsize)
    async def on_any_message(self, event: AstrMessageEvent):
        try:
            # 仅处理 Telegram 且来自指定用户的消息，其余直接忽略
            platform_name = (event.get_platform_name() or "").lower()
            if platform_name != "telegram":
                return
            allowed_ids = {"1087968824", "1606247770", "1623126769"}
            if str(event.get_sender_id()) not in allowed_ids:
                return

            files: List[File] = []
            images: List[Image] = []
            for seg in event.get_messages():
                if isinstance(seg, File):
                    files.append(seg)
                elif isinstance(seg, Image):
                    images.append(seg)

            if not files and not images:
                return

            # 可选：先发一条“收到文件”的提示
            yield event.plain_result("📥 收到文件，正在读取信息...")

            results: List[str] = []
            sender_name = event.get_sender_name() or "(未知)"
            sender_id = get_unified_user_id(event) or "(未知)"
            idx_counter = 1
            forward_jobs: List[tuple[str, str, str]] = []  # (target_id, file_id, book_info)
            logger.info(f"开始处理 {len(files)} 个文件")
            for i, f in enumerate(files):
                try:
                    logger.info(f"处理第 {i+1} 个文件: {f}")
                    # 不下载：仅拿到可用的路径或 URL
                    file_path_or_url = await f.get_file(allow_return_url=True)
                    logger.info(f"获取文件路径成功: {file_path_or_url}")

                    # 基本信息
                    name = f.name or os.path.basename(file_path_or_url) or "(未命名)"
                    ext = os.path.splitext(name)[1] if name and "." in name else ""
                    ext = ext.lstrip(".") if ext else "(无后缀)"

                    # 优先：元数据大小；回退：本地路径大小
                    size_text = self._get_size_text_from_metadata(event, kind="file") or ""
                    if not size_text:
                        size_text = await self._get_size_text_if_local(file_path_or_url)

                    # 源: 优先使用组件自带的 URL；否则尝试原始 file_ 字段（可能是 http URL 或本地路径）
                    source_text = getattr(f, "url", None) or ""
                    if not source_text:
                        raw_file = getattr(f, "file_", None) or ""
                        if isinstance(raw_file, str) and raw_file:
                            if raw_file.startswith("http://") or raw_file.startswith("https://"):
                                source_text = raw_file
                            elif os.path.exists(raw_file):
                                source_text = os.path.abspath(raw_file)
                    if not source_text:
                        source_text = file_path_or_url or "(未知来源)"

                    file_id = self._get_file_id_from_metadata(event, kind="file") or "(未知)"
                    caption = self._get_caption_from_metadata(event) or ""
                    caption_line = f"\ncaption: {caption}" if caption else ""
                    
                    # 检查是否是书籍文件（caption中包含SSID）
                    is_book_file, book_info_from_caption = self._is_book_file(caption)

                    # 尝试保存文件缓存
                    success = False
                    book_info_from_db = None
                    if is_book_file and file_id != "(未知)":
                        try:
                            # 将已解析的书籍信息传递给 _save_book_file_cache 方法
                            success, book_info_from_db = await self._save_book_file_cache(event, book_info_from_caption)
                        except Exception as e:
                            logger.error(f"保存书籍文件缓存异常: {e}")
                            import traceback
                            logger.error(traceback.format_exc())
                            success = False
                        if success:
                            logger.info(f"✅ 已保存书籍文件缓存: {name}")
                        else:
                            logger.error(f"❌ 保存书籍文件缓存失败: {name}")

                    # 检查是否需要转发
                    if "receive:" in caption and file_id != "(未知)":
                        try:
                            target_user_id = caption.split("receive:", 1)[1].split("|", 1)[0]
                            # 支持统一格式 "platform:raw_id" 或纯数字
                            # 提取原始 Telegram user_id 用于转发
                            if ":" in target_user_id:
                                # 统一格式: telegram:1623126769 -> 1623126769
                                raw_target_id = target_user_id.split(":", 1)[1]
                            else:
                                raw_target_id = target_user_id
                            
                            if raw_target_id.isdigit():
                                # 优先使用从数据库获取的详细信息，其次是caption中的信息
                                final_book_info = book_info_from_db or book_info_from_caption
                                logger.info(f"📤 准备转发文件到用户 {raw_target_id} (原始ID: {target_user_id})")
                                logger.info(f"📋 book_info_from_db: {book_info_from_db}")
                                logger.info(f"📋 book_info_from_caption: {book_info_from_caption}")
                                logger.info(f"📋 final_book_info: {final_book_info}")
                                # 使用原始 Telegram user_id 进行转发
                                forward_jobs.append((raw_target_id, file_id, final_book_info))
                        except Exception as e:
                            logger.error(f"解析转发目标用户失败: {e}")

                    elif caption and file_id != "(未知)":
                        logger.debug(f"非书籍文件，跳过缓存: {name[:50]}...")
                    else:
                        logger.debug(f"跳过文件处理: is_book_file={is_book_file}, file_id={file_id}")
                    
                    results.append(
                        f"{idx_counter}. [文件] 名称: {name}\n"
                        f"后缀: {ext}\n"
                        f"大小: {size_text}\n"
                        f"来源: {source_text}\n"
                        f"file_id: {file_id}"
                        f"{caption_line}"
                    )
                    idx_counter += 1
                except Exception as e:
                    import traceback
                    logger.error(f"处理第 {i+1} 个文件失败: {e}\n{traceback.format_exc()}")
                    continue
            
            # 统一处理转发任务（使用新的 target 参数）
            if forward_jobs:
                for target, file_id, book_info in forward_jobs:
                    caption = self._build_rich_caption(book_info)
                    logger.info(f"正在向 {target} 转发文件 {file_id}")
                    logger.info(f"🏷️ 生成的转发caption: {caption}")
                    logger.info(f"📚 用于生成caption的book_info: {book_info}")
                    try:
                        # 使用统一的 event.send() 发送到指定用户
                        file_comp = File(file=f"file_id:{file_id}", name="", caption=caption)
                        result = await event.send(MessageChain([file_comp]), target=str(target))
                        logger.info(f"成功转发文件到 {target}")
                        if result:
                            logger.debug(f"转发结果: 消息ID={result.message_id}")
                    except Exception as e:
                        logger.error(f"转发文件失败: {e}")

            # 回复给文件发送者
            if results:
                summary = "\n\n".join(results)
                header = f"👤 发送人: {sender_name} ({sender_id})\n"
                yield event.plain_result("✅ 文件信息:\n" + header + summary)
            
            # 处理完成后终止事件传播，不让LLM处理
            event.stop_event()
            logger.info("文件处理完成，已终止事件传播")
        except Exception as e:
            logger.error(f"处理失败: {e}", exc_info=True)
            # 不暴露详细错误信息给用户
            yield event.plain_result("❌ 处理失败，请稍后重试")
            # 即使出错也要终止事件传播
            event.stop_event()
            logger.info("文件处理出错，已终止事件传播")

    def _generate_backup_identifier(self, file_name: str, file_size: int) -> str:
        """
        为备用源文件生成唯一标识符
        
        Args:
            file_name: 文件名
            file_size: 文件大小（字节）
            
        Returns:
            格式为 backup:{文件名MD5前8位}_{文件大小} 的标识符
        """
        # 计算文件名的 MD5 哈希
        name_hash = hashlib.md5(file_name.encode('utf-8')).hexdigest()[:8]
        return f"backup:{name_hash}_{file_size}"

    async def _get_size_text_if_local(self, path_or_url: str) -> str:
        try:
            if not os.path.exists(path_or_url):
                # 非本地：可能是 URL 或空
                if path_or_url and (path_or_url.startswith("http://") or path_or_url.startswith("https://")):
                    return "(远程 URL，未下载)"
                return "(未知或不存在)"
            size = os.path.getsize(path_or_url)
            units = ["B", "KB", "MB", "GB", "TB"]
            s = float(size)
            for u in units:
                if s < 1024.0 or u == units[-1]:
                    if u == "B":
                        return f"{int(s)}B"
                    return f"{s:.2f}{u}"
                s /= 1024.0
            return f"{size}B"
        except Exception as e:
            logger.warning(f"获取大小失败: {e}")
            return "(未知)"

    def _bytes_to_human(self, size_bytes: int) -> str:
        try:
            s = float(size_bytes)
            units = ["B", "KB", "MB", "GB", "TB"]
            for u in units:
                if s < 1024.0 or u == units[-1]:
                    if u == "B":
                        return f"{int(s)}B"
                    return f"{s:.2f}{u}"
                s /= 1024.0
            return f"{size_bytes}B"
        except Exception:
            return str(size_bytes)

    def _get_size_text_from_metadata(self, event: AstrMessageEvent, kind: str) -> str | None:
        try:
            platform_name = (event.get_platform_name() or "").lower()
            raw = getattr(event.message_obj, "raw_message", None)
            if not raw:
                return None
            # Telegram: sizes exist on update.message.photo[i].file_size and update.message.document.file_size
            if platform_name == "telegram":
                try:
                    message = raw.message
                except Exception:
                    message = None
                if not message:
                    return None
                if kind == "image" and getattr(message, "photo", None):
                    try:
                        # use largest size (last element)
                        photo_sizes = message.photo
                        if photo_sizes:
                            fs = getattr(photo_sizes[-1], "file_size", None)
                            if fs:
                                return self._bytes_to_human(int(fs))
                    except Exception:
                        return None
                if kind == "file" and getattr(message, "document", None):
                    try:
                        fs = getattr(message.document, "file_size", None)
                        if fs:
                            return self._bytes_to_human(int(fs))
                    except Exception:
                        return None
            # TODO: 其他平台可在此扩展（如 Lark 等）
            return None
        except Exception:
            return None

    def _get_file_id_from_metadata(self, event: AstrMessageEvent, kind: str) -> str | None:
        try:
            platform_name = (event.get_platform_name() or "").lower()
            raw = getattr(event.message_obj, "raw_message", None)
            if not raw:
                return None
            if platform_name == "telegram":
                try:
                    message = raw.message
                except Exception:
                    message = None
                if not message:
                    return None
                if kind == "image" and getattr(message, "photo", None):
                    try:
                        photo_sizes = message.photo
                        if photo_sizes:
                            fid = getattr(photo_sizes[-1], "file_id", None)
                            if fid:
                                return str(fid)
                    except Exception:
                        return None
                if kind == "file" and getattr(message, "document", None):
                    try:
                        fid = getattr(message.document, "file_id", None)
                        if fid:
                            return str(fid)
                    except Exception:
                        return None
            return None
        except Exception:
            return None

    def _get_caption_from_metadata(self, event: AstrMessageEvent) -> str | None:
        try:
            platform_name = (event.get_platform_name() or "").lower()
            # 优先从平台原始消息读取
            raw = getattr(event.message_obj, "raw_message", None)
            if raw and platform_name == "telegram":
                try:
                    message = raw.message
                    cap = getattr(message, "caption", None)
                    if cap:
                        return str(cap)
                except Exception:
                    pass
            # 回退：使用解析后的 message_str
            cap2 = event.message_str or ""
            return cap2 if cap2.strip() else None
        except Exception:
            return None

    def _is_book_file(self, caption: str) -> tuple[bool, dict]:
        """
        检查文件是否是书籍文件，并尝试从caption中解析出基本书籍信息。
        返回 (是否是书籍文件, 解析出的书籍信息字典)
        """
        if not caption:
            return False, {}

        # 检查caption中是否包含SSID关键字
        caption_upper = caption.upper()
        if "SSID" in caption_upper:
            # 尝试从多行文本中解析
            book_info = {}
            lines = caption.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('书名:') or line.startswith('书名：'):
                    book_info['title'] = line.replace('书名:', '').replace('书名：', '').strip()
                elif line.startswith('作者:') or line.startswith('作者：'):
                    book_info['author'] = line.replace('作者:', '').replace('作者：', '').strip()
                elif line.startswith('SSID:') or line.startswith('SSID：'):
                    book_info['book_ssid'] = line.replace('SSID:', '').replace('SSID：', '').strip()
            return True, book_info
        
        # 检查是否包含8位数字SSID
        import re
        if re.search(r'\b\d{8}\b', caption):
            return True, {}

        # 检查是否包含书籍相关的关键词或文件格式
        book_keywords = ["书", "book", "小说", "novel", "pdf", "epub", "mobi", "azw3"]
        for keyword in book_keywords:
            if keyword in caption.lower():
                logger.debug(f"检测到书籍关键词'{keyword}'，判定为书籍文件")
                return True, {}
        
        return False, {}

    def _build_rich_caption(self, book_info: Optional[dict]) -> str:
        """根据书籍信息字典生成丰富的Caption"""
        if not book_info:
            return ""
        
        import json
        details_dict = {}
        # 如果 book_data 存在且是字符串，说明是从数据库缓存来的详细信息，需要解析
        if 'book_data' in book_info and isinstance(book_info['book_data'], str):
            try:
                details_dict = json.loads(book_info['book_data'])
            except json.JSONDecodeError:
                logger.error(f"解析 book_data JSON 失败: {book_info['book_data']}")
                details_dict = book_info # 解析失败，回退到使用外层字典
        else:
            # 否则，说明数据可能直接来自caption解析，直接使用顶层字典
            details_dict = book_info

        details = []
        if details_dict.get('title'):
            details.append(f"书名: {details_dict.get('title')}")
        if details_dict.get('author'):
            details.append(f"作者: {details_dict.get('author')}")
        if details_dict.get('publisher'):
            details.append(f"出版: {details_dict.get('publisher')}")
        if details_dict.get('year'):
            details.append(f"年份: {details_dict.get('year')}")
        if details_dict.get('pages'):
            details.append(f"页数: {details_dict.get('pages')}")
        if details_dict.get('isbn'):
            details.append(f"ISBN: {details_dict.get('isbn')}")
        
        # 兼容 book_ssid, ssid, id 三种可能的key，SSID总是从顶层获取
        ssid = book_info.get('book_ssid') or book_info.get('ssid') or book_info.get('id')
        if ssid:
             details.append(f"SSID: {ssid}")

        return "\n".join(details)


    async def _save_book_file_cache(self, event: AstrMessageEvent, book_info_from_caption: Optional[dict] = None) -> tuple[bool, Optional[dict]]:
        """
        保存书籍文件缓存到云盘插件数据库。
        
        Args:
            event: 消息事件
            book_info_from_caption: 从caption中解析出的书籍信息
            
        返回 (是否成功, 从数据库获取的书籍详情字典)
        """
        import os
        import sys
        logger.debug("--- 开始执行 _save_book_file_cache ---")
        try:
            file_id = self._get_file_id_from_metadata(event, kind="file") or "(未知)"
            sender_id = get_unified_user_id(event)
            logger.debug(f"获取到 file_id: {file_id}, sender_id: {sender_id}")
            
            if not file_id or file_id == "(未知)":
                logger.error(f"无效的file_id，跳过缓存")
                return False, None

            # 解析书籍信息
            book_ssid = ""
            book_title = ""
            author = ""
            
            # 优先从传入的 book_info_from_caption 获取信息
            if book_info_from_caption:
                book_ssid = book_info_from_caption.get('book_ssid', '')
                book_title = book_info_from_caption.get('title', '')
                author = book_info_from_caption.get('author', '')
                logger.debug(f"从caption解析获得: book_ssid='{book_ssid}', title='{book_title}', author='{author}'")
            
            # 从 event 的消息组件中提取文件名
            file_name = ""
            for seg in event.get_messages():
                if isinstance(seg, File):
                    file_name = seg.name or ""
                    break
            caption = self._get_caption_from_metadata(event) or ""
            logger.debug(f"获取到文件名: '{file_name}'")
            logger.debug(f"获取到caption: '{caption}'")

            # 初始化API数据变量
            api_size = None
            api_format = None
            
            # 解析 caption 获取 api_size 和 api_format（用于缓存匹配）
            # 即使已有 book_ssid，也需要解析这些信息
            if caption.startswith("receive:") and "|book_info:" in caption:
                try:
                    book_info_part = caption.split("|book_info:", 1)[1]
                    
                    # 尝试解析新格式: SSID:12345678,size:15515814,format:pdf
                    import re
                    if "size:" in book_info_part and "format:" in book_info_part:
                        ssid_match = re.search(r'SSID:(\d{8})', book_info_part)
                        size_match = re.search(r'size:(\d+)', book_info_part)
                        format_match = re.search(r'format:([a-z]+)', book_info_part)
                        
                        if ssid_match and not book_ssid:
                            book_ssid = ssid_match.group(1)
                        if size_match:
                            api_size = int(size_match.group(1))
                        if format_match:
                            api_format = format_match.group(1)
                    else:
                        # 解析旧格式的多行文本
                        lines = book_info_part.split('\n')
                        logger.debug(f"解析book_info_part行数: {len(lines)}")
                        for line in lines:
                            line = line.strip()
                            logger.debug(f"处理行: '{line}'")
                            # 检查新的结构化格式
                            if line.startswith('SSID_SIZE_FORMAT:'):
                                # 格式: SSID_SIZE_FORMAT:27775148:pdf
                                parts = line.split(':', 2)
                                if len(parts) >= 3:
                                    api_size = int(parts[1])
                                    api_format = parts[2]
                                    logger.debug(f"从SSID_SIZE_FORMAT提取: size={api_size}, format={api_format}")
                            elif line.startswith('SSID:') or line.startswith('SSID：'):
                                if not book_ssid:
                                    book_ssid = line.replace('SSID:', '').replace('SSID：', '').strip()
                                    logger.debug(f"提取SSID: '{book_ssid}'")
                            elif line.startswith('书名:') or line.startswith('书名：'):
                                book_title = line.replace('书名:', '').replace('书名：', '').strip()
                                logger.debug(f"提取书名: '{book_title}'")
                except Exception:
                    pass
            
            # 如果新格式解析失败，回退到旧格式解析
            if not book_ssid:
                lines = caption.split('\n')
                
                # 方法1: 标准格式解析
                for line in lines:
                    line = line.strip()
                    if line.startswith('书名:') or line.startswith('书名：'):
                        book_title = line.replace('书名:', '').replace('书名：', '').strip()
                    elif line.startswith('作者:') or line.startswith('作者：'):
                        author = line.replace('作者:', '').replace('作者：', '').strip()
                    elif line.startswith('SSID:') or line.startswith('SSID：'):
                        book_ssid = line.replace('SSID:', '').replace('SSID：', '').strip()
                
                logger.debug(f"标准格式解析后: book_title='{book_title}', author='{author}', book_ssid='{book_ssid}'")
                
                # 方法2: 如果没有找到SSID，尝试提取8位数字
                if not book_ssid:
                    import re
                    ssid_matches = re.findall(r'\b\d{8}\b', caption)
                    if ssid_matches:
                        book_ssid = ssid_matches[0]  # 使用第一个8位数字
                        logger.debug(f"从caption中提取8位数字作为SSID: {book_ssid}")
            
            # 方法3: 如果没有书名，尝试从文件名提取
            if not book_title and file_name:
                # 移除文件扩展名作为书名
                book_title = file_name.rsplit('.', 1)[0] if '.' in file_name else file_name
                logger.debug(f"从文件名中提取书名: {book_title}")
            
            # 检查是否有有效的SSID，如果没有则生成备用标识符
            logger.debug(f"最终解析结果: book_ssid='{book_ssid}', book_title='{book_title}', author='{author}'")
            
            use_backup_id = False
            if not book_ssid or not book_ssid.isdigit() or len(book_ssid) != 8:
                logger.info(f"无有效SSID: '{book_ssid}'，将使用备用标识符进行缓存")
                use_backup_id = True
            
            # 解析文件大小 - 优先使用API数据
            if api_size is not None:
                file_size = api_size
            else:
                file_size = 0
                size_text = self._get_size_text_from_metadata(event, kind="file") or ""
                if size_text and size_text != "(未知)":
                    try:
                        # 解析类似 "12.34MB" 的格式
                        import re
                        match = re.match(r'([\d.]+)([A-Z]+)', size_text.upper())
                        if match:
                            size_val = float(match.group(1))
                            unit = match.group(2)
                            multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
                            file_size = int(size_val * multipliers.get(unit, 1))
                    except Exception:
                        pass
            
            # 获取文件格式 - 优先使用API数据
            if api_format:
                file_format = f".{api_format}"
            else:
                ext = os.path.splitext(file_name)[1] if file_name and "." in file_name else ""
                file_format = ext.lower() if ext and ext != "(无后缀)" else ""
            
            logger.debug(f"解析得到 file_size: {file_size} bytes, file_format: '{file_format}'")

            # 生成file_tag
            file_tag = self._get_file_tag(file_size, file_format)
            logger.debug(f"生成的 file_tag: '{file_tag}'")
            
            # 导入云盘插件的数据库管理器
            plugins_path = os.path.dirname(os.path.dirname(__file__))
            if plugins_path not in sys.path:
                sys.path.append(plugins_path)
            
            try:
                from astrbot_plugin_book.db.database import BookDatabaseManager
                from astrbot_plugin_book.db.models import TelegramBookFileCache
                from datetime import datetime
                import json
                from dataclasses import asdict
            except ImportError as e:
                logger.error(f"导入书籍插件模块失败: {e}. 请确保 'astrbot_plugin_book' 插件存在且结构正确。")
                return False, None
            
            # 获取数据库路径 (与 book 插件保持一致)
            current_plugin_dir = os.path.dirname(__file__)
            plugins_dir = os.path.dirname(current_plugin_dir)
            data_dir = os.path.dirname(plugins_dir)
            book_data_path = os.path.join(data_dir, "plugin_data", "book")

            # 如果目录不存在则创建
            if not os.path.isdir(book_data_path):
                os.makedirs(book_data_path, exist_ok=True)
                logger.info(f"创建书籍插件数据目录: {book_data_path}")

            db_path = os.path.join(book_data_path, "book.db")
            
            # 建立数据库连接
            try:
                logger.debug(f"正在连接数据库: {db_path}")
                db = BookDatabaseManager(db_path)
                
                # 优先从数据库获取详细信息，其次使用caption信息
                book_info_json = None
                book_info_dict = None
                
                # 首先尝试从数据库获取完整详情
                try:
                    if use_backup_id:
                        # 生成备用标识符
                        backup_id = self._generate_backup_identifier(file_name, file_size)
                        logger.info(f"🔍 使用备用标识符查询: {backup_id}")
                        # 对于备用源，暂时跳过数据库查询（因为通常没有详情缓存）
                        detail_cache = None
                        book_ssid = backup_id  # 使用备用标识符作为 book_ssid
                    else:
                        logger.info(f"🔍 尝试从数据库 book_detail_cache 表中获取SSID {book_ssid} 的详细信息")
                        detail_cache = db.get_book_detail_cache(book_ssid)
                    
                    if detail_cache:
                        logger.info(f"✅ 找到书籍详情缓存: {book_ssid}")
                        logger.info(f"📖 详情缓存内容: {detail_cache.book_data[:200]}...")
                        # BookDetailCache 的 book_data 字段包含完整的书籍信息JSON
                        import json
                        try:
                            book_data = json.loads(detail_cache.book_data)
                            
                            # 构建 book_info_dict，包含 book_data 和其他元数据
                            from dataclasses import asdict
                            book_info_dict = asdict(detail_cache)
                            
                            # 从解析的 book_data 中获取标题和作者
                            book_title = book_data.get('title', book_title)
                            author = book_data.get('author', author)
                            logger.info(f"从详情缓存获取到书籍信息: {book_title} - {author}")
                            
                            # 将完整的缓存信息序列化为 JSON，处理 datetime 对象
                            
                            # 处理 datetime 对象，转换为字符串
                            serializable_dict = book_info_dict.copy()
                            for key, value in serializable_dict.items():
                                if hasattr(value, 'isoformat'):  # datetime 对象
                                    serializable_dict[key] = value.isoformat()
                            
                            book_info_json = json.dumps(serializable_dict, ensure_ascii=False)
                        except json.JSONDecodeError as je:
                            logger.error(f"解析 book_data JSON 失败: {je}")
                            logger.error(f"book_data 内容: {detail_cache.book_data}")
                            # 回退：直接使用 dataclass 的字典形式
                            from dataclasses import asdict
                            book_info_dict = asdict(detail_cache)
                            # 处理 datetime 对象
                            serializable_dict = book_info_dict.copy()
                            for key, value in serializable_dict.items():
                                if hasattr(value, 'isoformat'):  # datetime 对象
                                    serializable_dict[key] = value.isoformat()
                            book_info_json = json.dumps(serializable_dict, ensure_ascii=False)
                    else:
                        logger.info(f"❌ SSID {book_ssid} 在 book_detail_cache 中没有找到记录")
                except Exception as e:
                    logger.debug(f"获取书籍详情缓存失败: {e}")
                
                # 如果数据库查询失败，回退到使用caption信息
                if not book_info_dict and book_info_from_caption:
                    logger.info(f"📝 回退使用caption中的书籍信息: {book_info_from_caption.get('title', 'N/A')} - {book_info_from_caption.get('author', 'N/A')}")
                    book_info_dict = book_info_from_caption.copy()
                    import json
                    book_info_json = json.dumps(book_info_dict, ensure_ascii=False)
                elif use_backup_id:
                    # 备用源不创建 book_info，避免生成无用的 caption
                    logger.info(f"📝 备用源文件跳过 book_info 创建，避免无用信息")
                    book_info_json = None
                
                logger.debug(f"最终准备写入数据库的 book_info (JSON): {book_info_json}")
                cache = TelegramBookFileCache(
                    book_ssid=book_ssid,
                    file_format=file_format,
                    file_tag=file_tag,
                    file_id=file_id,
                    file_size=file_size,
                    file_name=file_name,
                    book_info=book_info_json,
                    mime_type=None,
                    uploaded_by=sender_id
                )
                
                logger.debug(f"准备写入 TelegramBookFileCache: {cache}")
                success = db.save_file_cache(cache)
                if success:
                    logger.info(f"✅ 数据库保存成功: SSID={book_ssid}, file_id={file_id}")
                    return True, book_info_dict
                else:
                    logger.error(f"数据库 save_file_cache 方法返回 False，保存失败")
                    return False, None
            except Exception as e:
                logger.error(f"数据库操作失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return False, None
            
        except Exception as e:
            logger.error(f"保存书籍文件缓存时发生未知异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False, None

    def _get_file_tag(self, size_bytes: int, file_format: str) -> str:
        """生成文件唯一标识 (文件大小+格式)，与book插件保持一致"""
        # 移除格式中的点，格式：{size}{ext_without_dot}
        clean_format = file_format.replace('.', '').lower()
        return f"{size_bytes}{clean_format}"


