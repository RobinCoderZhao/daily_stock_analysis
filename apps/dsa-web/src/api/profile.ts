import apiClient from './index';

// Memory types
export type MemoryItem = {
  id: string;
  memory: string;
  created_at?: string;
};

export type InvestmentProfileData = {
  profile: Record<string, unknown>;
  memory_count: number;
};

export const profileApi = {
  async getMemories(): Promise<{ memories: MemoryItem[] }> {
    const { data } = await apiClient.get('/api/v1/profile/memories');
    return data;
  },

  async deleteMemory(memoryId: string): Promise<{ ok: boolean }> {
    const { data } = await apiClient.delete(`/api/v1/profile/memories/${encodeURIComponent(memoryId)}`);
    return data;
  },

  async clearAllMemories(): Promise<{ ok: boolean }> {
    const { data } = await apiClient.delete('/api/v1/profile/memories');
    return data;
  },

  async getInvestmentProfile(): Promise<InvestmentProfileData> {
    const { data } = await apiClient.get<InvestmentProfileData>('/api/v1/profile/investment-profile');
    return data;
  },
};
