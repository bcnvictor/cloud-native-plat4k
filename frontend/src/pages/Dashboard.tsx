import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { monitoringApi, AppValue, LogEntry } from '@/api/monitoring';
import { grafanaFinopsUrl } from '@/utils/grafanaLinks';

function AppBarChart({ data, color, unit }: { data: AppValue[]; color: string; unit: string }) {
  const top = data.slice(0, 6);
  const max = top[0]?.value ?? 1;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '4px 0' }}>
      {top.map(({ app, owner, value }) => (
        <div key={app} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'rgba(255,255,255,0.35)', width: 90, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flexShrink: 0 }} title={owner}>
            {app}
          </span>
          <div style={{ flex: 1, height: 4, background: 'rgba(255,255,255,0.07)', borderRadius: 2 }}>
            <div style={{ width: `${(value / max) * 100}%`, height: '100%', background: color, borderRadius: 2 }} />
          </div>
          <span style={{ fontFamily: 'var(--mono)', fontSize: 9, color: 'rgba(255,255,255,0.4)', width: 48, textAlign: 'right', flexShrink: 0 }}>
            {value} {unit}
          </span>
        </div>
      ))}
    </div>
  );
}

function UnavailableChart({ label }: { label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 64, color: 'rgba(255,255,255,0.2)', fontSize: 11, fontFamily: 'var(--mono)' }}>
      {label} indisponible
    </div>
  );
}

