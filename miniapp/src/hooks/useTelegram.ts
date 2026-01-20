import { useEffect, useState, useCallback } from 'react';
import WebApp from '@twa-dev/sdk';

export interface TelegramUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  is_premium?: boolean;
  photo_url?: string;
}

// 检测是否在 Telegram 环境中运行
export function isTelegramEnvironment(): boolean {
  // 检查 Telegram WebApp 对象是否存在且有有效数据
  try {
    // 检查 window.Telegram 对象
    if (typeof window !== 'undefined' && (window as any).Telegram?.WebApp) {
      const tgWebApp = (window as any).Telegram.WebApp;
      // 检查是否有 initData（只有真实 Telegram 环境才有）
      if (tgWebApp.initData && tgWebApp.initData.length > 0) {
        return true;
      }
      // 检查是否有用户信息
      if (tgWebApp.initDataUnsafe?.user?.id) {
        return true;
      }
    }
    return false;
  } catch {
    return false;
  }
}

export function useTelegram() {
  const [isReady, setIsReady] = useState(false);
  const [initData, setInitData] = useState('');
  const [user, setUser] = useState<TelegramUser | null>(null);
  const [isTelegram, setIsTelegram] = useState<boolean | null>(null); // null = 检测中

  useEffect(() => {
    // 检测是否在 Telegram 环境
    const inTelegram = isTelegramEnvironment();
    setIsTelegram(inTelegram);

    if (!inTelegram) {
      // 不在 Telegram 环境，不初始化 SDK
      setIsReady(true);
      return;
    }

    // 初始化 Telegram Web App
    WebApp.ready();
    WebApp.expand();
    
    setInitData(WebApp.initData);
    setUser(WebApp.initDataUnsafe.user as TelegramUser || null);
    setIsReady(true);

    // 设置主题
    document.body.style.backgroundColor = WebApp.backgroundColor;
  }, []);

  // 显示主按钮
  const showMainButton = useCallback((text: string, onClick: () => void) => {
    WebApp.MainButton.setText(text);
    WebApp.MainButton.onClick(onClick);
    WebApp.MainButton.show();
  }, []);

  // 隐藏主按钮
  const hideMainButton = useCallback(() => {
    WebApp.MainButton.hide();
  }, []);

  // 显示返回按钮
  const showBackButton = useCallback((onClick: () => void) => {
    WebApp.BackButton.onClick(onClick);
    WebApp.BackButton.show();
  }, []);

  // 隐藏返回按钮
  const hideBackButton = useCallback(() => {
    WebApp.BackButton.hide();
  }, []);

  // 触发震动反馈
  const hapticFeedback = useCallback((type: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft' = 'medium') => {
    WebApp.HapticFeedback.impactOccurred(type);
  }, []);

  // 显示确认弹窗
  const showConfirm = useCallback((message: string): Promise<boolean> => {
    return new Promise((resolve) => {
      WebApp.showConfirm(message, (confirmed) => {
        resolve(confirmed);
      });
    });
  }, []);

  // 显示提示弹窗
  const showAlert = useCallback((message: string): Promise<void> => {
    return new Promise((resolve) => {
      WebApp.showAlert(message, () => {
        resolve();
      });
    });
  }, []);

  // 关闭 Mini App
  const close = useCallback(() => {
    WebApp.close();
  }, []);

  return {
    isReady,
    isTelegram,
    initData,
    user,
    webApp: WebApp,
    showMainButton,
    hideMainButton,
    showBackButton,
    hideBackButton,
    hapticFeedback,
    showConfirm,
    showAlert,
    close,
  };
}
