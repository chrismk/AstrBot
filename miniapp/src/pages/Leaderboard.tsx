import { useState, useEffect } from 'react';
import { getLeaderboard, LeaderboardItem } from '../services/api';

type RankType = 'streak' | 'total' | 'points';

const rankTypeLabels: Record<RankType, { label: string; unit: string }> = {
  streak: { label: '连续签到', unit: '天' },
  total: { label: '累计签到', unit: '天' },
  points: { label: '积分榜', unit: '分' },
};

export function Leaderboard() {
  const [rankType, setRankType] = useState<RankType>('streak');
  const [leaderboard, setLeaderboard] = useState<LeaderboardItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadLeaderboard();
  }, [rankType]);

  const loadLeaderboard = async () => {
    setLoading(true);
    const response = await getLeaderboard(rankType, 50);
    if (response.status === 'ok' && response.data) {
      setLeaderboard(response.data.leaderboard);
    }
    setLoading(false);
  };

  const getRankIcon = (rank: number): string => {
    switch (rank) {
      case 1: return '🥇';
      case 2: return '🥈';
      case 3: return '🥉';
      default: return `${rank}`;
    }
  };

  const getRankColor = (rank: number): string => {
    switch (rank) {
      case 1: return 'text-yellow-500';
      case 2: return 'text-gray-400';
      case 3: return 'text-amber-600';
      default: return 'text-tg-hint';
    }
  };

  return (
    <div className="p-4 pb-20">
      {/* 标签切换 */}
      <div className="flex gap-2 mb-4">
        {(Object.keys(rankTypeLabels) as RankType[]).map((type) => (
          <button
            key={type}
            onClick={() => setRankType(type)}
            className={`flex-1 py-2 px-3 rounded-lg text-sm font-medium transition-colors
              ${rankType === type 
                ? 'bg-tg-button text-tg-button-text' 
                : 'bg-tg-secondary-bg text-tg-text'
              }`}
          >
            {rankTypeLabels[type].label}
          </button>
        ))}
      </div>

      {/* 排行榜列表 */}
      <div className="card">
        {loading ? (
          <div className="flex items-center justify-center h-48">
            <div className="w-6 h-6 border-2 border-tg-button border-t-transparent rounded-full animate-spin" />
          </div>
        ) : leaderboard.length === 0 ? (
          <div className="text-center py-12 text-tg-hint">
            暂无数据
          </div>
        ) : (
          <div className="space-y-3">
            {leaderboard.map((item) => (
              <div
                key={item.user_id}
                className={`flex items-center gap-3 p-3 rounded-lg
                  ${item.rank <= 3 ? 'bg-tg-button/5' : ''}`}
              >
                {/* 排名 */}
                <div className={`w-8 text-center font-bold ${getRankColor(item.rank)}`}>
                  {getRankIcon(item.rank)}
                </div>

                {/* 用户信息 */}
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate">
                    {item.username}
                  </div>
                </div>

                {/* 数值 */}
                <div className="text-right">
                  <span className="font-bold text-tg-button">{item.value}</span>
                  <span className="text-xs text-tg-hint ml-1">
                    {rankTypeLabels[rankType].unit}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
