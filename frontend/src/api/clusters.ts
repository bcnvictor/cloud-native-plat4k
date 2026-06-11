import { api } from './client';

export interface ClusterConnection {
  id: number;
  name: string;
  endpoint: string;
  kubeconfig_secret_ref: string;
  status: 'online' | 'offline' | 'unknown';
  last_seen_at?: string;
  created_at: string;
  updated_at?: string;
}

export const clustersApi = {
  list: async (): Promise<ClusterConnection[]> => {
    const { data } = await api.get<ClusterConnection[]>('/clusters/');
    return data;
  },
};
