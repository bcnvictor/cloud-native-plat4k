import { api } from './client';

export const authApi = {
  login: async (email: string, password: string) => {
    const { data } = await api.post('/auth/login', { email, password });
    return data; // { access_token, token_type }
  },

  logout: async () => {
    await api.post('/auth/logout');
  },

  getApiKeys: async () => {
    const { data } = await api.get('/auth/apikeys');
    return data;
  },

  createApiKey: async (label: string) => {
    // Note: passing as query param for simplicity given current backend implementation.
    // In a stricter setup, might be a JSON body.
    const { data } = await api.post(`/auth/apikeys?label=${encodeURIComponent(label)}`);
    return data;
  },

  revokeApiKey: async (id: number) => {
    await api.delete(`/auth/apikeys/${id}`);
  }
};
