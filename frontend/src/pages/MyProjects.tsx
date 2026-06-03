import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { gitlabApi, GitLabProject } from '@/api/gitlab';
import { timeAgo } from '@/utils/timeAgo';

const TEMPLATES = [
  { name: 'FastAPI — Python', desc: 'API REST async avec FastAPI, SQLAlchemy et Dockerfile prêt à déployer.', tags: ['Python', 'FastAPI', 'Docker'], available: true, icon: 'PY', iconBg: 'rgba(59,130,246,0.1)', iconColor: '#3B82F6' },
  { name: 'React — TypeScript', desc: 'SPA React avec Vite, TailwindCSS et Nginx en production.', tags: ['TypeScript', 'Vite'], available: false, icon: 'RE', iconBg: 'rgba(6,182,212,0.1)', iconColor: '#06B6D4' },
  { name: 'Node.js — Worker', desc: 'Worker async avec Bull, Redis et gestion de jobs en file.', tags: ['Node.js', 'Redis'], available: false, icon: 'NJ', iconBg: 'rgba(16,185,129,0.1)', iconColor: '#10B981' },
  { name: 'Go — Microservice', desc: 'Service Go minimaliste avec chi router et healthcheck intégré.', tags: ['Go', 'chi'], available: false, icon: 'GO', iconBg: 'rgba(99,102,241,0.1)', iconColor: '#6366F1' },
  { name: 'Next.js — Fullstack', desc: 'Application fullstack avec App Router et déploiement conteneurisé.', tags: ['Next.js', 'SSR'], available: false, icon: 'NX', iconBg: 'rgba(0,0,0,0.06)', iconColor: '#374151' },
  { name: 'Spring Boot — Java', desc: 'Service Java avec Spring Boot et build Maven multi-stage.', tags: ['Java', 'Spring'], available: false, icon: 'JV', iconBg: 'rgba(239,68,68,0.08)', iconColor: '#EF4444' },
];

const LANG_COLORS: Record<string, string> = {
  Python: '#3B82F6',
  TypeScript: '#06B6D4',
  JavaScript: '#F59E0B',
  Go: '#6366F1',
  Java: '#EF4444',
  Ruby: '#DC2626',
};

export const MyProjects = () => {
  const [toast, setToast] = useState<string | null>(null);

  const { data: projects = [], isLoading, isError } = useQuery({
    queryKey: ['gitlab-projects'],
    queryFn: () => gitlabApi.listProjects(),
  });

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  };

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Templates &amp; Repos</span>
      </div>

      <div className="page-content">
        {/* Templates */}
        <div>
          <div className="section-header">
            <div>
              <span className="section-title-text">Templates</span>
              <span className="section-sub">Scaffoldez une nouvelle application en quelques secondes</span>
            </div>
          </div>
          <div className="templates-grid">
            {TEMPLATES.map(t => (
              <div
                key={t.name}
                className={`template-card ${t.available ? 'available' : 'coming'}`}
                onClick={() => t.available && showToast('Coming soon')}
              >
                <div className="template-icon" style={{ background: t.iconBg, color: t.iconColor }}>
                  {t.icon}
                </div>
                <div>
                  <div className="template-name">{t.name}</div>
                  <div className="template-desc">{t.desc}</div>
                </div>
                <div className="template-footer">
                  <div className="template-tags">
                    {t.tags.map(tg => <span key={tg} className="tag">{tg}</span>)}
                  </div>
                  {t.available
                    ? <span className="use-btn">Utiliser <i className="ti ti-arrow-right" aria-hidden="true" /></span>
                    : <span className="coming-badge">bientôt</span>}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Repos */}
        <div>
          <div className="section-header">
            <div>
              <span className="section-title-text">Repositories GitLab</span>
              <span className="section-sub">Vos repos disponibles</span>
            </div>
          </div>

          {isLoading ? (
            <div className="loading-state">
              <i className="ti ti-loader-2" aria-hidden="true" style={{ fontSize: 16 }} />
              Chargement des projets GitLab…
            </div>
          ) : isError ? (
            <div className="alert error">
              <i className="ti ti-alert-circle" aria-hidden="true" />
              Impossible de charger les projets. Vérifiez que GitLab est connecté dans Paramètres.
            </div>
          ) : projects.length === 0 ? (
            <div className="card">
              <div className="empty-state">
                <i className="ti ti-git-branch" />
                <div className="empty-state-title">Aucun projet GitLab</div>
                <div className="empty-state-desc">Connectez votre compte GitLab dans Paramètres pour voir vos repos.</div>
              </div>
            </div>
          ) : (
            <div className="repos-list">
              {projects.map((p: GitLabProject) => {
                const lang = (p as any).language ?? 'Python';
                const color = LANG_COLORS[lang] ?? '#94A3B8';
                return (
                  <div key={p.id} className="repo-row">
                    <i className="ti ti-git-branch" style={{ color: 'var(--text-muted)', fontSize: 15 }} aria-hidden="true" />
                    <div className="repo-info">
                      <div className="repo-name">{p.name}</div>
                      <div className="repo-url">{p.path_with_namespace}</div>
                    </div>
                    <div className="repo-meta">
                      <span className="repo-lang">
                        <span className="lang-dot" style={{ background: color }} />{lang}
                      </span>
                      <span className="repo-updated">{timeAgo(p.last_activity_at)}</span>
                    </div>
                    <a
                      href={p.web_url}
                      target="_blank"
                      rel="noreferrer"
                      className="import-btn imported"
                      onClick={e => e.stopPropagation()}
                    >
                      <i className="ti ti-external-link" style={{ fontSize: 11 }} aria-hidden="true" />
                      Ouvrir
                    </a>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {toast && <div className="toast">{toast}</div>}
    </>
  );
};
