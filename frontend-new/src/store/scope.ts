import { create } from 'zustand';

type ScopeType = 'group' | 'admin';

interface ScopeState {
  activeScope: ScopeType;
  activeGroupSlug: string | null;
  setScope: (scope: ScopeType, groupSlug?: string) => void;
}

export const useScopeStore = create<ScopeState>((set) => ({
  activeScope: 'group',
  activeGroupSlug: null,
  setScope: (scope, groupSlug) =>
    set({ activeScope: scope, activeGroupSlug: groupSlug ?? null }),
}));
