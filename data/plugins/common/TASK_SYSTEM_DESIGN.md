# 📋 任务系统设计方案

## 一、系统概述

### 1.1 设计目标
- 统一的任务管理框架，支持每日/每周/每月任务
- 与现有系统无缝集成（积分、签到、搜索统计、订阅）
- 插件可扩展，各插件可注册自己的任务
- 自动进度追踪和奖励发放

### 1.2 现有系统集成点

| 系统 | 模块 | 可追踪行为 |
|------|------|-----------|
| 签到系统 | `CheckinManager` | 每日签到、连续签到 |
| 搜索统计 | `SearchStatistics` | 搜索次数、下载次数 |
| 订阅系统 | `SubscriptionManager` | 订阅数量、反馈次数 |
| 积分系统 | `PointsManager` | 积分变动、兑换次数 |
| 定时调度 | `PluginScheduler` | 任务重置、定时检查 |

---

## 二、架构设计

### 2.1 模块结构

```
common/
├── task_manager.py          # 核心任务管理器
├── task_definitions.py      # 任务定义和配置
└── task_tracker.py          # 进度追踪器（事件监听）

astrbot_plugin_task/         # 任务系统插件
├── main.py                  # 插件入口
├── handlers/
│   ├── task_handler.py      # 任务交互处理
│   └── response_builder.py  # 响应构建
└── metadata.yaml
```

### 2.2 核心类设计

```python
# 任务类型枚举
class TaskType(Enum):
    DAILY = "daily"       # 每日任务
    WEEKLY = "weekly"     # 每周任务
    MONTHLY = "monthly"   # 每月任务

# 任务触发类型
class TaskTrigger(Enum):
    CHECKIN = "checkin"           # 签到
    SEARCH = "search"             # 搜索
    DOWNLOAD = "download"         # 下载
    SUBSCRIBE = "subscribe"       # 订阅
    FEEDBACK = "feedback"         # 反馈
    CHAT = "chat"                 # 群聊发言
    CUSTOM = "custom"             # 自定义

# 任务定义
@dataclass
class TaskDefinition:
    task_id: str                  # 任务ID
    name: str                     # 任务名称
    description: str              # 任务描述
    task_type: TaskType           # 任务类型
    trigger: TaskTrigger          # 触发类型
    target: int                   # 目标值
    reward_points: int            # 奖励积分
    icon: str = "📋"              # 图标
    enabled: bool = True          # 是否启用
    plugin_name: str = None       # 所属插件（可选）
    extra_config: Dict = None     # 额外配置

# 用户任务进度
@dataclass
class UserTaskProgress:
    user_id: str
    task_id: str
    progress: int = 0             # 当前进度
    target: int = 0               # 目标值
    completed: bool = False       # 是否完成
    reward_claimed: bool = False  # 是否已领取奖励
    completed_at: datetime = None # 完成时间
    period_start: datetime = None # 周期开始时间
```

---

## 三、数据库设计

### 3.1 任务配置表 `task_definitions`

```sql
CREATE TABLE IF NOT EXISTS task_definitions (
    task_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    task_type TEXT NOT NULL,        -- daily/weekly/monthly
    trigger_type TEXT NOT NULL,     -- checkin/search/download/subscribe/feedback/chat
    target INTEGER NOT NULL,        -- 目标值
    reward_points INTEGER NOT NULL, -- 奖励积分
    icon TEXT DEFAULT '📋',
    plugin_name TEXT,               -- 所属插件
    extra_config TEXT,              -- JSON配置
    enabled INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 3.2 用户任务进度表 `user_task_progress`

```sql
CREATE TABLE IF NOT EXISTS user_task_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    progress INTEGER DEFAULT 0,
    target INTEGER NOT NULL,
    completed INTEGER DEFAULT 0,
    reward_claimed INTEGER DEFAULT 0,
    completed_at DATETIME,
    period_start DATETIME NOT NULL,  -- 周期开始时间
    period_end DATETIME NOT NULL,    -- 周期结束时间
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, task_id, period_start)
);

-- 索引
CREATE INDEX idx_user_task_user ON user_task_progress(user_id);
CREATE INDEX idx_user_task_period ON user_task_progress(period_start, period_end);
CREATE INDEX idx_user_task_completed ON user_task_progress(user_id, completed, reward_claimed);
```

### 3.3 任务完成日志表 `task_completion_logs`

```sql
CREATE TABLE IF NOT EXISTS task_completion_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    task_type TEXT NOT NULL,
    reward_points INTEGER NOT NULL,
    completed_at DATETIME NOT NULL,
    period_start DATETIME NOT NULL
);

