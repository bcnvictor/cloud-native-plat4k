import { api } from './client';

export type AppValue = { app: string; owner: string; value: number };

export type MonitoringConfig = { grafana_url: string };

export type MonitoringMetrics = {
  cpu_by_app: AppValue[];
  ram_by_app: AppValue[];
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
  getConfig: async (): Promise<MonitoringConfig> => {
    const res = await api.get<MonitoringConfig>('/monitoring/config');
    return res.data;
  },
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
  getAppLogs: async (appName: string, limit = 50): Promise<LogEntry[]> => {
    const res = await api.get<LogEntry[]>('/monitoring/logs', {
      params: { app: appName, limit },
    });
    return res.data;
  },
};
