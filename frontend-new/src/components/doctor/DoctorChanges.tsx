import { IconExternalLink, IconGitCompare, IconInfoCircle } from '@tabler/icons-react';
import type { DoctorChanges as Changes, DoctorFileChange } from '@/types';
import { cn } from '@/utils/cn';
import { formatDateTime, shortRev } from './doctorText';

const CHANGE_META: Record<DoctorFileChange['change'], { mark: string; word: string; className: string }> = {
  added: { mark: '+', word: 'added', className: 'text-success-text' },
  modified: { mark: '~', word: 'modified', className: 'text-warning-text' },
  deleted: { mark: '−', word: 'deleted', className: 'text-danger-text' },
  renamed: { mark: '→', word: 'renamed', className: 'text-info-text' },
};

/** Commits et fichiers entre la dernière version saine et la version suspecte. */
export function DoctorChanges({ changes }: { changes: Changes }) {
  const empty = changes.commits.length === 0 && changes.files.length === 0;

  return (
    <div className="flex flex-col gap-2">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <span className="font-mono">
          {shortRev(changes.from_revision)} → {shortRev(changes.to_revision)}
        </span>
        {changes.compare_url && (
          <a
            href={changes.compare_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 rounded-sm font-medium text-primary hover:underline"
          >
            <IconGitCompare size={13} aria-hidden="true" />
            Compare on GitLab
            <span className="sr-only"> (new tab)</span>
          </a>
        )}
      </p>

      {changes.unavailable_reason && (
        <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
          <IconInfoCircle size={13} aria-hidden="true" className="mt-0.5 shrink-0" />
          {changes.unavailable_reason}
        </p>
      )}

      {changes.commits.length > 0 && (
        <ul className="flex flex-col divide-y divide-border rounded-md border border-border">
          {changes.commits.map((c) => (
            <li key={c.sha} className="flex flex-col gap-0.5 px-2.5 py-2">
              <span className="break-words text-xs text-foreground">{c.title}</span>
              <span className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
                {c.url ? (
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-0.5 rounded-sm font-mono hover:text-foreground hover:underline"
                    aria-label={`Commit ${shortRev(c.sha)} on GitLab (new tab)`}
                  >
                    {shortRev(c.sha)}
                    <IconExternalLink size={11} aria-hidden="true" />
                  </a>
                ) : (
                  <span className="font-mono">{shortRev(c.sha)}</span>
                )}
                {c.author && <span>{c.author}</span>}
                {c.at && <time dateTime={c.at}>{formatDateTime(c.at)}</time>}
              </span>
            </li>
          ))}
        </ul>
      )}

      {changes.files.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Changed files">
          {changes.files.map((f) => {
            const meta = CHANGE_META[f.change] ?? CHANGE_META.modified;
            return (
              <li
                key={`${f.change}-${f.path}`}
                className="inline-flex max-w-full items-baseline gap-1 rounded-md border border-border bg-background-subtle px-1.5 py-0.5 font-mono text-xs text-foreground"
                title={`${f.path} (${meta.word})`}
              >
                <span aria-hidden="true" className={cn('font-semibold', meta.className)}>
                  {meta.mark}
                </span>
                <span className="min-w-0 break-all">{f.path}</span>
                <span className="sr-only"> ({meta.word})</span>
              </li>
            );
          })}
        </ul>
      )}

      {changes.truncated && (
        <p className="text-xs text-muted-foreground">
          Truncated list: only the first commits and files are shown
          {changes.compare_url ? '; the GitLab comparison shows everything.' : '.'}
        </p>
      )}

      {empty && !changes.unavailable_reason && (
        <p className="text-xs text-muted-foreground">No commits between these two versions.</p>
      )}
    </div>
  );
}