CREATE INDEX idx_task_log_user ON task_completion_logs(user_id, completed_at);
```

---

## 四、默认任务配置

### 4.1 每日任务

| 任务ID | 名称 | 触发 | 目标 | 奖励 |
|--------|------|------|------|------|
| `daily_checkin` | 每日签到 | checkin | 1 | 10 |
| `daily_search_3` | 搜索3次 | search | 3 | 20 |
| `daily_view_ranking` | 查看热搜榜 | custom | 1 | 15 |
| `daily_subscribe` | 订阅1个内容 | subscribe | 1 | 10 |
| `daily_all_complete` | 全部完成 | custom | 4 | 50 |

### 4.2 每周任务

| 任务ID | 名称 | 触发 | 目标 | 奖励 |
|--------|------|------|------|------|
| `weekly_streak_7` | 连续签到7天 | checkin | 7 | 100 |
| `weekly_search_20` | 累计搜索20次 | search | 20 | 50 |
| `weekly_subscribe_3` | 订阅3个榜单 | subscribe | 3 | 30 |
| `weekly_feedback_5` | 反馈5次 | feedback | 5 | 40 |

### 4.3 每月任务

| 任务ID | 名称 | 触发 | 目标 | 奖励 |
|--------|------|------|------|------|
| `monthly_full_checkin` | 本月全勤 | checkin | 30 | 500 |
| `monthly_search_100` | 累计搜索100次 | search | 100 | 200 |
| `monthly_subscribe_10` | 订阅10个内容 | subscribe | 10 | 150 |
| `monthly_all_weekly` | 完成所有周任务 | custom | 4 | 300 |

---

## 五、核心实现

### 5.1 TaskManager 核心方法

```python
class TaskManager:
    """任务管理器"""
    
    def __init__(self, db: DatabaseManager, points_manager: PointsManager):
        self.db = db
        self.points_manager = points_manager
        self._init_tables()
        self._load_default_tasks()
    
    # ========== 任务定义管理 ==========
    
    def register_task(self, task: TaskDefinition) -> bool:
        """注册任务（插件可调用）"""
        
    def get_task(self, task_id: str) -> Optional[TaskDefinition]:
        """获取任务定义"""
        
    def get_tasks_by_type(self, task_type: TaskType) -> List[TaskDefinition]:
        """按类型获取任务列表"""
    
    # ========== 进度管理 ==========
    
    def get_user_tasks(self, user_id: str, task_type: TaskType = None) -> List[UserTaskProgress]:
        """获取用户任务列表（含进度）"""
        
    def update_progress(self, user_id: str, trigger: TaskTrigger, increment: int = 1, **kwargs) -> List[str]:
        """
        更新任务进度（核心方法）
        
        Args:
            user_id: 用户ID
            trigger: 触发类型
            increment: 增量
            **kwargs: 额外参数（如 plugin_name）
            
        Returns:
            完成的任务ID列表
        """
        
    def claim_reward(self, user_id: str, task_id: str) -> Tuple[bool, str]:
        """领取任务奖励"""
        
    def claim_all_rewards(self, user_id: str) -> Tuple[int, int]:
        """一键领取所有奖励，返回(任务数, 积分数)"""
    
    # ========== 周期管理 ==========
    
    def reset_daily_tasks(self):
        """重置每日任务（定时任务调用）"""
        
    def reset_weekly_tasks(self):
        """重置每周任务（每周一0点）"""
        
    def reset_monthly_tasks(self):
        """重置每月任务（每月1号0点）"""
    
    # ========== 统计查询 ==========
    
    def get_completion_stats(self, user_id: str) -> Dict:
        """获取用户任务完成统计"""
        
    def get_leaderboard(self, task_type: TaskType, limit: int = 10) -> List[Dict]:
        """获取任务完成排行榜"""
```

### 5.2 TaskTracker 事件追踪器

```python
class TaskTracker:
    """
    任务进度追踪器
    
    各插件在关键操作后调用，自动更新任务进度
    """
    
    _instance = None
    
    @classmethod
    def get_instance(cls) -> 'TaskTracker':
        """获取单例"""
        
    def track(self, user_id: str, trigger: TaskTrigger, increment: int = 1, **kwargs):
        """
        追踪用户行为
        
        使用示例：
            # 在签到插件中
            TaskTracker.get_instance().track(user_id, TaskTrigger.CHECKIN)
            
            # 在搜索插件中
            TaskTracker.get_instance().track(user_id, TaskTrigger.SEARCH, plugin_name='music')
            
            # 在订阅插件中
            TaskTracker.get_instance().track(user_id, TaskTrigger.SUBSCRIBE)
        """
        
    async def on_task_completed(self, user_id: str, task: TaskDefinition):
        """任务完成回调（可推送通知）"""
