import { api } from './client';
import type { Notification, NotificationPreference } from '@/types';

export const notificationsApi = {
  async list(params?: { state?: string; limit?: number; offset?: number }): Promise<Notification[]> {
    const res = await api.get<Notification[]>('/notifications/', { params });
    return res.data;
  },

  async countUnread(): Promise<{ count: number }> {
    const res = await api.get<{ count: number }>('/notifications/count');
    return res.data;
  },

  async markRead(id: number): Promise<Notification> {
    const res = await api.patch<Notification>(`/notifications/${id}`, { state: 'read' });
    return res.data;
  },

  async markAcknowledged(id: number): Promise<Notification> {
    const res = await api.patch<Notification>(`/notifications/${id}`, { state: 'acknowledged' });
    return res.data;
  },

  async clearAll(): Promise<void> {
    await api.post('/notifications/clear');
  },

  async getPreferences(): Promise<NotificationPreference[]> {
    const res = await api.get<NotificationPreference[]>('/notifications/preferences');
    return res.data;
  },

  async updatePreference(category: string, enabled: boolean): Promise<NotificationPreference> {
    const res = await api.patch<NotificationPreference>(`/notifications/preferences/${category}`, { enabled });
    return res.data;
  },
};
