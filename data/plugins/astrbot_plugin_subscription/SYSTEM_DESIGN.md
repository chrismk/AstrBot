# 订阅系统设计文档

## 一、系统架构概览

```
+-------------------------------------------------------------------------+
|                         订阅系统 (Subscription System)                    |
+-------------------------------------------------------------------------+
|                                                                          |
|  +------------+  +------------+  +------------+  +------------+          |
|  |  用户层    |  |  管理层    |  |  调度层    |  |  数据层    |          |
|  | User Layer |  |Admin Layer |  | Scheduler  |  | Data Layer |          |
|  +-----+------+  +-----+------+  +-----+------+  +-----+------+          |
|        |               |               |               |                 |
|        v               v               v               v                 |
|  +-------------------------------------------------------------------+  |
|  |                      核心组件 (Core Components)                    |  |
|  |  +-----------+ +-----------+ +-----------+ +-----------+          |  |
|  |  |Subscription| |  Source   | | Prefetcher| |   Push    |          |  |
|  |  |  Manager   | |  Manager  | | Scheduler | | Formatter |          |  |
|  |  +-----------+ +-----------+ +-----------+ +-----------+          |  |
|  +-------------------------------------------------------------------+  |
|                                                                          |
+-------------------------------------------------------------------------+
```

---

## 二、核心模块说明

### 2.1 订阅管理器 (SubscriptionManager)
**文件**: `common/subscription_manager.py`

**职责**:
- 管理用户订阅的 CRUD 操作
- 计算下次推送时间
- 管理推送日志和重试队列
- 内容去重检查

**核心数据结构**:
```python
@dataclass
class Subscription:
    id: int
    user_id: str                    # 统一用户ID (platform:raw_id)
    subscription_type: SubscriptionType  # ranking/keyword/source 等
    plugin_name: str                # 插件名称
    target: str                     # 订阅目标（源ID/关键词等）
    config: Dict[str, Any]          # 订阅配置
    push_frequency: PushFrequency   # daily/multi_daily/realtime/weekly_digest
    push_time: str                  # "08:00" 或 "08:00,20:00"
    push_days: List[int]            # [0,1,2,3,4,5,6] 周一到周日
    enabled: bool
    next_push_at: datetime          # 下次推送时间
```

**关键方法**:
| 方法 | 说明 |
|------|------|
| `create_subscription()` | 创建订阅 |
| `get_due_subscriptions()` | 获取到期需推送的订阅 |
| `get_all_active_subscriptions()` | 获取所有活跃订阅 |
| `mark_pushed()` | 标记已推送，计算下次时间 |
| `is_content_pushed()` | 检查内容是否已推送（去重） |
| `add_to_retry_queue()` | 添加到重试队列 |

---

### 2.2 订阅源管理器 (SourceManager)
**文件**: `common/subscription_source.py`

**职责**:
- 管理订阅源的 CRUD
- 管理订阅链接（一个链接可包含多个源）
- 内容抓取和缓存
- 适配器模式支持多种源类型

**核心数据结构**:
```python
@dataclass
class SubscriptionSource:
    id: int
    name: str                       # 唯一标识
    display_name: str               # 显示名称
    source_type: SourceType         # internal/rss/api/webhook
    category: str                   # 分类
    url: str                        # 源URL
    icon: str                       # 图标
    status: SourceStatus            # active/inactive/error
    access_level: AccessLevel       # public/member/vip/admin
    
    # 推送配置
    push_content_mode: str          # full/ai_summary/brief/title_list
    push_max_items: int             # 每次推送最大条目
    push_include_link: bool         # 是否包含链接
```

**源类型适配器**:
```
SourceAdapter (基类)
    +-- InternalAdapter   # 内部榜单（搜索统计）
    +-- RSSAdapter        # RSS/Atom 订阅
    +-- APIAdapter        # REST API
    +-- WebhookAdapter    # Webhook 推送
```

---

