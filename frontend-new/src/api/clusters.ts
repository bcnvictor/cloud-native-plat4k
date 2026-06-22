import { api } from './client';
import { ClusterConnection } from '@/types';

export const clustersApi = {
  async list(): Promise<ClusterConnection[]> {
    const res = await api.get<ClusterConnection[]>('/clusters/');
    return res.data;
  },

  async register(payload: {
    name: string;
    endpoint: string;
    kubeconfig: string;
  }): Promise<ClusterConnection> {
    const res = await api.post<ClusterConnection>('/clusters/', payload);
    return res.data;
  },
};
