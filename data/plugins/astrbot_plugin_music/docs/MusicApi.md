---

# 🎵 Music API Server — 多源聚合音乐 API 服务

> 一个功能强大的私有化音乐 API 服务器，集成本地音乐库、QQ音乐、网易云音乐和酷我音乐四大平台。提供智能搜索、自动下载、批量入库、元数据管理、Cookie 自动续期等企业级特性，为音乐播放器、个人音乐库管理系统提供统一、标准化的数据接口。

---

## ✨ 核心特性

### 🎯 多平台支持
- **四源聚合架构**  
  统一接入本地音乐库、QQ音乐、网易云音乐、酷我音乐，一个接口访问所有平台。

- **智能音质选择**  
  自动识别并下载最高可用音质（支持 Master、无损FLAC、320K、128K等多种音质）。

### 🔍 智能搜索与匹配
- **标准化搜索格式**  
  支持 `歌手 - 歌曲名` 统一搜索格式，可选专辑名精确过滤。

- **模糊专辑匹配**  
  智能识别不同版本专辑名称（如"十一月的肖邦"与"11月的肖邦"），自动标准化匹配。

### 📥 自动化下载与管理
- **智能增量下载**  
  - 自动检测本地已有音质，避免重复下载
  - 支持音质升级策略（从低音质自动补充高音质）
  - 已有 Master 版本时自动跳过下载

- **批量下载支持**  
  - 支持整张专辑批量下载（网易云、QQ音乐）
  - 支持歌单批量下载（网易云、QQ音乐）
  - 后台异步下载，不阻塞 API 响应

- **完整元数据嵌入** ⭐ 增强  
  自动写入歌曲标题、艺术家、专辑、专辑艺术家、发行日期、音轨号、碟片号、发行商、作词、作曲、编曲、BPM、流派、封面图片、歌词（含翻译）等 15+ 项元数据。
  
- **平台溯源信息** ⭐ 新增  
  每个下载的文件自动嵌入音乐平台标识和歌曲ID，支持反查原始音源，方便后续更新和管理。

### 🗄️ 本地音乐库管理
- **SQLite 数据库索引**  
  高效管理本地音乐文件，支持按歌手、歌名、专辑、音质快速检索。

- **自动扫描与入库**  
  通过 `scanner.py` 自动扫描音乐目录，提取元数据并建立索引。

- **音质向下兼容**  
  查询时自动降级查找（master → flac → 320 → 128），提升匹配成功率。

### 🔐 安全与稳定
- **API 密钥认证**  
  所有接口通过 `X-API-Key` 请求头认证，保障私有部署安全。

- **Cookie 自动续期**  
  内置 APScheduler 定时任务，每 23 小时自动刷新 QQ 音乐 Cookie，无需手动维护。

- **历史记录自动清理**  
  每 24 小时自动清理 30 天前的历史数据，保持数据库性能和存储空间。

- **健康检查机制**  
  Docker 容器内置健康检查，自动监控服务运行状态。

### 📊 监控与统计 ⭐ 新功能
- **状态监控 API**  
  实时查看服务状态、平台账号状态、数据库健康度等信息，支持集成到监控系统。

- **历史记录追踪**  
  自动记录搜索历史、点击记录、下载记录，便于分析使用情况。最多保留 30 天数据，自动清理。

- **统计分析功能**  
  提供搜索次数、下载统计、热门关键词、热门歌曲等多维度数据分析。

### 🐳 生产级部署
- **Docker 一键部署**  
  提供完整的 Docker 和 Docker Compose 配置，开箱即用。

- **数据持久化**  
  音乐文件、数据库文件通过 Volume 挂载，数据安全可靠。

- **日志与错误追踪**  
  自动记录下载失败日志（`download_errors_qq.log`），便于问题排查。

---

## 📊 项目概览

### 支持的音乐平台

| 平台 | 搜索 | 单曲获取 | 批量下载 | 元数据嵌入 | 音质支持 |
|------|------|---------|---------|-----------|----------|
| **本地音乐库** | ✅ | ✅ | - | ✅ | Master/FLAC/320K/128K |
| **网易云音乐** | ✅ | ✅ | ✅（歌单/专辑） | ✅ | HiRes/FLAC/320K/128K |
| **QQ 音乐** | ✅ | ✅ | ✅（歌单/专辑） | ✅ | Master/FLAC/320K/128K |
| **酷我音乐** | ✅ | ✅ | ❌ | ❌ | 在线播放 |

### 功能矩阵

| 功能类别 | 具体功能 | 实现状态 |
|---------|---------|---------|
| **🔍 搜索与查询** | 统一搜索格式（`歌手 - 歌曲名`） | ✅ |
| | 专辑名精确过滤 | ✅ |
| | 模糊专辑匹配（简繁体） | ✅ |
| | 音质向下兼容查询 | ✅ |
| **📥 下载管理** | 智能增量下载 | ✅ |
| | 批量歌单下载 | ✅ |
| | 批量专辑下载 | ✅ |
| | 后台异步下载 | ✅ |
| | 下载重试机制 | ✅ |
| | 失败日志记录 | ✅ |
| **🎵 元数据管理** | 歌曲信息（15+字段） | ✅ |
| | 专辑封面嵌入 | ✅ |
| | 歌词嵌入（含翻译） | ✅ |
| | 作词/作曲/编曲 | ✅ |
| | BPM/流派/发行商 | ✅ |
| **🗄️ 数据库管理** | SQLite 索引 | ✅ |
| | 自动扫描入库 | ✅ |
| | 多音质版本管理 | ✅ |
| | 专辑标准化匹配 | ✅ |
| **🔐 安全与维护** | API 密钥认证 | ✅ |
| | Cookie 自动续期 | ✅ |
| | 健康检查 | ✅ |
| | Docker 部署 | ✅ |

### 性能指标

- **并发处理**：支持多线程异步下载
- **响应速度**：单曲查询 < 2 秒（含在线 API 调用）
- **批量下载**：立即返回 202 Accepted，后台处理
- **数据库查询**：SQLite 索引优化，毫秒级响应
- **下载重试**：最多 3 次重试，间隔 5 秒
- **Cookie 刷新**：每 23 小时自动执行

---

## 🚀 快速开始

### 方式一：使用 Docker（推荐）🐳

#### 1. 克隆项目

```bash
git clone https://github.com/mkr-0920/music-api-server.git
cd music-api-server
```

#### 2. 配置环境

```bash
# 复制配置模板
cp core/config.py.template core/config.py

# 编辑配置文件
nano core/config.py
```

请务必填写以下关键配置项：

| 配置项             | 说明                         |
|--------------------|------------------------------|
| `API_SECRET_KEY`   | 用于 API 认证的密钥           |
| `QQ_USER_CONFIG`  | QQ音乐相关配置 |
| `NETEASE_COOKIE_STR`   | 网易云音乐 Cookies     |
| `MUSIC_DIRECTORY`  | 本地音乐文件存储路径（Docker 中为 `/app/music`）|

> ⚠️ **Docker 用户注意**: 在配置文件中，将 `MUSIC_DIRECTORY` 设置为 `/app/music`，将 `DATABASE_FILE` 设置为 `/app/data/music_library.db`

#### 3. 启动 Docker 容器

```bash
# 方式 A：使用 docker-compose（推荐）
cd docker
docker-compose up -d

# 方式 B：使用 docker 命令（在项目根目录执行）
docker build -f docker/Dockerfile -t music-api-server .
docker run -d \
  --name music-api-server \
  -p 5000:5000 \
  -v $(pwd)/music:/app/music \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/core/config.py:/app/core/config.py \
  music-api-server
```

#### 4. 初始化数据库（可选）

**注意**：`music_library.db` 数据库会在服务启动时自动创建空表结构。如果您有本地音乐文件需要索引，请运行扫描器：

```bash
# docker-compose 方式
docker exec -it music-api python scanner.py

# docker 方式
docker exec -it music-api-server python scanner.py
```

