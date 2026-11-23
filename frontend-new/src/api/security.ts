import { api } from './client';
import { SecurityReportResponse } from '@/types';

export const securityApi = {
  async getLatest(appId: number): Promise<SecurityReportResponse> {
    const res = await api.get<SecurityReportResponse>(`/apps/${appId}/security/latest`);
    return res.data;
  },
};
