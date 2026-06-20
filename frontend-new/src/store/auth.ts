import { create } from 'zustand';
import { UserMe } from '@/types';

interface AuthState {
  token: string | null;
  user: UserMe | null;
  setAuth: (token: string, user: UserMe) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: localStorage.getItem('token'),
  user: localStorage.getItem('user')
    ? (JSON.parse(localStorage.getItem('user') as string) as UserMe)
    : null,

  setAuth: (token, user) => {
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(user));
    set({ token, user });
  },

  clearAuth: () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    set({ token: null, user: null });
  },
}));
