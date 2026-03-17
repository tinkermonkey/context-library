import type { ReactNode } from 'react';
import { AppNavbar } from './AppNavbar';

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <AppNavbar />
      <main className="container mx-auto px-4 py-6">{children}</main>
    </div>
  );
}
