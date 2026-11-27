"""AI FinOps advisor (4K-46): right-sizing recommendations from Prometheus metrics.

Flow: Prometheus (24 h of CPU/RAM per environment + requests/limits) → reference
sizing computed here (deterministic, LLMs are poor at arithmetic) → the platform AI
provider (Réglages plateforme → Assistant IA) writes the recommendations.

The analysis (analyze_usage / describe_analysis) is shared by two consumers:
- GET /apps/{id}/ai-advice: one LLM call, JSON answer, validated and returned;
- the global assistant tool get_finops_advice: the figures are handed to the
  chat model, which writes the recommendations in the conversation.

Proof of concept: no cache. Advice only — nothing is ever applied automatically.

No imports from backend.api.*.
"""
from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from shared.models import AIPurpose
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ai.factory import get_provider
from backend.ai.pricing import estimate_cost
from backend.ai.provider import LLMMessage
from backend.core.config import settings
from backend.db.models import AIUsageRecord, Application, User
from backend.services.ai_settings_service import EffectiveAIConfig
from backend.services.monitoring_service import (
    CPU_CORE_HOUR_USD,
    HOURS_PER_MONTH,
    RAM_GIB_HOUR_USD,
    get_app_resource_usage,
)
from backend.services.monitoring_sources import resolve_prometheus_url

logger = logging.getLogger(__name__)

# Sizing rules of the reference proposal.
_HEADROOM = 1.3          # 30 % above the observed peak
_MIN_CPU_MCPU = 10
_MIN_RAM_MIB = 32
_MAX_OUTPUT_TOKENS = 2048

_SYSTEM_PROMPT = """\
You are the FinOps advisor of the Cloud Native Platform (CNP). You analyse the actual \
consumption of a Kubernetes application and recommend resource adjustments \
(right-sizing) or other cost optimisations.

Rules:
- Rely ONLY on the data provided; never invent a value.
- Use the figures of the "reference proposal" (already computed) for the proposed resources \
and the savings; do not redo the calculations.
- Memory: never propose a request below the observed maximum (OOMKill risk).
- If the metrics coverage is short (less than 24 h) or there are restarts, lower the \
confidence level and say so.
- If the app is already right-sized, say so and do not force a recommendation.
- Changes are made in the app's Helm chart (resources.requests / resources.limits); \
nothing is applied automatically, the team validates.
- Write every text field in English, concisely, even when the data is labelled in French.

Answer with ONE SINGLE JSON object, with no text around it, in this format:
{
  "summary": "2 sentences maximum: overall state and possible gain",
  "recommendations": [
    {
      "title": "short title",
      "env": "prod | dev | toutes",
      "action": "what to change, concretely",
      "current": "current value",
      "proposed": "proposed value",
      "monthly_savings_usd": 0.0,
      "risk": "bas | moyen | élevé",
      "confidence": "haute | moyenne | faible",
      "rationale": "short justification based on the metrics"
    }
  ]
}

JSON keys and enum values are a fixed contract, never translate them: "env" is exactly one \
of prod, dev or toutes (all environments); "risk" is exactly one of bas, moyen or élevé \
(low, medium, high); "confidence" is exactly one of haute, moyenne or faible (high, medium, low).
"""

_LEVELS = {"bas", "moyen", "élevé"}
_CONFIDENCE = {"haute", "moyenne", "faible"}


@dataclass
class EnvSnapshot:
    env: str
    pods: int
    restarts: int
    coverage_hours: float
    cpu_avg_mcpu: float
    cpu_p95_mcpu: float
    cpu_max_mcpu: float
    ram_avg_mib: float
    ram_p95_mib: float
    ram_max_mib: float
    cpu_request_mcpu: Optional[float]
    cpu_limit_mcpu: Optional[float]
    ram_request_mib: Optional[float]
    ram_limit_mib: Optional[float]
    reserved_cost_month_usd: Optional[float]
    used_cost_month_usd: float
    proposed_cpu_request_mcpu: int
    proposed_ram_request_mib: int
    proposed_cost_month_usd: float
    potential_savings_month_usd: Optional[float]


