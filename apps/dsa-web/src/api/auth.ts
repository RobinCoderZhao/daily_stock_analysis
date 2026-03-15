import apiClient from './index';

export type AuthStatusResponse = {
  authEnabled: boolean;
  loggedIn: boolean;
  passwordSet?: boolean;
  passwordChangeable?: boolean;
  // SaaS mode fields
  saasMode?: boolean;
};

export type SaasLoginResponse = {
  user_id: number;
  email: string;
  nickname?: string;
  role: string;
  tier: string;
  access_token: string;
};

export type SaasProfileResponse = {
  user_id: number;
  uuid: string;
  email: string;
  nickname?: string;
  avatar_url?: string;
  role: string;
  tier: string;
  watchlist_limit: number;
  expire_at?: string;
  created_at?: string;
  last_login_at?: string;
};

export const authApi = {
  async getStatus(): Promise<AuthStatusResponse> {
    const { data } = await apiClient.get<AuthStatusResponse>('/api/v1/auth/status');
    return data;
  },

  // === Legacy admin auth (SAAS_MODE=false) ===

  async login(password: string, passwordConfirm?: string): Promise<void> {
    const body: { password: string; passwordConfirm?: string } = { password };
    if (passwordConfirm !== undefined) {
      body.passwordConfirm = passwordConfirm;
    }
    await apiClient.post('/api/v1/auth/login', body);
  },

  async changePassword(
    currentPassword: string,
    newPassword: string,
    newPasswordConfirm: string
  ): Promise<void> {
    await apiClient.post('/api/v1/auth/change-password', {
      currentPassword,
      newPassword,
      newPasswordConfirm,
    });
  },

  async logout(): Promise<void> {
    await apiClient.post('/api/v1/auth/logout');
  },

  // === SaaS mode auth (SAAS_MODE=true) ===

  async register(
    email: string,
    password: string,
    nickname?: string
  ): Promise<SaasLoginResponse> {
    const { data } = await apiClient.post<SaasLoginResponse>(
      '/api/v1/auth/register',
      { email, password, nickname }
    );
    return data;
  },

  async saasLogin(email: string, password: string): Promise<SaasLoginResponse> {
    const { data } = await apiClient.post<SaasLoginResponse>(
      '/api/v1/auth/saas-login',
      { email, password }
    );
    return data;
  },

  async refreshToken(): Promise<{ access_token: string }> {
    const { data } = await apiClient.post<{ access_token: string }>(
      '/api/v1/auth/refresh'
    );
    return data;
  },

  async getProfile(): Promise<SaasProfileResponse> {
    const { data } = await apiClient.get<SaasProfileResponse>('/api/v1/auth/me');
    return data;
  },
};
