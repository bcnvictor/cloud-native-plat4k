import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';
import { jwtDecode } from 'jwt-decode';

export const OAuthCallback = () => {
  const navigate = useNavigate();
  const setAuth = useAuthStore((state) => state.setAuth);

  useEffect(() => {
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
    const role = (params.get('role') || 'viewer') as 'admin' | 'viewer';
    const userIdParam = params.get('user_id');

    try {
      const payload: any = jwtDecode(accessToken);
      const userId = userIdParam ? parseInt(userIdParam, 10) : parseInt(payload.sub);
      setAuth(accessToken, {
        id: userId,
        email: email || 'gitlab-user',
        role,
        is_active: true,
        created_at: new Date().toISOString(),
      });
      navigate('/dashboard');
    } catch {
      navigate('/login');
    }
  }, [navigate, setAuth]);

  return <div className="min-h-screen flex items-center justify-center">Signing you in...</div>;
};
