import { useModels } from '@/api/hooks';
import { useWs } from '@/app/workspace';
import { useDrafts, useUi } from '@/state/ui';
import { Icon } from '@/ui/icons';
import { MenuItem, useOverlay } from '@/ui/overlay';
import { useToast } from '@/ui/toast';
import { CreateProjectDialog } from '@/features/projects/ProjectDialogs';

/** Model menu. Approved deviation D-01: Claude model tiers from the control plane replace the prototype's vendor list. */
export function ModelMenu() {
  const { t, tenantId } = useWs();
  const overlay = useOverlay();
  const models = useModels();
  const drafts = useDrafts(tenantId);
  const setDrafts = useUi(s => s.setDrafts);
  return (
    <>
      <div className="menu-caption">{t('web.modelCaption')}</div>
      {(models.data || []).map(m => (
        <MenuItem key={m.id} action="choose-model" data-value={m.id} label={t(m.label)} icon="star" checked={drafts.model === m.id} onClick={() => { setDrafts(tenantId, { model: m.id }); overlay.close(); }} />
      ))}
    </>
  );
}

export function modelLabel(t: (k: string) => string, id: string, models?: { id: string; label: string }[]) {
  return t(models?.find(m => m.id === id)?.label || id);
}

export function ProjectMenu() {
  const { t, ws, tenantId } = useWs();
  const overlay = useOverlay();
  const drafts = useDrafts(tenantId);
  const setDrafts = useUi(s => s.setDrafts);
  const choose = (id: string) => { setDrafts(tenantId, { selectedProject: id }); overlay.close(); };
  return (
    <>
      <MenuItem action="choose-project" data-id="" label={t('No project')} icon="folder" checked={!drafts.selectedProject} onClick={() => choose('')} />
      {ws.projects.map(p => <MenuItem key={p.id} action="choose-project" data-id={p.id} label={p.name} icon="folder" checked={p.id === drafts.selectedProject} onClick={() => choose(p.id)} />)}
      <div className="menu-separator" />
      <MenuItem action="create-project" label={t('New project')} icon="plus" onClick={() => overlay.modal(t('New project'), <CreateProjectDialog />, <CreateProjectDialog.Footer />)} />
    </>
  );
}

export function MoreCapabilitiesMenu() {
  const { t, tenantId } = useWs();
  const overlay = useOverlay();
  const toast = useToast();
  const drafts = useDrafts(tenantId);
  const setDrafts = useUi(s => s.setDrafts);
  return (
    <>
      {['Data Visualization', 'Product Prototype', 'Office', 'Image'].map(m => (
        <MenuItem key={m} action="choose-capability" data-value={m} label={t(m)} icon="grid" checked={drafts.capabilities.includes(m)}
          onClick={() => {
            const on = !drafts.capabilities.includes(m);
            setDrafts(tenantId, { capabilities: on ? [...drafts.capabilities, m] : drafts.capabilities.filter(x => x !== m) });
            overlay.close();
            toast(t(on ? 'actions.enabled' : 'actions.disabled', { name: t(m) }));
          }} />
      ))}
    </>
  );
}

export function AttachMenu() {
  const { t, tenantId } = useWs();
  const overlay = useOverlay();
  const toast = useToast();
  const setDrafts = useUi(s => s.setDrafts);
  const upload = () => {
    overlay.close();
    const input = document.createElement('input');
    input.type = 'file';
    input.addEventListener('change', () => {
      const file = input.files?.[0];
      if (!file) return;
      // File upload to object storage is a backend capability (Part 7); the adapter records the name only.
      setDrafts(tenantId, { attachment: file.name });
      toast(t('附件已加入演示任务，仅记录文件名称'));
    });
    input.click();
  };
  return (
    <>
      <MenuItem action="upload-attachment" label={t('Upload a file')} icon="upload" onClick={upload} />
      <MenuItem action="select-library-file" label={t('Choose from Library')} icon="library" onClick={() => overlay.modal(t('Choose a file'), <ChooseFileDialog />)} />
    </>
  );
}

function ChooseFileDialog() {
  const { ws, tenantId } = useWs();
  const overlay = useOverlay();
  const setDrafts = useUi(s => s.setDrafts);
  return (
    <>
      {ws.library.map(f => (
        <button key={f.id} className="search-result" data-action="attach-library-file" data-id={f.id} onClick={() => { setDrafts(tenantId, { attachment: f.name }); overlay.close(); }}>
          <Icon name="file" size={18} /><span>{f.name}</span><Icon name="plus" size={16} />
        </button>
      ))}
    </>
  );
}

export function VoiceDialog() {
  const { t, runtime } = useWs();
  return (
    <>
      <div className="modal-illustration"><Icon name="mic" size={36} /></div>
      <p className="muted" style={{ textAlign: 'center' }}>{t('语音转写交互演示')}</p>
      <label className="form-field"><span>{t('Transcript')}</span><textarea id="voice-text" placeholder={t('在这里输入模拟转写内容…')} /></label>
      {runtime.simulated ? <p className="prototype-note">{t('此原型不会调用麦克风。输入文字后可插入任务。')}</p> : null}
    </>
  );
}

VoiceDialog.Footer = function Footer() {
  const { t, tenantId } = useWs();
  const overlay = useOverlay();
  const drafts = useDrafts(tenantId);
  const setDrafts = useUi(s => s.setDrafts);
  const use = () => {
    const el = document.getElementById('voice-text') as HTMLTextAreaElement | null;
    const value = el?.value.trim();
    if (!value) { el?.focus(); return; }
    setDrafts(tenantId, { draft: drafts.draft + (drafts.draft ? '\n' : '') + value });
    overlay.close();
  };
  return (
    <>
      <button className="btn" data-action="close" onClick={overlay.close}>{t('Cancel')}</button>
      <button className="btn primary" data-action="use-transcript" onClick={use}>{t('Insert into task')}</button>
    </>
  );
};
