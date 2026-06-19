import { api } from './client';
import type { UserMe } from '../types';

export const usersApi = {
  getMe: () => api.get<UserMe>('/users/me').then(r => r.data),
};
