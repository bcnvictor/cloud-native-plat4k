import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';
import { authApi } from '@/api/auth';
import { groupsApi } from '@/api/groups';
import { Spinner } from '@/components/ui/Spinner';

export function OAuthCallback() {
  const navigate = useNavigate();
  const { setAuth } = useAuthStore();

  useEffect(() => {
    async function handleCallback() {
      // Backend sends the token in the URL fragment: #access_token=...&user_id=...
      const hash = window.location.hash.slice(1); // strip leading '#'
      const params = new URLSearchParams(hash);
      const token = params.get('access_token');

      if (!token) {
        navigate('/login');
        return;
      }

      try {
        // Set the token in the store first so the axios interceptor can use it
        // for the /users/me call. We pass a temporary placeholder user.
        const tempUser = await authApi.meWithToken(token);
        setAuth(token, tempUser);
        const groups = await groupsApi.getMyGroups();
        const firstSlug = groups[0] ? groupsApi.getSlug(groups[0]) : null;
        navigate(firstSlug ? `/groups/${firstSlug}` : '/login');
      } catch {
        navigate('/login');
      }
    }
    handleCallback();
  }, []);

  return (
    <div className="flex items-center justify-center h-screen bg-background-subtle">
      <Spinner size="lg" />
    </div>
  );
}
