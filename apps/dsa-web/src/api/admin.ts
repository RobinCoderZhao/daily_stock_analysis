import apiClient from './index';

// ======== Dashboard ========

export type DashboardOverview = {
  total_users: number;
  active_today: number;
  active_subscriptions: number;
  monthly_revenue_cents: number;
  today_usage: number;
};

export type GrowthDataPoint = { date: string; registrations: number };
export type UsageDataPoint = { date: string; action: string; count: number };
export type RevenueDataPoint = { date: string; plan: string; total_cents: number; order_count: number };
export type LlmCostDataPoint = { action: string; total_tokens: number; call_count: number };

// ======== Users ========

export type AdminUser = {
  id: number;
  email: string;
  nickname?: string;
  role: string;
  status: string;
  created_at?: string;
};

export type AdminUserDetail = {
  user: AdminUser;
  subscription: {
    tier: string;
    status: string;
    expire_at?: string | null;
    temp_credits: number;
  } | null;
  usage_today: number;
};

export type UserListResponse = {
  total: number;
  page: number;
  limit: number;
  users: AdminUser[];
};

// ======== Keys ========

export type PlatformKey = {
  id: number;
  provider: string;
  key_preview: string;
  is_active: boolean;
  priority: number;
  daily_limit: number | null;
  used_today: number;
  label?: string;
  last_rotated_at?: string | null;
  created_at?: string;
};

export type KeyUsageStat = {
  provider: string;
  total_keys: number;
  active_keys: number;
  total_used_today: number;
  total_daily_limit: number;
};

export const adminApi = {
  // Dashboard
  async getOverview(): Promise<DashboardOverview> {
    const { data } = await apiClient.get<DashboardOverview>('/api/v1/admin/dashboard/overview');
    return data;
  },

  async getUserGrowth(days = 30): Promise<{ period_days: number; data: GrowthDataPoint[] }> {
    const { data } = await apiClient.get('/api/v1/admin/dashboard/user-growth', { params: { days } });
    return data;
  },

  async getUsageStats(days = 30): Promise<{ period_days: number; data: UsageDataPoint[] }> {
    const { data } = await apiClient.get('/api/v1/admin/dashboard/usage-stats', { params: { days } });
    return data;
  },

  async getRevenue(days = 30): Promise<{ period_days: number; data: RevenueDataPoint[] }> {
    const { data } = await apiClient.get('/api/v1/admin/dashboard/revenue', { params: { days } });
    return data;
  },

  async getLlmCost(days = 30): Promise<{ period_days: number; data: LlmCostDataPoint[] }> {
    const { data } = await apiClient.get('/api/v1/admin/dashboard/llm-cost', { params: { days } });
    return data;
  },

  // Users
  async listUsers(page = 1, limit = 20, search?: string): Promise<UserListResponse> {
    const { data } = await apiClient.get<UserListResponse>('/api/v1/admin/users/', {
      params: { page, limit, ...(search ? { search } : {}) },
    });
    return data;
  },

  async getUserDetail(userId: number): Promise<AdminUserDetail> {
    const { data } = await apiClient.get<AdminUserDetail>(`/api/v1/admin/users/${userId}`);
    return data;
  },

  async updateUserStatus(userId: number, status: 'active' | 'suspended'): Promise<{ ok: boolean }> {
    const { data } = await apiClient.put(`/api/v1/admin/users/${userId}/status`, { status });
    return data;
  },

  async adjustSubscription(
    userId: number,
    body: { tier?: string; temp_credits?: number; extend_days?: number }
  ): Promise<{ ok: boolean; changes: string[] }> {
    const { data } = await apiClient.put(`/api/v1/admin/users/${userId}/subscription`, body);
    return data;
  },

  // Keys
  async listKeys(provider?: string): Promise<{ keys: PlatformKey[] }> {
    const { data } = await apiClient.get('/api/v1/admin/keys/', {
      params: provider ? { provider } : {},
    });
    return data;
  },

  async addKey(body: {
    provider: string;
    raw_key: string;
    priority?: number;
    daily_limit?: number | null;
    label?: string;
  }): Promise<{ ok: boolean; key_id: number }> {
    const { data } = await apiClient.post('/api/v1/admin/keys/', body);
    return data;
  },

  async deactivateKey(keyId: number): Promise<{ ok: boolean }> {
    const { data } = await apiClient.put(`/api/v1/admin/keys/${keyId}/deactivate`);
    return data;
  },

  async getKeyUsage(): Promise<{ stats: KeyUsageStat[] }> {
    const { data } = await apiClient.get('/api/v1/admin/keys/usage');
    return data;
  },
};
