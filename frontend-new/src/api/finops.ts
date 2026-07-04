import { api } from './client';
import { FinopsGrafanaUrls, TeamCostEntry } from '@/types';

export const finopsApi = {
  async getGrafanaUrls(): Promise<FinopsGrafanaUrls> {
    const res = await api.get<FinopsGrafanaUrls>('/admin/finops/grafana-urls');
    return res.data;
  },

  async getCostByTeam(): Promise<TeamCostEntry[]> {
    const res = await api.get<TeamCostEntry[]>('/admin/finops/cost-by-team');
    return res.data;
  },
};
