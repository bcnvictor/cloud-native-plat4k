import { api } from './client';
import { GitLabProject } from '@/types';

interface GitLabHealthcheck {
  status: 'ok' | 'error' | 'not_configured';
  detail?: string;
}

interface GitLabCredential {
  namespace: string;
  configured: boolean;
}

export const gitlabApi = {
  async getCredentials(): Promise<GitLabCredential> {
    const res = await api.get<GitLabCredential>('/gitlab/credentials');
    return res.data;
  },

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
