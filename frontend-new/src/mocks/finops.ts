// MOCK: aucun endpoint FinOps backend (prévu S2) — décommissionner quand GET /finops/ existe
import { FinOpsData } from '@/types';

export const FINOPS_MOCK: FinOpsData = {
  period: '2026-06',
  totalCostUsd: 247.3,
  azureCreditsTotal: 500,
  azureCreditsUsed: 247.3,
  azureCreditsRemainingDays: 31,
  clusters: [
    { name: 'cnp-aks', provider: 'Azure', costUsd: 247.3 },
    { name: 'cnp-k3s', provider: 'Oracle Cloud', costUsd: 0 },
  ],
  groups: [
    {
      groupName: 'cnp-system',
      totalUsd: 89.4,
      apps: [
        { appName: 'argocd', costUsd: 52.1 },
        { appName: 'prometheus-stack', costUsd: 37.3 },
      ],
    },
    {
      groupName: 'team-alpha',
      totalUsd: 98.7,
      apps: [
        { appName: 'auth-service', costUsd: 31.2 },
        { appName: 'api-gateway', costUsd: 28.9 },
        { appName: 'frontend-app', costUsd: 24.1 },
        { appName: 'worker', costUsd: 14.5 },
      ],
    },
    {
      groupName: 'team-beta',
      totalUsd: 59.2,
      apps: [
        { appName: 'data-pipeline', costUsd: 38.6 },
        { appName: 'dashboard', costUsd: 20.6 },
      ],
    },
  ],
};
