import { useState, useRef, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import {
  IconDownload,
  IconExternalLink,
  IconSearch,
  IconWifiOff,
} from '@tabler/icons-react';
import { useAppLogs } from '@/hooks/useAppLogs';
import { useLokiUrl } from '@/hooks/useMonitoringConfig';
import { Button } from '@/components/ui/Button';
import { Select } from '@/components/ui/Select';
import { Input } from '@/components/ui/Input';
import { Spinner } from '@/components/ui/Spinner';
import { cn } from '@/utils/cn';

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

const ENV_OPTIONS = [
  { value: 'dev', label: 'dev' },
  { value: 'prod', label: 'prod' },
];

export function LogsTab() {
  const { appSlug } = useParams<{ appSlug: string }>();
  const [env, setEnv] = useState('dev');
  const [level, setLevel] = useState('ALL');
  const [search, setSearch] = useState('');
  const topRef = useRef<HTMLDivElement>(null);
  const lokiUrl = useLokiUrl(appSlug!);

  const { data: logs = [], isLoading, isError } = useAppLogs({
    appSlug: appSlug!,
    namespace: env,
    level,
    search,
  });

  useEffect(() => {
    topRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

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
          options={ENV_OPTIONS}
          value={env}
          onChange={setEnv}
          className="w-24"
        />
        <Select
          options={LEVEL_OPTIONS}
          value={level}
          onChange={setLevel}
          className="w-24"
        />
        <div className="flex-1 min-w-40">
          <Input
            placeholder="Search logs…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            suffix={<IconSearch size={13} />}
          />
        </div>
        {lokiUrl && (
          <a
            href={lokiUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <IconExternalLink size={13} />
            Open in Loki
          </a>
        )}
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
        ) : isError ? (
          <div className="flex flex-col items-center gap-2 py-10 text-muted-foreground">
            <IconWifiOff size={20} />
            <p className="text-xs font-mono">Loki unavailable — check cluster connection</p>
          </div>
        ) : logs.length === 0 ? (
          <p className="px-4 py-8 text-xs text-muted-foreground text-center font-mono">
            No logs available.
          </p>
        ) : (
          <div className="overflow-auto max-h-[600px] text-xs font-mono">
            <div ref={topRef} />
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
                      {new Date(log.timestamp).toLocaleTimeString('en-US')}
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
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {level !== 'ALL' ? `Filter: ${level}` : 'All levels'}
          {search && ` · "${search}"`}
          {' '}· {logs.length} entry{logs.length !== 1 ? 'ies' : ''}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-success animate-pulse" />
          Live
        </span>
      </div>
    </div>
  );
}
