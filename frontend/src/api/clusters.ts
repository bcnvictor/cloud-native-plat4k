import { api } from './client';

export interface ClusterConnection {
  id: number;
  name: string;
  endpoint: string;
  kubeconfig_secret_ref: string;
  created_at: string;
  updated_at?: string;
}

export interface ClusterConnectionCreate {
  name: string;
  endpoint: string;
  kubeconfig: string;
}

export interface ClusterConnectionUpdate {
  name?: string;
  endpoint?: string;
  kubeconfig?: string;
}

export const clustersApi = {
  list: async (): Promise<ClusterConnection[]> => {
    const { data } = await api.get<ClusterConnection[]>('/clusters/');
    return data;
  },
  get: async (id: number): Promise<ClusterConnection> => {
    const { data } = await api.get<ClusterConnection>(`/clusters/${id}`);
    return data;
  },
  create: async (payload: ClusterConnectionCreate): Promise<ClusterConnection> => {
    const { data } = await api.post<ClusterConnection>('/clusters/', payload);
    return data;
  },
  update: async (id: number, payload: ClusterConnectionUpdate): Promise<ClusterConnection> => {
    const { data } = await api.put<ClusterConnection>(`/clusters/${id}`, payload);
    return data;
  },
  delete: async (id: number): Promise<void> => {
    await api.delete(`/clusters/${id}`);
  },
};

