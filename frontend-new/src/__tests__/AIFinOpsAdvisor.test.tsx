import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AIFinOpsAdvisor } from '@/components/AIFinOpsAdvisor';
import { assistantApi } from '@/api/assistant';
import type { AIFinOpsAdvice } from '@/types';

const ADVICE: AIFinOpsAdvice = {
  app_id: 1, app_name: 'my-app', status: 'ok', window_hours: 24,
  generated_at: '2026-10-02T10:00:00Z',
  metrics: [{
    env: 'prod', pods: 1, restarts: 0, coverage_hours: 24,
    cpu_avg_mcpu: 0.02, cpu_p95_mcpu: 0.03, cpu_max_mcpu: 0.05,
    ram_avg_mib: 1.1, ram_p95_mib: 1.2, ram_max_mib: 1.3,
    cpu_request_mcpu: 100, cpu_limit_mcpu: 500, ram_request_mib: 128, ram_limit_mib: 256,
    reserved_cost_month_usd: 4.0, used_cost_month_usd: 0.01,
    proposed_cpu_request_mcpu: 10, proposed_ram_request_mib: 32,
    proposed_cost_month_usd: 0.48, potential_savings_month_usd: 3.52,
  }],
  summary: 'my-app est très surdimensionnée.',
  recommendations: [{
    title: 'Réduire les requests CPU', env: 'prod', action: 'cpu: 100m → 10m',
    current: '100 mCPU', proposed: '10 mCPU', monthly_savings_usd: 3.11,
    risk: 'bas', confidence: 'haute', rationale: 'p95 à 0,03 mCPU',
  }],
  raw_text: null, provider: 'anthropic', model: 'claude-haiku-4-5', notice: null,
  input_tokens: 900, output_tokens: 300, estimated_cost_usd: 0.0024,
};

function renderAdvisor(enabled = true) {
  vi.spyOn(assistantApi, 'getUiSettings').mockResolvedValue({
    assistant_enabled: enabled, graphical_bot_enabled: true,
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AIFinOpsAdvisor appId={1} />
    </QueryClientProvider>
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('AIFinOpsAdvisor', () => {
  it('lance l’analyse au clic et affiche les recommandations', async () => {
    const spy = vi.spyOn(assistantApi, 'getAiAdvice').mockResolvedValue(ADVICE);
    renderAdvisor();
    fireEvent.click(await screen.findByRole('button', { name: /Analyser la consommation/ }));

    expect(await screen.findByText('Réduire les requests CPU')).toBeTruthy();
    expect(spy).toHaveBeenCalledWith(1);
    expect(screen.getByText('my-app est très surdimensionnée.')).toBeTruthy();
    expect(screen.getByText('−$3.52')).toBeTruthy();
    expect(screen.getByText(/rien n'est appliqué automatiquement/)).toBeTruthy();
  });

  it("affiche le message d'erreur de l'API", async () => {
    vi.spyOn(assistantApi, 'getAiAdvice').mockRejectedValue({
      response: { data: { detail: "Quota de l'API Anthropic atteint. Réessayez dans une minute." } },
    });
    renderAdvisor();
    fireEvent.click(await screen.findByRole('button', { name: /Analyser la consommation/ }));
    expect(await screen.findByText(/Quota de l'API Anthropic atteint/)).toBeTruthy();
  });

  it("reste masqué quand l'assistant IA est désactivé", async () => {
    renderAdvisor(false);
    await waitFor(() => expect(assistantApi.getUiSettings).toHaveBeenCalled());
    expect(screen.queryByText('Conseiller FinOps IA')).toBeNull();
  });
});