扫描器会：
- ✅ 扫描您的音乐目录（`/app/music`）
- ✅ 提取所有音频文件的元数据
- ✅ 建立歌曲索引到数据库

**如果没有本地音乐文件**，可以跳过此步骤，直接使用在线平台（网易云、QQ音乐、酷我）。

#### 5. 查看日志

```bash
# docker-compose（在 docker 目录下执行）
cd docker
docker-compose logs -f

# docker
docker logs -f music-api-server
```

#### 6. 停止服务

```bash
# docker-compose（在 docker 目录下执行）
cd docker
docker-compose down

# docker
docker stop music-api-server
docker rm music-api-server
```

✅ 服务启动后，默认监听地址：  
👉 `http://localhost:5000`

---

### 方式二：本地部署

#### 1. 克隆项目

```bash
git clone https://github.com/mkr-0920/music-api-server.git
cd music-api-server
```

#### 2. 配置环境

```bash
cp core/config.py.template core/config.py
nano core/config.py
```

请务必填写以下关键配置项：

| 配置项             | 说明                         |
|--------------------|------------------------------|
| `API_SECRET_KEY`   | 用于 API 认证的密钥           |
| `QQ_USER_CONFIG`  | QQ音乐相关配置 |
| `NETEASE_COOKIE_STR`   | 网易云音乐 Cookies     |
| `MUSIC_DIRECTORY`  | 本地音乐文件存储路径          |

> 💡 建议使用虚拟环境隔离依赖

#### 3. 安装依赖（推荐虚拟环境）

```bash
# 创建并激活虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

#### 4. 初始化数据库（可选）

**注意**：`music_library.db` 数据库会在服务启动时自动创建空表结构。如果您有本地音乐文件需要索引，请运行扫描器：

```bash
python scanner.py
```

扫描器会：
- ✅ 扫描您配置的音乐目录
- ✅ 提取所有音频文件的元数据（歌名、艺术家、专辑、时长、音质等）
- ✅ 建立歌曲索引到数据库

**输出示例**：
```
本地音乐数据库初始化成功: music_library.db
正在扫描音乐文件夹: /path/to/music
扫描完成！本次新增了 156 首歌曲。
```

**如果没有本地音乐文件**，可以跳过此步骤，直接使用在线平台（网易云、QQ音乐、酷我）。

#### 5. 启动服务

```bash
python main.py
```

✅ 服务启动后，默认监听地址：  
👉 `http://0.0.0.0:5000`

**启动日志示例**：
```
本地音乐数据库初始化成功: music_library.db
qq音乐cookies定时刷新启动
历史记录自动清理启动（每24小时清理30天前的数据）
服务器启动于 http://0.0.0.0:5000
```

---

## 📖 API 使用说明

所有请求 **必须携带认证头**：

```http
X-API-Key: YOUR_SECRET_KEY
```

---

## 🔍 搜索功能

### 两阶段搜索模式

本项目提供**两阶段搜索模式**，让您可以先浏览搜索结果，再精确获取歌曲详情：

```
第一阶段：模糊搜索 → 浏览列表 → 翻页查看
第二阶段：选择歌曲 → 精确获取 → 自动下载
```

---

### 统一搜索接口 `/api/search` ⭐ 新功能

**方法**：`GET`  
**描述**：多平台统一搜索接口，支持分页、多种搜索类型、结果缓存。

#### 参数：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `platform` | String | ❌ | `netease` | 平台标识：`netease`（网易云）、`qq`（QQ音乐）、`kuwo`（酷我）、`all`（聚合搜索） |
| `keyword` | String | ✅ | - | 搜索关键词（支持模糊搜索） |
| `page` | Integer | ❌ | 1 | 页码（从 1 开始，最大 100） |
| `limit` | Integer | ❌ | 20 | 每页数量（最大 20） |
| `type` | String | ❌ | `song` | 搜索类型：`song`（歌曲）、`album`（专辑）、`artist`（艺术家） |

#### 特性：

- ✅ **轻量级搜索**：只返回列表，不触发下载
- ✅ **支持翻页**：浏览大量搜索结果
- ✅ **智能缓存**：10 分钟缓存，减少 API 调用
- ✅ **聚合搜索**：`platform=all` 同时搜索所有平台
- ✅ **多种类型**：支持歌曲、专辑、艺术家搜索

> **关于酷我音乐搜索结果的说明**：  
> 当使用 `platform=kuwo` 进行搜索时，返回的列表中 `cover_url` 和 `publish_time` 字段会是 `null`。这是因为酷我的搜索专用接口不提供这些信息。当您根据搜索结果的 `id` 去请求单曲详情接口时（如 `/api/kuwo?id=...`），才会返回包含封面图的完整数据。

#### 返回数据结构：

```json
{
  "code": 200,
  "message": "成功",
  "data": {
    "platform": "netease",
    "keyword": "周杰伦",
    "search_type": "song",
    "items": [
      {
        "index": 1,
        "platform": "netease",
        "id": "191179",
        "name": "稻香",
        "artist": "周杰伦",
        "album": "魔杰座",
        "duration": 223000,
        "cover_url": "https://...",
        "publish_time": 1223568000000
      },
      {
        "index": 2,
        "platform": "netease",
        "id": "191180",
        "name": "青花瓷",
        "artist": "周杰伦",
        "album": "我很忙",
        "duration": 238000,
        "cover_url": "https://...",
        "publish_time": 1193932800000
      }
      // ... 更多结果
    ],
    "pagination": {
      "current_page": 1,
      "page_size": 20,
      "total_items": 256,
      "total_pages": 13,
      "has_next": true,
      "has_prev": false,
      "next_page": 2,
      "prev_page": null
    }
  }
}
```

#### 使用示例：

##### 1. 搜索歌曲（默认网易云）

```bash
curl -G -H "X-API-Key: YOUR_SECRET_KEY" \
  --data-urlencode "keyword=周杰伦 稻香" \
  --data-urlencode "page=1" \
  --data-urlencode "limit=20" \
  "http://127.0.0.1:5000/api/search"
```

##### 2. 搜索 QQ 音乐专辑

```bash
curl -G -H "X-API-Key: YOUR_SECRET_KEY" \
  --data-urlencode "platform=qq" \
  --data-urlencode "keyword=魔杰座" \
  --data-urlencode "type=album" \
  --data-urlencode "page=1" \
  "http://127.0.0.1:5000/api/search"
```

##### 3. 聚合搜索所有平台

```bash
curl -G -H "X-API-Key: YOUR_SECRET_KEY" \
  --data-urlencode "platform=all" \
  --data-urlencode "keyword=周杰伦" \
  --data-urlencode "type=song" \
  "http://127.0.0.1:5000/api/search"
```

##### 4. 搜索艺术家

```bash
curl -G -H "X-API-Key: YOUR_SECRET_KEY" \
  --data-urlencode "platform=netease" \
  --data-urlencode "keyword=周杰伦" \
  --data-urlencode "type=artist" \
  "http://127.0.0.1:5000/api/search"
```

##### 5. 翻页查看第 2 页

```bash
curl -G -H "X-API-Key: YOUR_SECRET_KEY" \
  --data-urlencode "keyword=周杰伦" \
  --data-urlencode "page=2" \
  "http://127.0.0.1:5000/api/search"
```

---

### 完整工作流程示例

#### JavaScript 示例（两阶段搜索）

