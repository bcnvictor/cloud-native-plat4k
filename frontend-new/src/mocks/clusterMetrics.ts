// MOCK: pas d'endpoint métriques cluster (CPU/RAM/pods/namespaces) — décommissionner quand GET /clusters/:id/metrics existe
import { ClusterMetrics } from '@/types';

export const CLUSTER_METRICS: Record<string, ClusterMetrics> = {
  'cnp-aks': {
    nodesActive: 3,
    cpuUsed: 4.2,
    cpuTotal: 12,
    ramUsedGi: 11.4,
    ramTotalGi: 24,
    k8sVersion: '1.29.2',
    type: 'Public · managed',
    provider: 'Azure · Sweden Central',
    icon: 'cloud',
    podsActive: 47,
    namespaces: [
      { name: 'cnp-system', apps: 3, pods: 12 },
      { name: 'team-alpha', apps: 4, pods: 11 },
      { name: 'team-beta', apps: 2, pods: 6 },
    ],
  },
  'cnp-k3s': {
    nodesActive: 1,
    cpuUsed: 1.1,
    cpuTotal: 4,
    ramUsedGi: 2.8,
    ramTotalGi: 8,
    k8sVersion: '1.28.5',
    type: 'Privé · IaaS',
    provider: 'Oracle Cloud · Frankfurt',
    icon: 'server',
    podsActive: 14,
    namespaces: [
      { name: 'cnp-system', apps: 2, pods: 6 },
      { name: 'team-gamma', apps: 1, pods: 3 },
    ],
  },
};
