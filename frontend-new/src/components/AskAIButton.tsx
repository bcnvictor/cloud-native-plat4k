import { useQuery } from '@tanstack/react-query';
import { IconSparkles } from '@tabler/icons-react';
import { assistantApi } from '@/api/assistant';
import { askAssistant } from '@/utils/assistantContext';
import { cn } from '@/utils/cn';

interface Props {
  /** Question envoyée telle quelle à l'assistant global. */
  question: string;
  label?: string;
  className?: string;
}

/**
 * « Expliquer avec l'IA » : ouvre l'assistant sur la question pré-remplie.
 * Masqué tant que l'assistant n'est pas activé sur la plateforme.
 */
export function AskAIButton({ question, label = 'Expliquer avec l’IA', className }: Props) {
  const { data: uiSettings } = useQuery({
    queryKey: ['ai-ui-settings'],
    queryFn: assistantApi.getUiSettings,
    retry: false,
  });
  if (!uiSettings?.assistant_enabled) return null;

  return (
    <button
      type="button"
      onClick={() => askAssistant(question)}
      className={cn(
        'inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium',
        'text-primary hover:bg-primary-50',
        className
      )}
    >
      <IconSparkles size={13} />
      {label}
    </button>
  );
}