### 2.3 内容预抓取器 (ContentPrefetcher)
**文件**: `common/content_prefetcher.py`

**职责**:
- 提前抓取内容，避免推送时集中请求
- 智能调度，根据推送时间和更新频率安排抓取
- 并发控制，防止IP封禁
- 内容缓存管理

**核心策略**:
```
推送时间: 8:00
    |
    v
6:00-7:00  预抓取阶段
    |      - 分散抓取所有8点要推送的源
    |      - 每次间隔2-5秒，最大并发3个
    v
7:30-7:55  紧急补抓
    |      - 检查缓存是否过期
    |      - 补抓失败的内容
    v
8:00       推送时刻
           - 直接使用缓存，无需抓取
```

**优先级队列**:
| 优先级 | 枚举值 | 触发条件 |
|--------|--------|----------|
| URGENT | 0 | 30分钟内推送 |
| HIGH | 1 | 1小时内推送 |
| NORMAL | 2 | 常规调度 |
| LOW | 3 | 不活跃源 |

---

### 2.4 推送调度器 (PushScheduler)
**文件**: `common/push_scheduler.py`

**职责**:
- 错峰推送，避免同一时刻大量推送
- 批量合并，相同源的推送共享内容
- 失败重试，递增延迟

**错峰策略**:
```
用户都设置8点推送 -> 分散到 8:00-8:10 窗口

8:00:00  用户A (源1)
8:00:30  用户B (源1)  <- 相同源，时间接近
8:01:00  用户C (源2)  <- 不同源，错开
8:01:30  用户D (源2)
...
```

---

### 2.5 推送格式化器 (PushFormatter)
**文件**: `common/push_formatter.py`

**职责**:
- 根据订阅源配置格式化推送内容
- 支持多种推送模式
- 整合AI摘要功能

**推送模式**:
| 模式 | 枚举值 | 说明 |
|------|--------|------|
| 完整内容 | `full` | 推送完整内容详情 |
| AI摘要 | `ai_summary` | AI生成内容摘要 |
| 简要提醒 | `brief` | 仅标题和链接 |
| 标题列表 | `title_list` | 多条合并为列表 |

---

## 三、完整推送流程

### 3.1 用户订阅流程

```
用户发送 /订阅
    |
    v
1. 显示订阅中心主菜单
   - 我的订阅 / 浏览订阅源 / 订阅设置
    |
    v 选择"浏览订阅源"
2. 显示订阅源分类列表
   - 按分类筛选
   - 根据用户等级过滤可见源
    |
    v 选择订阅源
3. 显示订阅源详情
   - 源描述 / 订阅人数 / 订阅按钮
    |
    v 点击"订阅"
4. 设置推送时间
   - 选择推送频率
   - 选择推送时间点
   - 选择推送日期
    |
    v 确认订阅
5. 创建订阅记录
   - SubscriptionManager.create()
   - 计算 next_push_at
```

### 3.2 内容抓取流程 (ContentPrefetcher)

```
启动时:
    |
    v
1. 构建推送时间索引
   - 遍历所有活跃订阅
   - 按推送小时分组: {8: [源1,源2], 12: [源3], ...}
    |
    v
2. 初始化任务队列
   - 获取所有活跃订阅源
   - 计算每个源的优先级和调度时间
   - 加入优先级队列
    |
    v
3. 调度循环 (每10秒)
   |
   +-> 检查到期任务
   |   - 取出到期任务
   |   - 异步执行抓取
   |   - 随机延迟2-5秒
   |
   +-> 每小时重建推送时间索引
```

### 3.3 单次抓取流程

```
execute_fetch(task):
    |
    v
1. 获取信号量 (并发控制)
    |
    v
2. 获取订阅源信息
    |
    v
3. 调用适配器抓取内容
   - RSSAdapter.fetch()
   - APIAdapter.fetch()
   - ...
    |
    v
4. 计算内容哈希 (用于检测更新)
    |
    v
5. 更新缓存
   - CachedContent(items, fetch_time, hash)
    |
    v
6. 更新统计信息
   - 成功率 / 平均耗时 / 更新频率
    |
    v
7. 重新调度下次抓取
   - 根据更新频率动态调整间隔
```

