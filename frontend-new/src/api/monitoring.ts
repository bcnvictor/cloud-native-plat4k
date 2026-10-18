import { api } from './client';
import { AppCostEntry, LogEntry, MonitoringMetrics } from '@/types';

interface BackendLogEntry {
  ts: number;
  app: string;
  namespace: string;
  level: string;
  msg: string;
}

export const monitoringApi = {
  async getConfig(): Promise<{ grafana_url: string | null; prometheus_url: string | null; loki_url: string | null }> {
    const res = await api.get<{ grafana_url: string | null; prometheus_url: string | null; loki_url: string | null }>('/monitoring/config');
    return res.data;
  },

  async getCostByGroup(groupId: number): Promise<AppCostEntry[]> {
    const res = await api.get<AppCostEntry[]>('/monitoring/cost', { params: { group_id: groupId } });
    return res.data;
  },

  // Sans clusterId, le backend interroge le Prometheus par défaut (PROMETHEUS_URL) ;
  // avec, celui de la ClusterConnection (cluster.prometheus_url).
  async getMetrics(clusterId?: number | null): Promise<MonitoringMetrics> {
    const res = await api.get<MonitoringMetrics>('/monitoring/metrics', {
      params: clusterId != null ? { cluster_id: clusterId } : undefined,
    });
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
