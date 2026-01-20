import { useState, useEffect } from 'react';
import { useTelegram } from '../hooks/useTelegram';
import { getUserProfile, UserProfile } from '../services/api';

export function Profile() {
  const { user } = useTelegram();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    const response = await getUserProfile();
    if (response.status === 'ok' && response.data) {
      setProfile(response.data);
    }
    setLoading(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-8 h-8 border-4 border-tg-button border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-4 pb-20">
      {/* 用户信息卡片 */}
      <div className="card mb-4">
        <div className="flex items-center gap-4">
          {/* 头像 */}
          <div className="w-16 h-16 rounded-full bg-tg-button flex items-center justify-center text-2xl text-tg-button-text">
            {user?.first_name?.charAt(0) || '👤'}
          </div>

          {/* 用户名 */}
          <div className="flex-1 min-w-0">
            <div className="text-lg font-bold truncate">
              {user?.first_name} {user?.last_name || ''}
            </div>
            {user?.username && (
              <div className="text-sm text-tg-hint">@{user.username}</div>
            )}
          </div>
        </div>
      </div>

      {/* 积分卡片 */}
      <div className="card mb-4">
        <div className="text-sm text-tg-hint mb-2">💰 我的积分</div>
        <div className="text-3xl font-bold text-tg-button">
          {profile?.points?.balance || 0}
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <div>
            <div className="text-xs text-tg-hint">累计获得</div>
            <div className="text-lg font-medium text-green-500">
              +{profile?.points?.total_earned || 0}
            </div>
          </div>
          <div>
            <div className="text-xs text-tg-hint">累计消费</div>
            <div className="text-lg font-medium text-red-500">
              -{profile?.points?.total_spent || 0}
            </div>
          </div>
        </div>
      </div>

      {/* 签到统计卡片 */}
      <div className="card mb-4">
        <div className="text-sm text-tg-hint mb-3">📊 签到统计</div>
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center">
            <div className="text-2xl font-bold text-tg-button">
              {profile?.checkin_stats?.total_days || 0}
            </div>
            <div className="text-xs text-tg-hint mt-1">累计签到</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-tg-button">
              {profile?.checkin_stats?.current_streak || 0}
            </div>
            <div className="text-xs text-tg-hint mt-1">连续签到</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-tg-button">
              {profile?.checkin_stats?.max_streak || 0}
            </div>
            <div className="text-xs text-tg-hint mt-1">最长连续</div>
          </div>
        </div>
      </div>

      {/* 功能入口 */}
      <div className="card">
        <div className="text-sm text-tg-hint mb-3">🔧 更多功能</div>
        <div className="space-y-2">
          <a href="/miniapp/search" className="flex items-center justify-between p-3 bg-tg-bg rounded-lg active:bg-gray-100 dark:active:bg-gray-800">
            <span>📚 书籍搜索</span>
            <span className="text-tg-hint text-sm">→</span>
          </a>
          <a href="/miniapp/search" className="flex items-center justify-between p-3 bg-tg-bg rounded-lg active:bg-gray-100 dark:active:bg-gray-800">
            <span>🎵 音乐搜索</span>
            <span className="text-tg-hint text-sm">→</span>
          </a>
          <a href="/miniapp/search" className="flex items-center justify-between p-3 bg-tg-bg rounded-lg active:bg-gray-100 dark:active:bg-gray-800">
            <span>⭐ 豆瓣评分</span>
            <span className="text-tg-hint text-sm">→</span>
          </a>
          <a href="/miniapp/search" className="flex items-center justify-between p-3 bg-tg-bg rounded-lg active:bg-gray-100 dark:active:bg-gray-800">
            <span>📁 网盘搜索</span>
            <span className="text-tg-hint text-sm">→</span>
          </a>
          <a href="/miniapp/leaderboard" className="flex items-center justify-between p-3 bg-tg-bg rounded-lg active:bg-gray-100 dark:active:bg-gray-800">
            <span>🏆 排行榜</span>
            <span className="text-tg-hint text-sm">→</span>
          </a>
          <a href="/miniapp/shop" className="flex items-center justify-between p-3 bg-tg-bg rounded-lg active:bg-gray-100 dark:active:bg-gray-800">
            <span>🛍 积分商城</span>
            <span className="text-tg-hint text-sm">→</span>
          </a>
        </div>
      </div>
    </div>
  );
}
