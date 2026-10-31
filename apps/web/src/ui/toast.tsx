import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Icon } from './icons';

const ToastContext = createContext<(message: string) => void>(() => {});
export const useToast = () => useContext(ToastContext);

/** One toast at a time in #toast-root (role="status" aria-live="polite"), removed after 3.2 s. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ id: number; message: string } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const show = useCallback((message: string) => {
    setToast({ id: Date.now() + Math.random(), message });
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(null), 3200);
  }, []);
  useEffect(() => () => clearTimeout(timer.current), []);
  return (
    <ToastContext.Provider value={show}>
      {children}
      {createPortal(toast ? (
        <div className="toast" key={toast.id}>
          <Icon name="checkcircle" size={18} />
          <span>{toast.message}</span>
        </div>
      ) : null, document.getElementById('toast-root')!)}
    </ToastContext.Provider>
  );
}
