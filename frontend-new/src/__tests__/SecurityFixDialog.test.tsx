import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SecurityFixDialog } from '@/components/SecurityFixDialog';

vi.mock('@/api/security', () => ({
  securityApi: { getFixPrompt: vi.fn().mockResolvedValue({ prompt: 'FIX flask 1.0 -> 2.0.1', finding: 'f1' }) },
}));

function renderDialog(modeB = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SecurityFixDialog open appId={1} finding="f1" onClose={() => {}} modeB={modeB} />
    </QueryClientProvider>,
  );
}

describe('SecurityFixDialog', () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  afterEach(cleanup);
  beforeEach(() => {
    writeText.mockClear();
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
  });

  it('shows Mode A as recommended and copies the prompt to the clipboard', async () => {
    renderDialog({ disabledReason: 'AI is disabled.' });
    expect(screen.getByText('Recommended')).toBeTruthy();
    await userEvent.click(await screen.findByRole('button', { name: /copy the prompt/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('FIX flask 1.0 -> 2.0.1'));
  });

  it('greys Mode B with its reason and hides the launch button', async () => {
    renderDialog({ disabledReason: 'AI is disabled.' });
    expect(await screen.findByText('AI is disabled.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /launch anyway/i })).toBeNull();
  });

  it('shows the warning and launches Mode B, then the MR link', async () => {
    const launch = vi.fn().mockResolvedValue({ status: 'created', mr_url: 'https://gl/mr/1' });
    renderDialog({ launch });
    expect(screen.getByText(/Less capable than a local agent/)).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /launch anyway/i }));
    expect((await screen.findByText(/Draft Merge Request created/)).closest('a')?.getAttribute('href')).toBe('https://gl/mr/1');
  });

  it('shows the error message when the launch fails', async () => {
    renderDialog({ launch: vi.fn().mockRejectedValue(new Error('AI quota reached, try again later')) });
    await userEvent.click(screen.getByRole('button', { name: /launch anyway/i }));
    expect(await screen.findByText('AI quota reached, try again later')).toBeTruthy();
  });
});
