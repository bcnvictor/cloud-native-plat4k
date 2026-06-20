import { api } from './client';
import { MonitoringMetrics, LogEntry } from '@/types';

export const monitoringApi = {
  async getMetrics(): Promise<MonitoringMetrics> {
    const res = await api.get<MonitoringMetrics>('/monitoring/metrics');
    return res.data;
  },

  async getLogs(params: {
    namespace?: string;
    app?: string;
    pod?: string;
    level?: string;
    limit?: number;
  }): Promise<LogEntry[]> {
    const res = await api.get<LogEntry[]>('/monitoring/logs', { params });
    return res.data;
  },
};
