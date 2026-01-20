"""
订阅源项目配置

存放已知API项目的端点配置，便于维护和扩展。
每个项目包含：
- name: 项目名称
- category: 默认分类
- endpoints: 端点列表，每个端点包含 path, name, display_name, icon, category, description
"""

# 已知API项目模板
KNOWN_PROJECTS = {
    # ==================== 60s-API ====================
    '60s.viki.moe': {
        'name': '60s-API',
        'category': '综合资讯',
        'description': '60s读懂世界API，提供新闻、热搜、天气等多种服务',
        'docs': 'https://docs.60s-api.viki.moe',
        'endpoints': [
            # 新闻资讯
            {'path': '/v2/60s', 'name': '60s', 'display_name': '每日60秒读懂世界', 'icon': '📰', 'category': '新闻资讯', 'description': '每天60秒读懂世界新闻'},
            {'path': '/v2/toutiao', 'name': 'toutiao', 'display_name': '今日头条热榜', 'icon': '📱', 'category': '新闻资讯', 'description': '今日头条热门新闻'},
            {'path': '/v2/ai-news', 'name': 'ai-news', 'display_name': 'AI新闻', 'icon': '🤖', 'category': '新闻资讯', 'description': 'AI领域最新资讯'},
            {'path': '/v2/today-in-history', 'name': 'today-in-history', 'display_name': '历史上的今天', 'icon': '📅', 'category': '新闻资讯', 'description': '历史上的今天发生了什么'},
            
            # 热搜榜单
            {'path': '/v2/weibo', 'name': 'weibo', 'display_name': '微博热搜', 'icon': '🔥', 'category': '热搜榜单', 'description': '微博实时热搜榜'},
            {'path': '/v2/zhihu', 'name': 'zhihu', 'display_name': '知乎热榜', 'icon': '💡', 'category': '热搜榜单', 'description': '知乎热门问题'},
            {'path': '/v2/baidu/hot', 'name': 'baidu-hot', 'display_name': '百度热搜', 'icon': '🔍', 'category': '热搜榜单', 'description': '百度实时热搜'},
            {'path': '/v2/bili', 'name': 'bili', 'display_name': 'B站热榜', 'icon': '📺', 'category': '热搜榜单', 'description': 'B站热门视频'},
            {'path': '/v2/douyin', 'name': 'douyin', 'display_name': '抖音热搜', 'icon': '🎵', 'category': '热搜榜单', 'description': '抖音热门话题'},
            {'path': '/v2/rednote', 'name': 'rednote', 'display_name': '小红书热榜', 'icon': '📕', 'category': '热搜榜单', 'description': '小红书热门内容'},
            {'path': '/v2/baidu/tieba', 'name': 'baidu-tieba', 'display_name': '贴吧热议', 'icon': '💬', 'category': '热搜榜单', 'description': '百度贴吧热议话题'},
            {'path': '/v2/hacker-news/top', 'name': 'hacker-news-top', 'display_name': 'Hacker News热榜', 'icon': '💻', 'category': '热搜榜单', 'description': 'Hacker News热门'},
            
            # 影视娱乐
            {'path': '/v2/maoyan/realtime/movie', 'name': 'maoyan-movie', 'display_name': '猫眼电影实时榜', 'icon': '🎬', 'category': '影视娱乐', 'description': '猫眼电影实时票房'},
            {'path': '/v2/maoyan/realtime/tv', 'name': 'maoyan-tv', 'display_name': '猫眼电视剧榜', 'icon': '📺', 'category': '影视娱乐', 'description': '猫眼电视剧热度榜'},
            {'path': '/v2/maoyan/realtime/web', 'name': 'maoyan-web', 'display_name': '猫眼网络剧榜', 'icon': '🎭', 'category': '影视娱乐', 'description': '猫眼网络剧热度榜'},
            {'path': '/v2/baidu/teleplay', 'name': 'baidu-teleplay', 'display_name': '百度电视剧榜', 'icon': '📺', 'category': '影视娱乐', 'description': '百度电视剧搜索榜'},
            {'path': '/v2/dongchedi', 'name': 'dongchedi', 'display_name': '懂车帝榜单', 'icon': '🚗', 'category': '生活服务', 'description': '懂车帝汽车热榜'},
            
            # 音乐榜单
            {'path': '/v2/ncm-rank/list', 'name': 'ncm-rank-list', 'display_name': '网易云音乐榜单', 'icon': '🎵', 'category': '音乐榜单', 'description': '网易云音乐各类榜单'},
            {'path': '/v2/changya', 'name': 'changya', 'display_name': '唱鸭热歌榜', 'icon': '🎤', 'category': '音乐榜单', 'description': '唱鸭热门歌曲'},
            
            # 游戏资讯
            {'path': '/v2/epic', 'name': 'epic', 'display_name': 'Epic免费游戏', 'icon': '🎮', 'category': '游戏资讯', 'description': 'Epic商城免费游戏'},
            
            # 生活服务
            {'path': '/v2/weather/realtime', 'name': 'weather-realtime', 'display_name': '实时天气', 'icon': '🌤️', 'category': '生活服务', 'description': '实时天气查询'},
            {'path': '/v2/weather/forecast', 'name': 'weather-forecast', 'display_name': '天气预报', 'icon': '☁️', 'category': '生活服务', 'description': '未来天气预报'},
            {'path': '/v2/exchange-rate', 'name': 'exchange-rate', 'display_name': '汇率查询', 'icon': '💱', 'category': '生活服务', 'description': '实时汇率查询'},
            {'path': '/v2/lunar', 'name': 'lunar', 'display_name': '农历日历', 'icon': '📆', 'category': '生活服务', 'description': '农历日期查询'},
            {'path': '/v2/luck', 'name': 'luck', 'display_name': '今日运势', 'icon': '🔮', 'category': '生活服务', 'description': '每日运势查询'},
            {'path': '/v2/health', 'name': 'health', 'display_name': '健康小贴士', 'icon': '💊', 'category': '生活服务', 'description': '每日健康提示'},
            
            # 图片壁纸
            {'path': '/v2/bing', 'name': 'bing', 'display_name': '必应每日壁纸', 'icon': '🖼️', 'category': '图片壁纸', 'description': '必应每日精选壁纸'},
            
            # 知识百科
            {'path': '/v2/baike', 'name': 'baike', 'display_name': '百科知识', 'icon': '📚', 'category': '知识百科', 'description': '百科知识查询'},
            {'path': '/v2/chemical', 'name': 'chemical', 'display_name': '化学元素', 'icon': '⚗️', 'category': '知识百科', 'description': '化学元素查询'},
            {'path': '/v2/answer', 'name': 'answer', 'display_name': '知识问答', 'icon': '❓', 'category': '知识百科', 'description': '知识问答'},
            
            # 趣味内容
            {'path': '/v2/hitokoto', 'name': 'hitokoto', 'display_name': '一言', 'icon': '💭', 'category': '趣味内容', 'description': '随机一言'},
            {'path': '/v2/duanzi', 'name': 'duanzi', 'display_name': '搞笑段子', 'icon': '😂', 'category': '趣味内容', 'description': '随机搞笑段子'},
            {'path': '/v2/kfc', 'name': 'kfc', 'display_name': 'KFC疯狂星期四', 'icon': '🍗', 'category': '趣味内容', 'description': 'KFC疯狂星期四文案'},
            {'path': '/v2/fabing', 'name': 'fabing', 'display_name': '发病文学', 'icon': '💔', 'category': '趣味内容', 'description': '发病文学生成'},
            {'path': '/v2/dad-joke', 'name': 'dad-joke', 'display_name': '冷笑话', 'icon': '🥶', 'category': '趣味内容', 'description': '英文冷笑话'},
            
            # 开发工具
            {'path': '/v2/ip', 'name': 'ip', 'display_name': 'IP查询', 'icon': '🌐', 'category': '开发工具', 'description': 'IP地址查询'},
            {'path': '/v2/qrcode', 'name': 'qrcode', 'display_name': '二维码生成', 'icon': '📱', 'category': '开发工具', 'description': '二维码生成'},
            {'path': '/v2/hash', 'name': 'hash', 'display_name': '哈希计算', 'icon': '🔐', 'category': '开发工具', 'description': '哈希值计算'},
            {'path': '/v2/password', 'name': 'password', 'display_name': '密码生成', 'icon': '🔑', 'category': '开发工具', 'description': '随机密码生成'},
            {'path': '/v2/fanyi', 'name': 'fanyi', 'display_name': '翻译', 'icon': '🌍', 'category': '开发工具', 'description': '多语言翻译'},
            {'path': '/v2/og', 'name': 'og', 'display_name': 'OG信息解析', 'icon': '🔗', 'category': '开发工具', 'description': '网页OG信息解析'},
            {'path': '/v2/color/random', 'name': 'color-random', 'display_name': '随机颜色', 'icon': '🎨', 'category': '开发工具', 'description': '随机颜色生成'},
            {'path': '/v2/awesome-js', 'name': 'awesome-js', 'display_name': 'JS库推荐', 'icon': '📦', 'category': '开发工具', 'description': 'JavaScript库推荐'},
        ]
    },
    
    # ==================== 韩小韩API ====================
    'api.vvhan.com': {
        'name': '韩小韩API',
        'category': '综合资讯',
        'description': '韩小韩API接口站，提供热搜、新闻等服务',
        'docs': 'https://api.vvhan.com/',
        'endpoints': [
            {'path': '/api/60s', 'name': '60s', 'display_name': '每日60秒新闻', 'icon': '📰', 'category': '新闻资讯', 'description': '每日60秒新闻'},
            {'path': '/api/hotlist/wbHot', 'name': 'weibo', 'display_name': '微博热搜榜', 'icon': '🔥', 'category': '热搜榜单', 'description': '微博实时热搜'},
            {'path': '/api/hotlist/baiduRD', 'name': 'baidu', 'display_name': '百度热搜榜', 'icon': '🔍', 'category': '热搜榜单', 'description': '百度实时热搜'},
            {'path': '/api/hotlist/zhihuHot', 'name': 'zhihu', 'display_name': '知乎热榜', 'icon': '💡', 'category': '热搜榜单', 'description': '知乎热门问题'},
            {'path': '/api/hotlist/douyinHot', 'name': 'douyin', 'display_name': '抖音热搜榜', 'icon': '🎵', 'category': '热搜榜单', 'description': '抖音热门话题'},
            {'path': '/api/hotlist/biliHot', 'name': 'bili', 'display_name': 'B站热搜榜', 'icon': '📺', 'category': '热搜榜单', 'description': 'B站热门视频'},
        ]
    },
    
    # ==================== TenAPI ====================
    'tenapi.cn': {
        'name': 'TenAPI',
        'category': '综合资讯',
        'description': 'TenAPI免费接口',
        'docs': 'https://docs.tenapi.cn/',
        'endpoints': [
            {'path': '/v2/news60s', 'name': '60s', 'display_name': '每日60秒新闻', 'icon': '📰', 'category': '新闻资讯', 'description': '每日60秒新闻'},
            {'path': '/v2/bing', 'name': 'bing', 'display_name': '必应每日壁纸', 'icon': '🖼️', 'category': '图片壁纸', 'description': '必应每日壁纸'},
        ]
    },
    
    # ==================== 以下为待添加的项目模板 ====================
    # 添加新项目时，按以下格式添加：
    # 'domain.com': {
    #     'name': '项目名称',
    #     'category': '默认分类',
    #     'description': '项目描述',
    #     'docs': '文档地址',
    #     'endpoints': [
    #         {'path': '/api/xxx', 'name': 'xxx', 'display_name': '显示名称', 'icon': '📰', 'category': '分类', 'description': '描述'},
    #     ]
    # },
}

