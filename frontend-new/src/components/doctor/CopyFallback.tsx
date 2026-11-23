import { useEffect, useId, useRef, useState } from 'react';
import { Button } from '@/components/ui/Button';
import { toast } from '@/components/ui/toast';
import { copyText } from './doctorText';

/**
 * Copie avec repli : si le navigateur refuse l'accès au presse-papiers, le texte est
 * affiché dans une zone sélectionnable au lieu d'être perdu.
 */
export function useCopyText() {
  const [fallback, setFallback] = useState<string | null>(null);

  const copy = async (text: string, success: { title: string; description?: string }) => {
    if (await copyText(text)) {
      setFallback(null);
      toast(success);
    } else {
      setFallback(text);
      toast({
        title: 'Copie automatique impossible',
        description: 'Le texte est affiché dans la carte : sélectionnez-le pour le copier.',
      });
    }
  };

  return { copy, fallback, dismiss: () => setFallback(null) };
}

export function CopyFallback({ text, onClose }: { text: string; onClose: () => void }) {
  const id = useId();
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    ref.current?.focus();
    ref.current?.select();
  }, [text]);

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs text-muted-foreground">
        Le navigateur bloque la copie automatique : sélectionnez le texte puis copiez-le (Ctrl+C).
      </label>
      <textarea
        id={id}
        ref={ref}
        readOnly
        rows={6}
        value={text}
        className="w-full resize-y rounded-md border border-border bg-background-subtle p-2 font-mono text-xs text-foreground"
      />
      <Button variant="ghost" size="sm" className="self-start" onClick={onClose}>
        Fermer
      </Button>
    </div>
  );
}
