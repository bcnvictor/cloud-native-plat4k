import { api } from './client';
import { GitLabGroupAdmin } from '@/types';

export interface GitLabSyncResult {
  skipped?: boolean;
  groups?: { created: number; updated: number; revoked: number };
}

export interface PlatformSchedules {
  scale_to_zero: {
    enabled: boolean;
    interval_minutes: number;
    scale_down_hour: number;
    scale_up_hour: number;
    timezone: string;
    weekdays_only: boolean;
  };
  gitlab_sync: { enabled: boolean; interval_minutes: number };
}

export const adminApi = {
  async getPlatformSchedules(): Promise<PlatformSchedules> {
    const res = await api.get<PlatformSchedules>('/admin/platform-schedules');
    return res.data;
  },

  async listGitlabGroups(): Promise<GitLabGroupAdmin[]> {
    const res = await api.get<GitLabGroupAdmin[]>('/admin/gitlab-groups');
    return res.data;
  },

  async registerGitlabGroup(identifier: string): Promise<GitLabGroupAdmin> {
    const body = /^\d+$/.test(identifier)
      ? { gitlab_group_id: Number(identifier) }
      : { full_path: identifier };
    const res = await api.post<GitLabGroupAdmin>('/admin/gitlab-groups', body);
    return res.data;
  },

  async deregisterGitlabGroup(gitlabGroupId: number): Promise<void> {
    await api.delete(`/admin/gitlab-groups/${gitlabGroupId}`);
  },

  async syncGitlab(): Promise<GitLabSyncResult> {
    const res = await api.post<GitLabSyncResult>('/admin/sync-gitlab');
    return res.data;
  },
};