```

---

## 六、插件集成指南

### 6.1 在现有插件中集成

```python
# 在 checkin 插件中
from common.task_tracker import TaskTracker, TaskTrigger

class CheckinManager:
    async def daily_checkin(self, user_id: str):
        # ... 签到逻辑 ...
        
        # 追踪签到行为
        TaskTracker.get_instance().track(user_id, TaskTrigger.CHECKIN)
        
        return result

# 在 music 插件中
async def search(self, event, keyword):
    # ... 搜索逻辑 ...
    
    # 追踪搜索行为
    TaskTracker.get_instance().track(
        user_id, 
        TaskTrigger.SEARCH, 
        plugin_name='music'
    )

# 在 subscription 插件中
def subscribe(self, user_id: str, source_id: int):
    # ... 订阅逻辑 ...
    
    # 追踪订阅行为
    TaskTracker.get_instance().track(user_id, TaskTrigger.SUBSCRIBE)
```

### 6.2 插件注册自定义任务

```python
# 在插件初始化时
from common.task_manager import get_task_manager, TaskDefinition, TaskType, TaskTrigger

def on_plugin_loaded(self):
    task_manager = get_task_manager()
    
    # 注册插件专属任务
    task_manager.register_task(TaskDefinition(
        task_id="music_download_5",
        name="下载5首音乐",
        description="今日下载5首音乐",
        task_type=TaskType.DAILY,
        trigger=TaskTrigger.DOWNLOAD,
        target=5,
        reward_points=30,
        icon="🎵",
        plugin_name="music"
    ))
```

---

## 七、用户交互设计

### 7.1 命令设计

| 命令 | 说明 |
|------|------|
| `/任务` 或 `/task` | 查看任务列表 |
| `/任务 每日` | 查看每日任务 |
| `/任务 每周` | 查看每周任务 |
| `/任务 领取` | 一键领取所有奖励 |

### 7.2 任务列表展示

```
📋 每日任务 (3/5 已完成)

✅ 每日签到 [1/1] +10积分 ✓已领取
✅ 搜索3次 [3/3] +20积分 [领取]
⬜ 查看热搜榜 [0/1] +15积分
⬜ 订阅1个内容 [0/1] +10积分
⬜ 全部完成 [3/5] +50积分

━━━━━━━━━━━━━━━━━━
💰 可领取: 20积分
📊 本周完成: 12个任务

[每日] [每周] [每月] [一键领取]
```

### 7.3 任务完成通知

```
🎉 任务完成！

📋 搜索3次
🎁 奖励: +20积分

💡 还有2个每日任务未完成
```

---

## 八、定时任务配置

```python
# 在 scheduler 中注册
from common import get_scheduler

scheduler = get_scheduler()

# 每日任务重置（每天0点）
scheduler.register_task(
    task_id="task_daily_reset",
    plugin_name="task",
    cron="0 0 * * *",
    handler=task_manager.reset_daily_tasks,
    description="重置每日任务"
)

# 每周任务重置（每周一0点）
scheduler.register_task(
    task_id="task_weekly_reset",
    plugin_name="task",
    cron="0 0 * * 1",
    handler=task_manager.reset_weekly_tasks,
    description="重置每周任务"
)

# 每月任务重置（每月1号0点）
scheduler.register_task(
    task_id="task_monthly_reset",
    plugin_name="task",
    cron="0 0 1 * *",
    handler=task_manager.reset_monthly_tasks,
    description="重置每月任务"
)
```

---

## 九、防作弊机制

### 9.1 进度更新限制

```python
def update_progress(self, user_id: str, trigger: TaskTrigger, increment: int = 1):
    # 1. 检查是否在有效周期内
    if not self._is_valid_period(task):
        return []
    
    # 2. 检查是否已完成（防止重复计数）
    if progress.completed:
        return []
    
    # 3. 检查增量合理性（单次最大增量）
    max_increment = self._get_max_increment(trigger)
    increment = min(increment, max_increment)
    
    # 4. 频率限制（同一触发类型的最小间隔）
    if not self._check_rate_limit(user_id, trigger):
        return []
    
    # 更新进度...
