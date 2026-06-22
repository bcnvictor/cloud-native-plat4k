import { createContext, useCallback, useContext, useState } from 'react';
import type { ReactNode } from 'react';

interface BreadcrumbItem {
  label: string;
  to?: string;
}

interface BreadcrumbContextValue {
  items: BreadcrumbItem[];
  setBreadcrumb: (items: BreadcrumbItem[]) => void;
}

const BreadcrumbContext = createContext<BreadcrumbContextValue>({
  items: [],
  setBreadcrumb: () => {},
});

export function BreadcrumbProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<BreadcrumbItem[]>([]);
  const setBreadcrumb = useCallback((next: BreadcrumbItem[]) => setItems(next), []);
  return (
    <BreadcrumbContext.Provider value={{ items, setBreadcrumb }}>
      {children}
    </BreadcrumbContext.Provider>
  );
}

export function useBreadcrumb() {
  return useContext(BreadcrumbContext);
}
