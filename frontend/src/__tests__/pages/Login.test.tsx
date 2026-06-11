import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Explicit factory so Vitest never evaluates auth.ts (which reads localStorage at module init)
vi.mock('@/store/auth', () => ({ useAuthStore: vi.fn() }));
vi.mock('@/api/auth', () => ({ authApi: { login: vi.fn() } }));
vi.mock('jwt-decode', () => ({ jwtDecode: vi.fn(() => ({ sub: '1', role: 'admin' })) }));
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

const mockNavigate = vi.fn();

import { Login } from '@/pages/Login';
import { useAuthStore } from '@/store/auth';
import { authApi } from '@/api/auth';

const mockSetAuth = vi.fn();
const mockUseAuthStore = vi.mocked(useAuthStore);
const mockLogin = vi.mocked(authApi.login);

function renderLogin() {
  return render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>
  );
}

describe('Login', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const fakeState = { token: null, user: null, setAuth: mockSetAuth, clearAuth: vi.fn() };
    mockUseAuthStore.mockImplementation((selector: (state: typeof fakeState) => unknown) => selector(fakeState));
  });

  it('affiche le formulaire de connexion', () => {
    renderLogin();
    expect(screen.getByLabelText('Adresse email')).toBeInTheDocument();
    expect(screen.getByLabelText('Mot de passe')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Se connecter' })).toBeInTheDocument();
  });

  it('affiche le bouton GitLab', () => {
    renderLogin();
    expect(screen.getByText(/Continuer avec GitLab/i)).toBeInTheDocument();
  });

  it('login réussi : appelle setAuth et navigue vers /', async () => {
    mockLogin.mockResolvedValueOnce({ access_token: 'fake-jwt', token_type: 'bearer' });
    const user = userEvent.setup();

    renderLogin();
    await user.type(screen.getByLabelText('Adresse email'), 'admin@test.com');
    await user.type(screen.getByLabelText('Mot de passe'), 'adminpass');
    await user.click(screen.getByRole('button', { name: 'Se connecter' }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('admin@test.com', 'adminpass');
      expect(mockSetAuth).toHaveBeenCalled();
      expect(mockNavigate).toHaveBeenCalledWith('/');
    });
  });

  it("login échoué : affiche le message d'erreur", async () => {
    mockLogin.mockRejectedValueOnce({
      response: { data: { detail: 'Incorrect email or password' } },
    });
    const user = userEvent.setup();

    renderLogin();
    await user.type(screen.getByLabelText('Adresse email'), 'wrong@test.com');
    await user.type(screen.getByLabelText('Mot de passe'), 'badpass');
    await user.click(screen.getByRole('button', { name: 'Se connecter' }));

    await waitFor(() => {
      expect(screen.getByText('Incorrect email or password')).toBeInTheDocument();
    });
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("affiche 'Connexion échouée' si pas de detail dans l'erreur", async () => {
    mockLogin.mockRejectedValueOnce(new Error('Network error'));
    const user = userEvent.setup();

    renderLogin();
    await user.type(screen.getByLabelText('Adresse email'), 'a@b.com');
    await user.type(screen.getByLabelText('Mot de passe'), 'pass');
    await user.click(screen.getByRole('button', { name: 'Se connecter' }));

    await waitFor(() => {
      expect(screen.getByText('Connexion échouée')).toBeInTheDocument();
    });
  });

  it('bascule la visibilité du mot de passe', async () => {
    const user = userEvent.setup();
    renderLogin();

    const input = screen.getByLabelText('Mot de passe');
    expect(input).toHaveAttribute('type', 'password');

    const toggle = input.closest('.form-input-wrap')!.querySelector('button')!;
    await user.click(toggle);
    expect(input).toHaveAttribute('type', 'text');

    await user.click(toggle);
    expect(input).toHaveAttribute('type', 'password');
  });
});
