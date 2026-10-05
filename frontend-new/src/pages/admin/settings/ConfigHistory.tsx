import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { auditApi } from '@/api/audit';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { timeAgo } from '@/utils/timeAgo';
import type { AuditLog } from '@/types';

// Actions d'audit qui relèvent de la configuration plateforme (vs actions par app).
export const CONFIG_ACTIONS = {
  clusters: ['cluster.'],
  gitlab: ['admin.register_gitlab_group', 'admin.deregister_gitlab_group', 'admin.sync_gitlab'],
  ai: ['ai_global_settings.'],
};
export const ALL_CONFIG_ACTIONS = Object.values(CONFIG_ACTIONS).flat();

function target(log: AuditLog): string {
  const extra = log.extra ?? {};
  if (typeof extra.name === 'string') return extra.name;
  if (log.action.startsWith('ai_global_settings.')) return 'Assistant IA';
  if (log.action === 'admin.sync_gitlab') return 'GitLab';
  return '—';
}

function detail(log: AuditLog): string | null {
  const extra = log.extra ?? {};
  if (Array.isArray(extra.fields)) return extra.fields.join(', ');
  if (typeof extra.reachable === 'boolean') return extra.reachable ? 'reachable' : 'unreachable';
  if (extra.group_id !== undefined) return `group_id: ${extra.group_id}`;
  const before = extra.old as Record<string, unknown> | undefined;
  const after = extra.new as Record<string, unknown> | undefined;
  if (before && after) {
    const changes = Object.keys(after)
      .filter((k) => JSON.stringify(before[k]) !== JSON.stringify(after[k]))
      .map((k) => `${k}: ${String(before[k])} → ${String(after[k])}`);
    if (extra.api_key_changed) changes.push('api_key');
    return changes.join(', ') || null;
  }
  return null;
}

interface ConfigHistoryProps {
  title: string;
  actions: string[];
  limit?: number;
}

export function ConfigHistory({ title, actions, limit = 10 }: ConfigHistoryProps) {
  const { data: logs = [], isLoading } = useQuery({
    queryKey: ['audit-logs', 'config', actions, limit],
    queryFn: () => auditApi.list(limit, 0, { action_prefix: actions }),
  });

  return (
    <Card padding="none" className="hover:translate-y-0 hover:shadow-sm">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h2 className="text-sm font-medium text-foreground">{title}</h2>
        <Link to="/admin/audit" className="text-xs text-primary hover:underline">
          View in audit log →
        </Link>
      </div>
      {isLoading ? (
        <div className="flex justify-center py-6"><Spinner /></div>
      ) : logs.length === 0 ? (
        <p className="px-4 py-6 text-xs text-muted-foreground text-center">No changes recorded yet.</p>
      ) : (
        <ul className="divide-y divide-border">
          {logs.map((log) => {
            const d = detail(log);
            return (
              <li key={log.id} className="grid grid-cols-[150px_minmax(0,1fr)_auto] gap-3 px-4 py-2.5 items-baseline">
                <span className="text-xs font-mono text-primary truncate">{log.action}</span>
                <span className="text-xs text-foreground min-w-0">
                  <span className="font-medium">{log.user_email ?? 'system'}</span>
                  <span className="text-muted-foreground"> on </span>
                  {target(log)}
                  {d && <span className="block font-mono text-[11px] text-muted-foreground break-words">{d}</span>}
                </span>
                <span className="text-xs text-muted-foreground whitespace-nowrap">{timeAgo(log.timestamp)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
