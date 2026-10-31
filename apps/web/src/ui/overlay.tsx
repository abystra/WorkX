import { createContext, useCallback, useContext, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useT } from '@/i18n';
import { Icon } from './icons';

type Overlay =
  | { kind: 'modal'; title: string; body: ReactNode; footer?: ReactNode; className?: string; focus?: string }
  | { kind: 'popover'; anchor: HTMLElement; content: ReactNode }
  | { kind: 'custom'; node: ReactNode; focus?: string };

interface OverlayApi {
  current: Overlay | null;
  modal: (title: string, body: ReactNode, footer?: ReactNode, options?: { className?: string; focus?: string }) => void;
  popover: (anchor: HTMLElement, content: ReactNode) => void;
  custom: (node: ReactNode, focus?: string) => void;
  close: () => void;
}

const OverlayContext = createContext<OverlayApi | null>(null);
export const useOverlay = () => useContext(OverlayContext)!;

/**
 * Overlay state (one overlay at a time, like the prototype). The visual host is <OverlayHost/>, rendered
 * inside the page layout so overlay content can read workspace context.
 */
export function OverlayProvider({ children }: { children: ReactNode }) {
  const [current, setCurrent] = useState<Overlay | null>(null);
  const previousFocus = useRef<Element | null>(null);

  const open = useCallback((overlay: Overlay, focusFrom?: Element | null) => {
    previousFocus.current = focusFrom ?? document.activeElement;
    setCurrent(overlay);
  }, []);
  const close = useCallback(() => {
    setCurrent(null);
    document.body.style.overflow = '';
    const el = previousFocus.current as HTMLElement | null;
    if (el?.isConnected) el.focus({ preventScroll: true });
  }, []);

  const value = useMemo<OverlayApi>(() => ({
    current,
    modal: (title, body, footer, options) => open({ kind: 'modal', title, body, footer, ...options }),
    popover: (anchor, content) => open({ kind: 'popover', anchor, content }, anchor),
    custom: (node, focus) => open({ kind: 'custom', node, focus }),
    close,
  }), [current, open, close]);

  return (
    <OverlayContext.Provider value={value}>
      {children}
    </OverlayContext.Provider>
  );
}

/** Renders the current overlay into #overlay-root. */
export function OverlayHost() {
  const { current, close } = useOverlay();
  return createPortal(current ? <OverlayView overlay={current} close={close} /> : null, document.getElementById('overlay-root')!);
}

function OverlayView({ overlay, close }: { overlay: Overlay; close: () => void }) {
  const t = useT();
  const popoverRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);

  useLayoutEffect(() => {
    if (overlay.kind === 'popover') {
      const p = popoverRef.current!;
      const rect = overlay.anchor.getBoundingClientRect();
      const left = Math.max(8, Math.min(rect.left, innerWidth - p.offsetWidth - 12));
      const top = rect.bottom + p.offsetHeight + 8 > innerHeight ? Math.max(8, rect.top - p.offsetHeight - 6) : rect.bottom + 6;
      setPosition({ left, top });
      p.querySelector('button')?.focus();
      return;
    }
    document.body.style.overflow = 'hidden';
    const selector = overlay.focus || '#overlay-root input, #overlay-root textarea, #overlay-root button';
    const timer = setTimeout(() => (document.querySelector(selector) as HTMLElement | null)?.focus(), overlay.focus ? 40 : 30);
    return () => clearTimeout(timer);
  }, [overlay]);

  if (overlay.kind === 'popover') {
    return (
      <>
        <div className="popover-backdrop" data-action="close" onClick={close} />
        <div className="popover" role="menu" ref={popoverRef} style={position ? { left: position.left + 'px', top: position.top + 'px' } : undefined}>
          {overlay.content}
        </div>
      </>
    );
  }
  if (overlay.kind === 'custom') return <>{overlay.node}</>;
  return (
    <div className="overlay" data-backdrop="true" onClick={e => { if (e.target === e.currentTarget) close(); }}>
      <section className={`modal ${overlay.className || ''}`} role="dialog" aria-modal="true" aria-label={overlay.title}>
        <div className="modal-header">
          <h2>{overlay.title}</h2>
          <IconButton action="close" icon="close" label={t('Close')} onClick={close} />
        </div>
        <div className="modal-body">{overlay.body}</div>
        {overlay.footer ? <div className="modal-footer">{overlay.footer}</div> : null}
      </section>
    </div>
  );
}

/** The prototype's iconButton(): icon-only button with aria-label and title. */
export function IconButton({ action, icon, label, className, onClick, size = 17, ...rest }: {
  action: string; icon: string; label: string; className?: string; size?: number;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
} & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'onClick'> & Record<`data-${string}`, string | undefined>) {
  return (
    <button className={`icon-btn${className ? ' ' + className : ''}`} data-action={action} aria-label={label} title={label} onClick={onClick} {...rest}>
      <Icon name={icon} size={size} />
    </button>
  );
}

/** The prototype's button(): text button with optional leading icon. */
export function Button({ action, label, icon, className = 'btn', onClick, ...rest }: {
  action: string; label: ReactNode; icon?: string; className?: string;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
} & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'onClick'> & Record<`data-${string}`, string | undefined>) {
  return (
    <button className={className} data-action={action} onClick={onClick} {...rest}>
      {icon ? <Icon name={icon} size={16} /> : null}
      {label}
    </button>
  );
}

/** The prototype's menuItem(). */
export function MenuItem({ action, label, icon, checked = false, onClick, children, ...rest }: {
  action: string; label?: string; icon?: string; checked?: boolean; children?: ReactNode;
  onClick?: (e: React.MouseEvent<HTMLButtonElement>) => void;
} & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'onClick'> & Record<`data-${string}`, string | undefined>) {
  return (
    <button className="menu-item" data-action={action} onClick={onClick} {...rest}>
      {children ?? (
        <>
          {icon ? <Icon name={icon} size={16} /> : null}
          <span>{label}</span>
          {checked ? <span className="menu-check"><Icon name="check" size={14} /></span> : null}
        </>
      )}
    </button>
  );
}
