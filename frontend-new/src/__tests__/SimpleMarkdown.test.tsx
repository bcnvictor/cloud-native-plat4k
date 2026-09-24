import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { SimpleMarkdown } from '@/components/ui/SimpleMarkdown';

describe('SimpleMarkdown', () => {
  it('rend gras, italique et code sans laisser les marqueurs', () => {
    const { container } = render(
      <SimpleMarkdown content="- **demo-api** : statut *deployed*, image `api:1.2`" />
    );
    expect(container.querySelector('strong')?.textContent).toBe('demo-api');
    expect(container.querySelector('em')?.textContent).toBe('deployed');
    expect(container.querySelector('code')?.textContent).toBe('api:1.2');
    expect(container.textContent).not.toContain('*');
  });

  it('laisse les astérisques isolés intacts', () => {
    const { container } = render(<SimpleMarkdown content="2 * 3 * 4" />);
    expect(container.querySelector('em')).toBeNull();
    expect(container.textContent).toBe('2 * 3 * 4');
  });
});
