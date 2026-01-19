import { useState, useEffect, useCallback } from 'react';
import { useTelegram } from './useTelegram';
import { authenticate, setAuthToken, getAuthToken, AuthResponse } from '../services/api';

export interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  user: AuthResponse['user'] | null;
}

export function useAuth() {
  const { isReady, initData } = useTelegram();
  const [authState, setAuthState] = useState<AuthState>({
    isAuthenticated: false,
    isLoading: true,
    error: null,
    user: null,
  });

  const login = useCallback(async () => {
    if (!initData) {
      setAuthState(prev => ({
        ...prev,
        isLoading: false,
        error: '无法获取 Telegram 认证信息',
      }));
      return;
    }

    try {
      const response = await authenticate(initData);
      
      if (response.status === 'ok' && response.data) {
        setAuthToken(response.data.token);
        setAuthState({
          isAuthenticated: true,
          isLoading: false,
          error: null,
          user: response.data.user,
        });
      } else {
        setAuthState(prev => ({
          ...prev,
          isLoading: false,
          error: response.message || '认证失败',
        }));
      }
    } catch (error) {
      console.error('Auth error:', error);
      setAuthState(prev => ({
        ...prev,
        isLoading: false,
        error: '认证请求失败',
      }));
    }
  }, [initData]);

  const logout = useCallback(() => {
    setAuthToken(null);
    setAuthState({
      isAuthenticated: false,
      isLoading: false,
      error: null,
      user: null,
    });
  }, []);

  useEffect(() => {
    if (!isReady) return;

    // 检查是否已有有效 token
    const existingToken = getAuthToken();
    if (existingToken) {
      // 可以在这里验证 token 是否有效
      // 暂时假设有效，后续 API 调用会处理过期情况
      setAuthState(prev => ({
        ...prev,
        isAuthenticated: true,
        isLoading: false,
      }));
    } else {
      // 没有 token，进行认证
      login();
    }
  }, [isReady, login]);

  return {
    ...authState,
    login,
    logout,
  };
}
