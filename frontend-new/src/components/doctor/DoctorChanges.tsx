import { IconExternalLink, IconGitCompare, IconInfoCircle } from '@tabler/icons-react';
import type { DoctorChanges as Changes, DoctorFileChange } from '@/types';
import { cn } from '@/utils/cn';
import { formatDateTime, shortRev } from './doctorText';

const CHANGE_META: Record<DoctorFileChange['change'], { mark: string; word: string; className: string }> = {
  added: { mark: '+', word: 'ajouté', className: 'text-success-text' },
  modified: { mark: '~', word: 'modifié', className: 'text-warning-text' },
  deleted: { mark: '−', word: 'supprimé', className: 'text-danger-text' },
  renamed: { mark: '→', word: 'renommé', className: 'text-info-text' },
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
            Comparer sur GitLab
            <span className="sr-only"> (nouvel onglet)</span>
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
              <span className="flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
                {c.url ? (
                  <a
                    href={c.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-0.5 rounded-sm font-mono hover:text-foreground hover:underline"
                    aria-label={`Commit ${shortRev(c.sha)} sur GitLab (nouvel onglet)`}
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
        <ul className="flex flex-wrap gap-1.5" aria-label="Fichiers modifiés">
          {changes.files.map((f) => {
            const meta = CHANGE_META[f.change] ?? CHANGE_META.modified;
            return (
              <li
                key={`${f.change}-${f.path}`}
                className="inline-flex max-w-full items-baseline gap-1 rounded-md border border-border bg-background-subtle px-1.5 py-0.5 font-mono text-[11px] text-foreground"
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
        <p className="text-[11px] text-muted-foreground">
          Liste tronquée : seuls les premiers commits et fichiers sont affichés
          {changes.compare_url ? ' ; la comparaison GitLab montre tout.' : '.'}
        </p>
      )}

      {empty && !changes.unavailable_reason && (
        <p className="text-xs text-muted-foreground">Aucun commit entre ces deux versions.</p>
      )}
    </div>
  );
}