```javascript
const API_KEY = "YOUR_SECRET_KEY";
const BASE_URL = "http://localhost:5000";

// ============ 第一阶段：搜索浏览 ============
async function searchSongs(keyword, page = 1) {
  const params = new URLSearchParams({
    platform: 'netease',
    keyword: keyword,
    page: page,
    limit: 20,
    type: 'song'
  });
  
  const response = await fetch(`${BASE_URL}/api/search?${params}`, {
    headers: { 'X-API-Key': API_KEY }
  });
  
  const result = await response.json();
  
  if (result.code === 200) {
    const data = result.data;
    
    // 显示搜索结果列表
    console.log(`搜索 "${data.keyword}" - 找到 ${data.pagination.total_items} 个结果\n`);
    
    data.items.forEach(item => {
      console.log(`[${item.index}] ${item.name} - ${item.artist} (${item.album})`);
    });
    
    // 显示分页信息
    console.log(`\n第 ${data.pagination.current_page}/${data.pagination.total_pages} 页`);
    
    return data;
  }
}

// ============ 第二阶段：精确获取 ============
async function getSongDetails(platform, songId, level = 'hires') {
  const params = new URLSearchParams({
    id: songId,
    level: level
  });
  
  const response = await fetch(`${BASE_URL}/api/${platform}?${params}`, {
    headers: { 'X-API-Key': API_KEY }
  });
  
  const result = await response.json();
  
  if (result.code === 200) {
    const song = result.data;
    
    // 播放歌曲
    console.log(`\n正在播放: ${song.name} - ${song.artist}`);
    console.log(`播放链接: ${song.url}`);
    console.log(`文件大小: ${song.size}`);
    console.log(`音质: ${song.quality_actual}`);
    
    // 实际应用中，这里会调用音频播放器
    // audioPlayer.src = song.url;
    // audioPlayer.play();
    
    return song;
  }
}

// ============ 完整使用流程 ============
async function main() {
  // 1. 搜索 "周杰伦 稻香"
  const searchResult = await searchSongs("周杰伦 稻香", 1);
  
  // 2. 用户选择第 1 首歌曲
  if (searchResult.items.length > 0) {
    const selectedSong = searchResult.items[0];
    
    // 3. 获取完整歌曲信息并播放
    await getSongDetails(
      selectedSong.platform,  // 'netease'
      selectedSong.id,        // '191179'
      'hires'
    );
  }
  
  // 4. 如果需要翻页
  // const page2 = await searchSongs("周杰伦", 2);
}

// 运行
main();
```

#### Python 示例

```python
import requests

API_KEY = "YOUR_SECRET_KEY"
BASE_URL = "http://localhost:5000"

def search_songs(keyword, page=1, platform="netease"):
    """第一阶段：搜索浏览"""
    params = {
        "platform": platform,
        "keyword": keyword,
        "page": page,
        "limit": 20,
        "type": "song"
    }
    
    response = requests.get(
        f"{BASE_URL}/api/search",
        params=params,
        headers={"X-API-Key": API_KEY}
    )
    
    result = response.json()
    
    if result["code"] == 200:
        data = result["data"]
        
        # 显示搜索结果
        print(f"搜索 \"{data['keyword']}\" - 找到 {data['pagination']['total_items']} 个结果\n")
        
        for item in data["items"]:
            print(f"[{item['index']}] {item['name']} - {item['artist']} ({item['album']})")
        
        print(f"\n第 {data['pagination']['current_page']}/{data['pagination']['total_pages']} 页")
        
        return data
    
    return None

def get_song_details(platform, song_id, level="hires"):
    """第二阶段：精确获取"""
    params = {
        "id": song_id,
        "level": level
    }
    
    response = requests.get(
        f"{BASE_URL}/api/{platform}",
        params=params,
        headers={"X-API-Key": API_KEY}
    )
    
    result = response.json()
    
    if result["code"] == 200:
        song = result["data"]
        
        print(f"\n正在播放: {song['name']} - {song['artist']}")
        print(f"播放链接: {song['url']}")
        print(f"文件大小: {song['size']}")
        print(f"音质: {song['quality_actual']}")
        
        return song
    
    return None

# 使用示例
if __name__ == "__main__":
    # 1. 搜索
    search_result = search_songs("周杰伦 稻香", page=1)
    
    # 2. 选择第 1 首
    if search_result and search_result["items"]:
        selected = search_result["items"][0]
        
        # 3. 获取详情并播放
        song_details = get_song_details(
            selected["platform"],
            selected["id"]
        )
```

---

### 状态监控接口 `/api/status` ⭐ 新功能

**方法**：`GET`  
**描述**：获取 API 服务状态、各平台账号状态、数据库状态等信息，方便运维监控。

#### 参数：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `detail` | String | ❌ | `full` | 详细程度：`full`（完整信息）、`simple`（简要信息） |

#### 返回数据结构（完整模式）：

```json
{
  "code": 200,
  "message": "状态检查完成",
  "overall_status": "healthy",
  "data": {
    "service": {
      "status": "running",
      "uptime_seconds": 3600,
      "uptime_readable": "1小时",
      "start_time": "2025-10-02T10:00:00",
      "current_time": "2025-10-02T11:00:00"
    },
    "platforms": {
      "netease": {
        "name": "网易云音乐",
        "status": "online",
        "has_cookie": true,
        "cookie_valid": true,
        "cookie_info": {
          "MUSIC_U": "已配置",
          "cookie_count": 3
        },
        "message": "Cookie 有效，可正常使用"
      },
      "qq": {
        "name": "QQ 音乐",
        "status": "online",
        "has_config": true,
        "config_valid": true,
        "config_info": {
          "uin": "12345***",
          "qqmusic_key": "已配置",
          "refresh_token": "已配置"
        },
        "message": "配置有效，可正常使用"
      },
      "kuwo": {
        "name": "酷我音乐",
        "status": "online",
        "requires_auth": false,
        "api_available": true,
        "message": "API 可用"
      }
    },
    "database": {
      "status": "online",
      "exists": true,
      "path": "/app/data/music_library.db",
      "size_bytes": 524288,
      "size_readable": "512.00 KB",
      "statistics": {
        "total_songs": 1234,
        "by_quality": {
          "master": 45,
          "flac": 567,
          "320": 456,
          "128": 166
        }
      },
      "message": "数据库正常"
    },
    "cache": {
      "status": "active",
      "statistics": {
        "total_entries": 10,
        "valid_entries": 8,
        "expired_entries": 2
      },
      "message": "缓存正常运行"
    },
    "system": {
      "python_version": "3.11.0",
      "platform": "Linux-5.10.0-amd64",
      "architecture": "x86_64",
      "api_version": "2.0.0",
      "features": {
        "search": true,
        "download": true,
        "cache": true,
        "pagination": true,
        "multi_platform": true
      }
    }
  }
}
```

#### 返回数据结构（简要模式）：

```json
{
  "code": 200,
  "message": "状态检查完成",
  "overall_status": "healthy",
  "data": {
    "service_status": "running",
    "uptime": "1小时 30分钟",
    "platforms": {
      "netease": "online",
      "qq": "online",
      "kuwo": "online"
    },
    "database_status": "online"
  }
}
```

#### 状态说明：

**overall_status（总体状态）**
- `healthy`：所有服务正常
- `warning`：部分服务有警告
- `degraded`：部分服务不可用
- `error`：系统错误

**平台状态**
- `online`：正常运行
- `warning`：可能存在问题
- `offline`：未配置或离线
- `error`：发生错误

**数据库状态**
- `online`：正常
- `offline`：不可用
- `error`：错误

#### 使用示例：

##### 1. 获取完整状态信息

```bash
curl -H "X-API-Key: YOUR_SECRET_KEY" \
  "http://127.0.0.1:5000/api/status"
```

##### 2. 获取简要状态信息

```bash
curl -H "X-API-Key: YOUR_SECRET_KEY" \
  "http://127.0.0.1:5000/api/status?detail=simple"
```

##### 3. 定时监控脚本（Bash）

```bash
#!/bin/bash
# 每5分钟检查一次服务状态

API_KEY="YOUR_SECRET_KEY"
API_URL="http://127.0.0.1:5000/api/status?detail=simple"

while true; do
  RESPONSE=$(curl -s -H "X-API-Key: $API_KEY" "$API_URL")
  STATUS=$(echo $RESPONSE | jq -r '.overall_status')
  
  echo "[$(date)] 服务状态: $STATUS"
  
  if [ "$STATUS" != "healthy" ]; then
    echo "警告：服务状态异常！"
    echo $RESPONSE | jq '.'
    # 可以在这里添加告警通知（邮件、webhook等）
  fi
  
  sleep 300  # 5分钟
done
```

