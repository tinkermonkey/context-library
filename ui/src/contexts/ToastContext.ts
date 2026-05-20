import { createContext } from 'react';

export interface ToastProps {
  title: string;
  subtitle?: string;
  variant?: 'success' | 'error' | 'warning' | 'info';
  duration?: number;
}

export interface ToastContextType {
  showToast: (props: ToastProps) => void;
}

export const ToastContext = createContext<ToastContextType | undefined>(undefined);
