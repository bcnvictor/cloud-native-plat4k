import { api } from './client';
import { GitLabGroupAdmin } from '@/types';

export interface GitLabSyncResult {
  skipped?: boolean;
  groups?: { created: number; updated: number; revoked: number };
}

export const adminApi = {
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
