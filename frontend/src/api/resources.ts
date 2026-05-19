import { api } from './client';
import { Resource, CloudType, ResourceType } from '@/types';

export const resourcesApi = {
  list: async (filters?: { cloud?: CloudType; type?: ResourceType; status?: string }) => {
    const { data } = await api.get<Resource[]>('/resources/', { params: filters });
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
