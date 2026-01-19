import { useState, useEffect, useCallback } from 'react';
import { useTelegram } from '../hooks/useTelegram';
import { getCheckinStatus, dailyCheckin, CheckinStatus } from '../services/api';
import { CheckinCalendar } from '../components/CheckinCalendar';

export function Home() {
  const { hapticFeedback, showAlert } = useTelegram();
  const [status, setStatus] = useState<CheckinStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkinLoading, setCheckinLoading] = useState(false);
  const [checkinResult, setCheckinResult] = useState<string | null>(null);

  const loadStatus = useCallback(async () => {
    const response = await getCheckinStatus();
    if (response.status === 'ok' && response.data) {
      setStatus(response.data);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const handleCheckin = async () => {
    if (checkinLoading || status?.is_checked_today) return;

    setCheckinLoading(true);
    hapticFeedback('medium');

    const response = await dailyCheckin();
    
    if (response.status === 'ok' && response.data) {
      if (response.data.success) {
        hapticFeedback('heavy');
        setCheckinResult(response.data.message);
        // 刷新状态
        loadStatus();
      } else {
        showAlert(response.data.message);
      }
    } else {
      showAlert(response.message || '签到失败');
    }
    
    setCheckinLoading(false);
  };

  const closeResult = () => {
    setCheckinResult(null);
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
      {/* 签到卡片 */}
      <div className="card mb-4">
        <div className="text-center">
          {/* 连续签到天数 */}
          <div className="mb-4">
            <div className="text-5xl font-bold text-tg-button">
              {status?.current_streak || 0}
            </div>
            <div className="text-sm text-tg-hint mt-1">连续签到天数</div>
          </div>

          {/* 签到按钮 */}
          <button
            onClick={handleCheckin}
            disabled={checkinLoading || status?.is_checked_today}
            className={`w-32 h-32 rounded-full flex flex-col items-center justify-center mx-auto transition-all
              ${status?.is_checked_today 
                ? 'bg-gray-200 dark:bg-gray-700 text-tg-hint' 
                : 'bg-tg-button text-tg-button-text active:scale-95'
              }`}
          >
            {checkinLoading ? (
              <div className="w-8 h-8 border-4 border-white border-t-transparent rounded-full animate-spin" />
            ) : status?.is_checked_today ? (
              <>
                <span className="text-3xl mb-1">✓</span>
                <span className="text-sm">已签到</span>
              </>
            ) : (
              <>
                <span className="text-3xl mb-1">👆</span>
                <span className="text-sm">立即签到</span>
              </>
            )}
          </button>

          {/* 累计签到 */}
          <div className="mt-4 text-sm text-tg-hint">
            累计签到 <span className="text-tg-text font-medium">{status?.total_days || 0}</span> 天
          </div>
        </div>
      </div>

      {/* 日历 */}
      <CheckinCalendar />

      {/* 签到结果弹窗 */}
      {checkinResult && (
        <div 
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          onClick={closeResult}
        >
          <div 
            className="bg-tg-bg rounded-2xl p-6 max-w-sm w-full max-h-[80vh] overflow-y-auto"
            onClick={e => e.stopPropagation()}
          >
            <div className="text-center mb-4">
              <span className="text-5xl">🎉</span>
            </div>
            <div className="whitespace-pre-wrap text-sm text-tg-text">
              {checkinResult}
            </div>
            <button
              onClick={closeResult}
              className="btn-primary w-full mt-4"
            >
              好的
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
