import type { WorkspaceCtx } from '@/app/workspace';
import { displayText, useT } from '@/i18n';
import { Icon } from '@/ui/icons';
import { useOverlay } from '@/ui/overlay';
import { useToast } from '@/ui/toast';
import { useWs } from '@/app/workspace';

/** Opens the artifact preview dialog (prototype showFile). */
export function showFile(ctx: WorkspaceCtx, overlay: ReturnType<typeof useOverlay>, id: string) {
  const file = ctx.ws.library.find(f => f.id === id) || ctx.ws.library[0];
  if (!file) return;
  overlay.modal(file.name, <FilePreview id={file.id} />, <FileFooter id={file.id} />);
}

function FilePreview({ id }: { id: string }) {
  const t = useT();
  const { ws, runtime } = useWs();
  const file = ws.library.find(f => f.id === id)!;
  const kind = { doc: t('Document'), slides: t('Presentation preview'), sheet: t('Spreadsheet preview') }[file.type];
  return (
    <>
      <div className="row" style={{ marginBottom: 17, color: '#6b7079', fontSize: 12 }}>
        <Icon name="file" size={15} />{kind} · {displayText(t, file.updated)}
        {runtime.simulated ? <span className="demo-badge">{t('Demo content')}</span> : null}
      </div>
      <div className="file-preview"><h2>{file.name}</h2>{file.content || t('actions.defaultDocument')}</div>
    </>
  );
}

function FileFooter({ id }: { id: string }) {
  const { ws, t } = useWs();
  const toast = useToast();
  const overlay = useOverlay();
  const download = () => {
    const file = ws.library.find(f => f.id === id);
    if (!file) return;
    const content = `# ${file.name}\n\n${file.content || t('actions.downloadDefault')}\n\n---\n${t('actions.downloadFooter')}`;
    const url = URL.createObjectURL(new Blob([content], { type: 'text/markdown;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = file.name + '.md';
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast(t('文档已下载'));
  };
  return (
    <>
      <button className="btn" data-action="close" onClick={overlay.close}>{t('Close')}</button>
      <button className="btn primary" data-action="download-file" data-id={id} onClick={download}><Icon name="download" size={16} />{t('Download .md')}</button>
    </>
  );
}
