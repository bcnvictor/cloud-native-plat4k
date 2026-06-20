import { api } from './client';
import { AdminUser, UserRole } from '@/types';

export const usersApi = {
  async list(): Promise<AdminUser[]> {
    const res = await api.get<AdminUser[]>('/users/');
    return res.data;
  },

  async patch(id: number, payload: { role?: UserRole; is_active?: boolean }): Promise<AdminUser> {
    const res = await api.patch<AdminUser>(`/users/${id}`, payload);
    return res.data;
  },
};
