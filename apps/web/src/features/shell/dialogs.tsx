import { useEffect } from 'react';
import { api } from '@/api/client';
import { useWs } from '@/app/workspace';
import { Icon, logoHtml } from '@/ui/icons';
import { IconButton, useOverlay } from '@/ui/overlay';

export function ShortcutsDialog() {
  const { t } = useWs();
  return (
    <>
      <div className="proactive-row"><span className="grow">{t('Search everything')}</span><span className="kbd">⌘ / Ctrl K</span></div>
      <div className="proactive-row"><span className="grow">{t('Send task')}</span><span className="kbd">⌘ / Ctrl Enter</span></div>
      <div className="proactive-row"><span className="grow">{t('Close dialog')}</span><span className="kbd">Esc</span></div>
    </>
  );
}

export function HelpDialog() {
  const { t } = useWs();
  const steps = [['选择一位伙伴', '从工作台选择适合你的智能伙伴，也可以创建自己的伙伴。'], ['开始一个任务', '输入目标，选择项目与能力，然后点击发送。'], ['让成果持续积累', '在 Library 查看交付文件，在 Automations 体验周期任务。']];
  return (
    <div className="help-steps">
      {steps.map(([title, desc], i) => (
        <div className="help-step" key={title}><span className="step-number">{i + 1}</span><div><strong>{t(title)}</strong><p>{t(desc)}</p></div></div>
      ))}
    </div>
  );
}

export function AboutDialog() {
  const { t } = useWs();
  return (
    <>
      <div className="modal-illustration" dangerouslySetInnerHTML={logoHtml} />
      <p>{t('workspace.about')}</p>
      <p className="muted">{t('支持智能伙伴管理、任务对话、全局搜索、项目空间、文件预览与自动化配置。')}</p>
      <p className="prototype-note">{t('使用通用演示数据；全部操作保存在当前浏览器，不连接真实飞书服务或 AI 模型。此为独立设计原型。')}</p>
    </>
  );
}

export function ProactiveDialog() {
  const ctx = useWs();
  const { t, ws } = ctx;
  const on = ws.tenant.settings.proactive;
  return (
    <>
      <div className="row" style={{ marginBottom: 18 }}>
        <Icon name="moon" size={24} />
        <div><strong>{t('A little help, at the right time.')}</strong><p className="muted" style={{ fontSize: 12, margin: '4px 0' }}>{t('让智能伙伴主动关注你的工作。')}</p></div>
      </div>
      <div className="proactive-row">
        <div className="grow">{t('Proactive suggestions')}<p>{t('在工作台中展示个性化任务建议。')}</p></div>
        <button className={`toggle ${on ? 'enabled' : ''}`} role="switch" aria-checked={!!on} aria-label={t('Enable proactive suggestions')} data-action="toggle-proactive"
          onClick={() => void ctx.run(() => api.updateTenant(ctx.tenantId, { proactive: !on }))} />
      </div>
      {ctx.runtime.simulated ? <p className="prototype-note">{t('此设置只影响原型中的演示状态。')}</p> : null}
    </>
  );
}

export function ProactiveFooter() {
  const { t } = useWs();
  const overlay = useOverlay();
  return <button className="btn primary" data-action="close" onClick={overlay.close}>{t('Done')}</button>;
}

/** Prototype notifications(): marks notifications read, then shows the drawer. */
export function NotificationsDrawer() {
  const ctx = useWs();
  const { t, ws } = ctx;
  const overlay = useOverlay();
  useEffect(() => {
    if (!ws.tenant.settings.notificationsRead) void ctx.run(() => api.updateTenant(ctx.tenantId, { notificationsRead: true }));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const completed = ws.tasks.find(task => task.status === 'done' && task.unread) || ws.tasks.find(task => task.status === 'done');
  return (
    <div className="overlay drawer-overlay" data-backdrop="true" onClick={e => { if (e.target === e.currentTarget) overlay.close(); }}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={t('Notifications')}>
        <div className="modal-header"><h2>{t('Notifications')}</h2><IconButton action="close" icon="close" label={t('Close notifications')} onClick={overlay.close} /></div>
        <div className="modal-body">
          <p className="muted" style={{ fontSize: 12 }}>{ctx.spaceName()} · {t('spaces.contextHint')}</p>
          {completed ? (
            <button className="notice-item" data-action="open-task" data-id={completed.id} style={{ textAlign: 'left', width: '100%' }} onClick={() => ctx.nav('task', completed.id)}>
              <span className="notification-icon"><Icon name="checkcircle" size={20} /></span>
              <span><strong>{t('你的智能伙伴已完成任务')}</strong><p>{t('actions.notificationComplete', { name: completed.name })}</p></span>
            </button>
          ) : null}
          <div className="notice-item">
            <span className="notification-icon" style={{ color: '#6c82c9', background: '#f0f3fc' }}><Icon name="users" size={20} /></span>
            <div><strong>{t('欢迎来到你的 WorkX 工作台')}</strong><p>{t('选择一个智能伙伴，开始你的第一个任务。')}</p><small>{t('Getting started')}</small></div>
          </div>
        </div>
      </aside>
    </div>
  );
}