### 3.4 推送执行流程

```
定时任务触发 (每分钟):
    |
    v
1. 获取到期订阅
   - get_due_subscriptions(buffer_minutes=1)
    |
    v
2. 按用户优先级排序
   - VIP用户优先推送
    |
    v
3. 并发处理 (信号量控制)
   |
   +-> 对每个订阅:
       |
       v
   4. 获取缓存内容
      - prefetcher.get_content(source_id)
      - 如无缓存，降级直接抓取
       |
       v
   5. 格式化内容
      - PushFormatter.format_push_content()
      - 根据 push_content_mode 选择格式
       |
       v
   6. 内容去重检查
      - is_content_pushed(user_id, source_id, hash)
      - 已推送则跳过
       |
       v
   7. 添加广告 (非会员)
      - privilege_manager.format_ad_message()
       |
       v
   8. 发送推送
      - message_pusher.send_private_message()
       |
       v
   9. 记录结果
      - 成功: mark_pushed() + mark_content_pushed()
      - 失败: add_to_retry_queue()
```

### 3.5 重试流程

```
重试任务 (每分钟):
    |
    v
1. 获取待重试列表
   - get_pending_retries(limit=50)
    |
    v
2. 逐个重试
   - 最大重试3次
   - 延迟递增: 1分钟 -> 5分钟 -> 15分钟
    |
    v
3. 更新状态
   - 成功: 标记完成
   - 失败: 更新重试次数，超限则放弃
```

---

## 四、数据库表结构

### 4.1 subscriptions (订阅表)
```sql
CREATE TABLE subscriptions (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL,              -- 统一用户ID
    subscription_type TEXT NOT NULL,    -- 订阅类型
    plugin_name TEXT,                   -- 插件名称
    target TEXT,                        -- 订阅目标
    config TEXT,                        -- JSON配置
    push_frequency TEXT DEFAULT 'daily',
    push_time TEXT DEFAULT '19:00',
    push_days TEXT DEFAULT '[0,1,2,3,4,5,6]',
    enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP,
    last_push_at TIMESTAMP,
    next_push_at TIMESTAMP,
    
    UNIQUE(user_id, subscription_type, target)
);
```

### 4.2 subscription_sources (订阅源表)
```sql
CREATE TABLE subscription_sources (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    display_name TEXT,
    source_type TEXT NOT NULL,
    category TEXT,
    description TEXT,
    url TEXT,
    icon TEXT DEFAULT '📰',
    parser_config TEXT,                 -- JSON
    status TEXT DEFAULT 'active',
    access_level INTEGER DEFAULT 0,
    current_subscribers INTEGER DEFAULT 0,
    max_subscribers INTEGER,
    update_interval INTEGER DEFAULT 3600,
    
    -- 推送配置
    push_content_mode TEXT DEFAULT 'full',
    push_max_items INTEGER DEFAULT 5,
    push_include_link INTEGER DEFAULT 1,
    push_ai_prompt TEXT,
    push_template TEXT,
    push_format TEXT,
    
    created_at TIMESTAMP,
    created_by TEXT,
    last_update TIMESTAMP,
    error_message TEXT
);
```

### 4.3 push_logs (推送日志表)
```sql
CREATE TABLE push_logs (
    id INTEGER PRIMARY KEY,
    subscription_id INTEGER,
    user_id TEXT,
    source_id INTEGER,
    status TEXT,                        -- success/failed
    content_hash TEXT,
    error_message TEXT,
    pushed_at TIMESTAMP,
    
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
);
```

