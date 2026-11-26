import { ReactNode } from 'react';
import { Link, useInRouterContext } from 'react-router-dom';

/**
 * Minimal, dependency-free markdown renderer for chat answers.
 * Supports: paragraphs, `#` headings, `-`/`*` and `1.` lists, **bold**, *italic*, `code`,
 * and `[label](href)` links.
 * Renders to React elements only (no dangerouslySetInnerHTML) — safe by design.
 */

const LINK_CLASS = 'font-medium text-primary underline underline-offset-2 hover:opacity-80';

/** Chemin interne de la CNP (`/groups/...`), pas `//autre-domaine` ni `/\autre-domaine` (le navigateur lit `\` comme `/`). */
const isInternalPath = (href: string) => /^\/(?![/\\])/.test(href);
const isHttps = (href: string) => /^https:\/\//i.test(href);

/** Lien interne : navigation du routeur (le panneau reste ouvert), `<a>` hors routeur. */
function InternalLink({ to, children }: { to: string; children: ReactNode }) {
  if (!useInRouterContext()) {
    return (
      <a href={to} className={LINK_CLASS}>
        {children}
      </a>
    );
  }
  return (
    <Link to={to} className={LINK_CLASS}>
      {children}
    </Link>
  );
}

function renderLink(label: string, href: string, key: number): ReactNode {
  const children = renderInline(label);
  if (isInternalPath(href)) {
    return (
      <InternalLink key={key} to={href}>
        {children}
      </InternalLink>
    );
  }
  if (isHttps(href)) {
    return (
      <a key={key} href={href} target="_blank" rel="noopener noreferrer" className={LINK_CLASS}>
        {children}
      </a>
    );
  }
  // Autre schéma (javascript:, http:, mailto:…) : le libellé seul, sans lien.
  return <span key={key}>{children}</span>;
}

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  // *italic* must not start/end with a space, so « 2 * 3 * 4 » stays literal.
  const re =
    /(\[([^\]\n]+)\]\(([^)\s]+)\)|\*\*([^*]+)\*\*|`([^`]+)`|\*([^*\s](?:[^*]*[^*\s])?)\*)/g;
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[2] !== undefined) {
      nodes.push(renderLink(m[2], m[3], key++));
    } else if (m[4] !== undefined) {
      nodes.push(<strong key={key++}>{renderInline(m[4])}</strong>);
    } else if (m[5] !== undefined) {
      nodes.push(
        <code
          key={key++}
          className="px-1 py-0.5 rounded bg-background font-mono text-[0.85em]"
        >
          {m[5]}
        </code>
      );
    } else if (m[6] !== undefined) {
      nodes.push(<em key={key++}>{renderInline(m[6])}</em>);
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export function SimpleMarkdown({ content }: { content: string }) {
  const lines = content.replace(/\r/g, '').split('\n');
  const blocks: ReactNode[] = [];
  let i = 0;
  let key = 0;

  const isUl = (l: string) => /^\s*[-*]\s+/.test(l);
  const isOl = (l: string) => /^\s*\d+\.\s+/.test(l);
  const isHeading = (l: string) => /^#{1,6}\s+/.test(l.trim());

  while (i < lines.length) {
    const trimmed = lines[i].trim();
    if (trimmed === '') {
      i++;
      continue;
    }
    const heading = trimmed.match(/^#{1,6}\s+(.*)$/);
    if (heading) {
      blocks.push(
        <p key={key++} className="font-semibold">
          {renderInline(heading[1])}
        </p>
      );
      i++;
      continue;
    }
    if (isUl(lines[i])) {
      const items: ReactNode[] = [];
      while (i < lines.length && isUl(lines[i])) {
        items.push(<li key={items.length}>{renderInline(lines[i].replace(/^\s*[-*]\s+/, ''))}</li>);
        i++;
      }
      blocks.push(
        <ul key={key++} className="list-disc pl-4 space-y-0.5">
          {items}
        </ul>
      );
      continue;
    }
    if (isOl(lines[i])) {
      const items: ReactNode[] = [];
      while (i < lines.length && isOl(lines[i])) {
        items.push(<li key={items.length}>{renderInline(lines[i].replace(/^\s*\d+\.\s+/, ''))}</li>);
        i++;
      }
      blocks.push(
        <ol key={key++} className="list-decimal pl-4 space-y-0.5">
          {items}
        </ol>
      );
      continue;
    }
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !isUl(lines[i]) &&
      !isOl(lines[i]) &&
      !isHeading(lines[i])
    ) {
      para.push(lines[i].trim());
      i++;
    }
    blocks.push(<p key={key++}>{renderInline(para.join(' '))}</p>);
  }

  return <div className="space-y-2">{blocks}</div>;
}
