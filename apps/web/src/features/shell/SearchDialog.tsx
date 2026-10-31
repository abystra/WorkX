import { Fragment, useState } from 'react';
import { useWs } from '@/app/workspace';
import { Empty } from '@/app/states';
import { Avatar, Icon } from '@/ui/icons';
import { useOverlay } from '@/ui/overlay';

/** Global search (⌘/Ctrl K): workmates, tasks, projects of the current workspace. */
export function SearchDialog() {
  const ctx = useWs();
  const { t, ws } = ctx;
  const overlay = useOverlay();
  const [query, setQuery] = useState('');
  const q = query.trim().toLowerCase();
  const groups = [
    { label: t('Workmates'), items: ws.agents.filter(a => (a.name + ' ' + a.description).toLowerCase().includes(q)).slice(0, 4).map(a => (
      <button key={a.id} className="search-result" data-action="agent-detail" data-id={a.id} onClick={() => ctx.nav('detail', a.id)}><Avatar index={a.avatar} size={26} /><span>{a.name}</span><Icon name="chevron" size={13} /></button>
    )) },
    { label: t('Tasks'), items: ws.tasks.filter(x => !x.archived && x.name.toLowerCase().includes(q)).slice(0, 6).map(x => (
      <button key={x.id} className="search-result" data-action="open-task" data-id={x.id} onClick={() => ctx.nav('task', x.id)}><Icon name="chat" size={19} /><span>{x.name}</span><Icon name="chevron" size={13} /></button>
    )) },
    { label: t('Projects'), items: ws.projects.filter(p => p.name.toLowerCase().includes(q)).slice(0, 3).map(p => (
      <button key={p.id} className="search-result" data-action="open-project" data-id={p.id} onClick={() => ctx.nav('project', p.id)}><Icon name="folder" size={19} /><span>{p.name}</span><Icon name="chevron" size={13} /></button>
    )) },
  ].filter(g => g.items.length);
  return (
    <div className="overlay" data-backdrop="true" onClick={e => { if (e.target === e.currentTarget) overlay.close(); }}>
      <section className="modal search-modal" role="dialog" aria-modal="true" aria-label={t('Search everything')}>
        <div className="global-search-box">
          <Icon name="search" size={22} />
          <input id="global-search" placeholder={t('Search tasks, workmates, and projects…')} aria-label={t('Search everything')} value={query} autoComplete="off" onChange={e => setQuery(e.target.value)} />
          <button className="kbd" data-action="close" onClick={overlay.close}>Esc</button>
        </div>
        <div id="global-results" className="search-results">
          {groups.length ? groups.map(g => (
            <Fragment key={g.label}><div className="search-caption">{g.label}</div>{g.items}</Fragment>
          )) : <Empty title={t('No results found')} description={t('换一个关键词试试')} />}
        </div>
        <div className="modal-footer" style={{ justifyContent: 'space-between', fontSize: 11, color: '#9ca1a8', padding: '10px 20px' }}>
          <span>{t('Find something to pick up where you left off')}</span><span>⌘ K</span>
        </div>
      </section>
    </div>
  );
}
