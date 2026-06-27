import { api } from './client';
import { Application, AppRuntimeStatus, AppMember, AppTemplate, EnvVar } from '@/types';

export const appsApi = {
  async list(): Promise<Application[]> {
    const res = await api.get<Application[]>('/apps/');
    return res.data;
  },

  async get(id: number): Promise<Application> {
    const res = await api.get<Application>(`/apps/${id}`);
    return res.data;
  },

  async getBySlug(slug: string): Promise<Application | undefined> {
    const all = await appsApi.list();
    return all.find((a) => {
      const name = a.name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
      return name === slug;
    });
  },

  async listTemplates(): Promise<AppTemplate[]> {
    const res = await api.get<AppTemplate[]>('/apps/templates');
    return res.data;
  },

  async scaffoldApp(payload: {
    name: string;
    owner: string;
    template: string;
    owning_gitlab_group_id?: number;
    target_cluster_id?: number | null;
  }): Promise<Application> {
    const res = await api.post<Application>('/apps/scaffold', payload);
    return res.data;
  },

  async onboardApp(payload: {
    name: string;
    owner: string;
    repo_url: string;
    owning_gitlab_group_id?: number;
  }): Promise<Application> {
    const res = await api.post<Application>('/apps/onboard', payload);
    return res.data;
  },

  async updateApp(
    id: number,
    payload: { name?: string; description?: string }
  ): Promise<Application> {
    const res = await api.put<Application>(`/apps/${id}`, payload);
    return res.data;
  },

  async getMembers(appId: number): Promise<AppMember[]> {
    const res = await api.get<AppMember[]>(`/apps/${appId}/members`);
    return res.data;
  },

  async addMember(
    appId: number,
    payload: { email: string; role: string }
  ): Promise<void> {
    await api.post(`/apps/${appId}/invitations`, payload);
  },

  async removeMember(appId: number, userId: number): Promise<void> {
    await api.delete(`/apps/${appId}/members/${userId}`);
  },

  async deleteApp(id: number): Promise<void> {
    await api.delete(`/apps/${id}`);
  },

  async getStatus(appId: number): Promise<AppRuntimeStatus> {
    const res = await api.get<AppRuntimeStatus>(`/apps/${appId}/status`);
    return res.data;
  },

  async getEnvVars(_appId: number): Promise<EnvVar[]> {
    // Not in backend yet — return empty for S1
    return [];
  },

  async updateEnvVars(_appId: number, _vars: EnvVar[]): Promise<void> {
    // Not in backend yet — no-op for S1
  },
};
