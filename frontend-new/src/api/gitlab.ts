import { api } from './client';
import { GitLabProject } from '@/types';

interface GitLabHealthcheck {
  connected: boolean;
  url: string;
  last_checked: string;
  scopes: string[];
}

interface GitLabCredential {
  token_masked: string;
  namespace: string;
  created_at: string;
}

export const gitlabApi = {
  async healthcheck(): Promise<GitLabHealthcheck> {
    const res = await api.get<GitLabHealthcheck>('/gitlab/healthcheck');
    return res.data;
  },

  async saveCredentials(
    token: string,
    namespace: string
  ): Promise<GitLabCredential> {
    const res = await api.post<GitLabCredential>('/gitlab/credentials', {
      token,
      namespace,
    });
    return res.data;
  },

  async deleteCredentials(): Promise<void> {
    await api.delete('/gitlab/credentials');
  },

  async listProjects(): Promise<GitLabProject[]> {
    const res = await api.get<GitLabProject[]>('/gitlab/projects');
    return res.data;
  },
};