function formatTs(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

const NAMESPACES = ['Tous', 'monitoring', 'kube-system', 'default'];
const LEVELS = ['Tous', 'INFO', 'WARN', 'ERROR', 'DEBUG'];

export const Dashboard = () => {
  const [nsFilter, setNsFilter] = useState('Tous');
  const [levelFilter, setLevelFilter] = useState('Tous');

  const { data: monitoringConfig } = useQuery({
    queryKey: ['monitoring-config'],
    queryFn: monitoringApi.getConfig,
    staleTime: Infinity,
  });

  const { data: metrics, isError: metricsError } = useQuery({
    queryKey: ['monitoring-metrics'],
    queryFn: monitoringApi.getMetrics,
    refetchInterval: 30_000,
    retry: 1,
  });

  const { data: logs, isError: logsError } = useQuery({
    queryKey: ['monitoring-logs', nsFilter],
    queryFn: () => monitoringApi.getLogs(nsFilter === 'Tous' ? undefined : nsFilter),
    refetchInterval: 15_000,
    retry: 1,
  });

  const filteredLogs = (logs ?? []).filter(l =>
    levelFilter === 'Tous' || l.level === levelFilter
  );

  const totalCpuCores = metrics?.cpu_by_app.reduce((s, n) => s + n.value, 0).toFixed(3) ?? '—';
  const totalRamMb = metrics?.ram_by_app.reduce((s, n) => s + n.value, 0).toFixed(0) ?? '—';
  const dailyCost = metrics ? `$${metrics.estimated_daily_cost_usd.toFixed(3)}` : '—';

  return (
    <>
      <div className="topbar">
        <span className="topbar-title">Monitoring</span>
        {monitoringConfig?.grafana_url && (
          <a
            href={grafanaFinopsUrl(monitoringConfig.grafana_url)}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-ghost"
            style={{ textDecoration: 'none' }}
          >
            <i className="ti ti-chart-area-line" aria-hidden="true" />
            Grafana FinOps
          </a>
        )}
      </div>

      <div className="page-content">
        <div className="panels-row">
          <div className="grafana-panel">
            <div className="panel-header">
              <span className="panel-title">CPU par app</span>
              <span className="panel-value" style={{ color: '#10B981' }}>{totalCpuCores} cores</span>
            </div>
            <div className="panel-chart">
              {metricsError || !metrics ? <UnavailableChart label="Prometheus" /> : (
                <AppBarChart data={metrics.cpu_by_app} color="#10B981" unit="c" />
              )}
            </div>
            <div className="panel-footer" />
          </div>

          <div className="grafana-panel">
            <div className="panel-header">
              <span className="panel-title">RAM par app</span>
              <span className="panel-value" style={{ color: '#93B8FA' }}>{totalRamMb} Mo</span>
            </div>
            <div className="panel-chart">
              {metricsError || !metrics ? <UnavailableChart label="Prometheus" /> : (
                <AppBarChart data={metrics.ram_by_app} color="#93B8FA" unit="Mo" />
              )}
            </div>
            <div className="panel-footer" />
          </div>

          <div className="grafana-panel">
            <div className="panel-header">
              <span className="panel-title">FinOps — Coût / jour</span>
              <span className="panel-value" style={{ color: '#F59E0B' }}>{dailyCost}</span>
            </div>
            <div className="panel-chart">
              <div style={{ padding: '8px 0', display: 'flex', flexDirection: 'column', gap: 6 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, fontFamily: 'var(--mono)', color: 'rgba(255,255,255,0.3)' }}>
                  <span>Coût / heure</span>
                  <span style={{ color: '#F59E0B' }}>{metrics ? `$${metrics.estimated_hourly_cost_usd}` : '—'}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, fontFamily: 'var(--mono)', color: 'rgba(255,255,255,0.3)' }}>
                  <span>Nodes</span>
                  <span>2 × Standard_B2ls_v2</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, fontFamily: 'var(--mono)', color: 'rgba(255,255,255,0.3)' }}>
                  <span>Estimation</span>
                  <span>prix public Azure</span>
                </div>
              </div>
            </div>
            <div className="panel-footer" />
          </div>
        </div>

        <div className="logs-section">
          <div className="logs-header">
            <div className="logs-title">
              <i className="ti ti-terminal-2" style={{ fontSize: 14, color: 'var(--text-muted)' }} aria-hidden="true" />
              Logs
              {!logsError && (
                <div className="logs-live">
                  <span className="live-dot" />
                  live
                </div>
              )}
            </div>
            <div className="filters">
              <div className="filter-select" style={{ position: 'relative' }}>
                <i className="ti ti-apps" aria-hidden="true" />
                <select
                  value={nsFilter}
                  onChange={e => setNsFilter(e.target.value)}
                  style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer', width: '100%' }}
                >
                  {NAMESPACES.map(n => <option key={n}>{n}</option>)}
                </select>
                App : {nsFilter}
                <i className="ti ti-chevron-down" aria-hidden="true" />
              </div>
              <div className="filter-select" style={{ position: 'relative' }}>
                <i className="ti ti-adjustments-horizontal" aria-hidden="true" />
                <select
                  value={levelFilter}
                  onChange={e => setLevelFilter(e.target.value)}
                  style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer', width: '100%' }}
                >
                  {LEVELS.map(l => <option key={l}>{l}</option>)}
                </select>
                Niveau : {levelFilter}
                <i className="ti ti-chevron-down" aria-hidden="true" />
              </div>
            </div>
          </div>
          <div className="logs-feed">
            {logsError ? (
              <div className="log-line" style={{ color: 'var(--text-muted)', fontFamily: 'var(--mono)', fontSize: 11 }}>
                Loki indisponible
              </div>
            ) : filteredLogs.length === 0 ? (
              <div className="log-line" style={{ color: 'var(--text-muted)', fontFamily: 'var(--mono)', fontSize: 11 }}>
                Aucun log
              </div>
            ) : filteredLogs.map((l: LogEntry, i: number) => (
              <div key={i} className={`log-line${l.level === 'ERROR' ? ' is-error' : ''}`}>
                <span className="log-ts">{formatTs(l.ts)}</span>
                <span className="log-app">{l.app}</span>
                <span className={`log-level ${l.level.toLowerCase()}`}>{l.level}</span>
                <span className="log-msg">{l.msg}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
};