@dataclass
class UsageAnalysis:
    status: str                      # "ok" | "no_data" | "metrics_unavailable"
    window_hours: int
    snapshots: list[EnvSnapshot] = field(default_factory=list)
    message: str = ""                # why there is nothing to analyse (status != "ok")


@dataclass
class Recommendation:
    title: str
    env: str
    action: str
    current: str
    proposed: str
    monthly_savings_usd: Optional[float]
    risk: str
    confidence: str
    rationale: str


@dataclass
class AdviceResult:
    app_id: int
    app_name: str
    status: str                      # "ok" | "no_data" | "metrics_unavailable"
    window_hours: int
    generated_at: datetime
    metrics: list[EnvSnapshot] = field(default_factory=list)
    summary: str = ""
    recommendations: list[Recommendation] = field(default_factory=list)
    raw_text: Optional[str] = None   # LLM answer when it could not be parsed as JSON
    provider: Optional[str] = None
    model: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: Optional[float] = None


# ── Reference sizing (deterministic) ─────────────────────────────────────────


def _monthly_cost(cpu_mcpu: float, ram_mib: float) -> float:
    cores = cpu_mcpu / 1000
    gib = ram_mib / 1024
    return (cores * CPU_CORE_HOUR_USD + gib * RAM_GIB_HOUR_USD) * HOURS_PER_MONTH


def build_snapshot(env: str, raw: dict, step_seconds: int) -> EnvSnapshot:
    cpu, ram = raw["cpu_mcpu"], raw["ram_mib"]
    proposed_cpu = max(_MIN_CPU_MCPU, math.ceil(cpu["p95"] * _HEADROOM))
    # Memory is not compressible: size on the peak, not on p95.
    proposed_ram = max(_MIN_RAM_MIB, math.ceil(ram["max"] * _HEADROOM))
    cpu_req, ram_req = raw["cpu_request_mcpu"], raw["ram_request_mib"]

    reserved = (
        _monthly_cost(cpu_req or 0.0, ram_req or 0.0)
        if cpu_req is not None or ram_req is not None
        else None
    )
    proposed_cost = _monthly_cost(proposed_cpu, proposed_ram)
    return EnvSnapshot(
        env=env,
        pods=raw["pods"],
        restarts=raw["restarts"],
        coverage_hours=round(max(cpu["points"], ram["points"]) * step_seconds / 3600, 2),
        cpu_avg_mcpu=round(cpu["avg"], 2),
        cpu_p95_mcpu=round(cpu["p95"], 2),
        cpu_max_mcpu=round(cpu["max"], 2),
        ram_avg_mib=round(ram["avg"], 1),
        ram_p95_mib=round(ram["p95"], 1),
        ram_max_mib=round(ram["max"], 1),
        cpu_request_mcpu=cpu_req,
        cpu_limit_mcpu=raw["cpu_limit_mcpu"],
        ram_request_mib=ram_req,
        ram_limit_mib=raw["ram_limit_mib"],
        reserved_cost_month_usd=round(reserved, 2) if reserved is not None else None,
        used_cost_month_usd=round(_monthly_cost(cpu["avg"], ram["avg"]), 2),
        proposed_cpu_request_mcpu=proposed_cpu,
        proposed_ram_request_mib=proposed_ram,
        proposed_cost_month_usd=round(proposed_cost, 2),
        potential_savings_month_usd=(
            round(max(0.0, reserved - proposed_cost), 2) if reserved is not None else None
        ),
    )


def _fmt(value: Optional[float], unit: str) -> str:
    return "not set" if value is None else f"{value:g} {unit}"


