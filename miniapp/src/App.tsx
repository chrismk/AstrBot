import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { useAuth } from './hooks/useAuth';
import { useTelegram } from './hooks/useTelegram';
import { BottomNav } from './components/BottomNav';
import { Loading } from './components/Loading';
import { Home } from './pages/Home';
import { Leaderboard } from './pages/Leaderboard';
import { Profile } from './pages/Profile';
import { Tasks } from './pages/Tasks';
import { Shop } from './pages/Shop';
import { Subscriptions } from './pages/Subscriptions';
import { Search } from './pages/Search';

// 非 Telegram 环境提示页面
function NotTelegramPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-6 text-center bg-gradient-to-b from-blue-50 to-white dark:from-gray-900 dark:to-gray-800">
      <div className="text-6xl mb-6">🤖</div>
      <div className="text-2xl font-bold mb-3 text-gray-800 dark:text-white">
        AstrBot Mini App
      </div>
      <div className="text-gray-600 dark:text-gray-300 mb-8 max-w-sm">
        请通过 Telegram 打开此应用
      </div>
      
      <div className="bg-white dark:bg-gray-700 rounded-2xl p-6 shadow-lg max-w-sm w-full">
        <div className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          访问方式
        </div>
        <ol className="text-left space-y-3 text-sm text-gray-700 dark:text-gray-200">
          <li className="flex items-start gap-2">
            <span className="bg-blue-500 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs flex-shrink-0">1</span>
            <span>打开 Telegram 应用</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="bg-blue-500 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs flex-shrink-0">2</span>
            <span>搜索并打开 AstrBot</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="bg-blue-500 text-white rounded-full w-5 h-5 flex items-center justify-center text-xs flex-shrink-0">3</span>
            <span>点击菜单中的 "Mini App" 按钮</span>
          </li>
        </ol>
      </div>
      
      <div className="mt-8 text-xs text-gray-400 dark:text-gray-500">
        此应用仅支持在 Telegram 内使用
      </div>
    </div>
  );
}

function AppContent() {
  const { isTelegram } = useTelegram();
  const { isAuthenticated, isLoading, error } = useAuth();

  // 检测中
  if (isTelegram === null) {
    return <Loading message="正在初始化..." />;
  }

  // 非 Telegram 环境
  if (isTelegram === false) {
    return <NotTelegramPage />;
  }

  if (isLoading) {
    return <Loading message="正在验证身份..." />;
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen p-4 text-center">
        <div className="text-4xl mb-4">😔</div>
        <div className="text-lg font-medium mb-2">认证失败</div>
        <div className="text-sm text-tg-hint">{error}</div>
        <div className="mt-4 text-xs text-tg-hint">
          请确保通过 Telegram 打开此应用
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Loading message="正在连接服务器..." />;
  }

  return (
    <div className="min-h-screen bg-tg-bg">
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/leaderboard" element={<Leaderboard />} />
        <Route path="/shop" element={<Shop />} />
        <Route path="/subscriptions" element={<Subscriptions />} />
        <Route path="/search" element={<Search />} />
        <Route path="/profile" element={<Profile />} />
      </Routes>
      <BottomNav />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter basename="/miniapp">
      <AppContent />
    </BrowserRouter>
  );
}
