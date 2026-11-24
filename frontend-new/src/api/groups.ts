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

  // `panel` / `env` : le dashboard s'ouvre directement sur ce panneau, pour cet environnement.
  async getGrafanaUrl(
    gitlabGroupId: number,
    options?: { panel?: 'cpu' | 'ram' | 'logs'; env?: 'dev' | 'prod' },
  ): Promise<{ dashboard_url: string | null; panel_base_url: string | null }> {
    const res = await api.get<{ dashboard_url: string | null; panel_base_url: string | null }>(
      `/groups/${gitlabGroupId}/grafana-url`,
      { params: options },
    );
    return res.data;
  },

  findBySlug(groups: GroupMembership[], slug: string): GroupMembership | undefined {
    return groups.find((g) => g.full_path.split('/').pop() === slug);
  },

  getSlug(group: GroupMembership): string {
    return group.full_path.split('/').pop() ?? group.full_path;
  },
};
