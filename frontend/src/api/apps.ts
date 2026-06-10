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

  onboardApp: async (payload: { name: string; owner: string; repo_url: string; framework?: string; target_cluster_id?: number }) => {
    const { data } = await api.post<Application>('/apps/onboard', payload);
    return data;
  },

  importApp: async (payload: { name: string; owner: string; source_url: string; framework?: string; target_cluster_id?: number; raw?: boolean }) => {
    const { data } = await api.post<Application>('/apps/import', payload);
    return data;
  },

  listTemplates: async (): Promise<AppTemplate[]> => {
    const { data } = await api.get<AppTemplate[]>('/apps/templates');
    return data;
  },

  scaffoldApp: async (payload: { name: string; owner: string; template: string; scaffolding?: { port: number; replicas: number }; skip_first_deploy?: boolean }) => {
    const { data } = await api.post<Application>('/apps/scaffold', payload);
    return data;
  },
};
