import { api } from './client';

export interface GitLabHealthcheck {
  status: 'ok' | 'error' | 'not_configured';
  gitlab_url?: string;
  authenticated_as?: string;
  detail?: string;
}

export interface GitLabCredential {
  namespace: string;
  configured: boolean;
}

export const gitlabApi = {
  getCredentials: async () => {
    const { data } = await api.get<GitLabCredential>('/gitlab/credentials');
    return data;
  },

  saveCredentials: async (token: string, namespace: string) => {
    const { data } = await api.post<GitLabCredential>('/gitlab/credentials', { token, namespace });
    return data;
  },

  deleteCredentials: async () => {
    await api.delete('/gitlab/credentials');
  },

  healthcheck: async () => {
    const { data } = await api.get<GitLabHealthcheck>('/gitlab/healthcheck');
    return data;
  },
};
