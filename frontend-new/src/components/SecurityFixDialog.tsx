import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { IconAlertTriangle, IconCheck, IconChevronDown, IconCopy, IconExternalLink, IconRobot, IconTerminal2 } from '@tabler/icons-react';
import { securityApi } from '@/api/security';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from '@/components/ui/toast';
import { cn } from '@/utils/cn';

export interface AutofixResult {
  status: 'created' | 'exists' | 'no_fix';
  mr_url?: string | null;
  message?: string | null;
}

export interface ModeBConfig {
  /** Greyed card + explanation when set (AI off, not a fixable dependency, missing role, …). */
  disabledReason?: string;
  /** Launches the CNP-AI fix; rejects with an Error whose message is shown to the user. */
  launch?: () => Promise<AutofixResult>;
}

interface Props {
  open: boolean;
  appId: number;
  /** finding id, or 'all' */
  finding: string;
  onClose: () => void;
  modeB: ModeBConfig;
}

async function copyText(text: string) {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(text);
  const ta = document.createElement('textarea');
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  ta.remove();
}

export function SecurityFixDialog({ open, appId, finding, onClose, modeB }: Props) {
  const [showPreview, setShowPreview] = useState(false);
  const [copied, setCopied] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<AutofixResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['security-fix-prompt', appId, finding],
    queryFn: () => securityApi.getFixPrompt(appId, finding),
    enabled: open,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!open) return;
    setShowPreview(false); setCopied(false); setResult(null); setError(null);
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, finding, onClose]);

  if (!open) return null;

  async function onCopy() {
    if (!data) return;
    try {
      await copyText(data.prompt);
      setCopied(true);
      toast({ title: 'Prompt copied', description: 'Paste it in your coding agent at the root of the cloned repository.' });
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast({ title: 'Copy failed', description: 'Select the preview text and copy it manually.', variant: 'destructive' });
    }
  }

  async function onLaunch() {
    if (!modeB.launch) return;
    setRunning(true); setError(null); setResult(null);
    try {
      setResult(await modeB.launch());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="fix-dialog-title"
        className="relative bg-background border border-border rounded-lg shadow-lg p-6 w-full max-w-2xl mx-4 max-h-[90vh] overflow-y-auto"
      >
        <h3 id="fix-dialog-title" className="text-sm font-semibold text-foreground mb-4">
          {finding === 'all' ? 'Fix all findings' : 'Fix this finding'}
        </h3>

        {/* Mode A — recommended */}
        <div className="rounded-lg border border-primary/40 bg-primary/5 p-4 mb-3">
          <div className="flex items-center gap-2 mb-1.5">
            <IconTerminal2 size={16} className="text-primary" />
            <h4 className="text-sm font-medium text-foreground">Locally, with your agent</h4>
            <Badge variant="primary">Recommended</Badge>
          </div>
          <p className="text-xs text-muted-foreground mb-3">
            Better quality: your agent runs the project's tests, and nothing leaves your machine.
          </p>
          {isLoading ? (
            <Skeleton className="h-8 w-40" />
          ) : isError || !data ? (
            <p className="text-xs text-danger-text flex items-center gap-1.5">
              <IconAlertTriangle size={12} /> Could not generate the prompt (the finding may have disappeared — refresh the tab).
            </p>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <Button autoFocus variant="primary" size="md" icon={copied ? <IconCheck size={14} /> : <IconCopy size={14} />} onClick={onCopy}>
                  {copied ? 'Copied' : 'Copy the prompt'}
                </Button>
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
                  aria-expanded={showPreview}
                  onClick={() => setShowPreview((v) => !v)}
                >
                  <IconChevronDown size={12} className={cn('transition-transform', showPreview && 'rotate-180')} />
                  Preview
                </button>
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                Paste it in your coding agent (Claude Code, Cursor, …) at the root of the cloned repository.
              </p>
              {showPreview && (
                <pre className="mt-3 max-h-64 overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap font-mono">{data.prompt}</pre>
              )}
            </>
          )}
        </div>

        {/* Mode B — discreet */}
        <div className={cn('rounded-lg border border-border p-4', modeB.disabledReason && 'opacity-60')}>
          <div className="flex items-center gap-2 mb-1.5">
            <IconRobot size={16} className="text-muted-foreground" />
            <h4 className="text-sm font-medium text-foreground">With the CNP AI</h4>
          </div>
          {modeB.disabledReason ? (
            <p className="text-xs text-muted-foreground">{modeB.disabledReason}</p>
          ) : (
            <>
              <div className="rounded-md border border-warning/40 bg-warning-subtle text-warning-text text-xs p-2.5 mb-3 flex gap-2">
                <IconAlertTriangle size={14} className="shrink-0 mt-0.5" />
                <span>
                  Less capable than a local agent: it does not run your tests, may hit rate limits, and the target
                  manifest may be sent to a third-party AI provider. It opens a draft Merge Request you must review.
                </span>
              </div>
              {result ? (
                result.status === 'no_fix' ? (
                  <p className="text-xs text-warning-text">No automatic fix: {result.message ?? 'the change was rejected by the safety checks.'}</p>
                ) : (
                  <a href={result.mr_url && /^https?:\/\//i.test(result.mr_url) ? result.mr_url : undefined} target="_blank" rel="noreferrer" className="text-xs text-primary inline-flex items-center gap-1 hover:underline">
                    {result.status === 'exists' ? 'A Merge Request already exists' : 'Draft Merge Request created'} <IconExternalLink size={12} />
                  </a>
                )
              ) : (
                <Button size="md" variant="secondary" loading={running} onClick={onLaunch}>
                  Launch anyway
                </Button>
              )}
              {error && <p className="text-xs text-danger-text mt-2 flex items-center gap-1.5"><IconAlertTriangle size={12} />{error}</p>}
            </>
          )}
        </div>

        <div className="flex justify-end mt-4">
          <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
        </div>
      </div>
    </div>
  );
}
