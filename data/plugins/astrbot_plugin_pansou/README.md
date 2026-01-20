# 资源搜索插件 (Pansou Plugin)

## 功能介绍

资源搜索插件支持多平台网盘资源搜索，基于 [pansou](https://github.com/fish2018/pansou) 项目提供的API。

### 主要特性

- 🔍 **多平台搜索** - 支持百度网盘、阿里云盘、夸克网盘等多个网盘平台
- 📱 **平台适配** - 自动适配按钮模式（Telegram/飞书）和会话模式（QQ/微信）
- 🎯 **智能筛选** - 支持按网盘类型筛选搜索结果
- 📄 **分页浏览** - 支持翻页查看更多结果
- 💬 **会话交互** - 会话模式下支持文本命令导航
- ⚡ **限流保护** - 内置限流和配额管理

## 使用方法

### 基本搜索

```
/搜 关键词
```

示例：
```
/搜 宇宙
/搜 Python教程
```

### 指定网盘类型

```
/搜 关键词 网盘类型
```

示例：
```
/搜 宇宙 百度
/搜 Python教程 阿里
/搜 电影 夸克
```

支持的网盘类型：
- 百度 (baidu)
- 阿里 (aliyun)
- 夸克 (quark)
- 天翼 (tianyi)
- 115 (115)
- PikPak (pikpak)
- 迅雷 (xunlei)
- 磁力 (magnet)

## 平台差异

### 按钮模式（Telegram/飞书）

- ✅ 序号按钮快速选择
- ✅ 翻页按钮
- ✅ 筛选按钮（可视化选择网盘类型）
- ✅ 返回按钮
- ❌ 不显示文本导航提示

### 会话模式（QQ/微信）

- ✅ 输入序号查看详情
- ✅ 文本命令导航（p-上页、n-下页、h-首页、0-退出）
- ✅ 筛选提示（f-筛选）
- ✅ 会话超时提示
- ❌ 无按钮界面

## 会话模式命令

在会话模式下，可以使用以下命令：

| 命令 | 说明 |
|------|------|
| `1-15` | 输入序号查看对应资源详情 |
| `p` / `上页` | 查看上一页 |
| `n` / `下页` | 查看下一页 |
| `h` / `首页` | 返回第一页 |
| `f` / `筛选` | 查看筛选说明 |
| `b` / `返回` | 返回列表（详情页） |
| `0` / `退出` | 退出会话 |

## 插件架构

```
astrbot_plugin_pansou/
├── handlers/
│   ├── __init__.py
│   ├── pansou_api.py          # API处理器
│   ├── formatter.py            # 格式化器
│   ├── session_handler.py      # 会话处理器
│   └── response_builder.py     # 响应构建器
├── main.py                     # 主插件文件
├── metadata.yaml               # 插件元数据
└── README.md                   # 说明文档
```

### 模块说明

#### PansouAPI (`handlers/pansou_api.py`)
- 负责与盘搜后端API交互
- 处理搜索请求和结果解析
- 支持merge、results、all三种结果类型

#### PansouFormatter (`handlers/formatter.py`)
- 格式化搜索结果列表
- 格式化资源详情
- 自动适配按钮模式和会话模式的显示

#### SessionHandler (`handlers/session_handler.py`)
- 处理会话模式下的用户交互
- 管理翻页、筛选等操作
- 集成NavigationHandler处理标准导航命令

#### PansouResponseBuilder (`handlers/response_builder.py`)
- 构建搜索结果键盘
- 构建筛选键盘
- 构建详情页键盘
- 自动适配飞书JSON格式和Telegram传统格式

## 依赖模块

插件依赖以下通用模块（位于 `common/` 目录）：

- `platform_capabilities` - 平台能力检测
- `session_manager` - 会话管理
- `navigation_handler` - 导航处理
- `navigation_hint` - 导航提示生成
- `rate_limiter` - 限流控制
- `quota_validator` - 配额验证
- `loading_indicator` - 加载提示
- `message_editor` - 消息编辑

## 配置说明

### API配置

默认API地址：`http://43.129.194.21:19005`

如需修改，请在 `handlers/pansou_api.py` 中修改 `api_base_url` 参数。

### 限流配置

默认限流：10次/分钟

如需修改，请在 `main.py` 中修改 `RateLimiter` 初始化参数。

### 会话超时

默认超时：1分钟

如需修改，请在 `main.py` 和 `handlers/session_handler.py` 中修改 `SESSION_TIMEOUT_MINUTES`。

## 最佳实践

本插件参考豆瓣插件的最佳实践：

1. **模块化设计** - 清晰的模块职责划分
2. **平台适配** - 自动适配不同平台的能力
3. **会话管理** - 统一的会话生命周期管理
4. **导航系统** - 标准化的导航命令和提示
5. **错误处理** - 完善的异常捕获和用户提示
6. **日志记录** - 详细的操作日志便于调试

## 开发说明

### 添加新的网盘类型

在 `handlers/pansou_api.py` 中的 `get_cloud_type_name` 和 `get_cloud_type_emoji` 方法中添加新的映射。

### 自定义格式化

修改 `handlers/formatter.py` 中的格式化方法。

### 扩展功能

参考豆瓣插件的实现方式，可以添加：
- 收藏功能
- 历史记录
- 高级筛选
- 资源评分

## 许可证

MIT License

## 作者

AstrBot Team

## 相关链接

- [盘搜项目](https://github.com/fish2018/pansou)
- [AstrBot](https://github.com/Soulter/AstrBot)
