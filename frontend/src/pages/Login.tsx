import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi } from '@/api/auth';
import { useAuthStore } from '@/store/auth';
import { jwtDecode } from 'jwt-decode';
import type { UserRole, CnpJwtPayload } from '@/types';

export const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPwd, setShowPwd] = useState(false);
  const navigate = useNavigate();
  const setAuth = useAuthStore((state) => state.setAuth);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await authApi.login(email, password);
      const payload = jwtDecode<CnpJwtPayload>(data.access_token);
      setAuth(data.access_token, {
        id: parseInt(payload.sub),
        email,
        role: (payload.role ?? 'viewer') as UserRole,
        is_active: true,
        created_at: new Date().toISOString(),
      });
      navigate('/');
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
      if (Array.isArray(detail)) setError((detail as Array<{ msg: string }>).map((e) => e.msg).join('. '));
      else setError(typeof detail === 'string' ? detail : 'Connexion échouée');
    } finally {
      setLoading(false);
    }
  };

  const handleGitLab = () => {
    const base = import.meta.env.VITE_API_URL || '/api/v1';
    window.location.href = `${base}/auth/gitlab/authorize`;
  };

  return (
    <div className="login-page">
      <div className="login-box">
        <div className="login-logo">
          <img src="/logo.png" alt="Plat4k" className="login-logo-icon" width="36" height="36" />
          <div>
            <div className="login-logo-name">CNP</div>
            <div className="login-logo-sub">Cloud Native Plat4k</div>
          </div>
        </div>

        <div className="login-title">Connexion</div>
        <div className="login-sub">Accédez à votre espace développeur</div>

        <form className="login-form" onSubmit={handleSubmit}>
          {error && (
            <div className="login-error">
              <i className="ti ti-alert-circle" aria-hidden="true" style={{ marginRight: 6 }} />
              {error}
            </div>
          )}

          <div className="form-group">
            <label className="form-label" htmlFor="email">Adresse email</label>
            <input
              id="email"
              type="email"
              required
              className="form-input"
              placeholder="vous@example.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              autoComplete="email"
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="password">Mot de passe</label>
            <div className="form-input-wrap">
              <input
                id="password"
                type={showPwd ? 'text' : 'password'}
                required
                className="form-input"
                placeholder="••••••••"
                value={password}
                onChange={e => setPassword(e.target.value)}
                autoComplete="current-password"
              />
              <button
                type="button"
                className="form-input-action"
                onClick={() => setShowPwd(v => !v)}
                tabIndex={-1}
              >
                <i className={`ti ${showPwd ? 'ti-eye-off' : 'ti-eye'}`} aria-hidden="true" />
              </button>
            </div>
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading}
            style={{ width: '100%', justifyContent: 'center', padding: '9px 16px' }}
          >
            {loading ? (
              <><i className="ti ti-loader-2" style={{ animation: 'spin 1s linear infinite' }} aria-hidden="true" /> Connexion…</>
            ) : (
              'Se connecter'
            )}
          </button>

          <div className="login-divider">ou</div>

          <button type="button" className="login-gitlab-btn" onClick={handleGitLab}>
            <i className="ti ti-brand-gitlab" aria-hidden="true" style={{ fontSize: 16 }} />
            Continuer avec GitLab EPITA
          </button>
        </form>
      </div>

    </div>
  );
};
