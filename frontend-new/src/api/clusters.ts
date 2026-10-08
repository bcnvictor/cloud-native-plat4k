import { api } from './client';
import { ClusterConnection, ClusterConnectionPayload, ClusterTestResult } from '@/types';

export const clustersApi = {
  async list(): Promise<ClusterConnection[]> {
    const res = await api.get<ClusterConnection[]>('/clusters/');
    return res.data;
  },

  async register(payload: ClusterConnectionPayload): Promise<ClusterConnection> {
    const res = await api.post<ClusterConnection>('/clusters/', payload);
    return res.data;
  },

  async update(id: number, payload: ClusterConnectionPayload): Promise<ClusterConnection> {
    const res = await api.put<ClusterConnection>(`/clusters/${id}`, payload);
    return res.data;
  },

  async remove(id: number): Promise<void> {
    await api.delete(`/clusters/${id}`);
  },

  async test(id: number): Promise<ClusterTestResult> {
    const res = await api.post<ClusterTestResult>(`/clusters/${id}/test`);
    return res.data;
  },

  async testKubeconfig(kubeconfig: string): Promise<ClusterTestResult> {
    const res = await api.post<ClusterTestResult>('/clusters/test', { kubeconfig });
    return res.data;
  },
};
