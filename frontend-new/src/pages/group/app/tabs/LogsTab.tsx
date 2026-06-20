import { useState, useRef, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  IconDownload,
  IconPlayerPlay,
  IconPlayerPause,
  IconSearch,
} from '@tabler/icons-react';
import { useAppLogs } from '@/hooks/useAppLogs';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { Input } from '@/components/ui/Input';
import { Spinner } from '@/components/ui/Spinner';
import { cn } from '@/lib/cn';

const LEVEL_COLORS: Record<string, string> = {
  ERROR: 'text-danger-text bg-danger-subtle',
  WARN: 'text-warning-text',
  INFO: 'text-info-text',
  DEBUG: 'text-muted-foreground',
};

const LEVEL_OPTIONS = [
  { value: 'ALL', label: 'ALL' },
  { value: 'INFO', label: 'INFO' },
  { value: 'WARN', label: 'WARN' },
  { value: 'ERROR', label: 'ERROR' },
];

export function LogsTab() {
  const { appSlug } = useParams<{ appSlug: string }>();
  const [level, setLevel] = useState('ALL');
  const [search, setSearch] = useState('');
  const [live, setLive] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const { data: logs = [], isLoading } = useAppLogs({
    appSlug: appSlug!,
    level,
    search,
    live,
  });

  useEffect(() => {
    if (live) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, live]);

  function exportLogs() {
    const text = logs.map((l) => `[${l.timestamp}] ${l.level} ${l.message}`).join('\n');
    const blob = new Blob([text], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${appSlug}-logs.txt`;
    a.click();
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Controls */}
      <div className="flex items-center gap-2 flex-wrap">
        <Select
          options={[{ value: appSlug!, label: appSlug! }]}
          value={appSlug!}
          onChange={() => {}}
          className="w-40"
        />
        <Select
          options={LEVEL_OPTIONS}
          value={level}
          onChange={setLevel}
          className="w-24"
        />
        <div className="flex-1 min-w-40">
          <Input
            placeholder="Rechercher dans les logs…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            suffix={<IconSearch size={13} />}
          />
        </div>
        <Button
          variant={live ? 'primary' : 'secondary'}
          size="sm"
          icon={live ? <IconPlayerPause size={13} /> : <IconPlayerPlay size={13} />}
          onClick={() => setLive((v) => !v)}
        >
          Live
        </Button>
        <Button
          variant="ghost"
          size="sm"
          icon={<IconDownload size={13} />}
          onClick={exportLogs}
        >
          Export
        </Button>
      </div>

      {/* Log stream */}
      <div className="bg-card border border-border rounded-md overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Spinner size="lg" />
          </div>
        ) : logs.length === 0 ? (
          <p className="px-4 py-8 text-xs text-muted-foreground text-center font-mono">
            Aucun log disponible.
          </p>
        ) : (
          <div className="overflow-auto max-h-[600px] text-xs font-mono">
            <table className="w-full">
              <tbody>
                {logs.map((log, i) => (
                  <tr
                    key={i}
                    className={cn(
                      'border-b border-border/50 last:border-0',
                      log.level === 'ERROR' && 'bg-danger-subtle'
                    )}
                  >
                    <td className="px-4 py-1 text-muted-foreground whitespace-nowrap align-top w-48">
                      {new Date(log.timestamp).toLocaleTimeString('fr-FR')}
                    </td>
                    <td className={cn('px-2 py-1 whitespace-nowrap align-top w-16', LEVEL_COLORS[log.level])}>
                      {log.level}
                    </td>
                    <td className="px-2 py-1 text-foreground break-all">
                      {log.message}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {level !== 'ALL' ? `Filtre : ${level}` : 'Tous les niveaux'}
          {search && ` · "${search}"`}
          {' '}· {logs.length} entrée{logs.length !== 1 ? 's' : ''}
        </span>
        {live && (
          <span className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-success animate-pulse" />
            Live
          </span>
        )}
      </div>
    </div>
  );
}