##### 4. Python 监控脚本

```python
import requests
import time
from datetime import datetime

API_KEY = "YOUR_SECRET_KEY"
API_URL = "http://127.0.0.1:5000/api/status"

def check_status():
    """检查服务状态"""
    try:
        response = requests.get(
            API_URL,
            headers={"X-API-Key": API_KEY},
            params={"detail": "simple"}
        )
        
        result = response.json()
        overall_status = result.get("overall_status", "unknown")
        
        print(f"[{datetime.now()}] 服务状态: {overall_status}")
        
        if overall_status != "healthy":
            print("⚠️ 警告：服务状态异常！")
            print(f"详细信息：{result}")
            # 可以在这里添加告警通知
            send_alert(result)
        
        return result
    
    except Exception as e:
        print(f"❌ 状态检查失败: {e}")
        return None

def send_alert(status_info):
    """发送告警通知"""
    # 这里可以集成邮件、Slack、钉钉等告警方式
    pass

# 定时监控
if __name__ == "__main__":
    while True:
        check_status()
        time.sleep(300)  # 5分钟检查一次
```

---

### 历史记录与统计接口 `/api/history` ⭐ 新功能

**方法**：`GET`  
**描述**：查询最近的搜索记录、点击记录、下载记录和统计信息，方便了解项目使用情况。

#### 参数：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `type` | String | ❌ | `search` | 历史类型：`search`（搜索历史）、`clicks`（点击历史）、`downloads`（下载历史）、`statistics`（统计信息） |
| `limit` | Integer | ❌ | `50` | 返回记录数量（最多100条） |
| `hours` | Integer | ❌ | 不限 | 时间范围（小时），例如 `24` 表示最近24小时 |
| `stat_hours` | Integer | ❌ | `24` | 统计时间范围（仅 `statistics` 类型有效，最多720小时） |

#### 返回数据结构：

##### 1. 搜索历史 (`type=search`)

```json
{
  "code": 200,
  "message": "成功",
  "data": {
    "type": "search_history",
    "count": 15,
    "records": [
      {
        "keyword": "周杰伦 稻香",
        "platform": "netease",
        "search_type": "song",
        "timestamp": 1696234567,
        "created_at": "2024-10-02T14:30:00"
      }
    ]
  }
}
```

##### 2. 点击历史 (`type=clicks`)

```json
{
  "code": 200,
  "message": "成功",
  "data": {
    "type": "click_history",
    "count": 12,
    "records": [
      {
        "platform": "netease",
        "song_id": "1901371647",
        "song_name": "稻香",
        "artist": "周杰伦",
        "album": "魔杰座",
        "timestamp": 1696234580,
        "created_at": "2024-10-02T14:30:15"
      }
    ]
  }
}
```

##### 3. 下载历史 (`type=downloads`)

```json
{
  "code": 200,
  "message": "成功",
  "data": {
    "type": "download_history",
    "count": 8,
    "records": [
      {
        "platform": "netease",
        "song_id": "1901371647",
        "song_name": "稻香",
        "artist": "周杰伦",
        "album": "魔杰座",
        "quality": "flac",
        "file_path": "/music/周杰伦 - 稻香 魔杰座.flac",
        "file_size": 35678912,
        "file_size_readable": "34.02 MB",
        "timestamp": 1696234600,
        "created_at": "2024-10-02T14:30:30",
        "status": "success"
      }
    ]
  }
}
```

##### 4. 统计信息 (`type=statistics`)

```json
{
  "code": 200,
  "message": "成功",
  "data": {
    "type": "statistics",
    "statistics": {
      "time_range_hours": 24,
      "search": {
        "total_count": 156,
        "by_platform": {"netease": 85, "qq": 45, "all": 26},
        "top_keywords": [
          {"keyword": "周杰伦", "count": 23}
        ]
      },
      "clicks": {
        "total_count": 89,
        "top_songs": [
          {"song_name": "稻香", "artist": "周杰伦", "count": 12}
        ]
      },
      "downloads": {
        "total_count": 67,
        "by_platform": {"netease": 38, "qq": 29},
        "by_quality": {"flac": 25, "320": 30, "master": 12},
        "top_songs": [
          {"song_name": "稻香", "artist": "周杰伦", "count": 8}
        ],
        "total_size_bytes": 2458963456,
        "total_size_readable": "2.29 GB"
      }
    }
  }
}
```

#### 使用示例：

```bash
# 查询最近搜索历史
curl -H "X-API-Key: YOUR_SECRET_KEY" \
  "http://127.0.0.1:5000/api/history?type=search&limit=50"

# 查询最近 24 小时的下载记录
curl -H "X-API-Key: YOUR_SECRET_KEY" \
  "http://127.0.0.1:5000/api/history?type=downloads&hours=24"

# 查询最近 7 天的统计
curl -H "X-API-Key: YOUR_SECRET_KEY" \
  "http://127.0.0.1:5000/api/history?type=statistics&stat_hours=168"
```

**Python 示例**：

```python
import requests

API_KEY = "YOUR_SECRET_KEY"

def get_statistics(hours=24):
    response = requests.get(
        "http://127.0.0.1:5000/api/history",
        params={"type": "statistics", "stat_hours": hours},
        headers={"X-API-Key": API_KEY}
    )
    
    result = response.json()
    if result["code"] == 200:
        stats = result["data"]["statistics"]
        print(f"搜索次数: {stats['search']['total_count']}")
        print(f"下载次数: {stats['downloads']['total_count']}")
        print(f"下载总大小: {stats['downloads']['total_size_readable']}")
        
        print("\n热门关键词:")
        for kw in stats['search']['top_keywords'][:5]:
            print(f"  - {kw['keyword']}: {kw['count']} 次")

get_statistics(168)  # 最近 7 天
```

#### 应用场景：

- **使用分析**：了解热门搜索关键词和用户偏好
- **运营监控**：监控服务使用量和下载趋势
- **故障排查**：查看失败的下载记录和错误模式
- **数据报表**：生成日报/周报/月报和可视化图表

#### 数据管理：

历史记录存储在 `history.db` SQLite 数据库中，与 `music_library.db` 在同一目录下。

**数据库位置**：
- **本地部署**：项目根目录下的 `history.db` 和 `music_library.db`
- **Docker 部署**：`/app/data/` 目录下（通过 volume 持久化）

**自动清理机制**：
- 系统每 24 小时自动清理 30 天前的旧数据
- 无需手动维护，启动服务后自动运行

**手动清理**（可选）：
```python
from utils.history_tracker import HistoryTracker
from core.config import Config

history_tracker = HistoryTracker(Config.HISTORY_DATABASE_FILE)
history_tracker.clear_old_records(days=30)  # 清理 30 天前的记录
```

**清理日志**：
```
[定时任务] 历史记录清理完成，删除了 156 条旧记录
```

---

### 1. 本地音乐搜索 `/api/local/search`

**方法**：`GET`  
**描述**：在本地音乐库中搜索匹配的歌曲。

#### 参数：

| 参数     | 必需 | 说明                     |
|----------|------|--------------------------|
| `q`      | ✅   | 搜索关键词，格式：`歌手 - 歌曲名` |
| `album`  | ❌   | 专辑名称，用于精确匹配     |
| `quality`| ❌   | 音质过滤（如：lossless）   |

#### 示例：

```bash
curl -G -H "X-API-Key: YOUR_SECRET_KEY" \
  --data-urlencode "q=周杰伦 - 梯田" \
  --data-urlencode "album=叶惠美" \
  "http://127.0.0.1:5000/api/local/search"
```

---

### 2. QQ音乐搜索 `/api/qq`

**方法**：`GET`  
**描述**：通过歌曲 MID/ID、关键词、歌单 ID 或专辑 MID 搜索/下载 QQ 音乐。

#### 参数：

