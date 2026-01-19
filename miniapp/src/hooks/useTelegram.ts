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

export function useTelegram() {
  const [isReady, setIsReady] = useState(false);
  const [initData, setInitData] = useState('');
  const [user, setUser] = useState<TelegramUser | null>(null);

  useEffect(() => {
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
