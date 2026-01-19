# AstrBot Telegram Mini App

基于 React + Vite + TypeScript 的 Telegram Mini App，用于访问 AstrBot 的签到、积分等功能。

## 功能特性

- ✅ Telegram 身份认证
- ✅ 每日签到（含幸运签到）
- ✅ 签到日历展示
- ✅ 连续签到统计
- ✅ 排行榜（连续签到/累计签到/积分）
- ✅ 个人中心（积分余额、签到统计）
- 🔜 书籍搜索
- 🔜 音乐搜索
- 🔜 豆瓣评分
- 🔜 网盘搜索

## 技术栈

- React 18 + TypeScript
- Vite 5
- TailwindCSS
- @twa-dev/sdk (Telegram Web App SDK)
- React Router

## 开发

### 安装依赖

```bash
cd miniapp
npm install
```

### 本地开发

```bash
npm run dev
```

开发服务器将在 http://localhost:5173 启动。

> 注意：本地开发时需要 AstrBot 后端运行在 http://localhost:6185

### 构建

```bash
npm run build
```

构建产物将输出到 `dist` 目录。

## 部署

### 方案 A: 集成到 AstrBot Dashboard

1. 构建 Mini App：
   ```bash
   npm run build
   ```

2. 将 `dist` 目录复制到 AstrBot 的 `data/miniapp/` 目录

3. Mini App 将通过 `http://your-server:6185/miniapp/` 访问

### 方案 B: 独立部署

1. 构建后部署到任意静态托管服务（Vercel、Netlify、CDN 等）

2. 配置 CORS（在 AstrBot 后端配置允许的来源域名）

3. 修改 `src/services/api.ts` 中的 `API_BASE` 为完整的后端地址

## Telegram Bot 配置

1. 在 @BotFather 中打开你的 Bot

2. 选择 "Bot Settings" > "Menu Button" > "Configure menu button"

3. 输入 Mini App 的 URL（如 `https://your-domain.com/miniapp/`）

4. 或者使用命令创建 Web App 按钮：
   ```
   /newapp
   ```

## 目录结构

```
miniapp/
├── src/
│   ├── components/      # 通用组件
│   │   ├── BottomNav.tsx
│   │   ├── CheckinCalendar.tsx
│   │   └── Loading.tsx
│   ├── hooks/           # React Hooks
│   │   ├── useAuth.ts
│   │   └── useTelegram.ts
│   ├── pages/           # 页面组件
│   │   ├── Home.tsx
│   │   ├── Leaderboard.tsx
│   │   └── Profile.tsx
│   ├── services/        # API 服务
│   │   └── api.ts
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css
├── index.html
├── package.json
├── vite.config.ts
├── tailwind.config.js
└── tsconfig.json
```

## API 接口

Mini App 通过以下 API 与 AstrBot 后端通信：

| 接口 | 方法 | 说明 |
|-----|------|-----|
| `/api/miniapp/auth` | POST | Telegram 身份验证 |
| `/api/miniapp/user/profile` | GET | 获取用户资料 |
| `/api/miniapp/user/points` | GET | 获取积分信息 |
| `/api/miniapp/checkin/daily` | POST | 每日签到 |
| `/api/miniapp/checkin/status` | GET | 获取签到状态 |
| `/api/miniapp/checkin/calendar` | GET | 获取签到日历 |
| `/api/miniapp/checkin/leaderboard` | GET | 获取排行榜 |
| `/api/miniapp/checkin/makeup` | POST | 补签 |

## 许可证

MIT