| 参数          | 必需          | 说明                          |
|--------------|---------------|-------------------------------|
| `mid`        | ✅（四选一）   | 歌曲的 Song MID               |
| `id`         | ✅（四选一）   | 歌曲的 Song ID                |
| `q`          | ✅（四选一）   | 搜索关键词，格式：`歌手 - 歌曲名` |
| `fast_q`     | ✅（五选一）   | 快速搜索关键词（返回搜索建议） |
| `playlist_id`| ✅（四选一）   | 歌单 ID（触发批量下载）        |
| `album_id`   | ✅（四选一）   | 专辑 MID（触发批量下载）       |
| `album`      | ❌            | 专辑名称（用于搜索过滤）       |
| `level`      | ❌            | 音质等级（仅作兼容性保留）     |

> ⚠️ `mid`、`id`、`q`、`fast_q`、`playlist_id`、`album_id` 至少提供一个

#### 示例：

##### 按 MID 获取单曲：

```bash
curl -H "X-API-Key: YOUR_SECRET_KEY" \
  "http://127.0.0.1:5000/api/qq?mid=002WCV372xJd69"
```

##### 按关键词搜索：

```bash
curl -G -H "X-API-Key: YOUR_SECRET_KEY" \
  --data-urlencode "q=周杰伦 - 稻香" \
  "http://127.0.0.1:5000/api/qq"
```

##### 快速搜索建议：

```bash
curl -G -H "X-API-Key: YOUR_SECRET_KEY" \
  --data-urlencode "fast_q=青花瓷" \
  "http://127.0.0.1:5000/api/qq"
```

##### 批量下载歌单：

```bash
curl -H "X-API-Key: YOUR_SECRET_KEY" \
  "http://127.0.0.1:5000/api/qq?playlist_id=8597034613"
```

##### 批量下载专辑：

```bash
curl -H "X-API-Key: YOUR_SECRET_KEY" \
  "http://127.0.0.1:5000/api/qq?album_id=002J7XBc0Gn7FH"
```

---

### 3. 网易云音乐搜索 `/api/netease`

**方法**：`GET`  
**描述**：通过歌曲 ID、关键词、歌单 ID 或专辑 ID 搜索/下载网易云音乐。

#### 参数：

| 参数          | 必需          | 说明                          |
|--------------|---------------|-------------------------------|
| `id`         | ✅（四选一）   | 歌曲 ID                       |
| `q`          | ✅（四选一）   | 搜索关键词，格式：`歌手 - 歌曲名` |
| `playlist_id`| ✅（四选一）   | 歌单 ID（触发批量下载）        |
| `album_id`   | ✅（四选一）   | 专辑 ID（触发批量下载）        |
| `album`      | ❌            | 专辑名称（用于搜索过滤）       |
| `level`      | ❌            | 音质等级，默认 `hires`<br>可选：`standard`, `exhigh`, `lossless`, `hires`, `jymaster` |

> ⚠️ `id`、`q`、`playlist_id`、`album_id` 至少提供一个

#### 示例：

##### 按 ID 获取单曲（指定音质）：

```bash
curl -H "X-API-Key: YOUR_SECRET_KEY" \
  "http://127.0.0.1:5000/api/netease?id=191179&level=hires"
```

##### 按关键词 + 专辑搜索：

```bash
curl -G -H "X-API-Key: YOUR_SECRET_KEY" \
  --data-urlencode "q=G.E.M.邓紫棋 - 龙卷风" \
  --data-urlencode "album=T-Time" \
  "http://127.0.0.1:5000/api/netease"
```

##### 批量下载歌单：

```bash
curl -H "X-API-Key: YOUR_SECRET_KEY" \
  "http://127.0.0.1:5000/api/netease?playlist_id=123456789&level=lossless"
```

##### 批量下载专辑：

```bash
curl -H "X-API-Key: YOUR_SECRET_KEY" \
  "http://127.0.0.1:5000/api/netease?album_id=987654321&level=hires"
```

---

### 4. 酷我音乐获取接口 `/api/kuwo`

**方法**：`GET`  
**描述**：获取单首酷我音乐的详细信息。支持两种模式：
1.  **按ID精确获取**：通过 `id` 参数获取指定歌曲的完整详情。
2.  **按关键词快速获取**：通过 `keyword` 参数搜索，并直接返回**第一首匹配歌曲**的完整详情。

> **💡 提示：需要更强大的搜索功能？**  
> 如果您需要浏览完整的搜索结果列表、进行分页或先搜索再选择歌曲，请使用**统一搜索接口**：  
> 👉 `/api/search?platform=kuwo`  
> 该接口提供了更灵活的搜索体验。

#### 参数：

| 参数      | 必需         | 说明                               |
|-----------|--------------|------------------------------------|
| `id`      | ✅ (二选一)  | 歌曲的 ID                          |
| `keyword` | ✅ (二选一)  | 搜索关键词，例如 `歌手 - 歌曲名`   |

> ⚠️ `id` 和 `keyword` 必须提供一个。

#### 示例：

##### 按 ID 获取单曲：
```bash
curl -H "X-API-Key: YOUR_SECRET_KEY" \
  "http://127.0.0.1:5000/api/kuwo?id=502592108"
```

##### 按关键词快速获取：
```bash
curl -G -H "X-API-Key: YOUR_SECRET_KEY" \
  --data-urlencode "keyword=周杰伦 夜曲" \
  "http://127.0.0.1:5000/api/kuwo"
```

---

## 📦 返回数据详细说明

所有 API 接口返回的数据都包含**丰富的歌曲元数据**，远不止播放链接。以下是各平台的详细返回数据结构：

### 统一响应格式

所有成功的 API 响应都遵循以下结构：

```json
{
  "code": 200,           // HTTP 状态码（200=成功，404=未找到，400=参数错误）
  "message": "成功",      // 响应消息
  "data": { ... }        // 具体数据（结构因平台而异）
}
```

---

### 1. 网易云音乐返回数据

#### 单曲查询响应示例：

```json
{
  "code": 200,
  "message": "成功",
  "data": {
    "name": "稻香",
    "artist": "周杰伦",
    "album": "魔杰座",
    "cover_url": "https://p1.music.126.net/...",
    "quality_requested": "hires",
    "quality_actual": "lossless",
    "size": "45.23MB",
    "url": "https://...(播放/下载链接)",
    "lyric": "[00:00.00]稻香 - 周杰伦\n[00:03.50]词：周杰伦\n...",
    "tlyric": "[00:00.00]Rice Fragrance\n..."
  }
}
```

#### 字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | String | 歌曲名称 |
| `artist` | String | 艺术家（多个用"、"分隔） |
| `album` | String | 专辑名称 |
| `cover_url` | String | 专辑封面图片 URL |
| `quality_requested` | String | 请求的音质等级 |
| `quality_actual` | String | 实际返回的音质等级 |
| `size` | String | 文件大小（人类可读格式） |
| `url` | String | 播放/下载链接（HTTPS） |
| `lyric` | String | 原文歌词（LRC 格式） |
| `tlyric` | String | 翻译歌词（LRC 格式） |

#### 批量下载响应示例：

```json
{
  "code": 202,
  "message": "任务已接受",
  "data": {
    "message": "歌单 123456789 已加入后台下载队列。"
  }
}
```

---

### 2. QQ 音乐返回数据

#### 单曲查询响应示例：

```json
{
  "code": 200,
  "message": "成功",
  "data": {
    "id": 102065756,
    "mid": "002WCV372xJd69",
    "name": "稻香",
    "artist": "周杰伦",
    "album_name": "魔杰座",
    "album_mid": "002J7XBc0Gn7FH",
    "duration": 223000,
    "cover_url": "https://y.qq.com/music/photo_new/T002R800x800M000...",
    "track_number": 5,
    "disc_number": 1,
    "bpm": 84,
    "lyricist": "周杰伦",
    "composer": "周杰伦",
    "arranger": "钟兴民",
    "genre": "流行",
    "urls": {
      "master": "https://...(Master 音质)",
      "flac": "https://...(FLAC 无损)",
      "320": "https://...(320K MP3)",
      "128": "https://...(128K MP3)"
    },
    "lyric": "[00:00.00]稻香 - 周杰伦\n...",
    "tlyric": ""
  }
}
```

