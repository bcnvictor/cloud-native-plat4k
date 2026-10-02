import { api } from './client';
import {
  AIFinOpsAdvice,
  AIAppSettings,
  AIAppSettingsPatch,
  AIGlobalSettings,
  AIGlobalSettingsPatch,
  AIUISettings,
  ChatPayload,
  ChatResponse,
} from '@/types';

export const assistantApi = {
  /** Conseiller FinOps IA : recommandations depuis 24 h de métriques Prometheus. */
  async getAiAdvice(appId: number): Promise<AIFinOpsAdvice> {
    const res = await api.get<AIFinOpsAdvice>(`/apps/${appId}/ai-advice`, { timeout: 120_000 });
    return res.data;
  },

  async getAppSettings(appId: number): Promise<AIAppSettings> {
    const res = await api.get<AIAppSettings>(`/apps/${appId}/assistant/settings`);
    return res.data;
  },

  async patchAppSettings(appId: number, payload: AIAppSettingsPatch): Promise<AIAppSettings> {
    const res = await api.patch<AIAppSettings>(`/apps/${appId}/assistant/settings`, payload);
    return res.data;
  },

  async chatWithApp(appId: number, payload: ChatPayload): Promise<ChatResponse> {
    const res = await api.post<ChatResponse>(`/apps/${appId}/assistant/chat`, payload);
    return res.data;
  },

  async chatGlobal(payload: ChatPayload): Promise<ChatResponse> {
    const res = await api.post<ChatResponse>('/assistant/chat', payload);
    return res.data;
  },

  async getGlobalSettings(): Promise<AIGlobalSettings> {
    const res = await api.get<AIGlobalSettings>('/assistant/global-settings');
    return res.data;
  },

  async getUiSettings(): Promise<AIUISettings> {
    const res = await api.get<AIUISettings>('/assistant/ui-settings');
    return res.data;
  },

  async patchGlobalSettings(payload: AIGlobalSettingsPatch): Promise<AIGlobalSettings> {
    const res = await api.patch<AIGlobalSettings>('/assistant/global-settings', payload);
    return res.data;
  },
};
