import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// Explicit factory so Vitest never evaluates auth.ts (which reads localStorage at module init)
vi.mock('@/store/auth', () => ({ useAuthStore: vi.fn() }));

import { useAuthStore } from '@/store/auth';
import { ProtectedRoute } from '@/router/ProtectedRoute';
import type { User } from '@/types';

const mockUseAuthStore = vi.mocked(useAuthStore);

const adminUser: User = {
  id: 1,
  email: 'admin@test.com',
  role: 'admin',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
};

const devUser: User = {
  id: 2,
  email: 'dev@test.com',
  role: 'dev',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
};

function renderRoute(initialPath: string, requiredRole?: 'admin' | 'dev' | 'viewer') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/login" element={<div>Page Login</div>} />
        <Route path="/dashboard" element={<div>Dashboard</div>} />
        <Route element={<ProtectedRoute requiredRole={requiredRole} />}>
          <Route path="/protected" element={<div>Contenu protégé</div>} />
          <Route path="/admin/users" element={<div>Admin Users</div>} />
        </Route>
      </Routes>
    </MemoryRouter>
  );
}

describe('ProtectedRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('redirige vers /login si non authentifié', () => {
    mockUseAuthStore.mockReturnValue({ token: null, user: null } as ReturnType<typeof useAuthStore>);
    renderRoute('/protected');
    expect(screen.getByText('Page Login')).toBeInTheDocument();
  });

  it('affiche le contenu si authentifié sans rôle requis', () => {
    mockUseAuthStore.mockReturnValue({ token: 'tok', user: devUser } as ReturnType<typeof useAuthStore>);
    renderRoute('/protected');
    expect(screen.getByText('Contenu protégé')).toBeInTheDocument();
  });

  it("affiche le contenu si l'utilisateur est admin (bypass rôle)", () => {
    mockUseAuthStore.mockReturnValue({ token: 'tok', user: adminUser } as ReturnType<typeof useAuthStore>);
    renderRoute('/admin/users', 'admin');
    expect(screen.getByText('Admin Users')).toBeInTheDocument();
  });

  it('redirige vers /dashboard si rôle insuffisant', () => {
    mockUseAuthStore.mockReturnValue({ token: 'tok', user: devUser } as ReturnType<typeof useAuthStore>);
    renderRoute('/admin/users', 'admin');
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
  });

  it('autorise un dev à accéder à une route requérant dev', () => {
    mockUseAuthStore.mockReturnValue({ token: 'tok', user: devUser } as ReturnType<typeof useAuthStore>);
    renderRoute('/protected', 'dev');
    expect(screen.getByText('Contenu protégé')).toBeInTheDocument();
  });
});
