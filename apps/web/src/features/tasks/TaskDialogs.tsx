import { api } from '@/api/client';
import type { Task } from '@/api/contracts';
import { useWs } from '@/app/workspace';
import { useOverlay } from '@/ui/overlay';

export function RenameTaskDialog({ task }: { task: Task }) {
  const { t } = useWs();
  return (
    <form id="rename-form" onSubmit={e => e.preventDefault()}>
      <label className="form-field"><span>{t('Task name')}</span><input name="name" defaultValue={task.name} required maxLength={100} /></label>
    </form>
  );
}

RenameTaskDialog.Footer = function Footer({ taskId }: { taskId: string }) {
  const ctx = useWs();
  const overlay = useOverlay();
  const save = async () => {
    const form = document.getElementById('rename-form') as HTMLFormElement | null;
    if (!form || !form.reportValidity()) return;
    const name = (form.elements.namedItem('name') as HTMLInputElement).value.trim();
    if (!name) return;
    overlay.close();
    await ctx.run(() => api.update(ctx.tenantId, 'tasks', taskId, { name }), '任务名称已更新');
  };
  return (
    <>
      <button className="btn" data-action="close" onClick={overlay.close}>{ctx.t('Cancel')}</button>
      <button className="btn primary" data-action="save-task-name" data-id={taskId} onClick={() => void save()}>{ctx.t('Save')}</button>
    </>
  );
};
