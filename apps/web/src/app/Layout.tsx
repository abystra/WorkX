import { useEffect, type ReactNode } from 'react';
import { useWs } from './workspace';
import { useUi } from '@/state/ui';
import { Icon } from '@/ui/icons';
import { OverlayHost, useOverlay } from '@/ui/overlay';
import { getLocale } from '@/i18n';
import { Sidebar, SpaceContext } from '@/features/shell/Sidebar';
import { SettingsSidebar } from '@/features/settings/SettingsSidebar';
import { SearchDialog } from '@/features/shell/SearchDialog';

/** Page frame (prototype render()): sidebar or settings sidebar, expand button, main with workspace bar. */
export function AppLayout({ children, title }: { children: ReactNode; title: string }) {
  const ctx = useWs();
  const { collapsed, mobileOpen, set } = useUi();
  const settingsPage = ctx.page === 'team' || ctx.page === 'settings';
  useGlobalKeys();
  useEffect(() => {
    document.title = `${title} · WorkX`;
    document.documentElement.lang = getLocale();
    document.querySelector('meta[name="description"]')?.setAttribute('content', ctx.t('ui.description'));
  }, [title, ctx]);
  return (
    <>
      <div className={`app-layout ${settingsPage ? 'ws-settings-layout' : ''} ${collapsed ? 'collapsed' : ''} ${mobileOpen ? 'mobile-open' : ''}`}>
        <div className="mobile-scrim" data-action="collapse" onClick={() => (innerWidth <= 680 ? set({ mobileOpen: false }) : set({ collapsed: true }))} />
        {settingsPage ? <SettingsSidebar /> : <Sidebar />}
        <button className="icon-btn floating-expand" data-action="expand" aria-label={ctx.t('Expand sidebar')} onClick={() => set({ collapsed: false, ...(innerWidth <= 680 ? { mobileOpen: true } : {}) })}>
          <Icon name="collapse" size={18} />
        </button>
        <main className="main" id="main-content">
          {!settingsPage ? <SpaceContext /> : null}
          {children}
        </main>
      </div>
      <OverlayHost />
    </>
  );
}

/** Keyboard behavior from the prototype: ⌘/Ctrl K, Esc, ⌘/Ctrl Enter, card activation, menu arrows, dialog focus trap. */
function useGlobalKeys() {
  const ctx = useWs();
  const overlay = useOverlay();
  const { mobileOpen, set } = useUi();
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        overlay.custom(<SearchDialog />, '#global-search');
        return;
      }
      if (event.key === 'Escape') {
        overlay.close();
        if (mobileOpen) set({ mobileOpen: false });
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key === 'Enter' && document.querySelector('#task-prompt')) {
        event.preventDefault();
        (document.querySelector('[data-action="send-task"]') as HTMLButtonElement | null)?.click();
        return;
      }
      if ((event.key === 'Enter' || event.key === ' ') && target.matches?.('.agent-card')) {
        event.preventDefault();
        ctx.nav('detail', target.dataset.id);
        return;
      }
      const menu = document.querySelector('.popover');
      if (menu && ['ArrowDown', 'ArrowUp', 'Home', 'End', 'Tab'].includes(event.key)) {
        event.preventDefault();
        const items = [...menu.querySelectorAll('button')];
        const index = items.indexOf(document.activeElement as HTMLButtonElement);
        const back = event.key === 'ArrowUp' || (event.key === 'Tab' && event.shiftKey);
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (back ? -1 : 1) + items.length) % items.length;
        items[next]?.focus();
        return;
      }
      const dialog = document.querySelector('[role="dialog"]');
      if (event.key === 'Tab' && dialog) {
        const focusables = [...dialog.querySelectorAll<HTMLElement>('button:not([disabled]),input,textarea,select,a[href]')].filter(e => e.offsetParent !== null);
        const first = focusables[0], last = focusables.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [ctx, overlay, mobileOpen, set]);
}
