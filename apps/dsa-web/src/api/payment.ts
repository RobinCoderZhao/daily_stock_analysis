import apiClient from './index';

// Types
export type TierInfo = {
  watchlist_limit: number;
  agent_daily_limit: number | null;
  features: string[];
  price_monthly_cents: number;
  price_yearly_cents: number;
};

export type TempPack = {
  credits: number;
  price_cents: number;
};

export type PlansResponse = {
  tiers: Record<string, TierInfo>;
  temp_packs: Record<string, TempPack>;
};

export type SubscriptionInfo = {
  id?: number;
  tier: string;
  status: string;
  watchlist_limit?: number;
  daily_analysis_limit?: number | null;
  agent_daily_limit?: number | null;
  temp_analysis_credits?: number;
  expire_at?: string | null;
  start_at?: string | null;
};

export type CheckoutResponse = {
  order_no: string;
  plan: string;
  amount_cents: number;
  currency: string;
  checkout_url?: string | null;
  error?: string;
};

export type OrderItem = {
  id: number;
  user_id: number;
  order_no: string;
  plan: string;
  amount_cents: number;
  currency: string;
  payment_provider?: string;
  status: string;
  paid_at?: string | null;
  created_at?: string | null;
};

export const paymentApi = {
  async getPlans(): Promise<PlansResponse> {
    const { data } = await apiClient.get<PlansResponse>('/api/v1/payment/plans');
    return data;
  },

  async createCheckout(plan: string): Promise<CheckoutResponse> {
    const { data } = await apiClient.post<CheckoutResponse>('/api/v1/payment/checkout', { plan });
    return data;
  },

  async getSubscription(): Promise<SubscriptionInfo> {
    const { data } = await apiClient.get<SubscriptionInfo>('/api/v1/payment/subscription');
    return data;
  },

  async cancelSubscription(): Promise<{ ok: boolean }> {
    const { data } = await apiClient.post('/api/v1/payment/subscription/cancel');
    return data;
  },

  async getOrders(limit = 20): Promise<{ orders: OrderItem[] }> {
    const { data } = await apiClient.get('/api/v1/payment/orders', { params: { limit } });
    return data;
  },
};
