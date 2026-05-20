import { createContext, useCallback, useContext, useState } from 'react';
import type { ReactNode } from 'react';
import { Toast, type ToastVariant } from '@tinkermonkey/heimdall-ui';

export interface ToastProps {
  title: string;
  subtitle?: string;
  variant?: ToastVariant;
  duration?: number;
}

interface ToastItem extends ToastProps {
  id: string;
}

interface ToastContextType {
  showToast: (props: ToastProps) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const showToast = useCallback((props: ToastProps) => {
    const id = Math.random().toString(36).substr(2, 9);
    const toast: ToastItem = { id, ...props };

    setToasts((prev) => [...prev, toast]);

    // Auto-remove after duration (if specified)
    const duration = props.duration ?? 4000;
    if (duration > 0) {
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, duration);
    }
  }, []);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div
        className="fixed bottom-4 right-4 flex flex-col gap-2 pointer-events-none z-50"
        style={{ pointerEvents: 'auto' }}
      >
        {toasts.map((toast) => (
          <Toast
            key={toast.id}
            isOpen={true}
            onClose={() => removeToast(toast.id)}
            title={toast.title}
            subtitle={toast.subtitle}
            variant={toast.variant}
            duration={toast.duration}
          />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextType {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within ToastProvider');
  }
  return context;
}
