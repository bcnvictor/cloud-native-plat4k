import { api } from './client';
import { EphemeralEnv } from '@/types';

export const ephemeralEnvsApi = {
  async list(appId: number): Promise<EphemeralEnv[]> {
    const res = await api.get<EphemeralEnv[]>(`/apps/${appId}/ephemeral-envs`);
    return res.data;
  },

  /** Branches du repo, sans la branche par défaut (Developer et plus). */
  async branches(appId: number): Promise<string[]> {
    const res = await api.get<string[]>(`/apps/${appId}/ephemeral-envs/branches`);
    return res.data;
  },

  async create(appId: number, branch: string, ttlHours?: number): Promise<EphemeralEnv> {
    const res = await api.post<EphemeralEnv>(`/apps/${appId}/ephemeral-envs`, {
      branch,
      ...(ttlHours ? { ttl_hours: ttlHours } : {}),
    });
    return res.data;
  },

  /** 202 tant qu'ArgoCD purge le namespace, 200 une fois détruit. */
  async destroy(appId: number, envId: number): Promise<EphemeralEnv> {
    const res = await api.delete<EphemeralEnv>(`/apps/${appId}/ephemeral-envs/${envId}`);
    return res.data;
  },
};
