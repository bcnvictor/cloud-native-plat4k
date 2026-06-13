import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';
import { jwtDecode } from 'jwt-decode';
import type { CnpJwtPayload } from '@/types';

export const OAuthCallback = () => {
  const navigate = useNavigate();
  const setAuth = useAuthStore((state) => state.setAuth);

  useEffect(() => {
    let cancelled = false;

    const hash = window.location.hash.startsWith('#')
      ? window.location.hash.slice(1)
      : window.location.hash;
    const params = new URLSearchParams(hash);
    const accessToken = params.get('access_token');

    if (!accessToken) {
      navigate('/login');
      return;
    }

    const email = params.get('email') || '';
    const userIdParam = params.get('user_id');

    try {
      const payload = jwtDecode<CnpJwtPayload>(accessToken);
      const userId = userIdParam ? parseInt(userIdParam, 10) : parseInt(payload.sub);
      // Prefer role from signed JWT payload; fall back to URL param as last resort
      const role = ((payload.role ?? params.get('role') ?? 'viewer') as 'admin' | 'viewer');
      if (!cancelled) {
        setAuth(accessToken, {
          id: userId,
          email: email || 'gitlab-user',
          role,
          is_active: true,
          created_at: new Date().toISOString(),
        });
        navigate('/');
      }
    } catch {
      if (!cancelled) navigate('/login');
    }

    return () => { cancelled = true; };
  }, [navigate, setAuth]);

  return <div className="loading-state">Connexion en cours…</div>;
};
