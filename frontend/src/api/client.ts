import axios from 'axios';
import { useAuthStore } from '@/store/auth';

// Create base instance
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api/v1',
  withCredentials: true, // important for sending/receiving the refresh token cookie
});

// Request interceptor to add token
api.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Shared in-flight refresh promise — prevents concurrent 401s from each triggering an independent refresh
let refreshPromise: Promise<string> | null = null;

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry && originalRequest.url !== '/auth/login') {
      originalRequest._retry = true;

      try {
        if (!refreshPromise) {
          refreshPromise = axios
            .post(`${import.meta.env.VITE_API_URL || '/api/v1'}/auth/refresh`, {}, { withCredentials: true })
            .then((res) => res.data.access_token)
            .finally(() => { refreshPromise = null; });
        }

        const access_token = await refreshPromise;
        const user = useAuthStore.getState().user;
        if (user) {
          useAuthStore.getState().setAuth(access_token, user);
        }

        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return api(originalRequest);
      } catch (refreshError) {
        useAuthStore.getState().clearAuth();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);
