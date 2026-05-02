import { api } from './client';
import { Resource, CloudType, ResourceType } from '@/types';

export const resourcesApi = {
  list: async (filters?: { cloud?: CloudType; type?: ResourceType; status?: string }) => {
    const params = new URLSearchParams();
    if (filters?.cloud) params.append('cloud', filters.cloud);
    if (filters?.type) params.append('type', filters.type);
    if (filters?.status) params.append('status', filters.status);

    const { data } = await api.get<Resource[]>(`/resources/?${params.toString()}`);
    return data;
  },

  get: async (id: number) => {
    const { data } = await api.get<Resource>(`/resources/${id}`);
    return data;
  },

  create: async (payload: { cloud: CloudType; type: ResourceType; name: string; size?: string }) => {
    const { data } = await api.post<Resource>('/resources/', payload);
    return data;
  },

  delete: async (id: number) => {
    await api.delete(`/resources/${id}`);
  }
};
