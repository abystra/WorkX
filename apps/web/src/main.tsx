// Stylesheets in the prototype's index.html order. Ported verbatim (D-04 color applied); see Part 15 §4.2.
import './styles/prototype/style.css';
import './styles/prototype/secondary.css';
import './styles/prototype/team.css';
import './styles/prototype/ecosystem.css';
import './styles/prototype/workspace.css';
import './styles/prototype/connection.css';
import './styles/prototype/channel.css';
import './styles/prototype/spaces.css';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from '@tanstack/react-router';
import { getLocale } from './i18n';
import { initTransport } from './api/client';
import { router } from './app/router';
import { OverlayProvider } from './ui/overlay';
import { ToastProvider } from './ui/toast';

async function boot() {
  const transport = await initTransport();
  if (import.meta.env.VITE_ENABLE_TEST_SEED === 'true' && window.location.pathname === '/__test__/seed') {
    const { runTestSeed } = await import('./app/test-seed-route');
    await runTestSeed(transport);
  }
  document.documentElement.lang = getLocale();
  const queryClient = new QueryClient({
    defaultOptions: { queries: { staleTime: 5_000, refetchOnWindowFocus: false, retry: transport.runtime.mode === 'http' ? 1 : 0 } },
  });
  createRoot(document.getElementById('app')!).render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <OverlayProvider>
          <RouterProvider router={router} />
        </OverlayProvider>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

void boot();
