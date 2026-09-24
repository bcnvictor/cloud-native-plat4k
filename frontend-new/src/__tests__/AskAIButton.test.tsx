import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AskAIButton } from '@/components/AskAIButton';
import { assistantApi } from '@/api/assistant';
import { ASSISTANT_ASK_EVENT, AssistantAskDetail } from '@/utils/assistantContext';

function renderButton(enabled: boolean) {
  vi.spyOn(assistantApi, 'getUiSettings').mockResolvedValue({
    assistant_enabled: enabled,
    graphical_bot_enabled: true,
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AskAIButton question="Pourquoi web est en erreur ?" />
    </QueryClientProvider>
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('AskAIButton', () => {
  it("pose la question à l'assistant au clic", async () => {
    const received: string[] = [];
    const listener = (e: Event) =>
      received.push((e as CustomEvent<AssistantAskDetail>).detail.question);
    window.addEventListener(ASSISTANT_ASK_EVENT, listener);

    renderButton(true);
    fireEvent.click(await screen.findByRole('button', { name: /Expliquer avec l’IA/ }));
    expect(received).toEqual(['Pourquoi web est en erreur ?']);

    window.removeEventListener(ASSISTANT_ASK_EVENT, listener);
  });

  it("reste masqué quand l'assistant est désactivé", async () => {
    renderButton(false);
    await waitFor(() => expect(assistantApi.getUiSettings).toHaveBeenCalled());
    expect(screen.queryByRole('button')).toBeNull();
  });
});
