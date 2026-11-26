import { describe, it, expect } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
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

  it('fait des chemins internes des liens qui naviguent dans la CNP', () => {
    render(
      <MemoryRouter initialEntries={['/groups/booking']}>
        <Routes>
          <Route
            path="/groups/booking"
            element={
              <SimpleMarkdown content="- [**Booking worker 1**](/groups/booking/apps/booking-worker-1) : dégradée" />
            }
          />
          <Route path="/groups/booking/apps/booking-worker-1" element={<p>page de l’app</p>} />
        </Routes>
      </MemoryRouter>
    );
    const link = screen.getByRole('link', { name: 'Booking worker 1' });
    expect(link.getAttribute('href')).toBe('/groups/booking/apps/booking-worker-1');
    expect(link.querySelector('strong')).not.toBeNull();
    fireEvent.click(link);
    expect(screen.getByText('page de l’app')).toBeTruthy();
  });

  it('ouvre les liens https dans un nouvel onglet', () => {
    render(<SimpleMarkdown content="Voir [le pipeline](https://gitlab.com/g/p/-/pipelines/42)." />);
    const link = screen.getByRole('link', { name: 'le pipeline' });
    expect(link.getAttribute('href')).toBe('https://gitlab.com/g/p/-/pipelines/42');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('ne fait pas de lien vers un schéma dangereux ou un autre domaine relatif', () => {
    const { container } = render(
      <SimpleMarkdown content="[clic](javascript:alert(1)) [ailleurs](//evil.example) [http](http://x.test)" />
    );
    expect(container.querySelector('a')).toBeNull();
    expect(container.textContent).toContain('clic');
    expect(container.textContent).not.toContain('javascript');
  });

  it('garde un lien interne utilisable hors routeur', () => {
    render(<SimpleMarkdown content="[Apps](/groups/booking/apps)" />);
    expect(screen.getByRole('link', { name: 'Apps' }).getAttribute('href')).toBe('/groups/booking/apps');
  });
});
