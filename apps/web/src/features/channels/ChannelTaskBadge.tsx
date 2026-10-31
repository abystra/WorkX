import type { Task } from '@/api/contracts';
import { useWs } from '@/app/workspace';
import { platformBy } from './platforms';

export function ChannelTaskBadge({ task }: { task: Task }) {
  const { t, ws } = useWs();
  if (task.kind !== 'channel') return null;
  const run = ws.channelRuns.find(item => item.id === task.channelRunId);
  if (!run) return null;
  return <span className="wx-channel-task-badge">{t(platformBy(run.platform)?.name || 'eco.platformPending')} · {t('channel.stage.' + run.stage)}</span>;
}
