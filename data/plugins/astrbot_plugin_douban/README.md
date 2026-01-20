# 豆瓣评分插件

## 功能介绍

这是一个为 AstrBot 开发的豆瓣评分图片显示插件，能够自动识别用户发送的豆瓣链接，并生成包含评分信息和用户评论的图片。

## 支持的链接格式

### 桌面版链接
- 电影链接：`https://movie.douban.com/subject/36208369/`
- 电影链接（带参数）：`https://movie.douban.com/subject/36208369/?icn=index-latestbook-subject`
- 图书链接：`https://book.douban.com/subject/37375410/`
- 图书链接（带参数）：`https://book.douban.com/subject/37375410/?icn=index-latestbook-subject`

### 移动版链接
- 移动版电影：`https://m.douban.com/movie/subject/36455616/`
- 移动版图书：`https://m.douban.com/book/subject/37353424/?source=collection`
- 移动版电视：`https://m.douban.com/tv/subject/36455616/`

### App调度链接
- App电影链接：`https://www.douban.com/doubanapp/dispatch/movie/36402017`
- App图书链接：`https://www.douban.com/doubanapp/dispatch/book/37353424`

## 功能特性

1. **自动链接识别**：当用户发送豆瓣链接时，插件会自动识别并处理
2. **评分图片生成**：调用第三方API生成豆瓣评分图片
3. **热门评论获取**：获取最热门的4条用户评论
4. **智能文本处理**：自动限制评论长度，避免消息过长
5. **操作按钮**：提供"搜索资源"和"查看详情"按钮

## 使用方法

1. 直接发送豆瓣电影或图书的链接到聊天中
2. 插件会自动识别并处理，返回：
   - 豆瓣评分图片（如果API可用）
   - 热门用户评论
   - 操作按钮（搜索资源、查看详情）

## 技术实现

- **URL解析**：使用正则表达式提取豆瓣类型和ID
- **图片API**：`https://api.wowoziyuan.com/douban/index.php`
- **评论API**：`https://m.douban.com/rexxar/api/v2`
- **异步处理**：并行获取图片和评论数据，提高响应速度
- **错误处理**：完善的异常处理机制

## 配置文件

插件支持通过 `config.yaml` 文件进行配置：

- API地址配置
- 评论数量和字符限制
- 请求超时设置
- 用户代理配置

## 版本信息

- 版本：1.0.0
- 作者：Chrismk
- 适用于：AstrBot v4.x

## 注意事项

1. 依赖第三方API服务，可能存在服务不稳定的情况
2. 评论内容来自豆瓣用户，插件不对内容负责
3. 请遵守豆瓣网站的使用条款和API调用限制
