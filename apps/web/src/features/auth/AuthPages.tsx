import { useEffect, useState, type ReactNode } from 'react';
import { useNavigate, useParams } from '@tanstack/react-router';
import { api, authLoginUrl, getTransport, safeReturnTo } from '@/api/client';
import { ApiRequestError } from '@/api/transport';
import { getLocale, setLocale, useT } from '@/i18n';
import { Icon, logoHtml } from '@/ui/icons';
import { useToast } from '@/ui/toast';

// Public account screens. New screens without a prototype reference (apps/web/docs/NEW-SCREENS.md).
// Credentials are never entered here: sign-in and sign-up hand off to the API's server-side OIDC flow
// (docs/architecture/09-FRONTEND.md §3), which sets the HttpOnly session cookie.

const returnToParam = () => safeReturnTo(new URLSearchParams(window.location.search).get('return_to'));

function AuthFrame({ title, children }: { title: string; children: ReactNode }) {
  const t = useT();
  const [, rerender] = useState(0);
  useEffect(() => { document.title = `${title} - WorkX`; }, [title]);
  return (
    <div className="wx-auth-page">
      <header className="wx-auth-brand">
        <span className="brand-logo" aria-hidden="true" dangerouslySetInnerHTML={logoHtml} />
        <span className="brand-word">WorkX</span>
      </header>
      <main className="wx-auth-center" id="main-content">
        <p className="wx-auth-tagline">{t('web.auth.tagline')}</p>
        <section className="modal wx-auth-card" aria-labelledby="auth-title">
          <div className="modal-header"><h1 id="auth-title">{title}</h1></div>
          <div className="modal-body">{children}</div>
        </section>
        <footer className="wx-auth-footer">
          <span>{t('web.auth.language')}</span>
          <div className="wx-conn-languages" aria-label={t('web.auth.language')}>
            {[['zh-CN', '中文'], ['en', 'English']].map(([locale, label]) => (
              <button key={locale} type="button" data-action="set-language" data-locale={locale} lang={locale} aria-pressed={getLocale() === locale}
                onClick={() => { setLocale(locale); rerender(n => n + 1); }}>{label}</button>
            ))}
          </div>
        </footer>
      </main>
    </div>
  );
}

/** The development adapter has no identity service; say so instead of pretending to sign in. */
function DevNotice() {
  const t = useT();
  return getTransport().runtime.simulated ? <p className="wx-auth-note is-dev" role="note"><Icon name="help" size={15} />{t('web.auth.devNotice')}</p> : null;
}

/** Leaves the SPA for the OIDC flow, or (development adapter) goes straight to the destination. */
function useContinue() {
  const navigate = useNavigate();
  return (intent: 'login' | 'signup', returnTo: string) => {
    if (getTransport().runtime.simulated) void navigate({ to: safeReturnTo(returnTo) });
    else window.location.assign(authLoginUrl(intent, returnTo));
  };
}

const switchLink = (to: string, label: string, returnTo: string) => (
  <a href={`${to}?return_to=${encodeURIComponent(returnTo)}`} data-action="auth-switch">{label}</a>
);

export function LoginPage() {
  const t = useT();
  const proceed = useContinue();
  const returnTo = returnToParam();
  return (
    <AuthFrame title={t('web.auth.loginTitle')}>
      <p className="wx-auth-lead">{t('web.auth.loginBody')}</p>
      <DevNotice />
      <button type="button" className="btn primary" data-action="auth-continue" onClick={() => proceed('login', returnTo)}>{t('web.auth.loginAction')}</button>
      <p className="wx-auth-switch">{t('web.auth.noAccount')}{switchLink('/signup', t('web.auth.toSignup'), returnTo)}</p>
      <p className="wx-auth-note"><Icon name="help" size={15} />{t('web.auth.terms')}</p>
    </AuthFrame>
  );
}

