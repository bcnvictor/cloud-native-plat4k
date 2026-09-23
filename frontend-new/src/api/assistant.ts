import { api } from './client';
import {
  AIAppSettings,
  AIAppSettingsPatch,
  AIGlobalSettings,
  AIGlobalSettingsPatch,
  AIUISettings,
  ChatPayload,
  ChatResponse,
  ChatTurn,
} from '@/types';

/** Nombre de tours renvoyés au backend pour garder le fil de la conversation. */
const HISTORY_TURNS = 12;

/**
 * Convertit le fil affiché en historique pour l'API : on écarte le message
 * d'accueil et les erreurs locales (ids `greeting` / `err…`), qui ne sont pas
 * de vraies réponses du modèle.
 */
export function toChatHistory(
  messages: { id: string; role: 'user' | 'assistant'; content: string }[]
): ChatTurn[] {
  return messages
    .filter((m) => m.id !== 'greeting' && !m.id.startsWith('err'))
    .slice(-HISTORY_TURNS)
    .map(({ role, content }) => ({ role, content }));
}

export const assistantApi = {
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
