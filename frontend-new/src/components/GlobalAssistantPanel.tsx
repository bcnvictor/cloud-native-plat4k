import { useState, useRef, useEffect, useLayoutEffect, useCallback, useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { IconX, IconSend, IconStethoscope } from '@tabler/icons-react';
import { assistantApi, toChatHistory } from '@/api/assistant';
import { appsApi } from '@/api/apps';
import { ChatTurn, DoctorEnv } from '@/types';
import {
  ASSISTANT_ASK_EVENT,
  AssistantAskDetail,
  chatMessagesOnly,
  docSources,
  doctorSuggestionsFor,
  greetingFor,
  modeNotice,
  pageContextFrom,
  suggestionsFor,
  waitHint,
} from '@/utils/assistantContext';
import { getAppHealth } from '@/utils/appHealth';
import { doctorKey, useDoctorStore } from '@/store/doctor';
import { SimpleMarkdown } from '@/components/ui/SimpleMarkdown';
import { BotAvatar, Mascot } from '@/components/assistant/Mascot';
import { ModeToggle } from '@/components/assistant/ModeToggle';
import { DoctorThreadMessage } from '@/components/assistant/DoctorThreadMessage';
import { cn } from '@/utils/cn';

interface LocalMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: string[];
  /**
   * `local` : accueil et changement de mode ; `diagnosis` : diagnostic lié au store.
   * Ni l'un ni l'autre n'est envoyé dans l'historique du chat.
   */
  kind?: 'local' | 'diagnosis';
  diagnosis?: { appId: number; env: DoctorEnv; appName?: string };
}

interface Props {
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
}

/** La mascotte fait signe toutes les X ms quand le tiroir est fermé. */
const ATTENTION_INTERVAL_MS = 60_000;
const ATTENTION_DURATION_MS = 3_600;

const DOCTOR_ENVS: DoctorEnv[] = ['prod', 'dev'];

function diagnosisMessage(appId: number, env: DoctorEnv, appName?: string): LocalMessage {
  return {
    id: `diag-${appId}-${env}-${Date.now()}`,
    role: 'assistant',
    content: '',
    kind: 'diagnosis',
    diagnosis: { appId, env, appName },
  };
}

function isDiagnosisOf(m: LocalMessage, appId: number, env: DoctorEnv): boolean {
  return m.kind === 'diagnosis' && m.diagnosis?.appId === appId && m.diagnosis.env === env;
}

function TypingDots({ className }: { className?: string }) {
  return (
    <>
      <span className={cn('h-1.5 w-1.5 rounded-full animate-[dotPulse_1.1s_infinite]', className)} />
      <span
        className={cn(
          'h-1.5 w-1.5 rounded-full animate-[dotPulse_1.1s_infinite] [animation-delay:.18s]',
          className
        )}
      />
      <span
        className={cn(
          'h-1.5 w-1.5 rounded-full animate-[dotPulse_1.1s_infinite] [animation-delay:.36s]',
          className
        )}
      />
    </>
  );
}

