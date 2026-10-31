import { useWs } from '@/app/workspace';
import { getLocale } from '@/i18n';
import { Icon } from '@/ui/icons';

/** Shared pieces of the prototype's secondary pages (secondary.js header/empty/date helpers). */
export function SecondaryHeader({ name, description, action, label, onAction }: { name: string; description: string; action?: string; label?: string; onAction?: () => void }) {
  const { t } = useWs();
  return (
    <header className="sw-page-heading">
      <div><h1>{t(name)}</h1><p>{t(description)}</p></div>
      {action ? <button className="sw-primary" data-action={action} onClick={onAction}><Icon name="plus" size={16} />{t(label!)}</button> : null}
    </header>
  );
}

export function SecondaryEmpty({ icon, name, description }: { icon: string; name: string; description: string }) {
  const { t } = useWs();
  return <div className="sw-empty"><span className="sw-empty-icon"><Icon name={icon} size={28} /></span><h3>{t(name)}</h3><p>{t(description)}</p></div>;
}

const RELATIVE: Record<string, string> = { Today: 'sec.today', Yesterday: 'sec.yesterday', 'Just now': 'sec.justNow', 'Just updated': 'sec.justUpdated' };
export function dateText(t: (k: string) => string, value?: string) {
  if (value && RELATIVE[value]) return t(RELATIVE[value]);
  const october = /^Oct (\d{1,2})$/.exec(String(value));
  return october && getLocale() === 'zh-CN' ? `10月${october[1]}日` : value || '';
}

const FREQUENCY: Record<string, string> = { 'Every weekday': 'sec.schedule.weekday', 'Every day': 'sec.schedule.day', 'Every Monday': 'sec.schedule.monday', 'Every Friday': 'sec.schedule.friday' };
export function scheduleText(t: (k: string, p?: Record<string, unknown>) => string, value?: string) {
  const match = /^(Every weekday|Every day|Every Monday|Every Friday) at (\d{2}:\d{2})$/.exec(String(value));
  return match ? t('sec.schedule.at', { frequency: t(FREQUENCY[match[1]]), time: match[2] }) : value || '';
}
