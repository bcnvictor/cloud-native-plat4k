import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { IconRobot, IconSend } from '@tabler/icons-react';
import { useAppDetail } from '@/layouts/AppDetailLayout';
import { assistantApi } from '@/api/assistant';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { SimpleMarkdown } from '@/components/ui/SimpleMarkdown';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { AIContextMode } from '@/types';
import { cn } from '@/utils/cn';

interface LocalMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

function Toggle({
  value,
  onChange,
  disabled,
}: {
  value: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!value)}
      disabled={disabled}
      className={cn(
        'relative mt-0.5 h-5 w-9 shrink-0 rounded-full border-2 transition-colors',
        value ? 'bg-info border-info' : 'bg-border border-border'
      )}
    >
      <span
        className={cn(
          'absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-transform',
          value ? 'translate-x-4' : 'translate-x-0.5'
        )}
      />
    </button>
  );
}

export function AssistantTab() {
  const { app, isLoading: appLoading } = useAppDetail();
  const qc = useQueryClient();
  const conversationId = useRef<string | undefined>(undefined);
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [input, setInput] = useState('');
  const [warnOpen, setWarnOpen] = useState(false);

  const {
    data: aiSettings,
    isLoading: settingsLoading,
    error: settingsError,
  } = useQuery({
    queryKey: ['ai-settings', app?.id],
    queryFn: () => assistantApi.getAppSettings(app!.id),
    enabled: !!app?.id,
    retry: false,
  });

  const patchMutation = useMutation({
    mutationFn: (patch: Parameters<typeof assistantApi.patchAppSettings>[1]) =>
      assistantApi.patchAppSettings(app!.id, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ai-settings', app?.id] }),
  });

  const chatMutation = useMutation({
    mutationFn: (message: string) =>
      assistantApi.chatWithApp(app!.id, {
        message,
        conversation_id: conversationId.current,
        requested_context_mode: aiSettings?.ai_context_mode ?? 'metadata_only',
      }),
    onSuccess: (data) => {
      conversationId.current = data.conversation_id;
      setMessages((prev) => [
        ...prev,
        { id: data.conversation_id + Date.now(), role: 'assistant', content: data.answer },
      ]);
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      const content =
        typeof detail === 'string'
          ? detail
          : "Une erreur est survenue lors de la requête à l'assistant. Réessayez.";
      setMessages((prev) => [
        ...prev,
        { id: 'err' + Date.now(), role: 'assistant', content: `⚠️ ${content}` },
      ]);
    },
  });

  if (appLoading || !app) return null;

  // Global AI feature disabled (503)
  const isGloballyDisabled =
    settingsError != null &&
    (settingsError as { response?: { status?: number } }).response?.status === 503;

  if (isGloballyDisabled) {
    return (
      <div className="max-w-2xl">
        <Card>
          <div className="flex items-start gap-3">
            <IconRobot size={20} className="text-muted-foreground mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-foreground">AI assistant inactive</p>
              <p className="text-xs text-muted-foreground mt-1">
                The AI feature is disabled on this platform (
                <code className="font-mono">AI_ASSISTANT_ENABLED=false</code>).
                Contact your administrator to enable it.
              </p>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  if (settingsLoading) return <Spinner size="md" />;

  const enabled = aiSettings?.ai_enabled ?? false;
  const contextMode: AIContextMode = aiSettings?.ai_context_mode ?? 'metadata_only';
  const scanEnabled = aiSettings?.ai_security_scan_enabled ?? false;
  const summaryEnabled = aiSettings?.ai_security_summary_enabled ?? false;

  function sendMessage() {
    const msg = input.trim();
    if (!msg || chatMutation.isPending) return;
    setMessages((prev) => [...prev, { id: Date.now().toString(), role: 'user', content: msg }]);
    setInput('');
    chatMutation.mutate(msg);
  }

  function handleCodeModeToggle() {
    if (contextMode === 'metadata_and_code') {
      patchMutation.mutate({ ai_context_mode: 'metadata_only' });
    } else {
      setWarnOpen(true);
    }
  }

  return (
    <div className="flex flex-col gap-5 max-w-2xl">
      {/* Settings */}
      <Card>
        <h2 className="text-sm font-medium text-foreground mb-4">AI Assistant settings</h2>
        <div className="flex flex-col gap-4">
          <div className="flex items-start gap-3">
            <Toggle
              value={enabled}
              onChange={(v) => patchMutation.mutate({ ai_enabled: v })}
              disabled={patchMutation.isPending}
            />
            <div>
              <p className="text-sm font-medium text-foreground">
                {enabled ? 'Assistant enabled' : 'Assistant disabled'}
              </p>
              <p className="text-xs text-muted-foreground">
                Allow team members to chat with the AI about this application.
              </p>
            </div>
          </div>

          {enabled && (
            <>
              <div className="h-px bg-border" />

              <div className="flex items-start gap-3">
                <Toggle
                  value={contextMode === 'metadata_and_code'}
                  onChange={handleCodeModeToggle}
                  disabled={patchMutation.isPending}
                />
                <div>
                  <p className="text-sm font-medium text-foreground">Code access</p>
                  <p className="text-xs text-muted-foreground">
                    Include source code excerpts in AI context (metadata only by default).
                  </p>
                  {contextMode === 'metadata_and_code' && (
                    <p className="text-xs text-[#d97706] mt-1">
                      Active — code excerpts may be sent to the AI provider.
                    </p>
                  )}
                </div>
              </div>

              <div className="h-px bg-border" />

              <div className="flex items-start gap-3">
                <Toggle
                  value={scanEnabled}
                  onChange={(v) => patchMutation.mutate({ ai_security_scan_enabled: v })}
                  disabled={patchMutation.isPending}
                />
                <div>
                  <p className="text-sm font-medium text-foreground">Security scan</p>
                  <p className="text-xs text-muted-foreground">
                    Enable automated security scans (gitleaks, semgrep, trivy…).
                  </p>
                </div>
              </div>

              {scanEnabled && (
                <div className="flex items-start gap-3 pl-12">
                  <Toggle
                    value={summaryEnabled}
                    onChange={(v) => patchMutation.mutate({ ai_security_summary_enabled: v })}
                    disabled={patchMutation.isPending}
                  />
                  <div>
                    <p className="text-sm font-medium text-foreground">AI scan summary</p>
                    <p className="text-xs text-muted-foreground">
                      Use AI to summarize scan findings (requires AI provider call).
                    </p>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </Card>

      {/* Chat */}
      {enabled ? (
        <div className="bg-background border border-border rounded-lg shadow-sm flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-border shrink-0">
            <p className="text-sm font-medium text-foreground flex items-center gap-2">
              <IconRobot size={15} className="text-primary" />
              Chat — {app.name}
            </p>
          </div>
          <div className="h-80 overflow-y-auto p-4 flex flex-col gap-3">
            {messages.length === 0 && (
              <p className="text-xs text-muted-foreground text-center mt-6">
                Ask anything about this application.
              </p>
            )}
            {messages.map((m) => (
              <div
                key={m.id}
                className={cn(
                  'max-w-[85%] rounded-lg px-3 py-2 text-sm',
                  m.role === 'user'
                    ? 'self-end bg-primary text-primary-foreground whitespace-pre-wrap'
                    : 'self-start bg-muted text-foreground'
                )}
              >
                {m.role === 'assistant' ? <SimpleMarkdown content={m.content} /> : m.content}
              </div>
            ))}
            {chatMutation.isPending && (
              <div className="self-start bg-muted rounded-lg px-3 py-2">
                <Spinner size="sm" />
              </div>
            )}
          </div>
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
        </div>
      ) : (
        <Card>
          <div className="flex items-start gap-3">
            <IconRobot size={20} className="text-muted-foreground mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-foreground">Assistant not enabled</p>
              <p className="text-xs text-muted-foreground mt-1">
                Enable the assistant above to start chatting about this application.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Code access warning dialog */}
      <ConfirmDialog
        open={warnOpen}
        title="Activate code access"
        description="You are authorizing the AI assistant to include source code excerpts from this repository in its context. Secrets, tokens, kubeconfigs, .env files, and masked values are excluded, but code and file names may be sensitive for the organization. Verify that the AI provider, its jurisdiction, and data-processing terms are acceptable before enabling this option."
        confirmLabel="I accept"
        variant="primary"
        onCancel={() => setWarnOpen(false)}
        onConfirm={() => {
          setWarnOpen(false);
          patchMutation.mutate({
            ai_context_mode: 'metadata_and_code',
            accept_code_access_warning: true,
          });
        }}
        loading={patchMutation.isPending}
      />
    </div>
  );
}
