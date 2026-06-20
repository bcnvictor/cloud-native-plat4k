import { api } from './client';
import { AppMember, GroupMembership } from '@/types';

export const groupsApi = {
  async getMyGroups(): Promise<GroupMembership[]> {
    const res = await api.get<GroupMembership[]>('/users/me/groups');
    return res.data;
  },

  async getMembers(gitlabGroupId: number): Promise<AppMember[]> {
    const res = await api.get<AppMember[]>(`/groups/${gitlabGroupId}/members`);
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
