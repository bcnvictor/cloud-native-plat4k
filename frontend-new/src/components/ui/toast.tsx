import { useState, useEffect } from 'react';
import { cn } from '@/utils/cn';

export type ToastVariant = 'default' | 'destructive';

export interface ToastOptions {
  title: string;
  description?: string;
  variant?: ToastVariant;
}

interface ToastEntry extends ToastOptions {
  id: string;
}

type Listener = (toasts: ToastEntry[]) => void;

let _toasts: ToastEntry[] = [];
const _listeners = new Set<Listener>();

function _notify() {
  _listeners.forEach((l) => l([..._toasts]));
}

export function toast(opts: ToastOptions) {
  const id = Math.random().toString(36).slice(2);
  _toasts = [..._toasts, { ...opts, id }];
  _notify();
  setTimeout(() => {
    _toasts = _toasts.filter((t) => t.id !== id);
    _notify();
  }, 4000);
}

export function useToast() {
  return { toast };
}

export function Toaster() {
  const [entries, setEntries] = useState<ToastEntry[]>(() => [..._toasts]);

  useEffect(() => {
    const listener: Listener = (t) => setEntries(t);
    _listeners.add(listener);
    return () => { _listeners.delete(listener); };
  }, []);

  if (entries.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
      {entries.map((t) => (
        <div
          key={t.id}
          className={cn(
            'px-4 py-3 rounded-lg border shadow-lg min-w-[280px] max-w-sm pointer-events-auto',
            t.variant === 'destructive'
              ? 'bg-danger text-white border-red-700'
              : 'bg-white text-foreground border-border shadow-md'
          )}
        >
          <p className="text-sm font-medium leading-snug">{t.title}</p>
          {t.description && (
            <p className={cn(
              'text-xs mt-0.5',
              t.variant === 'destructive' ? 'text-white/80' : 'text-muted-foreground'
            )}>
              {t.description}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
