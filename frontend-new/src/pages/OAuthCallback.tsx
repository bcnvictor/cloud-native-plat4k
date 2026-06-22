import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';
import { authApi } from '@/api/auth';
import { groupsApi } from '@/api/groups';
import { toast } from '@/components/ui/toast';

const POLL_INTERVAL_MS = 2000;
const POLL_MAX_ATTEMPTS = 10;

export function OAuthCallback() {
  const navigate = useNavigate();
  const { setAuth } = useAuthStore();

  const [syncing, setSyncing] = useState(false);
  const [progress, setProgress] = useState(15);

  useEffect(() => {
    if (!syncing) return;

    const interval = setInterval(() => {
      setProgress((p) => Math.min(p + 8, 90));
    }, 1000);

    return () => clearInterval(interval);
  }, [syncing]);

  useEffect(() => {
    async function handleCallback() {
      const hash = window.location.hash.slice(1);
      const params = new URLSearchParams(hash);
      const token = params.get('access_token');

      if (!token) {
        toast({ title: 'GitLab sign-in failed', description: 'No token received — try again or contact an admin.', variant: 'destructive' });
        navigate('/login');
        return;
      }

      try {
        const tempUser = await authApi.meWithToken(token);

        setProgress(25);

        setAuth(token, tempUser);

        let groups = await groupsApi.getMyGroups();

        setProgress(40);

        if (groups.length === 0 && !tempUser.is_admin) {
          setSyncing(true);

          for (let i = 0; i < POLL_MAX_ATTEMPTS; i++) {
            await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));

            groups = await groupsApi.getMyGroups();

            if (groups.length > 0) {
              setProgress(100);
              break;
            }
          }

          setSyncing(false);
        } else {
          setProgress(100);
        }

        const firstSlug = groups[0]
        ? groupsApi.getSlug(groups[0])
        : null;

        setTimeout(() => {
          if (firstSlug) navigate(`/groups/${firstSlug}`);
          else if (tempUser.is_admin) navigate('/admin/clusters');
          else navigate('/');
        }, 250);
      } catch {
        toast({ title: 'Sign-in error', description: 'Something went wrong during authentication. Please try again.', variant: 'destructive' });
        navigate('/login');
      }
    }

    handleCallback();
  }, [navigate, setAuth]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background-subtle px-6">
    <div className="w-full max-w-md rounded-lg border border-border bg-card p-8 shadow-sm">
    <div className="space-y-6">
    <div className="space-y-2 text-center">
    <h1 className="text-xl font-semibold text-foreground">
    {syncing
      ? 'Preparing your workspace'
  : 'Signing you in'}
  </h1>

  <p className="text-sm text-muted-foreground">
  {syncing
    ? 'Creating your workspace and synchronizing your profile.'
  : 'Authenticating your account.'}
  </p>
  </div>

  <div className="space-y-3">
  <div className="h-2 overflow-hidden rounded-full bg-muted">
  <div
  className="h-full rounded-full bg-primary transition-all duration-700 ease-out"
  style={{ width: `${progress}%` }}
  />
  </div>

  <p className="text-center text-xs text-muted-foreground">
  {syncing
    ? 'Setting up workspace...'
  : 'Verifying account...'}
  </p>
  </div>
  </div>
  </div>
  </div>
  );
}
