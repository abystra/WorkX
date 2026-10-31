import { useT } from '@/i18n';
import { Icon } from '@/ui/icons';

/** New state (Part 15 §4.3): uses the prototype's empty-state pattern. */
export function LoadError({ onRetry }: { onRetry: () => void }) {
  const t = useT();
  return (
    <main className="main" id="main-content" style={{ marginLeft: 0 }}>
      <div className="empty-state">
        <Icon name="help" size={25} />
        <h3>{t('web.loadErrorTitle')}</h3>
        <p>{t('web.loadErrorBody')}</p>
        <button className="btn primary" data-action="retry" onClick={onRetry}>{t('web.retry')}</button>
      </div>
    </main>
  );
}

export function NotFound({ onHome }: { onHome: () => void }) {
  const t = useT();
  return (
    <div className="empty-state">
      <Icon name="search" size={25} />
      <h3>{t('web.notFoundTitle')}</h3>
      <p>{t('web.notFoundBody')}</p>
      <button className="btn" data-action="nav" data-page="home" onClick={onHome}>{t('web.backHome')}</button>
    </div>
  );
}

/** The prototype's empty(): search icon, title, description. */
export function Empty({ title, description }: { title: string; description: string }) {
  return (
    <div className="empty-state">
      <Icon name="search" size={25} />
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}