def build_user_prompt(app: Application, snapshots: list[EnvSnapshot], window_hours: int) -> str:
    lines = [
        f"Application: {app.name} (slug {app.slug}, framework {app.framework or 'not specified'})",
        f"Requested window: {window_hours} h. Prices: CPU ${CPU_CORE_HOUR_USD}/core·h, "
        f"RAM ${RAM_GIB_HOUR_USD}/GiB·h, month = {HOURS_PER_MONTH} h.",
    ]
    for s in snapshots:
        lines += [
            f"\n=== Environment {s.env} ===",
            f"Pods: {s.pods} — restarts over the window: {s.restarts} — "
            f"actual metrics coverage: {s.coverage_hours} h",
            f"CPU used: average {s.cpu_avg_mcpu} mCPU, p95 {s.cpu_p95_mcpu}, max {s.cpu_max_mcpu}",
            f"RAM used: average {s.ram_avg_mib} MiB, p95 {s.ram_p95_mib}, max {s.ram_max_mib}",
            f"Requests: CPU {_fmt(s.cpu_request_mcpu, 'mCPU')}, RAM {_fmt(s.ram_request_mib, 'MiB')} — "
            f"Limits: CPU {_fmt(s.cpu_limit_mcpu, 'mCPU')}, RAM {_fmt(s.ram_limit_mib, 'MiB')}",
            f"Reserved monthly cost (requests): "
            f"{'$' + str(s.reserved_cost_month_usd) if s.reserved_cost_month_usd is not None else 'no requests'}"
            f" — cost of actual usage: ${s.used_cost_month_usd}",
            f"Reference proposal: requests CPU {s.proposed_cpu_request_mcpu} mCPU "
            f"(p95 × {_HEADROOM}), RAM {s.proposed_ram_request_mib} MiB (max × {_HEADROOM}) → "
            f"${s.proposed_cost_month_usd}/month"
            + (
                f", potential saving ${s.potential_savings_month_usd}/month"
                if s.potential_savings_month_usd is not None
                else ""
            ),
        ]
    return "\n".join(lines)


# Rules handed to the global assistant with the figures (get_finops_advice).
_ASSISTANT_GUIDANCE = """\
Guidelines for writing the FinOps recommendations:
- Reuse the figures of the "reference proposal"; do not redo the calculations.
- Memory: never propose a request below the observed maximum (OOMKill risk).
- Coverage < 24 h or restarts: lower the confidence level and say so.
- App already right-sized: say so, without forcing a recommendation.
- For each recommendation: environment, current → proposed value, monthly saving,
  risk (low / medium / high) and confidence (high / medium / low).
- Changes are made in the app's Helm chart (resources.requests / resources.limits);
  nothing is applied automatically, the team validates."""


async def _prometheus_url(db: AsyncSession, app: Application) -> str:
    """Prometheus of the app's target cluster, else the platform one."""
    return await resolve_prometheus_url(db, app=app)


async def analyze_usage(db: AsyncSession, app: Application) -> UsageAnalysis:
    """Prometheus usage over the advisor window + reference sizing, per environment."""
    window = settings.AI_FINOPS_WINDOW_HOURS
    step = 900 if window >= 6 else 60
    try:
        raw = await get_app_resource_usage(await _prometheus_url(db, app), app.slug, window, step)
    except Exception as exc:
        logger.warning("FinOps advisor: Prometheus query failed for %s", app.slug, exc_info=True)
        return UsageAnalysis(
            status="metrics_unavailable", window_hours=window,
            message=f"Metrics unavailable: Prometheus unreachable ({type(exc).__name__}).",
        )

    snapshots = [
        build_snapshot(env, data, step)
        for env, data in sorted(raw.items())
        if data["cpu_mcpu"]["points"] or data["ram_mib"]["points"]
    ]
    if not snapshots:
        return UsageAnalysis(
            status="no_data", window_hours=window,
            message=(
                f"No metrics for {app.name} over the last {window} hours: the app "
                "is not deployed, is stopped, or its pods do not have the label "
                "app.kubernetes.io/managed-by=cnp."
            ),
        )
    return UsageAnalysis(status="ok", window_hours=window, snapshots=snapshots)


