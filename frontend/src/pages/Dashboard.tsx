import { useQuery } from '@tanstack/react-query';
import { resourcesApi } from '@/api/resources';

const LOGS = [
  { ts: '10:42:31', app: 'api-gateway', level: 'INFO', msg: 'GET /api/v1/health 200 — 4ms' },
  { ts: '10:42:29', app: 'api-gateway', level: 'INFO', msg: 'JWT validated — request forwarded' },
  { ts: '10:42:27', app: 'payment-worker', level: 'ERROR', msg: 'Stripe webhook signature mismatch — aborting' },
  { ts: '10:42:25', app: 'payment-worker', level: 'ERROR', msg: 'CrashLoopBackOff: container exited with code 1' },
  { ts: '10:42:22', app: 'user-service', level: 'INFO', msg: 'Pod starting…' },
  { ts: '10:42:20', app: 'user-service', level: 'WARN', msg: 'Readiness probe failed — retrying in 5s' },
  { ts: '10:42:18', app: 'frontend-app', level: 'INFO', msg: 'GET /dashboard 200 — 12ms' },
  { ts: '10:42:15', app: 'api-gateway', level: 'INFO', msg: 'Rate limit reached for /auth — 429 returned' },
];

type Panel = {
  title: string;
  color: string;
  type: 'line' | 'bar' | 'line2';
  getValue: (running: number, total: number) => string;
};

const PANELS: Panel[] = [
  {
    title: 'Cluster — Ressources actives',
    color: '#10B981',
    type: 'line',
    getValue: (running, total) => `${running} / ${total}`,
  },
  {
    title: 'FinOps — Coût / jour',
    color: '#F59E0B',
    type: 'bar',
    getValue: () => '€2.14',
  },
  {
    title: 'Latence p95',
    color: '#93B8FA',
    type: 'line2',
    getValue: () => '142ms',
  },
];

function Chart({ color, type }: { color: string; type: Panel['type'] }) {
  if (type === 'bar') {
    return (
      <svg width="100%" height="64" viewBox="0 0 200 64" preserveAspectRatio="none">
        {[8, 32, 56, 80, 104, 128, 152, 176].map((x, i) => (
          <rect key={x} x={x} y={64 - (20 + i * 4)} width="16" height={20 + i * 4} fill={color} opacity={0.5 + i * 0.07} rx="2" />
        ))}
      </svg>
    );
  }
  const d = type === 'line'
    ? 'M0,48 C20,40 40,36 60,32 C80,28 100,25 120,22 C140,18 160,16 180,18 C190,14 200,18 200,18'
    : 'M0,32 C20,28 40,34 60,18 C80,16 100,26 120,22 C140,20 160,28 200,24';
  const cy = type === 'line' ? 18 : 24;
  return (
    <svg width="100%" height="64" viewBox="0 0 200 64" preserveAspectRatio="none">
      <defs>
        <linearGradient id={`g-${type}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${d} L200,64 L0,64 Z`} fill={`url(#g-${type})`} />
      <path d={d} stroke={color} strokeWidth="1.5" fill="none" />
      <circle cx="200" cy={cy} r="3" fill={color} />
    </svg>
  );
}

export const Dashboard = () => {
  const { data: resources, isLoading } = useQuery({
    queryKey: ['resources'],
    queryFn: () => resourcesApi.list(),
  });

  const total = resources?.length ?? 0;
  const running = resources?.filter(r => r.status === 'running').length ?? 0;

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Monitoring</span>
      </div>

      <div className="page-content">
        {isLoading ? (
          <div className="loading-state">
            <i className="ti ti-loader-2" aria-hidden="true" style={{ fontSize: 16, animation: 'spin 1s linear infinite' }} />
            Chargement…
          </div>
        ) : (
          <>
            <div className="panels-row">
              {PANELS.map(p => (
                <div key={p.title} className="grafana-panel">
                  <div className="panel-header">
                    <span className="panel-title">{p.title}</span>
                    <span className="panel-value" style={{ color: p.color }}>
                      {p.getValue(running, total)}
                    </span>
                  </div>
                  <div className="panel-chart">
                    <Chart color={p.color} type={p.type} />
                  </div>
                  <div className="panel-footer">
                    <span className="panel-link">
                      Ouvrir dans Grafana <i className="ti ti-external-link" aria-hidden="true" />
                    </span>
                  </div>
                </div>
              ))}
            </div>

            <div className="logs-section">
              <div className="logs-header">
                <div className="logs-title">
                  <i className="ti ti-terminal-2" style={{ fontSize: 14, color: 'var(--text-muted)' }} aria-hidden="true" />
                  Logs
                  <div className="logs-live">
                    <span className="live-dot" />
                    live
                  </div>
                </div>
                <div className="filters">
                  <div className="filter-select">
                    <i className="ti ti-apps" aria-hidden="true" />App : Toutes
                    <i className="ti ti-chevron-down" aria-hidden="true" />
                  </div>
                  <div className="filter-select">
                    <i className="ti ti-adjustments-horizontal" aria-hidden="true" />Niveau : Tous
                    <i className="ti ti-chevron-down" aria-hidden="true" />
                  </div>
                </div>
              </div>
              <div className="logs-feed">
                {LOGS.map((l, i) => (
                  <div key={i} className={`log-line${l.level === 'ERROR' ? ' is-error' : ''}`}>
                    <span className="log-ts">{l.ts}</span>
                    <span className="log-app">{l.app}</span>
                    <span className={`log-level ${l.level.toLowerCase()}`}>{l.level}</span>
                    <span className="log-msg">{l.msg}</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>

    </>
  );
};