#### 字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer | 歌曲 ID |
| `mid` | String | 歌曲 MID（唯一标识） |
| `name` | String | 歌曲名称 |
| `artist` | String | 艺术家（多个用"、"分隔） |
| `album_name` | String | 专辑名称 |
| `album_mid` | String | 专辑 MID |
| `duration` | Integer | 歌曲时长（毫秒） |
| `cover_url` | String | 专辑封面图片 URL（800x800） |
| `track_number` | Integer | 专辑中的音轨号 |
| `disc_number` | Integer | 碟片号（多碟专辑） |
| `bpm` | Integer | 每分钟节拍数 |
| `lyricist` | String | 作词人 |
| `composer` | String | 作曲人 |
| `arranger` | String | 编曲人 |
| `genre` | String | 音乐流派 |
| `urls` | Object | 多种音质的播放链接 |
| `lyric` | String | 原文歌词（LRC 格式） |
| `tlyric` | String | 翻译歌词（LRC 格式） |

---

### 3. 本地音乐库返回数据

#### 查询响应示例（注意：返回数组）：

```json
{
  "code": 200,
  "message": "成功",
  "data": [
    {
      "id": 1,
      "title": "周杰伦 - 稻香",
      "duration_ms": 223000,
      "album": "魔杰座",
      "quality": "flac",
      "download_url": "/api/local/download/1"
    },
    {
      "id": 2,
      "title": "周杰伦 - 稻香",
      "duration_ms": 223000,
      "album": "魔杰座",
      "quality": "master",
      "download_url": "/api/local/download/2"
    }
  ]
}
```

#### 字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | Integer | 数据库记录 ID |
| `title` | String | 歌曲标题（格式：艺术家 - 歌名） |
| `duration_ms` | Integer | 歌曲时长（毫秒） |
| `album` | String | 专辑名称 |
| `quality` | String | 音质标识（master/flac/320/128） |
| `download_url` | String | 本地下载路径 |

> ⚠️ **注意**：本地音乐库返回的是**数组**，因为同一首歌可能存在多个音质版本。

---

### 4. 酷我音乐返回数据

#### 查询响应示例：

```json
{
  "code": 200,
  "message": "成功",
  "data": {
    "id": "502592108",
    "name": "打火机 (火机摇)",
    "artist": "Penny",
    "album": "打火机 (火机摇)",
    "duration": 150000,
    "cover_url": "http://img1.kwcdn.kuwo.cn/star/albumcover/240/s4s27/80/1461251263.jpg",
    "url": "https://er-sycdn.kuwo.cn/...",
    "lyric": "[00:00.00]打火机 (火机摇) - Penny\\n...",
    "tlyric": null,
    "album_id": "76735886",
    "artist_id": "16049101",
    "popularity": 84,
    "has_mv": false,
    "size": "15.32 MB",
    "quality_actual": "HiRes音质 FLAC"
  }
}
```

#### 字段说明：

| 字段             | 类型    | 说明                                     |
|------------------|---------|------------------------------------------|
| `id`             | String  | 歌曲 ID                                  |
| `name`           | String  | 歌曲名称                                 |
| `artist`         | String  | 艺术家                                   |
| `album`          | String  | 专辑名称                                 |
| `duration`       | Integer | 歌曲时长（毫秒）                         |
| `cover_url`      | String  | 专辑封面图片 URL                         |
| `url`            | String  | 在线播放链接                             |
| `lyric`          | String  | 原文歌词 (LRC 格式)                      |
| `tlyric`         | String  | 翻译歌词 (酷我通常为 `null`)             |
| `album_id`       | String  | 专辑 ID                                  |
| `artist_id`      | String  | 艺术家 ID                                |
| `popularity`     | Integer | 歌曲热度 (0-100)                         |
| `has_mv`         | Boolean | 是否有 MV                                |
| `size`           | String  | 文件大小 (人类可读格式，来自备用接口)    |
| `quality_actual` | String  | 实际音质 (来自备用接口)                  |

> ⚠️ **注意**：酷我音乐接口用于在线播放，不直接触发本服务的后台下载与元数据嵌入流程。

---

### 错误响应格式

当请求失败时，API 返回以下格式：

```json
{
  "code": 404,
  "message": "未在本地库中找到歌曲: '周杰伦 - 不存在的歌'"
}
```

或

```json
{
  "code": 400,
  "message": "必须提供 'id', 'q', 'playlist_id' 或 'album_id' 参数之一。"
}
```

### 常见错误码

| 错误码 | 说明 |
|-------|------|
| `400` | 请求参数错误或缺失 |
| `401` | API 密钥认证失败 |
| `404` | 未找到请求的资源 |
| `202` | 批量任务已接受（后台处理中） |

---

### 前端使用示例

#### JavaScript / TypeScript

```javascript
// 获取 QQ 音乐歌曲详情
async function getSongDetails(keyword) {
  const response = await fetch(
    `http://localhost:5000/api/qq?q=${encodeURIComponent(keyword)}`,
    {
      headers: {
        'X-API-Key': 'YOUR_SECRET_KEY'
      }
    }
  );
  
  const result = await response.json();
  
  if (result.code === 200) {
    const song = result.data;
    
    // 使用返回的数据
    console.log(`歌曲名: ${song.name}`);
    console.log(`艺术家: ${song.artist}`);
    console.log(`BPM: ${song.bpm}`);
    
    // 播放最高音质
    const audioUrl = song.urls.master || song.urls.flac || song.urls['320'];
    audioPlayer.src = audioUrl;
    
    // 显示封面
    coverImage.src = song.cover_url;
    
    // 显示歌词
    lyricsDisplay.innerHTML = song.lyric;
  }
}

// 批量下载歌单
async function downloadPlaylist(playlistId) {
  const response = await fetch(
    `http://localhost:5000/api/netease?playlist_id=${playlistId}&level=lossless`,
    {
      headers: {
        'X-API-Key': 'YOUR_SECRET_KEY'
      }
    }
  );
  
  const result = await response.json();
  
  if (result.code === 202) {
    console.log(result.data.message);
    // 提示用户：任务已加入队列，后台处理中
  }
}
```

#### Python

```python
import requests

# API 配置
API_KEY = "YOUR_SECRET_KEY"
BASE_URL = "http://localhost:5000"

def get_song_details(keyword):
    headers = {"X-API-Key": API_KEY}
    params = {"q": keyword}
    
    response = requests.get(
        f"{BASE_URL}/api/netease",
        params=params,
        headers=headers
    )
    
    result = response.json()
    
    if result["code"] == 200:
        song = result["data"]
        print(f"歌曲名: {song['name']}")
        print(f"艺术家: {song['artist']}")
        print(f"音质: {song['quality_actual']}")
        print(f"文件大小: {song['size']}")
        print(f"下载链接: {song['url']}")
        
        return song
    else:
        print(f"错误: {result['message']}")
        return None

# 使用示例
song = get_song_details("周杰伦 - 稻香")
```

---

### 数据流说明

#### 在线平台（网易云/QQ音乐）请求流程：

1. **立即返回**：API 立即返回在线播放链接和完整元数据
2. **后台下载**：同时触发后台下载线程（如果 `DOWNLOADS_ENABLED = True`）
3. **自动入库**：下载完成后自动写入本地数据库
4. **下次使用**：下次查询时可直接使用本地高音质文件

#### 智能优先级策略：

```
用户请求歌曲
    ↓
检查本地数据库
    ├─ 已存在 → 返回本地文件路径（无需在线请求）
    └─ 不存在 → 调用在线 API
        ↓
    立即返回在线链接 + 元数据
        ↓
    后台下载 + 元数据嵌入
        ↓
    写入数据库（下次直接用本地）
