import { useCallback, useState } from 'react';
import type { ReactNode } from 'react';
import { Toast } from '@tinkermonkey/heimdall-ui';
import { ToastContext, type ToastProps } from '../contexts/ToastContext';

interface ToastItem extends ToastProps {
  id: string;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const showToast = useCallback((props: ToastProps) => {
    const id = Math.random().toString(36).substr(2, 9);
    const toast: ToastItem = { id, ...props };

    setToasts((prev) => [...prev, toast]);
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="fixed bottom-4 right-4 flex flex-col gap-2 pointer-events-none z-50">
        {toasts.map((toast) => (
          <div key={toast.id} className="pointer-events-auto">
            <Toast
              isOpen={true}
              onClose={() => removeToast(toast.id)}
              title={toast.title}
              subtitle={toast.subtitle}
              variant={toast.variant}
              duration={toast.duration ?? 4000}
            />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
