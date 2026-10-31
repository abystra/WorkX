import { api } from '@/api/client';
import { useWs } from '@/app/workspace';
import { useOverlay } from '@/ui/overlay';

export function CreateAutomationDialog() {
  const { t } = useWs();
  return (
    <form id="automation-form" onSubmit={e => e.preventDefault()}>
      <label className="form-field"><span>{t('Name')} <span className="muted">*</span></span><input name="name" placeholder={t('e.g. 每周工作报告')} maxLength={60} required /></label>
      <label className="form-field"><span>{t('Task instructions')} <span className="muted">*</span></span><textarea name="description" placeholder={t('Describe what your workmate should do…')} required /></label>
      <label className="form-field"><span>{t('Schedule')}</span>
        <select name="frequency">{['Every weekday', 'Every day', 'Every Monday', 'Every Friday'].map(f => <option key={f} value={f}>{t(f)}</option>)}</select>
      </label>
      <label className="form-field"><span>{t('Time')}</span><input type="time" name="time" defaultValue="09:00" required /></label>
      {/* Scheduling is R2 (approved wording, Q-17). */}
      <p className="prototype-note">{t('原型仅演示自动化配置与状态切换，不会真正定时执行。')}</p>
    </form>
  );
}

CreateAutomationDialog.Footer = function Footer() {
  const ctx = useWs();
  const overlay = useOverlay();
  const save = async () => {
    const form = document.getElementById('automation-form') as HTMLFormElement | null;
    if (!form || !form.reportValidity()) return;
    const values = Object.fromEntries(new FormData(form).entries());
    if (!String(values.name).trim() || !String(values.description).trim()) return;
    const created = await ctx.run(() => api.create(ctx.tenantId, 'automations', values), '自动化演示已创建');
    if (created) ctx.nav('automations');
  };
  return (
    <>
      <button className="btn" data-action="close" onClick={overlay.close}>{ctx.t('Cancel')}</button>
      <button className="btn primary" data-action="save-automation" onClick={() => void save()}>{ctx.t('Create automation')}</button>
    </>
  );
};
