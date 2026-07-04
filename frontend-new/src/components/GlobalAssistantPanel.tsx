import { useState, useRef } from 'react';
import { useMutation } from '@tanstack/react-query';
import { IconX, IconSend, IconRobot } from '@tabler/icons-react';
import { assistantApi } from '@/api/assistant';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
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
  onClose: () => void;
}

export function GlobalAssistantPanel({ open, onClose }: Props) {
  const conversationId = useRef<string | undefined>(undefined);
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [input, setInput] = useState('');
  const [globallyDisabled, setGloballyDisabled] = useState(false);

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

  if (!open) return null;

  function sendMessage() {
    const msg = input.trim();
    if (!msg || chatMutation.isPending) return;
    setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'user', content: msg }]);
    setInput('');
    chatMutation.mutate(msg);
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/20" onClick={onClose} />
      <div className="relative flex flex-col bg-background border-l border-border shadow-xl w-96 h-full">
        {/* Header */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border shrink-0">
          <IconRobot size={16} className="text-primary" />
          <span className="text-sm font-medium text-foreground flex-1">AI Assistant</span>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Close"
          >
            <IconX size={16} />
          </button>
        </div>

        {globallyDisabled ? (
          <div className="flex-1 flex items-center justify-center p-6 text-center">
            <div>
              <IconRobot size={32} className="text-muted-foreground mx-auto mb-3" />
              <p className="text-sm font-medium text-foreground">AI assistant inactive</p>
              <p className="text-xs text-muted-foreground mt-1">
                The AI feature is disabled on this platform.
              </p>
            </div>
          </div>
        ) : (
          <>
            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3 min-h-0">
              {messages.length === 0 && (
                <p className="text-xs text-muted-foreground text-center mt-8">
                  Ask anything about your applications or the platform.
                </p>
              )}
              {messages.map((m) => (
                <div
                  key={m.id}
                  className={cn(
                    'flex flex-col gap-1 max-w-[85%]',
                    m.role === 'user' ? 'self-end items-end' : 'self-start items-start'
                  )}
                >
                  <div
                    className={cn(
                      'rounded-lg px-3 py-2 text-sm',
                      m.role === 'user'
                        ? 'bg-primary text-primary-foreground whitespace-pre-wrap'
                        : 'bg-muted text-foreground'
                    )}
                  >
                    {m.role === 'assistant' ? (
                      <SimpleMarkdown content={m.content} />
                    ) : (
                      m.content
                    )}
                  </div>
                  {m.citations && m.citations.length > 0 && (
                    <div className="text-[11px] text-muted-foreground pl-1">
                      <span className="font-medium">Sources :</span>{' '}
                      {m.citations.join(' · ')}
                    </div>
                  )}
                </div>
              ))}
              {chatMutation.isPending && (
                <div className="self-start bg-muted rounded-lg px-3 py-2">
                  <Spinner size="sm" />
                </div>
              )}
            </div>

            {/* Input */}
            <div className="px-4 py-3 border-t border-border flex items-center gap-2 shrink-0">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && sendMessage()}
                placeholder="Type a message…"
                className="flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              />
              <Button
                variant="primary"
                size="sm"
                onClick={sendMessage}
                disabled={!input.trim() || chatMutation.isPending}
                icon={<IconSend size={13} />}
              >
                Send
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
