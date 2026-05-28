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

export interface GitLabProject {
  id: number;
  name: string;
  path_with_namespace: string;
  web_url: string;
  last_activity_at: string | null;
  language?: string | null;
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

  listProjects: async () => {
    const { data } = await api.get<GitLabProject[]>('/gitlab/projects');
    return data;
  },
};
