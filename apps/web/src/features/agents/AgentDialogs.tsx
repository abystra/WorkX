import { useState } from 'react';
import { api } from '@/api/client';
import { useWs } from '@/app/workspace';
import { Avatar } from '@/ui/icons';
import { useOverlay } from '@/ui/overlay';

const TAGS = ['Personal', 'Team', 'Third-party', 'Squads'];

/** Create / edit workmate dialog (prototype createAgent). */
export function CreateAgentDialog({ editId, squad = false }: { editId?: string; squad?: boolean }) {
  const { t, ws } = useWs();
  const agent = editId ? ws.agents.find(a => a.id === editId) : undefined;
  const [avatarIndex, setAvatarIndex] = useState(agent?.avatar ?? (squad ? 5 : 0));
  return (
    <form id="agent-form" data-edit={agent?.id || ''} onSubmit={e => e.preventDefault()}>
      <div className="avatar-options">
        {[0, 1, 2, 3, 4, 5].map(i => (
          <button key={i} type="button" className={`avatar-option ${i === avatarIndex ? 'selected' : ''}`} data-action="pick-avatar" data-value={String(i)}
            aria-label={t('actions.avatar', { number: i + 1 })} aria-pressed={i === avatarIndex} onClick={() => setAvatarIndex(i)}>
            <Avatar index={i} size={42} />
          </button>
        ))}
      </div>
      <label className="form-field"><span>{t('Name')} <span className="muted">*</span></span>
        <input name="name" placeholder={t('Give your workmate a name')} defaultValue={agent?.name || ''} maxLength={40} required />
      </label>
      <label className="form-field"><span>{t('Description')}</span>
        <textarea name="description" placeholder={t('What can this workmate help you with?')} maxLength={300} defaultValue={agent?.description === 'No description yet' ? '' : agent?.description || ''} />
      </label>
      <label className="form-field"><span>{t('Type')}</span>
        <select name="tag" defaultValue={agent?.tag || (squad ? 'Squads' : 'Personal')}>
          {TAGS.map(tag => <option key={tag} value={tag}>{t(tag)}</option>)}
        </select>
      </label>
      <p className="prototype-note">{t('保存在此浏览器中，随时可以编辑。')}</p>
      <input type="hidden" name="avatar" value={avatarIndex} />
    </form>
  );
}

CreateAgentDialog.Footer = function Footer({ editId }: { editId?: string }) {
  const ctx = useWs();
  const { t } = ctx;
  const overlay = useOverlay();
  const form = () => document.getElementById('agent-form') as HTMLFormElement | null;
  const save = async () => {
    const f = form();
    if (!f || !f.reportValidity()) return;
    const values = new FormData(f);
    const name = String(values.get('name')).trim();
    const nameInput = f.elements.namedItem('name') as HTMLInputElement;
    if (!name) { nameInput.setCustomValidity(t('请输入伙伴名称')); f.reportValidity(); nameInput.setCustomValidity(''); return; }
    const changes = { name, description: String(values.get('description')).trim() || 'No description yet', tag: values.get('tag'), avatar: Number(values.get('avatar')) };
    overlay.close();
    await ctx.run(() => (editId ? api.update(ctx.tenantId, 'agents', editId, changes) : api.create(ctx.tenantId, 'agents', changes)), editId ? '伙伴信息已更新' : '已创建新的智能伙伴');
  };
  return (
    <>
      <button className="btn" data-action="close" onClick={overlay.close}>{t('Cancel')}</button>
      <button className="btn primary" data-action="save-agent" onClick={() => void save()}>{editId ? t('Save changes') : t('Create Workmate')}</button>
    </>
  );
};
