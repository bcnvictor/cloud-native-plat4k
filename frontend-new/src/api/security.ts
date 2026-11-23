import { api } from './client';
import { SecurityReportResponse } from '@/types';
import type { AutofixResult } from '@/components/SecurityFixDialog';

export interface FixPromptResponse {
  prompt: string;
  finding: string;
}

export const securityApi = {
  async autofix(appId: number, findingId: string): Promise<AutofixResult> {
    const res = await api.post<AutofixResult>(`/apps/${appId}/security/findings/${findingId}/autofix`, null, { timeout: 60_000 });
    return res.data;
  },

  async getFixPrompt(appId: number, finding: string): Promise<FixPromptResponse> {
    const res = await api.get<FixPromptResponse>(`/apps/${appId}/security/fix-prompt`, { params: { finding } });
    return res.data;
  },

  async getLatest(appId: number): Promise<SecurityReportResponse> {
    const res = await api.get<SecurityReportResponse>(`/apps/${appId}/security/latest`);
    return res.data;
  },
};
