import { api } from './client';

export type NamespaceValue = { namespace: string; value: number };

export type MonitoringMetrics = {
  cpu_by_namespace: NamespaceValue[];
  ram_by_namespace: NamespaceValue[];
  estimated_hourly_cost_usd: number;
  estimated_daily_cost_usd: number;
};

export type LogEntry = {
  ts: number;
  app: string;
  namespace: string;
  level: string;
  msg: string;
};

export const monitoringApi = {
  getMetrics: async (): Promise<MonitoringMetrics> => {
    const res = await api.get<MonitoringMetrics>('/monitoring/metrics');
    return res.data;
  },
  getLogs: async (namespace?: string, limit = 50): Promise<LogEntry[]> => {
    const res = await api.get<LogEntry[]>('/monitoring/logs', {
      params: { ...(namespace ? { namespace } : {}), limit },
    });
    return res.data;
  },
};
