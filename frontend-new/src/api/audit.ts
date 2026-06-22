import { api } from './client';
import { AuditLog } from '@/types';

export const auditApi = {
  async list(limit = 100, offset = 0): Promise<AuditLog[]> {
    const res = await api.get<AuditLog[]>('/audit/', { params: { limit, offset } });
    return res.data;
  },
};
