import { ReactNode } from 'react';

/**
 * Minimal, dependency-free markdown renderer for chat answers.
 * Supports: paragraphs, `#` headings, `-`/`*` and `1.` lists, **bold**, `code`.
 * Renders to React elements only (no dangerouslySetInnerHTML) — safe by design.
 */
function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /(\*\*([^*]+)\*\*|`([^`]+)`)/g;
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[2] !== undefined) {
      nodes.push(<strong key={key++}>{m[2]}</strong>);
    } else if (m[3] !== undefined) {
      nodes.push(
        <code
          key={key++}
          className="px-1 py-0.5 rounded bg-background/60 font-mono text-[0.85em]"
        >
          {m[3]}
        </code>
      );
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
