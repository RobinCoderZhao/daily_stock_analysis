import apiClient from './index';

export type WatchlistItem = {
  stock_code: string;
  stock_name: string;
  added_at: string;
  latest_analysis_at?: string;
  composite_score?: number;
};

export type WatchlistResponse = {
  watchlist: WatchlistItem[];
  limit: number;
  used: number;
};

export const watchlistApi = {
  async getList(): Promise<WatchlistResponse> {
    const { data } = await apiClient.get<WatchlistResponse>('/api/v1/watchlist/');
    return data;
  },

  async add(stockCode: string): Promise<{ ok: boolean }> {
    const { data } = await apiClient.post('/api/v1/watchlist/add', { stock_code: stockCode });
    return data;
  },

  async remove(stockCode: string): Promise<{ ok: boolean }> {
    const { data } = await apiClient.delete(`/api/v1/watchlist/${encodeURIComponent(stockCode)}`);
    return data;
  },
};
