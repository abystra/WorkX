import { createRootRoute, createRoute, createRouter, Navigate, Outlet, useParams } from '@tanstack/react-router';
import { useMe, useTenants } from '@/api/hooks';
import { AppLayout } from './Layout';
import { PAGES, WorkspaceProvider, useWs, type Page } from './workspace';
import { NotFound } from './states';
import { pageTitle, PageSwitch } from './pages';
import { InvitePage, LoginPage, SessionExpiredPage, SignupPage } from '@/features/auth/AuthPages';

const rootRoute = createRootRoute({ component: () => <Outlet /> });

function RootRedirect() {
  const me = useMe();
  const tenants = useTenants();
  if (!me.data || !tenants.data) return null;
  // A first sign-in has no remembered workspace yet: open the personal one (listed first).
  const known = tenants.data.some(t => t.id === me.data.lastTenantId);
  const target = known ? me.data.lastTenantId : tenants.data[0]?.id;
  return target ? <Navigate to={`/t/${target}/home`} replace /> : null;
}

function TenantPage() {
  const params = useParams({ strict: false }) as { tenantId?: string; page?: string; id?: string };
  const page = (PAGES as string[]).includes(params.page || '') && params.page !== 'settings' ? (params.page as Page) : 'home';
  return (
    <WorkspaceProvider key={params.tenantId} tenantId={params.tenantId} page={page} routeId={params.id}>
      <Frame />
    </WorkspaceProvider>
  );
}

function SettingsPage() {
  const params = useParams({ strict: false }) as { tab?: string };
  return (
    <WorkspaceProvider page="settings" routeId={params.tab || 'general'}>
      <Frame />
    </WorkspaceProvider>
  );
}

function Frame() {
  const ctx = useWs();
  return <AppLayout title={pageTitle(ctx)}><PageSwitch /></AppLayout>;
}

const indexRoute = createRoute({ getParentRoute: () => rootRoute, path: '/', component: RootRedirect });
const settingsIndexRoute = createRoute({ getParentRoute: () => rootRoute, path: '/settings', component: () => <Navigate to="/settings/general" replace /> });
const settingsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/settings/$tab', component: SettingsPage });
const tenantIndexRoute = createRoute({ getParentRoute: () => rootRoute, path: '/t/$tenantId', component: () => {
  const { tenantId } = useParams({ strict: false }) as { tenantId: string };
  return <Navigate to={`/t/${tenantId}/home`} replace />;
} });
const tenantPageRoute = createRoute({ getParentRoute: () => rootRoute, path: '/t/$tenantId/$page', component: TenantPage });
const tenantPageIdRoute = createRoute({ getParentRoute: () => rootRoute, path: '/t/$tenantId/$page/$id', component: TenantPage });

// Public account screens: rendered outside WorkspaceProvider, so they never request /me.
const loginRoute = createRoute({ getParentRoute: () => rootRoute, path: '/login', component: LoginPage });
const signupRoute = createRoute({ getParentRoute: () => rootRoute, path: '/signup', component: SignupPage });
const inviteRoute = createRoute({ getParentRoute: () => rootRoute, path: '/invite/$token', component: InvitePage });
const sessionExpiredRoute = createRoute({ getParentRoute: () => rootRoute, path: '/session-expired', component: SessionExpiredPage });

const routeTree = rootRoute.addChildren([loginRoute, signupRoute, inviteRoute, sessionExpiredRoute, indexRoute, settingsIndexRoute, settingsRoute, tenantIndexRoute, tenantPageRoute, tenantPageIdRoute]);

export const router = createRouter({
  routeTree,
  defaultNotFoundComponent: () => <main className="main"><NotFound onHome={() => { window.location.assign('/'); }} /></main>,
});

