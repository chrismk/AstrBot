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

// ==================== 任务系统 API ====================

export interface TaskItem {
  task_id: string;
  name: string;
  description: string;
  icon: string;
  reward_points: number;
  target: number;
  progress: number;
  progress_percent: number;
  completed: boolean;
  reward_claimed: boolean;
  is_claimable: boolean;
  is_bonus: boolean;
}

export interface TasksData {
  type: string;
  tasks: TaskItem[];
  summary: {
    total: number;
    completed: number;
    claimable: number;
    claimable_points: number;
  };
}

export async function getTasks(type: 'daily' | 'weekly' | 'monthly' = 'daily'): Promise<ApiResponse<TasksData>> {
  return request<TasksData>(`/tasks?type=${type}`);
}

export interface ClaimResult {
  success: boolean;
  message: string;
}

export async function claimTask(taskId: string): Promise<ApiResponse<ClaimResult>> {
  return request<ClaimResult>('/tasks/claim', {
    method: 'POST',
    body: JSON.stringify({ task_id: taskId }),
  });
}

export interface ClaimAllResult {
  success: boolean;
  claimed_count: number;
  total_points: number;
  message: string;
}

export async function claimAllTasks(): Promise<ApiResponse<ClaimAllResult>> {
  return request<ClaimAllResult>('/tasks/claim-all', {
    method: 'POST',
  });
}

export interface TaskStats {
  daily: { completed: number; total: number; points: number };
  weekly: { completed: number; total: number; points: number };
  monthly: { completed: number; total: number; points: number };
  total_points_earned: number;
}

export async function getTaskStats(): Promise<ApiResponse<TaskStats>> {
  return request<TaskStats>('/tasks/stats');
}

// ==================== 积分明细与商城 API ====================

export interface PointsRecord {
  amount: number;
  balance_after: number;
  type: string;
  source: string;
  description: string;
  created_at: string;
}

export interface PointsHistoryData {
  records: PointsRecord[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    has_more: boolean;
  };
}

export async function getPointsHistory(page: number = 1, limit: number = 20): Promise<ApiResponse<PointsHistoryData>> {
  return request<PointsHistoryData>(`/points/history?page=${page}&limit=${limit}`);
}

export interface PointsPackage {
  package_id: string;
  name: string;
  points_cost: number;
  boost_amount: number;
  days: number;
  action_type: string | null;
}

export interface PackagesData {
  packages: PointsPackage[];
  balance: number;
}

export async function getPointsPackages(): Promise<ApiResponse<PackagesData>> {
  return request<PackagesData>('/points/packages');
}

export interface ExchangeResult {
  success: boolean;
  message: string;
  balance: number;
}

export async function exchangePackage(packageId: string): Promise<ApiResponse<ExchangeResult>> {
  return request<ExchangeResult>('/points/exchange', {
    method: 'POST',
    body: JSON.stringify({ package_id: packageId }),
  });
}

// ==================== 订阅系统 API ====================

export interface SubscriptionSource {
  id: number;
  name: string;
  icon: string;
  category: string;
}

export interface SubscriptionItem {
  id: number;
  type: string;
  plugin_name: string;
  target: string;
  source: SubscriptionSource | null;
  push_time: string;
  push_frequency: string;
  enabled: boolean;
  created_at: string | null;
  last_push_at: string | null;
}

export interface SubscriptionsData {
  subscriptions: SubscriptionItem[];
}

export async function getSubscriptions(): Promise<ApiResponse<SubscriptionsData>> {
  return request<SubscriptionsData>('/subscriptions');
}

export interface SourceItem {
  id: number;
  name: string;
  description: string;
  icon: string;
  category: string;
  subscribers: number;
  is_subscribed: boolean;
}

export interface SourceCategory {
  name: string;
  sources: SourceItem[];
}

export interface SourcesData {
  categories: SourceCategory[];
}

export async function getSubscriptionSources(category?: string): Promise<ApiResponse<SourcesData>> {
  const query = category ? `?category=${encodeURIComponent(category)}` : '';
  return request<SourcesData>(`/subscriptions/sources${query}`);
}

export interface SubscribeResult {
  success: boolean;
  subscription_id?: number;
  message: string;
}

export async function subscribeSource(sourceId: number, pushTime: string = '19:00'): Promise<ApiResponse<SubscribeResult>> {
  return request<SubscribeResult>('/subscriptions/subscribe', {
    method: 'POST',
    body: JSON.stringify({ source_id: sourceId, push_time: pushTime }),
  });
}

export interface UnsubscribeResult {
  success: boolean;
  message: string;
}

export async function unsubscribe(subscriptionId: number): Promise<ApiResponse<UnsubscribeResult>> {
  return request<UnsubscribeResult>('/subscriptions/unsubscribe', {
    method: 'POST',
    body: JSON.stringify({ subscription_id: subscriptionId }),
  });
}
