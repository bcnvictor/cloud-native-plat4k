import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi } from '@/api/auth';
import { useAuthStore } from '@/store/auth';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Toaster } from '@/components/ui/toast';
import { IconBrandGitlab } from '@tabler/icons-react';

export function Login() {
  const navigate = useNavigate();
  const { setAuth } = useAuthStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    document.body.style.zoom = '1';
    return () => { document.body.style.zoom = ''; };
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const { access_token } = await authApi.login(email, password);
      // Fetch user profile with the token explicitly — store isn't populated yet
      const user = await authApi.meWithToken(access_token);
      setAuth(access_token, user);
      navigate('/');
    } catch {
      setError('Incorrect email or password.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="force-light h-screen flex items-center justify-center bg-dotted">
      <Toaster />
      <div className="flex flex-col items-center gap-6 w-full max-w-sm mx-auto">
        {/* Logo */}
        <div className="w-20 h-20 rounded-2xl bg-[#0C1236] flex items-center justify-center shrink-0 overflow-hidden">
          <img src="/favicon.svg" className="w-12 h-12 object-contain" alt="CNP" />
        </div>

        <div className="bg-card border border-border rounded-lg p-8 shadow-sm w-full">
          <h1 className="text-xl font-semibold text-foreground mb-1">
            Cloud Native Platform
          </h1>
          <p className="text-sm text-muted-foreground mb-6">
            Sign in to your workspace
          </p>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <Input
              label="Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              autoFocus
            />
            <Input
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />

            {error && <p className="text-xs text-danger-text">{error}</p>}

            <Button variant="primary" type="submit" loading={loading} className="w-full justify-center mt-1">
              Sign in
            </Button>
          </form>

          <div className="flex items-center gap-3 my-4">
            <div className="flex-1 border-t border-border" />
            <span className="text-xs text-muted-foreground">or</span>
            <div className="flex-1 border-t border-border" />
          </div>

          <Button
            variant="secondary"
            className="w-full justify-center"
            icon={<IconBrandGitlab size={16} />}
            onClick={() => authApi.initiateGitLab()}
          >
            Continue with GitLab
          </Button>
        </div>
      </div>
    </div>
  );
}
