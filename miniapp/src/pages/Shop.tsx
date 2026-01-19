import { useState, useEffect, useCallback } from 'react';
import { useTelegram } from '../hooks/useTelegram';
import { getPointsPackages, exchangePackage, PointsPackage, PackagesData } from '../services/api';

export function Shop() {
  const { hapticFeedback, showAlert, showConfirm } = useTelegram();
  const [data, setData] = useState<PackagesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [exchanging, setExchanging] = useState<string | null>(null);

  const loadPackages = useCallback(async () => {
    const response = await getPointsPackages();
    if (response.status === 'ok' && response.data) {
      setData(response.data);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadPackages();
  }, [loadPackages]);

  const handleExchange = async (pkg: PointsPackage) => {
    if (exchanging) return;

    // 检查余额
    if (data && data.balance < pkg.points_cost) {
      showAlert('积分不足');
      return;
    }

    // 确认兑换
    const confirmed = await showConfirm(
      `确认使用 ${pkg.points_cost} 积分兑换「${pkg.name}」？`
    );
    
    if (!confirmed) return;

    setExchanging(pkg.package_id);
    hapticFeedback('medium');

    const response = await exchangePackage(pkg.package_id);
    
    if (response.status === 'ok' && response.data) {
      if (response.data.success) {
        hapticFeedback('heavy');
        showAlert(response.data.message);
        // 更新余额
        if (data) {
          setData({ ...data, balance: response.data.balance });
        }
      } else {
        showAlert(response.data.message);
      }
    } else {
      showAlert(response.message || '兑换失败');
    }
    
    setExchanging(null);
  };

  const renderPackage = (pkg: PointsPackage) => {
    const canAfford = data && data.balance >= pkg.points_cost;

    return (
      <div 
        key={pkg.package_id}
        className="card p-4"
      >
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="font-medium text-tg-text">{pkg.name}</div>
            <div className="text-sm text-tg-hint mt-1">
              有效期：{pkg.days}天
            </div>
          </div>
          <div className="text-right">
            <div className="text-lg font-bold text-tg-button">
              {pkg.points_cost}
            </div>
            <div className="text-xs text-tg-hint">积分</div>
          </div>
        </div>
        
        <button
          onClick={() => handleExchange(pkg)}
          disabled={exchanging === pkg.package_id || !canAfford}
          className={`w-full mt-3 py-2 rounded-xl text-sm font-medium transition-all ${
            canAfford
              ? 'bg-tg-button text-tg-button-text active:scale-95'
              : 'bg-gray-200 dark:bg-gray-700 text-tg-hint'
          }`}
        >
          {exchanging === pkg.package_id ? '兑换中...' : canAfford ? '立即兑换' : '积分不足'}
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
      {/* 积分余额 */}
      <div className="card mb-4 text-center">
        <div className="text-sm text-tg-hint">当前积分</div>
        <div className="text-4xl font-bold text-tg-button mt-2">
          {data?.balance || 0}
        </div>
      </div>

      {/* 配额包列表 */}
      <div className="text-sm text-tg-hint mb-3">配额包</div>
      
      {data?.packages.length ? (
        <div className="space-y-3">
          {data.packages.map(renderPackage)}
        </div>
      ) : (
        <div className="text-center text-tg-hint py-8">
          暂无可兑换的配额包
        </div>
      )}

      {/* 说明 */}
      <div className="mt-6 p-4 bg-tg-secondary-bg rounded-xl">
        <div className="text-sm font-medium text-tg-text mb-2">📋 兑换说明</div>
        <ul className="text-xs text-tg-hint space-y-1">
          <li>• 配额包兑换后立即生效</li>
          <li>• 有效期内可叠加使用</li>
          <li>• 过期后未使用的配额自动失效</li>
          <li>• 积分可通过签到、任务等方式获取</li>
        </ul>
      </div>
    </div>
  );
}