```

### 9.2 奖励发放验证

```python
def claim_reward(self, user_id: str, task_id: str):
    # 1. 验证任务确实完成
    if not progress.completed:
        return False, "任务未完成"
    
    # 2. 验证未重复领取
    if progress.reward_claimed:
        return False, "奖励已领取"
    
    # 3. 验证在有效周期内
    if not self._is_valid_period(progress):
        return False, "任务已过期"
    
    # 4. 发放奖励并记录
    self.points_manager.add_points(user_id, reward, "task_reward", task_id)
    
    return True, f"获得 {reward} 积分"
```

---

## 十、实现优先级

### Phase 1: 核心框架 ✅ 已完成
- [x] 数据库表设计
- [x] `TaskManager` 核心类 (`common/task_manager.py`)
- [x] `TaskTracker` 追踪器 (`common/task_tracker.py`)
- [x] 默认任务配置
- [x] 导出到 `common/__init__.py`

### Phase 2: 插件集成 ✅ 已完成
- [x] 签到插件集成 (`checkin_manager.py`)
- [x] 搜索统计集成 (`search_statistics.py`)
- [x] 订阅系统集成 (`subscription_manager.py`)
- [x] 反馈系统集成 (`subscription_manager.py`)

### Phase 3: 用户交互 ✅ 已完成
- [x] 任务系统插件 (`astrbot_plugin_task/main.py`)
- [x] 任务列表展示（每日/每周/每月）
- [x] 奖励领取（单个/一键领取）
- [x] 任务统计和排行榜

### Phase 4: 邀请系统 ✅ 已完成
- [x] 邀请管理器 (`common/invite_manager.py`)
- [x] 一次性任务类型 (`TaskType.ONETIME`)
- [x] 邀请触发器 (`TaskTrigger.INVITE`, `BIND_INVITE`)
- [x] 深度链接支持 (Telegram: `https://t.me/{bot}?start=inv_{code}`)
- [x] 邀请码绑定命令 (`/绑定邀请`)
- [x] 整合到 `/我` 命令

### Phase 5: 定时任务 ✅ 已完成
- [x] 每日任务重置 (每天 0:05)
- [x] 每周任务重置 (每周一 0:10)
- [x] 每月任务重置 (每月1号 0:15)
- [x] 过期日志清理 (每周日 3:00，保留90天)

---

## 十一、邀请系统设计

### 11.1 邀请方式

| 方式 | 适用平台 | 格式 |
|------|----------|------|
| 深度链接 | Telegram | `https://t.me/{bot}?start=inv_{code}` |
| 邀请码 | 全平台 | `/绑定邀请 {code}` |

### 11.2 奖励配置

```python
InviteReward(
    inviter_points=50,      # 邀请人获得积分
    invitee_points=30,      # 被邀请人获得积分
    max_daily_invites=10,   # 每日最大邀请数
    max_total_invites=100   # 总最大邀请数
)
```

### 11.3 邀请任务

| 任务ID | 名称 | 目标 | 奖励 |
|--------|------|------|------|
| onetime_bind_invite | 绑定邀请码 | 1 | 30积分 |
| onetime_invite_1 | 邀请1位好友 | 1 | 50积分 |
| onetime_invite_5 | 邀请5位好友 | 5 | 200积分 |
| onetime_invite_10 | 邀请大使 | 10 | 500积分 |

### 11.4 数据库表

```sql
-- 邀请码表
CREATE TABLE invite_codes (
    user_id TEXT UNIQUE,
    invite_code TEXT UNIQUE
);

-- 邀请关系表
CREATE TABLE invite_relations (
    inviter_id TEXT,
    invitee_id TEXT UNIQUE,
    invite_code TEXT,
    status TEXT,  -- pending/rewarded
    inviter_reward INTEGER,
    invitee_reward INTEGER
);

-- 邀请统计表
CREATE TABLE invite_stats (
    user_id TEXT PRIMARY KEY,
    total_invites INTEGER,
    successful_invites INTEGER,
    total_rewards INTEGER
);
```

---

## 十二、文件清单

```
common/
├── task_manager.py          # 任务管理器（~900行）
├── task_tracker.py          # 进度追踪器（~220行）
├── invite_manager.py        # 邀请管理器（~500行）
└── __init__.py              # 模块导出

astrbot_plugin_task/
├── main.py                  # 任务插件（~260行）
└── metadata.yaml

astrbot_plugin_quota_admin/
├── main.py                  # 整合任务/邀请入口
└── handlers/
    └── response_builder.py  # 任务/邀请页面构建
```

实际总代码量：~2000行
