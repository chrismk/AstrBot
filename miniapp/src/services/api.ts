const API_BASE = '/api/miniapp';

// 存储 token
let authToken: string | null = null;

export function setAuthToken(token: string | null) {
  authToken = token;
  if (token) {
    localStorage.setItem('miniapp_token', token);
  } else {
    localStorage.removeItem('miniapp_token');
  }
}

export function getAuthToken(): string | null {
  if (!authToken) {
    authToken = localStorage.getItem('miniapp_token');
  }
  return authToken;
}

// API 响应类型
export interface ApiResponse<T = unknown> {
  status: 'ok' | 'error';
  message?: string;
  data?: T;
}

// 通用请求方法
async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  const token = getAuthToken();
  
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  try {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    const data = await response.json();
    
    if (response.status === 401) {
      // Token 过期或无效
      setAuthToken(null);
    }
    
    return data;
  } catch (error) {
    console.error('API request failed:', error);
    return {
      status: 'error',
      message: '网络请求失败',
    };
  }
}

// ==================== 认证 API ====================

export interface AuthResponse {
  token: string;
  user: {
    tg_user_id: string;
    user_id: string;
    username: string;
    first_name: string;
  };
}

export async function authenticate(initData: string): Promise<ApiResponse<AuthResponse>> {
  return request<AuthResponse>('/auth', {
    method: 'POST',
    body: JSON.stringify({ init_data: initData }),
  });
}

// ==================== 用户 API ====================

export interface UserProfile {
  user_id: string;
  username: string;
  points?: {
    balance: number;
    total_earned: number;
    total_spent: number;
  };
  checkin_stats?: {
    total_days: number;
    current_streak: number;
    max_streak: number;
    last_checkin_date: string | null;
  };
}

export async function getUserProfile(): Promise<ApiResponse<UserProfile>> {
  return request<UserProfile>('/user/profile');
}

export interface PointsInfo {
  balance: number;
  total_earned: number;
  total_spent: number;
}

export async function getUserPoints(): Promise<ApiResponse<PointsInfo>> {
  return request<PointsInfo>('/user/points');
}

// ==================== 签到 API ====================

export interface CheckinResult {
  success: boolean;
  message: string;
}

export async function dailyCheckin(): Promise<ApiResponse<CheckinResult>> {
  return request<CheckinResult>('/checkin/daily', {
    method: 'POST',
  });
}

export interface CheckinStatus {
  is_checked_today: boolean;
  current_streak: number;
  total_days: number;
}

export async function getCheckinStatus(): Promise<ApiResponse<CheckinStatus>> {
  return request<CheckinStatus>('/checkin/status');
}

export interface CalendarRecord {
  date: string;
  points: number;
  is_lucky: boolean;
  streak: number;
}

export interface CalendarData {
  year: number;
  month: number;
  records: CalendarRecord[];
  total_days: number;
}

export async function getCheckinCalendar(month?: string): Promise<ApiResponse<CalendarData>> {
  const query = month ? `?month=${month}` : '';
  return request<CalendarData>(`/checkin/calendar${query}`);
}

export interface LeaderboardItem {
  rank: number;
  user_id: string;
  username: string;
  value: number;
}

export interface LeaderboardData {
  type: string;
  leaderboard: LeaderboardItem[];
}

export async function getLeaderboard(
  type: 'streak' | 'total' | 'points' = 'streak',
  limit: number = 20
): Promise<ApiResponse<LeaderboardData>> {
  return request<LeaderboardData>(`/checkin/leaderboard?type=${type}&limit=${limit}`);
}

export async function makeupCheckin(date: string): Promise<ApiResponse<CheckinResult>> {
  return request<CheckinResult>('/checkin/makeup', {
    method: 'POST',
    body: JSON.stringify({ date }),
  });
}