def describe_analysis(app: Application, analysis: UsageAnalysis) -> str:
    """Plain-text analysis for the global assistant (figures + writing rules)."""
    if analysis.status != "ok":
        return analysis.message
    return (
        f"FinOps analysis of {app.name} (Prometheus, last {analysis.window_hours} hours):\n"
        f"{build_user_prompt(app, analysis.snapshots, analysis.window_hours)}\n\n"
        f"{_ASSISTANT_GUIDANCE}"
    )


# ── LLM answer parsing ───────────────────────────────────────────────────────

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_advice(text: str) -> tuple[str, list[Recommendation]] | None:
    """Extract {summary, recommendations} from the LLM answer, or None if not JSON."""
    cleaned = _FENCE_RE.sub("", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    recs: list[Recommendation] = []
    for item in data.get("recommendations") or []:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        savings = item.get("monthly_savings_usd")
        try:
            savings = round(float(savings), 2) if savings is not None else None
        except (TypeError, ValueError):
            savings = None
        risk = str(item.get("risk", "")).strip().lower()
        confidence = str(item.get("confidence", "")).strip().lower()
        recs.append(Recommendation(
            title=str(item["title"])[:120],
            env=str(item.get("env", "toutes"))[:20],
            action=str(item.get("action", ""))[:600],
            current=str(item.get("current", ""))[:120],
            proposed=str(item.get("proposed", ""))[:120],
            monthly_savings_usd=savings,
            risk=risk if risk in _LEVELS else "moyen",
            confidence=confidence if confidence in _CONFIDENCE else "faible",
            rationale=str(item.get("rationale", ""))[:600],
        ))
    return str(data.get("summary", ""))[:600], recs


# ── Service ──────────────────────────────────────────────────────────────────


class FinOpsAdvisorService:
    def __init__(self, db: AsyncSession, cfg: EffectiveAIConfig) -> None:
        self.db = db
        self.cfg = cfg

    async def advise(self, app: Application, user: User) -> AdviceResult:
        analysis = await analyze_usage(self.db, app)
        result = AdviceResult(
            app_id=app.id, app_name=app.name, status=analysis.status,
            window_hours=analysis.window_hours, generated_at=datetime.now(timezone.utc),
            metrics=analysis.snapshots, summary=analysis.message,
        )
        if analysis.status != "ok":
            # No LLM call when there is nothing to analyse (cost + no hallucination).
            return result

        # Same provider and model as the assistant (Réglages plateforme → Assistant IA).
        provider = get_provider(self.cfg.provider_name, self.cfg.api_key)
        label = type(provider).__name__.replace("Provider", "").lower()
        llm = await provider.complete(
            messages=[
                LLMMessage(role="system", content=_SYSTEM_PROMPT),
                LLMMessage(
                    role="user",
                    content=build_user_prompt(app, analysis.snapshots, analysis.window_hours),
                ),
            ],
            model=self.cfg.model,
            max_tokens=_MAX_OUTPUT_TOKENS,
            temperature=0.2,
        )
        result.provider, result.model = label, llm.model
        result.input_tokens, result.output_tokens = llm.input_tokens, llm.output_tokens
        result.estimated_cost_usd = estimate_cost(llm.model, llm.input_tokens, llm.output_tokens)

        parsed = parse_advice(llm.content)
        if parsed is None:
            result.raw_text = llm.content
        else:
            result.summary, result.recommendations = parsed

        self.db.add(AIUsageRecord(
            app_id=app.id, user_id=user.id, provider=label, model=llm.model,
            purpose=AIPurpose.FINOPS, input_tokens=llm.input_tokens,
            output_tokens=llm.output_tokens, estimated_cost_usd=result.estimated_cost_usd,
        ))
        await self.db.commit()
        return result
