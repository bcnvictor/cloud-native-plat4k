import { useState, useRef, useEffect } from 'react';
import { useMutation } from '@tanstack/react-query';
import { IconX, IconSend } from '@tabler/icons-react';
import { assistantApi } from '@/api/assistant';
import { SimpleMarkdown } from '@/components/ui/SimpleMarkdown';
import { cn } from '@/utils/cn';

interface LocalMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: string[];
}

interface Props {
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
}

const GREETING =
  "Salut 👋 Je suis l'assistant Plat4k. Pose-moi une question sur tes applications ou la plateforme.";

const SUGGESTIONS = ['État des apps', 'Voir les métriques', 'Membres du groupe'];

/** La mascotte fait signe toutes les X ms quand le tiroir est fermé. */
const ATTENTION_INTERVAL_MS = 60_000;
const ATTENTION_DURATION_MS = 3_600;

function BotAvatar() {
  return (
    <div className="flex h-[30px] w-[30px] flex-none items-center justify-center gap-1 rounded-[9px] bg-primary">
      <span className="h-[5px] w-[5px] rounded-full bg-[#8fe3ee]" />
      <span className="h-[5px] w-[5px] rounded-full bg-[#8fe3ee]" />
    </div>
  );
}

function Mascot() {
  return (
    <div className="m-robot relative h-[104px] w-[92px] drop-shadow-[0_10px_18px_rgba(31,44,84,.22)]">
      {/* Antenne */}
      <div className="absolute -top-0.5 left-1/2 h-4 w-[3px] -translate-x-1/2 rounded-sm bg-primary" />
      <div className="absolute -top-[9px] left-1/2 h-[11px] w-[11px] -translate-x-1/2 rounded-full bg-primary" />

      {/* Bras qui salue */}
      <div className="m-arm absolute -left-[9px] top-11 h-[34px] w-[15px] origin-bottom rotate-[8deg] rounded-[9px] bg-primary">
        <div className="absolute -left-1 -top-3 h-[22px] w-[22px] rounded-[50%_50%_50%_40%] bg-primary" />
      </div>

      {/* Oreilles */}
      <div className="absolute left-0.5 top-10 h-[26px] w-[11px] rounded-md bg-primary" />
      <div className="absolute right-0.5 top-10 h-[26px] w-[11px] rounded-md bg-primary" />

      {/* Corps */}
      <div className="absolute bottom-0 left-1/2 h-[38px] w-14 -translate-x-1/2 rounded-[16px_16px_12px_12px] border-2 border-border bg-card">
        <div className="absolute left-1/2 top-[9px] h-4 w-[26px] -translate-x-1/2 rounded-md bg-primary-50" />
      </div>

      {/* Tête */}
      <div className="absolute left-1/2 top-3.5 h-[60px] w-[74px] -translate-x-1/2 rounded-[26px_26px_22px_22px] border-2 border-border bg-card">
        <div className="absolute left-1/2 top-1/2 flex h-[38px] w-14 -translate-x-1/2 -translate-y-1/2 items-center justify-center gap-3 rounded-[20px] bg-[#2e3f73]">
          <div className="m-eye h-[11px] w-[11px] rounded-full bg-[#8fe3ee] shadow-[0_0_8px_rgba(143,227,238,.9)]" />
          <div className="m-eye h-[11px] w-[11px] rounded-full bg-[#8fe3ee] shadow-[0_0_8px_rgba(143,227,238,.9)] [animation-delay:.08s]" />
        </div>
      </div>
    </div>
  );
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
  const conversationId = useRef<string | undefined>(undefined);
  const msgRef = useRef<HTMLDivElement>(null);
  const talkTimeout = useRef<ReturnType<typeof setTimeout>>();
  const attnTimeout = useRef<ReturnType<typeof setTimeout>>();
  const [messages, setMessages] = useState<LocalMessage[]>([
    { id: 'greeting', role: 'assistant', content: GREETING },
  ]);
  const [input, setInput] = useState('');
  const [globallyDisabled, setGloballyDisabled] = useState(false);
  const [attn, setAttn] = useState(false);
  const [talk, setTalk] = useState(false);

  function wave(ms = 1600) {
    setTalk(true);
    clearTimeout(talkTimeout.current);
    talkTimeout.current = setTimeout(() => setTalk(false), ms);
  }

  // Signe de la main périodique quand le tiroir est fermé
  useEffect(() => {
    if (open || globallyDisabled) return;
    const interval = setInterval(() => {
      setAttn(true);
      clearTimeout(attnTimeout.current);
      attnTimeout.current = setTimeout(() => setAttn(false), ATTENTION_DURATION_MS);
    }, ATTENTION_INTERVAL_MS);
    return () => {
      clearInterval(interval);
      clearTimeout(attnTimeout.current);
    };
  }, [open, globallyDisabled]);

  useEffect(() => () => clearTimeout(talkTimeout.current), []);

  useEffect(() => {
    if (open) {
      setAttn(false);
      wave(1800);
    }
  }, [open]);

  const chatMutation = useMutation({
    mutationFn: (message: string) =>
      assistantApi.chatGlobal({ message, agent: 'platform', conversation_id: conversationId.current }),
    onSuccess: (data) => {
      conversationId.current = data.conversation_id;
      const citations = Array.from(
        new Set(
          (data.citations as { type?: string; ref?: string }[] | undefined)
            ?.filter((c) => c?.type === 'doc' && c.ref)
            .map((c) => c.ref as string) ?? []
        )
      );
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

  // Défilement auto vers le dernier message
  useEffect(() => {
    const el = msgRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, chatMutation.isPending]);

  function ask(text: string) {
    const msg = text.trim();
    if (!msg || chatMutation.isPending) return;
    setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'user', content: msg }]);
    setInput('');
    chatMutation.mutate(msg);
  }

  return (
    <div
      className={cn(
        'plat4k-assistant',
        open && 'is-open',
        ((attn && !open) || talk) && 'is-attn'
      )}
    >
      {/* ===== Tiroir de chat (glisse depuis la droite) ===== */}
      <div
        className="m-drawer fixed inset-y-0 right-0 z-40 flex w-[440px] max-w-[calc(92vw/1.25)] flex-col border-l border-border bg-background shadow-[-24px_0_60px_rgba(31,44,84,.14)]"
        aria-hidden={!open}
      >
        {/* Bandeau héro : le robot vient se docker sur la gauche */}
        <div className="relative h-[150px] flex-none border-b border-border bg-gradient-to-b from-primary-50 to-background">
          <button
            onClick={onClose}
            aria-label="Fermer"
            className="absolute right-3.5 top-3.5 flex h-[30px] w-[30px] items-center justify-center rounded-lg bg-foreground/5 text-muted-foreground hover:bg-foreground/10 hover:text-foreground"
          >
            <IconX size={16} />
          </button>
          <div className="absolute left-[150px] right-4 top-11">
            <div className="text-[17px] font-bold text-foreground">Assistant Plat4k</div>
            <div className="mt-1.5 flex items-center gap-1.5">
              <span className="h-[7px] w-[7px] rounded-full bg-success shadow-[0_0_0_3px_rgba(34,197,94,.16)]" />
              <span className="text-xs font-medium text-muted-foreground">
                En ligne · prêt à vous aider
              </span>
            </div>
          </div>
        </div>

        {globallyDisabled ? (
          <div className="flex flex-1 items-center justify-center p-6 text-center">
            <div>
              <p className="text-sm font-medium text-foreground">Assistant IA inactif</p>
              <p className="mt-1 text-xs text-muted-foreground">
                La fonctionnalité IA est désactivée sur cette plateforme.
              </p>
            </div>
          </div>
        ) : (
          <>
            {/* Fil de messages */}
            <div ref={msgRef} className="min-h-0 flex-1 overflow-y-auto px-[18px] pb-2 pt-5">
              {messages.map((m) =>
                m.role === 'assistant' ? (
                  <div
                    key={m.id}
                    className="mb-3.5 flex items-end gap-[9px] animate-[msgIn_.28s_ease-out_both]"
                  >
                    <BotAvatar />
                    <div className="max-w-[76%]">
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
                <div className="mb-3.5 flex items-end gap-[9px]">
                  <BotAvatar />
                  <div className="flex gap-[5px] rounded-[4px_15px_15px_15px] bg-muted px-[15px] py-[13px]">
                    <TypingDots className="bg-muted-foreground/60" />
                  </div>
                </div>
              )}
            </div>

            {/* Puces de suggestions */}
            <div className="flex flex-wrap gap-2 px-[18px] pb-0.5 pt-1.5">
              {SUGGESTIONS.map((label) => (
                <button
                  key={label}
                  onClick={() => ask(`${label} ?`)}
                  className="rounded-[20px] border border-border bg-card px-3 py-[7px] text-xs font-medium text-muted-foreground hover:border-primary hover:bg-primary-50 hover:text-primary"
                >
                  {label}
                </button>
              ))}
            </div>

            {/* Barre de saisie */}
            <div className="flex-none border-t border-border px-4 pb-[18px] pt-3.5">
              <div className="flex items-center gap-[9px] rounded-[26px] border-[1.5px] border-border bg-muted py-[5px] pl-4 pr-[5px]">
                <input
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
      <div className="m-dock fixed bottom-[26px] right-[30px] z-50 flex flex-col items-end gap-[11px]">
        {attn && !open && (
          <div className="flex items-center gap-[5px] rounded-[14px_14px_4px_14px] border border-primary-border bg-primary-50 px-3.5 py-[9px] shadow-[0_8px_20px_rgba(31,44,84,.12)] animate-[bubblePop_.3s_cubic-bezier(.2,1.3,.5,1)_both]">
            <TypingDots className="bg-primary" />
          </div>
        )}

        <button
          onClick={onToggle}
          aria-label={open ? "Fermer l'assistant" : "Ouvrir l'assistant"}
          className="relative cursor-pointer border-none bg-transparent p-0 animate-[mascotPop_.5s_cubic-bezier(.2,1.3,.5,1)_both]"
        >
          <span className="m-ring absolute inset-x-1.5 bottom-1 top-1.5 rounded-full bg-primary opacity-0" />
          <Mascot />
        </button>
      </div>
    </div>
  );
}
