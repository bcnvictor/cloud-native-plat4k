import { api } from './client';
import { Credential, CloudType } from '@/types';

export const credentialsApi = {
  list: async () => {
    const { data } = await api.get<Credential[]>('/credentials/');
    return data;
  },

  add: async (cloud: CloudType, credentials: Record<string, string>) => {
    const { data } = await api.post<Credential>('/credentials/', { cloud, credentials });
    return data;
  },

  delete: async (id: number) => {
    await api.delete(`/credentials/${id}`);
  }
};