export function GlobalAssistantPanel({ open, onToggle, onClose }: Props) {
  const { pathname } = useLocation();
  const page = useMemo(() => pageContextFrom(pathname), [pathname]);
  const appSlug = page.app_slug;
  const suggestions = useMemo(() => suggestionsFor(page), [page]);
  const doctorSuggestions = useMemo(() => doctorSuggestionsFor(page), [page]);

  const mode = useDoctorStore((s) => s.mode);
  const runs = useDoctorStore((s) => s.runs);
  const setModeManual = useDoctorStore((s) => s.setModeManual);
  const isDoctor = mode === 'doctor';

  const conversationId = useRef<string | undefined>(undefined);
  const msgRef = useRef<HTMLDivElement>(null);
  const dockRef = useRef<HTMLDivElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
  const slotRef = useRef<HTMLDivElement>(null);
  const robotBtnRef = useRef<HTMLButtonElement>(null);
  const talkTimeout = useRef<ReturnType<typeof setTimeout>>();
  const attnTimeout = useRef<ReturnType<typeof setTimeout>>();
  const [messages, setMessages] = useState<LocalMessage[]>(() => [
    { id: 'greeting', role: 'assistant', content: greetingFor(mode), kind: 'local' },
  ]);
  const [input, setInput] = useState('');
  const [globallyDisabled, setGloballyDisabled] = useState(false);
  const [attn, setAttn] = useState(false);
  const [talk, setTalk] = useState(false);
  const [announcement, setAnnouncement] = useState('');

  const { data: uiSettings } = useQuery({
    queryKey: ['ai-ui-settings'],
    queryFn: assistantApi.getUiSettings,
    retry: false,
  });
  const graphicalBotEnabled = uiSettings?.graphical_bot_enabled ?? true;

  // Application affichée : même clé que AppDetailLayout, donc servie depuis le cache.
  const { data: app } = useQuery({
    queryKey: ['app', appSlug],
    queryFn: () => appsApi.getBySlug(appSlug!),
    enabled: !!appSlug,
  });
  const currentApp = appSlug ? app : undefined;
  const appUnhealthy = !!currentApp && getAppHealth(currentApp) === 'unhealthy';

  // Bascule automatique. L'ordre compte : le contexte d'abord (retour au chatbot et
  // oubli du choix manuel quand l'application change), puis le passage en docteur.
  useEffect(() => {
    useDoctorStore.getState().setContext(page.app_slug ?? null);
  }, [pathname]);

  useEffect(() => {
    if (appUnhealthy) useDoctorStore.getState().autoDoctor();
  }, [appUnhealthy, appSlug]);

  useEffect(() => {
    if (uiSettings?.assistant_enabled === false) {
      setGloballyDisabled(true);
    } else if (uiSettings?.assistant_enabled === true) {
      setGloballyDisabled(false);
    }
  }, [uiSettings?.assistant_enabled]);

  function wave(ms = 1600) {
    setTalk(true);
    clearTimeout(talkTimeout.current);
    talkTimeout.current = setTimeout(() => setTalk(false), ms);
  }

  // Mesure FLIP du vol du robot vers le bandeau héro. Les unités viewport
  // (100vh) sont résolues différemment sous `zoom` body selon les navigateurs
  // (Chrome legacy vs Firefox spec) : on mesure donc la cible réelle et on
  // injecte le delta en px locaux via --dock-tx/--dock-ty.
  const measureDockFlight = useCallback(() => {
    if (!graphicalBotEnabled) return;
    const dock = dockRef.current;
    const btn = robotBtnRef.current;
    const drawer = drawerRef.current;
    const slot = slotRef.current;
    if (!dock || !btn || !drawer || !slot) return;

    // Neutralise le transform du dock le temps de la mesure (aucun paint
    // n'a lieu entre les deux : invisible à l'écran).
    const prevTransform = dock.style.transform;
    const prevTransition = dock.style.transition;
    dock.style.transition = 'none';
    dock.style.transform = 'none';
    const b = btn.getBoundingClientRect(); // position naturelle du robot (coin)
    const d = drawer.getBoundingClientRect();
    const s = slot.getBoundingClientRect();
    dock.style.transform = prevTransform;
    dock.style.transition = prevTransition;

    // Le tiroir ouvert est ancré top:0 / right:0 ; l'offset du slot dans le
    // tiroir est invariant par translation, donc sa position finale se déduit
    // sans dépendre de l'état de la transition du tiroir.
    const finalX = window.innerWidth - d.width + (s.x - d.x);
    const finalY = s.y - d.y;
    // getBoundingClientRect renvoie des px viewport ; le translate CSS du dock
    // s'exprime en px locaux (zoomés). Le robot fait 92px locaux de large.
    const zoom = b.width / 92 || 1;
    dock.style.setProperty('--dock-tx', `${(finalX - b.x) / zoom}px`);
    dock.style.setProperty('--dock-ty', `${(finalY - b.y) / zoom}px`);
  }, [graphicalBotEnabled]);

  useLayoutEffect(() => {
    if (open && graphicalBotEnabled) measureDockFlight();
  }, [open, graphicalBotEnabled, measureDockFlight]);

  useEffect(() => {
    if (!open || !graphicalBotEnabled) return;
    window.addEventListener('resize', measureDockFlight);
    return () => window.removeEventListener('resize', measureDockFlight);
  }, [open, graphicalBotEnabled, measureDockFlight]);

  // Signe de la main périodique quand le tiroir est fermé
  useEffect(() => {
    if (open || globallyDisabled || !graphicalBotEnabled) return;
    const interval = setInterval(() => {
      setAttn(true);
      clearTimeout(attnTimeout.current);
      attnTimeout.current = setTimeout(() => setAttn(false), ATTENTION_DURATION_MS);
    }, ATTENTION_INTERVAL_MS);
    return () => {
      clearInterval(interval);
      clearTimeout(attnTimeout.current);
    };
  }, [open, globallyDisabled, graphicalBotEnabled]);

  useEffect(() => () => clearTimeout(talkTimeout.current), []);

  useEffect(() => {
    if (open && graphicalBotEnabled) {
      setAttn(false);
      wave(1800);
    }
  }, [open, graphicalBotEnabled]);

  // Clavier : à l'ouverture, le focus entre dans le tiroir (sinon il faut traverser
  // toute la page pour l'atteindre) ; à la fermeture, il revient à l'élément qui l'a
  // ouvert, s'il était resté dans le tiroir.
  useEffect(() => {
    if (!open) return;
    const active = document.activeElement;
    const opener = active instanceof HTMLElement && !drawerRef.current?.contains(active) ? active : null;
    // La classe is-open est déjà posée : le tiroir est visible, donc focalisable.
    drawerRef.current?.focus({ preventScroll: true });
    return () => {
      if (opener?.isConnected && drawerRef.current?.contains(document.activeElement)) {
        opener.focus({ preventScroll: true });
      }
    };
  }, [open]);

  // Changement de mode : annonce vocale et message dans le fil (la conversation
  // est conservée ; un fil sans échange repart simplement du nouvel accueil).
  const previousMode = useRef(mode);
  useEffect(() => {
    if (previousMode.current === mode) return;
    previousMode.current = mode;
    setAnnouncement(mode === 'doctor' ? 'Mode Doctor activé' : 'Mode Assistant activé');
    const consulted = currentApp?.name ?? appSlug;
    setMessages((prev) => {
      const id = `mode-${Date.now()}`;
      if (prev.every((m) => m.kind === 'local')) {
        return [{ id, role: 'assistant', content: greetingFor(mode, consulted), kind: 'local' }];
      }
      const notice: LocalMessage = {
        id,
        role: 'assistant',
        content: modeNotice(mode, consulted),
        kind: 'local',
      };
      const last = prev[prev.length - 1];
      // Deux bascules d'affilée : on remplace l'annonce précédente au lieu d'empiler.
      if (last?.kind === 'local' && last.id.startsWith('mode-')) {
        return [...prev.slice(0, -1), notice];
      }
      return [...prev, notice];
    });
  }, [mode]);

  // Diagnostic lancé ailleurs (carte d'Overview) pour l'application affichée : on
  // l'ajoute au fil, il se met à jour depuis le store. Abonnement direct au store
  // pour voir chaque lancement, même si la réponse arrive dans le même rendu.
  const appId = currentApp?.id;
  const appName = currentApp?.name;
  useEffect(() => {
    if (appId == null) return;
    return useDoctorStore.subscribe((state, prev) => {
      for (const env of DOCTOR_ENVS) {
        const key = doctorKey(appId, env);
        if (state.runs[key]?.status !== 'running' || prev.runs[key]?.status === 'running') continue;
        setMessages((msgs) =>
          msgs.some((m) => isDiagnosisOf(m, appId, env))
            ? msgs
            : [...msgs, diagnosisMessage(appId, env, appName)]
        );
      }
    });
  }, [appId, appName]);

  function diagnoseFromPanel(env: DoctorEnv) {
    if (!currentApp) return;
    const { id, name } = currentApp;
    // Un seul message par application et environnement : il descend en bas du fil.
    setMessages((prev) => [
      ...prev.filter((m) => !isDiagnosisOf(m, id, env)),
      diagnosisMessage(id, env, name),
    ]);
    void useDoctorStore.getState().diagnose(id, env);
  }

  const chatMutation = useMutation({
    mutationFn: ({ message, history }: { message: string; history: ChatTurn[] }) =>
      assistantApi.chatGlobal({
        message,
        agent: 'platform',
        conversation_id: conversationId.current,
        history,
        page,
      }),
    onSuccess: (data) => {
      conversationId.current = data.conversation_id;
      const citations = docSources(data.citations);
      setMessages((prev) => [
        ...prev,
        {
          id: data.conversation_id + Date.now(),
          role: 'assistant',
          content: data.answer,
          citations: citations.length ? citations : undefined,
        },
      ]);
      wave(1600);
    },
    onError: (err: unknown) => {
      const response = (err as { response?: { status?: number; data?: { detail?: string } } })
        ?.response;
      const status = response?.status;
      if (status === 503) {
        setGloballyDisabled(true);
        return;
      }
      const detail =
        typeof response?.data?.detail === 'string'
          ? response.data.detail
          : "Une erreur est survenue lors de la requête à l'assistant. Réessayez.";
      setMessages((prev) => [
        ...prev,
        { id: 'err' + Date.now(), role: 'assistant', content: `⚠️ ${detail}` },
      ]);
    },
  });

  // Message d'attente progressif tant que la réponse n'est pas arrivée
  const [pendingSince, setPendingSince] = useState<number | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  useEffect(() => {
    if (!chatMutation.isPending) {
      setPendingSince(null);
      setHint(null);
      return;
    }
    const start = Date.now();
    setPendingSince(start);
    const timer = setInterval(() => setHint(waitHint(Date.now() - start)), 1_000);
    return () => clearInterval(timer);
  }, [chatMutation.isPending]);

  // Défilement auto vers le dernier message (un diagnostic grandit en se terminant)
  useEffect(() => {
    const el = msgRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, chatMutation.isPending, hint, runs]);

  function ask(text: string) {
    const msg = text.trim();
    if (!msg || chatMutation.isPending) return;
    setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'user', content: msg }]);
    setInput('');
    // Diagnostics et messages locaux ne partent jamais dans l'historique du modèle.
    chatMutation.mutate({ message: msg, history: toChatHistory(chatMessagesOnly(messages)) });
  }

  // Questions posées depuis un bouton « Expliquer avec l'IA » ailleurs dans l'UI.
  const askRef = useRef(ask);
  askRef.current = ask;
  useEffect(() => {
    const onAsk = (e: Event) => {
      const question = (e as CustomEvent<AssistantAskDetail>).detail?.question;
      if (question) askRef.current(question);
    };
    window.addEventListener(ASSISTANT_ASK_EVENT, onAsk);
    return () => window.removeEventListener(ASSISTANT_ASK_EVENT, onAsk);
  }, []);

  const title = isDoctor ? 'CNP Doctor' : 'Assistant Plat4k';
  const status = isDoctor
    ? appSlug
      ? `En consultation · ${currentApp?.name ?? appSlug}`
      : 'Prêt pour un diagnostic'
    : 'En ligne · prêt à vous aider';
  // Robot docké, tiroir fermé, application en erreur : proposer le diagnostic.
  const offerDiagnosis = !open && !globallyDisabled && isDoctor && appUnhealthy;

  const chipClass =
    'rounded-[20px] border border-border bg-card px-3 py-[7px] text-xs font-medium text-muted-foreground hover:border-primary hover:bg-primary-50 hover:text-primary';

  return (
    <div
      className={cn(
        'plat4k-assistant',
        open && 'is-open',
        graphicalBotEnabled && ((attn && !open) || talk) && 'is-attn'
      )}
    >
      {/* Annonce du changement de mode (hors du tiroir : audible tiroir fermé) */}
      <div className="sr-only" aria-live="polite">
        {announcement}
      </div>

      {/* ===== Tiroir de chat (glisse depuis la droite) ===== */}
      <div
        ref={drawerRef}
        className="m-drawer fixed inset-y-0 right-0 z-40 flex w-[440px] max-w-[calc(92vw/1.25)] flex-col border-l border-border bg-background shadow-[-24px_0_60px_rgba(31,44,84,.14)] focus-visible:ring-0 focus-visible:ring-offset-0"
        role="region"
        aria-label={title}
        tabIndex={-1}
        aria-hidden={!open}
        data-mode={mode}
        onKeyDown={(e) => {
          // Échap ferme le tiroir (les confirmations du Doctor arrêtent l'événement avant).
          if (e.key === 'Escape' && open) {
            e.stopPropagation();
            onClose();
          }
        }}
      >
        {/* Bandeau héro : le robot vient se docker sur la gauche */}
        <div
          className={cn(
            'relative flex-none border-b border-border',
            graphicalBotEnabled
              ? 'h-[150px] bg-gradient-to-b from-primary-50 to-background'
              : 'h-[132px] bg-background'
          )}
        >
          {/* Cible du vol du robot (mesurée par measureDockFlight) */}
          {graphicalBotEnabled && (
            <div
              ref={slotRef}
              aria-hidden="true"
              className="pointer-events-none absolute left-2 top-5 h-[104px] w-[92px]"
            />
          )}
          <button
            onClick={onClose}
            aria-label="Fermer"
            className="absolute right-3.5 top-3.5 flex h-[30px] w-[30px] items-center justify-center rounded-lg bg-foreground/5 text-muted-foreground hover:bg-foreground/10 hover:text-foreground"
          >
            <IconX size={16} />
          </button>
          <div
            className={cn(
              'absolute right-4',
              graphicalBotEnabled ? 'left-[150px] top-11 max-sm:left-[112px]' : 'left-5 top-6'
            )}
          >
            <div
              className={cn(
                'truncate text-[17px] font-bold text-foreground',
                !graphicalBotEnabled && 'pr-10'
              )}
            >
              {title}
            </div>
            <div className="mt-1.5 flex min-w-0 items-center gap-1.5">
              <span className="h-[7px] w-[7px] flex-none rounded-full bg-success shadow-[0_0_0_3px_rgba(34,197,94,.16)]" />
              <span className="truncate text-xs font-medium text-muted-foreground">{status}</span>
            </div>
            <ModeToggle className="mt-3" mode={mode} onChange={setModeManual} />
          </div>
        </div>

        {globallyDisabled ? (
          <div className="flex flex-1 items-center justify-center p-6 text-center">
            <div>
              <p className="text-sm font-medium text-foreground">Assistant IA inactif</p>
              <p className="mt-1 text-xs text-muted-foreground">
                La fonctionnalité IA est désactivée sur cette plateforme. Un administrateur
                peut l’activer dans Platform → Settings → AI assistant.
              </p>
            </div>
          </div>
        ) : (
          <>
            {/* Fil de messages */}
            <div ref={msgRef} className="min-h-0 flex-1 overflow-y-auto px-[18px] pb-2 pt-5">
              {messages.map((m) =>
                m.kind === 'diagnosis' && m.diagnosis ? (
                  <DoctorThreadMessage
                    key={m.id}
                    appId={m.diagnosis.appId}
                    env={m.diagnosis.env}
                    appName={m.diagnosis.appName}
                    showAvatar={graphicalBotEnabled}
                    mode={mode}
                  />
                ) : m.role === 'assistant' ? (
                  <div
                    key={m.id}
                    className={cn(
                      'mb-3.5 flex items-end animate-[msgIn_.28s_ease-out_both]',
                      graphicalBotEnabled && 'gap-[9px]'
                    )}
                  >
                    {graphicalBotEnabled && <BotAvatar mode={mode} />}
                    <div className={cn(graphicalBotEnabled ? 'max-w-[76%]' : 'max-w-[88%]')}>
                      <div className="rounded-[4px_15px_15px_15px] bg-muted px-3.5 py-[11px] text-[13.5px] leading-relaxed text-foreground">
                        <SimpleMarkdown content={m.content} />
                      </div>
                      {m.citations && m.citations.length > 0 && (
                        <div className="mt-1 pl-1 text-[11px] text-muted-foreground">
                          <span className="font-medium">Sources :</span> {m.citations.join(' · ')}
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div
                    key={m.id}
                    className="mb-3.5 flex justify-end animate-[msgIn_.28s_ease-out_both]"
                  >
                    <div className="max-w-[76%] whitespace-pre-wrap rounded-[15px_4px_15px_15px] bg-primary px-3.5 py-[11px] text-[13.5px] leading-relaxed text-primary-foreground">
                      {m.content}
                    </div>
                  </div>
                )
              )}

              {chatMutation.isPending && (
                <div
                  className={cn(
                    'mb-3.5 flex items-end',
                    graphicalBotEnabled && 'gap-[9px]'
                  )}
                >
                  {graphicalBotEnabled && <BotAvatar mode={mode} />}
                  <div className="rounded-[4px_15px_15px_15px] bg-muted px-[15px] py-[13px]">
                    {/* Pas de modificateur d'opacité : les couleurs sont des var() CSS */}
                    <div className="flex gap-[5px]" aria-label="L'assistant réfléchit">
                      <TypingDots className="bg-muted-foreground" />
                    </div>
                    {pendingSince !== null && hint && (
                      <p className="mt-2 text-xs text-muted-foreground">{hint}</p>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Puces de suggestions */}
            {isDoctor ? (
              <div className="px-[18px] pb-0.5 pt-1.5">
                {doctorSuggestions.hint && (
                  <p className="mb-2 text-xs text-muted-foreground">{doctorSuggestions.hint}</p>
                )}
                <div className="flex flex-wrap gap-2">
                  {doctorSuggestions.items.map((s) =>
                    s.kind === 'diagnose' ? (
                      <button
                        key={s.label}
                        type="button"
                        onClick={() => diagnoseFromPanel(s.env)}
                        disabled={!currentApp}
                        className="inline-flex items-center gap-1.5 rounded-[20px] border border-primary-border bg-primary-subtle px-3 py-[7px] text-xs font-medium text-primary hover:border-primary disabled:opacity-50 dark:text-primary-300"
                      >
                        <IconStethoscope size={13} aria-hidden="true" />
                        {s.label}
                      </button>
                    ) : (
                      <button
                        key={s.label}
                        type="button"
                        onClick={() => ask(s.question)}
                        className={chipClass}
                      >
                        {s.label}
                      </button>
                    )
                  )}
                </div>
              </div>
            ) : (
              <div className="flex flex-wrap gap-2 px-[18px] pb-0.5 pt-1.5">
                {suggestions.map(({ label, question }) => (
                  <button key={label} onClick={() => ask(question)} className={chipClass}>
                    {label}
                  </button>
                ))}
              </div>
            )}

            {/* Barre de saisie */}
            <div className="flex-none border-t border-border px-4 pb-[18px] pt-3.5">
              <div className="flex items-center gap-[9px] rounded-[26px] border-[1.5px] border-border bg-muted py-[5px] pl-4 pr-[5px] focus-within:border-primary focus-within:ring-2 focus-within:ring-ring">
                <input
                  aria-label="Message à l’assistant"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && ask(input)}
                  placeholder="Écrivez un message…"
                  className="min-w-0 flex-1 border-none bg-transparent py-1.5 text-[13.5px] text-foreground outline-none placeholder:text-muted-foreground focus:outline-none"
                />
                <button
                  onClick={() => ask(input)}
                  disabled={!input.trim() || chatMutation.isPending}
                  aria-label="Envoyer"
                  className="flex h-10 w-10 flex-none items-center justify-center rounded-full bg-primary text-primary-foreground hover:bg-primary-hover disabled:opacity-50"
                >
                  <IconSend size={16} />
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* ===== Dock du robot (lanceur en coin → se docke dans le bandeau) ===== */}
      {graphicalBotEnabled && (
        <div ref={dockRef} className="m-dock fixed bottom-[26px] right-[30px] z-50 flex flex-col items-end gap-[11px]">
          {/* Écran étroit : la bulle masquerait la carte, et le bandeau d'erreur propose
              déjà « Diagnostiquer ». */}
          {offerDiagnosis ? (
            <button
              type="button"
              onClick={onToggle}
              className="flex items-center gap-1.5 max-sm:hidden rounded-[14px_14px_4px_14px] border border-danger-border bg-card px-3.5 py-[9px] text-xs font-medium text-foreground shadow-[0_8px_20px_rgba(31,44,84,.12)] animate-[bubblePop_.3s_cubic-bezier(.2,1.3,.5,1)_both] hover:border-primary"
            >
              <IconStethoscope size={14} aria-hidden="true" className="text-danger" />
              Besoin d'un diagnostic ?
            </button>
          ) : (
            attn &&
            !open && (
              <div className="flex items-center gap-[5px] rounded-[14px_14px_4px_14px] border border-primary-border bg-primary-50 px-3.5 py-[9px] shadow-[0_8px_20px_rgba(31,44,84,.12)] animate-[bubblePop_.3s_cubic-bezier(.2,1.3,.5,1)_both]">
                <TypingDots className="bg-primary" />
              </div>
            )
          )}

          <button
            ref={robotBtnRef}
            onClick={onToggle}
            aria-label={open ? "Fermer l'assistant" : "Ouvrir l'assistant"}
            className="relative cursor-pointer border-none bg-transparent p-0 animate-[mascotPop_.5s_cubic-bezier(.2,1.3,.5,1)_both]"
          >
            <span className="m-ring absolute inset-x-1.5 bottom-1 top-1.5 rounded-full bg-primary opacity-0" />
            <Mascot mode={mode} />
          </button>
        </div>
      )}
    </div>
  );
}