### 4.4 push_retry_queue (重试队列表)
```sql
CREATE TABLE push_retry_queue (
    id INTEGER PRIMARY KEY,
    subscription_id INTEGER,
    user_id TEXT,
    content TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    last_error TEXT,
    next_retry_at TIMESTAMP,
    created_at TIMESTAMP,
    status TEXT DEFAULT 'pending'       -- pending/success/failed
);
```

### 4.5 content_push_history (内容推送历史，用于去重)
```sql
CREATE TABLE content_push_history (
    id INTEGER PRIMARY KEY,
    user_id TEXT,
    source_id INTEGER,
    content_hash TEXT,
    pushed_at TIMESTAMP,
    
    UNIQUE(user_id, source_id, content_hash)
);
```

---

## 五、配置项说明

### 5.1 插件配置 (main.py)
```python
defaults = {
    'session_timeout': 2,           # 会话超时（分钟）
    'max_subscriptions_per_user': 20,  # 每用户最大订阅数
    'default_push_time': '19:00',   # 默认推送时间
    'push_check_interval': 60,      # 推送检查间隔（秒）
    'push_batch_size': 50,          # 批量推送大小
    'push_concurrency': 10,         # 推送并发数
    
    # 智能调度配置
    'prefetch_enabled': True,       # 启用预抓取
    'prefetch_max_concurrent': 3,   # 预抓取最大并发
    'prefetch_interval_min': 300,   # 预抓取最小间隔（秒）
    'push_spread_window': 600,      # 错峰推送窗口（秒）
}
```

### 5.2 预抓取器配置 (content_prefetcher.py)
```python
DEFAULT_FETCH_INTERVAL = 1800       # 默认抓取间隔：30分钟
MIN_FETCH_INTERVAL = 300            # 最小抓取间隔：5分钟
MAX_FETCH_INTERVAL = 7200           # 最大抓取间隔：2小时

MAX_CONCURRENT_FETCHES = 3          # 最大并发抓取数
FETCH_DELAY_MIN = 2                 # 抓取间隔最小延迟（秒）
FETCH_DELAY_MAX = 5                 # 抓取间隔最大延迟（秒）

PRE_FETCH_WINDOW = 3600             # 预抓取窗口：推送前1小时
URGENT_WINDOW = 1800                # 紧急窗口：推送前30分钟

CACHE_TTL = 7200                    # 缓存有效期：2小时
MAX_RETRY = 3                       # 最大重试次数
```

---

## 六、待优化项

### 6.1 已完成
- [x] P0: 内容去重机制
- [x] P0: 推送失败重试机制
- [x] P1: 推送并发控制
- [x] P1: 内容缓存
- [x] 推送时间智能化（多时段/实时/每周摘要）
- [x] 批量导入订阅源
- [x] 预抓取调度系统
- [x] 推送内容模式（完整/AI摘要/简要/标题列表）

### 6.2 可优化项
- [x] **源健康监控**: 自动检测源是否失效，连续失败5次自动停用
- [x] **数据库索引**: 为高频查询字段添加索引
- [x] **批量日志写入**: 推送日志批量写入，减少IO
- [x] **用户反馈闭环**: 用户可标记推送"有用/无用"，优化推荐
- [ ] **推送时间学习**: 根据用户阅读时间自动调整推送时间
- [ ] **内容相似度去重**: 不同源的相似内容合并推送
- [ ] **推送限流**: 单用户单日推送上限，防止骚扰
- [ ] **分布式支持**: 多实例部署时的任务协调

### 6.3 已实现的性能优化

#### 源健康监控 (content_prefetcher.py)
```python
# 配置
CONSECUTIVE_FAIL_THRESHOLD = 5  # 连续失败阈值
AUTO_DISABLE_ENABLED = True     # 启用自动停用

# 逻辑
- 成功抓取: consecutive_fails = 0
- 失败抓取: consecutive_fails += 1
- 超过阈值: 自动停用源，标记为 ERROR 状态
- 管理员可手动调用 reactivate_source() 重新激活
```