# 分类图标映射
CATEGORY_ICONS = {
    '新闻资讯': '📰',
    '热搜榜单': '🔥',
    '影视娱乐': '🎬',
    '音乐榜单': '🎵',
    '游戏资讯': '🎮',
    '生活服务': '🏠',
    '图片壁纸': '🖼️',
    '知识百科': '📚',
    '趣味内容': '😂',
    '开发工具': '🔧',
    '其他': '📌',
}

# ==================== 自定义解析函数 ====================
# 这些函数可以热更新，重载插件即可生效

def parse_60s_news(data: dict) -> dict:
    """解析60s新闻数据"""
    try:
        from astrbot.api import logger
    except ImportError:
        import logging
        logger = logging.getLogger(__name__)
    
    logger.debug(f"[parse_60s_news] 收到数据类型: {type(data)}")
    logger.debug(f"[parse_60s_news] 数据keys: {data.keys() if isinstance(data, dict) else 'N/A'}")
    
    # API返回格式: {"code": 200, "data": {"date": "...", "news": [...]}}
    # 需要从 data 字段中获取实际数据
    actual_data = data.get('data', data)  # 如果有 data 字段则使用，否则使用原数据
    
    news_list = actual_data.get('news', [])
    date = actual_data.get('date', '')
    
    # 兜底：检查空数据
    if not news_list:
        return {
            'title': '📰 每日60秒读懂世界',
            'content': '📭 暂无新闻数据，请稍后再试',
            'extra': {'date': date, 'count': 0}
        }
    
    # 格式化新闻列表
    content_lines = []
    for i, item in enumerate(news_list[:15], 1):
        # 跳过空内容
        if item and str(item).strip():
            content_lines.append(f"{i}. {item}")
    
    content = '\n'.join(content_lines) if content_lines else '📭 暂无有效新闻内容'
    
    return {
        'title': '📰 每日60秒读懂世界',
        'content': content,
        'extra': {'date': date, 'count': len(content_lines)}
    }

