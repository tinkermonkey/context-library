import type { ReactNode } from 'react';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="flex overflow-hidden" style={{ height: '100vh', background: '#0F0F0F' }}>
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto" style={{ background: '#0F0F0F' }}>
          {children}
        </main>
      </div>
    </div>
  );
}
