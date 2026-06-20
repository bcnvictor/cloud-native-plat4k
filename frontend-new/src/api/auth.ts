import { api } from './client';
import { UserMe, ApiKey } from '@/types';

export const authApi = {
  async login(email: string, password: string): Promise<{ access_token: string }> {
    const form = new URLSearchParams();
    form.append('username', email);
    form.append('password', password);
    const res = await api.post<{ access_token: string }>('/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    return res.data;
  },

  async logout(): Promise<void> {
    await api.post('/auth/logout');
  },

  async me(): Promise<UserMe> {
    const res = await api.get<UserMe>('/users/me');
    return res.data;
  },

  async meWithToken(token: string): Promise<UserMe> {
    const res = await api.get<UserMe>('/users/me', {
      headers: { Authorization: `Bearer ${token}` },
    });
    return res.data;
  },

  async listApiKeys(): Promise<ApiKey[]> {
    const res = await api.get<ApiKey[]>('/auth/apikeys');
    return res.data;
  },

  async createApiKey(label: string): Promise<ApiKey & { key: string }> {
    const res = await api.post<ApiKey & { key: string }>(`/auth/apikeys?label=${encodeURIComponent(label)}`);
    return res.data;
  },

  async deleteApiKey(id: number): Promise<void> {
    await api.delete(`/auth/apikeys/${id}`);
  },

  initiateGitLab(): void {
    const returnTo = `${window.location.origin}/oauth/callback`;
    const base = import.meta.env.VITE_API_URL || '/api/v1';
    window.location.href = `${base}/auth/gitlab/authorize?return_to=${encodeURIComponent(returnTo)}`;
  },
};
