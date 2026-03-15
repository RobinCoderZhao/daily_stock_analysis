import apiClient from './index';

export type WatchlistItem = {
  id: number;
  code: string;
  name: string;
  group: string;
  market: string;
  sort_order: number;
  added_at: string;
};

export type WatchlistResponse = {
  items: WatchlistItem[];
  count: number;
};

export const watchlistApi = {
  async getList(): Promise<WatchlistResponse> {
    const { data } = await apiClient.get<WatchlistResponse>('/api/v1/watchlist/');
    return data;
  },

  async add(code: string, name?: string, group?: string): Promise<WatchlistItem> {
    const { data } = await apiClient.post('/api/v1/watchlist/add', {
      code,
      name: name || undefined,
      group: group || '默认分组',
    });
    return data;
  },

  async remove(code: string): Promise<{ ok: boolean }> {
    const { data } = await apiClient.delete(`/api/v1/watchlist/${encodeURIComponent(code)}`);
    return data;
  },

  async getQuota(): Promise<{ limit: number; used: number; remaining: number; tier: string }> {
    const { data } = await apiClient.get('/api/v1/watchlist/quota');
    return data;
  },
};
