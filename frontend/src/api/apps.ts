import { api } from './client';
import { Application, Deployment } from '@/types';

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
};
