import { useState, useEffect, useRef } from 'react';
import { Outlet, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
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

  // Group-scoped queries are keyed by groupId so a switch always fetches
  // fresh data — this only forces it immediately instead of waiting on
  // staleTime for a group revisited within the same session.
  const { slug } = useParams<{ slug?: string }>();
  const queryClient = useQueryClient();
  const previousSlug = useRef(slug);
  useEffect(() => {
    if (slug && slug !== previousSlug.current) {
      queryClient.invalidateQueries();
    }
    previousSlug.current = slug;
  }, [slug, queryClient]);

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