def parse_hotlist(data: dict, title_field: str = 'title', hot_field: str = 'hot') -> dict:
    """解析热榜数据（通用）"""
    items = data.get('data', data.get('list', []))
    if isinstance(items, dict):
        items = items.get('list', [])
    
    # 兜底：检查空数据
    if not items:
        return {
            'title': '',
            'content': '📭 暂无热榜数据，请稍后再试',
            'extra': {'count': 0}
        }
    
    content_lines = []
    index = 1
    for item in items[:15]:
        if isinstance(item, dict):
            title = item.get(title_field) or item.get('name') or ''
            # 跳过空标题
            if not title.strip():
                continue
            hot = item.get(hot_field) or item.get('hotValue') or ''
            if hot:
                content_lines.append(f"{index}. {title} 🔥{hot}")
            else:
                content_lines.append(f"{index}. {title}")
            index += 1
        elif isinstance(item, str) and item.strip():
            content_lines.append(f"{index}. {item}")
            index += 1
    
    return {
        'title': '',  # 使用配置的 display_name
        'content': '\n'.join(content_lines) if content_lines else '📭 暂无有效内容',
        'extra': {'count': len(content_lines)}
    }

def parse_weibo(data: dict) -> dict:
    """解析微博热搜"""
    return parse_hotlist(data, title_field='title', hot_field='hot')