export function SignupPage() {
  const t = useT();
  const proceed = useContinue();
  const returnTo = returnToParam();
  return (
    <AuthFrame title={t('web.auth.signupTitle')}>
      <p className="wx-auth-lead">{t('web.auth.signupBody')}</p>
      <DevNotice />
      <button type="button" className="btn primary" data-action="auth-continue" onClick={() => proceed('signup', returnTo)}>{t('web.auth.signupAction')}</button>
      <p className="wx-auth-switch">{t('web.auth.hasAccount')}{switchLink('/login', t('web.auth.toLogin'), returnTo)}</p>
      <p className="wx-auth-note"><Icon name="help" size={15} />{t('web.auth.terms')}</p>
    </AuthFrame>
  );
}

const INVITE_ERRORS = ['INVITATION_NOT_FOUND', 'INVITATION_EXPIRED', 'INVITATION_CLOSED', 'INVITATION_EMAIL_MISMATCH', 'SEAT_LIMIT_REACHED'];

/**
 * /invite/:token (J2). Acceptance is an explicit action, never a side effect of opening the link.
 * Unauthenticated visitors are offered sign-in/sign-up and come back here afterwards.
 */
export function InvitePage() {
  const t = useT();
  const toast = useToast();
  const navigate = useNavigate();
  const proceed = useContinue();
  const { token } = useParams({ strict: false }) as { token: string };
  const [state, setState] = useState<{ busy: boolean; error: string; needsSignIn: boolean }>({ busy: false, error: '', needsSignIn: false });
  const here = `/invite/${encodeURIComponent(token)}`;
  const accept = async () => {
    setState({ busy: true, error: '', needsSignIn: false });
    try {
      const result = await api.acceptInvitation(token);
      toast(t('web.auth.inviteJoined'));
      void navigate({ to: `/t/${result.tenant_id}/home` });
    } catch (error) {
      const e = error as ApiRequestError;
      if (e.status === 401) setState({ busy: false, error: '', needsSignIn: true });
      else setState({ busy: false, error: INVITE_ERRORS.includes(e.code) ? 'web.auth.' + e.code : 'web.requestFailed', needsSignIn: false });
    }
  };
  return (
    <AuthFrame title={t('web.auth.inviteTitle')}>
      <p className="wx-auth-lead">{t('web.auth.inviteBody')}</p>
      {state.error ? <p className="wx-auth-error" role="alert">{t(state.error)}</p> : null}
      {state.needsSignIn ? (
        <>
          <p className="wx-auth-note" role="status"><Icon name="help" size={15} />{t('web.auth.inviteNeedsSignIn')}</p>
          <button type="button" className="btn primary" data-action="auth-continue" onClick={() => proceed('login', here)}>{t('web.auth.inviteSignIn')}</button>
          <p className="wx-auth-switch">{t('web.auth.noAccount')}{switchLink('/signup', t('web.auth.toSignup'), here)}</p>
        </>
      ) : (
        <>
          <p className="wx-auth-note"><Icon name="users" size={15} />{t('web.auth.inviteEmailHint')}</p>
          <button type="button" className="btn primary" data-action="invite-accept" disabled={state.busy} aria-busy={state.busy} onClick={() => void accept()}>
            {t(state.busy ? 'web.auth.inviteAccepting' : 'web.auth.inviteAccept')}
          </button>
          <button type="button" className="btn" data-action="invite-later" onClick={() => void navigate({ to: '/' })}>{t('web.auth.inviteLater')}</button>
        </>
      )}
    </AuthFrame>
  );
}

/** Shown when a working session is revoked or expires (401 SESSION_REVOKED / UNAUTHENTICATED). */
export function SessionExpiredPage() {
  const t = useT();
  const proceed = useContinue();
  return (
    <AuthFrame title={t('web.auth.expiredTitle')}>
      <p className="wx-auth-lead">{t('web.auth.expiredBody')}</p>
      <DevNotice />
      <button type="button" className="btn primary" data-action="auth-continue" onClick={() => proceed('login', returnToParam())}>{t('web.auth.expiredAction')}</button>
    </AuthFrame>
  );
}
