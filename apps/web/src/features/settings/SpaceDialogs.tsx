import { api } from '@/api/client';
import { useWs } from '@/app/workspace';
import { SpaceMark } from '@/features/shell/menus';
import { useOverlay } from '@/ui/overlay';
import { useToast } from '@/ui/toast';

/** Form helpers from the prototype's spaces.js: label.form-field > span + control. */
export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="form-field"><span>{label}</span>{children}</label>;
}

export function SpaceButton({ action, label, primary = false, onClick, ...rest }: { action: string; label: string; primary?: boolean; onClick?: () => void } & Record<`data-${string}`, string>) {
  return <button type="button" className={`btn${primary ? ' primary' : ''}`} data-action={action} onClick={onClick} {...rest}>{label}</button>;
}

/** Reads a dialog form the way the prototype's formFor() does (tenant check + native validation). */
export function readForm(id: string, tenantId: string): FormData | null {
  const form = document.getElementById(id) as HTMLFormElement | null;
  return form && (!form.dataset.tenant || form.dataset.tenant === tenantId) && form.reportValidity() ? new FormData(form) : null;
}

export function CreateOrganizationDialog() {
  const { t } = useWs();
  return (
    <>
      <p className="ws-body-copy">{t('spaces.createHint')}</p>
      <form id="space-create-form" onSubmit={e => e.preventDefault()}>
        <Field label={t('spaces.orgName')}><input name="name" maxLength={80} required placeholder={t('spaces.orgPlaceholder')} autoComplete="organization" /></Field>
      </form>
    </>
  );
}

CreateOrganizationDialog.Footer = function Footer() {
  const ctx = useWs();
  const overlay = useOverlay();
  const toast = useToast();
  const save = async () => {
    const values = readForm('space-create-form', ctx.tenantId);
    if (!values) return;
    try {
      const space = await api.createTenant(String(values.get('name') || ''));
      await ctx.refresh();
      ctx.switchWorkspace(space.id, { page: 'team', tab: 'general', notice: 'spaces.created', space });
    } catch (e) {
      toast(ctx.t((e as { code?: string }).code || 'web.requestFailed'));
    }
  };
  return (
    <>
      <SpaceButton action="close" label={ctx.t('team.cancel')} onClick={overlay.close} />
      <SpaceButton action="space-save-organization" label={ctx.t('spaces.create')} primary onClick={() => void save()} />
    </>
  );
};

export function InviteDialog() {
  const ctx = useWs();
  const { t } = ctx;
  return (
    <>
      <p className="ws-body-copy">{t('spaces.inviteHint')}</p>
      <div className="ws-dialog-space"><SpaceMark space={ctx.current} /><strong>{ctx.spaceName()}</strong></div>
      <form id="space-invite-form" data-tenant={ctx.tenantId} onSubmit={e => e.preventDefault()}>
        <Field label={t('spaces.emails')}><textarea name="emails" rows={3} maxLength={5000} required placeholder={t('spaces.emailsPlaceholder')} /></Field>
        <Field label={t('team.role')}>
          <select name="role"><option value="member">{t('team.role.member')}</option><option value="admin">{t('team.role.admin')}</option></select>
        </Field>
      </form>
    </>
  );
}

InviteDialog.Footer = function Footer() {
  const ctx = useWs();
  const overlay = useOverlay();
  const save = async () => {
    const values = readForm('space-invite-form', ctx.tenantId);
    if (!values) return;
    const result = await ctx.run(() => api.invite(ctx.tenantId, String(values.get('emails') || ''), String(values.get('role'))), 'spaces.invited');
    if (result) { overlay.close(); ctx.nav('team', 'members'); }
  };
  return (
    <>
      <SpaceButton action="close" label={ctx.t('team.cancel')} onClick={overlay.close} />
      <SpaceButton action="space-save-invite" label={ctx.t('spaces.createInvitations')} primary onClick={() => void save()} />
    </>
  );
};