def parse_zhihu(data: dict) -> dict:
    """解析知乎热榜"""
    return parse_hotlist(data, title_field='title', hot_field='hot')

def parse_bili(data: dict) -> dict:
    """解析B站热榜"""
    return parse_hotlist(data, title_field='title', hot_field='stat')

def parse_bing_wallpaper(data: dict) -> dict:
    """解析必应壁纸"""
    url = data.get('url') or ''
    title = data.get('title') or '必应每日壁纸'
    
    # 兜底：检查空URL
    if not url:
        return {
            'title': '🖼️ 必应每日壁纸',
            'content': '📭 暂无壁纸数据，请稍后再试',
            'url': '',
            'extra': {}
        }
    
    return {
        'title': title,
        'content': url,
        'url': url,
        'extra': data
    }

def parse_epic(data: dict) -> dict:
    """解析Epic免费游戏"""
    games = data.get('games', data.get('data', []))
    if not isinstance(games, list):
        games = [games] if games else []
    
    # 兜底：检查空数据
    if not games:
        return {
            'title': '🎮 Epic免费游戏',
            'content': '📭 暂无免费游戏信息',
            'extra': {'count': 0}
        }
    
    content_lines = []
    for game in games[:5]:
        if isinstance(game, dict):
            name = game.get('title') or game.get('name') or ''
            # 跳过空名称
            if not name.strip():
                continue
            end_date = game.get('endDate') or ''
            if end_date:
                content_lines.append(f"🎮 {name}\n   截止: {end_date}")
            else:
                content_lines.append(f"🎮 {name}")
        elif isinstance(game, str) and game.strip():
            content_lines.append(f"🎮 {game}")
    
    return {
        'title': '🎮 Epic免费游戏',
        'content': '\n'.join(content_lines) if content_lines else '📭 暂无有效游戏信息',
        'extra': {'count': len(content_lines)}
    }


