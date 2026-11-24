/** bringIntoView : la carte arrive sous l'en-tête collant, calcul en px de mise en page (zoom de la page). */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { bringIntoView } from '@/components/doctor/doctorText';

function layout(el: HTMLElement, props: Record<string, number | Element | null>) {
  for (const [key, value] of Object.entries(props)) {
    Object.defineProperty(el, key, { configurable: true, get: () => value });
  }
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('bringIntoView', () => {
  it("fait défiler la zone principale pour placer l'élément sous l'en-tête collant", () => {
    const main = document.createElement('main');
    main.style.overflowY = 'auto';
    const header = document.createElement('div');
    header.className = 'sticky';
    header.style.position = 'sticky';
    const card = document.createElement('section');
    main.append(header, card);
    document.body.append(main);

    layout(main, { scrollHeight: 3000, clientHeight: 700, offsetTop: 60, offsetParent: null });
    layout(header, { offsetHeight: 140 });
    layout(card, { offsetTop: 900, offsetParent: main });
    main.scrollTo = vi.fn() as unknown as typeof main.scrollTo;

    bringIntoView(card, 'smooth');

    // 60 (main) + 900 (carte) - 60 (main) - 140 (en-tête) - 16 (marge)
    expect(main.scrollTo).toHaveBeenCalledWith({ top: 744, behavior: 'smooth' });
  });

  it('se rabat sur scrollIntoView sans zone de défilement', () => {
    const card = document.createElement('section');
    document.body.append(card);
    card.scrollIntoView = vi.fn();
    bringIntoView(card, 'auto');
    expect(card.scrollIntoView).toHaveBeenCalledWith({ block: 'start', behavior: 'auto' });
  });
});
