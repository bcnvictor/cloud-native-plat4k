import { FINOPS_MOCK } from '@/mocks/finops';
import { FinOpsData } from '@/types';

export const finopsApi = {
  async getData(_month: string): Promise<FinOpsData> {
    // Mock-backed for S1 — no cost API in backend
    return Promise.resolve(FINOPS_MOCK);
  },
};
