import { describe, it, expect, beforeEach, vi } from 'vitest';

// vi.hoisted runs before any imports — needed for Node.js 22+ where localStorage
// is defined as a non-configurable experimental global that jsdom cannot replace.
const localStorageMock = vi.hoisted(() => {
  let store: Record<string, string> = {};
  const mock = {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, val: string) => { store[key] = val; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
    get length() { return Object.keys(store).length; },
    key: (_: number) => null,
  };
  Object.defineProperty(globalThis, 'localStorage', { value: mock, writable: true, configurable: true });
  return mock;
});

import { useAuthStore } from '@/store/auth';
import type { User } from '@/types';

const mockUser: User = {
  id: 1,
  email: 'test@example.com',
  role: 'admin',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
};

describe('useAuthStore', () => {
  beforeEach(() => {
    localStorageMock.clear();
    useAuthStore.setState({ token: null, user: null });
  });

  it('est initialement vide si localStorage est vide', () => {
    const { token, user } = useAuthStore.getState();
    expect(token).toBeNull();
    expect(user).toBeNull();
  });

  it("setAuth persiste le token et l'utilisateur", () => {
    useAuthStore.getState().setAuth('my-token', mockUser);

    const { token, user } = useAuthStore.getState();
    expect(token).toBe('my-token');
    expect(user).toEqual(mockUser);
    expect(localStorageMock.getItem('token')).toBe('my-token');
    expect(JSON.parse(localStorageMock.getItem('user')!)).toEqual(mockUser);
  });

  it("clearAuth supprime le token et l'utilisateur", () => {
    useAuthStore.getState().setAuth('my-token', mockUser);
    useAuthStore.getState().clearAuth();

    const { token, user } = useAuthStore.getState();
    expect(token).toBeNull();
    expect(user).toBeNull();
    expect(localStorageMock.getItem('token')).toBeNull();
    expect(localStorageMock.getItem('user')).toBeNull();
  });

  it('setAuth écrase une session précédente', () => {
    const otherUser: User = { ...mockUser, id: 2, email: 'other@example.com' };
    useAuthStore.getState().setAuth('token-1', mockUser);
    useAuthStore.getState().setAuth('token-2', otherUser);

    const { token, user } = useAuthStore.getState();
    expect(token).toBe('token-2');
    expect(user?.email).toBe('other@example.com');
  });

  it('se réhydrate depuis localStorage', () => {
    localStorageMock.setItem('token', 'persisted-token');
    localStorageMock.setItem('user', JSON.stringify(mockUser));

    useAuthStore.setState({
      token: localStorageMock.getItem('token'),
      user: JSON.parse(localStorageMock.getItem('user')!),
    });

    expect(useAuthStore.getState().token).toBe('persisted-token');
    expect(useAuthStore.getState().user?.email).toBe('test@example.com');
  });
});
