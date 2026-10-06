import { api } from './client';
import { AuditLog } from '@/types';

export interface AuditLogFilters {
  since?: string;
  until?: string;
  action_prefix?: string[];
}

export const auditApi = {
  async list(limit = 100, offset = 0, filters: AuditLogFilters = {}): Promise<AuditLog[]> {
    const res = await api.get<AuditLog[]>('/audit/', {
      params: { limit, offset, ...filters },
      // action_prefix=a&action_prefix=b (FastAPI), pas action_prefix[]=…
      paramsSerializer: { indexes: null },
    });
    return res.data;
  },

  async exportCsv(filters: AuditLogFilters = {}): Promise<Blob> {
    const res = await api.get('/audit/export', { params: filters, responseType: 'blob' });
    return res.data;
  },
};
