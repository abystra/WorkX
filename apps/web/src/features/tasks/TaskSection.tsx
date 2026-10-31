import type { Task } from '@/api/contracts';
import { useWs } from '@/app/workspace';
import { Empty } from '@/app/states';
import { formatRelative, formatSchedule } from '@/i18n';
import { useUi } from '@/state/ui';
import { Avatar, Icon } from '@/ui/icons';
import { IconButton, useOverlay } from '@/ui/overlay';
import { FilterMenu, TaskMenu } from '@/features/shell/menus';
import { ChannelTaskBadge } from '@/features/channels/ChannelTaskBadge';
import { showFile } from '@/features/library/FileDialog';

/** Recent activity list on Home and New Task (prototype taskSection + taskRows). */
export function TaskSection() {
  const ctx = useWs();
  const { t, page } = ctx;
  const overlay = useOverlay();
  const { listTab, filter, query, set } = useUi();
  const tabs = ['tasks', 'automations', ...(page === 'new' ? ['artifacts'] : [])];
  return (
    <section className="task-section">
      <div className="list-toolbar">
        <div className="tabs" role="tablist" aria-label={t('Recent activity')}>
          {tabs.map(tab => (
            <button key={tab} className={`tab-btn ${listTab === tab ? 'active' : ''}`} role="tab" aria-selected={listTab === tab} data-action="list-tab" data-tab={tab} onClick={() => set({ listTab: tab, query: '' })}>
              {t(tab[0].toUpperCase() + tab.slice(1))}
            </button>
          ))}
        </div>
        <div className="list-tools">
          <IconButton action="filter" icon="filter" label={t('Filter tasks')} className={`filter-btn ${filter !== 'all' ? 'selected' : ''}`} onClick={e => overlay.popover(e.currentTarget, <FilterMenu />)} />
          <label className="search-field">
            <Icon name="search" size={16} />
            <input data-task-search="" value={query} placeholder={t('Search')} aria-label={t('Search tasks')} onChange={e => set({ query: e.target.value })} />
          </label>
        </div>
      </div>
      <div id="task-results"><TaskRows /></div>
    </section>
  );
}

function TaskRows() {
  const ctx = useWs();
  const { t, ws, page } = ctx;
  const overlay = useOverlay();
  const { listTab, filter, query } = useUi();
  const q = query.toLowerCase();
  if (listTab === 'automations') {
    const items = ws.automations.filter(a => a.name.toLowerCase().includes(q));
    return items.length ? <>{items.map(a => (
      <div className="task-row" key={a.id}>
        <button className="task-open" data-action="nav" data-page="automations" onClick={() => ctx.nav('automations')}><Icon name="clock" size={20} /><span>{a.name}</span></button>
        <span className="task-date">{t(a.enabled ? 'Active' : 'Paused')} · {formatSchedule(t, a.schedule)}</span>
      </div>
    ))}</> : <Empty title={t('No automations found')} description={t('试试其他关键词')} />;
  }
  if (listTab === 'artifacts') {
    const items = ws.library.filter(f => f.name.toLowerCase().includes(q));
    return items.length ? <>{items.map(f => (
      <div className="task-row" key={f.id}>
        <button className="task-open" data-action="open-file" data-id={f.id} onClick={() => showFile(ctx, overlay, f.id)}><Icon name="file" size={20} />{f.name}</button>
        <span className="task-date">{formatRelative(t, f.updated)}</span>
      </div>
    ))}</> : <Empty title={t('No files found')} description={t('试试其他关键词')} />;
  }
  const matches = (task: Task) =>
    (filter === 'archived' ? task.archived : !task.archived) && task.name.toLowerCase().includes(q) &&
    (filter === 'all' || filter === 'archived' || (filter === 'unread' && task.unread) || (filter === 'pinned' && task.pinned) || (filter === 'done' && task.status === 'done'));
  const tasks = ws.tasks.filter(matches).sort((a, b) => Number(!!b.pinned) - Number(!!a.pinned));
  if (!tasks.length) return <Empty title={t('No tasks found')} description={t('试试其他关键词，或创建一个新任务。')} />;
  const agentBy = (id: string) => ws.agents.find(a => a.id === id) || ws.agents[0];
  return (
    <>
      {tasks.map(task => (
        <div className="task-row" key={task.id}>
          <button className="task-open" data-action="open-task" data-id={task.id} onClick={() => ctx.nav('task', task.id)}>
            {page === 'home' ? <Avatar index={agentBy(task.agent).avatar} size={24} /> : null}
            <span className="ellipsis">{task.name}{task.unread ? <span className="dot" /> : null}</span>
          </button>
          {task.kind === 'channel' ? <ChannelTaskBadge task={task} /> : null}
          <span className="task-date">{task.date}</span>
          <button className="icon-btn task-more" aria-label={t('ui.moreTask', { name: task.name })} data-action="task-menu" data-id={task.id} onClick={e => overlay.popover(e.currentTarget, <TaskMenu taskId={task.id} />)}>
            <Icon name="more" size={17} />
          </button>
        </div>
      ))}
    </>
  );
}
