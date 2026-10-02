import { useMutation, useQuery } from '@tanstack/react-query';
import { IconArrowRight, IconCoin, IconRefresh, IconSparkles } from '@tabler/icons-react';
import { assistantApi } from '@/api/assistant';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { SimpleMarkdown } from '@/components/ui/SimpleMarkdown';
import { Spinner } from '@/components/ui/Spinner';
import type { AIFinOpsAdvice, FinOpsEnvSnapshot, FinOpsRecommendation } from '@/types';

const RISK_VARIANT: Record<string, 'success' | 'warning' | 'danger'> = {
  bas: 'success',
  moyen: 'warning',
  élevé: 'danger',
};

function usd(value: number | null | undefined): string {
  return value == null ? '—' : `$${value.toFixed(2)}`;
}

function qty(value: number | null | undefined, unit: string): string {
  return value == null ? 'non défini' : `${Math.round(value * 100) / 100} ${unit}`;
}

function apiError(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === 'string'
    ? detail
    : "L'analyse n'a pas pu aboutir. Réessayez dans un instant.";
}

function EnvSizing({ s }: { s: FinOpsEnvSnapshot }) {
  return (
    <div className="rounded-md border border-border p-3 text-xs">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-medium text-foreground">{s.env}</span>
        <span className="text-muted-foreground">
          {s.pods} pod{s.pods > 1 ? 's' : ''} · {s.restarts} redémarrage{s.restarts > 1 ? 's' : ''} ·{' '}
          {s.coverage_hours} h de métriques
        </span>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt className="text-muted-foreground">CPU</dt>
        <dd className="flex flex-wrap items-center gap-1">
          p95 {qty(s.cpu_p95_mcpu, 'm')} · request {qty(s.cpu_request_mcpu, 'm')}
          <IconArrowRight size={12} className="text-muted-foreground" />
          <span className="font-medium text-foreground">{s.proposed_cpu_request_mcpu} m</span>
        </dd>
        <dt className="text-muted-foreground">RAM</dt>
        <dd className="flex flex-wrap items-center gap-1">
          max {qty(s.ram_max_mib, 'Mi')} · request {qty(s.ram_request_mib, 'Mi')}
          <IconArrowRight size={12} className="text-muted-foreground" />
          <span className="font-medium text-foreground">{s.proposed_ram_request_mib} Mi</span>
        </dd>
        <dt className="text-muted-foreground">Coût / mois</dt>
        <dd className="flex flex-wrap items-center gap-1">
          réservé {usd(s.reserved_cost_month_usd)}
          <IconArrowRight size={12} className="text-muted-foreground" />
          <span className="font-medium text-foreground">{usd(s.proposed_cost_month_usd)}</span>
          {s.potential_savings_month_usd != null && s.potential_savings_month_usd > 0 && (
            <Badge variant="success">−{usd(s.potential_savings_month_usd)}</Badge>
          )}
        </dd>
      </dl>
    </div>
  );
}

function RecommendationItem({ r }: { r: FinOpsRecommendation }) {
  return (
    <li className="rounded-md border border-border p-3">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-foreground">{r.title}</span>
        <Badge variant="muted">{r.env}</Badge>
        <Badge variant={RISK_VARIANT[r.risk] ?? 'warning'}>risque {r.risk}</Badge>
        <Badge variant="info">confiance {r.confidence}</Badge>
        {r.monthly_savings_usd != null && r.monthly_savings_usd > 0 && (
          <Badge variant="success">−{usd(r.monthly_savings_usd)}/mois</Badge>
        )}
      </div>
      <p className="text-xs text-foreground">{r.action}</p>
      {(r.current || r.proposed) && (
        <p className="mt-1 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
          {r.current} <IconArrowRight size={12} /> {r.proposed}
        </p>
      )}
      {r.rationale && <p className="mt-1 text-xs text-muted-foreground">{r.rationale}</p>}
    </li>
  );
}

function AdviceBody({ advice }: { advice: AIFinOpsAdvice }) {
  if (advice.status !== 'ok') {
    return <p className="text-sm text-muted-foreground">{advice.summary}</p>;
  }
  return (
    <div className="flex flex-col gap-3">
      {advice.notice && (
        <p className="rounded-md bg-warning-subtle px-3 py-2 text-xs text-warning-text">{advice.notice}</p>
      )}
      {advice.summary && <p className="text-sm text-foreground">{advice.summary}</p>}
      <div className="grid gap-2 md:grid-cols-2">
        {advice.metrics.map((s) => (
          <EnvSizing key={s.env} s={s} />
        ))}
      </div>
      {advice.recommendations.length > 0 && (
        <ul className="flex flex-col gap-2">
          {advice.recommendations.map((r, i) => (
            <RecommendationItem key={`${r.title}-${i}`} r={r} />
          ))}
        </ul>
      )}
      {advice.raw_text && (
        <div className="rounded-md border border-border p-3 text-sm">
          <SimpleMarkdown content={advice.raw_text} />
        </div>
      )}
      <p className="text-[11px] text-muted-foreground">
        {advice.model ?? advice.provider} · {advice.input_tokens + advice.output_tokens} tokens
        {advice.estimated_cost_usd != null && ` · ~$${advice.estimated_cost_usd.toFixed(4)}`} ·
        Conseils uniquement : rien n'est appliqué automatiquement (à reporter dans le chart Helm).
      </p>
    </div>
  );
}

/** Conseiller FinOps IA (4K-46) : right-sizing à partir des 24 dernières heures de métriques. */
export function AIFinOpsAdvisor({ appId }: { appId: number }) {
  const { data: uiSettings } = useQuery({
    queryKey: ['ai-ui-settings'],
    queryFn: assistantApi.getUiSettings,
    retry: false,
  });
  const advice = useMutation({ mutationFn: () => assistantApi.getAiAdvice(appId) });

  if (!uiSettings?.assistant_enabled) return null;

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-sm font-medium text-foreground">
          <IconCoin size={14} />
          Conseiller FinOps IA
        </h2>
        {advice.data && !advice.isPending && (
          <Button variant="ghost" size="sm" icon={<IconRefresh size={13} />} onClick={() => advice.mutate()}>
            Relancer
          </Button>
        )}
      </div>

      {advice.isPending ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Spinner size="sm" />
          Analyse des 24 dernières heures de métriques et rédaction des recommandations…
        </div>
      ) : advice.isError ? (
        <div className="flex flex-col items-start gap-2">
          <p className="text-sm text-danger-text">{apiError(advice.error)}</p>
          <Button variant="secondary" size="sm" onClick={() => advice.mutate()}>
            Réessayer
          </Button>
        </div>
      ) : advice.data ? (
        <AdviceBody advice={advice.data} />
      ) : (
        <div className="flex flex-col items-start gap-2">
          <p className="text-sm text-muted-foreground">
            Analyse la consommation CPU/RAM réelle (Prometheus, 24 h) et propose des ajustements de
            ressources pour réduire le coût, sans risque pour l'application.
          </p>
          <Button variant="primary" size="sm" icon={<IconSparkles size={13} />} onClick={() => advice.mutate()}>
            Analyser la consommation
          </Button>
        </div>
      )}
    </Card>
  );
}
