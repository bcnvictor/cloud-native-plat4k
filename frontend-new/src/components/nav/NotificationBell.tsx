import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { IconBell, IconX } from '@tabler/icons-react';
import { notificationsApi } from '@/api/notifications';
import type { Notification, NotificationSeverity } from '@/types';
import { cn } from '@/utils/cn';
import { timeAgo } from '@/utils/timeAgo';

const SEVERITY_DOT: Record<NotificationSeverity, string> = {
  critical: 'bg-destructive',
  warning:  'bg-warning',
  info:     'bg-primary',
};

const TYPE_LABEL: Record<string, string> = {
  'app.created':          'App created',
  'app.updated':          'App updated',
  'app.deleted':          'App deleted',
  'app.deployed':         'Deployment successful',
  'app.rollback':         'Rollback performed',
  'app.health.degraded':  'App degraded',
  'app.health.recovered': 'App recovered',
  'app.expose.changed':   'Exposure changed',
  'cluster.offline':      'Cluster offline',
  'cluster.online':       'Cluster online',
  'group.renamed':        'Group renamed',
  'group.member.added':   'Added to group',
  'group.member.removed': 'Removed from group',
};

function NotificationItem({
  n,
  onRead,
}: {
  n: Notification;
  onRead: () => void;
}) {
  const isNew = n.state === 'new';
  const label = TYPE_LABEL[n.event.type] ?? n.event.type;
  const name = (n.event.payload?.name as string) ?? (n.event.payload?.cluster_name as string) ?? '';
  const severityDot = SEVERITY_DOT[n.event.severity] ?? 'bg-muted-foreground';

  return (
    <li
      className={cn(
        'flex items-start gap-2.5 px-3 py-2.5 cursor-pointer hover:bg-accent transition-colors',
        isNew ? 'bg-background' : 'bg-muted/50',
      )}
      onClick={onRead}
    >
      <span className={cn(
        'mt-1.5 h-2 w-2 shrink-0 rounded-full transition-colors',
        isNew ? severityDot : 'bg-muted-foreground/30',
      )} />
      <div className="flex-1 min-w-0">
        <p className={cn(
          'text-xs transition-colors',
          isNew ? 'font-medium text-foreground' : 'text-muted-foreground',
        )}>
          {label}
          {name && <span className="font-normal"> · {name}</span>}
        </p>
        <p className="text-[10px] text-muted-foreground/70 mt-0.5">{timeAgo(n.created_at)}</p>
      </div>
    </li>
  );
}

export function NotificationBell() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const { data: countData } = useQuery({
    queryKey: ['notifications-count'],
    queryFn: notificationsApi.countUnread,
    refetchInterval: 30_000,
  });
  const unread = countData?.count ?? 0;

  const { data: notifications = [] } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => notificationsApi.list({ limit: 20 }),
    enabled: open,
  });

  const markRead = useMutation({
    mutationFn: notificationsApi.markRead,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications'] });
      qc.invalidateQueries({ queryKey: ['notifications-count'] });
    },
  });

  const clearAll = useMutation({
    mutationFn: notificationsApi.clearAll,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['notifications'] });
      qc.invalidateQueries({ queryKey: ['notifications-count'] });
    },
  });

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative h-8 w-8 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        aria-label="Notifications"
      >
        <IconBell size={17} />
        {unread > 0 && (
          <span className="absolute top-0.5 right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[9px] font-bold text-destructive-foreground leading-none">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute bottom-0 left-full ml-3 w-80 bg-background border border-border rounded-md shadow-lg z-50 flex flex-col">
          <header className="flex items-center justify-between px-3 py-2 border-b border-border shrink-0">
            <span className="text-xs font-medium text-foreground">Notifications</span>
            <div className="flex items-center gap-2">
              {notifications.length > 0 && (
                <button
                  onClick={() => clearAll.mutate()}
                  disabled={clearAll.isPending}
                  className="text-[11px] text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
                >
                  Clear all
                </button>
              )}
              <button
                onClick={() => setOpen(false)}
                className="text-muted-foreground hover:text-foreground transition-colors"
              >
                <IconX size={13} />
              </button>
            </div>
          </header>

          <ul className="max-h-80 overflow-y-auto divide-y divide-border">
            {notifications.map((n) => (
              <NotificationItem
                key={n.id}
                n={n}
                onRead={() => {
                  if (n.state === 'new') markRead.mutate(n.id);
                }}
              />
            ))}
            {notifications.length === 0 && (
              <li className="px-3 py-8 text-center text-xs text-muted-foreground">
                No notifications
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