# ==================== 预置API配置 ====================
# parser: 指定解析函数名（字符串），会动态调用上面定义的函数
# 修改解析函数后，重载插件即可生效

PRESETS = {
    '60s读懂世界': {
        'url': 'https://60s.viki.moe/v2/60s',
        'name': '60s',
        'display_name': '每日60秒读懂世界',
        'icon': '📰',
        'category': '新闻资讯',
        'description': '每天60秒读懂世界新闻',
        'parser': 'parse_60s_news',  # 指定解析函数
    },
    '微博热搜': {
        'url': 'https://60s.viki.moe/v2/weibo',
        'name': 'weibo',
        'display_name': '微博热搜',
        'icon': '🔥',
        'category': '热搜榜单',
        'description': '微博实时热搜榜',
        'parser': 'parse_weibo',
    },
    '知乎热榜': {
        'url': 'https://60s.viki.moe/v2/zhihu',
        'name': 'zhihu',
        'display_name': '知乎热榜',
        'icon': '💡',
        'category': '热搜榜单',
        'description': '知乎热门问题',
        'parser': 'parse_zhihu',
    },
    'B站热榜': {
        'url': 'https://60s.viki.moe/v2/bili',
        'name': 'bili',
        'display_name': 'B站热榜',
        'icon': '📺',
        'category': '热搜榜单',
        'description': 'B站热门视频',
        'parser': 'parse_bili',
    },
    '必应壁纸': {
        'url': 'https://60s.viki.moe/v2/bing',
        'name': 'bing',
        'display_name': '必应每日壁纸',
        'icon': '🖼️',
        'category': '图片壁纸',
        'description': '必应每日精选壁纸',
        'parser': 'parse_bing_wallpaper',
    },
    'Epic免费游戏': {
        'url': 'https://60s.viki.moe/v2/epic',
        'name': 'epic',
        'display_name': 'Epic免费游戏',
        'icon': '🎮',
        'category': '游戏资讯',
        'description': 'Epic商城免费游戏',
        'parser': 'parse_epic',
    },
}


def get_known_project(domain: str) -> dict:
    """
    根据域名获取已知项目配置
    
    Args:
        domain: 域名（如 60s.viki.moe）
    
    Returns:
        项目配置字典，未找到返回 None
    """
    domain = domain.lower()
    for known_domain, project in KNOWN_PROJECTS.items():
        if known_domain in domain:
            return project
    return None


def get_preset(name: str) -> dict:
    """
    获取预置API配置
    
    Args:
        name: 预置名称
    
    Returns:
        预置配置字典，未找到返回 None
    """
    return PRESETS.get(name)


def list_presets() -> list:
    """列出所有预置API名称"""
    return list(PRESETS.keys())


def get_category_icon(category: str) -> str:
    """获取分类图标"""
    return CATEGORY_ICONS.get(category, '📌')