```

这样的设计确保了：
- ✅ **响应速度快**：用户无需等待下载完成
- ✅ **体验渐进增强**：首次在线播放，之后自动使用本地高音质
- ✅ **数据完整性**：保存完整的音乐元数据和歌词

---

## 🔍 音乐源信息查询工具

### 功能说明

每个下载的音乐文件都嵌入了平台溯源信息：
- **MusicSource**：`平台:ID` 格式，如 `netease:1901371647` 或 `qq:002WCV372xJd69`

这些信息可用于：
- 🔍 反查歌曲原始来源
- 🔄 更新歌曲元数据
- 📊 统计音乐库来源分布
- 🔗 生成平台分享链接

### 使用查询工具

项目提供了 `tools/music_source_checker.py` 工具：

```bash
# 查询单个文件
python tools/music_source_checker.py "music/周杰伦 - 稻香 魔杰座.flac"

# 扫描目录
python tools/music_source_checker.py music/

# 递归扫描所有子目录
python tools/music_source_checker.py music/ -r
```

### 查询结果示例

```
============================================================
📁 文件: music/周杰伦 - 稻香 魔杰座.flac
📝 格式: FLAC
🎵 标题: 稻香
👤 艺术家: 周杰伦
💿 专辑: 魔杰座
============================================================
🔗 音乐源: netease:1901371647
🌐 平台: 网易云音乐
🆔 ID: 1901371647

📡 反查链接:
   网易云: https://music.163.com/#/song?id=1901371647
   API: /api/netease?id=1901371647
```

### Python 代码查询

```python
from mutagen.mp3 import MP3
from mutagen.flac import FLAC

# MP3 文件
audio = MP3("music/周杰伦 - 稻香.mp3")
for tag in audio.tags.values():
    if hasattr(tag, 'desc') and tag.desc == 'MusicSource':
        music_source = tag.text[0]  # netease:1901371647
        print(f"音乐源: {music_source}")
        
        # 解析平台和ID
        if ':' in music_source:
            platform, music_id = music_source.split(':', 1)
            print(f"平台: {platform}")  # netease
            print(f"ID: {music_id}")     # 1901371647
        break

# FLAC 文件
audio = FLAC("music/周杰伦 - 稻香.flac")
music_source = audio.get('musicsource', [''])[0]  # netease:1901371647
print(f"音乐源: {music_source}")

if music_source and ':' in music_source:
    platform, music_id = music_source.split(':', 1)
    print(f"平台: {platform}")
    print(f"ID: {music_id}")
```

### 嵌入的元数据标签

#### MP3 文件（ID3 标签）
| 标签 | 描述 | 示例 |
|------|------|------|
| `TXXX:MusicSource` | 音乐源标识（平台:ID） | `netease:1901371647` 或 `qq:002WCV372xJd69` |

#### FLAC 文件（Vorbis Comment）
| 标签 | 描述 | 示例 |
|------|------|------|
| `musicsource` | 音乐源标识（平台:ID） | `netease:1901371647` 或 `qq:002WCV372xJd69` |

### 应用场景

#### 1. 批量更新元数据
```bash
# 扫描找到所有网易云音乐
python tools/music_source_checker.py music/ -r | grep "netease"

# 使用API更新元数据
curl -H "X-API-Key: YOUR_KEY" \
  "http://localhost:5000/api/netease?id=1901371647"
```

#### 2. 生成分享链接
```python
# 根据嵌入信息生成平台链接
platform = "netease"
song_id = "1901371647"

if platform == "netease":
    url = f"https://music.163.com/#/song?id={song_id}"
elif platform == "qq":
    url = f"https://y.qq.com/n/ryqq/songDetail/{song_id}"

print(f"分享链接: {url}")
```

#### 3. 统计音乐库来源
```bash
# 使用工具统计
python tools/music_source_checker.py music/ -r

# 输出示例：
# 📊 平台分布:
#    网易云音乐: 234 首
#    QQ音乐: 156 首
#    未知/其他: 45 首
```

---

## 🐳 Docker 部署说明

### 快速启动

使用我们提供的快速启动脚本：

```bash
# Linux/macOS
cd docker
chmod +x start.sh
./start.sh

# Windows
cd docker
start.bat
```

### 目录结构

项目的完整目录结构如下：

```
music-api-server/
├── api/                # API 模块
├── core/               # 核心配置
│   ├── config.py       # 配置文件（需要挂载到容器）
│   └── config.py.template  # 配置模板
├── docker/             # 🐳 Docker 相关文件
│   ├── Dockerfile      # Docker 镜像构建文件
│   ├── docker-compose.yml  # Docker Compose 配置
│   ├── .dockerignore   # Docker 构建忽略文件
│   ├── start.sh        # Linux/macOS 快速启动脚本
│   ├── start.bat       # Windows 快速启动脚本
│   ├── config.docker.example.py  # Docker 配置示例
│   ├── README.md       # Docker 目录说明
│   └── DOCKER.md       # 详细的 Docker 部署文档
├── music/              # 音乐文件存储目录（挂载）
├── data/               # 数据库文件目录（挂载）
│   └── music_library.db
├── utils/              # 工具模块
├── main.py             # 主程序入口
└── requirements.txt    # Python 依赖
```

### 配置注意事项

1. **配置文件路径**：Docker 环境中，请在 `core/config.py` 中设置：
   ```python
   MUSIC_DIRECTORY = "/app/music"
   DATABASE_FILE = "/app/data/music_library.db"
   HISTORY_DATABASE_FILE = "/app/data/history.db"
   ```

2. **音乐目录挂载**：
   - 默认挂载项目根目录的 `./music` 到容器的 `/app/music`
   - 可在 `docker/docker-compose.yml` 中修改路径为你的实际音乐目录

3. **数据持久化**：
   - 数据库文件保存在项目根目录的 `./data` 目录
   - 所有下载的音乐文件保存在项目根目录的 `./music` 目录

4. **Docker 文件位置**：
   - 所有 Docker 相关配置文件都在 `docker/` 目录下
   - 需要在 `docker/` 目录下执行 `docker-compose` 命令

### 常用 Docker 命令

```bash
# 进入 docker 目录
cd docker

# 重启服务
docker-compose restart

# 查看实时日志
docker-compose logs -f music-api

# 进入容器
docker-compose exec music-api bash

# 更新镜像并重启
docker-compose down
docker-compose up -d --build

# 查看容器状态
docker-compose ps
```

---

### 详细文档

更多 Docker 使用说明和故障排查，请参阅：

- 📖 [docker/README.md](docker/README.md) - Docker 目录说明和快速参考
- 📘 [docker/DOCKER.md](docker/DOCKER.md) - 完整的 Docker 部署指南

---

## 🔧 环境变量配置（可选）

你也可以通过环境变量来覆盖部分配置项。在 `docker/docker-compose.yml` 中添加：

```yaml
environment:
  - API_SECRET_KEY=your_secret_key
  - DEBUG_MODE=False
