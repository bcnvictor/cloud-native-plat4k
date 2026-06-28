import { api } from './client';
import type { NotificationEvent } from '@/types';

export const eventsApi = {
  async groupActivity(gitlabGroupId: number, limit = 10): Promise<NotificationEvent[]> {
    const res = await api.get<NotificationEvent[]>(
      `/groups/${gitlabGroupId}/activity`,
      { params: { limit } },
    );
    return res.data;
  },
};
