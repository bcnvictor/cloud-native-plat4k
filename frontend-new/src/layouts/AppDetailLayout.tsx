import { useEffect, createContext, useContext } from 'react';
import { Outlet, useNavigate, useParams, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { IconBrandGitlab, IconDots, IconBrandDocker } from '@tabler/icons-react';
import { appsApi } from '@/api/apps';
import { useScopeStore } from '@/store/scope';
import { Application } from '@/types';
import { AppStatusBadge } from '@/components/AppStatusBadge';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { getAppHealth } from '@/utils/appHealth';
import { cn } from '@/utils/cn';
import { useBreadcrumb } from '@/components/nav/BreadcrumbContext';

interface AppDetailContext {
  app: Application | null;
  isLoading: boolean;
}

const Ctx = createContext<AppDetailContext>({ app: null, isLoading: false });
export const useAppDetail = () => useContext(Ctx);

const TABS = [
  { key: '', label: 'Overview' },
  { key: 'logs', label: 'Logs' },
  { key: 'history', label: 'History' },
  { key: 'settings', label: 'Settings' },
  { key: 'assistant', label: 'Assistant' },
];

export function AppDetailLayout() {
  const { slug, appSlug } = useParams<{ slug: string; appSlug: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { setScope } = useScopeStore();
  const { setBreadcrumb } = useBreadcrumb();

  useEffect(() => {
    if (slug) setScope('group', slug);
  }, [slug, setScope]);

  const { data: app, isLoading } = useQuery({
    queryKey: ['app', appSlug],
    queryFn: () => appsApi.getBySlug(appSlug!),
    enabled: !!appSlug,
    refetchInterval: 30_000,
    staleTime: 25_000,
  });

  useEffect(() => {
    setBreadcrumb([
      { label: 'Apps', to: `/groups/${slug}/apps` },
      { label: app?.name ?? appSlug ?? '' },
    ]);
    return () => setBreadcrumb([]);
  }, [app?.name, appSlug, slug, setBreadcrumb]);

  const health = app ? getAppHealth(app) : 'stopped';
  const basePath = `/groups/${slug}/apps/${appSlug}`;

  function activeTab(): string {
    return location.pathname.replace(basePath, '').replace(/^\//, '');
  }

  function navigateTo(tabKey: string) {
    navigate(tabKey ? `${basePath}/${tabKey}` : basePath);
  }

  return (
    <Ctx.Provider value={{ app: app ?? null, isLoading }}>
      {/* ── Header zone — full-bleed ── */}
      <div className="bg-background border-b border-border sticky top-0 z-30 w-full">
        <div className="max-w-[1440px] mx-auto px-8">
          {/* App identity row */}
          <div className="flex items-center gap-3 py-3">
            {isLoading ? (
              <Spinner size="md" />
            ) : (
              <>
                <div className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0" style={{ background: 'linear-gradient(135deg, #0C1236 0%, #007BA7 100%)' }}>
                  <IconBrandDocker size={24} color="white" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <h1 className="text-xl font-bold tracking-tight text-foreground">{app?.name ?? appSlug}</h1>
                    {app && <AppStatusBadge status={health} />}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {app?.origin ?? 'scaffold'} · {app?.framework ?? 'app'} · {slug}
                  </p>
                </div>
                <div className="flex items-center gap-1.5">
                  {app?.source_url && (
                    <Button
                      variant="secondary"
                      size="sm"
                      icon={<IconBrandGitlab size={14} />}
                      onClick={() => window.open(app.source_url!, '_blank')}
                    >
                      GitLab
                    </Button>
                  )}
                  <Button variant="ghost" size="sm">
                    <IconDots size={15} />
                  </Button>
                </div>
              </>
            )}
          </div>

          {/* Unhealthy alert */}
          {health === 'unhealthy' && (
            <div className="flex items-center gap-2 py-2 mb-1 px-3 bg-danger-subtle rounded-md text-xs text-danger-text">
              <span>⚠</span>
              <span>The application is in error.</span>
              <button className="underline ml-auto" onClick={() => navigateTo('logs')}>
                View logs
              </button>
            </div>
          )}

          {/* Tab bar — flush to bottom of header */}
          <div className="flex">
            {TABS.map((tab) => {
              const isActive = tab.key === activeTab();
              return (
                <button
                  key={tab.key}
                  onClick={() => navigateTo(tab.key)}
                  className={cn(
                    'px-4 py-2.5 text-sm -mb-px border-b-2 transition-colors',
                    isActive
                      ? 'font-medium text-primary border-primary'
                      : 'text-muted-foreground border-transparent hover:text-foreground'
                  )}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Content zone — gray page background ── */}
      <div className="bg-background-subtle">
        <div className="max-w-[1440px] mx-auto px-8 py-6">
          <Outlet />
        </div>
      </div>
    </Ctx.Provider>
  );
}
