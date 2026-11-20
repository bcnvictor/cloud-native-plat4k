import { describe, it, expect, afterEach, vi } from 'vitest';
import { act, cleanup, render } from '@testing-library/react';
import { BotAvatar, CHANGE_SAFETY_MS, Mascot } from '@/components/assistant/Mascot';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function robot(container: HTMLElement): HTMLElement {
  return container.querySelector('.m-robot') as HTMLElement;
}

function part(container: HTMLElement, name: string): Element | null {
  return container.querySelector(`[data-part="${name}"]`);
}

/** Fin d'animation CSS : jsdom ne joue pas les animations, on émet l'événement. */
function endAnimation(el: Element, animationName: string) {
  const event = new Event('animationend', { bubbles: true });
  Object.assign(event, { animationName });
  act(() => {
    el.dispatchEvent(event);
  });
}

describe('Mascot', () => {
  it('garde la tenue de chatbot en mode chat, à 92×104 px', () => {
    const { container } = render(<Mascot mode="chat" />);
    expect(robot(container).dataset.mode).toBe('chat');
    expect(robot(container).className).toMatch(/h-\[104px\] w-\[92px\]/);
    expect(robot(container).getAttribute('aria-hidden')).toBe('true');
    expect(part(container, 'coat')).toBeNull();
    expect(part(container, 'stethoscope')).toBeNull();
    expect(part(container, 'head-mirror')).toBeNull();
    // les éléments animés existants sont toujours là
    expect(container.querySelector('.m-arm')).toBeTruthy();
    expect(container.querySelectorAll('.m-eye')).toHaveLength(2);
  });

  it('porte blouse, stéthoscope, miroir frontal et manche en mode docteur', () => {
    const { container } = render(<Mascot mode="doctor" />);
    expect(robot(container).dataset.mode).toBe('doctor');
    expect(part(container, 'coat')).toBeTruthy();
    expect(part(container, 'stethoscope')).toBeTruthy();
    expect(part(container, 'head-mirror')).toBeTruthy();
    expect(part(container, 'sleeve')).toBeTruthy();
    expect(container.querySelector('.m-arm')).toBeTruthy();
    expect(container.querySelectorAll('.m-eye')).toHaveLength(2);
  });

  it("ne joue pas l'animation au premier rendu", () => {
    const { container } = render(<Mascot mode="doctor" />);
    expect(robot(container).className).not.toMatch(/is-changing-to/);
    expect(part(container, 'sparks')).toBeNull();
  });

  it('joue le changement de tenue vers docteur, puis retire la classe en fin d’animation', () => {
    const { container, rerender } = render(<Mascot mode="chat" />);
    rerender(<Mascot mode="doctor" />);
    expect(robot(container).classList.contains('is-changing-to-doctor')).toBe(true);
    expect(part(container, 'sparks')).toBeTruthy();
    expect(part(container, 'coat')).toBeTruthy();

    // une animation secondaire ne termine pas le changement
    endAnimation(container.querySelector('.m-stetho')!, 'mascotStethoSwing');
    expect(robot(container).classList.contains('is-changing-to-doctor')).toBe(true);

    endAnimation(container.querySelector('.m-costume')!, 'mascotSuitUp');
    expect(robot(container).className).not.toMatch(/is-changing-to/);
    expect(part(container, 'sparks')).toBeNull();
    expect(part(container, 'coat')).toBeTruthy();
  });

  it("joue l'animation inverse vers chatbot : la blouse reste le temps de s'envoler", () => {
    vi.useFakeTimers();
    const { container, rerender } = render(<Mascot mode="doctor" />);
    rerender(<Mascot mode="chat" />);
    expect(robot(container).classList.contains('is-changing-to-chat')).toBe(true);
    expect(robot(container).classList.contains('is-changing-to-doctor')).toBe(false);
    expect(part(container, 'puffs')).toBeTruthy();
    expect(part(container, 'coat')).toBeTruthy();

    // délai de sécurité si animationend n'arrive jamais
    act(() => {
      vi.advanceTimersByTime(CHANGE_SAFETY_MS);
    });
    expect(robot(container).className).not.toMatch(/is-changing-to/);
    expect(part(container, 'coat')).toBeNull();
    expect(part(container, 'stethoscope')).toBeNull();
  });

  it('termine aussi sur le fondu du mode « mouvement réduit »', () => {
    const { container, rerender } = render(<Mascot mode="doctor" />);
    rerender(<Mascot mode="chat" />);
    endAnimation(container.querySelector('.m-coat')!, 'mascotOutfitFadeOut');
    expect(robot(container).className).not.toMatch(/is-changing-to/);
    expect(part(container, 'coat')).toBeNull();
  });

  it('enchaîne les deux sens si le mode change pendant l’animation', () => {
    const { container, rerender } = render(<Mascot mode="chat" />);
    rerender(<Mascot mode="doctor" />);
    rerender(<Mascot mode="chat" />);
    expect(robot(container).classList.contains('is-changing-to-chat')).toBe(true);
    expect(robot(container).classList.contains('is-changing-to-doctor')).toBe(false);
  });
});

describe('BotAvatar', () => {
  it('porte une marque médicale en mode docteur seulement', () => {
    const { container, rerender } = render(<BotAvatar mode="chat" />);
    expect(part(container, 'avatar-cross')).toBeNull();
    rerender(<BotAvatar mode="doctor" />);
    expect(part(container, 'avatar-cross')).toBeTruthy();
  });
});
