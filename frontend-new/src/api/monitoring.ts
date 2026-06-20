import { api } from './client';
import { MonitoringMetrics, LogEntry } from '@/types';

interface BackendLogEntry {
  ts: number;
  app: string;
  namespace: string;
  level: string;
  msg: string;
}

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
    const res = await api.get<BackendLogEntry[]>('/monitoring/logs', { params });

    return res.data.map((e) => ({
      timestamp: new Date(e.ts * 1000).toISOString(),
      level: e.level.toUpperCase() as LogEntry['level'],
      message: e.msg,
      pod: e.namespace ? `${e.namespace}/${e.app}` : e.app,
    }));
  },
};
