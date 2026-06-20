import { Outlet } from 'react-router-dom';
import { TopNav } from '@/components/nav/TopNav';
import { Toaster } from '@/components/ui/toast';

export function RootLayout() {
  return (
    <>
      <TopNav />
      <main className="pt-topnav min-h-screen">
        <Outlet />
      </main>
      <Toaster />
    </>
  );
}