#### 数据库索引 (subscription_manager.py)
```sql
-- 订阅表索引
CREATE INDEX idx_subscriptions_user ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_type ON subscriptions(subscription_type);
CREATE INDEX idx_subscriptions_next_push ON subscriptions(next_push_at);
CREATE INDEX idx_subscriptions_enabled ON subscriptions(enabled);
CREATE INDEX idx_subscriptions_source ON subscriptions(source_id);
CREATE INDEX idx_subscriptions_active_next ON subscriptions(is_active, next_push_at);

-- 推送日志索引
CREATE INDEX idx_push_logs_user ON subscription_push_logs(user_id);
CREATE INDEX idx_push_logs_time ON subscription_push_logs(pushed_at);

-- 内容历史索引
CREATE INDEX idx_content_history_time ON push_content_history(pushed_at);

-- 订阅源索引 (subscription_source.py)
CREATE INDEX idx_sources_type ON subscription_sources(source_type);
CREATE INDEX idx_sources_status ON subscription_sources(status);
CREATE INDEX idx_sources_access ON subscription_sources(access_level);
```

#### 批量日志写入 (subscription_manager.py)
```python
# 配置
LOG_BATCH_SIZE = 50         # 批量写入阈值
LOG_FLUSH_INTERVAL = 30     # 强制刷新间隔（秒）

# 逻辑
1. 日志先写入内存缓冲区
2. 达到阈值或超时时批量写入数据库
3. 批量写入失败时降级为逐条写入
4. 提供 flush_logs() 方法供外部强制刷新
```

#### 用户反馈系统 (subscription_manager.py)
```python
# 数据库表
push_feedback:        # 用户反馈记录
  - user_id, source_id, feedback_type, feedback_value, content_hash
  
source_ratings:       # 源评分缓存（聚合反馈）
  - source_id, total_useful, total_useless, avg_score

# 反馈类型
feedback_values = {
    'useful': 1,      # 有用 +1
    'useless': -1,    # 无用 -1
    'report': -2      # 举报
}

# 核心方法
submit_feedback()              # 提交反馈
get_source_rating()            # 获取源评分
get_recommended_sources()      # 基于反馈的推荐
should_reduce_push_frequency() # 判断是否降低推送频率

# 推送消息带反馈按钮
[👍 有用] [👎 无用]
回调: subscription:feedback:{source_id}:{type}:{hash}
```

#### 运营数据分析 (subscription_manager.py)
```python
# 订阅趋势
get_subscription_trend(days=7)
返回: {daily: [{date, new, lost, net}], total_new, total_lost, net_growth}

# 源健康度排行
get_source_health_ranking(limit=10)
综合指标: 成功率40% + 满意度40% + 订阅热度20%
返回: [{source_id, health_score, success_rate, satisfaction, subscribers}]

# 用户活跃度
get_user_activity_stats()
返回: {total_users, active_users, feedback_rate, avg_subscriptions, activity_distribution}

# 管理后台入口
统计页面 -> [📈 运营数据] 按钮 -> 运营数据分析页面
```

### 6.4 其他性能建议
1. **缓存预热**: 启动时预加载热门源的内容
2. **连接池**: 数据库连接复用
3. **异步IO**: 抓取和推送使用异步操作

---

## 七、文件清单

```
astrbot_plugin_subscription/
├── main.py                     # 插件入口
├── SYSTEM_DESIGN.md            # 本文档
└── handlers/
    ├── __init__.py
    ├── response_builder.py     # 用户界面构建
    ├── session_handler.py      # 会话处理
    └── source_admin.py         # 管理员功能

common/
├── subscription_manager.py     # 订阅管理器
├── subscription_source.py      # 订阅源管理器
├── content_prefetcher.py       # 内容预抓取器
├── push_scheduler.py           # 推送调度器
├── push_formatter.py           # 推送格式化器
├── subscription_privileges.py  # 订阅权益管理
└── feedback.py                 # 反馈系统
```
