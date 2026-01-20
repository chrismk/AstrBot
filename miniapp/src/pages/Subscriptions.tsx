import { useState, useEffect, useCallback } from 'react';
import { useTelegram } from '../hooks/useTelegram';
import {
  getSubscriptions,
  getSubscriptionSources,
  subscribeSource,
  unsubscribe,
  SubscriptionItem,
  SourceCategory,
  SourceItem,
} from '../services/api';

type Tab = 'my' | 'discover';

export function Subscriptions() {
  const { hapticFeedback, showAlert, showConfirm } = useTelegram();
  const [tab, setTab] = useState<Tab>('my');
  const [mySubscriptions, setMySubscriptions] = useState<SubscriptionItem[]>([]);
  const [sourceCategories, setSourceCategories] = useState<SourceCategory[]>([]);
  const [loading, setLoading] = useState(true);
  const [operating, setOperating] = useState<number | null>(null);

  const loadMySubscriptions = useCallback(async () => {
    const response = await getSubscriptions();
    if (response.status === 'ok' && response.data) {
      setMySubscriptions(response.data.subscriptions);
    }
  }, []);

  const loadSources = useCallback(async () => {
    const response = await getSubscriptionSources();
    if (response.status === 'ok' && response.data) {
      setSourceCategories(response.data.categories);
    }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    await Promise.all([loadMySubscriptions(), loadSources()]);
    setLoading(false);
  }, [loadMySubscriptions, loadSources]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSubscribe = async (source: SourceItem) => {
    if (operating || source.is_subscribed) return;

    setOperating(source.id);
    hapticFeedback('medium');

    const response = await subscribeSource(source.id);
    
    if (response.status === 'ok' && response.data) {
      if (response.data.success) {
        hapticFeedback('heavy');
        showAlert(response.data.message);
        loadData();
      } else {
        showAlert(response.data.message);
      }
    } else {
      showAlert(response.message || '订阅失败');
    }
    
    setOperating(null);
  };

  const handleUnsubscribe = async (sub: SubscriptionItem) => {
    if (operating) return;

    const confirmed = await showConfirm(
      `确认取消订阅「${sub.source?.name || sub.target}」？`
    );
    if (!confirmed) return;

    setOperating(sub.id);
    hapticFeedback('medium');

    const response = await unsubscribe(sub.id);
    
    if (response.status === 'ok' && response.data) {
      if (response.data.success) {
        hapticFeedback('medium');
        showAlert(response.data.message);
        loadData();
      } else {
        showAlert(response.data.message);
      }
    } else {
      showAlert(response.message || '取消失败');
    }
    
    setOperating(null);
  };

  const renderMySubscription = (sub: SubscriptionItem) => {
    return (
      <div 
        key={sub.id}
        className="flex items-center gap-3 p-3 bg-tg-secondary-bg rounded-xl"
      >
        <div className="text-2xl">{sub.source?.icon || '📰'}</div>
        <div className="flex-1 min-w-0">
          <div className="font-medium text-tg-text truncate">
            {sub.source?.name || sub.target || '未知订阅'}
          </div>
          <div className="text-xs text-tg-hint mt-0.5">
            每日 {sub.push_time} 推送
          </div>
        </div>
        <button
          onClick={() => handleUnsubscribe(sub)}
          disabled={operating === sub.id}
          className="px-3 py-1.5 text-sm text-red-500 bg-red-50 dark:bg-red-900/20 rounded-lg"
        >
          {operating === sub.id ? '...' : '取消'}
        </button>
      </div>
    );
  };

  const renderSourceItem = (source: SourceItem) => {
    return (
      <div 
        key={source.id}
        className="flex items-center gap-3 p-3 bg-tg-secondary-bg rounded-xl"
      >
        <div className="text-2xl">{source.icon}</div>
        <div className="flex-1 min-w-0">
          <div className="font-medium text-tg-text truncate">{source.name}</div>
          {source.description && (
            <div className="text-xs text-tg-hint mt-0.5 line-clamp-1">
              {source.description}
            </div>
          )}
          <div className="text-xs text-tg-hint mt-0.5">
            {source.subscribers} 人订阅
          </div>
        </div>
        <button
          onClick={() => handleSubscribe(source)}
          disabled={operating === source.id || source.is_subscribed}
          className={`px-3 py-1.5 text-sm rounded-lg transition-all ${
            source.is_subscribed
              ? 'bg-gray-100 dark:bg-gray-800 text-tg-hint'
              : 'bg-tg-button text-tg-button-text active:scale-95'
          }`}
        >
          {operating === source.id ? '...' : source.is_subscribed ? '已订阅' : '订阅'}
        </button>
      </div>
    );
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
      {/* Tab 切换 */}
      <div className="flex gap-2 mb-4">
        <button
          onClick={() => setTab('my')}
          className={`flex-1 py-2 rounded-xl text-sm font-medium transition-all ${
            tab === 'my'
              ? 'bg-tg-button text-tg-button-text'
              : 'bg-tg-secondary-bg text-tg-hint'
          }`}
        >
          我的订阅
        </button>
        <button
          onClick={() => setTab('discover')}
          className={`flex-1 py-2 rounded-xl text-sm font-medium transition-all ${
            tab === 'discover'
              ? 'bg-tg-button text-tg-button-text'
              : 'bg-tg-secondary-bg text-tg-hint'
          }`}
        >
          发现
        </button>
      </div>

      {/* 我的订阅 */}
      {tab === 'my' && (
        <div>
          {mySubscriptions.length > 0 ? (
            <div className="space-y-2">
              {mySubscriptions.map(renderMySubscription)}
            </div>
          ) : (
            <div className="text-center py-12">
              <div className="text-4xl mb-3">📭</div>
              <div className="text-tg-hint">暂无订阅</div>
              <button
                onClick={() => setTab('discover')}
                className="mt-4 px-4 py-2 bg-tg-button text-tg-button-text rounded-xl text-sm"
              >
                去发现
              </button>
            </div>
          )}
        </div>
      )}

      {/* 发现订阅源 */}
      {tab === 'discover' && (
        <div className="space-y-4">
          {sourceCategories.length > 0 ? (
            sourceCategories.map((category) => (
              <div key={category.name}>
                <div className="text-sm font-medium text-tg-hint mb-2">
                  {category.name}
                </div>
                <div className="space-y-2">
                  {category.sources.map(renderSourceItem)}
                </div>
              </div>
            ))
          ) : (
            <div className="text-center text-tg-hint py-8">
              暂无可用订阅源
            </div>
          )}
        </div>
      )}
    </div>
  );
}
