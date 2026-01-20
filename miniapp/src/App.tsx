import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { useAuth } from './hooks/useAuth';
import { BottomNav } from './components/BottomNav';
import { Loading } from './components/Loading';
import { Home } from './pages/Home';
import { Leaderboard } from './pages/Leaderboard';
import { Profile } from './pages/Profile';
import { Tasks } from './pages/Tasks';
import { Shop } from './pages/Shop';
import { Subscriptions } from './pages/Subscriptions';
import { Search } from './pages/Search';

function AppContent() {
  const { isAuthenticated, isLoading, error } = useAuth();

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
