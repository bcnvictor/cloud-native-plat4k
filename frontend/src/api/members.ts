import { api } from './client';
import type { AppMember, GroupMembership, MyAccess } from '../types';

export const membersApi = {
  listAppMembers: (appId: number) =>
    api.get<AppMember[]>(`/apps/${appId}/members`).then(r => r.data),

  getMyAccess: (appId: number) =>
    api.get<MyAccess>(`/apps/${appId}/my-access`).then(r => r.data),

  getMyGroups: () =>
    api.get<GroupMembership[]>('/users/me/groups').then(r => r.data),

  getUserGroups: (userId: number) =>
    api.get<GroupMembership[]>(`/users/${userId}/groups`).then(r => r.data),

  syncTeams: () =>
    api.post<{ skipped?: boolean }>('/users/me/sync-teams').then(r => r.data),
};
