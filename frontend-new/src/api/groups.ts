import { api } from './client';
import { GroupMembership } from '@/types';

export const groupsApi = {
  async getMyGroups(): Promise<GroupMembership[]> {
    const res = await api.get<GroupMembership[]>('/users/me/groups');
    return res.data;
  },

  async syncTeams(): Promise<void> {
    await api.post('/users/me/sync-teams');
  },

  findBySlug(groups: GroupMembership[], slug: string): GroupMembership | undefined {
    return groups.find((g) => g.full_path.split('/').pop() === slug);
  },

  getSlug(group: GroupMembership): string {
    return group.full_path.split('/').pop() ?? group.full_path;
  },
};
