import { api } from './client';
import type { DependencySearchResponse } from '@/types';

export interface DependencyFilters {
  q?: string;
  version?: string;
  ecosystem?: string;
  limit?: number;
  offset?: number;
}

export const dependenciesApi = {
  async search(filters: DependencyFilters): Promise<DependencySearchResponse> {
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== undefined && v !== ''));
    const res = await api.get<DependencySearchResponse>('/admin/dependencies', { params });
    return res.data;
  },
};