```

---

## 📊 健康检查

Docker 容器已配置健康检查，每 30 秒自动检测服务状态：

```bash
# 查看健康状态
docker inspect --format='{{.State.Health.Status}}' music-api-server
```

---

## 🏗️ 技术架构

### 核心技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.11 | 主要开发语言 |
| Flask | 3.1.2 | Web 框架 |
| SQLite | 3 | 本地音乐库索引数据库 |
| APScheduler | 3.11.0 | 定时任务调度（Cookie 刷新） |
| Mutagen | 1.47.0 | 音频元数据读写 |
| Requests | 2.32.5 | HTTP 请求处理 |
| Cryptography | 46.0.1 | 加密解密（网易云 EAPI） |
| PyCryptodome | 3.23.0 | DES 加密（酷我音乐） |
| OpenCC | 0.1.7 | 简繁体转换 |

### 项目架构

```
music-api-server/
├── api/                          # API 模块（多平台音乐源）
│   ├── __init__.py
│   ├── local.py                  # 本地音乐库 API（SQLite 查询、音质匹配）
│   ├── netease.py                # 网易云音乐 API（EAPI 加密、批量下载）
│   ├── qq.py                     # QQ 音乐 API（多音质获取、批量下载）
│   └── kuwo.py                   # 酷我音乐 API（DES 加密）
│
├── core/                         # 核心配置与功能
│   ├── config.py.template        # 配置模板
│   ├── config.py                 # 实际配置文件（需自行创建）
│   └── qq_refresh/               # QQ 音乐 Cookie 刷新模块
│       ├── refresher.py          # Cookie 刷新核心逻辑
│       └── utils.py              # 签名算法实现
│
├── utils/                        # 工具函数
│   ├── __init__py
│   └── helpers.py                # 通用辅助函数（文件大小格式化、Cookie 解析）
│
├── docker/                       # Docker 部署文件
│   ├── Dockerfile                # 镜像构建文件
│   ├── docker-compose.yml        # 容器编排配置
│   ├── start.sh                  # Linux/macOS 启动脚本
│   ├── start.bat                 # Windows 启动脚本
│   ├── config.docker.example.py  # Docker 配置示例
│   ├── README.md                 # Docker 快速参考
│   └── DOCKER.md                 # 完整 Docker 部署指南
│
├── main.py                       # Flask 应用入口（路由定义、认证、定时任务）
├── scanner.py                    # 本地音乐扫描器（自动建立索引）
├── requirements.txt              # Python 依赖清单
└── README.md                     # 项目文档
```

### 核心模块说明

#### 1. API 模块（`api/`）

**本地音乐 API（`local.py`）**
- SQLite 数据库查询优化
- 音质向下兼容逻辑（master → flac → 320 → 128）
- 专辑名标准化与模糊匹配
- 支持按音质、专辑过滤

**网易云音乐 API（`netease.py`）**
- EAPI 加密/解密（AES-128-ECB）
- 智能分层下载（jymaster、lossless、exhigh）
- 歌单/专辑批量下载
- 后台异步下载线程
- 完整元数据嵌入（15+ 字段）
- 专辑详情缓存机制

**QQ 音乐 API（`qq.py`）**
- 多音质链接获取（Master、FLAC、320K等）
- 歌单/专辑批量下载
- 重试机制（最多 3 次）
- 失败日志记录
- 完整元数据嵌入（含作词、作曲、编曲、BPM）

**酷我音乐 API（`kuwo.py`）**
- DES 加密参数生成
- 搜索与播放链接获取
- 仅支持在线播放

#### 2. Cookie 自动刷新（`core/qq_refresh/`）

- 基于 APScheduler 的定时任务（每 23 小时执行）
- 自动生成签名（SHA1 + Base64 + 字符串变换）
- 刷新成功后自动更新 `config.py`
- 刷新失败时保留旧配置并记录日志

#### 3. 本地音乐扫描器（`scanner.py`）

- 递归扫描音乐目录（支持 MP3、FLAC、WAV、M4A）
- 自动提取元数据（Mutagen）
- 识别音质标记（`[M]` 后缀表示 Master）
- 简繁体自动转换（OpenCC）
- SQLite 数据库索引管理

#### 4. 主应用（`main.py`）

- Flask 路由注册
- API 密钥认证中间件
- 定时任务初始化
- 多 API 实例管理

### 数据流

#### 单曲搜索流程

```
用户请求 → API 认证 → 平台 API 查询 
  ↓
检查本地数据库（已存在？）
  ├─ 是 → 返回本地文件信息
  └─ 否 → 调用在线 API
      ↓
   获取歌曲详情（元数据 + 歌词）
      ↓
   启动后台下载线程（异步）
      ├─ 智能音质选择
      ├─ 下载音频文件
      ├─ 嵌入完整元数据
      └─ 写入 SQLite 数据库
      ↓
   立即返回在线播放链接（不等待下载完成）
```

#### 批量下载流程

```
用户请求（playlist_id/album_id）
  ↓
立即返回 202 Accepted（任务已接受）
  ↓
后台线程启动
  ├─ 获取歌单/专辑曲目列表
  ├─ 遍历每首歌曲
  │   ├─ 获取详情
  │   ├─ 检查本地是否已存在
  │   ├─ 启动下载（如需要）
  │   └─ 延迟 1 秒（避免请求过快）
  └─ 完成后输出日志
```

---

## 🎯 使用场景

### 1. 个人音乐库管理
- 自动整理本地音乐文件
- 批量下载高音质音乐
- 统一管理多平台音乐

### 2. 音乐播放器后端
- 为自定义播放器提供统一 API
- 支持在线播放和本地播放切换
- 自动音质选择

### 3. 音乐收藏与归档
- 批量下载歌单、专辑
- 完整保存元数据和歌词
- 支持无损音质归档

### 4. 音乐数据分析
- 导出音乐库元数据
- 分析收藏习惯
- 生成统计报告

---

## 📝 配置说明

### 必需配置项

```python
# core/config.py

# API 认证密钥（必需）
API_SECRET_KEY = "your_secret_key_here"

# 网易云音乐 Cookie（必需）
NETEASE_COOKIE_STR = "MUSIC_U=your_music_u_cookie;os=pc;appver=9.9.9"

# QQ 音乐配置（必需）
QQ_USER_CONFIG = {
    "uin": "your_qq_uin",
    "qqmusic_key": "your_qqmusic_key",
    "qm_keyst": "your_qm_keyst",
    "refresh_token": "your_refresh_token"
}

# 本地音乐目录（必需）
MUSIC_DIRECTORY = "/path/to/your/music"

# 数据库文件路径（必需）
DATABASE_FILE = "music_library.db"

# 历史记录数据库路径（可选，默认与音乐库数据库同目录）
HISTORY_DATABASE_FILE = "history.db"
```

### 可选配置项

```python
# 服务器设置
HOST = '0.0.0.0'  # 监听地址
PORT = 5000       # 监听端口
DEBUG_MODE = False  # 生产环境建议关闭

# 下载功能开关
DOWNLOADS_ENABLED = True  # 设置为 False 禁用自动下载
```

---

## 🔒 安全建议

1. **API 密钥保护**
   - 使用强随机密钥（建议 32 位以上）
   - 定期更换 API 密钥
   - 不要将密钥提交到版本控制系统

2. **Cookie 安全**
   - 不要分享你的 Cookie 文件
   - 定期检查账号登录设备
   - Cookie 泄露后立即在官方网站退出登录

3. **网络安全**
   - 建议仅在内网使用
   - 如需公网访问，务必配置 HTTPS
   - 使用防火墙限制访问 IP

4. **文件权限**
   - 确保配置文件权限为 600（仅所有者可读写）
   - 音乐目录权限适当限制

---

## ❓ 常见问题

### Q1: 如何获取网易云音乐的 Cookie？

1. 在浏览器中登录 [music.163.com](https://music.163.com)
2. 按 F12 打开开发者工具 → Network 标签
3. 刷新页面，找到任意请求
4. 在 Request Headers 中找到 `Cookie` 字段
5. 复制 `MUSIC_U=...` 的完整值

### Q2: 如何获取 QQ 音乐的配置？

1. 使用抓包工具（如 Fiddler、Charles）
2. 登录 QQ 音乐客户端
3. 捕获请求，提取 Cookie 中的 `uin` 和 `qqmusic_key`
4. `refresh_token` 可从登录响应中获取

### Q3: 下载的音乐保存在哪里？

默认保存在 `MUSIC_DIRECTORY` 配置的目录中，文件名格式：
- 普通音质：`歌手 - 歌名 专辑名.扩展名`
- Master 音质：`歌手 - 歌名 专辑名 [M].flac`

### Q4: 如何扫描本地音乐库？

```bash
# 进入项目目录
cd music-api-server

# 运行扫描器
python scanner.py
```

### Q5: 下载失败如何排查？

1. 查看控制台输出日志
2. 检查 `download_errors_qq.log` 文件
3. 验证 Cookie 是否过期
4. 确认音乐是否有版权限制

---

## 📄 许可证

本项目仅供学习交流使用，请勿用于商业用途。使用本项目时请遵守相关平台的服务条款。

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## ⭐ Star History

如果这个项目对你有帮助，欢迎给个 Star ⭐

---

