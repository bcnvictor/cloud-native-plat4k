import { api } from './client';
import { Application, Deployment } from '@/types';

export interface AppTemplate {
  name: string;
  path: string;
  web_url: string;
}

export const appsApi = {
  list: async () => {
    const { data } = await api.get<Application[]>('/apps/');
    return data;
  },

  get: async (id: number) => {
    const { data } = await api.get<Application>(`/apps/${id}`);
    return data;
  },

  create: async (payload: { name: string; owner: string; repo_url?: string; origin?: string }) => {
    const { data } = await api.post<Application>('/apps/', payload);
    return data;
  },

  delete: async (id: number) => {
    await api.delete(`/apps/${id}`);
  },

  listDeployments: async (applicationId?: number) => {
    const params = applicationId != null ? `?application_id=${applicationId}` : '';
    const { data } = await api.get<Deployment[]>(`/deployments/${params}`);
    return data;
  },

  syncFromK8s: async () => {
    const { data } = await api.post<Application[]>('/apps/sync');
    return data;
  },

  onboardApp: async (payload: { name: string; owner: string; repo_url: string; framework?: string; target_cluster_id?: number; owning_gitlab_group_id?: number | null }) => {
    const { data } = await api.post<Application>('/apps/onboard', payload);
    return data;
  },

  importApp: async (payload: { name: string; owner: string; source_url: string; framework?: string; target_cluster_id?: number; raw?: boolean; owning_gitlab_group_id?: number | null }) => {
    const { data } = await api.post<Application>('/apps/import', payload);
    return data;
  },

  listTemplates: async (): Promise<AppTemplate[]> => {
    const { data } = await api.get<AppTemplate[]>('/apps/templates');
    return data;
  },

  scaffoldApp: async (payload: { name: string; owner: string; template: string; scaffolding?: { port: number; replicas: number; services: string[]; pg_size?: string }; skip_first_deploy?: boolean; target_cluster_id?: number; owning_gitlab_group_id?: number | null }) => {
    const { data } = await api.post<Application>('/apps/scaffold', payload);
    return data;
  },

  getPostgresCredentials: async (appId: number, namespace: string) => {
    const { data } = await api.get<{ host: string; port: number; username: string; password: string; database: string; database_url: string }>(
      `/apps/${appId}/services/postgresql/credentials`,
      { params: { namespace } },
    );
    return data;
  },
};
