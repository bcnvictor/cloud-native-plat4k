import { Outlet } from 'react-router-dom';
import { TopNav } from '@/components/nav/TopNav';

export function RootLayout() {
  return (
    <>
      <TopNav />
      <main className="pt-topnav min-h-screen max-w-[1440px] mx-auto px-8">
        <Outlet />
      </main>
    </>
  );
}
