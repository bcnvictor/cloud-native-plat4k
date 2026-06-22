import { useState, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from '@/components/nav/Sidebar';
import { TopNav } from '@/components/nav/TopNav';
import { BreadcrumbProvider } from '@/components/nav/BreadcrumbContext';
import { Toaster } from '@/components/ui/toast';

export function RootLayout() {
  const [expanded, setExpanded] = useState(
    () => localStorage.getItem('cnp_sidebar_expanded') !== 'false'
  );

  useEffect(() => {
    localStorage.setItem('cnp_sidebar_expanded', String(expanded));
  }, [expanded]);

  return (
    <BreadcrumbProvider>
      <div className="flex h-screen-corrected overflow-hidden">
        <Sidebar expanded={expanded} onToggle={() => setExpanded((p) => !p)} />
        <div className="flex flex-col flex-1 min-w-0">
          <TopNav />
          <main className="flex-1 overflow-y-auto bg-background">
            <Outlet />
          </main>
        </div>
        <Toaster />
      </div>
    </BreadcrumbProvider>
  );
}
